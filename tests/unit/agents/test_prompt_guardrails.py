"""Guardrail checks: the user-facing generation prompts must forbid inventing data.

These tests pin the anti-hallucination and scope instructions in place so a
future prompt edit cannot silently drop them.
"""

from app.agents.nodes.image_ingestion import PROPOSAL_HEADER
from app.agents.nodes.response_generator_constants import RESPONSE_SYSTEM_PROMPT
from app.agents.nodes.tool_agent_constants import TOOL_AGENT_SYSTEM_PROMPT
from app.agents.tools.card_tools import CARD_TOOL_SCHEMAS


class TestAntiHallucinationGuardrail:
    def test_prompts_forbid_inventing(self) -> None:
        for name, prompt in {
            "tool_agent": TOOL_AGENT_SYSTEM_PROMPT,
            "response_generator": RESPONSE_SYSTEM_PROMPT,
        }.items():
            assert "no inventes" in prompt.lower(), f"{name} prompt missing 'no inventes' rule"

    def test_response_generator_grounds_and_disclaims(self) -> None:
        lowered = RESPONSE_SYSTEM_PROMPT.lower()
        assert "únicamente los datos" in lowered
        assert "no eres un asesor financiero certificado" in lowered

    def test_prompts_enforce_scope(self) -> None:
        # Both user-facing agents must decline out-of-scope (non-finance) requests.
        for prompt in (TOOL_AGENT_SYSTEM_PROMPT, RESPONSE_SYSTEM_PROMPT):
            assert "alcance" in prompt.lower()


class TestNoInventedProposalGuardrail:
    def test_prompt_has_no_literal_data_the_model_can_copy(self) -> None:
        for literal in ("199.966", "57.000", "Néstor"):
            assert literal not in TOOL_AGENT_SYSTEM_PROMPT

    def test_bare_confirmation_without_a_proposal_confirms_nothing(self) -> None:
        assert '"sí"/"dale"/"regístralos" suelto NO confirma nada' in TOOL_AGENT_SYSTEM_PROMPT
        assert "NUNCA digas que registraste" in TOOL_AGENT_SYSTEM_PROMPT


class TestNoMentalArithmeticGuardrail:
    def test_totals_come_from_the_tool_never_from_the_model(self) -> None:
        assert "NUNCA sumes ni restes cifras tú mismo" in TOOL_AGENT_SYSTEM_PROMPT
        assert 'línea\n  "TOTAL" que entrega la herramienta' in TOOL_AGENT_SYSTEM_PROMPT
        assert "con los filtros que den ese total" in TOOL_AGENT_SYSTEM_PROMPT
        assert "query_transactions sin categoría" in TOOL_AGENT_SYSTEM_PROMPT
        assert 'tope "General" ya cubre todo' in TOOL_AGENT_SYSTEM_PROMPT
        assert "no puedes calcularlo" in TOOL_AGENT_SYSTEM_PROMPT


class TestFileProposalRules:
    def test_registers_only_the_lines_under_the_proposal_header(self) -> None:
        assert f'DESPUÉS de "{PROPOSAL_HEADER}"' in TOOL_AGENT_SYSTEM_PROMPT
        assert "NUNCA las registres" in TOOL_AGENT_SYSTEM_PROMPT

    def test_corrections_apply_to_exceptions_and_never_ask_category_per_line(self) -> None:
        assert "el segundo es mercado" in TOOL_AGENT_SYSTEM_PROMPT
        assert "NUNCA preguntes una categoría por línea" in TOOL_AGENT_SYSTEM_PROMPT

    def test_card_payment_lines_go_through_pay_card_never_income(self) -> None:
        assert "Pago a tarjeta" in TOOL_AGENT_SYSTEM_PROMPT
        assert "pay_card(card_name, amount, payment_date)" in TOOL_AGENT_SYSTEM_PROMPT

    def test_naming_the_card_resolves_the_pending_question(self) -> None:
        assert '"es de Nu"' in TOOL_AGENT_SYSTEM_PROMPT
        assert "no repitas una" in TOOL_AGENT_SYSTEM_PROMPT

    def test_marker_header_is_the_single_source_of_truth(self) -> None:
        assert PROPOSAL_HEADER == "Faltan por registrar:"
        assert PROPOSAL_HEADER in TOOL_AGENT_SYSTEM_PROMPT


def _update_card_description() -> str:
    schema = next(s for s in CARD_TOOL_SCHEMAS if s["function"]["name"] == "update_card")
    function = schema["function"]
    cutoff = function["parameters"]["properties"]["new_cutoff_day"]["description"]
    return f"{function['description']} {cutoff}"


class TestCardCutoffVocabulary:
    def test_prompt_maps_billing_period_synonyms_to_cutoff_day(self) -> None:
        lowered = TOOL_AGENT_SYSTEM_PROMPT.lower()
        for phrase in ("periodo de facturación", "ciclo", "fecha de corte", "cierre"):
            assert phrase in lowered
        assert "fecha límite de pago" in lowered
        assert "último día" in lowered
        assert "inicio - 1" in lowered

    def test_prompt_never_defers_to_the_bank_for_stored_data(self) -> None:
        assert "solo el banco" in TOOL_AGENT_SYSTEM_PROMPT
        assert "modificar y eliminar" in TOOL_AGENT_SYSTEM_PROMPT

    def test_prompt_keeps_deduction_rules_and_never_reasks(self) -> None:
        assert "→" in TOOL_AGENT_SYSTEM_PROMPT
        assert "re-preguntes" in TOOL_AGENT_SYSTEM_PROMPT
        assert "la razón" in TOOL_AGENT_SYSTEM_PROMPT

    def test_prompt_routes_schedule_changes_through_propose_then_confirm(self) -> None:
        # Code enforces the confirmation; the prompt only has to name the two steps.
        assert "PROPONE" in TOOL_AGENT_SYSTEM_PROMPT
        assert "confirm_card_change" in TOOL_AGENT_SYSTEM_PROMPT
        assert "✏️ Actualicé" in TOOL_AGENT_SYSTEM_PROMPT

    def test_update_card_schema_carries_the_same_rules(self) -> None:
        description = _update_card_description().lower()
        for phrase in ("periodo de facturación", "ciclo", "fecha de corte", "cierre"):
            assert phrase in description
        assert "fecha límite de pago" in description
        assert "solo el banco" in description
        assert "→" in description

    def test_update_card_schema_only_proposes_schedule_changes(self) -> None:
        description = _update_card_description()
        assert "SOLO crea una propuesta" in description
        assert "no la aplica" in description

    def test_confirm_card_change_is_argument_free_and_gated_on_the_current_message(self) -> None:
        schema = next(
            s for s in CARD_TOOL_SCHEMAS if s["function"]["name"] == "confirm_card_change"
        )
        function = schema["function"]
        assert function["parameters"]["properties"] == {}
        assert "SOLO si el mensaje ACTUAL" in function["description"]
