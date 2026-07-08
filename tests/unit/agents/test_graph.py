"""Unit tests for the FinanceGPT graph: routing helpers and end-to-end wiring."""

import json

from app.agents.graph import create_financegpt_graph, route_to_agent
from app.agents.state import build_initial_state
from tests.fakes import FakeEmbeddingClient, FakeLLM, FakeToolkit, FakeVectorStore


class TestRouteToAgent:
    def test_routes_to_valid_agent(self) -> None:
        assert route_to_agent({"next_agent": "tool_agent"}) == "tool_agent"

    def test_unknown_agent_falls_back_to_response_generator(self) -> None:
        # analyst is no longer a routing target (its intent goes to tool_agent).
        assert route_to_agent({"next_agent": "analyst"}) == "response_generator"

    def test_missing_agent_falls_back_to_response_generator(self) -> None:
        assert route_to_agent({}) == "response_generator"


def _build_test_graph(
    final_text: str = "Categoricé tu gasto como restaurantes.",
    intent: str = "categorize",
):
    """Compile the graph wired with deterministic fakes."""
    classifier_llm = FakeLLM(json.dumps({"intent": intent, "complexity": "simple"}))
    response_llm = FakeLLM(final_text)
    return (
        create_financegpt_graph(
            llm_simple=classifier_llm,
            llm_complex=response_llm,
            embedding_client=FakeEmbeddingClient(),
            vector_store=FakeVectorStore(category="restaurantes"),
            toolkit=FakeToolkit(),
        ),
        classifier_llm,
        response_llm,
    )


class TestGraphEndToEnd:
    async def test_simple_categorize_flow_produces_ai_response(self) -> None:
        graph, classifier_llm, response_llm = _build_test_graph(
            final_text="Tu gasto fue categorizado como restaurantes."
        )
        state = build_initial_state(message="gasté 50 en pizza", user_id="u1")

        result = await graph.ainvoke(state, config={"configurable": {"thread_id": "t1"}})

        # The orchestrator classified the intent via the simple LLM.
        assert result["detected_intent"] == "categorize"
        # The categorizer used the vector store match.
        assert result["category_suggestion"] == "restaurantes"
        # The response generator produced the final assistant message.
        last_message = result["messages"][-1]
        assert last_message.content == "Tu gasto fue categorizado como restaurantes."
        # Both LLM roles were exercised.
        assert classifier_llm.calls, "orchestrator should call the simple LLM"
        assert response_llm.calls, "response generator should call the complex LLM"

    async def test_plan_intent_routes_through_tool_agent(self) -> None:
        # 'plan' is now a data-driven intent handled by the tool agent, which
        # (with no tool calls scripted) answers directly.
        graph, _, _ = _build_test_graph(
            final_text="Aquí está tu plan de ahorro.", intent="plan"
        )
        state = build_initial_state(message="ayúdame a ahorrar para un viaje", user_id="u1")

        result = await graph.ainvoke(state, config={"configurable": {"thread_id": "tp"}})

        assert result["detected_intent"] == "plan"
        assert result["messages"][-1].content == "Aquí está tu plan de ahorro."

    async def test_register_intent_routes_through_tool_agent(self) -> None:
        graph, _, _ = _build_test_graph(
            final_text="Registré tu gasto de pizza.", intent="register"
        )
        state = build_initial_state(message="gasté 50 en pizza", user_id="u1")

        result = await graph.ainvoke(state, config={"configurable": {"thread_id": "tr"}})

        assert result["detected_intent"] == "register"
        # The tool agent produced the final assistant message and terminated.
        assert result["messages"][-1].content == "Registré tu gasto de pizza."

    async def test_off_topic_is_declined_at_the_gate(self) -> None:
        from app.agents.nodes.refusal import REFUSAL_MESSAGE

        graph, _, response_llm = _build_test_graph(
            final_text="no debería usarse", intent="off_topic"
        )
        state = build_initial_state(message="escríbeme un poema", user_id="u1")

        result = await graph.ainvoke(state, config={"configurable": {"thread_id": "ot"}})

        assert result["detected_intent"] == "off_topic"
        # Declined with the canned message and NO downstream LLM call (cost control).
        assert result["messages"][-1].content == REFUSAL_MESSAGE
        assert not response_llm.calls, "off-topic must not reach the response generator"

    async def test_conversation_keeps_human_and_ai_messages(self) -> None:
        graph, _, _ = _build_test_graph()
        state = build_initial_state(message="gasté 50 en pizza", user_id="u1")

        result = await graph.ainvoke(state, config={"configurable": {"thread_id": "t2"}})

        roles = [m.type for m in result["messages"]]
        assert "human" in roles
        assert "ai" in roles
