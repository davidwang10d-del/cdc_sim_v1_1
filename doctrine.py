"""Universal command doctrine shared by every simulation scenario.

Tactical orders describe what a unit is tasked to do. Combat stances describe
how it executes that task. These concepts and their interaction do not change
between battles, so DLC packages reference them instead of redefining them.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


CORE_RULE_SECTIONS = frozenset({"orders", "stances"})


_CORE_DOCTRINE: dict[str, Any] = {
    "orders": {
        "modes": {
            "hold": {
                "id": "HOLD",
                "label": "Hold",
                "summary": "STOP • KEEP STANCE",
                "description": (
                    "Cancel movement and remain in place. The selected combat stance "
                    "continues to govern fire, concealment, and protection."
                ),
                "color": "#8b949e",
            },
            "relocate": {
                "id": "RELOCATE",
                "label": "Relocate",
                "summary": "MOVE • AVOID CONTACT",
                "description": (
                    "Move directly to one destination without initiating ranged combat; "
                    "close-contact self-defense remains active."
                ),
                "color": "#58a6ff",
            },
            "route": {
                "id": "ROUTE",
                "label": "Planned Route",
                "summary": "WAYPOINTS • AVOID CONTACT",
                "description": (
                    "Follow multiple waypoints without initiating ranged combat; "
                    "close-contact self-defense remains active."
                ),
                "color": "#d2a8ff",
            },
            "assault": {
                "id": "ASSAULT",
                "label": "Assault",
                "summary": "MOVE • SEEK CONTACT",
                "description": (
                    "Advance toward an objective, halt at detected weapon contact, engage "
                    "according to the selected stance, and resume when contact clears."
                ),
                "color": "#d97706",
            },
            "defend": {
                "id": "DEFEND",
                "label": "Defend Here",
                "summary": "STOP • PREPARE POSITION",
                "description": (
                    "Stop at the current location, recover, and build fieldworks at the "
                    "standard rate while retaining the selected stance."
                ),
                "color": "#7ee787",
            },
            "fortify": {
                "id": "FORTIFY",
                "label": "Fortify",
                "summary": "STOP • BUILD RAPIDLY",
                "description": (
                    "Stop and accelerate fieldwork construction by consuming supply and "
                    "adding fatigue while retaining the selected stance."
                ),
                "color": "#3fb950",
            },
        },
        "default_role": "hold",
        "arrival_role": "hold",
        "defending_status": "DEFENDING",
        "fortifying_status": "FORTIFYING",
        "fortify_completion_role": "defend",
        "assault_speed_multiplier": 0.75,
        "assault_halts_at_contact": True,
        "close_contact_self_defense": True,
        "relocate_allows_stance_fire": False,
        "route_allows_stance_fire": False,
    },
    "stances": {
        "AGGRESSIVE": {
            "label": "Aggressive",
            "description": "Prioritize engagement and combat power with minimal concealment.",
            "color": "#f59e0b",
            "combat_multiplier": 1.0,
            "movement_multiplier": 1.0,
            "visibility_multiplier": 1.0,
            "recon_multiplier": 1.0,
            "recovery_multiplier": 1.0,
            "political_presence_multiplier": 1.0,
            "base_cover": 0.0,
            "allows_ranged_fire": True,
            "auto_evasion": False,
            "conceals_border_crossing": False,
        },
        "DEFENSIVE": {
            "label": "Defensive",
            "description": "Prioritize protection and lower exposure while retaining normal firepower.",
            "color": "#7ee787",
            "combat_multiplier": 1.0,
            "movement_multiplier": 1.0,
            "visibility_multiplier": 0.7,
            "recon_multiplier": 1.0,
            "recovery_multiplier": 1.0,
            "political_presence_multiplier": 1.0,
            "base_cover": 0.15,
            "allows_ranged_fire": True,
            "auto_evasion": False,
            "conceals_border_crossing": False,
        },
        "STEALTH": {
            "label": "Stealth",
            "description": "Minimize detection and evade contact at the cost of speed and combat power.",
            "color": "#a78bfa",
            "combat_multiplier": 0.7,
            "movement_multiplier": 0.5,
            "visibility_multiplier": 0.3,
            "recon_multiplier": 0.7,
            "recovery_multiplier": 1.0,
            "political_presence_multiplier": 0.1,
            "base_cover": 0.25,
            "allows_ranged_fire": True,
            "auto_evasion": True,
            "conceals_border_crossing": True,
        },
        "RECON": {
            "label": "Recon",
            "description": "Prioritize movement and detection while accepting reduced combat power.",
            "color": "#58a6ff",
            "combat_multiplier": 0.8,
            "movement_multiplier": 1.15,
            "visibility_multiplier": 1.2,
            "recon_multiplier": 1.8,
            "recovery_multiplier": 1.0,
            "political_presence_multiplier": 1.0,
            "base_cover": 0.0,
            "allows_ranged_fire": True,
            "auto_evasion": False,
            "conceals_border_crossing": False,
        },
        "RESERVE": {
            "label": "Reserve",
            "description": "Conserve strength and recover faster with slower movement and reduced combat power.",
            "color": "#a5d6ff",
            "combat_multiplier": 0.6,
            "movement_multiplier": 0.75,
            "visibility_multiplier": 0.8,
            "recon_multiplier": 1.0,
            "recovery_multiplier": 1.5,
            "political_presence_multiplier": 1.0,
            "base_cover": 0.0,
            "allows_ranged_fire": True,
            "auto_evasion": False,
            "conceals_border_crossing": False,
        },
        "HOLD_FIRE": {
            "label": "Hold Fire",
            "description": "Withhold ranged fire while preserving close-contact self-defense.",
            "color": "#ff7b72",
            "combat_multiplier": 0.4,
            "movement_multiplier": 1.0,
            "visibility_multiplier": 0.65,
            "recon_multiplier": 1.0,
            "recovery_multiplier": 1.0,
            "political_presence_multiplier": 1.0,
            "base_cover": 0.0,
            "allows_ranged_fire": False,
            "auto_evasion": False,
            "conceals_border_crossing": False,
        },
    },
}


def get_core_doctrine() -> dict[str, Any]:
    """Return an isolated copy so a running scenario cannot mutate the core."""

    return deepcopy(_CORE_DOCTRINE)
