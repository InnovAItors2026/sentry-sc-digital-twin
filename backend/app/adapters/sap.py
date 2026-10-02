"""SAP integration stub. No live SAP connection is claimed."""

from __future__ import annotations

from typing import Any

from app.data.demo_network import build_demo_network
from app.domain.models import NetworkSnapshot


class SapNetworkAdapter:
    """Placeholder for the SAP/backend team.

    Replace `load_network` with IDoc / OData / event mapping when SAP is available.
    """

    def available(self) -> bool:
        return False

    def load_network(self) -> NetworkSnapshot:
        if self.available():
            raise RuntimeError("SAP adapter marked available but no connector is implemented")
        return build_demo_network()

    def push_simulation_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "accepted": False,
            "reason": "SAP connector not configured. Result retained in SENTRY-SC scenario store only.",
        }
