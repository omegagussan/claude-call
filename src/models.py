import phonenumbers
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PhoneNumber(BaseModel):
    """International number components, excluding national trunk prefixes."""

    model_config = ConfigDict(extra="forbid")

    country_code: str = Field(pattern=r"^\+[1-9][0-9]{0,2}$", examples=["+46"])
    area_code: str = Field(
        pattern=r"^[0-9]{0,5}$",
        description="Area code (riktnummer) or mobile prefix in international form: 8, not 08.",
        examples=["8"],
    )
    subscriber_number: str = Field(pattern=r"^[0-9]{1,14}$", examples=["12345678"])

    @model_validator(mode="after")
    def validate_number(self) -> "PhoneNumber":
        try:
            parsed = phonenumbers.parse(self.e164, None)
        except phonenumbers.NumberParseException as exc:
            raise ValueError("Invalid international phone number") from exc
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Phone number does not match a valid international numbering plan")
        if phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164) != self.e164:
            raise ValueError("Use international components without a national trunk prefix")
        if str(parsed.country_code) != self.country_code[1:]:
            raise ValueError("Invalid country calling code")
        prefix_length = phonenumbers.length_of_national_destination_code(parsed)
        if len(self.area_code) != prefix_length:
            raise ValueError("Area code must match the number's area code or mobile prefix")
        return self

    @property
    def e164(self) -> str:
        return f"{self.country_code}{self.area_code}{self.subscriber_number}"


class CallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_number: PhoneNumber


class FrokenUrRequest(CallRequest):
    pause_seconds: float = 3.0


class TodoCallRequest(CallRequest):
    pass
