import logging
from typing import Annotated, Any

import httpx
from fastapi import Depends, HTTPException, Request

from src.config import get_worker_setting, settings

logger = logging.getLogger(__name__)


def provider_error_codes(response: httpx.Response) -> list[str]:
    try:
        data = response.json()
    except ValueError:
        return []
    if not isinstance(data, dict) or not isinstance(data.get("errors"), list):
        return []
    return [
        str(error["code"])
        for error in data["errors"]
        if isinstance(error, dict)
        and isinstance(error.get("code"), (str, int))
        and str(error["code"]).isascii()
        and str(error["code"]).isdigit()
        and len(str(error["code"])) <= 12
    ]


def destination_verification_required(exc: httpx.HTTPStatusError) -> bool:
    if exc.response.status_code != 403 or exc.request.url.path != "/v2/calls":
        return False
    try:
        data = exc.response.json()
    except ValueError:
        return False
    if not isinstance(data, dict) or not isinstance(data.get("errors"), list):
        return False
    return any(
        isinstance(error, dict)
        and str(error.get("code")) == "10010"
        and isinstance(error.get("detail"), str)
        and "can not make calls to non-verified numbers at this account level" in error["detail"].lower()
        for error in data["errors"]
    )


class TelnyxClient:
    async def _request(self, method: str, path: str, body: dict[str, Any] | None, action: str) -> dict[str, Any]:
        logger.info("telnyx_request", extra={"action": action})
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method, f"{self.base_url}{path}", headers=self.headers, json=body, timeout=10.0
                )
        except httpx.RequestError as exc:
            logger.error("telnyx_transport_error", extra={"action": action, "error_type": type(exc).__name__})
            raise

        if response.is_error:
            logger.error(
                "telnyx_rejected",
                extra={
                    "action": action,
                    "status_code": response.status_code,
                    "provider_error_codes": provider_error_codes(response),
                },
            )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        data = result.get("data")
        logger.info(
            "telnyx_completed",
            extra={
                "action": action,
                "status_code": response.status_code,
                "call_control_id": data.get("call_control_id") if isinstance(data, dict) else None,
            },
        )
        return result

    async def _post(self, path: str, body: dict[str, Any], action: str) -> dict[str, Any]:
        return await self._request("POST", path, body, action)

    async def start_number_verification(self, phone_number: str, method: str) -> dict[str, Any]:
        return await self._post(
            "/verified_numbers",
            {"phone_number": phone_number, "verification_method": method},
            "start_number_verification",
        )

    async def confirm_number_verification(self, phone_number: str, code: str) -> dict[str, Any]:
        return await self._post(
            f"/verified_numbers/{phone_number}/actions/verify",
            {"verification_code": code},
            "confirm_number_verification",
        )

    async def number_verification_status(self, phone_number: str) -> dict[str, Any] | None:
        try:
            return await self._request("GET", f"/verified_numbers/{phone_number}", None, "number_verification_status")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        connection_id: str | None = None,
        from_number: str | None = None,
    ):
        self.base_url = (base_url if base_url is not None else settings.telnyx_api_base).rstrip("/")
        self.connection_id = connection_id if connection_id is not None else settings.telnyx_connection_id
        self.from_number = from_number if from_number is not None else settings.telnyx_from_number
        api_key = api_key if api_key is not None else settings.telnyx_api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def dial(
        self,
        to_number: str,
        connection_id: str | None = None,
        client_state: str | None = None,
    ) -> dict[str, Any]:
        """Initiate an outbound call to a landline/PSTN or SIP endpoint."""
        payload: dict[str, Any] = {
            "to": to_number,
            "from": self.from_number,
            "connection_id": connection_id if connection_id is not None else self.connection_id,
        }
        if client_state:
            payload["client_state"] = client_state

        return await self._post("/calls", payload, "dial")

    async def speak(
        self,
        call_control_id: str,
        payload_text: str,
        voice: str = "female",
        language: str = "sv-SE",
        client_state: str | None = None,
    ) -> dict[str, Any]:
        """Instruct Telnyx Call Control to speak text on an active call."""
        body: dict[str, Any] = {
            "payload": payload_text,
            "voice": voice,
            "language": language,
        }
        if client_state:
            body["client_state"] = client_state

        return await self._post(f"/calls/{call_control_id}/actions/speak", body, "speak")

    async def gather_using_speak(
        self,
        call_control_id: str,
        payload_text: str,
        voice: str = "female",
        language: str = "en-US",
        timeout_millis: int = 5000,
        client_state: str | None = None,
    ) -> dict[str, Any]:
        """Play a prompt and gather user input (e.g. speech / DTMF)."""
        body: dict[str, Any] = {
            "payload": payload_text,
            "voice": voice,
            "language": language,
            "timeout_millis": timeout_millis,
        }
        if client_state:
            body["client_state"] = client_state

        return await self._post(f"/calls/{call_control_id}/actions/gather_using_speak", body, "gather_using_speak")

    async def hangup(self, call_control_id: str) -> dict[str, Any]:
        """Hang up a call."""
        return await self._post(f"/calls/{call_control_id}/actions/hangup", {}, "hangup")


telnyx_client = TelnyxClient()


async def get_telnyx_client(request: Request) -> TelnyxClient:
    env = request.scope.get("env")
    if env is None:
        return TelnyxClient()

    required = ("TELNYX_API_KEY", "TELNYX_CONNECTION_ID", "TELNYX_FROM_NUMBER")
    values = {key: get_worker_setting(env, key) for key in required}
    missing = [key for key, value in values.items() if not isinstance(value, str) or not value.strip()]
    if missing:
        logger.error("worker_configuration_missing", extra={"missing_settings": missing})
        raise HTTPException(status_code=503, detail=f"Missing Worker configuration: {', '.join(missing)}")
    return TelnyxClient(
        api_key=values["TELNYX_API_KEY"],
        connection_id=values["TELNYX_CONNECTION_ID"],
        from_number=values["TELNYX_FROM_NUMBER"],
    )


TelnyxClientDep = Annotated[TelnyxClient, Depends(get_telnyx_client)]
