"""Local CLI dry-run simulator for Telnyx calls without needing public webhooks or live credit."""

import asyncio
import httpx
from tests.mock_telnyx import build_telnyx_event

BASE_URL = "http://127.0.0.1:8000"


async def run_simulation(target_phone: str = "+15551234567"):
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        print(f"[*] Step 1: Requesting outbound call to landline: {target_phone}...")
        try:
            dial_resp = await client.post("/calls/dial", json={"to_number": target_phone})
            dial_resp.raise_for_status()
        except httpx.ConnectError:
            print("[!] Could not connect to FastAPI server. Make sure `uv run uvicorn main:app` is running.")
            return

        call_data = dial_resp.json()
        call_control_id = call_data["call_control_id"]
        print(f"[+] Call initiated successfully! call_control_id = {call_control_id}")

        await asyncio.sleep(1)

        print("[*] Step 2: Simulating Telnyx webhook -> 'call.initiated' (SIP signaling / Landline ringing)...")
        wh1 = await client.post("/webhooks/telnyx", json=build_telnyx_event("call.initiated", call_control_id))
        print(f"[+] Webhook response: {wh1.json()}")

        await asyncio.sleep(1.5)

        print("[*] Step 3: Simulating Telnyx webhook -> 'call.answered' (Landline picked up)...")
        wh2 = await client.post("/webhooks/telnyx", json=build_telnyx_event("call.answered", call_control_id))
        print(f"[+] Webhook response: {wh2.json()}")

        await asyncio.sleep(2)

        print("[*] Step 4: Simulating Telnyx webhook -> 'call.speak.ended' (TTS finished playing)...")
        wh3 = await client.post("/webhooks/telnyx", json=build_telnyx_event("call.speak.ended", call_control_id))
        print(f"[+] Webhook response: {wh3.json()}")

        await asyncio.sleep(1)

        print("[*] Step 5: Simulating Telnyx webhook -> 'call.hangup' (Call terminated)...")
        wh4 = await client.post(
            "/webhooks/telnyx",
            json=build_telnyx_event("call.hangup", call_control_id, hangup_reason="normal_clearing"),
        )
        print(f"[+] Webhook response: {wh4.json()}")

        # Check final status
        status_resp = await client.get(f"/calls/{call_control_id}")
        print(f"\n[+] Final Call State in FastAPI: {status_resp.json()}")


if __name__ == "__main__":
    asyncio.run(run_simulation())
