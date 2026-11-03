from typing import Any

import httpx

from src.config import settings


class TelnyxClient:
    def __init__(self, api_key: str = settings.telnyx_api_key, base_url: str = settings.telnyx_api_base):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def dial(
        self,
        to_number: str,
        from_number: str = settings.telnyx_from_number,
        connection_id: str = settings.telnyx_connection_id,
        webhook_url: str | None = None,
        client_state: str | None = None,
    ) -> dict[str, Any]:
        """Initiate an outbound call to a landline/PSTN or SIP endpoint."""
        payload: dict[str, Any] = {
            "to": to_number,
            "from": from_number,
            "connection_id": connection_id,
        }
        if webhook_url:
            payload["webhook_url"] = webhook_url
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
