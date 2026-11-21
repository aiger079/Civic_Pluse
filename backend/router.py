import math
import json
import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

EARTH_RADIUS_METERS = 6371000.0

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates distance between two GPS coordinates in meters using Haversine formula."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return round(EARTH_RADIUS_METERS * c, 1)

class HelperRouter:
    def __init__(self, helpers_filepath: Optional[str] = None):
        if helpers_filepath is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            helpers_filepath = os.path.join(base_dir, "data", "helpers.json")
        self.helpers_filepath = helpers_filepath
        self.helpers: List[Dict[str, Any]] = self._load_helpers()

    def _load_helpers(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.helpers_filepath):
            with open(self.helpers_filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def get_all_helpers(self) -> List[Dict[str, Any]]:
        return self.helpers

    def match_helpers(
        self,
        incident_lat: float,
        incident_lon: float,
        required_capability: Optional[str] = None,
        top_k: int = 5,
        cooldown_hours: float = 2.0
    ) -> List[Dict[str, Any]]:
        """
        Dispatches to top-K closest matching helpers who are available
        and not on cooldown window.
        """
        now = datetime.now(timezone.utc)
        candidates = []

        for helper in self.helpers:
            # 1. Availability check
            if not helper.get("is_available", True):
                continue

            # 2. Daily fatigue check
            if helper.get("daily_pings_count", 0) >= 5:
                continue

            # 3. 2-Hour Cooldown check
            last_dispatched = helper.get("last_dispatched_at")
            if last_dispatched:
                try:
                    last_dt = datetime.fromisoformat(last_dispatched)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    elapsed = (now - last_dt).total_seconds() / 3600.0
                    if elapsed < cooldown_hours:
                        continue  # Cooldown active! Skip to prevent burnout
                except Exception:
                    pass

            # 4. Capability matching
            capabilities = helper.get("capabilities", [])
            match_score = 1.0
            if required_capability:
                req_clean = required_capability.lower().strip()
                has_exact = any(req_clean in cap.lower() for cap in capabilities)
                if has_exact:
                    match_score = 1.0
                elif any("first_aid" in cap or "pump" in cap for cap in capabilities):
                    match_score = 0.6
                else:
                    match_score = 0.3

            # 5. Distance calculation
            dist = haversine_distance(
                incident_lat, incident_lon,
                helper["latitude"], helper["longitude"]
            )

            # Combined score: closer + higher capability match = higher rank
            rank_score = round(match_score / (1.0 + (dist / 100.0)), 4)

            candidates.append({
                "id": helper["id"],
                "name": helper["name"],
                "phone": helper.get("phone", "N/A"),
                "block": helper.get("block", "Unknown"),
                "flat": helper.get("flat", ""),
                "capabilities": capabilities,
                "distance_meters": dist,
                "rank_score": rank_score
            })

        # Sort descending by rank score (best match & closest first)
        candidates.sort(key=lambda x: x["rank_score"], reverse=True)
        return candidates[:top_k]
