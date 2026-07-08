"""Tests for the off-topic scope guardrail (classifier + refusal node)."""

from app.agents.nodes.classifier import _parse_classification_response
from app.agents.nodes.refusal import REFUSAL_MESSAGE, refusal_node
from app.agents.state import build_initial_state
from app.agents.types import AgentName


class TestClassifierOffTopic:
    def test_off_topic_routes_to_refusal(self) -> None:
        result = _parse_classification_response('{"intent": "off_topic"}')

        assert result.intent == "off_topic"
        assert result.next_agent == AgentName.REFUSAL

    def test_unknown_intent_falls_back_to_query(self) -> None:
        # An unrecognized intent must not crash routing; it defaults to query.
        result = _parse_classification_response('{"intent": "banana"}')

        assert result.intent == "query"
        assert result.next_agent == AgentName.TOOL_AGENT


class TestRefusalNode:
    async def test_returns_canned_message_without_llm(self) -> None:
        state = build_initial_state(message="escríbeme un poema", user_id="u1")

        result = await refusal_node(state)

        assert result["messages"][-1].content == REFUSAL_MESSAGE
        assert result["should_respond"] is False
