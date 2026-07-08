"""Guardrail checks: the user-facing generation prompts must forbid inventing data.

These tests pin the anti-hallucination and scope instructions in place so a
future prompt edit cannot silently drop them.
"""

from app.agents.nodes.response_generator_constants import RESPONSE_SYSTEM_PROMPT
from app.agents.nodes.tool_agent_constants import TOOL_AGENT_SYSTEM_PROMPT


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
