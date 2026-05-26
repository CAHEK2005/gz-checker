from datetime import datetime

import pytest

from gorzdrav.models import ApiAppointment, ReferralDoctor, ReferralInfo, ReferralSpeciality


@pytest.fixture
def referral_fixture() -> ReferralInfo:
    return ReferralInfo(
        lpuId=42,
        lpuFullName="Поликлиника",
        lpuAddress="СПб",
        lpuPhone="+7",
        patId="patient-1",
        lastName="Иванов",
        firstName="Иван",
        middleName="Иванович",
        birthDate="2000-01-01T00:00:00",
        email="patient@example.test",
        homePhoneNumber="+7",
        specialities=[
            ReferralSpeciality(
                id="spec-1",
                name="Терапевт",
                doctors=[
                    ReferralDoctor(
                        id="doc-1",
                        name="Петров П.П.",
                        appointments=[
                            ApiAppointment(
                                id="slot-1",
                                visitStart=datetime(2026, 6, 13, 19, 0),
                                visitEnd=datetime(2026, 6, 13, 19, 15),
                                number=1,
                                room="10",
                                address="СПб",
                            )
                        ],
                    )
                ],
            )
        ],
    )
