"""Unit tests for the category management toolkit (rename/delete)."""

from app.agents.tools.category_tools import MANAGE_CATEGORY_TOOL, CategoryToolkit


class FakeTxService:
    def __init__(self, count: int = 0) -> None:
        self.count = count
        self.recategorized: list[tuple[str, str]] = []
        self.deleted: list[str] = []

    async def count_by_category(self, user_id: str, category: str) -> int:
        return self.count

    async def recategorize(self, user_id: str, old: str, new: str) -> int:
        self.recategorized.append((old, new))
        return self.count

    async def delete_by_category(self, user_id: str, category: str) -> int:
        self.deleted.append(category)
        return self.count


class FakeBudgetService:
    def __init__(self, topes: int = 1) -> None:
        self.topes = topes
        self.recategorized: list[tuple[str, str]] = []
        self.deleted: list[str] = []

    async def recategorize(self, user_id: str, old: str, new: str) -> int:
        self.recategorized.append((old, new))
        return self.topes

    async def delete_by_category(self, user_id: str, category: str) -> int:
        self.deleted.append(category)
        return self.topes


def _toolkit(tx: FakeTxService, bud: FakeBudgetService) -> CategoryToolkit:
    return CategoryToolkit(tx, bud)  # type: ignore[arg-type]


class TestRename:
    async def test_renames_transactions_and_budget(self) -> None:
        tx, bud = FakeTxService(count=5), FakeBudgetService(topes=1)

        result = await _toolkit(tx, bud).dispatch(
            MANAGE_CATEGORY_TOOL,
            {"action": "rename", "category": "improvistos", "new_name": "imprevistos"},
            user_id="u1",
        )

        assert tx.recategorized == [("improvistos", "imprevistos")]
        assert bud.recategorized == [("improvistos", "imprevistos")]
        assert "imprevistos" in result

    async def test_rename_requires_new_name(self) -> None:
        tx, bud = FakeTxService(), FakeBudgetService()

        result = await _toolkit(tx, bud).dispatch(
            MANAGE_CATEGORY_TOOL, {"action": "rename", "category": "gym"}, user_id="u1"
        )

        assert tx.recategorized == []  # nothing changed
        assert "renombrar" in result.lower() or "nombre" in result.lower()


class TestDelete:
    async def test_asks_what_to_do_when_movements_and_no_decision(self) -> None:
        tx, bud = FakeTxService(count=3), FakeBudgetService()

        result = await _toolkit(tx, bud).dispatch(
            MANAGE_CATEGORY_TOOL, {"action": "delete", "category": "imprevistos"}, user_id="u1"
        )

        # Must ASK, not delete or move anything.
        assert "3" in result and "imprevistos" in result
        assert tx.deleted == [] and tx.recategorized == [] and bud.deleted == []

    async def test_moves_movements_and_deletes_tope(self) -> None:
        tx, bud = FakeTxService(count=3), FakeBudgetService(topes=1)

        result = await _toolkit(tx, bud).dispatch(
            MANAGE_CATEGORY_TOOL,
            {"action": "delete", "category": "imprevistos", "move_to": "otros"},
            user_id="u1",
        )

        assert tx.recategorized == [("imprevistos", "otros")]
        assert bud.deleted == ["imprevistos"]
        assert tx.deleted == []  # moved, not deleted
        assert "otros" in result

    async def test_deletes_movements_when_requested(self) -> None:
        tx, bud = FakeTxService(count=3), FakeBudgetService(topes=1)

        await _toolkit(tx, bud).dispatch(
            MANAGE_CATEGORY_TOOL,
            {"action": "delete", "category": "imprevistos", "delete_movements": True},
            user_id="u1",
        )

        assert tx.deleted == ["imprevistos"]
        assert bud.deleted == ["imprevistos"]
        assert tx.recategorized == []

    async def test_empty_category_only_deletes_tope(self) -> None:
        tx, bud = FakeTxService(count=0), FakeBudgetService(topes=1)

        result = await _toolkit(tx, bud).dispatch(
            MANAGE_CATEGORY_TOOL, {"action": "delete", "category": "vacia"}, user_id="u1"
        )

        assert bud.deleted == ["vacia"]
        assert "vacia" in result


class TestGuards:
    async def test_empty_category_asks_never_touches_otros(self) -> None:
        # normalize_category("") == "otros"; a missing category must ASK, not act.
        tx, bud = FakeTxService(count=3), FakeBudgetService()

        result = await _toolkit(tx, bud).dispatch(
            MANAGE_CATEGORY_TOOL,
            {"action": "delete", "category": "", "delete_movements": True},
            user_id="u1",
        )

        assert "categoría" in result.lower()
        assert tx.deleted == [] and bud.deleted == []  # nothing deleted

    async def test_delete_move_to_same_category_asks_not_deletes(self) -> None:
        # move_to == category is a no-op move; must not fall through to deleting.
        tx, bud = FakeTxService(count=3), FakeBudgetService()

        result = await _toolkit(tx, bud).dispatch(
            MANAGE_CATEGORY_TOOL,
            {"action": "delete", "category": "gym", "move_to": "gym"},
            user_id="u1",
        )

        assert "3" in result  # asks (clarification mentions the count)
        assert tx.deleted == [] and tx.recategorized == [] and bud.deleted == []


class TestDispatch:
    async def test_unknown_action(self) -> None:
        result = await _toolkit(FakeTxService(), FakeBudgetService()).dispatch(
            MANAGE_CATEGORY_TOOL, {"action": "explode", "category": "gym"}, user_id="u1"
        )
        assert "no reconocida" in result.lower()

    async def test_unknown_tool_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="Unknown category tool"):
            await _toolkit(FakeTxService(), FakeBudgetService()).dispatch(
                "nope", {}, user_id="u1"
            )
