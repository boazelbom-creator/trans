"""Cleaning captured text and computing the duplicate fingerprint (PRD §8.2, §10.2)."""

import hashlib
import re
import unicodedata

# Unicode categories removed by cleaning:
#   So - symbols such as emojis, ✅, ⭐, 📍
#   Sk - modifier symbols such as emoji skin tones
#   Cf - invisible format characters such as direction marks and zero-width spaces
# Variation selectors (e.g. U+FE0F after an emoji) are category Mn, so they are listed explicitly.
_REMOVED_CATEGORIES = {"So", "Sk", "Cf"}
_VARIATION_SELECTORS = {chr(c) for c in range(0xFE00, 0xFE10)}

_SPACES = re.compile(r"[ \t  -   　]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def _keep(ch: str) -> bool:
    if ch in _VARIATION_SELECTORS:
        return False
    return unicodedata.category(ch) not in _REMOVED_CATEGORIES


def clean_text(text: str) -> str:
    """Remove emojis, symbols and invisible characters; tidy spaces and empty lines.

    Hebrew, English, digits, punctuation, emails, phone numbers and links are kept as is.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if _keep(ch) or ch == "\n")
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def fingerprint(text: str) -> str:
    """A hash that is the same for two texts that differ only in spacing, punctuation, emojis or letter case."""
    kept = []
    for ch in unicodedata.normalize("NFC", text):
        cat = unicodedata.category(ch)
        if cat[0] in ("Z", "P") or cat in _REMOVED_CATEGORIES or ch.isspace() or ch in _VARIATION_SELECTORS:
            continue
        kept.append(ch.lower())
    return hashlib.sha256("".join(kept).encode("utf-8")).hexdigest()
