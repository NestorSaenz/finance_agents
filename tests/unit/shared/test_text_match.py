"""Unit tests for the shared name-matching helpers."""

from app.shared.text_match import (
    contains_normalized,
    names_match,
    normalize,
    significant_words,
)


def test_normalize_strips_accents_and_case() -> None:
    assert normalize("  Buñuelos ") == "bunuelos"
    assert normalize("EMERGENCIA") == "emergencia"


def test_significant_words_drops_filler() -> None:
    assert significant_words("Fondo de la emergencia") == ["fondo", "emergencia"]


def test_names_match_singular_plural() -> None:
    # The reported bug: "emergencias" must resolve "Fondo de emergencia".
    assert names_match("emergencias", "Fondo de emergencia")
    assert names_match("emergencia", "Fondo de emergencias")


def test_names_match_accents_and_typos() -> None:
    assert names_match("vacaciones playa", "Vacaciones de la playa")
    assert names_match("imprevistos", "improvistos")  # typo tolerance


def test_names_match_rejects_unrelated() -> None:
    assert not names_match("carro", "Fondo de emergencia")
    assert not names_match("casa", "carro")


def test_names_match_short_word_does_not_overmatch() -> None:
    # A 3-letter word must match exactly, so "gym" can't swallow "gimnasio".
    assert not names_match("gym", "gimnasio mensual")
    assert names_match("gimnasio", "gimnasio mensual")


def test_names_match_empty_never_matches() -> None:
    assert not names_match("", "meta")
    assert not names_match("meta", "")


def test_contains_normalized_both_directions() -> None:
    assert contains_normalized("merca", "Merca Facil")  # query inside stored
    assert contains_normalized("Envío a Venezuela", "venezuela")  # stored inside query


def test_contains_normalized_short_stored_guarded() -> None:
    # A tiny stored value ("nu", 2 chars) must not match an unrelated long query.
    assert not contains_normalized("una compra en un supermercado", "nu")
