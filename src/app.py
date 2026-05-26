import logging

import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from db.repository import BookingMode, DatabaseRepository, Referral
from gorzdrav.api import GorzdravClient
from gorzdrav.endpoint import normalize_referral_number
from gorzdrav.exceptions import GorzdravError
from scheduler import ReferralScheduler
from services.booking import parse_time_window
from telegram_ui import (
    BOT_COMMANDS,
    TEXT,
    main_menu_markup,
    mode_markup,
    referral_actions_markup,
    referral_label,
    referrals_markup,
)


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
    try:
        bot.set_my_commands(BOT_COMMANDS)
    except Exception:
        logging.getLogger(__name__).exception("Failed to set Telegram command menu")
    scheduler = ReferralScheduler(repo, bot, config.checker_interval_secs)
    register_handlers(bot, repo, scheduler)
    return bot, scheduler


def register_handlers(bot: telebot.TeleBot, repo: DatabaseRepository, scheduler: ReferralScheduler) -> None:
    def ensure_user(user_id: int) -> None:
        repo.upsert_user(user_id)

    def send_main_menu(chat_id: int, user_id: int) -> None:
        ensure_user(user_id)
        bot.send_message(
            chat_id,
            "Выберите действие:",
            reply_markup=main_menu_markup(),
        )

    def prompt_referral_input(chat_id: int, user_id: int) -> None:
        ensure_user(user_id)
        pending_actions[user_id] = ("set_referral", None)
        bot.send_message(
            chat_id,
            "Введите номер направления и фамилию одним сообщением.\n"
            "Пример: 7800-123-456-7890 Иванов",
        )

    def show_help(chat_id: int) -> None:
        bot.send_message(
            chat_id,
            "Бот работает через кнопки.\n\n"
            "1. Нажмите «Добавить направление».\n"
            "2. Введите номер направления и фамилию.\n"
            "3. Выберите врача из данных направления.\n"
            "4. Выберите режим записи и при необходимости окно времени.\n\n"
            "Команды в меню Telegram оставлены как быстрые входы в те же кнопочные экраны.",
            reply_markup=main_menu_markup(),
        )

    def show_status(chat_id: int, user_id: int) -> None:
        referrals = repo.list_user_referrals(user_id)
        if not referrals:
            bot.send_message(chat_id, "Направлений нет.", reply_markup=main_menu_markup())
            return
        text = "\n\n".join(format_referral_status(item) for item in referrals)
        bot.send_message(chat_id, text, reply_markup=main_menu_markup())

    def show_referrals(chat_id: int, user_id: int, prefix: str = "ref") -> None:
        referrals = repo.list_user_referrals(user_id)
        if not referrals:
            bot.send_message(chat_id, "Направлений нет.", reply_markup=main_menu_markup())
            return
        bot.send_message(
            chat_id,
            "Выберите направление:",
            reply_markup=referrals_markup(referrals, prefix),
        )

    def show_referral_actions(chat_id: int, referral_id: int) -> None:
        referral = repo.get_referral(referral_id)
        if referral is None:
            bot.send_message(chat_id, "Направление не найдено.", reply_markup=main_menu_markup())
            return
        bot.send_message(
            chat_id,
            format_referral_status(referral),
            reply_markup=referral_actions_markup(referral_id),
        )

    def show_mode_menu(chat_id: int, referral_id: int) -> None:
        bot.send_message(chat_id, "Выберите режим записи:", reply_markup=mode_markup(referral_id))

    @bot.message_handler(commands=["start", "menu"])
    def start(message: Message):
        if not message.from_user:
            return
        send_main_menu(message.chat.id, message.from_user.id)

    @bot.message_handler(commands=["help"])
    def help_message(message: Message):
        show_help(message.chat.id)

    @bot.message_handler(commands=["delete"])
    def delete(message: Message):
        if not message.from_user:
            return
        repo.delete_user(message.from_user.id)
        pending_actions.pop(message.from_user.id, None)
        bot.send_message(message.chat.id, "Профиль и все направления удалены.", reply_markup=main_menu_markup())

    @bot.message_handler(commands=["set_doctor"])
    def set_doctor_legacy(message: Message):
        bot.send_message(
            message.chat.id,
            "Врач выбирается кнопкой из данных направления после добавления направления.",
            reply_markup=main_menu_markup(),
        )

    @bot.message_handler(commands=["set_referral"])
    def set_referral(message: Message):
        if not message.from_user:
            return
        prompt_referral_input(message.chat.id, message.from_user.id)

    @bot.message_handler(commands=["status", "referral_status"])
    def status(message: Message):
        if not message.from_user:
            return
        show_status(message.chat.id, message.from_user.id)

    @bot.message_handler(commands=["booking_mode"])
    def booking_mode(message: Message):
        if not message.from_user:
            return
        show_referrals(message.chat.id, message.from_user.id, "mode_ref")

    @bot.message_handler(commands=["time_window"])
    def time_window(message: Message):
        if not message.from_user:
            return
        show_referrals(message.chat.id, message.from_user.id, "win_ref")

    @bot.message_handler(commands=["on"])
    def monitor_on(message: Message):
        if not message.from_user:
            return
        show_referrals(message.chat.id, message.from_user.id, "on_ref")

    @bot.message_handler(commands=["off"])
    def monitor_off(message: Message):
        if not message.from_user:
            return
        show_referrals(message.chat.id, message.from_user.id, "off_ref")

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("menu:"))
    def menu_callback(call):
        if not call.message:
            return
        action = call.data.split(":", 1)[1]
        bot.answer_callback_query(call.id)
        if action == "main":
            send_main_menu(call.message.chat.id, call.from_user.id)
        elif action == "add_referral":
            prompt_referral_input(call.message.chat.id, call.from_user.id)
        elif action == "referrals":
            show_referrals(call.message.chat.id, call.from_user.id)
        elif action == "status":
            show_status(call.message.chat.id, call.from_user.id)
        elif action == "help":
            show_help(call.message.chat.id)

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("ref:"))
    def referral_callback(call):
        if not call.message:
            return
        referral_id = int(call.data.split(":")[1])
        bot.answer_callback_query(call.id)
        show_referral_actions(call.message.chat.id, referral_id)

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
            bot.send_message(
                message.chat.id,
                "Нужно указать номер и фамилию: 7800-123-456-7890 Иванов",
                reply_markup=main_menu_markup(),
            )
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
            bot.send_message(
                message.chat.id,
                f"Направление сохранено, но Горздрав вернул ошибку: {exc.message}",
                reply_markup=main_menu_markup(),
            )
            return

        doctors = repo.list_referral_doctors(referral.id)
        if not doctors:
            bot.send_message(
                message.chat.id,
                "Направление сохранено, но доступных врачей не найдено.",
                reply_markup=main_menu_markup(),
            )
            return
        markup = InlineKeyboardMarkup()
        for doctor in doctors:
            markup.add(
                InlineKeyboardButton(
                    f"{doctor.doctor_name} ({doctor.speciality_name or doctor.speciality_id})"[:60],
                    callback_data=f"rd:{doctor.id}",
                )
            )
        markup.add(InlineKeyboardButton(TEXT["back"], callback_data="menu:main"))
        bot.send_message(message.chat.id, "Выберите врача по направлению:", reply_markup=markup)

    def handle_window_input(message: Message, referral_id: int):
        assert message.text is not None
        raw = message.text.strip()
        if raw.lower() in {"clear", "сброс", "очистить"}:
            repo.clear_window(referral_id)
            bot.send_message(message.chat.id, "Окно записи очищено.", reply_markup=referral_actions_markup(referral_id))
            return
        try:
            window = parse_time_window(raw)
        except ValueError as exc:
            pending_actions[message.from_user.id] = ("set_window", referral_id)
            bot.send_message(
                message.chat.id,
                f"Не понял окно: {exc}\n"
                "Примеры: 19:00-21:00 или 13.06.2026 19:00-13.06.2026 21:00",
                reply_markup=referral_actions_markup(referral_id),
            )
            return
        if window.window_type == "daily":
            assert window.start_time and window.end_time
            repo.set_daily_window(referral_id, window.start_time, window.end_time)
        else:
            assert window.start_at and window.end_at
            repo.set_exact_window(referral_id, window.start_at, window.end_at)
        bot.send_message(message.chat.id, "Окно записи сохранено.", reply_markup=referral_actions_markup(referral_id))

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("rd:"))
    def select_referral_doctor(call):
        if not call.message:
            return
        doctor_row_id = int(call.data.split(":")[1])
        referral = repo.set_selected_doctor(doctor_row_id)
        bot.answer_callback_query(call.id, "Врач выбран")
        bot.send_message(
            call.message.chat.id,
            f"Врач выбран: {referral.selected_doctor_name}",
            reply_markup=referral_actions_markup(referral.id),
        )

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("mode_ref:"))
    def select_mode_referral(call):
        if not call.message:
            return
        referral_id = int(call.data.split(":")[1])
        bot.answer_callback_query(call.id)
        show_mode_menu(call.message.chat.id, referral_id)

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("mode_set:"))
    def set_mode(call):
        if not call.message:
            return
        _prefix, referral_id_raw, mode = call.data.split(":")
        referral_id = int(referral_id_raw)
        repo.update_referral_mode(referral_id, BookingMode(mode))
        bot.answer_callback_query(call.id, "Режим сохранен")
        text = f"Режим сохранен: {mode}"
        if mode == BookingMode.AUTO_WINDOW.value:
            text += "\nТеперь задайте окно кнопкой «Окно»."
        bot.send_message(call.message.chat.id, text, reply_markup=referral_actions_markup(referral_id))

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("win_ref:"))
    def window_referral(call):
        if not call.message:
            return
        referral_id = int(call.data.split(":")[1])
        pending_actions[call.from_user.id] = ("set_window", referral_id)
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            "Введите окно одним сообщением: 19:00-21:00 или 13.06.2026 19:00-13.06.2026 21:00.\n"
            "Для сброса отправьте clear.",
            reply_markup=referral_actions_markup(referral_id),
        )

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("on_ref:"))
    def enable_referral(call):
        if not call.message:
            return
        referral_id = int(call.data.split(":")[1])
        repo.set_referral_active(referral_id, True, "Мониторинг включен")
        bot.answer_callback_query(call.id, "Мониторинг включен")
        show_referral_actions(call.message.chat.id, referral_id)

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("off_ref:"))
    def disable_referral(call):
        if not call.message:
            return
        referral_id = int(call.data.split(":")[1])
        repo.set_referral_active(referral_id, False, "Мониторинг выключен")
        bot.answer_callback_query(call.id, "Мониторинг выключен")
        show_referral_actions(call.message.chat.id, referral_id)

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("bk:"))
    def book_slot(call):
        if not call.message:
            return
        slot_id = int(call.data.split(":")[1])
        bot.answer_callback_query(call.id, "Пробую записать")
        try:
            _user_id, referral_number = scheduler.book_notified_slot(slot_id)
            bot.send_message(
                call.message.chat.id,
                f"Запрос записи отправлен для направления {referral_number}.",
                reply_markup=main_menu_markup(),
            )
        except Exception as exc:
            bot.send_message(
                call.message.chat.id,
                f"Не удалось записаться: {exc}",
                reply_markup=main_menu_markup(),
            )


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
