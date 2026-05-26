from datetime import UTC, datetime, time
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class BookingMode(str, Enum):
    NOTIFY_ONLY = "notify_only"
    AUTO_FIRST = "auto_first"
    AUTO_WINDOW = "auto_window"


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    referral_number: Mapped[str] = mapped_column(String(32), index=True)
    last_name: Mapped[str] = mapped_column(String(255))
    lpu_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lpu_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    lpu_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    patient_first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    patient_middle_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    patient_birthdate: Mapped[str | None] = mapped_column(String(64), nullable=True)
    selected_doctor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    selected_doctor_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_speciality_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    selected_speciality_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    booking_mode: Mapped[str] = mapped_column(String(32), default=BookingMode.NOTIFY_ONLY.value)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    window_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    window_start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    window_end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    window_start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    window_end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class ReferralDoctor(Base):
    __tablename__ = "referral_doctors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referral_id: Mapped[int] = mapped_column(Integer, ForeignKey("referrals.id", ondelete="CASCADE"), index=True)
    doctor_id: Mapped[str] = mapped_column(String(255))
    doctor_name: Mapped[str] = mapped_column(Text)
    speciality_id: Mapped[str] = mapped_column(String(255))
    speciality_name: Mapped[str | None] = mapped_column(Text, nullable=True)


class NotifiedSlot(Base):
    __tablename__ = "notified_slots"
    __table_args__ = (UniqueConstraint("referral_id", "appointment_id", name="uq_referral_appointment"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referral_id: Mapped[int] = mapped_column(Integer, ForeignKey("referrals.id", ondelete="CASCADE"), index=True)
    appointment_id: Mapped[str] = mapped_column(String(255))
    visit_start: Mapped[datetime] = mapped_column(DateTime)
    visit_end: Mapped[datetime] = mapped_column(DateTime)
    room: Mapped[str | None] = mapped_column(String(64), nullable=True)
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class BookingAttempt(Base):
    __tablename__ = "booking_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referral_id: Mapped[int] = mapped_column(Integer, ForeignKey("referrals.id", ondelete="CASCADE"), index=True)
    appointment_id: Mapped[str] = mapped_column(String(255))
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(64))
    error_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class DatabaseRepository:
    def __init__(self, database_url: str):
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, future=True, connect_args=connect_args)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def migrate(self) -> None:
        Base.metadata.create_all(self.engine)

    def _session(self) -> Session:
        return self.session_factory()

    def upsert_user(self, telegram_id: int) -> User:
        with self._session() as session:
            user = session.get(User, telegram_id)
            if user is None:
                user = User(id=telegram_id)
                session.add(user)
            user.updated_at = utc_now()
            session.commit()
            return user

    def delete_user(self, telegram_id: int) -> None:
        with self._session() as session:
            user = session.get(User, telegram_id)
            if user is not None:
                session.delete(user)
                session.commit()

    def create_referral(self, user_id: int, referral_number: str, last_name: str) -> Referral:
        with self._session() as session:
            referral = Referral(user_id=user_id, referral_number=referral_number, last_name=last_name)
            session.add(referral)
            session.commit()
            return referral

    def update_referral_from_info(self, referral_id: int, info) -> Referral:
        with self._session() as session:
            referral = session.get(Referral, referral_id)
            if referral is None:
                raise ValueError("referral not found")
            referral.lpu_id = info.lpuId
            referral.lpu_name = info.lpuFullName
            referral.lpu_address = info.lpuAddress
            referral.patient_id = info.patId
            referral.patient_first_name = info.firstName
            referral.patient_middle_name = info.middleName
            referral.patient_birthdate = info.birthDate
            session.query(ReferralDoctor).filter_by(referral_id=referral_id).delete()
            for speciality, doctor in info.iter_doctors():
                session.add(
                    ReferralDoctor(
                        referral_id=referral_id,
                        doctor_id=doctor.id,
                        doctor_name=doctor.name,
                        speciality_id=speciality.id,
                        speciality_name=speciality.name,
                    )
                )
            session.commit()
            return referral

    def list_referral_doctors(self, referral_id: int) -> list[ReferralDoctor]:
        with self._session() as session:
            return list(session.scalars(select(ReferralDoctor).where(ReferralDoctor.referral_id == referral_id)))

    def set_selected_doctor(self, referral_doctor_id: int) -> Referral:
        with self._session() as session:
            doctor = session.get(ReferralDoctor, referral_doctor_id)
            if doctor is None:
                raise ValueError("doctor not found")
            referral = session.get(Referral, doctor.referral_id)
            if referral is None:
                raise ValueError("referral not found")
            referral.selected_doctor_id = doctor.doctor_id
            referral.selected_doctor_name = doctor.doctor_name
            referral.selected_speciality_id = doctor.speciality_id
            referral.selected_speciality_name = doctor.speciality_name
            referral.updated_at = utc_now()
            session.commit()
            return referral

    def get_referral(self, referral_id: int) -> Referral | None:
        with self._session() as session:
            return session.get(Referral, referral_id)

    def list_user_referrals(self, user_id: int) -> list[Referral]:
        with self._session() as session:
            return list(
                session.scalars(
                    select(Referral).where(Referral.user_id == user_id).order_by(Referral.id)
                )
            )

    def list_active_referrals(self) -> list[Referral]:
        with self._session() as session:
            return list(session.scalars(select(Referral).where(Referral.active.is_(True)).order_by(Referral.id)))

    def update_referral_mode(self, referral_id: int, mode: BookingMode | str) -> None:
        with self._session() as session:
            referral = session.get(Referral, referral_id)
            if referral is None:
                raise ValueError("referral not found")
            referral.booking_mode = BookingMode(mode).value
            referral.updated_at = utc_now()
            session.commit()

    def set_daily_window(self, referral_id: int, start: time, end: time) -> None:
        with self._session() as session:
            referral = session.get(Referral, referral_id)
            if referral is None:
                raise ValueError("referral not found")
            referral.window_type = "daily"
            referral.window_start_time = start
            referral.window_end_time = end
            referral.window_start_at = None
            referral.window_end_at = None
            session.commit()

    def set_exact_window(self, referral_id: int, start: datetime, end: datetime) -> None:
        with self._session() as session:
            referral = session.get(Referral, referral_id)
            if referral is None:
                raise ValueError("referral not found")
            referral.window_type = "exact"
            referral.window_start_at = start
            referral.window_end_at = end
            referral.window_start_time = None
            referral.window_end_time = None
            session.commit()

    def clear_window(self, referral_id: int) -> None:
        with self._session() as session:
            referral = session.get(Referral, referral_id)
            if referral is None:
                raise ValueError("referral not found")
            referral.window_type = None
            referral.window_start_time = None
            referral.window_end_time = None
            referral.window_start_at = None
            referral.window_end_at = None
            session.commit()

    def set_referral_active(self, referral_id: int, active: bool, status: str | None = None) -> None:
        with self._session() as session:
            referral = session.get(Referral, referral_id)
            if referral is None:
                raise ValueError("referral not found")
            referral.active = active
            referral.last_status = status
            referral.updated_at = utc_now()
            session.commit()

    def deactivate_referral(self, referral_id: int, status: str | None = None) -> None:
        self.set_referral_active(referral_id, False, status)

    def update_last_status(self, referral_id: int, status: str) -> None:
        with self._session() as session:
            referral = session.get(Referral, referral_id)
            if referral is None:
                raise ValueError("referral not found")
            referral.last_status = status
            referral.updated_at = utc_now()
            session.commit()

    def add_notified_slot(
        self,
        referral_id: int,
        appointment_id: str,
        visit_start: datetime,
        visit_end: datetime,
        room: str | None,
        number: int | None,
        address: str | None,
    ) -> NotifiedSlot:
        with self._session() as session:
            existing = session.scalar(
                select(NotifiedSlot).where(
                    NotifiedSlot.referral_id == referral_id,
                    NotifiedSlot.appointment_id == appointment_id,
                )
            )
            if existing is not None:
                return existing
            item = NotifiedSlot(
                referral_id=referral_id,
                appointment_id=appointment_id,
                visit_start=visit_start,
                visit_end=visit_end,
                room=room,
                number=number,
                address=address,
            )
            session.add(item)
            session.commit()
            return item

    def get_notified_slot(self, slot_id: int) -> NotifiedSlot | None:
        with self._session() as session:
            return session.get(NotifiedSlot, slot_id)

    def list_notified_slots(self, referral_id: int) -> list[NotifiedSlot]:
        with self._session() as session:
            return list(session.scalars(select(NotifiedSlot).where(NotifiedSlot.referral_id == referral_id)))

    def log_booking_attempt(
        self,
        referral_id: int,
        appointment_id: str,
        attempt_number: int,
        status: str,
        error_code: int | None,
        message: str | None,
    ) -> None:
        with self._session() as session:
            session.add(
                BookingAttempt(
                    referral_id=referral_id,
                    appointment_id=appointment_id,
                    attempt_number=attempt_number,
                    status=status,
                    error_code=error_code,
                    message=message,
                )
            )
            session.commit()

    def list_booking_attempts(self, referral_id: int) -> list[BookingAttempt]:
        with self._session() as session:
            return list(
                session.scalars(
                    select(BookingAttempt)
                    .where(BookingAttempt.referral_id == referral_id)
                    .order_by(BookingAttempt.id)
                )
            )
