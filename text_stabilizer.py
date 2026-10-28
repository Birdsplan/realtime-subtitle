import re


def remove_repeated_prefix(text, previous_text, max_words=12):
    """Remove a repeated prefix caused by overlapping audio segments."""
    if not text or not previous_text:
        return text

    current_words = text.split()
    previous_words = previous_text.split()
    max_overlap = min(max_words, len(current_words), len(previous_words))

    for overlap in range(max_overlap, 0, -1):
        previous_tail = " ".join(previous_words[-overlap:])
        current_head = " ".join(current_words[:overlap])
        if _normalize(previous_tail) == _normalize(current_head):
            return " ".join(current_words[overlap:]).strip()

    return text


def _normalize(value):
    return re.sub(r"[^\w\s]", "", value).lower().strip()
