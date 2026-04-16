"""Logfire/OpenTelemetry tracing for mcp-getgather.

Owns all observability wiring:
- Logfire configuration and FastAPI/httpx instrumentation
- Loguru → Logfire handler
- Per-request `mcp-session-id` generation, propagation, and session-trace
  reparenting via a raw ASGI middleware

The `mcp-session-id` header exists solely for observability. The MCP server
runs in stateless_http mode (for multi-instance deployment), so it doesn't
assign session IDs on its own. We generate one per client and echo it back
so the client SDK reuses it across requests.

To make all spans for a session appear under one clickable trace in Logfire,
we reparent every request's spans under a deterministic "MCP Session" root
span. The outer ASGI middleware rewrites the incoming W3C traceparent to
point at the session root BEFORE OpenTelemetry's FastAPI instrumentation
extracts it — otherwise OTel would parent spans under the caller's trace.
The caller's original traceparent is stashed in the scope so the inner
FastAPI middleware can attach it as a span link for discoverability.

The session ID is a uuid4().hex (32 hex chars), which doubles as a valid
OTel trace_id — so the session ID literally IS the trace ID and can be
pasted into Logfire to find the trace.
"""

import hashlib
import os
import uuid
from typing import TYPE_CHECKING

import logfire
from fastapi import FastAPI, Request
from loguru import logger
from opentelemetry import trace
from opentelemetry.sdk.trace import _Span as SDKSpan  # pyright: ignore[reportPrivateUsage]
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import Link, SpanContext, TraceFlags
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from getgather.config import settings

if TYPE_CHECKING:
    from loguru import HandlerConfig


MCP_SESSION_ID_HEADER = b"mcp-session-id"
TRACEPARENT_HEADER = b"traceparent"
TRACESTATE_HEADER = b"tracestate"

SCOPE_SESSION_ID_KEY = "mcp_session_id"
SCOPE_CALLER_TRACEPARENT_KEY = "mcp_session_caller_traceparent"
SCOPE_CALLER_TRACESTATE_KEY = "mcp_session_caller_tracestate"


def setup_logfire() -> None:
    if not settings.LOGFIRE_TOKEN:
        logger.warning("Logfire is disabled, no LOGFIRE_TOKEN provided")
        return

    logger.info("Initializing Logfire")
    logfire.configure(
        service_name="mcp-getgather",
        send_to_logfire="if-token-present",
        token=settings.LOGFIRE_TOKEN,
        environment=settings.ENVIRONMENT,
        code_source=logfire.CodeSource(
            repository="https://github.com/remotebrowser/mcp-getgather", revision="main"
        ),
        distributed_tracing=True,
        console=False,
        scrubbing=False,
    )
    logfire.instrument_httpx()


def instrument_fastapi(app: FastAPI) -> None:
    if not settings.LOGFIRE_TOKEN:
        return
    logfire.instrument_fastapi(app, capture_headers=True, excluded_urls="/health")


def logfire_loguru_handler() -> "HandlerConfig | None":
    if not settings.LOGFIRE_TOKEN:
        return None
    handler = logfire.loguru_handler()
    handler["level"] = settings.LOG_LEVEL
    return handler


_emitted_session_root_spans: set[str] = set()


_SESSION_INSTRUMENTATION_SCOPE = InstrumentationScope("getgather.session")


def _mcp_endpoint_from_path(path: str) -> str:
    return path.removeprefix("/mcp").strip("/").split("/")[0] or "root"


class MCPSessionTraceMiddleware:
    """Raw ASGI middleware that reparents /mcp request spans under a session trace.

    Must wrap the FastAPI app from OUTSIDE OpenTelemetry's instrumentation.
    OTel's FastAPIInstrumentor wraps the entire user-middleware stack via
    `build_middleware_stack`, so a `@app.middleware("http")` runs too late —
    OTel has already extracted traceparent and parented the request span
    under the caller's trace. This middleware rewrites the scope headers
    BEFORE the instrumented app sees them.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        headers: list[tuple[bytes, bytes]] = list(scope["headers"])
        header_map: dict[bytes, bytes] = {k: v for k, v in headers}

        raw_session_id = header_map.get(MCP_SESSION_ID_HEADER, b"").decode() or None
        mcp_session_id = raw_session_id or uuid.uuid4().hex

        caller_traceparent = header_map.get(TRACEPARENT_HEADER, b"").decode() or None
        caller_tracestate = header_map.get(TRACESTATE_HEADER, b"").decode() or None

        endpoint = _mcp_endpoint_from_path(scope.get("path", ""))
        self._emit_mcp_session_root_span_once(mcp_session_id, endpoint)
        session_traceparent = self._traceparent_for_mcp_session(mcp_session_id)

        # Strip traceparent/tracestate/mcp-session-id; append our rewritten versions.
        stripped = [
            (k, v)
            for k, v in headers
            if k not in (TRACEPARENT_HEADER, TRACESTATE_HEADER, MCP_SESSION_ID_HEADER)
        ]
        stripped.append((TRACEPARENT_HEADER, session_traceparent))
        stripped.append((MCP_SESSION_ID_HEADER, mcp_session_id.encode()))
        scope["headers"] = stripped

        scope[SCOPE_SESSION_ID_KEY] = mcp_session_id
        scope[SCOPE_CALLER_TRACEPARENT_KEY] = caller_traceparent
        scope[SCOPE_CALLER_TRACESTATE_KEY] = caller_tracestate

        session_id_header_bytes = mcp_session_id.encode()

        async def send_with_session_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing: list[tuple[bytes, bytes]] = list(message.get("headers") or [])
                response_headers = [(k, v) for k, v in existing if k != MCP_SESSION_ID_HEADER]
                response_headers.append((MCP_SESSION_ID_HEADER, session_id_header_bytes))
                message["headers"] = response_headers
            await send(message)

        await self.app(scope, receive, send_with_session_id)

    @classmethod
    def _traceparent_for_mcp_session(cls, mcp_session_id: str) -> bytes:
        ctx = cls._span_context_from_mcp_session_id(mcp_session_id)
        return f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-01".encode()

    @classmethod
    def _emit_mcp_session_root_span_once(cls, mcp_session_id: str, endpoint: str) -> None:
        if mcp_session_id in _emitted_session_root_spans:
            return
        _emitted_session_root_spans.add(mcp_session_id)

        # tracer.start_span() assigns a random span_id from the provider's
        # IdGenerator, which would mean our deterministic session span_id (used
        # as the parent in the injected traceparent) never matches any emitted
        # span — leaving the session trace with an orphaned root. Construct the
        # SDK _Span directly so we control both trace_id AND span_id.
        provider = trace.get_tracer_provider()
        sdk_provider = getattr(provider, "provider", provider)  # unwrap logfire proxy
        span_processor = getattr(sdk_provider, "_active_span_processor", None)
        resource = getattr(sdk_provider, "resource", None)
        if span_processor is None or resource is None:
            return  # not an SDK TracerProvider — nothing to export to

        session_ctx = cls._span_context_from_mcp_session_id(mcp_session_id)
        span = SDKSpan(
            name=f"MCP root, endpoint {endpoint}, session {mcp_session_id}",
            context=session_ctx,
            parent=None,
            resource=resource,
            span_processor=span_processor,
            instrumentation_scope=_SESSION_INSTRUMENTATION_SCOPE,
            attributes={"mcp.mcp_session_id": mcp_session_id, "mcp.endpoint": endpoint},
        )
        span.start()
        span.end()

    @classmethod
    def _span_context_from_mcp_session_id(cls, mcp_session_id: str) -> SpanContext:
        # A uuid4().hex is 32 hex chars = 128 bits, a valid OTel trace_id. Use
        # it directly so the session ID IS the trace ID. Fall back to SHA-256
        # for any non-hex input.
        try:
            trace_id = int(mcp_session_id, 16) & ((1 << 128) - 1)
            span_id = int(mcp_session_id[:16], 16) & ((1 << 64) - 1)
            if trace_id == 0 or span_id == 0:
                raise ValueError("invalid session id")
        except ValueError:
            digest = hashlib.sha256(mcp_session_id.encode()).digest()
            trace_id = int.from_bytes(digest[:16])
            span_id = int.from_bytes(digest[16:24])
        return SpanContext(
            trace_id=trace_id, span_id=span_id, is_remote=True, trace_flags=TraceFlags(1)
        )


def setup_mcp_tracing(request: Request) -> str:
    mcp_session_id: str = request.scope[SCOPE_SESSION_ID_KEY]

    if not settings.LOGFIRE_TOKEN:
        return mcp_session_id

    endpoint = _mcp_endpoint_from_path(request.url.path)

    # 1. ensure the mcp_session_id is set in the current span
    trace.get_current_span().set_attribute("mcp.mcp_session_id", mcp_session_id)

    caller_traceparent = request.scope.get(SCOPE_CALLER_TRACEPARENT_KEY)
    if not caller_traceparent:
        return mcp_session_id

    caller_tracestate = request.scope.get(SCOPE_CALLER_TRACESTATE_KEY)

    # 2. link the current span to the caller
    _link_current_span_to_caller(caller_traceparent, caller_tracestate)

    # 3. link the caller trace to the current span via a bridge span
    _emit_caller_trace_bridge_span(caller_traceparent, caller_tracestate, mcp_session_id, endpoint)

    return mcp_session_id


def _link_current_span_to_caller(
    caller_traceparent: str, caller_tracestate: str | None = None
) -> None:
    carrier: dict[str, str] = {"traceparent": caller_traceparent}
    if caller_tracestate:
        carrier["tracestate"] = caller_tracestate
    extracted = TraceContextTextMapPropagator().extract(carrier=carrier)
    caller_span_context = trace.get_current_span(extracted).get_span_context()
    if not caller_span_context.is_valid:
        return
    attributes: dict[str, str] = {"caller.traceparent": caller_traceparent}
    if caller_tracestate:
        attributes["caller.tracestate"] = caller_tracestate
    trace.get_current_span().add_link(caller_span_context, attributes)


def _emit_caller_trace_bridge_span(
    caller_traceparent: str,
    caller_tracestate: str | None,
    mcp_session_id: str,
    endpoint: str,
) -> None:
    # Emits a short-lived span parented to the CALLER's trace (not ours),
    # holding an OTel span link to the current server request span. Because
    # its trace_id/parent come from the incoming traceparent, Logfire ingests
    # it into the client's trace — appearing as a child of the caller's
    # httpx span. Clicking its link navigates client → server session trace.
    carrier: dict[str, str] = {"traceparent": caller_traceparent}
    if caller_tracestate:
        carrier["tracestate"] = caller_tracestate
    extracted = TraceContextTextMapPropagator().extract(carrier=carrier)
    caller_ctx = trace.get_current_span(extracted).get_span_context()
    if not caller_ctx.is_valid:
        return

    server_ctx = trace.get_current_span().get_span_context()
    if not server_ctx.is_valid:
        return

    provider = trace.get_tracer_provider()
    sdk_provider = getattr(provider, "provider", provider)  # unwrap logfire proxy
    span_processor = getattr(sdk_provider, "_active_span_processor", None)
    resource = getattr(sdk_provider, "resource", None)
    if span_processor is None or resource is None:
        return

    # Fresh span_id in the caller's trace. Force non-zero.
    bridge_span_id = int.from_bytes(os.urandom(8)) or 1
    bridge_ctx = SpanContext(
        trace_id=caller_ctx.trace_id,
        span_id=bridge_span_id,
        is_remote=False,
        trace_flags=TraceFlags(1),  # force sampled; don't inherit caller's flags
    )

    span = SDKSpan(
        name=f"MCP bridge, endpoint {endpoint}, session {mcp_session_id}",
        context=bridge_ctx,
        parent=caller_ctx,
        resource=resource,
        span_processor=span_processor,
        instrumentation_scope=_SESSION_INSTRUMENTATION_SCOPE,
        attributes={
            "mcp.mcp_session_id": mcp_session_id,
            "mcp.endpoint": endpoint,
            "server.trace_id": f"{server_ctx.trace_id:032x}",
            "server.span_id": f"{server_ctx.span_id:016x}",
        },
        links=[Link(server_ctx, {"mcp.mcp_session_id": mcp_session_id})],
    )
    span.start()
    span.end()
