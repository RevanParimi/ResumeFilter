"""In-process counters (S8.3 Phase A).

A :class:`Metrics` instance hangs off the injected ``Services`` bundle and is
therefore PER-APP. A module-level registry would be shared by every test in the
suite, and the first ordering-dependent assertion would be a flake nobody could
reproduce -- which is the same reason ``Services`` exists at all.

Rendered as Prometheus text with no dependency: the exposition format is a
handful of lines, and adding ``prometheus_client`` to buy them would put a
package in the tree that only this file uses.

Durations are a SUM and a COUNT -- an average. No buckets, no quantiles.
Stating that is better than shipping a histogram whose buckets nobody chose.
"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Dict, Tuple

_PREFIX = "veritas_"

#: Counter name -> the metric's help text. A name absent here still renders;
#: this only supplies HELP, so a new counter is never blocked on documentation.
_HELP: Dict[str, str] = {
    "http_requests": "HTTP requests by route template, method and status.",
    "rate_limit_decisions": "Rate-limit decisions by rule, scope and outcome.",
    "llm_calls": "LLM calls by tier and outcome.",
    "asr_calls": "Speech-to-text calls by outcome.",
    "screening_items": "Screening items finished, by outcome.",
    "retention_deleted": "Rows deleted by the retention sweep, by data class.",
}

_LabelKey = Tuple[Tuple[str, str], ...]


def _escape(value: str) -> str:
    """Prometheus label-value escaping: backslash, quote, newline."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class Metrics:
    def __init__(self) -> None:
        self._counters: Dict[Tuple[str, _LabelKey], int] = defaultdict(int)
        self._duration_sum: Dict[str, float] = defaultdict(float)
        self._duration_count: Dict[str, int] = defaultdict(int)
        self._lock = Lock()

    def increment(self, name: str, **labels: str) -> None:
        key = (name, tuple(sorted((k, str(v)) for k, v in labels.items())))
        with self._lock:
            self._counters[key] += 1

    def observe_duration(self, route: str, ms: float) -> None:
        with self._lock:
            self._duration_sum[route] += ms
            self._duration_count[route] += 1

    def snapshot(self) -> Dict[Tuple[str, _LabelKey], int]:
        with self._lock:
            return dict(self._counters)

    def render(self) -> str:
        """The Prometheus text exposition format, sorted for a stable document."""
        with self._lock:
            counters = dict(self._counters)
            d_sum = dict(self._duration_sum)
            d_count = dict(self._duration_count)

        lines: list[str] = []
        by_metric: Dict[str, list[Tuple[_LabelKey, int]]] = defaultdict(list)
        for (name, labels), value in counters.items():
            by_metric[name].append((labels, value))

        for name in sorted(by_metric):
            full = f"{_PREFIX}{name}_total"
            if name in _HELP:
                lines.append(f"# HELP {full} {_HELP[name]}")
            lines.append(f"# TYPE {full} counter")
            for labels, value in sorted(by_metric[name]):
                rendered = ",".join(f'{k}="{_escape(v)}"' for k, v in labels)
                lines.append(f"{full}{{{rendered}}} {value}")

        if d_count:
            lines.append(f"# TYPE {_PREFIX}http_request_duration_ms_sum counter")
            for route in sorted(d_sum):
                lines.append(
                    f"{_PREFIX}http_request_duration_ms_sum"
                    f'{{route="{_escape(route)}"}} {d_sum[route]:g}'
                )
            lines.append(f"# TYPE {_PREFIX}http_request_duration_ms_count counter")
            for route in sorted(d_count):
                lines.append(
                    f"{_PREFIX}http_request_duration_ms_count"
                    f'{{route="{_escape(route)}"}} {d_count[route]}'
                )

        return "\n".join(lines)


def build_metrics() -> Metrics:
    return Metrics()
