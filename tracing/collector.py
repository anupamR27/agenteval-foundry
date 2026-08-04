from __future__ import annotations

import time
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from types import TracebackType
from typing import Any
from uuid import UUID

from tracing.models import ExecutionTrace, TraceNodeType, TraceSpan, TraceStatus

_ACTIVE_SPAN_ID: ContextVar[UUID | None] = ContextVar("active_trace_span_id", default=None)


class TraceCollector:
    """Owns an in-memory execution trace and span lifecycle."""

    def __init__(self, run_id: UUID | str) -> None:
        self.trace = ExecutionTrace(run_id=run_id)
        self._started_monotonic: dict[UUID, float] = {}

    def span(
        self,
        node_type: TraceNodeType,
        name: str,
        input_data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceSpanContext:
        return TraceSpanContext(
            collector=self,
            node_type=node_type,
            name=name,
            input_data=input_data or {},
            metadata=metadata or {},
        )

    def start_span(
        self,
        node_type: TraceNodeType,
        name: str,
        input_data: dict[str, Any],
        metadata: dict[str, Any],
    ) -> TraceSpan:
        span = TraceSpan(
            trace_id=self.trace.trace_id,
            parent_span_id=_ACTIVE_SPAN_ID.get(),
            node_type=node_type,
            name=name,
            started_at=datetime.now(UTC),
            input_data=input_data,
            metadata=metadata,
        )
        self._started_monotonic[span.span_id] = time.monotonic()
        self.trace.spans.append(span)
        return span

    def complete_span(self, span: TraceSpan, output_data: dict[str, Any] | None = None) -> None:
        self._finish_span(span, TraceStatus.SUCCESS, output_data=output_data or {}, error=None)

    def fail_span(
        self,
        span: TraceSpan,
        error: str,
        output_data: dict[str, Any] | None = None,
    ) -> None:
        self._finish_span(span, TraceStatus.ERROR, output_data=output_data or {}, error=error)

    def _finish_span(
        self,
        span: TraceSpan,
        status: TraceStatus,
        output_data: dict[str, Any],
        error: str | None,
    ) -> None:
        if span.ended_at is not None:
            return

        started = self._started_monotonic.pop(span.span_id)
        span.ended_at = datetime.now(UTC)
        span.latency_ms = max((time.monotonic() - started) * 1000, 0.0)
        span.status = status
        span.output_data = output_data
        span.error = error


class TraceSpanContext:
    """Async context manager that propagates the current parent span."""

    def __init__(
        self,
        collector: TraceCollector,
        node_type: TraceNodeType,
        name: str,
        input_data: dict[str, Any],
        metadata: dict[str, Any],
    ) -> None:
        self._collector = collector
        self._node_type = node_type
        self._name = name
        self._input_data = input_data
        self._metadata = metadata
        self._token: Token[UUID | None] | None = None
        self.span: TraceSpan | None = None

    async def __aenter__(self) -> TraceSpan:
        self.span = self._collector.start_span(
            node_type=self._node_type,
            name=self._name,
            input_data=self._input_data,
            metadata=self._metadata,
        )
        self._token = _ACTIVE_SPAN_ID.set(self.span.span_id)
        return self.span

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if self.span is None:
            return False

        if exc is not None:
            self._collector.fail_span(self.span, error=str(exc))
        elif self.span.status == TraceStatus.RUNNING:
            self._collector.complete_span(self.span)

        if self._token is not None:
            _ACTIVE_SPAN_ID.reset(self._token)

        return False
