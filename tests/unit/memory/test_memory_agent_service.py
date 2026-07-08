"""Unit tests for the Memory Agent service (extract / store / serve context)."""

import json

from app.src.memory.constants import MAX_ENTRIES_PER_TURN
from app.src.memory.models import KnowledgeEntry
from app.src.memory.services.memory_agent_service import MemoryAgentService
from tests.fakes import FakeLLM


class FakeKnowledgeRepository:
    """In-memory user-knowledge repository stub."""

    def __init__(self, existing: list[KnowledgeEntry] | None = None) -> None:
        self._existing = existing or []
        self.upserts: list[list[KnowledgeEntry]] = []

    async def get_all(self, user_id: str) -> list[KnowledgeEntry]:
        return list(self._existing)

    async def upsert_many(self, user_id: str, entries: list[KnowledgeEntry]) -> None:
        self.upserts.append(entries)


def _llm_returning(entries: list[dict[str, str]]) -> FakeLLM:
    return FakeLLM(json.dumps({"knowledge": entries}))


class TestProcess:
    async def test_extracts_and_upserts_facts(self) -> None:
        repo = FakeKnowledgeRepository()
        llm = _llm_returning([{"key": "moneda_preferida", "value": "MXN"}])
        service = MemoryAgentService(repo, llm)

        await service.process("u1", "uso pesos mexicanos", "Anotado.")

        assert repo.upserts == [[KnowledgeEntry(key="moneda_preferida", value="MXN")]]

    async def test_no_upsert_when_nothing_extracted(self) -> None:
        repo = FakeKnowledgeRepository()
        service = MemoryAgentService(repo, _llm_returning([]))

        await service.process("u1", "hola", "¡Hola!")

        assert repo.upserts == []

    async def test_caps_entries_per_turn(self) -> None:
        many = [{"key": f"k{i}", "value": str(i)} for i in range(MAX_ENTRIES_PER_TURN + 3)]
        repo = FakeKnowledgeRepository()
        service = MemoryAgentService(repo, _llm_returning(many))

        await service.process("u1", "un mensaje largo", "ok")

        assert len(repo.upserts[0]) == MAX_ENTRIES_PER_TURN

    async def test_tolerates_invalid_json_without_raising(self) -> None:
        repo = FakeKnowledgeRepository()
        service = MemoryAgentService(repo, FakeLLM("no soy json"))

        await service.process("u1", "hola", "¡Hola!")  # must not raise

        assert repo.upserts == []

    async def test_strips_markdown_fences(self) -> None:
        fenced = "```json\n" + json.dumps({"knowledge": [{"key": "pais", "value": "MX"}]}) + "\n```"
        repo = FakeKnowledgeRepository()
        service = MemoryAgentService(repo, FakeLLM(fenced))

        await service.process("u1", "vivo en México", "ok")

        assert repo.upserts == [[KnowledgeEntry(key="pais", value="MX")]]


class TestGetContext:
    async def test_formats_facts_as_bullet_lines(self) -> None:
        repo = FakeKnowledgeRepository(
            existing=[
                KnowledgeEntry(key="moneda_preferida", value="MXN"),
                KnowledgeEntry(key="meta_ahorro", value="viaje a Japón"),
            ]
        )
        service = MemoryAgentService(repo, FakeLLM(""))

        context = await service.get_context("u1")

        assert context == "- moneda_preferida: MXN\n- meta_ahorro: viaje a Japón"

    async def test_empty_when_no_facts(self) -> None:
        service = MemoryAgentService(FakeKnowledgeRepository(), FakeLLM(""))

        assert await service.get_context("u1") == ""
