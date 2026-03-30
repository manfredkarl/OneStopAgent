"""OpenTelemetry configuration for OneStopAgent.

Configures TracerProvider with:
  - ConsoleSpanExporter for local dev (always on)
  - OTLPSpanExporter for production (when APPLICATIONINSIGHTS_CONNECTION_STRING is set)

The agent-framework package already instruments its own calls; this module
adds the exporter pipeline and exposes helpers for custom spans.
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


def setup_telemetry() -> None:
    """Initialise the global TracerProvider. Call once at app startup."""
    provider = TracerProvider()

    # Always export to console for local dev visibility
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # When an App Insights connection string is present, also export via OTLP
    conn_str = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if conn_str:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            otlp_exporter = OTLPSpanExporter()
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        except ImportError:
            pass  # OTLP exporter not installed — skip silently

    trace.set_tracer_provider(provider)


def get_tracer(name: str = __name__) -> trace.Tracer:
    """Return a tracer for creating manual spans."""
    return trace.get_tracer(name)
