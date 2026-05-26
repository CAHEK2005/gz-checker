from datetime import datetime
from types import SimpleNamespace

from gorzdrav.exceptions import GorzdravTransientError
from gorzdrav.models import ApiAppointment, ReferralInfo, ReferralSpeciality, ReferralDoctor
from scheduler import ReferralScheduler


class RepoStub:
    def __init__(self):
        self.statuses = []
        self.attempts = []

    def update_last_status(self, referral_id, status):
        self.statuses.append((referral_id, status))

    def log_booking_attempt(self, referral_id, appointment_id, attempt_number, status, error_code, message):
        self.attempts.append((referral_id, appointment_id, attempt_number, status, error_code, message))

    def deactivate_referral(self, referral_id, status=None):
        self.statuses.append((referral_id, status))


class BotStub:
    def __init__(self):
        self.messages = []

    def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text, kwargs))


class ClientStub:
    def create_appointment(self, _payload):
        raise GorzdravTransientError("temporary overload", error_code=616)


def test_transient_booking_failure_after_retries_is_silent_for_user():
    repo = RepoStub()
    bot = BotStub()
    scheduler = ReferralScheduler(
        repo=repo,
        bot=bot,
        interval_secs=30,
        retry_sleep=lambda _delay: None,
        retry_jitter=lambda: 0,
    )
    referral = SimpleNamespace(id=10, user_id=100, referral_number="78001234567890")
    referral_info = ReferralInfo(
        lpuId=1,
        patId="patient-1",
        lastName="Иванов",
        firstName="Иван",
        middleName="Иванович",
        birthDate="2000-01-01T00:00:00",
        specialities=[
            ReferralSpeciality(
                id="spec-1",
                doctors=[ReferralDoctor(id="doc-1", name="Петров", appointments=[])],
            )
        ],
    )
    appointment = ApiAppointment(
        id="slot-1",
        visitStart=datetime(2026, 6, 13, 19, 0),
        visitEnd=datetime(2026, 6, 13, 19, 15),
    )

    scheduler.book_selected(ClientStub(), referral, referral_info, appointment)

    assert bot.messages == []
    assert repo.statuses[-1] == (10, "Временная ошибка записи: temporary overload")
    assert len(repo.attempts) == 6


class RepoWithActiveReferral(RepoStub):
    def __init__(self, referral):
        super().__init__()
        self.referral = referral
        self.deactivated = []

    def list_active_referrals(self):
        return [self.referral]

    def deactivate_referral(self, referral_id, status=None):
        self.deactivated.append((referral_id, status))
        super().deactivate_referral(referral_id, status)


class FailingClientFactory:
    def __init__(self, exc):
        self.exc = exc

    def __call__(self):
        return self

    def get_referral(self, _referral_number, _last_name):
        raise self.exc


def active_referral():
    return SimpleNamespace(
        id=10,
        user_id=100,
        referral_number="78001234567890",
        last_name="Иванов",
        selected_doctor_id="doc-1",
    )


def test_referral_lookup_transient_error_updates_status_without_error_log_or_user_message(caplog):
    repo = RepoWithActiveReferral(active_referral())
    bot = BotStub()
    scheduler = ReferralScheduler(
        repo=repo,
        bot=bot,
        interval_secs=30,
        client_factory=FailingClientFactory(GorzdravTransientError("read timeout")),
    )

    scheduler.check_once()

    assert bot.messages == []
    assert repo.statuses[-1] == (10, "Временная ошибка проверки направления: read timeout")
    assert not [record for record in caplog.records if record.levelname == "ERROR"]


def test_no_schedule_response_updates_status_without_error_log_or_user_message(caplog):
    from gorzdrav.exceptions import GorzdravPermanentError

    message = "В настоящее время в медицинской организации отсутствуют врачи с доступным расписанием"
    repo = RepoWithActiveReferral(active_referral())
    bot = BotStub()
    scheduler = ReferralScheduler(
        repo=repo,
        bot=bot,
        interval_secs=30,
        client_factory=FailingClientFactory(GorzdravPermanentError(message)),
    )

    scheduler.check_once()

    assert bot.messages == []
    assert repo.statuses[-1] == (10, f"Проверка направления: {message}")
    assert repo.deactivated == []
    assert not [record for record in caplog.records if record.levelname == "ERROR"]


def test_invalid_referral_is_deactivated_without_error_log_or_user_message(caplog):
    from gorzdrav.exceptions import GorzdravPermanentError

    repo = RepoWithActiveReferral(active_referral())
    bot = BotStub()
    scheduler = ReferralScheduler(
        repo=repo,
        bot=bot,
        interval_secs=30,
        client_factory=FailingClientFactory(GorzdravPermanentError("Направление не найдено", error_code=676)),
    )

    scheduler.check_once()

    assert bot.messages == []
    assert repo.deactivated == [(10, "Направление недействительно: Направление не найдено")]
    assert not [record for record in caplog.records if record.levelname == "ERROR"]
