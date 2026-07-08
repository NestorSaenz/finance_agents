---
name: financegpt-code-review
description: >
  Comprehensive guide for reviewing code in the FinanceGPT FastAPI + LangGraph + LangChain
  application. Trigger: when reviewing code, checking diffs/PRs, or evaluating code quality
  against project standards (Clean Architecture, DDD, strict typing).
license: Apache-2.0
metadata:
  author: financegpt
  version: "1.0"
---

## When to Use

- Reviewing changes to the FinanceGPT backend (agents, services, repositories, routes).
- Verifying a developer addressed previous review comments.
- Ensuring code adheres to the project's Clean Architecture, DDD, and strict-typing rules
  (see `docs/MODULE_STRUCTURE_GUIDE.md` and `docs/ARCHITECTURE.md`).
- Validating performance, Big-O complexity, and avoiding redundant iterations.

## Critical Patterns (Must Enforce)

1. **Strict Typing (No `Any`)**
   - Code must pass `uv run mypy app/` (config: `disallow_untyped_defs = true`).
   - No `List`, `Dict`, `Optional`, or `Any`. Use built-ins (`list`, `dict`) and `|` unions.
   - Type-hint every public method.
2. **Clean Architecture & Boundaries** (per `MODULE_STRUCTURE_GUIDE.md`)
   - Routes speak DTOs (`dto.py`), Services speak Domain Models (`models.py`),
     Repositories return Domain Models.
   - No business logic in repositories (data access only).
   - No direct Supabase/Cohere/Pinecone SDK calls from routes or nodes — go through
     services/clients behind an interface.
3. **Dependency Injection**
   - Use FastAPI `Depends` + ABC interfaces (`interfaces.py`) for services and repositories.
   - LangGraph nodes must receive collaborators (LLM, stores) via binding
     (e.g. `functools.partial` / closures), NOT as bare extra positional params on a node
     registered with `add_node` — LangGraph only passes `state`.
4. **Declarative Programming**
   - Prefer comprehensions, generator expressions, and `next()` over imperative `.append()` loops.
   - Avoid deep nesting; use early returns.
5. **Performance & Big-O**
   - Flag redundant iterations (3 passes that can be 1–2).
   - Flag N+1 queries or blocking I/O on hot paths.
   - Reuse async clients (`httpx.AsyncClient`, Cohere, Pinecone) where the architecture allows.
6. **Specific Exceptions**
   - Never use bare `except:` or `except Exception:`. Catch specific domain exceptions
     (`app/core/exceptions.py`) or stdlib ones (`ValueError`, `TypeError`).
   - Always chain with `from e`.
   - A broad catch is acceptable ONLY at an agent/LLM boundary with an explicit fallback,
     and must log the error with context.
7. **Constants & Enums**
   - Static values → `Final[type]` in `constants.py`. No magic strings/numbers.
   - String enumerations → `StrEnum` (or `str, Enum`) in `types.py`.
8. **Money & Dates**
   - Monetary amounts use `Decimal`, never `float`, in domain/models (Supabase boundary may
     convert). Flag `float` arithmetic on money.
   - Use timezone-aware `datetime` (`datetime.now(UTC)`).
9. **Async correctness**
   - All I/O is `async`; never call blocking SDK methods inside `async def` without offloading.
   - LLM/embedding/vector calls use the `a*`/await variants.

## Project-Specific Pitfalls (seen in this codebase)

- **Placeholder endpoints**: routes returning hardcoded data with `# TODO` (e.g. `/chat`).
  Flag any endpoint that does not call into a service.
- **Stub nodes**: `planner`/`recommender` returning hardcoded lists instead of LLM logic.
- **Empty domain layer**: `app/src/<module>/services|repositories` containing only empty
  `__init__.py`. Business logic must live here, not in agent nodes.
- **Node/graph wiring**: a node function signed `node(state, llm)` but added via
  `add_node("x", node)` will raise `TypeError` at runtime — verify DI binding.
- **`Field` as query default**: FastAPI query params must use `Query(...)`, not pydantic `Field(...)`.

## Review Methodology

1. **Verify Previous Comments**: on re-review, map each prior comment to
   ✅ FIXED / ⚠️ PARTIALLY FIXED / ❌ NOT FIXED.
2. **Read Full Context**: review whole files, not isolated diffs.
3. **Severity-rank findings**: 🔴 Blocker (broken/insecure) → 🟠 Major (violates architecture)
   → 🟡 Minor (style/cleanup). Lead with blockers.
4. **Don't be a zealot**: accept the simplest option when a "violation" is pragmatic; don't
   invent hypothetical edge cases that won't realistically occur.
5. **Anchor findings** to `file:line` and give a concrete fix.

## Code Examples

### ❌ Bad: imperative, loose typing, bare except, float money
```python
def get_total(txs) -> float:
    total = 0.0
    try:
        for t in txs:
            total += t["amount"]
    except:
        pass
    return total
```

### ✅ Good: declarative, strict typing, specific exceptions, Decimal
```python
from decimal import Decimal

def get_total(transactions: list[Transaction]) -> Decimal:
    try:
        return sum((t.amount for t in transactions), start=Decimal("0"))
    except (TypeError, KeyError) as e:
        logger.error("Failed to total transactions", error=str(e))
        raise InvalidTransactionError("Malformed transaction data") from e
```

## Commands

```bash
# Static checks (run before approving)
uv run ruff check .
uv run mypy app/
uv run pytest -q

# Local diff review (no GitHub remote required)
git diff --stat
git diff > /tmp/diff.txt
```

## Output Format

Produce a Markdown report:
- **Summary**: 1–3 lines + overall verdict (APPROVE / CHANGES REQUESTED).
- **Findings**: grouped by severity, each as `severity — file:line — problem — fix`.
- **Checklist**: the Critical Patterns above marked ✅/⚠️/❌.

## Resources

- `docs/MODULE_STRUCTURE_GUIDE.md` — module layout & layer responsibilities.
- `docs/ARCHITECTURE.md` — system architecture, agent graph, RAG pipeline.
- Sibling skills: `pytest`, `langchain-architecture`, `systematic-debugging`,
  `verification-before-completion`, `langfuse`.
