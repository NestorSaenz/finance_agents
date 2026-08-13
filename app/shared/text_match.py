"""Accent- and inflection-tolerant name matching shared across resolvers.

Centralizes the fuzzy name logic that goals, budgets, cards and the movement
finder use, so a query like "emergencias" still resolves the stored "Fondo de
emergencia" (singular/plural, accents, small typos) without a short generic word
swallowing an unrelated name. Previously each resolver reimplemented a subset of
this (goals matched whole words for exact equality — so "emergencia" ≠
"emergencias"; cards had fuzzy matching but no accent stripping), which is the
gap that made Astrid's "fondo de emergencia" (sin s) fail to resolve.
"""

import unicodedata
from difflib import SequenceMatcher
from typing import Final

# Filler words ignored when comparing multi-word names (de/la/para…), so
# "vacaciones de la playa" still matches "vacaciones playa".
_FILLER_WORDS: Final[frozenset[str]] = frozenset(
    {"de", "la", "el", "los", "las", "para", "un", "una", "del", "al", "mi", "mis", "y", "con"}
)

# Per-word similarity to treat two words as the same (plural/typo tolerant):
# "emergencia"≈"emergencias", "imprevistos"≈"improvistos". High enough that
# distinct words ("carro" vs "casa") don't collide.
_WORD_SIMILARITY: Final[float] = 0.82

# Minimum word length before fuzzy similarity applies. Shorter words must match
# exactly, so a 3-letter word ("gym") can't fuzzily swallow an unrelated one.
_MIN_FUZZY_LEN: Final[int] = 4


def normalize(text: str) -> str:
    """Lowercase and strip accents so 'Buñuelos'/'bunuelos' compare equal."""
    decomposed = unicodedata.normalize("NFKD", text.lower().strip())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def significant_words(text: str) -> list[str]:
    """The meaningful, accent-stripped words of ``text`` (filler removed)."""
    return [w for w in normalize(text).split() if w and w not in _FILLER_WORDS]


def _word_matches(a: str, b: str) -> bool:
    """True if two words are equal or close enough (plural/typo tolerant)."""
    if a == b:
        return True
    # Short words must match exactly; fuzzy only helps longer words so a tiny
    # word can't fuzzily swallow an unrelated one.
    if min(len(a), len(b)) < _MIN_FUZZY_LEN:
        return False
    return SequenceMatcher(None, a, b).ratio() >= _WORD_SIMILARITY


def names_match(query: str, stored: str) -> bool:
    """True if ``query`` and ``stored`` name the same thing.

    Accent-insensitive and inflection-tolerant: every significant word of the
    SHORTER side must have a close counterpart on the other, so "emergencias"
    matches "Fondo de emergencia" and vice versa. Filler words are ignored; an
    empty side never matches.
    """
    q = significant_words(query)
    s = significant_words(stored)
    if not q or not s:
        return False
    shorter, longer = (q, s) if len(q) <= len(s) else (s, q)
    return all(any(_word_matches(word, other) for other in longer) for word in shorter)


def contains_normalized(query: str, stored: str) -> bool:
    """Accent-insensitive substring match in either direction (length-guarded).

    The reverse direction (``stored`` inside ``query``) requires ``stored`` be at
    least ``_MIN_FUZZY_LEN`` chars, so a tiny stored value can't match an
    unrelated longer query. Empty inputs never match.
    """
    q = normalize(query)
    s = normalize(stored)
    if not q or not s:
        return False
    return q in s or (len(s) >= _MIN_FUZZY_LEN and s in q)
