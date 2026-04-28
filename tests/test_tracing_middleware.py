import asyncio
import uuid
from typing import Any

import pytest
from starlette.types import Message, Receive, Scope, Send

from getgather import tracing
from getgather.tracing import (
    MCP_SESSION_ID_HEADER,
    SCOPE_SESSION_ID_KEY,
    TRACEPARENT_HEADER,
    TRACESTATE_HEADER,
    MCPSessionTraceMiddleware,
)


class _CapturingApp:
    def __init__(self) -> None:
        self.scope: Scope | None = None
        self.received_headers: list[tuple[bytes, bytes]] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.scope = scope
        self.received_headers = list(scope["headers"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})


async def _drive(middleware: MCPSessionTraceMiddleware, scope: Scope) -> list[Message]:
    sent: list[Message] = []

    async def _receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def _send(msg: Message) -> None:
        sent.append(msg)

    await middleware(scope, _receive, _send)
    return sent


@pytest.fixture(autouse=True)
def clear_emitted_session_root_spans() -> Any:
    tracing._emitted_session_root_spans.clear()  # pyright: ignore[reportPrivateUsage]
    yield


def _http_scope(path: str, headers: list[tuple[bytes, bytes]]) -> Scope:
    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "raw_path": path.encode(),
        "headers": headers,
        "query_string": b"",
    }
    return scope


def test_case1_caller_traceparent_passes_through_unchanged() -> None:
    inner = _CapturingApp()
    middleware = MCPSessionTraceMiddleware(inner)
    session_id = uuid.uuid4().hex
    caller_traceparent = b"00-12345678901234567890123456789012-1234567890123456-01"
    caller_tracestate = b"vendor=foo"

    scope = _http_scope(
        "/mcp/",
        [
            (TRACEPARENT_HEADER, caller_traceparent),
            (TRACESTATE_HEADER, caller_tracestate),
            (MCP_SESSION_ID_HEADER, session_id.encode()),
        ],
    )
    sent = asyncio.run(_drive(middleware, scope))

    assert inner.scope is not None
    assert inner.scope[SCOPE_SESSION_ID_KEY] == session_id

    received = dict(inner.received_headers)
    assert received[TRACEPARENT_HEADER] == caller_traceparent
    assert received[TRACESTATE_HEADER] == caller_tracestate
    assert received[MCP_SESSION_ID_HEADER] == session_id.encode()

    assert session_id not in tracing._emitted_session_root_spans  # pyright: ignore[reportPrivateUsage]

    start = next(m for m in sent if m["type"] == "http.response.start")
    response_headers = dict(start["headers"])
    assert response_headers[MCP_SESSION_ID_HEADER] == session_id.encode()


def test_case2_no_traceparent_injects_session_traceparent_and_emits_root_once() -> None:
    inner = _CapturingApp()
    middleware = MCPSessionTraceMiddleware(inner)
    session_id = uuid.uuid4().hex

    scope = _http_scope("/mcp/", [(MCP_SESSION_ID_HEADER, session_id.encode())])
    asyncio.run(_drive(middleware, scope))

    assert inner.scope is not None
    received = dict(inner.received_headers)
    expected_traceparent = MCPSessionTraceMiddleware._traceparent_for_mcp_session(session_id)  # pyright: ignore[reportPrivateUsage]
    assert received[TRACEPARENT_HEADER] == expected_traceparent
    assert TRACESTATE_HEADER not in received
    assert received[MCP_SESSION_ID_HEADER] == session_id.encode()
    assert session_id in tracing._emitted_session_root_spans  # pyright: ignore[reportPrivateUsage]

    # Second request with same session id reuses the root span (no re-emit).
    inner2 = _CapturingApp()
    middleware2 = MCPSessionTraceMiddleware(inner2)
    scope2 = _http_scope("/mcp/", [(MCP_SESSION_ID_HEADER, session_id.encode())])
    asyncio.run(_drive(middleware2, scope2))
    assert inner2.scope is not None
    assert (
        dict(inner2.received_headers)[TRACEPARENT_HEADER] == expected_traceparent
    )  # still session-deterministic


def test_no_mcp_session_id_header_generates_one() -> None:
    inner = _CapturingApp()
    middleware = MCPSessionTraceMiddleware(inner)

    scope = _http_scope("/mcp/", [])
    sent = asyncio.run(_drive(middleware, scope))

    assert inner.scope is not None
    generated_id = inner.scope[SCOPE_SESSION_ID_KEY]
    assert isinstance(generated_id, str) and len(generated_id) == 32
    int(generated_id, 16)  # valid hex

    received = dict(inner.received_headers)
    assert received[MCP_SESSION_ID_HEADER] == generated_id.encode()

    start = next(m for m in sent if m["type"] == "http.response.start")
    response_headers = dict(start["headers"])
    assert response_headers[MCP_SESSION_ID_HEADER] == generated_id.encode()


def test_invalid_caller_traceparent_falls_back_to_case2() -> None:
    inner = _CapturingApp()
    middleware = MCPSessionTraceMiddleware(inner)
    session_id = uuid.uuid4().hex

    scope = _http_scope(
        "/mcp/",
        [
            (TRACEPARENT_HEADER, b"not-a-valid-traceparent"),
            (MCP_SESSION_ID_HEADER, session_id.encode()),
        ],
    )
    asyncio.run(_drive(middleware, scope))

    received = dict(inner.received_headers)
    expected_traceparent = MCPSessionTraceMiddleware._traceparent_for_mcp_session(session_id)  # pyright: ignore[reportPrivateUsage]
    assert received[TRACEPARENT_HEADER] == expected_traceparent
    assert session_id in tracing._emitted_session_root_spans  # pyright: ignore[reportPrivateUsage]


def test_non_mcp_path_is_passthrough() -> None:
    inner = _CapturingApp()
    middleware = MCPSessionTraceMiddleware(inner)

    original_headers = [(b"x-foo", b"bar")]
    scope = _http_scope("/health", list(original_headers))
    asyncio.run(_drive(middleware, scope))

    assert inner.scope is not None
    assert SCOPE_SESSION_ID_KEY not in inner.scope
    assert inner.received_headers == original_headers
