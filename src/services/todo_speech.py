import re

OPTIONS_PROMPT = "Please say POP to get the oldest item, PUSH followed by your item, or LIST to hear all items."


def parse_todo_intent(speech_text: str) -> tuple[str, str]:
    """
    Parse user speech into (command, argument).
    Commands: POP, PUSH, LIST, or UNKNOWN.
    """
    text = speech_text.strip()
    clean = re.sub(r"[^\w\s]", "", text).strip()
    words = clean.split()

    if not words:
        return ("SILENCE", "")

    first_word = words[0].upper()
    if first_word == "POP":
        return ("POP", "")
    elif first_word == "LIST":
        return ("LIST", "")
    elif first_word == "PUSH":
        # Argument is the rest of the sentence
        item = " ".join(words[1:]).strip()
        return ("PUSH", item)

    # In case word order varies (e.g. "please list", "add with push")
    upper_full = clean.upper()
    if "POP" in upper_full:
        return ("POP", "")
    elif "LIST" in upper_full:
        return ("LIST", "")
    elif "PUSH" in upper_full:
        parts = re.split(r"\bPUSH\b", clean, flags=re.IGNORECASE)
        item = parts[1].strip() if len(parts) > 1 else ""
        return ("PUSH", item)

    return ("UNKNOWN", speech_text)
