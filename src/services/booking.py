import random
import time
from dataclasses import dataclass
from datetime import datetime, time as dtime
from enum import Enum
from typing import Callable

from gorzdrav.endpoint import normalize_referral_number
from gorzdrav.exceptions import GorzdravPermanentError, GorzdravTransientError
from gorzdrav.models import ApiAppointment, AppointmentCreateRequest, ReferralInfo


class BookingMode(str, Enum):
    NOTIFY_ONLY = "notify_only"
    AUTO_FIRST = "auto_first"
    AUTO_WINDOW = "auto_window"


@dataclass(frozen=True)
class TimeWindow:
    window_type: str
    start_time: dtime | None = None
    end_time: dtime | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None

    @classmethod
    def daily(cls, start: str, end: str) -> "TimeWindow":
        return cls(
            window_type="daily",
            start_time=dtime.fromisoformat(start),
            end_time=dtime.fromisoformat(end),
        )

    @classmethod
    def exact(cls, start: datetime, end: datetime) -> "TimeWindow":
        return cls(window_type="exact", start_at=start, end_at=end)

    def contains(self, value: datetime) -> bool:
        if self.window_type == "daily":
            assert self.start_time is not None
            assert self.end_time is not None
            current = value.time().replace(second=0, microsecond=0)
            if self.start_time <= self.end_time:
                return self.start_time <= current <= self.end_time
            return current >= self.start_time or current <= self.end_time
        if self.window_type == "exact":
            assert self.start_at is not None
            assert self.end_at is not None
            return self.start_at <= value <= self.end_at
        return False


def parse_time_window(raw: str) -> TimeWindow:
    raw = raw.strip()
    if " " not in raw and len(raw.split("-")) == 2:
        start, end = raw.split("-", 1)
        return TimeWindow.daily(start.strip(), end.strip())

    start_raw, end_raw = raw.split("-", 1)
    return TimeWindow.exact(_parse_ru_datetime(start_raw.strip()), _parse_ru_datetime(end_raw.strip()))


def _parse_ru_datetime(value: str) -> datetime:
    for fmt in ("%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unsupported datetime format: {value}")


def _sorted_appointments(appointments: list[ApiAppointment]) -> list[ApiAppointment]:
    return sorted(appointments, key=lambda item: item.visitStart)


def select_appointment(
    appointments: list[ApiAppointment],
    mode: BookingMode | str,
    window: TimeWindow | None = None,
) -> ApiAppointment | None:
    parsed_mode = BookingMode(mode)
    sorted_items = _sorted_appointments(appointments)
    if parsed_mode == BookingMode.NOTIFY_ONLY:
        return None
    if parsed_mode == BookingMode.AUTO_FIRST:
        return sorted_items[0] if sorted_items else None
    if parsed_mode == BookingMode.AUTO_WINDOW:
        if window is None:
            return None
        return next((item for item in sorted_items if window.contains(item.visitStart)), None)
    return None


def build_appointment_request(
    referral: ReferralInfo,
    appointment: ApiAppointment,
    referral_number: str,
) -> AppointmentCreateRequest:
    address = appointment.address or referral.lpuAddress
    return AppointmentCreateRequest(
        lpuId=referral.lpuId,
        patientId=referral.patId,
        appointmentId=appointment.id,
        referralId=normalize_referral_number(referral_number),
        recipientEmail=referral.email,
        patientLastName=referral.lastName,
        patientFirstName=referral.firstName,
        patientMiddleName=referral.middleName,
        patientBirthdate=referral.birthDate,
        room=appointment.room,
        num=appointment.number,
        address=address,
        visitDate=appointment.visitStart.isoformat(),
    )


def book_with_retry(
    create: Callable[[object], bool],
    payload: object,
    *,
    attempts: int = 6,
    delays: tuple[float, ...] = (1, 2, 3, 5, 8),
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = lambda: random.uniform(0, 0.3),
    on_attempt: Callable[[int, str, int | None, str | None], None] | None = None,
) -> bool:
    last_error: GorzdravTransientError | None = None
    for attempt in range(1, attempts + 1):
        try:
            result = create(payload)
            if on_attempt:
                on_attempt(attempt, "success", None, None)
            return result
        except GorzdravPermanentError as exc:
            if on_attempt:
                on_attempt(attempt, "permanent_error", exc.error_code, exc.message)
            raise
        except GorzdravTransientError as exc:
            last_error = exc
            if on_attempt:
                on_attempt(attempt, "retry" if attempt < attempts else "failed", exc.error_code, exc.message)
            if attempt >= attempts:
                raise
            delay = delays[min(attempt - 1, len(delays) - 1)] + jitter()
            sleep(delay)
    assert last_error is not None
    raise last_error
