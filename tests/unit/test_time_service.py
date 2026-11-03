from datetime import datetime
from zoneinfo import ZoneInfo
from src.services.time_service import (
    format_froken_ur_speech,
    get_stockholm_time,
    estimate_speech_duration_seconds,
    calculate_next_schedule_delay,
)


def test_get_stockholm_time():
    utc_dt = datetime(2026, 11, 3, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    stockholm_dt = get_stockholm_time(utc_dt)
    assert stockholm_dt.hour == 13
    assert stockholm_dt.minute == 0


def test_format_froken_ur_speech():
    dt = datetime(2026, 11, 3, 14, 5, 9, tzinfo=ZoneInfo("Europe/Stockholm"))
    speech, est_duration = format_froken_ur_speech(target_time=dt)
    assert speech == "Vid ett pip är klockan 14, 05 och 09 sekunder."
    assert 3.0 <= est_duration <= 6.0


def test_estimate_speech_duration_and_scheduling():
    text = "Vid ett pip är klockan 14, 05 och 09 sekunder."
    duration = estimate_speech_duration_seconds(text)
    assert duration > 0

    next_delay = calculate_next_schedule_delay(estimated_duration=duration, pause_between_announcements=3.0)
    assert next_delay == duration + 3.0
