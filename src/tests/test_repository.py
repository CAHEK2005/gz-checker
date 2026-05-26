from datetime import datetime, time

from db.repository import BookingMode, DatabaseRepository


def test_user_can_store_multiple_referrals(tmp_path):
    repo = DatabaseRepository(f"sqlite:///{tmp_path / 'test.db'}")
    repo.migrate()
    repo.upsert_user(telegram_id=100)

    first = repo.create_referral(100, "78001234567890", "Иванов")
    second = repo.create_referral(100, "78001234567891", "Петров")

    referrals = repo.list_user_referrals(100)

    assert [r.id for r in referrals] == [first.id, second.id]


def test_referral_mode_and_daily_window_are_saved(tmp_path):
    repo = DatabaseRepository(f"sqlite:///{tmp_path / 'test.db'}")
    repo.migrate()
    repo.upsert_user(telegram_id=100)
    referral = repo.create_referral(100, "78001234567890", "Иванов")

    repo.update_referral_mode(referral.id, BookingMode.AUTO_WINDOW)
    repo.set_daily_window(referral.id, time(19, 0), time(21, 0))

    saved = repo.get_referral(referral.id)

    assert saved is not None
    assert saved.booking_mode == BookingMode.AUTO_WINDOW.value
    assert saved.window_type == "daily"
    assert saved.window_start_time == time(19, 0)


def test_successful_booking_deactivates_only_that_referral(tmp_path):
    repo = DatabaseRepository(f"sqlite:///{tmp_path / 'test.db'}")
    repo.migrate()
    repo.upsert_user(telegram_id=100)
    first = repo.create_referral(100, "78001234567890", "Иванов")
    second = repo.create_referral(100, "78001234567891", "Петров")

    repo.deactivate_referral(first.id, "booked")

    assert repo.get_referral(first.id).active is False
    assert repo.get_referral(second.id).active is True


def test_notified_slot_dedupe(tmp_path):
    repo = DatabaseRepository(f"sqlite:///{tmp_path / 'test.db'}")
    repo.migrate()
    repo.upsert_user(telegram_id=100)
    referral = repo.create_referral(100, "78001234567890", "Иванов")

    first = repo.add_notified_slot(
        referral.id,
        appointment_id="slot-1",
        visit_start=datetime(2026, 6, 13, 19, 0),
        visit_end=datetime(2026, 6, 13, 19, 15),
        room="10",
        number=1,
        address="СПб",
    )
    second = repo.add_notified_slot(
        referral.id,
        appointment_id="slot-1",
        visit_start=datetime(2026, 6, 13, 19, 0),
        visit_end=datetime(2026, 6, 13, 19, 15),
        room="10",
        number=1,
        address="СПб",
    )

    assert first.id == second.id
    assert len(repo.list_notified_slots(referral.id)) == 1


def test_booking_attempts_are_logged(tmp_path):
    repo = DatabaseRepository(f"sqlite:///{tmp_path / 'test.db'}")
    repo.migrate()
    repo.upsert_user(telegram_id=100)
    referral = repo.create_referral(100, "78001234567890", "Иванов")

    repo.log_booking_attempt(referral.id, "slot-1", 1, "retry", 616, "temporary")

    attempts = repo.list_booking_attempts(referral.id)
    assert attempts[0].attempt_number == 1
    assert attempts[0].status == "retry"
