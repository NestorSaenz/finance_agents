"""Unit tests for the agent state builder."""

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.state import build_initial_state


class TestBuildInitialState:
    def test_seeds_user_message(self) -> None:
        state = build_initial_state(message="gasté 50 en pizza", user_id="u1")

        assert len(state["messages"]) == 1
        message = state["messages"][0]
        assert isinstance(message, HumanMessage)
        assert message.content == "gasté 50 en pizza"

    def test_sets_safe_defaults(self) -> None:
        state = build_initial_state(message="hola", user_id="u1")

        assert state["user_id"] == "u1"
        assert state["user_context"] == ""
        assert state["detected_intent"] == "unknown"
        assert state["category_suggestion"] is None
        assert state["next_agent"] == ""
        assert state["should_respond"] is False

    def test_prepends_history_then_current_message(self) -> None:
        history = [HumanMessage(content="hola"), AIMessage(content="¡Hola!")]
        state = build_initial_state(
            message="gasté 50", user_id="u1", history=history, user_context="- pais: MX"
        )

        assert [m.content for m in state["messages"]] == ["hola", "¡Hola!", "gasté 50"]
        assert state["user_context"] == "- pais: MX"
