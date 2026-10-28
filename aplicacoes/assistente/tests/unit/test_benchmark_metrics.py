"""Testes puros da telemetria de ferramentas do benchmark."""

from uuid import uuid4

from sei_ia.services.benchmark_metrics import (
    BenchmarkToolHandler,
    classify_tool,
    current_collector,
    reset_current_collector,
    set_current_collector,
)


def test_classify_tool_uses_explicit_categories():
    assert classify_tool("web_research_search") == "web"
    assert classify_tool("read_file") == "filesystem"
    assert classify_tool("task") == "subagent"
    assert classify_tool("retrieve_chunks") == "rag"
    assert classify_tool("future_tool") == "unclassified"


def test_handler_records_success_error_and_web_references():
    handler = BenchmarkToolHandler()
    ok_run = uuid4()
    error_run = uuid4()
    handler.on_tool_start({"name": "web_research_search"}, "q", run_id=ok_run)
    handler.on_tool_end(
        [{"references": [{"url": "https://a.example"}, {"url": "https://b.example"}]}],
        run_id=ok_run,
    )
    handler.on_tool_start({"name": "read_file"}, "x", run_id=error_run)
    handler.on_tool_error(RuntimeError("failed"), run_id=error_run)

    summary = handler.summary()

    assert summary["total_calls"] == 2
    assert summary["calls_by_category"] == {"filesystem": 1, "web": 1}
    assert summary["web_references_returned"] == 2
    assert summary["web_unique_urls_returned"] == 2
    assert {call["outcome"] for call in summary["calls"]} == {"success", "error"}


def test_handler_marks_unfinished_calls_without_dropping_them():
    handler = BenchmarkToolHandler()
    handler.on_tool_start({"name": "unknown"}, "x", run_id=uuid4())

    summary = handler.summary()

    assert summary["observability_status"] == "N/D"
    assert summary["total_calls"] is None
    assert summary["calls"][0]["outcome"] == "unfinished"
    assert summary["calls"][0]["status"] == "N/D"
    assert summary["calls"][0]["category"] == "unclassified"


def test_handler_counts_grep_content_paths_with_line_numbers():
    handler = BenchmarkToolHandler(document_paths=["/proc/doc.txt"])
    run_id = uuid4()
    handler.on_tool_start(
        {"name": "grep"},
        "ignored",
        run_id=run_id,
        inputs={"path": "/", "output_mode": "content"},
    )
    handler.on_tool_end(
        "/proc/doc.txt:12:linha encontrada\n/proc/doc.txt:18:outra linha",
        run_id=run_id,
    )

    call = handler.summary()["calls"][0]

    assert call["files_returned"] == call["files_scanned"]


def test_classic_web_bridge_uses_request_context_without_serializing_state():
    handler = BenchmarkToolHandler()
    token = set_current_collector(handler)
    try:
        assert current_collector() is handler
        call = current_collector().start_external_tool("deep_research_search")
        current_collector().finish_external_tool(
            call, [{"references": [{"url": "https://classic.example"}]}]
        )
    finally:
        reset_current_collector(token)

    summary = handler.summary()

    assert current_collector() is None
    assert summary["calls"][0]["source"] == "classic_web_bridge"
    assert summary["calls"][0]["category"] == "web"
