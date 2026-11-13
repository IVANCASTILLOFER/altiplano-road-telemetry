"""Alert engine: raise on entering WARNING+, clear after consecutive safe readings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .physics import RoadRisk

ALERT_LEVEL = RoadRisk.WARNING
CLEAR_AFTER = 2  # consecutive readings below ALERT_LEVEL before an alert is cleared


@dataclass
class Alert:
    ts: float
    node_id: int
    kind: str  # 'raised' | 'cleared' | 'node_silent'
    risk: RoadRisk | None
    message: str


@dataclass
class _NodeState:
    active: bool = False
    level: RoadRisk = RoadRisk.OK
    calm: int = 0


@dataclass
class AlertEngine:
    sinks: list[Callable[[Alert], None]] = field(default_factory=list)
    _state: dict[int, _NodeState] = field(default_factory=dict)

    def _emit(self, alert: Alert) -> Alert:
        for sink in self.sinks:
            sink(alert)
        return alert

    def update(self, ts: float, node_id: int, risk: RoadRisk, reason: str) -> Alert | None:
        st = self._state.setdefault(node_id, _NodeState())
        if risk >= ALERT_LEVEL:
            st.calm = 0
            escalated = risk > st.level
            st.level = max(st.level, risk) if st.active else risk
            if not st.active or escalated:
                st.active = True
                return self._emit(Alert(ts, node_id, "raised", risk, f"node {node_id}: {risk.name} - {reason}"))
            return None
        if st.active:
            st.calm += 1
            if st.calm >= CLEAR_AFTER:
                st.active, st.level, st.calm = False, RoadRisk.OK, 0
                return self._emit(Alert(ts, node_id, "cleared", risk, f"node {node_id}: back to {risk.name}"))
        else:
            st.level = risk
        return None

    def node_silent(self, ts: float, node_id: int, minutes: float) -> Alert:
        return self._emit(Alert(ts, node_id, "node_silent", None, f"node {node_id}: no data for {minutes:.0f} min"))
