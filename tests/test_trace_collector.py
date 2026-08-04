import pytest

from tracing.collector import TraceCollector
from tracing.models import TraceNodeType, TraceStatus


@pytest.mark.asyncio
async def test_root_and_nested_spans_record_parent_and_latency() -> None:
    collector = TraceCollector(run_id="test-run")

    async with collector.span(TraceNodeType.AGENT_EXECUTION, "agent") as root:
        async with collector.span(TraceNodeType.TOOL_EXECUTION, "search_policy") as child:
            collector.complete_span(child, output_data={"ok": True})
        collector.complete_span(root, output_data={"done": True})

    assert collector.trace.spans == [root, child]
    assert root.parent_span_id is None
    assert child.parent_span_id == root.span_id
    assert root.status == TraceStatus.SUCCESS
    assert child.status == TraceStatus.SUCCESS
    assert root.ended_at is not None
    assert child.ended_at is not None
    assert root.latency_ms is not None and root.latency_ms >= 0
    assert child.latency_ms is not None and child.latency_ms >= 0


@pytest.mark.asyncio
async def test_exception_marks_span_error_and_reraises() -> None:
    collector = TraceCollector(run_id="test-run")

    with pytest.raises(RuntimeError, match="boom"):
        async with collector.span(TraceNodeType.SYNTHESIS, "answer"):
            raise RuntimeError("boom")

    span = collector.trace.spans[0]
    assert span.status == TraceStatus.ERROR
    assert span.error == "boom"
    assert span.ended_at is not None
    assert span.latency_ms is not None and span.latency_ms >= 0
