from types import SimpleNamespace

from telegram_ui import (
    BOT_COMMANDS,
    main_menu_markup,
    mode_markup,
    referral_actions_markup,
    referral_label,
    referrals_markup,
)


def referral(**kwargs):
    defaults = {
        "id": 1,
        "referral_number": "78001234567890",
        "last_name": "Иванов",
        "selected_doctor_name": "Петров П.П.",
        "active": True,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def button_matrix(markup):
    return [[button.callback_data for button in row] for row in markup.keyboard]


def test_main_menu_has_inline_buttons_for_core_flows():
    markup = main_menu_markup()

    assert button_matrix(markup) == [
        ["menu:add_referral"],
        ["menu:referrals", "menu:status"],
        ["menu:help"],
    ]


def test_bot_commands_populate_telegram_menu():
    assert [command.command for command in BOT_COMMANDS] == [
        "start",
        "menu",
        "set_referral",
        "referral_status",
        "booking_mode",
        "time_window",
        "on",
        "off",
        "help",
    ]


def test_referrals_markup_uses_requested_prefix():
    markup = referrals_markup([referral(id=7)], "mode_ref")

    assert button_matrix(markup) == [["mode_ref:7"], ["menu:main"]]


def test_mode_markup_contains_all_booking_modes_and_back_button():
    markup = mode_markup(referral_id=7)

    assert button_matrix(markup) == [
        ["mode_set:7:notify_only"],
        ["mode_set:7:auto_first"],
        ["mode_set:7:auto_window"],
        ["ref:7"],
    ]


def test_referral_actions_markup_exposes_all_actions():
    markup = referral_actions_markup(referral_id=7)

    assert button_matrix(markup) == [
        ["mode_ref:7", "win_ref:7"],
        ["on_ref:7", "off_ref:7"],
        ["menu:status"],
        ["menu:main"],
    ]


def test_referral_label_contains_number_name_doctor_and_status():
    text = referral_label(referral(active=False, selected_doctor_name=None))

    assert "#1" in text
    assert "78001234567890" in text
    assert "Иванов" in text
    assert "врач не выбран" in text
    assert "выключено" in text
