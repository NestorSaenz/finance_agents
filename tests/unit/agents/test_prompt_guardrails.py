"""Guardrail checks: the user-facing generation prompts must forbid inventing data.

These tests pin the anti-hallucination and scope instructions in place so a
future prompt edit cannot silently drop them.
"""

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

    def test_prompt_confirms_with_the_deduced_value_and_never_reasks(self) -> None:
        assert "→" in TOOL_AGENT_SYSTEM_PROMPT
        assert "re-preguntes" in TOOL_AGENT_SYSTEM_PROMPT
        assert "la razón" in TOOL_AGENT_SYSTEM_PROMPT
        assert "valor deducido" in TOOL_AGENT_SYSTEM_PROMPT

    def test_update_card_schema_carries_the_same_rules(self) -> None:
        description = _update_card_description().lower()
        for phrase in ("periodo de facturación", "ciclo", "fecha de corte", "cierre"):
            assert phrase in description
        assert "último día" in description
        assert "fecha límite de pago" in description
        assert "solo el banco" in description
        assert "→" in description
        assert "inicio - 1" in description
