"""Unit tests for the analyst helper functions."""

from typing import Any

from app.agents.nodes.analyst_utils import top_expenses
from app.agents.tools.transaction_tools import _format_analysis


def _tx(
    description: str,
    amount: float,
    *,
    tx_type: str = "expense",
    category: str = "otros",
) -> dict[str, Any]:
    return {
        "description": description,
        "amount": amount,
        "transaction_type": tx_type,
        "category": category,
    }


class TestTopExpenses:
    def test_returns_largest_expenses_with_descriptions(self) -> None:
        txs = [
            _tx("montolivo", 40000, category="restaurantes"),
            _tx("nevera", 1200000, category="hogar"),
            _tx("uber", 15000, category="transporte"),
        ]

        result = top_expenses(txs, 2)

        # Sorted by amount desc, each carrying its description and category.
        assert result == [
            ("nevera", 1200000.0, "hogar"),
            ("montolivo", 40000.0, "restaurantes"),
        ]

    def test_excludes_income(self) -> None:
        txs = [
            _tx("salario", 5000000, tx_type="income"),
            _tx("mercado", 200000, category="alimentacion"),
        ]

        assert [row[0] for row in top_expenses(txs, 5)] == ["mercado"]

    def test_respects_the_limit(self) -> None:
        txs = [_tx(f"g{i}", i * 1000) for i in range(1, 11)]

        assert len(top_expenses(txs, 3)) == 3

    def test_missing_description_is_labeled(self) -> None:
        assert top_expenses([_tx("", 50000)], 1)[0][0] == "(sin descripción)"


class TestFormatAnalysis:
    def test_renders_top_expenses_section_with_descriptions(self) -> None:
        output = _format_analysis(
            period="este_mes",
            income=1000.0,
            expenses=600.0,
            by_category={"hogar": 600.0},
            patterns=[],
            top=[("nevera", 600.0, "hogar")],
        )

        assert "Mayores gastos individuales" in output
        assert "nevera" in output

    def test_omits_top_expenses_section_when_empty(self) -> None:
        output = _format_analysis(
            period="este_mes",
            income=0.0,
            expenses=0.0,
            by_category={},
            patterns=[],
            top=[],
        )

        assert "Mayores gastos individuales" not in output
