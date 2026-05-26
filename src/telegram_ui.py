from typing import Iterable, Protocol

from telebot.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup


class ReferralLike(Protocol):
    id: int
    referral_number: str
    last_name: str
    selected_doctor_name: str | None
    active: bool


TEXT = {
    "main_menu": "\u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e",
    "add_referral": "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043d\u0430\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435",
    "my_referrals": "\u041c\u043e\u0438 \u043d\u0430\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u044f",
    "status": "\u0421\u0442\u0430\u0442\u0443\u0441",
    "help": "\u041f\u043e\u043c\u043e\u0449\u044c",
    "back": "\u041d\u0430\u0437\u0430\u0434",
    "notify_only": "\u0423\u0432\u0435\u0434\u043e\u043c\u043b\u044f\u0442\u044c \u0438 \u0432\u044b\u0431\u0438\u0440\u0430\u0442\u044c",
    "auto_first": "\u0410\u0432\u0442\u043e: \u043f\u0435\u0440\u0432\u044b\u0439 \u0442\u0430\u043b\u043e\u043d",
    "auto_window": "\u0410\u0432\u0442\u043e: \u043f\u043e \u043e\u043a\u043d\u0443",
    "mode": "\u0420\u0435\u0436\u0438\u043c",
    "window": "\u041e\u043a\u043d\u043e",
    "enable": "\u0412\u043a\u043b\u044e\u0447\u0438\u0442\u044c",
    "disable": "\u0412\u044b\u043a\u043b\u044e\u0447\u0438\u0442\u044c",
    "doctor_not_selected": "\u0432\u0440\u0430\u0447 \u043d\u0435 \u0432\u044b\u0431\u0440\u0430\u043d",
    "active": "\u0430\u043a\u0442\u0438\u0432\u043d\u043e",
    "inactive": "\u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d\u043e",
}


BOT_COMMANDS = [
    BotCommand("start", "\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u0431\u043e\u0442\u0430"),
    BotCommand("menu", "\u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e"),
    BotCommand("set_referral", "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043d\u0430\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435"),
    BotCommand("referral_status", "\u0421\u0442\u0430\u0442\u0443\u0441 \u043d\u0430\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0439"),
    BotCommand("booking_mode", "\u0420\u0435\u0436\u0438\u043c \u0437\u0430\u043f\u0438\u0441\u0438"),
    BotCommand("time_window", "\u041e\u043a\u043d\u043e \u0430\u0432\u0442\u043e\u0437\u0430\u043f\u0438\u0441\u0438"),
    BotCommand("on", "\u0412\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u043c\u043e\u043d\u0438\u0442\u043e\u0440\u0438\u043d\u0433"),
    BotCommand("off", "\u0412\u044b\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u043c\u043e\u043d\u0438\u0442\u043e\u0440\u0438\u043d\u0433"),
    BotCommand("help", "\u041f\u043e\u043c\u043e\u0449\u044c"),
]


def main_menu_markup() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(TEXT["add_referral"], callback_data="menu:add_referral"))
    markup.add(
        InlineKeyboardButton(TEXT["my_referrals"], callback_data="menu:referrals"),
        InlineKeyboardButton(TEXT["status"], callback_data="menu:status"),
    )
    markup.add(InlineKeyboardButton(TEXT["help"], callback_data="menu:help"))
    return markup


def referral_label(referral: ReferralLike) -> str:
    doctor = referral.selected_doctor_name or TEXT["doctor_not_selected"]
    active = TEXT["active"] if referral.active else TEXT["inactive"]
    return f"#{referral.id} {referral.referral_number} ({referral.last_name}), {doctor}, {active}"


def referrals_markup(referrals: Iterable[ReferralLike], prefix: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    for referral in referrals:
        markup.add(InlineKeyboardButton(referral_label(referral)[:60], callback_data=f"{prefix}:{referral.id}"))
    markup.add(InlineKeyboardButton(TEXT["back"], callback_data="menu:main"))
    return markup


def referral_actions_markup(referral_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton(TEXT["mode"], callback_data=f"mode_ref:{referral_id}"),
        InlineKeyboardButton(TEXT["window"], callback_data=f"win_ref:{referral_id}"),
    )
    markup.add(
        InlineKeyboardButton(TEXT["enable"], callback_data=f"on_ref:{referral_id}"),
        InlineKeyboardButton(TEXT["disable"], callback_data=f"off_ref:{referral_id}"),
    )
    markup.add(InlineKeyboardButton(TEXT["status"], callback_data="menu:status"))
    markup.add(InlineKeyboardButton(TEXT["back"], callback_data="menu:main"))
    return markup


def mode_markup(referral_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(TEXT["notify_only"], callback_data=f"mode_set:{referral_id}:notify_only"))
    markup.add(InlineKeyboardButton(TEXT["auto_first"], callback_data=f"mode_set:{referral_id}:auto_first"))
    markup.add(InlineKeyboardButton(TEXT["auto_window"], callback_data=f"mode_set:{referral_id}:auto_window"))
    markup.add(InlineKeyboardButton(TEXT["back"], callback_data=f"ref:{referral_id}"))
    return markup
