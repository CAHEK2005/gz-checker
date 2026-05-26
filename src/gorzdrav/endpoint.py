from urllib.parse import quote


def normalize_referral_number(referral_number: str) -> str:
    return "".join(ch for ch in referral_number if ch.isdigit())


class GorzdravEndpoint:
    API_URL = "https://gorzdrav.spb.ru/_api/api/v2"

    @classmethod
    def districts(cls) -> str:
        return f"{cls.API_URL}/shared/districts"

    @classmethod
    def lpus(cls, district_id: str | None = None) -> str:
        if district_id is None:
            return f"{cls.API_URL}/shared/lpus"
        return f"{cls.API_URL}/shared/district/{district_id}/lpus"

    @classmethod
    def lpu(cls, lpu_id: int) -> str:
        return f"{cls.API_URL}/shared/lpu/{lpu_id}"

    @classmethod
    def specialties(cls, lpu_id: int) -> str:
        return f"{cls.API_URL}/schedule/lpu/{lpu_id}/specialties"

    @classmethod
    def doctors(cls, lpu_id: int, specialty_id: str) -> str:
        return (
            f"{cls.API_URL}/schedule/lpu/{lpu_id}"
            f"/speciality/{quote(str(specialty_id), safe='')}/doctors"
        )

    @classmethod
    def appointments(cls, lpu_id: int, doctor_id: str) -> str:
        return (
            f"{cls.API_URL}/schedule/lpu/{lpu_id}"
            f"/doctor/{quote(str(doctor_id), safe='')}/appointments"
        )

    @classmethod
    def timetable(cls, lpu_id: int, doctor_id: str) -> str:
        return (
            f"{cls.API_URL}/schedule/lpu/{lpu_id}"
            f"/doctor/{quote(str(doctor_id), safe='')}/timetable"
        )

    @classmethod
    def referral(cls, referral_number: str) -> str:
        return f"{cls.API_URL}/referral/{normalize_referral_number(referral_number)}"

    @classmethod
    def appointment_create(cls) -> str:
        return f"{cls.API_URL}/appointment/create"
