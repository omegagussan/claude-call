from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Tuple

STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")

# Average Swedish reading speed in speech synthesis: ~130-150 words per minute (~2.2 - 2.5 words/sec),
# or approximately 13-15 characters/second for Swedish TTS including pauses.
SWEDISH_TTS_WORDS_PER_MINUTE = 140.0
BASE_SPEECH_OVERHEAD_SECONDS = 0.5  # Pauses around punctuation / pip beep


def get_stockholm_time(now: datetime | None = None) -> datetime:
    """Return the current datetime in Stockholm timezone."""
    if now is None:
        return datetime.now(STOCKHOLM_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=STOCKHOLM_TZ)
    return now.astimezone(STOCKHOLM_TZ)


def estimate_speech_duration_seconds(text: str, wpm: float = SWEDISH_TTS_WORDS_PER_MINUTE) -> float:
    """
    Estimate how many seconds TTS speech will take to speak a given text.
    Uses word count + punctuation pause overhead.
    """
    words = text.strip().split()
    word_count = len(words)
    if word_count == 0:
        return 0.0

    # Words per minute -> seconds per word
    duration = (word_count / wpm) * 60.0
    # Add minor pause overhead for commas and period
    comma_count = text.count(",")
    period_count = text.count(".")
    duration += comma_count * 0.3 + period_count * 0.4 + BASE_SPEECH_OVERHEAD_SECONDS
    return round(duration, 2)


def format_froken_ur_speech(
    target_time: datetime | None = None,
    lead_time_seconds: float | None = None,
) -> Tuple[str, float]:
    """
    Formats the Fröken Ur announcement for Stockholm time.

    In classic Fröken Ur, the announcement states the time when the pip actually sounds:
    e.g., if it takes ~3.5 seconds to read the phrase, it announces the time (now + lead_time).

    Returns:
        (speech_text, estimated_duration_seconds)
    """
    if target_time is None:
        now = get_stockholm_time()
        # If no explicit lead time provided, estimate typical lead time (~4s)
        lead = lead_time_seconds if lead_time_seconds is not None else 4.0
        target_time = now + timedelta(seconds=lead)
    else:
        target_time = get_stockholm_time(target_time)

    hours = target_time.hour
    minutes = target_time.minute
    seconds = target_time.second

    speech_text = f"Vid ett pip är klockan {hours}, {minutes:02d} och {seconds:02d} sekunder."
    estimated_duration = estimate_speech_duration_seconds(speech_text)

    return speech_text, estimated_duration


def calculate_next_schedule_delay(
    estimated_duration: float,
    pause_between_announcements: float = 3.0,
) -> float:
    """Calculate the scheduling delay after playback starts before triggering the next cycle."""
    return estimated_duration + pause_between_announcements
