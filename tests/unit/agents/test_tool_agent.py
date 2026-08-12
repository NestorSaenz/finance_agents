"""Unit tests for the tool-calling agent node."""

from datetime import UTC, datetime
from decimal import Decimal

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.context import category_context_block
from app.agents.nodes.tool_agent import MAX_TOOL_ROUNDS, tool_agent_node
from app.agents.state import build_initial_state
from app.agents.tools.transaction_tools import TransactionToolkit
from app.shared.interfaces.llm import LLMResponse, MessageRole, ToolCall
from app.shared.types import CategoryType, CurrencyType, TransactionType
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
