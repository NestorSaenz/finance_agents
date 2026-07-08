"""Unit tests for category normalization and validation helpers."""

from app.shared.types import (
    CategoryType,
    is_valid_category,
    normalize_category,
)


class TestNormalizeCategory:
    def test_lowercases_and_trims(self) -> None:
        assert normalize_category("  Alimentación  ") == "alimentación"

    def test_collapses_internal_whitespace(self) -> None:
        assert normalize_category("Servicios   Públicos") == "servicios públicos"

    def test_empty_falls_back_to_otros(self) -> None:
        assert normalize_category("   ") == CategoryType.OTROS.value

    def test_preserves_custom_category(self) -> None:
        # A category outside the canonical enum is kept (just normalized).
        assert normalize_category("Jardinería") == "jardinería"


class TestIsValidCategory:
    def test_true_for_known_category(self) -> None:
        assert is_valid_category("alimentacion") is True

    def test_false_for_custom_category(self) -> None:
        # Custom categories are storable but are not "known" enum values.
        assert is_valid_category("jardineria") is False
