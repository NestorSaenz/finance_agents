"""Unit tests for the false-write-claim guard (pure functions)."""

import time
from dataclasses import fields
from unittest.mock import MagicMock

import pytest
import structlog.testing

from app.agents.nodes.action_claims import (
    DISPATCH_ERROR_PREFIX,
    FALSE_CLAIM_REPLY,
    MUTATING_TOOLS,
    READ_ONLY_TOOLS,
    claims_completed_write,
    enforce_truthful_reply,
    invented_figures,
    is_write_attempt,
)
from app.agents.tools.card_tools import ALREADY_PROPOSED_PREFIX, PROPOSAL_PREFIX
from app.agents.tools.registry import ToolServices, build_composite_toolkit

PRODUCTION_REPLY = (
    "¡Listo! Registré tus gastos: Factura de servicios públicos: $199.966 "
    "(servicios, en efectivo)"
)


@pytest.mark.parametrize(
    "text",
    [
        PRODUCTION_REPLY,
        "Eliminé tu meta",
        "He actualizado tu tarjeta",
        "Tu gasto quedó registrado",
        "Los gastos quedaron guardados",
        "Actualicé el corte",
        "Hemos creado el presupuesto.",
        "Todo bien. Anoté tu gasto de $50.000.",
        "No te preocupes, registré tu gasto.",
        "No registré el café, pero eliminé el duplicado.",
        "✅ Gasto registrado: pizza $50.000",
        "Ingreso guardado: sueldo $3.000.000",
        "🗑️ Movimiento eliminado: taxi",
    ],
)
def test_claims_completed_write_true_positives(text: str) -> None:
    assert claims_completed_write(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Si quieres, lo registro",
        "¿Lo registro?",
        "¿Ya registré el gasto?",
        "No registré nada",
        "Aún no he registrado nada",
        "Todavía no actualicé el corte",
        "Dijiste «registré 50»",
        'Escribiste "registré 50" pero no veo la propuesta',
        "ya habías registrado ese gasto",
        "Ese gasto ya está registrado",
        "Pagué 50 mil en el super",
        "Registraré los de arriba",
        "Listo",
        "Tienes $199.966 en servicios públicos.",
        "¿Gasto registrado?",
        "Gasto no registrado todavía",
        FALSE_CLAIM_REPLY,
    ],
)
def test_claims_completed_write_false_positives(text: str) -> None:
    assert claims_completed_write(text) is False


def test_false_claim_reply_is_not_itself_a_claim() -> None:
    assert claims_completed_write(FALSE_CLAIM_REPLY) is False


class TestIsWriteAttempt:
    def test_proposal_result_is_not_an_attempt(self) -> None:
        assert is_write_attempt("update_card", f"{PROPOSAL_PREFIX}: corte 19 → 20") is False

    def test_already_proposed_is_not_an_attempt(self) -> None:
        result = f"{ALREADY_PROPOSED_PREFIX}: corte 19 → 20"
        assert is_write_attempt("update_card", result) is False

    def test_dispatch_error_is_not_an_attempt(self) -> None:
        result = f"{DISPATCH_ERROR_PREFIX}: Unknown tool"
        assert is_write_attempt("register_transaction", result) is False

    def test_read_only_tool_is_not_an_attempt(self) -> None:
        assert is_write_attempt("query_cards", "Tienes 1 tarjeta") is False

    def test_clarification_question_is_not_applied(self) -> None:
        result = "¿Lo pagaste en efectivo o con tarjeta de crédito?"
        assert is_write_attempt("register_transaction", result) is False

    def test_not_found_is_not_applied(self) -> None:
        assert is_write_attempt("delete_transaction", "No encontré ese gasto.") is False

    def test_emoji_success_counts(self) -> None:
        assert is_write_attempt("register_transaction", "✅ Registré: pizza $50") is True

    def test_success_without_marker_counts(self) -> None:
        assert is_write_attempt("register_transaction", "Gasto guardado: pizza $50") is True


class TestEnforceTruthfulReply:
    def test_blocks_claim_without_write(self) -> None:
        assert enforce_truthful_reply(PRODUCTION_REPLY, write_attempted=False) == FALSE_CLAIM_REPLY

    def test_keeps_claim_after_write(self) -> None:
        assert enforce_truthful_reply(PRODUCTION_REPLY, write_attempted=True) == PRODUCTION_REPLY

    def test_claim_after_read_only_tools_is_kept(self) -> None:
        text = "Sí, registré tu Uber el 5."
        assert (
            enforce_truthful_reply(text, write_attempted=False, tools_called=["find_movements"])
            == text
        )

    @pytest.mark.parametrize(
        "text",
        ["Lo que he registrado este mes suma $300.000.", "Tu último gasto quedó registrado el 5."],
    )
    def test_recount_after_find_movements_is_kept(self, text: str) -> None:
        reply = enforce_truthful_reply(text, write_attempted=False, tools_called=["find_movements"])
        assert reply == text

    def test_keeps_honest_text(self) -> None:
        text = "¿Cuánto gastaste?"
        assert enforce_truthful_reply(text, write_attempted=False) == text


def _production_tool_names() -> set[str]:
    """Tool names of the SAME composite toolkit production wires (collaborators mocked)."""
    services = ToolServices(**{f.name: MagicMock() for f in fields(ToolServices)})
    return {schema["function"]["name"] for schema in build_composite_toolkit(services).schemas}


def test_every_exposed_tool_is_classified_exactly_once() -> None:
    exposed = _production_tool_names()

    assert MUTATING_TOOLS.isdisjoint(READ_ONLY_TOOLS)
    assert MUTATING_TOOLS | READ_ONLY_TOOLS == exposed


UBER_HISTORY = "Usuario: gasté 12.000 en Uber\nSafi: ✅ Registré: Uber $12.000"
UBER_ASSISTANT_TURNS = "✅ Registré: Uber $12.000"


class TestInventedFigures:
    def test_figure_absent_from_history_is_invented(self) -> None:
        assert invented_figures("Registré $199.966", UBER_HISTORY) is True

    def test_figure_repeated_from_history_is_not_invented(self) -> None:
        assert invented_figures("Sí, registré tu Uber de $12.000", UBER_HISTORY) is False

    def test_formatting_differences_do_not_matter(self) -> None:
        assert invented_figures("Registré 12000", UBER_HISTORY) is False

    def test_reply_without_figures_is_not_invented(self) -> None:
        assert invented_figures("Sí, lo registré", UBER_HISTORY) is False

    def test_dates_and_years_do_not_count(self) -> None:
        reply = "Lo registré el 15 de octubre de 2026 (2026-10-15)"
        assert invented_figures(reply, UBER_HISTORY) is False


class TestRecountVersusInvention:
    def test_no_history_replaces(self) -> None:
        assert enforce_truthful_reply(PRODUCTION_REPLY, write_attempted=False) == FALSE_CLAIM_REPLY

    def test_recount_with_known_figures_is_kept_and_logged(self) -> None:
        text = "Sí, registré tu Uber de $12.000"
        with structlog.testing.capture_logs() as logs:
            reply = enforce_truthful_reply(
                text,
                write_attempted=False,
                history_text=UBER_HISTORY,
                history_claims_text=UBER_ASSISTANT_TURNS,
            )

        assert reply == text
        assert any(e.get("reason") == "recount_from_history" for e in logs)

    def test_invented_figure_with_history_is_replaced(self) -> None:
        reply = enforce_truthful_reply(
            PRODUCTION_REPLY, write_attempted=False, history_text=UBER_HISTORY
        )
        assert reply == FALSE_CLAIM_REPLY

    def test_no_figures_recount_backed_by_history_is_kept_and_logged(self) -> None:
        with structlog.testing.capture_logs() as logs:
            reply = enforce_truthful_reply(
                "Sí, ya lo registré",
                write_attempted=False,
                history_text=UBER_HISTORY,
                history_claims_text=UBER_ASSISTANT_TURNS,
            )

        assert reply == "Sí, ya lo registré"
        assert any(e.get("reason") == "recount_from_history" for e in logs)

    def test_user_only_claim_in_history_is_not_evidence(self) -> None:
        reply = enforce_truthful_reply(
            "Listo, registré tu gasto.",
            write_attempted=False,
            history_text="registré 50 en comida",
            history_claims_text="",
        )
        assert reply == FALSE_CLAIM_REPLY

    def test_assistant_claim_with_known_figures_is_kept_and_logged(self) -> None:
        with structlog.testing.capture_logs() as logs:
            reply = enforce_truthful_reply(
                "Sí, ya registré tu café de $8.000",
                write_attempted=False,
                history_text="Usuario: café 8.000\nSafi: ✅ Registré: café $8.000",
                history_claims_text="✅ Registré: café $8.000",
            )

        assert reply == "Sí, ya registré tu café de $8.000"
        assert any(e.get("reason") == "recount_from_history" for e in logs)

    def test_claim_when_history_shows_no_completed_write_is_replaced(self) -> None:
        history = "Usuario: hola\nSafi: ¡Hola! ¿En qué te ayudo?"
        reply = enforce_truthful_reply(
            "¡Listo! Registré tus gastos.", write_attempted=False, history_text=history
        )
        assert reply == FALSE_CLAIM_REPLY

    def test_refused_write_then_claim_is_replaced_even_with_tools(self) -> None:
        reply = enforce_truthful_reply(
            "Actualicé el corte",
            write_attempted=False,
            write_refused=True,
            tools_called=["update_card"],
        )
        assert reply == FALSE_CLAIM_REPLY

    def test_applied_write_wins_over_a_refused_one(self) -> None:
        reply = enforce_truthful_reply(
            "Registré el primero", write_attempted=True, write_refused=True
        )
        assert reply == "Registré el primero"


class TestNegationWithNi:
    @pytest.mark.parametrize(
        "text", ["Ni registré ni borré nada", "Tampoco registré el café", "No registré ni borré"]
    )
    def test_ni_and_tampoco_negate(self, text: str) -> None:
        assert claims_completed_write(text) is False


class TestShortAmountFormats:
    @pytest.mark.parametrize(
        "reply",
        [
            "Registré $2M",
            "Registré 300k",
            "Registré 1.5M",
            "Registré 12,5 dólares",
            "Registré 1 234 567",
            "Registré 5 millones",
        ],
    )
    def test_short_formats_count_as_invented_against_unrelated_history(self, reply: str) -> None:
        assert invented_figures(reply, "hola") is True

    @pytest.mark.parametrize(
        ("reply", "history"),
        [
            ("Registré $2M", "gasté 2.000.000"),
            ("Registré 300k", "pagué $300.000"),
            ("Registré 1.5M", "son 1.500.000"),
            ("Registré 5 millones", "son $5.000.000"),
            ("Registré 12,5 dólares", "eran 12.5 dólares"),
            ("Registré 1 234 567", "total 1.234.567"),
        ],
    )
    def test_same_value_in_another_format_is_not_invented(self, reply: str, history: str) -> None:
        assert invented_figures(reply, history) is False

    def test_day_numbers_are_ignored(self) -> None:
        assert invented_figures("Lo registré el 5 y el 15", "hola") is False


class TestScanCap:
    def test_claim_in_the_tail_of_a_huge_reply_is_detected(self) -> None:
        text = "x" * 20_000 + " Todo listo. Registré tu gasto."
        assert claims_completed_write(text) is True

    def test_long_negated_sentence_finishes_quickly(self) -> None:
        # Timing guard (generous bound): a single sentence with ~1500 negated claim verbs
        # used to take quadratic time in the clause scan; the scan cap bounds it.
        text = "No " + "registré " * 1500 + "nada"
        started = time.perf_counter()
        claims_completed_write(text)
        assert time.perf_counter() - started < 0.5
