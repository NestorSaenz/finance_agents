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

    def test_tool_span_is_noop_when_disabled(self) -> None:
        with observability.start_tool_span("tool:register", {"a": 1}) as span:
            assert span is None
            # Must not raise even though there is no real span to update.
            observability.record_tool_span(span, output="ok")
        observability.record_tool_span(None, output="x", error="boom")


class TestEnabled:
    def _install_fake_sdk(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
        """Register fake ``langfuse`` modules so no network/keys are needed."""
        spy: dict[str, object] = {"flushed": False, "client": None}

        class FakeSpan:
            def __init__(self) -> None:
                self.updates: list[dict[str, object]] = []

            def update(self, **kwargs: object) -> None:
                self.updates.append(kwargs)

            def __enter__(self) -> "FakeSpan":
                return self

            def __exit__(self, *exc: object) -> None:
                return None

        class FakeClient:
            def flush(self) -> None:
                spy["flushed"] = True

            def start_as_current_span(self, *, name: str, input: object) -> "FakeSpan":
                span = FakeSpan()
                spy["span"] = span
                spy["span_name"] = name
                return span

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
            "release": observability.settings.RELEASE or None,
        }

        callbacks = observability.get_trace_callbacks()
        assert len(callbacks) == 1

    def test_flush_calls_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = self._install_fake_sdk(monkeypatch)
        observability.init_observability()

        observability.flush_observability()

        assert spy["flushed"] is True

    def test_tool_span_records_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = self._install_fake_sdk(monkeypatch)
        observability.init_observability()

        with observability.start_tool_span("tool:register", {"amount": 100}) as span:
            observability.record_tool_span(span, output="done")

        assert spy["span_name"] == "tool:register"
        assert spy["span"].updates == [{"output": "done"}]  # type: ignore[union-attr]

    def test_tool_span_records_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = self._install_fake_sdk(monkeypatch)
        observability.init_observability()

        with observability.start_tool_span("tool:register", {}) as span:
            observability.record_tool_span(span, output="msg", error="bad")

        assert spy["span"].updates == [  # type: ignore[union-attr]
            {"output": "msg", "level": "ERROR", "status_message": "bad"}
        ]

    def test_tool_span_degrades_when_sdk_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        spy = self._install_fake_sdk(monkeypatch)
        observability.init_observability()

        def boom(**_: object) -> object:
            raise RuntimeError("sdk down")

        monkeypatch.setattr(spy["client"], "start_as_current_span", boom)

        entered = False
        # A failing SDK must not turn a working tool call into an error.
        with observability.start_tool_span("tool:register", {}) as span:
            entered = True
            assert span is None
            observability.record_tool_span(span, output="ok")  # no-op

        assert entered is True
