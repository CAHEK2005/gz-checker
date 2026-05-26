import pytest
import requests

from gorzdrav.api import GorzdravClient
from gorzdrav.exceptions import GorzdravPermanentError, GorzdravTransientError
from gorzdrav.endpoint import GorzdravEndpoint
from gorzdrav.models import AppointmentCreateRequest


class DummyResponse:
    def __init__(self, data, status_code=200, headers=None):
        self._data = data
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self._data


class DummySession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)


def test_referral_endpoint_normalizes_number():
    assert (
        GorzdravEndpoint.referral("7800-123-456-7890")
        == "https://gorzdrav.spb.ru/_api/api/v2/referral/78001234567890"
    )


def test_get_referral_parses_response_and_stores_token():
    session = DummySession(
        [
            DummyResponse(
                {
                    "success": True,
                    "errorCode": 0,
                    "result": {
                        "lpuId": 42,
                        "lpuFullName": "Поликлиника",
                        "lpuAddress": "СПб",
                        "patId": "patient-1",
                        "lastName": "Иванов",
                        "firstName": "Иван",
                        "middleName": "Иванович",
                        "birthDate": "2000-01-01T00:00:00",
                        "specialities": [
                            {
                                "id": "spec-1",
                                "name": "Терапевт",
                                "doctors": [
                                    {
                                        "id": "doc-1",
                                        "name": "Петров П.П.",
                                        "appointments": [
                                            {
                                                "id": "slot-1",
                                                "visitStart": "2026-06-13T19:00:00",
                                                "visitEnd": "2026-06-13T19:15:00",
                                                "number": 1,
                                                "room": "10",
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    },
                },
                headers={"token": "abc"},
            )
        ]
    )

    client = GorzdravClient(session=session)
    referral = client.get_referral("7800-123-456-7890", "Иванов")

    assert referral.lpuId == 42
    assert referral.specialities[0].doctors[0].appointments[0].id == "slot-1"
    assert client.auth_token == "abc"
    assert session.calls[0][2]["params"] == {"lastName": "Иванов"}


def test_create_appointment_sends_current_token_and_payload():
    session = DummySession([DummyResponse({"success": True, "errorCode": 0, "result": True})])
    client = GorzdravClient(session=session)
    client.auth_token = "abc"

    request = AppointmentCreateRequest(
        lpuId=42,
        patientId="patient-1",
        appointmentId="slot-1",
        referralId="78001234567890",
        patientLastName="Иванов",
        patientFirstName="Иван",
        patientMiddleName="Иванович",
        patientBirthdate="2000-01-01T00:00:00",
        room="10",
        num=1,
        address="СПб",
        visitDate="2026-06-13T19:00:00",
    )

    assert client.create_appointment(request) is True
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url.endswith("/v2/appointment/create")
    assert kwargs["headers"]["token"] == "abc"
    assert kwargs["json"]["appointmentId"] == "slot-1"


@pytest.mark.parametrize(
    "error_code,message",
    [
        (616, "Возникла ошибка в работе медицинской информационной системы. Попробуйте позже."),
        (500, "Попробуйте позже"),
    ],
)
def test_temporary_gorzdrav_errors_are_transient(error_code, message):
    session = DummySession([DummyResponse({"success": False, "errorCode": error_code, "message": message})])
    client = GorzdravClient(session=session)

    with pytest.raises(GorzdravTransientError):
        client.get_referral("78001234567890", "Иванов")


def test_invalid_referral_is_permanent():
    session = DummySession(
        [
            DummyResponse(
                {
                    "success": False,
                    "errorCode": 676,
                    "message": "Направление не найдено",
                }
            )
        ]
    )
    client = GorzdravClient(session=session)

    with pytest.raises(GorzdravPermanentError):
        client.get_referral("78001234567890", "Иванов")
