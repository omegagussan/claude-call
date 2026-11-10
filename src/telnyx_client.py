from typing import Annotated, Any

import httpx
from fastapi import Depends, HTTPException, Request

from src.config import get_worker_setting, settings


class TelnyxClient:
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

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/calls",
                headers=self.headers,
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()
            res_data: dict[str, Any] = response.json()
            return res_data

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

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/calls/{call_control_id}/actions/speak",
                headers=self.headers,
                json=body,
                timeout=10.0,
            )
            response.raise_for_status()
            res_data: dict[str, Any] = response.json()
            return res_data

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

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/calls/{call_control_id}/actions/gather_using_speak",
                headers=self.headers,
                json=body,
                timeout=10.0,
            )
            response.raise_for_status()
            res_data: dict[str, Any] = response.json()
            return res_data

    async def hangup(self, call_control_id: str) -> dict[str, Any]:
        """Hang up a call."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/calls/{call_control_id}/actions/hangup",
                headers=self.headers,
                json={},
                timeout=10.0,
            )
            response.raise_for_status()
            res_data: dict[str, Any] = response.json()
            return res_data


telnyx_client = TelnyxClient()


async def get_telnyx_client(request: Request) -> TelnyxClient:
    env = request.scope.get("env")
    if env is None:
        return TelnyxClient()

    required = ("TELNYX_API_KEY", "TELNYX_CONNECTION_ID", "TELNYX_FROM_NUMBER")
    values = {key: get_worker_setting(env, key) for key in required}
    missing = [key for key, value in values.items() if not isinstance(value, str) or not value.strip()]
    if missing:
        raise HTTPException(status_code=503, detail=f"Missing Worker configuration: {', '.join(missing)}")
    return TelnyxClient(
        api_key=values["TELNYX_API_KEY"],
        connection_id=values["TELNYX_CONNECTION_ID"],
        from_number=values["TELNYX_FROM_NUMBER"],
    )


TelnyxClientDep = Annotated[TelnyxClient, Depends(get_telnyx_client)]
