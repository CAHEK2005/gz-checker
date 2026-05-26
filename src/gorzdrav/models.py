from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class ApiResponse(ApiModel):
    success: bool
    errorCode: int = 0
    message: str | None = None
    result: Any | None = None
    requestId: str | None = None


class ApiDistrict(ApiModel):
    id: str
    name: str


class ApiLPU(ApiModel):
    id: int
    address: str | None = None
    lpuFullName: str | None = None
    lpuShortName: str | None = None


class ApiSpecialty(ApiModel):
    id: str
    name: str | None = None
    countFreeParticipant: int | None = None
    countFreeTicket: int | None = None


class ApiDoctor(ApiModel):
    id: str
    name: str
    freeParticipantCount: int = 0
    freeTicketCount: int = 0
    ariaNumber: str | None = None


class ApiAppointment(ApiModel):
    id: str
    visitStart: datetime
    visitEnd: datetime
    number: int | None = None
    room: str | None = None
    address: str | None = None


class ReferralDoctor(ApiModel):
    id: str
    name: str
    ariaNumber: str | None = None
    appointments: list[ApiAppointment] = Field(default_factory=list)


class ReferralSpeciality(ApiModel):
    id: str
    name: str | None = None
    doctors: list[ReferralDoctor] = Field(default_factory=list)


class ReferralInfo(ApiModel):
    lpuId: int
    lpuFullName: str | None = None
    lpuAddress: str | None = None
    lpuPhone: str | None = None
    patId: str
    lastName: str
    firstName: str | None = None
    middleName: str | None = None
    birthDate: str
    email: str | None = None
    homePhoneNumber: str | None = None
    specialities: list[ReferralSpeciality] = Field(default_factory=list)

    def iter_doctors(self):
        for speciality in self.specialities:
            for doctor in speciality.doctors:
                yield speciality, doctor


class AppointmentCreateRequest(ApiModel):
    lpuId: int
    patientId: str
    appointmentId: str
    referralId: str
    patientLastName: str
    patientFirstName: str | None = None
    patientMiddleName: str | None = None
    patientBirthdate: str
    room: str | None = None
    num: int | None = None
    address: str | None = None
    visitDate: str
    esiaId: str | None = None
    userFullName: str | None = None
    userSnils: str | None = None
    userBirthDate: str | None = None
    ipmpiCardId: str | None = None
    recipientEmail: str | None = None
