import logging
from typing import Any

import requests

from .endpoint import GorzdravEndpoint
from .exceptions import GorzdravPermanentError, GorzdravTransientError
from .models import (
    ApiAppointment,
    ApiDistrict,
    ApiDoctor,
    ApiLPU,
    ApiResponse,
    ApiSpecialty,
    AppointmentCreateRequest,
    ReferralInfo,
)

logger = logging.getLogger(__name__)


TRANSIENT_ERROR_CODES = {500, 502, 503, 504, 616}
PERMANENT_ERROR_CODES = {37, 38, 39, 45, 676}
TRANSIENT_MESSAGE_MARKERS = (
    "попробуйте позже",
    "медицинской информационной системы",
    "временно",
    "timeout",
    "temporar",
)


class GorzdravClient:
    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = 20.0,
        headers: dict[str, str] | None = None,
    ):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.headers = headers or {"User-Agent": "gz-checker-referral-bot"}
        self.auth_token = ""

    def _headers(self, include_token: bool = True) -> dict[str, str]:
        headers = dict(self.headers)
        if include_token and self.auth_token:
            headers["token"] = self.auth_token
        return headers

    def _remember_token(self, response: Any) -> None:
        token = getattr(response, "headers", {}).get("token")
        if token is not None:
            self.auth_token = token

    def _classify_error(self, error_code: int | None, message: str | None):
        normalized_message = (message or "").lower()
        if error_code in TRANSIENT_ERROR_CODES or any(
            marker in normalized_message for marker in TRANSIENT_MESSAGE_MARKERS
        ):
            return GorzdravTransientError
        if error_code in PERMANENT_ERROR_CODES:
            return GorzdravPermanentError
        return GorzdravPermanentError

    def _parse_response(self, response: Any) -> Any:
        self._remember_token(response)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            status_code = getattr(exc.response, "status_code", None)
            if status_code == 429 or (status_code is not None and status_code >= 500):
                raise GorzdravTransientError(f"HTTP {status_code}", status_code) from exc
            raise GorzdravPermanentError(f"HTTP {status_code}", status_code) from exc

        payload = ApiResponse(**response.json())
        if payload.success:
            return payload.result

        error_cls = self._classify_error(payload.errorCode, payload.message)
        raise error_cls(payload.message or "Gorzdrav API error", payload.errorCode)

    def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = self.session.get(
                url,
                params=params,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise GorzdravTransientError(str(exc)) from exc
        return self._parse_response(response)

    def _post_json(self, url: str, payload: dict[str, Any]) -> Any:
        try:
            response = self.session.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise GorzdravTransientError(str(exc)) from exc
        return self._parse_response(response)

    def get_districts(self) -> list[ApiDistrict]:
        return [ApiDistrict(**item) for item in self._get(GorzdravEndpoint.districts())]

    def get_lpus(self, district_id: str | None = None) -> list[ApiLPU]:
        return [ApiLPU(**item) for item in self._get(GorzdravEndpoint.lpus(district_id))]

    def get_lpu(self, lpu_id: int) -> ApiLPU:
        return ApiLPU(**self._get(GorzdravEndpoint.lpu(lpu_id)))

    def get_specialties(self, lpu_id: int) -> list[ApiSpecialty]:
        return [ApiSpecialty(**item) for item in self._get(GorzdravEndpoint.specialties(lpu_id))]

    def get_doctors(self, lpu_id: int, specialty_id: str) -> list[ApiDoctor]:
        return [ApiDoctor(**item) for item in self._get(GorzdravEndpoint.doctors(lpu_id, specialty_id))]

    def get_appointments(self, lpu_id: int, doctor_id: str) -> list[ApiAppointment]:
        return [ApiAppointment(**item) for item in self._get(GorzdravEndpoint.appointments(lpu_id, doctor_id))]

    def get_referral(self, referral_number: str, last_name: str) -> ReferralInfo:
        result = self._get(
            GorzdravEndpoint.referral(referral_number),
            params={"lastName": last_name},
        )
        return ReferralInfo(**result)

    def create_appointment(self, request: AppointmentCreateRequest) -> bool:
        payload = request.model_dump(exclude_none=True)
        result = self._post_json(GorzdravEndpoint.appointment_create(), payload)
        return bool(result)
