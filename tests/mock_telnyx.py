from typing import Any, Dict


def build_telnyx_event(event_type: str, call_control_id: str, to: str = "+15559876543", from_: str = "+15551234567", **extra_payload) -> Dict[str, Any]:
    """Helper to generate realistic Telnyx webhook payloads."""
    payload = {
        "call_control_id": call_control_id,
        "call_leg_id": f"leg_{call_control_id}",
        "call_session_id": f"sess_{call_control_id}",
        "connection_id": "conn_mock_123",
        "to": to,
        "from": from_,
        "state": "active",
        **extra_payload,
    }
    return {
        "data": {
            "event_type": event_type,
            "id": f"evt_{event_type}_{call_control_id}",
            "occurred_at": "2026-11-03T14:00:00.000000Z",
            "record_type": "event",
            "payload": payload,
        }
    }
