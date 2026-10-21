"""Unit tests for the tool-calling agent node."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import structlog.testing
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.context import category_context_block
from app.agents.nodes.action_claims import FALSE_CLAIM_REPLY
from app.agents.nodes.tool_agent import MAX_TOOL_ROUNDS, _history_block, tool_agent_node
from app.agents.state import build_initial_state
from app.agents.tools.card_tools import PROPOSAL_PREFIX
from app.agents.tools.transaction_tools import TransactionToolkit
from app.shared.clock import current_today, local_today
from app.shared.interfaces.llm import LLMResponse, MessageRole, ToolCall
from app.shared.turn import TurnContext, current_turn
from app.shared.types import CategoryType, CurrencyType, TransactionType, UserId
from app.src.transactions.interfaces import TransactionServiceABC
from app.src.transactions.models import SpendingSummary, Transaction, TransactionCreate
from tests.fakes import FakeLLM


class FakeTxService(TransactionServiceABC):
    def __init__(self) -> None:
        self.created: list[tuple[TransactionCreate, str]] = []
        self.list_calls: list[str] = []

    async def create_transaction(self, transaction: TransactionCreate, user_id: str) -> Transaction:
        self.created.append((transaction, user_id))
        return Transaction(
            id="tx-1",
            user_id=user_id,
            amount=transaction.amount,
            currency=CurrencyType.MXN,
            transaction_type=transaction.transaction_type,
            description=transaction.description,
            category=transaction.category or CategoryType.OTROS,
            transaction_date=transaction.transaction_date,
            budget_date=transaction.transaction_date,
            source="manual",
            created_at=datetime(2024, 12, 20, tzinfo=UTC),
        )

    async def create_installments(
        self, base: TransactionCreate, installments: int, user_id: str
    ) -> list[Transaction]:
        per = base.amount / installments
        return [
            await self.create_transaction(base.model_copy(update={"amount": per}), user_id)
            for _ in range(installments)
        ]

    async def categorize(self, description: str) -> str:
        return CategoryType.OTROS.value

    async def materialize_occurrence(
        self, transaction: TransactionCreate, user_id: str
    ) -> Transaction | None:
        return await self.create_transaction(transaction, user_id)

    async def get_transaction(self, transaction_id: str, user_id: str) -> Transaction:
        raise NotImplementedError

    async def list_transactions(self, user_id: str, **kwargs: object) -> tuple[list[Transaction], int]:
        self.list_calls.append(user_id)
        return [], 0

    async def list_by_period(self, user_id: str, **kwargs: object) -> list[Transaction]:
        return []

    async def delete_movements(self, user_id: str, **kwargs: object) -> int:
        return 0

    async def resolve_category(self, proposed: str, user_id: str) -> str:
        return proposed

    async def count_by_category(self, user_id: str, category: str) -> int:
        return 0

    async def list_categories(self, user_id: str) -> list[str]:
        return []

    async def recategorize(self, user_id: str, old: str, new: str) -> int:
        return 0

    async def delete_by_category(self, user_id: str, category: str) -> int:
        return 0

    async def update_transaction(self, transaction_id: str, user_id: str, **kwargs: object) -> Transaction:
        raise NotImplementedError

    async def delete_transaction(self, transaction_id: str, user_id: str) -> Transaction:
        raise NotImplementedError

    async def get_spending_summary(self, user_id: str, **kwargs: object) -> SpendingSummary:
        raise NotImplementedError


class ScriptedToolLLM(FakeLLM):
    """LLM that returns a scripted sequence of ``generate_with_tools`` responses.

    Mirrors the ReAct loop: each round consumes the next response; the last one
    is reused if the loop runs longer than the script.
    """

    def __init__(self, responses: list[LLMResponse]) -> None:
        super().__init__("(forced answer)")  # FakeLLM.generate returns this
        self._responses = responses
        self._index = 0

    async def generate_with_tools(self, messages, tools, config=None):  # type: ignore[no-untyped-def]
        response = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        return response


def _register_call() -> LLMResponse:
    return LLMResponse(
        content="",
        model="fake",
        tool_calls=[
            ToolCall(
                id="1",
                name="register_transaction",
                arguments={"amount": 50, "description": "pizza", "transaction_type": "expense"},
            )
        ],
    )


def _text(content: str) -> LLMResponse:
    return LLMResponse(content=content, model="fake")


class TestToolAgentNode:
    async def test_prior_turn_is_context_not_a_new_instruction(self) -> None:
        """A past expense in history must be context, not re-executed as a new action."""
        service = FakeTxService()
        toolkit = TransactionToolkit(service)
        captured: dict[str, list] = {}

        class CapturingLLM(ScriptedToolLLM):
            async def generate_with_tools(self, messages, tools, config=None):  # type: ignore[no-untyped-def]
                captured.setdefault("messages", list(messages))
                return await super().generate_with_tools(messages, tools, config)

        # Current, unrelated request; model answers without any tool call.
        llm = CapturingLLM([_text("Listo.")])
        history = [
            HumanMessage(content="gasté 50 en jardinería"),
            AIMessage(content="Registré tu gasto de 50 en jardinería."),
        ]
        state = build_initial_state(
            message="agrega una tarjeta BBVA", user_id="u1", history=history
        )

        await tool_agent_node(state, llm, toolkit)

        msgs = captured["messages"]
        # Only the current message is a live user instruction.
        assert msgs[-1].role == MessageRole.USER
        assert msgs[-1].content == "agrega una tarjeta BBVA"
        # The past expense lives in the system prompt as context, never as a live user turn.
        assert "jardinería" in msgs[0].content
        assert all(
            m.content != "gasté 50 en jardinería"
            for m in msgs
            if m.role == MessageRole.USER
        )

    async def test_injects_user_categories_into_context(self) -> None:
        """The user's existing categories reach the agent so it reuses them."""
        service = FakeTxService()
        toolkit = TransactionToolkit(service)
        captured: dict[str, list] = {}

        class CapturingLLM(ScriptedToolLLM):
            async def generate_with_tools(self, messages, tools, config=None):  # type: ignore[no-untyped-def]
                captured.setdefault("messages", list(messages))
                return await super().generate_with_tools(messages, tools, config)

        async def provider(user_id: str) -> list[str]:
            return ["venezuela", "consultas y medicamentos"]

        llm = CapturingLLM([_text("Listo.")])
        state = build_initial_state(message="cuánto gasté en venezuela", user_id="u1")

        await tool_agent_node(state, llm, toolkit, categories_provider=provider)

        system_prompt = captured["messages"][0].content
        assert "venezuela" in system_prompt
        assert "consultas y medicamentos" in system_prompt

    async def test_executes_tool_then_responds(self) -> None:
        service = FakeTxService()
        toolkit = TransactionToolkit(service)
        # Round 1: call the tool. Round 2: no tools -> final answer.
        llm = ScriptedToolLLM([_register_call(), _text("Listo, registré tu pizza.")])
        state = build_initial_state(message="gasté 50 en pizza", user_id="u1")

        result = await tool_agent_node(state, llm, toolkit)

        # The tool persisted exactly once, scoped to the auth user.
        assert len(service.created) == 1
        created, user_id = service.created[0]
        assert created.amount == Decimal("50")
        assert created.transaction_type == TransactionType.EXPENSE
        assert user_id == "u1"
        assert result["messages"][-1].content == "Listo, registré tu pizza."

    async def test_parallel_tools_in_one_round(self) -> None:
        service = FakeTxService()
        toolkit = TransactionToolkit(service)
        two_calls = LLMResponse(
            content="",
            model="fake",
            tool_calls=[
                ToolCall(id="1", name="register_transaction",
                         arguments={"amount": 50, "description": "pizza", "transaction_type": "expense"}),
                ToolCall(id="2", name="query_transactions", arguments={}),
            ],
        )
        llm = ScriptedToolLLM([two_calls, _text("Registré y consulté.")])
        state = build_initial_state(message="registra 50 en pizza y dime mis gastos", user_id="u1")

        result = await tool_agent_node(state, llm, toolkit)

        # Both tools of the single round ran (register persisted + query queried).
        assert len(service.created) == 1
        assert service.list_calls == ["u1"]
        assert result["messages"][-1].content == "Registré y consulté."

    async def test_stops_at_max_rounds_and_forces_answer(self) -> None:
        # LLM that always asks for a tool -> the loop must stop at the cap and
        # force a final plain answer (runaway-cost backstop).
        service = FakeTxService()
        toolkit = TransactionToolkit(service)
        llm = ScriptedToolLLM([_register_call()])  # reused every round
        state = build_initial_state(message="loop", user_id="u1")

        result = await tool_agent_node(state, llm, toolkit)

        # Tool dispatched exactly MAX_TOOL_ROUNDS times, then a forced answer.
        assert len(service.created) == MAX_TOOL_ROUNDS
        assert result["messages"][-1].content == "(forced answer)"  # FakeLLM.generate

    async def test_no_tool_call_returns_text_directly(self) -> None:
        toolkit = TransactionToolkit(FakeTxService())
        llm = ScriptedToolLLM([_text("¿Cuánto gastaste?")])
        state = build_initial_state(message="quiero registrar algo", user_id="u1")

        result = await tool_agent_node(state, llm, toolkit)

        assert result["messages"][-1].content == "¿Cuánto gastaste?"

    async def test_one_today_feeds_both_prompt_and_tools(self) -> None:
        """The turn resolves ONE local today; the prompt and every dispatched tool see it."""
        observed: list[date] = []
        captured: dict[str, list] = {}

        class RecordingToolkit:
            """Minimal Toolkit that records current_today() at dispatch time."""

            @property
            def schemas(self) -> list[dict[str, Any]]:
                return [
                    {
                        "type": "function",
                        "function": {"name": "probe", "parameters": {"type": "object"}},
                    }
                ]

            async def dispatch(
                self, name: str, arguments: dict[str, Any], user_id: UserId
            ) -> str:
                observed.append(current_today())
                return "ok"

        probe_call = LLMResponse(
            content="",
            model="fake",
            tool_calls=[
                ToolCall(id="1", name="probe", arguments={}),
                ToolCall(id="2", name="probe", arguments={}),
            ],
        )

        class CapturingLLM(ScriptedToolLLM):
            async def generate_with_tools(self, messages, tools, config=None):  # type: ignore[no-untyped-def]
                captured.setdefault("messages", list(messages))
                return await super().generate_with_tools(messages, tools, config)

        llm = CapturingLLM([probe_call, _text("Listo.")])
        state = build_initial_state(
            message="¿qué gasté hoy?", user_id="u1", timezone="America/Bogota"
        )

        await tool_agent_node(state, llm, RecordingToolkit())

        expected = local_today("America/Bogota")
        # The prompt carries the Bogota local date...
        assert expected.isoformat() in captured["messages"][0].content
        # ...and BOTH tools dispatched across the gather saw the SAME value.
        assert observed == [expected, expected]

    async def test_llm_failure_degrades_gracefully(self) -> None:
        class BrokenLLM(FakeLLM):
            async def generate_with_tools(self, messages, tools, config=None):  # type: ignore[no-untyped-def]
                raise RuntimeError("llm down")

        toolkit = TransactionToolkit(FakeTxService())
        state = build_initial_state(message="gasté 50", user_id="u1")

        result = await tool_agent_node(state, BrokenLLM("x"), toolkit)

        assert "no pude completar" in result["messages"][-1].content.lower()


class TestCategoryContextBlock:
    def test_empty_when_no_categories(self) -> None:
        assert category_context_block([]) == ""

    def test_lists_categories_for_reuse(self) -> None:
        block = category_context_block(["venezuela", "consultas y medicamentos"])
        assert "venezuela" in block
        assert "consultas y medicamentos" in block
        assert "REUTIL" in block.upper()


class TestToolAgentTurnBinding:
    @staticmethod
    def _probe_llm() -> ScriptedToolLLM:
        call = LLMResponse(
            content="",
            model="fake",
            tool_calls=[ToolCall(id="1", name="probe", arguments={})],
        )
        return ScriptedToolLLM([call, _text("ok")])

    @staticmethod
    def _probe_toolkit(seen: list[TurnContext | None]) -> Any:
        class ProbeToolkit:
            @property
            def schemas(self) -> list[dict[str, Any]]:
                return [{"type": "function", "function": {"name": "probe", "parameters": {}}}]

            async def dispatch(self, name: str, arguments: dict[str, Any], user_id: UserId) -> str:
                seen.append(current_turn())
                return "ok"

        return ProbeToolkit()

    async def test_tools_see_the_turn_and_conversation_from_the_state(self) -> None:
        seen: list[TurnContext | None] = []
        state = build_initial_state(
            message="hola", user_id="u1", conversation_id="conv-9", turn_id="turn-9"
        )

        await tool_agent_node(state, self._probe_llm(), self._probe_toolkit(seen))

        assert seen == [TurnContext(turn_id="turn-9", conversation_id="conv-9")]
        assert current_turn() is None  # unbound again after the node

    async def test_without_ids_no_turn_is_bound_so_two_step_tools_fail_closed(self) -> None:
        seen: list[TurnContext | None] = []
        state = build_initial_state(message="hola", user_id="u1")

        await tool_agent_node(state, self._probe_llm(), self._probe_toolkit(seen))

        assert seen == [None]


class TestToolAgentTurnFailedFlag:
    async def test_normal_answer_is_not_a_failed_turn(self) -> None:
        state = build_initial_state(message="hola", user_id="u1")

        result = await tool_agent_node(state, ScriptedToolLLM([_text("Hola")]), FakeToolkitStub())

        assert result["turn_failed"] is False

    async def test_generic_fallback_marks_the_turn_failed(self) -> None:
        class BoomLLM(ScriptedToolLLM):
            async def generate_with_tools(self, messages, tools, config=None):  # type: ignore[no-untyped-def]
                raise RuntimeError("llm down")

        state = build_initial_state(message="hola", user_id="u1")

        result = await tool_agent_node(state, BoomLLM([_text("x")]), FakeToolkitStub())

        assert result["turn_failed"] is True
        assert result["messages"][-1].content.startswith("Lo siento, no pude completar")


CLAIM_TEXT = (
    "¡Listo! Registré tus gastos: Factura de servicios públicos: $199.966 "
    "(servicios, en efectivo)"
)


class ResultToolkit:
    """Toolkit whose every tool returns a fixed result."""

    def __init__(self, result: str) -> None:
        self._result = result

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return []

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: UserId) -> str:
        return self._result


class NamedResultsToolkit:
    """register_transaction applies; delete_transaction finds nothing."""

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return []

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: UserId) -> str:
        return "✅ Registré: pizza" if name == "register_transaction" else "No encontré ese gasto."


def _call(name: str) -> LLMResponse:
    return LLMResponse(
        content="", model="fake", tool_calls=[ToolCall(id="1", name=name, arguments={})]
    )


class ClaimingForcedLLM(ScriptedToolLLM):
    """Scripted tool rounds; the forced final answer always claims a write."""

    async def generate(self, messages, config=None):  # type: ignore[no-untyped-def]
        return LLMResponse(content=CLAIM_TEXT, model="fake")


class TestTruthfulReplyGuard:
    async def _reply(self, llm: ScriptedToolLLM, toolkit: Any) -> str:
        state = build_initial_state(message="sí", user_id="u1")
        result = await tool_agent_node(state, llm, toolkit)
        return str(result["messages"][-1].content)

    async def test_claim_without_any_tool_call_is_replaced(self) -> None:
        reply = await self._reply(ScriptedToolLLM([_text(CLAIM_TEXT)]), FakeToolkitStub())

        assert reply == FALSE_CLAIM_REPLY

    async def test_recount_from_history_without_tools_is_kept(self) -> None:
        history = [
            HumanMessage(content="gasté 25.000 en Uber"),
            AIMessage(content="Listo, registré tu Uber de $25.000"),
        ]
        state = build_initial_state(message="¿registraste el Uber?", user_id="u1", history=history)
        llm = ScriptedToolLLM([_text("Sí, registré tu Uber de $25.000")])

        result = await tool_agent_node(state, llm, FakeToolkitStub())

        assert result["messages"][-1].content == "Sí, registré tu Uber de $25.000"

    async def test_user_only_write_claim_in_history_does_not_back_a_reply(self) -> None:
        history = [
            HumanMessage(content="registré 50 en comida"),
            AIMessage(content="¿Lo pagaste en efectivo o con tarjeta?"),
        ]
        state = build_initial_state(message="sí", user_id="u1", history=history)
        llm = ScriptedToolLLM([_text("Listo, registré tu gasto.")])

        result = await tool_agent_node(state, llm, FakeToolkitStub())

        assert result["messages"][-1].content == FALSE_CLAIM_REPLY

    async def test_invented_figures_with_history_are_replaced(self) -> None:
        history = [HumanMessage(content="hola"), AIMessage(content="¡Hola!")]
        state = build_initial_state(message="sí", user_id="u1", history=history)

        result = await tool_agent_node(state, ScriptedToolLLM([_text(CLAIM_TEXT)]), FakeToolkitStub())

        assert result["messages"][-1].content == FALSE_CLAIM_REPLY

    async def test_claim_after_a_register_call_is_kept(self) -> None:
        llm = ScriptedToolLLM([_call("register_transaction"), _text(CLAIM_TEXT)])

        reply = await self._reply(llm, ResultToolkit("Gasto guardado"))

        assert reply == CLAIM_TEXT

    async def test_claim_after_a_read_only_call_is_kept_and_logged(self) -> None:
        # Honest recount: "¿registraste el Uber?" -> find_movements -> "Sí, registré...".
        llm = ScriptedToolLLM([_call("find_movements"), _text(CLAIM_TEXT)])

        with structlog.testing.capture_logs() as logs:
            reply = await self._reply(llm, ResultToolkit("1 movimiento"))

        assert reply == CLAIM_TEXT
        assert any(entry["event"] == "Possible false write claim" for entry in logs)

    async def test_claim_after_a_proposal_only_result_is_replaced(self) -> None:
        llm = ScriptedToolLLM([_call("update_card"), _text("Actualicé el corte")])

        reply = await self._reply(llm, ResultToolkit(f"{PROPOSAL_PREFIX}: corte 19 → 20"))

        assert reply == FALSE_CLAIM_REPLY

    async def test_claim_after_a_not_found_write_is_replaced(self) -> None:
        llm = ScriptedToolLLM([_call("delete_transaction"), _text("Eliminé tu gasto")])

        reply = await self._reply(llm, ResultToolkit("No encontré esa transacción."))

        assert reply == FALSE_CLAIM_REPLY

    async def test_one_applied_and_one_refused_write_keeps_the_text(self) -> None:
        both = LLMResponse(
            content="",
            model="fake",
            tool_calls=[
                ToolCall(id="1", name="register_transaction", arguments={}),
                ToolCall(id="2", name="delete_transaction", arguments={}),
            ],
        )
        llm = ScriptedToolLLM([both, _text("Registré el primero")])

        reply = await self._reply(llm, NamedResultsToolkit())

        assert reply == "Registré el primero"

    async def test_forced_answer_after_reads_is_kept(self) -> None:
        # Always asks for a read-only tool -> rounds exhausted -> forced answer.
        reply = await self._reply(ClaimingForcedLLM([_call("query_cards")]), ResultToolkit("ok"))

        assert reply == CLAIM_TEXT

    async def test_forced_answer_after_a_write_is_kept(self) -> None:
        llm = ClaimingForcedLLM([_call("register_transaction")])

        reply = await self._reply(llm, ResultToolkit("Gasto guardado"))

        assert reply == CLAIM_TEXT


class TestHistoryBlock:
    def test_empty_history_states_nothing_is_pending(self) -> None:
        block = _history_block([])

        assert "ninguna propuesta" in block
        assert "Conversación previa: ninguna" in block


class FakeToolkitStub:
    @property
    def schemas(self) -> list[dict[str, Any]]:
        return []

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: UserId) -> str:
        return "ok"
