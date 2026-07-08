"""Unit tests for Langfuse observability wiring (safe no-op + enabled path)."""

import sys
import types
from collections.abc import Iterator

import pytest

from app.core import observability


@pytest.fixture(autouse=True)
def reset_state() -> Iterator[None]:
    """Isolate the module-level ``_enabled`` flag between tests."""
    original = observability._enabled
    observability._enabled = False
    yield
    observability._enabled = original


class TestDisabled:
    def test_no_keys_keeps_tracing_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(observability.settings, "LANGFUSE_PUBLIC_KEY", "")
        monkeypatch.setattr(observability.settings, "LANGFUSE_SECRET_KEY", "")

        observability.init_observability()

        assert observability._enabled is False

    def test_callbacks_empty_when_disabled(self) -> None:
        assert observability.get_trace_callbacks() == []

    def test_flush_is_noop_when_disabled(self) -> None:
        observability.flush_observability()  # must not raise


class TestEnabled:
    def _install_fake_sdk(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
        """Register fake ``langfuse`` modules so no network/keys are needed."""
        spy: dict[str, object] = {"flushed": False, "client": None}

        class FakeClient:
            def flush(self) -> None:
                spy["flushed"] = True

        client = FakeClient()
        spy["client"] = client

        class FakeLangfuse:
            def __init__(self, **kwargs: object) -> None:
                spy["init_kwargs"] = kwargs

        class FakeCallbackHandler:
            pass

        langfuse_mod = types.ModuleType("langfuse")
        langfuse_mod.Langfuse = FakeLangfuse  # type: ignore[attr-defined]
        langfuse_mod.get_client = lambda: client  # type: ignore[attr-defined]
        langchain_mod = types.ModuleType("langfuse.langchain")
        langchain_mod.CallbackHandler = FakeCallbackHandler  # type: ignore[attr-defined]

        monkeypatch.setitem(sys.modules, "langfuse", langfuse_mod)
        monkeypatch.setitem(sys.modules, "langfuse.langchain", langchain_mod)
        monkeypatch.setattr(observability.settings, "LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setattr(observability.settings, "LANGFUSE_SECRET_KEY", "sk-test")
        return spy

    def test_init_enables_and_builds_handler(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = self._install_fake_sdk(monkeypatch)

        observability.init_observability()

        assert observability._enabled is True
        assert spy["init_kwargs"] == {
            "public_key": "pk-test",
            "secret_key": "sk-test",
            "host": observability.settings.LANGFUSE_HOST,
        }

        callbacks = observability.get_trace_callbacks()
        assert len(callbacks) == 1

    def test_flush_calls_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = self._install_fake_sdk(monkeypatch)
        observability.init_observability()

        observability.flush_observability()

        assert spy["flushed"] is True
