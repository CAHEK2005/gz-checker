import logging
import threading
import time
from datetime import datetime
from typing import Protocol

from db.repository import DatabaseRepository, NotifiedSlot, Referral
from gorzdrav.api import GorzdravClient
from gorzdrav.exceptions import GorzdravError, GorzdravPermanentError, GorzdravTransientError
from gorzdrav.models import ApiAppointment, ReferralInfo
from services.booking import (
    BookingMode,
    TimeWindow,
    book_with_retry,
    build_appointment_request,
    select_appointment,
)

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    def send_message(self, chat_id: int, text: str, **kwargs): ...


def window_from_referral(referral: Referral) -> TimeWindow | None:
    if referral.window_type == "daily" and referral.window_start_time and referral.window_end_time:
        return TimeWindow(
            window_type="daily",
            start_time=referral.window_start_time,
            end_time=referral.window_end_time,
        )
    if referral.window_type == "exact" and referral.window_start_at and referral.window_end_at:
        return TimeWindow.exact(referral.window_start_at, referral.window_end_at)
    return None


def find_referral_doctor(referral_info: ReferralInfo, doctor_id: str | None):
    if not doctor_id:
        return None
    for _speciality, doctor in referral_info.iter_doctors():
        if doctor.id == doctor_id:
            return doctor
    return None


def slot_to_model(slot: NotifiedSlot) -> ApiAppointment:
    return ApiAppointment(
        id=slot.appointment_id,
        visitStart=slot.visit_start,
        visitEnd=slot.visit_end,
        number=slot.number,
        room=slot.room,
        address=slot.address,
    )


class ReferralScheduler:
    def __init__(
        self,
        repo: DatabaseRepository,
        bot: Notifier,
        interval_secs: int,
        client_factory=GorzdravClient,
    ):
        self.repo = repo
        self.bot = bot
        self.interval_secs = interval_secs
        self.client_factory = client_factory
        self._stop_event = threading.Event()

    def start_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.run_forever, name="referral-scheduler", daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self._stop_event.set()

    def run_forever(self) -> None:
        while not self._stop_event.is_set():
            self.check_once()
            self._stop_event.wait(self.interval_secs)

    def check_once(self) -> None:
        for referral in self.repo.list_active_referrals():
            try:
                self.check_referral(referral)
            except Exception:
                logger.exception("Referral check failed for id=%s", referral.id)

    def check_referral(self, referral: Referral) -> None:
        if not referral.selected_doctor_id:
            self.repo.update_last_status(referral.id, "Не выбран врач по направлению")
            return
        client = self.client_factory()
        info = client.get_referral(referral.referral_number, referral.last_name)
        self.repo.update_referral_from_info(referral.id, info)
        doctor = find_referral_doctor(info, referral.selected_doctor_id)
        if doctor is None:
            self.repo.update_last_status(referral.id, "Выбранный врач сейчас недоступен по направлению")
            return

        appointments = doctor.appointments
        if not appointments:
            self.repo.update_last_status(referral.id, f"Свободных талонов нет: {datetime.now():%Y-%m-%d %H:%M}")
            return

        mode = BookingMode(referral.booking_mode)
        if mode == BookingMode.NOTIFY_ONLY:
            self.notify_slots(referral, doctor.name, appointments)
            return

        selected = select_appointment(appointments, mode, window_from_referral(referral))
        if selected is None:
            self.bot.send_message(
                referral.user_id,
                f"По направлению {referral.referral_number} есть талоны, но нет подходящих под выбранное окно.",
            )
            self.repo.update_last_status(referral.id, "Есть талоны, но нет подходящих под окно")
            return

        self.book_selected(client, referral, info, selected)

    def notify_slots(self, referral: Referral, doctor_name: str, appointments: list[ApiAppointment]) -> None:
        from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

        new_slots = []
        for appointment in sorted(appointments, key=lambda item: item.visitStart):
            saved = self.repo.add_notified_slot(
                referral.id,
                appointment_id=appointment.id,
                visit_start=appointment.visitStart,
                visit_end=appointment.visitEnd,
                room=appointment.room,
                number=appointment.number,
                address=appointment.address or referral.lpu_address,
            )
            if saved.created_at.replace(tzinfo=None) >= referral.updated_at.replace(tzinfo=None):
                new_slots.append(saved)

        if not new_slots:
            self.repo.update_last_status(referral.id, "Новых талонов нет")
            return

        markup = InlineKeyboardMarkup()
        for slot in new_slots[:20]:
            text = f"{slot.visit_start:%d.%m %H:%M}"
            if slot.room:
                text += f", каб. {slot.room}"
            markup.add(InlineKeyboardButton(text=text, callback_data=f"bk:{slot.id}"))

        self.bot.send_message(
            referral.user_id,
            f"Найдены талоны по направлению {referral.referral_number}\nВрач: {doctor_name}",
            reply_markup=markup,
        )
        self.repo.update_last_status(referral.id, f"Отправлено талонов: {len(new_slots)}")

    def book_notified_slot(self, slot_id: int) -> tuple[int, str]:
        slot = self.repo.get_notified_slot(slot_id)
        if slot is None:
            raise ValueError("slot not found")
        referral = self.repo.get_referral(slot.referral_id)
        if referral is None:
            raise ValueError("referral not found")
        client = self.client_factory()
        info = client.get_referral(referral.referral_number, referral.last_name)
        appointment = slot_to_model(slot)
        self.book_selected(client, referral, info, appointment)
        return referral.user_id, referral.referral_number

    def book_selected(
        self,
        client: GorzdravClient,
        referral: Referral,
        info: ReferralInfo,
        appointment: ApiAppointment,
    ) -> None:
        payload = build_appointment_request(info, appointment, referral.referral_number)

        def on_attempt(attempt: int, status: str, error_code: int | None, message: str | None) -> None:
            self.repo.log_booking_attempt(referral.id, appointment.id, attempt, status, error_code, message)

        try:
            book_with_retry(
                client.create_appointment,
                payload,
                on_attempt=on_attempt,
            )
        except GorzdravTransientError as exc:
            self.repo.update_last_status(referral.id, f"Временная ошибка записи: {exc.message}")
            self.bot.send_message(
                referral.user_id,
                f"Не удалось записаться после 6 попыток: {exc.message}\nМониторинг продолжен.",
            )
            return
        except GorzdravPermanentError as exc:
            self.repo.deactivate_referral(referral.id, f"Постоянная ошибка записи: {exc.message}")
            self.bot.send_message(
                referral.user_id,
                f"Запись остановлена для направления {referral.referral_number}: {exc.message}",
            )
            return
        except GorzdravError as exc:
            self.repo.update_last_status(referral.id, f"Ошибка записи: {exc.message}")
            self.bot.send_message(referral.user_id, f"Ошибка записи: {exc.message}")
            return

        self.repo.deactivate_referral(referral.id, "Запись выполнена")
        self.bot.send_message(
            referral.user_id,
            f"Запись выполнена: {appointment.visitStart:%d.%m.%Y %H:%M}\n"
            f"Направление: {referral.referral_number}",
        )
