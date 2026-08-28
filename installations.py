"""Persistent, targetable military installations.

The core owns lifecycle and combat behavior.  Every label, icon, durability,
construction cost, vulnerability, and operational effect is supplied by the
mounted DLC's ``military_installations.types`` registry.
"""

from __future__ import annotations

import math


def _finite_number(value, label, minimum=None, maximum=None):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    if minimum is not None and number < minimum:
        raise ValueError(f"{label} must be at least {minimum:g}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{label} must be at most {maximum:g}")
    return number


class MilitaryInstallation:
    """A static construction site, operational target, or destroyed wreck."""

    def __init__(self, installation_id, data, type_registry):
        if not isinstance(data, dict):
            raise ValueError(f"Installation [{installation_id}] must be an object")
        self.id = str(installation_id)
        self.type_id = str(data.get("type_id", ""))
        if self.type_id not in type_registry:
            raise ValueError(
                f"Installation [{installation_id}] references unknown type [{self.type_id}]"
            )
        self.type_registry = type_registry
        profile = type_registry[self.type_id]

        self.name = str(data.get("name", profile["label"])).strip()
        self.faction = str(data.get("faction", "")).strip()
        if not self.name:
            raise ValueError(f"Installation [{installation_id}] requires a name")
        if not self.faction:
            raise ValueError(f"Installation [{installation_id}] requires a faction")

        self.lon = _finite_number(
            data.get("lon"), f"Installation [{installation_id}] longitude", -180.0, 180.0
        )
        self.lat = _finite_number(
            data.get("lat"), f"Installation [{installation_id}] latitude", -90.0, 90.0
        )
        self.construction_progress = _finite_number(
            data.get("construction_progress", 1.0),
            f"Installation [{installation_id}] construction progress",
            0.0,
            1.0,
        )
        self.max_integrity = float(profile["max_integrity"])
        self.integrity = _finite_number(
            data.get("integrity", self.max_integrity),
            f"Installation [{installation_id}] integrity",
            0.0,
            self.max_integrity,
        )
        builder_unit_id = data.get("builder_unit_id")
        self.builder_unit_id = (
            str(builder_unit_id).strip() if builder_unit_id is not None else None
        ) or None
        self.altitude = _finite_number(
            data.get("altitude", 0.0), f"Installation [{installation_id}] altitude"
        )
        self.current_province = str(data.get("current_province", "Unknown"))

    @property
    def profile(self):
        return self.type_registry[self.type_id]

    @property
    def status(self):
        if self.integrity <= 0:
            return "DESTROYED"
        if self.construction_progress < 1.0:
            return "UNDER_CONSTRUCTION"
        return "OPERATIONAL"

    @property
    def is_operational(self):
        return self.status == "OPERATIONAL"

    def apply_damage(self, amount):
        damage = max(0.0, float(amount))
        actual = min(self.integrity, damage)
        self.integrity -= actual
        return actual

    def to_dict(self):
        profile = self.profile
        return {
            "id": self.id,
            "type_id": self.type_id,
            "type_label": profile["label"],
            "description": profile["description"],
            "icon": profile["icon"],
            "name": self.name,
            "faction": self.faction,
            "lon": self.lon,
            "lat": self.lat,
            "altitude": self.altitude,
            "current_province": self.current_province,
            "integrity": self.integrity,
            "max_integrity": self.max_integrity,
            "integrity_fraction": self.integrity / self.max_integrity,
            "construction_progress": self.construction_progress,
            "construction_hours": float(profile["construction_hours"]),
            "construction_supply_cost": float(profile["construction_supply_cost"]),
            "builder_unit_id": self.builder_unit_id,
            "status": self.status,
            "radius": float(profile["radius_km"]),
            "armor": float(profile["armor"]),
            "softness": float(profile["softness"]),
            "fortification_cover_bonus": float(profile["fortification_cover_bonus"]),
            "effect_radius_km": float(profile["effect_radius_km"]),
            "radar_range_km": float(profile["radar_range_km"]),
            "radar_recon_power": float(profile["radar_recon_power"]),
            "radar_requires_line_of_sight": bool(profile["radar_requires_line_of_sight"]),
        }
