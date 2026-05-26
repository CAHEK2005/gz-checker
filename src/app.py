import logging
from datetime import time as dtime

import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from db.repository import BookingMode, DatabaseRepository, Referral
from gorzdrav.api import GorzdravClient
from gorzdrav.endpoint import normalize_referral_number
from gorzdrav.exceptions import GorzdravError
from scheduler import ReferralScheduler
from services.booking import parse_time_window


pending_actions: dict[int, tuple[str, int | None]] = {}


def build_app():
    config = Config.from_env()
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    repo = DatabaseRepository(config.database_url)
    repo.migrate()
    bot = telebot.TeleBot(config.bot_token)
    scheduler = ReferralScheduler(repo, bot, config.checker_interval_secs)
    register_handlers(bot, repo, scheduler)
    return bot, scheduler


def referral_label(referral: Referral) -> str:
    doctor = referral.selected_doctor_name or "врач не выбран"
    active = "активно" if referral.active else "выключено"
    return f"#{referral.id} {referral.referral_number} ({referral.last_name}), {doctor}, {active}"


def referrals_keyboard(referrals: list[Referral], prefix: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    for referral in referrals:
        markup.add(InlineKeyboardButton(referral_label(referral)[:60], callback_data=f"{prefix}:{referral.id}"))
    return markup


def register_handlers(bot: telebot.TeleBot, repo: DatabaseRepository, scheduler: ReferralScheduler) -> None:
    @bot.message_handler(commands=["start"])
    def start(message: Message):
        if not message.from_user:
            return
        repo.upsert_user(message.from_user.id)
        bot.reply_to(
            message,
            "Профиль создан. Добавьте направление командой /set_referral.\n"
            "Все медицинские данные вводятся в боте и хранятся в PostgreSQL.",
        )

    @bot.message_handler(commands=["help"])
    def help_message(message: Message):
        bot.reply_to(
            message,
            "/set_referral - добавить направление и фамилию\n"
            "/booking_mode - выбрать режим записи\n"
            "/time_window - задать окно для auto_window\n"
            "/referral_status - статус направлений\n"
            "/status - краткий статус\n"
            "/on - включить мониторинг направления\n"
            "/off - выключить мониторинг направления\n"
            "/delete - удалить профиль и все направления\n"
            "/set_doctor - врач выбирается из данных направления после /set_referral",
        )

    @bot.message_handler(commands=["delete"])
    def delete(message: Message):
        if not message.from_user:
            return
        repo.delete_user(message.from_user.id)
        pending_actions.pop(message.from_user.id, None)
        bot.reply_to(message, "Профиль и все направления удалены.")

    @bot.message_handler(commands=["set_doctor"])
    def set_doctor_legacy(message: Message):
        bot.reply_to(message, "Для записи по направлению врач выбирается из доступных врачей после /set_referral.")

    @bot.message_handler(commands=["set_referral"])
    def set_referral(message: Message):
        if not message.from_user:
            return
        repo.upsert_user(message.from_user.id)
        pending_actions[message.from_user.id] = ("set_referral", None)
        bot.reply_to(
            message,
            "Введите номер направления и фамилию через пробел.\n"
            "Пример: 7800-123-456-7890 Иванов",
        )

    @bot.message_handler(commands=["status", "referral_status"])
    def status(message: Message):
        if not message.from_user:
            return
        referrals = repo.list_user_referrals(message.from_user.id)
        if not referrals:
            bot.reply_to(message, "Направлений нет. Добавьте /set_referral.")
            return
        text = "\n\n".join(format_referral_status(item) for item in referrals)
        bot.reply_to(message, text)

    @bot.message_handler(commands=["booking_mode"])
    def booking_mode(message: Message):
        choose_referral_for(message, "mode_ref", "Выберите направление для смены режима записи:")

    @bot.message_handler(commands=["time_window"])
    def time_window(message: Message):
        choose_referral_for(message, "win_ref", "Выберите направление для настройки окна:")

    @bot.message_handler(commands=["on"])
    def monitor_on(message: Message):
        choose_referral_for(message, "on_ref", "Выберите направление для включения мониторинга:")

    @bot.message_handler(commands=["off"])
    def monitor_off(message: Message):
        choose_referral_for(message, "off_ref", "Выберите направление для выключения мониторинга:")

    def choose_referral_for(message: Message, prefix: str, text: str) -> None:
        if not message.from_user:
            return
        referrals = repo.list_user_referrals(message.from_user.id)
        if not referrals:
            bot.reply_to(message, "Направлений нет. Добавьте /set_referral.")
            return
        bot.send_message(message.chat.id, text, reply_markup=referrals_keyboard(referrals, prefix))

    @bot.message_handler(func=lambda message: bool(message.from_user and pending_actions.get(message.from_user.id)))
    def pending_text(message: Message):
        if not message.from_user or not message.text:
            return
        action, referral_id = pending_actions.pop(message.from_user.id)
        if action == "set_referral":
            handle_referral_input(message)
        elif action == "set_window" and referral_id is not None:
            handle_window_input(message, referral_id)

    def handle_referral_input(message: Message):
        assert message.from_user is not None
        assert message.text is not None
        parts = message.text.strip().split(maxsplit=1)
        if len(parts) != 2:
            bot.reply_to(message, "Нужно указать номер и фамилию: 7800-123-456-7890 Иванов")
            return
        referral_number = normalize_referral_number(parts[0])
        last_name = parts[1].strip()
        referral = repo.create_referral(message.from_user.id, referral_number, last_name)
        client = GorzdravClient()
        try:
            info = client.get_referral(referral_number, last_name)
            repo.update_referral_from_info(referral.id, info)
        except GorzdravError as exc:
            repo.update_last_status(referral.id, exc.message)
            bot.reply_to(message, f"Направление сохранено, но Горздрав вернул ошибку: {exc.message}")
            return

        doctors = repo.list_referral_doctors(referral.id)
        if not doctors:
            bot.reply_to(message, "Направление сохранено, но доступных врачей не найдено.")
            return
        markup = InlineKeyboardMarkup()
        for doctor in doctors:
            markup.add(
                InlineKeyboardButton(
                    f"{doctor.doctor_name} ({doctor.speciality_name or doctor.speciality_id})"[:60],
                    callback_data=f"rd:{doctor.id}",
                )
            )
        bot.send_message(message.chat.id, "Выберите врача по направлению:", reply_markup=markup)

    def handle_window_input(message: Message, referral_id: int):
        assert message.text is not None
        raw = message.text.strip()
        if raw.lower() in {"clear", "сброс", "очистить"}:
            repo.clear_window(referral_id)
            bot.reply_to(message, "Окно записи очищено.")
            return
        try:
            window = parse_time_window(raw)
        except ValueError as exc:
            bot.reply_to(
                message,
                f"Не понял окно: {exc}\n"
                "Примеры: 19:00-21:00 или 13.06.2026 19:00-13.06.2026 21:00",
            )
            return
        if window.window_type == "daily":
            assert window.start_time and window.end_time
            repo.set_daily_window(referral_id, window.start_time, window.end_time)
        else:
            assert window.start_at and window.end_at
            repo.set_exact_window(referral_id, window.start_at, window.end_at)
        bot.reply_to(message, "Окно записи сохранено.")

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("rd:"))
    def select_referral_doctor(call):
        doctor_row_id = int(call.data.split(":")[1])
        referral = repo.set_selected_doctor(doctor_row_id)
        bot.answer_callback_query(call.id, "Врач выбран")
        bot.send_message(
            call.message.chat.id,
            f"Врач выбран: {referral.selected_doctor_name}\n"
            "Теперь задайте режим /booking_mode. По умолчанию включен notify_only.",
        )

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("mode_ref:"))
    def select_mode_referral(call):
        referral_id = int(call.data.split(":")[1])
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Уведомлять и выбирать вручную", callback_data=f"mode_set:{referral_id}:notify_only"))
        markup.add(InlineKeyboardButton("Авто: первый доступный", callback_data=f"mode_set:{referral_id}:auto_first"))
        markup.add(InlineKeyboardButton("Авто: по временному окну", callback_data=f"mode_set:{referral_id}:auto_window"))
        bot.send_message(call.message.chat.id, "Выберите режим:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("mode_set:"))
    def set_mode(call):
        _prefix, referral_id_raw, mode = call.data.split(":")
        repo.update_referral_mode(int(referral_id_raw), BookingMode(mode))
        bot.answer_callback_query(call.id, "Режим сохранен")
        if mode == BookingMode.AUTO_WINDOW.value:
            bot.send_message(call.message.chat.id, "Для режима auto_window задайте окно командой /time_window.")
        else:
            bot.send_message(call.message.chat.id, f"Режим сохранен: {mode}")

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("win_ref:"))
    def window_referral(call):
        referral_id = int(call.data.split(":")[1])
        pending_actions[call.from_user.id] = ("set_window", referral_id)
        bot.send_message(
            call.message.chat.id,
            "Введите окно: 19:00-21:00 или 13.06.2026 19:00-13.06.2026 21:00.\n"
            "Для сброса отправьте clear.",
        )

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("on_ref:"))
    def enable_referral(call):
        referral_id = int(call.data.split(":")[1])
        repo.set_referral_active(referral_id, True, "Мониторинг включен")
        bot.answer_callback_query(call.id, "Мониторинг включен")

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("off_ref:"))
    def disable_referral(call):
        referral_id = int(call.data.split(":")[1])
        repo.set_referral_active(referral_id, False, "Мониторинг выключен")
        bot.answer_callback_query(call.id, "Мониторинг выключен")

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("bk:"))
    def book_slot(call):
        slot_id = int(call.data.split(":")[1])
        bot.answer_callback_query(call.id, "Пробую записать")
        try:
            _user_id, referral_number = scheduler.book_notified_slot(slot_id)
            bot.send_message(call.message.chat.id, f"Запрос записи отправлен для направления {referral_number}.")
        except Exception as exc:
            bot.send_message(call.message.chat.id, f"Не удалось записаться: {exc}")


def format_referral_status(referral: Referral) -> str:
    window = "не задано"
    if referral.window_type == "daily":
        window = f"{referral.window_start_time:%H:%M}-{referral.window_end_time:%H:%M}"
    elif referral.window_type == "exact":
        window = f"{referral.window_start_at:%d.%m.%Y %H:%M}-{referral.window_end_at:%d.%m.%Y %H:%M}"
    return (
        f"{referral_label(referral)}\n"
        f"Режим: {referral.booking_mode}\n"
        f"Окно: {window}\n"
        f"Последний статус: {referral.last_status or 'нет'}"
    )


if __name__ == "__main__":
    bot_app, app_scheduler = build_app()
    app_scheduler.start_background()
    bot_app.infinity_polling(skip_pending=True)
