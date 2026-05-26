from datetime import datetime

import pytest

from gorzdrav.exceptions import GorzdravPermanentError, GorzdravTransientError
from gorzdrav.models import ApiAppointment
from services.booking import (
    BookingMode,
    TimeWindow,
    book_with_retry,
    build_appointment_request,
    parse_time_window,
    select_appointment,
)


def slot(slot_id: str, start: str) -> ApiAppointment:
    return ApiAppointment(
        id=slot_id,
        visitStart=datetime.fromisoformat(start),
        visitEnd=datetime.fromisoformat(start),
        number=1,
        room="10",
        address="СПб",
    )


def test_auto_first_selects_earliest_slot():
    slots = [
        slot("late", "2026-06-13T20:00:00"),
        slot("early", "2026-06-13T19:00:00"),
    ]

    selected = select_appointment(slots, BookingMode.AUTO_FIRST)

    assert selected is not None
    assert selected.id == "early"


def test_daily_window_selects_first_slot_inside_time_range():
    slots = [
        slot("too-early", "2026-06-13T18:00:00"),
        slot("match", "2026-06-13T19:00:00"),
        slot("later", "2026-06-13T20:00:00"),
    ]
    window = parse_time_window("19:00-21:00")

    selected = select_appointment(slots, BookingMode.AUTO_WINDOW, window)

    assert selected is not None
    assert selected.id == "match"
    assert window.window_type == "daily"


def test_exact_window_selects_slot_inside_datetime_range():
    slots = [
        slot("wrong-date", "2026-06-12T19:30:00"),
        slot("match", "2026-06-13T19:30:00"),
    ]
    window = parse_time_window("13.06.2026 19:00-13.06.2026 21:00")

    selected = select_appointment(slots, BookingMode.AUTO_WINDOW, window)

    assert selected is not None
    assert selected.id == "match"
    assert window.window_type == "exact"


def test_window_returns_none_when_no_slot_matches():
    slots = [slot("early", "2026-06-13T18:00:00")]

    assert select_appointment(slots, BookingMode.AUTO_WINDOW, TimeWindow.daily("19:00", "21:00")) is None


def test_booking_retries_transient_errors_until_success():
    attempts = []

    def create(_payload):
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            raise GorzdravTransientError("temporary", error_code=616)
        return True

    result = book_with_retry(create, object(), sleep=lambda _delay: None, jitter=lambda: 0)

    assert result is True
    assert attempts == [1, 2, 3]


def test_booking_stops_after_six_transient_attempts():
    attempts = []

    def create(_payload):
        attempts.append(len(attempts) + 1)
        raise GorzdravTransientError("temporary", error_code=616)

    with pytest.raises(GorzdravTransientError):
        book_with_retry(create, object(), sleep=lambda _delay: None, jitter=lambda: 0)

    assert attempts == [1, 2, 3, 4, 5, 6]


def test_booking_does_not_retry_permanent_error():
    attempts = []

    def create(_payload):
        attempts.append(1)
        raise GorzdravPermanentError("bad referral", error_code=676)

    with pytest.raises(GorzdravPermanentError):
        book_with_retry(create, object(), sleep=lambda _delay: None, jitter=lambda: 0)

    assert attempts == [1]


def test_build_appointment_request_uses_referral_patient_and_slot_data(referral_fixture):
    request = build_appointment_request(
        referral=referral_fixture,
        appointment=referral_fixture.specialities[0].doctors[0].appointments[0],
        referral_number="7800-123-456-7890",
    )

    assert request.referralId == "78001234567890"
    assert request.patientId == "patient-1"
    assert request.appointmentId == "slot-1"
