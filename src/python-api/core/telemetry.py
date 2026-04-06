"""OpenTelemetry configuration for OneStopAgent.

Configures TracerProvider with:
  - ConsoleSpanExporter for local dev (always on)
  - OTLPSpanExporter for production (when APPLICATIONINSIGHTS_CONNECTION_STRING is set)

The agent-framework package already instruments its own calls; this module
adds the exporter pipeline and exposes helpers for custom spans.
"""

from __future__ import annotations

import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

logger = logging.getLogger(__name__)


def setup_telemetry() -> None:
    """Initialise the global TracerProvider. Call once at app startup."""
    # Don't override if MAF or another library already set a provider
    current = trace.get_tracer_provider()
    provider_name = type(current).__name__
    if provider_name != "ProxyTracerProvider":
        return  # Already initialized by agent-framework or another library

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
            logger.info("OTLP exporter not installed — telemetry export disabled")

    trace.set_tracer_provider(provider)


def get_tracer(name: str = __name__) -> trace.Tracer:
    """Return a tracer for creating manual spans."""
    return trace.get_tracer(name)
