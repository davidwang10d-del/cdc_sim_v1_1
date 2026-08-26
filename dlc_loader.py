"""Safe loading and validation for scenario DLC packages.

The simulation core consumes data from this module instead of reaching into a
scenario directory ad hoc.  Keeping path resolution and schema checks here
prevents a malformed package from partially replacing a running committee.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from typing import Any

from doctrine import CORE_RULE_SECTIONS, get_core_doctrine


PROJECT_ROOT = Path(__file__).resolve().parent
DLC_ROOT = PROJECT_ROOT / "dlc"

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$")
_SUPPORTED_DIRECTIVE_EFFECTS = frozenset({"none", "morale", "supply", "fatigue", "combat_modifier", "speed_modifier"})
_SUPPORTED_MODIFIER_TYPES = frozenset({"combat", "speed", "morale"})
_MAP_PATH_FIELDS = {
    "dem_file": "file",
    "dem_dir": "dir",
    "roads_file": "file",
    "rivers_file": "file",
    "provinces_file": "file",
}


class DLCValidationError(ValueError):
    """A package is unsafe or incompatible with the current core."""

    def __init__(self, errors: list[str] | str):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True)
class DLCPackage:
    dlc_id: str
    directory: Path
    scenario: dict[str, Any]
    map_config: dict[str, Any]
    units: dict[str, dict[str, Any]]
    weapons: dict[str, dict[str, Any]]
    battalions: dict[str, dict[str, Any]]
    rules: dict[str, Any]
    source_rules: dict[str, Any]


def validate_identifier(value: Any, label: str = "ID") -> str:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value) or value in {".", ".."}:
        raise DLCValidationError(
            f"{label} must be 1-64 characters using letters, numbers, underscore, dash, or dot"
        )
    return value


def resolve_dlc_path(dlc_id: Any) -> Path:
    safe_id = validate_identifier(dlc_id, "DLC ID")
    root = DLC_ROOT.resolve()
    candidate = (root / safe_id).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise DLCValidationError("DLC path escapes the dlc directory") from exc
    if not candidate.is_dir():
        raise DLCValidationError(f"DLC [{safe_id}] does not exist")
    return candidate


def _safe_child(base: Path, value: Any, label: str, expected: str | None = None) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise DLCValidationError(f"{label} must be a non-empty relative path")
    raw = Path(value)
    if raw.is_absolute():
        raise DLCValidationError(f"{label} must stay inside its DLC directory")

    root = base.resolve()
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise DLCValidationError(f"{label} escapes its DLC directory") from exc

    if expected == "file" and not candidate.is_file():
        raise DLCValidationError(f"{label} was configured but the file is missing: {value}")
    if expected == "dir" and not candidate.is_dir():
        raise DLCValidationError(f"{label} was configured but the directory is missing: {value}")
    return candidate


def _json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise DLCValidationError(f"Missing required {label}: {path.name}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise DLCValidationError(f"Cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise DLCValidationError(f"{label} must contain a JSON object")
    return value


def _finite_number(value: Any, label: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool):
        raise DLCValidationError(f"{label} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DLCValidationError(f"{label} must be a number") from exc
    if not math.isfinite(number):
        raise DLCValidationError(f"{label} must be finite")
    if minimum is not None and number < minimum:
        raise DLCValidationError(f"{label} must be at least {minimum:g}")
    if maximum is not None and number > maximum:
        raise DLCValidationError(f"{label} must be at most {maximum:g}")
    return number


def _rule_value(rules: dict[str, Any], path: str) -> Any:
    value: Any = rules
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise DLCValidationError(f"rules.json requires {path}")
        value = value[part]
    return value


def _validate_rules(rules: dict[str, Any], errors: list[str]) -> None:
    """Validate every rule consumed by the simulation core.

    Core doctrine is injected before this validation. Every remaining tuning
    value must be supplied by the DLC; incomplete packages are rejected.
    """
    if rules.get("schema_version") != 1:
        errors.append("rules.json schema_version must be 1")

    required_objects = (
        "clock", "resources", "state_limits", "unit_defaults", "footprint",
        "composition", "unit_types", "stances", "readiness", "recovery",
        "movement", "orders", "defense", "detection", "tactical_support", "political_influence",
        "combat", "missions", "geography", "directives", "modifiers",
    )
    for path in required_objects:
        try:
            if not isinstance(_rule_value(rules, path), dict):
                errors.append(f"rules.json {path} must be an object")
        except DLCValidationError as exc:
            errors.extend(exc.errors)

    numeric_rules = {
        "clock.default_time_multiplier": (0.0, None),
        "clock.game_seconds_per_real_second": (0.0, None),
        "clock.heartbeat_interval_seconds": (0.001, None),
        "clock.speed_multiplier_min": (0.001, None),
        "clock.speed_multiplier_max": (0.001, None),
        "resources.minimum": (None, None),
        "resources.maximum": (None, None),
        "unit_defaults.personnel": (0.0, None),
        "unit_defaults.equipment_level": (0.0, None),
        "unit_defaults.morale": (0.0, None),
        "unit_defaults.supply": (0.0, None),
        "unit_defaults.fatigue": (0.0, None),
        "unit_defaults.suppression": (0.0, None),
        "unit_defaults.entrenchment": (0.0, None),
        "unit_defaults.altitude_m": (None, None),
        "unit_defaults.modifier_value": (0.0, None),
        "unit_defaults.modifier_duration_hours": (0.0, None),
        "footprint.minimum_radius_km": (0.0, None),
        "footprint.personnel_sqrt_scale": (0.0, None),
        "footprint.zero_personnel_radius_km": (0.0, None),
        "composition.minimum_organization": (0.0, None),
        "readiness.combat.supply_floor": (0.0, 1.0),
        "readiness.combat.fatigue_penalty": (0.0, 1.0),
        "readiness.combat.suppression_penalty": (0.0, 1.0),
        "readiness.combat.minimum": (0.0, 1.0),
        "readiness.movement.supply_floor": (0.0, 1.0),
        "readiness.movement.fatigue_penalty": (0.0, 1.0),
        "readiness.movement.suppression_penalty": (0.0, 1.0),
        "readiness.movement.minimum": (0.0, 1.0),
        "readiness.morale_floor": (0.0, None),
        "readiness.morale_scale": (0.001, None),
        "recovery.suppression_decay_per_hour": (0.0, None),
        "recovery.idle_morale_per_hour": (0.0, None),
        "recovery.idle_fatigue_per_hour": (0.0, None),
        "recovery.idle_supply_per_hour": (0.0, None),
        "recovery.entrenchment_per_hour": (0.0, None),
        "recovery.maximum_entrenchment": (0.0, None),
        "movement.arrival_distance_km": (0.0, None),
        "movement.base_fatigue_per_hour": (0.0, None),
        "movement.terrain_fatigue_per_hour": (0.0, None),
        "movement.base_supply_per_hour": (0.0, None),
        "orders.assault_speed_multiplier": (0.001, None),
        "defense.defend_entrenchment_multiplier": (0.0, None),
        "defense.fortify_entrenchment_per_hour": (0.0, None),
        "defense.fortify_supply_per_hour": (0.0, None),
        "defense.fortify_fatigue_per_hour": (0.0, None),
        "defense.minimum_supply_to_start": (0.0, None),
        "defense.stop_supply_threshold": (0.0, None),
        "defense.suppression_build_penalty": (0.0, 1.0),
        "detection.base_visibility_minimum": (0.0, None),
        "detection.minimum_recon_power": (0.0, None),
        "detection.personnel_reference": (0.001, None),
        "detection.terrain_hide_minimum": (0.0, 1.0),
        "detection.terrain_hide_strength": (0.0, None),
        "detection.final_visibility_minimum": (0.0, None),
        "detection.minimum_distance_km": (0.001, None),
        "detection.distance_exponent": (0.0, None),
        "detection.probability_scale": (0.0, None),
        "detection.contact_ttl_hours": (0.0, None),
        "detection.default_status_visibility_multiplier": (0.0, None),
        "tactical_support.range_km": (0.0, None),
        "tactical_support.minimum_equipment_level": (0.0, None),
        "tactical_support.equipment_multiplier": (0.0, None),
        "political_influence.minimum": (None, None),
        "political_influence.maximum": (None, None),
        "political_influence.personnel_reference": (0.001, None),
        "political_influence.shift_per_reference_unit_hour": (0.0, None),
        "political_influence.default_faction_weight": (None, None),
        "combat.cover.entrenchment_effect": (0.0, None),
        "combat.cover.entrenchment_cap": (0.0, None),
        "combat.cover.moving_modifier": (None, None),
        "combat.cover.terrain_direct_effect": (0.0, None),
        "combat.cover.terrain_indirect_effect": (0.0, None),
        "combat.cover.terrain_cap": (0.0, None),
        "combat.cover.cover_minimum": (None, None),
        "combat.cover.cover_maximum": (None, None),
        "combat.cover.damage_multiplier_minimum": (0.0, None),
        "combat.cover.damage_multiplier_maximum": (0.0, None),
        "combat.direct.minimum_engagement_distance_km": (0.0, None),
        "combat.direct.river_crossing_multiplier": (0.0, None),
        "combat.direct.river_engineer_multiplier": (0.0, None),
        "combat.direct.frontage_minimum_personnel": (0.0, None),
        "combat.direct.frontage_maximum_personnel": (0.0, None),
        "combat.direct.frontage_terrain_reduction": (0.0, None),
        "combat.direct.personnel_reference": (0.001, None),
        "combat.direct.elevation_advantage_threshold_m": (0.0, None),
        "combat.direct.elevation_advantage_multiplier": (0.0, None),
        "combat.direct.failed_penetration_multiplier": (0.0, None),
        "combat.direct.attack_scale": (0.0, None),
        "combat.direct.indirect_without_los_multiplier": (0.0, None),
        "combat.direct.defended_hit_coefficient": (0.0, None),
        "combat.direct.overmatch_hit_coefficient": (0.0, None),
        "combat.direct.casualty_time_multiplier": (0.0, None),
        "combat.direct.organization_casualty_multiplier": (0.0, None),
        "combat.direct.organization_pressure_multiplier": (0.0, None),
        "combat.direct.suppression_cap": (0.0, None),
        "combat.direct.suppression_attack_multiplier": (0.0, None),
        "combat.direct.unopposed_log_probability_per_hour": (0.0, None),
        "combat.evasion.trigger_range_fraction": (0.0, None),
        "combat.evasion.retreat_min_km": (0.0, None),
        "combat.evasion.retreat_max_km": (0.0, None),
        "combat.evasion.log_probability_per_hour": (0.0, None),
        "combat.routing.morale_threshold": (0.0, None),
        "combat.routing.speed_multiplier": (0.0, None),
        "combat.routing.rally_morale": (0.0, None),
        "combat.routing.retreat_min_km": (0.0, None),
        "combat.routing.retreat_max_km": (0.0, None),
        "missions.bombard.duration_hours": (0.0, None),
        "missions.bombard.fatigue_per_hour": (0.0, None),
        "missions.bombard.supply_per_hour": (0.0, None),
        "missions.bombard.minimum_supply_to_start": (0.0, None),
        "missions.bombard.stop_supply_threshold": (0.0, None),
        "missions.bombard.blast_radius_km": (0.001, None),
        "missions.bombard.minimum_aim_factor": (0.0, 1.0),
        "missions.bombard.terrain_efficiency_multiplier": (0.0, None),
        "missions.bombard.casualty_coefficient": (0.0, None),
        "missions.bombard.organization_base_per_hour": (0.0, None),
        "missions.bombard.organization_casualty_multiplier": (0.0, None),
        "missions.bombard.suppression_per_hour": (0.0, None),
        "missions.airstrike.blast_radius_km": (0.001, None),
        "missions.airstrike.minimum_aim_factor": (0.0, 1.0),
        "missions.airstrike.casualty_coefficient": (0.0, None),
        "missions.airstrike.organization_base": (0.0, None),
        "missions.airstrike.organization_casualty_multiplier": (0.0, None),
        "missions.airstrike.suppression": (0.0, None),
        "missions.airstrike.fatigue_cost": (0.0, None),
        "missions.airstrike.supply_cost": (0.0, None),
        "missions.air_defense.range_km": (0.0, None),
        "missions.air_defense.minimum_equipment_level": (0.0, None),
        "missions.air_defense.kill_probability_per_hour": (0.0, None),
        "geography.line_of_sight.automatic_clear_distance_km": (0.0, None),
        "geography.line_of_sight.observer_height_m": (0.0, None),
        "geography.line_of_sight.effective_earth_radius_km": (0.001, None),
        "directives.default_duration_hours": (0.001, None),
        "modifiers.value_minimum": (0.0, None),
        "modifiers.value_maximum": (0.0, None),
        "modifiers.default_value": (0.0, None),
        "modifiers.duration_minimum_hours": (0.001, None),
        "modifiers.duration_maximum_hours": (0.001, None),
        "modifiers.default_duration_hours": (0.001, None),
    }
    for path, (minimum, maximum) in numeric_rules.items():
        try:
            _finite_number(_rule_value(rules, path), path, minimum=minimum, maximum=maximum)
        except DLCValidationError as exc:
            errors.extend(exc.errors)

    integer_rules = {
        "state_limits.structured_logs": 1,
        "state_limits.committee_records": 1,
        "state_limits.public_sitrep_records": 1,
        "state_limits.staff_sitrep_records": 1,
        "state_limits.state_feed_logs": 1,
        "combat.direct.river_probe_steps": 2,
        "geography.void_search_radius_pixels": 1,
        "movement.max_route_waypoints": 1,
    }
    for path, minimum in integer_rules.items():
        try:
            number = _finite_number(_rule_value(rules, path), path, minimum=minimum)
            if not number.is_integer():
                errors.append(f"{path} must be an integer")
        except DLCValidationError as exc:
            errors.extend(exc.errors)

    string_rules = (
        "unit_defaults.unit_type", "unit_defaults.stance", "unit_defaults.status",
        "unit_defaults.modifier_name", "tactical_support.capability",
        "orders.default_role", "orders.arrival_role", "orders.defending_status",
        "orders.fortifying_status", "orders.fortify_completion_role",
        "combat.direct.river_engineer_capability", "combat.routing.stance",
        "missions.bombard.capability", "missions.airstrike.capability",
        "missions.air_defense.capability", "directives.default_title",
        "directives.default_faction", "modifiers.default_name",
        "geography.pathing.heavy_river_crossing_capability",
        "geography.pathing.river_engineer_capability",
    )
    for path in string_rules:
        try:
            if not isinstance(_rule_value(rules, path), str) or not _rule_value(rules, path).strip():
                errors.append(f"{path} must be a non-empty string")
        except DLCValidationError as exc:
            errors.extend(exc.errors)

    for path in (
        "political_influence.enabled", "combat.routing.can_deal_damage",
        "orders.assault_halts_at_contact", "orders.close_contact_self_defense",
        "orders.relocate_allows_stance_fire", "orders.route_allows_stance_fire",
    ):
        try:
            if not isinstance(_rule_value(rules, path), bool):
                errors.append(f"{path} must be true or false")
        except DLCValidationError as exc:
            errors.extend(exc.errors)

    order_rules = rules.get("orders", {})
    order_modes = order_rules.get("modes", {}) if isinstance(order_rules, dict) else {}
    required_order_roles = ("hold", "relocate", "route", "assault", "defend", "fortify")
    if not isinstance(order_modes, dict):
        errors.append("orders.modes must be an object")
        order_modes = {}
    missing_roles = [role for role in required_order_roles if role not in order_modes]
    if missing_roles:
        errors.append(f"orders.modes is missing required roles: {', '.join(missing_roles)}")
    order_ids = []
    for role, profile in order_modes.items():
        if not isinstance(profile, dict):
            errors.append(f"Order mode [{role}] must be an object")
            continue
        try:
            order_ids.append(validate_identifier(profile.get("id"), f"Order mode [{role}] id"))
        except DLCValidationError as exc:
            errors.extend(exc.errors)
        for field in ("label", "summary", "description", "color"):
            if not isinstance(profile.get(field), str) or not profile.get(field).strip():
                errors.append(f"Order mode [{role}] requires {field}")
        if isinstance(profile.get("color"), str) and not re.fullmatch(r"#[0-9A-Fa-f]{6}", profile["color"]):
            errors.append(f"Order mode [{role}] color must be a six-digit hex color")
    if len({order_id.casefold() for order_id in order_ids}) != len(order_ids):
        errors.append("Order mode IDs must be unique ignoring case")
    for field in ("default_role", "arrival_role"):
        if isinstance(order_rules, dict) and order_rules.get(field) not in order_modes:
            errors.append(f"orders.{field} must reference orders.modes")

    if isinstance(order_rules, dict) and order_rules.get("fortify_completion_role") not in order_modes:
        errors.append("orders.fortify_completion_role must reference orders.modes")

    unit_types = rules.get("unit_types", {})
    if not isinstance(unit_types, dict) or not unit_types:
        errors.append("rules.json unit_types must define at least one unit type")
        unit_types = {}
    if len({type_id.casefold() for type_id in unit_types if isinstance(type_id, str)}) != len(unit_types):
        errors.append("rules.json unit type IDs must be unique ignoring case")
    fixed_stat_fields = (
        "speed_kmh", "soft_attack", "hard_attack", "defense", "breakthrough",
        "organization", "armor_piercing", "armor", "softness", "terrain_modifier",
    )
    for type_id, profile in unit_types.items():
        try:
            validate_identifier(type_id, "Unit type ID")
        except DLCValidationError as exc:
            errors.extend(exc.errors)
        if not isinstance(profile, dict):
            errors.append(f"Unit type [{type_id}] must be an object")
            continue
        if profile.get("stats_source") not in {"composition", "fixed"}:
            errors.append(f"Unit type [{type_id}] stats_source must be composition or fixed")
        if profile.get("radius_mode") not in {"footprint", "fixed"}:
            errors.append(f"Unit type [{type_id}] radius_mode must be footprint or fixed")
        if profile.get("fire_range_mode") not in {"weapon", "fixed"}:
            errors.append(f"Unit type [{type_id}] fire_range_mode must be weapon or fixed")
        if profile.get("terrain_efficiency_mode") not in {"terrain", "fixed"}:
            errors.append(f"Unit type [{type_id}] terrain_efficiency_mode must be terrain or fixed")
        for field in ("label", "icon"):
            if not isinstance(profile.get(field), str) or not profile.get(field):
                errors.append(f"Unit type [{type_id}] requires {field}")
        capabilities = profile.get("capabilities")
        if not isinstance(capabilities, list) or not all(isinstance(item, str) and item.strip() for item in capabilities):
            errors.append(f"Unit type [{type_id}] capabilities must be a list of non-empty strings")
        for field in (
            "ignores_movement_terrain", "can_direct_combat", "can_be_airstrike_target", "uncapped_frontage",
            "applies_stance_combat", "applies_morale", "applies_combat_modifiers",
            "fixed_stats_apply_equipment",
        ):
            if not isinstance(profile.get(field), bool):
                errors.append(f"Unit type [{type_id}] {field} must be true or false")
        for field in (
            "terrain_efficiency_multiplier", "outgoing_direct_fire_multiplier", "incoming_direct_fire_multiplier",
        ):
            try:
                _finite_number(profile.get(field), f"Unit type [{type_id}] {field}", minimum=0.0)
            except DLCValidationError as exc:
                errors.extend(exc.errors)
        detection = profile.get("detection")
        if not isinstance(detection, dict):
            errors.append(f"Unit type [{type_id}] detection must be an object")
        else:
            for field in ("base_recon", "max_range_km"):
                try:
                    _finite_number(detection.get(field), f"Unit type [{type_id}] detection.{field}", minimum=0.0)
                except DLCValidationError as exc:
                    errors.extend(exc.errors)
            if not isinstance(detection.get("requires_line_of_sight"), bool):
                errors.append(f"Unit type [{type_id}] detection.requires_line_of_sight must be true or false")
        if profile.get("stats_source") == "fixed":
            stats = profile.get("fixed_stats")
            if not isinstance(stats, dict):
                errors.append(f"Unit type [{type_id}] fixed_stats must be an object")
            else:
                for field in fixed_stat_fields:
                    try:
                        value = _finite_number(stats.get(field), f"Unit type [{type_id}] fixed_stats.{field}", minimum=0.0)
                        if field == "softness" and value > 1.0:
                            errors.append(f"Unit type [{type_id}] fixed_stats.softness must be at most 1")
                    except DLCValidationError as exc:
                        errors.extend(exc.errors)
        for mode, field in (("fixed", "radius_km"),):
            if profile.get("radius_mode") == mode:
                try:
                    _finite_number(profile.get(field), f"Unit type [{type_id}] {field}", minimum=0.0)
                except DLCValidationError as exc:
                    errors.extend(exc.errors)
        if profile.get("fire_range_mode") == "fixed":
            try:
                _finite_number(profile.get("fire_range_km"), f"Unit type [{type_id}] fire_range_km", minimum=0.0)
            except DLCValidationError as exc:
                errors.extend(exc.errors)

    stances = rules.get("stances", {})
    if not isinstance(stances, dict) or not stances:
        errors.append("Core doctrine must define at least one stance")
        stances = {}
    if len({stance_id.casefold() for stance_id in stances if isinstance(stance_id, str)}) != len(stances):
        errors.append("Core doctrine stance IDs must be unique ignoring case")
    for stance_id, profile in stances.items():
        try:
            validate_identifier(stance_id, "Stance ID")
        except DLCValidationError as exc:
            errors.extend(exc.errors)
        if not isinstance(profile, dict):
            errors.append(f"Stance [{stance_id}] must be an object")
            continue
        for field in ("label", "description", "color"):
            if not isinstance(profile.get(field), str) or not profile.get(field).strip():
                errors.append(f"Stance [{stance_id}] requires {field}")
        if isinstance(profile.get("color"), str) and not re.fullmatch(r"#[0-9A-Fa-f]{6}", profile["color"]):
            errors.append(f"Stance [{stance_id}] color must be a six-digit hex color")
        for field in (
            "combat_multiplier", "movement_multiplier", "visibility_multiplier", "recon_multiplier",
            "recovery_multiplier", "political_presence_multiplier", "base_cover",
        ):
            try:
                _finite_number(profile.get(field), f"Stance [{stance_id}] {field}", minimum=None if field == "base_cover" else 0.0)
            except DLCValidationError as exc:
                errors.extend(exc.errors)
        for field in ("allows_ranged_fire", "auto_evasion", "conceals_border_crossing"):
            if not isinstance(profile.get(field), bool):
                errors.append(f"Stance [{stance_id}] {field} must be true or false")

    defaults = rules.get("unit_defaults", {})
    if isinstance(defaults, dict):
        if not any(type_id.casefold() == str(defaults.get("unit_type", "")).casefold() for type_id in unit_types):
            errors.append("unit_defaults.unit_type must reference rules.json unit_types")
        if not any(stance_id.casefold() == str(defaults.get("stance", "")).casefold() for stance_id in stances):
            errors.append("unit_defaults.stance must reference a core doctrine stance")
    routing = rules.get("combat", {}).get("routing", {}) if isinstance(rules.get("combat"), dict) else {}
    if isinstance(routing, dict) and not any(stance_id.casefold() == str(routing.get("stance", "")).casefold() for stance_id in stances):
        errors.append("combat.routing.stance must reference a core doctrine stance")
    political = rules.get("political_influence", {})
    if isinstance(political, dict):
        for field in ("excluded_statuses", "excluded_province_names", "excluded_province_prefixes"):
            value = political.get(field)
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                errors.append(f"political_influence.{field} must be a list of strings")
        weights = political.get("faction_weights")
        if not isinstance(weights, dict):
            errors.append("political_influence.faction_weights must be an object")
        else:
            for faction, weight in weights.items():
                if not isinstance(faction, str) or not faction.strip():
                    errors.append("political influence faction names must be non-empty strings")
                try:
                    _finite_number(weight, f"Political influence weight [{faction}]")
                except DLCValidationError as exc:
                    errors.extend(exc.errors)

    detection_rules = rules.get("detection", {})
    if isinstance(detection_rules, dict):
        status_multipliers = detection_rules.get("status_visibility_multipliers")
        if not isinstance(status_multipliers, dict):
            errors.append("detection.status_visibility_multipliers must be an object")
        else:
            for status, multiplier in status_multipliers.items():
                if not isinstance(status, str) or not status.strip():
                    errors.append("Detection status names must be non-empty strings")
                try:
                    _finite_number(multiplier, f"Detection status multiplier [{status}]", minimum=0.0)
                except DLCValidationError as exc:
                    errors.extend(exc.errors)

    for path in ("directives.allowed_effects", "modifiers.allowed_types"):
        try:
            values = _rule_value(rules, path)
            if not isinstance(values, list) or not values or not all(isinstance(item, str) and item.strip() for item in values):
                errors.append(f"{path} must be a non-empty list of strings")
        except DLCValidationError as exc:
            errors.extend(exc.errors)
    directive_effects = rules.get("directives", {}).get("allowed_effects", []) if isinstance(rules.get("directives"), dict) else []
    if isinstance(directive_effects, list):
        unsupported = sorted(set(directive_effects) - _SUPPORTED_DIRECTIVE_EFFECTS)
        if unsupported:
            errors.append(f"Unsupported directive effects: {', '.join(unsupported)}")
    modifier_types = rules.get("modifiers", {}).get("allowed_types", []) if isinstance(rules.get("modifiers"), dict) else []
    if isinstance(modifier_types, list):
        unsupported = sorted(set(modifier_types) - _SUPPORTED_MODIFIER_TYPES)
        if unsupported:
            errors.append(f"Unsupported modifier types: {', '.join(unsupported)}")

    relation_checks = (
        ("clock.speed_multiplier_min", "clock.speed_multiplier_max"),
        ("resources.minimum", "resources.maximum"),
        ("political_influence.minimum", "political_influence.maximum"),
        ("combat.cover.cover_minimum", "combat.cover.cover_maximum"),
        ("combat.cover.damage_multiplier_minimum", "combat.cover.damage_multiplier_maximum"),
        ("combat.evasion.retreat_min_km", "combat.evasion.retreat_max_km"),
        ("combat.routing.retreat_min_km", "combat.routing.retreat_max_km"),
        ("modifiers.value_minimum", "modifiers.value_maximum"),
        ("modifiers.duration_minimum_hours", "modifiers.duration_maximum_hours"),
    )
    for lower_path, upper_path in relation_checks:
        try:
            if float(_rule_value(rules, lower_path)) > float(_rule_value(rules, upper_path)):
                errors.append(f"{lower_path} must not exceed {upper_path}")
        except (DLCValidationError, TypeError, ValueError):
            pass

    bounded_values = (
        ("clock.default_time_multiplier", "clock.speed_multiplier_min", "clock.speed_multiplier_max"),
        ("modifiers.default_value", "modifiers.value_minimum", "modifiers.value_maximum"),
        ("modifiers.default_duration_hours", "modifiers.duration_minimum_hours", "modifiers.duration_maximum_hours"),
        ("unit_defaults.morale", "resources.minimum", "resources.maximum"),
        ("unit_defaults.supply", "resources.minimum", "resources.maximum"),
        ("unit_defaults.fatigue", "resources.minimum", "resources.maximum"),
        ("unit_defaults.suppression", "resources.minimum", "resources.maximum"),
        ("combat.routing.morale_threshold", "resources.minimum", "resources.maximum"),
        ("combat.routing.rally_morale", "resources.minimum", "resources.maximum"),
        ("missions.bombard.minimum_supply_to_start", "resources.minimum", "resources.maximum"),
        ("missions.bombard.stop_supply_threshold", "resources.minimum", "resources.maximum"),
        ("defense.minimum_supply_to_start", "resources.minimum", "resources.maximum"),
        ("defense.stop_supply_threshold", "resources.minimum", "resources.maximum"),
    )
    for value_path, lower_path, upper_path in bounded_values:
        try:
            value = float(_rule_value(rules, value_path))
            lower = float(_rule_value(rules, lower_path))
            upper = float(_rule_value(rules, upper_path))
            if value < lower or value > upper:
                errors.append(f"{value_path} must be between {lower_path} and {upper_path}")
        except (DLCValidationError, TypeError, ValueError):
            pass
    try:
        if float(_rule_value(rules, "missions.bombard.stop_supply_threshold")) > float(_rule_value(rules, "missions.bombard.minimum_supply_to_start")):
            errors.append("missions.bombard.stop_supply_threshold must not exceed minimum_supply_to_start")
    except (DLCValidationError, TypeError, ValueError):
        pass
    try:
        if float(_rule_value(rules, "defense.stop_supply_threshold")) > float(_rule_value(rules, "defense.minimum_supply_to_start")):
            errors.append("defense.stop_supply_threshold must not exceed defense.minimum_supply_to_start")
    except (DLCValidationError, TypeError, ValueError):
        pass

    # Do not flood users with the same missing-path message repeated by dependent checks.
    errors[:] = list(dict.fromkeys(errors))


def _validate_map_config(directory: Path, scenario: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    config = scenario.get("map_config")
    if not isinstance(config, dict):
        errors.append("scenario.json: map_config must be an object")
        return {}
    config = deepcopy(config)

    bounds = config.get("bounds")
    if not isinstance(bounds, dict):
        errors.append("scenario.json: map_config.bounds must be an object")
        return config

    parsed_bounds: dict[str, float] = {}
    for key, minimum, maximum in (
        ("min_lon", -180.0, 180.0),
        ("max_lon", -180.0, 180.0),
        ("min_lat", -90.0, 90.0),
        ("max_lat", -90.0, 90.0),
    ):
        try:
            parsed_bounds[key] = _finite_number(bounds.get(key), f"map_config.bounds.{key}", minimum=minimum, maximum=maximum)
        except DLCValidationError as exc:
            errors.extend(exc.errors)

    if len(parsed_bounds) == 4:
        if parsed_bounds["min_lon"] >= parsed_bounds["max_lon"]:
            errors.append("map_config bounds require min_lon < max_lon")
        if parsed_bounds["min_lat"] >= parsed_bounds["max_lat"]:
            errors.append("map_config bounds require min_lat < max_lat")
        config["bounds"] = parsed_bounds

    resolution = config.get("grid_resolution")
    if not isinstance(resolution, list) or len(resolution) != 2:
        errors.append("map_config.grid_resolution must be [width, height]")
    else:
        parsed_resolution: list[int] = []
        for index, value in enumerate(resolution):
            try:
                number = _finite_number(value, f"grid_resolution[{index}]", minimum=16, maximum=4000)
                if not number.is_integer():
                    raise DLCValidationError(f"grid_resolution[{index}] must be an integer")
                parsed_resolution.append(int(number))
            except DLCValidationError as exc:
                errors.extend(exc.errors)
        if len(parsed_resolution) == 2:
            config["grid_resolution"] = parsed_resolution

    for key, expected in _MAP_PATH_FIELDS.items():
        raw_path = config.get(key)
        if raw_path in (None, ""):
            config[key] = ""
            continue
        try:
            config[key] = str(_safe_child(directory, raw_path, f"map_config.{key}", expected))
        except DLCValidationError as exc:
            errors.extend(exc.errors)

    if len(parsed_bounds) == 4:
        center = scenario.get("map_center")
        if center is None:
            scenario["map_center"] = [
                (parsed_bounds["min_lat"] + parsed_bounds["max_lat"]) / 2.0,
                (parsed_bounds["min_lon"] + parsed_bounds["max_lon"]) / 2.0,
            ]
        elif not isinstance(center, list) or len(center) != 2:
            errors.append("scenario.json: map_center must be [latitude, longitude]")
        else:
            try:
                scenario["map_center"] = [
                    _finite_number(center[0], "map_center latitude", minimum=-90, maximum=90),
                    _finite_number(center[1], "map_center longitude", minimum=-180, maximum=180),
                ]
            except DLCValidationError as exc:
                errors.extend(exc.errors)

        if "map_zoom" not in scenario:
            span = max(
                parsed_bounds["max_lon"] - parsed_bounds["min_lon"],
                parsed_bounds["max_lat"] - parsed_bounds["min_lat"],
            )
            scenario["map_zoom"] = max(1, min(12, int(math.log2(360.0 / max(span, 1e-6))) + 1))

    try:
        scenario["map_zoom"] = int(_finite_number(scenario.get("map_zoom"), "map_zoom", minimum=0, maximum=20))
    except DLCValidationError as exc:
        errors.extend(exc.errors)

    analysis_resolution = config.get("dem_analysis_resolution")
    if not isinstance(analysis_resolution, list) or len(analysis_resolution) != 2:
        errors.append("map_config.dem_analysis_resolution must be [width, height]")
    else:
        parsed: list[int] = []
        for index, value in enumerate(analysis_resolution):
            try:
                number = _finite_number(value, f"dem_analysis_resolution[{index}]", minimum=16, maximum=8000)
                if not number.is_integer():
                    raise DLCValidationError(f"dem_analysis_resolution[{index}] must be an integer")
                parsed.append(int(number))
            except DLCValidationError as exc:
                errors.extend(exc.errors)
        if len(parsed) == 2:
            config["dem_analysis_resolution"] = parsed

    for field, minimum in (
        ("fallback_elevation_m", None),
        ("terrain_elevation_scale_m", 1.0),
        ("terrain_cost_multiplier", 0.0),
        ("terrain_cost_exponent", 0.0),
    ):
        try:
            config[field] = _finite_number(config.get(field), f"map_config.{field}", minimum=minimum)
        except DLCValidationError as exc:
            errors.extend(exc.errors)

    pathing = config.get("pathing", {})
    if not isinstance(pathing, dict):
        errors.append("map_config.pathing must be an object")
    else:
        parsed_pathing = {}
        for field in ("road_cost", "river_penalty_default", "river_penalty_heavy", "river_penalty_engineer"):
            try:
                parsed_pathing[field] = _finite_number(pathing.get(field), f"map_config.pathing.{field}", minimum=0.0)
            except DLCValidationError as exc:
                errors.extend(exc.errors)
        config["pathing"] = {**pathing, **parsed_pathing}

    return config


def _validate_registries(
    weapons: dict[str, Any], battalions: dict[str, Any], errors: list[str]
) -> None:
    if not weapons:
        errors.append("weapons.json must define at least one weapon")
    for weapon_id, weapon in weapons.items():
        try:
            validate_identifier(weapon_id, "Weapon ID")
        except DLCValidationError as exc:
            errors.extend(exc.errors)
        if not isinstance(weapon, dict):
            errors.append(f"Weapon [{weapon_id}] must be an object")
            continue
        if not str(weapon.get("name", "")).strip():
            errors.append(f"Weapon [{weapon_id}] requires a name")
        try:
            _finite_number(weapon.get("range"), f"Weapon [{weapon_id}] range", minimum=0)
        except DLCValidationError as exc:
            errors.extend(exc.errors)
        if not isinstance(weapon.get("indirect_fire"), bool):
            errors.append(f"Weapon [{weapon_id}] indirect_fire must be true or false")

    if not battalions:
        errors.append("battalions.json must define at least one battalion type")
    numeric_fields = (
        "speed", "soft", "hard", "ap", "armor", "defense", "breakthrough",
        "org", "terrain", "recon_power", "movement_supply_cost",
    )
    for battalion_id, battalion in battalions.items():
        try:
            validate_identifier(battalion_id, "Battalion ID")
        except DLCValidationError as exc:
            errors.extend(exc.errors)
        if not isinstance(battalion, dict):
            errors.append(f"Battalion [{battalion_id}] must be an object")
            continue
        if not str(battalion.get("name", "")).strip():
            errors.append(f"Battalion [{battalion_id}] requires a name")
        for field in numeric_fields:
            try:
                minimum = None if field == "recon_power" else 0
                _finite_number(battalion.get(field), f"Battalion [{battalion_id}] {field}", minimum=minimum)
            except DLCValidationError as exc:
                errors.extend(exc.errors)
        try:
            battalion_size = _finite_number(battalion.get("size"), f"Battalion [{battalion_id}] size", minimum=1)
            if not battalion_size.is_integer():
                errors.append(f"Battalion [{battalion_id}] size must be an integer")
        except DLCValidationError as exc:
            errors.extend(exc.errors)
        try:
            _finite_number(battalion.get("softness"), f"Battalion [{battalion_id}] softness", minimum=0, maximum=1)
        except DLCValidationError as exc:
            errors.extend(exc.errors)
        capabilities = battalion.get("capabilities", [])
        if not isinstance(capabilities, list) or not all(isinstance(item, str) and item.strip() for item in capabilities):
            errors.append(f"Battalion [{battalion_id}] capabilities must be a list of non-empty strings")


def _validate_units(
    units: dict[str, Any],
    weapons: dict[str, Any],
    battalions: dict[str, Any],
    rules: dict[str, Any],
    errors: list[str],
) -> None:
    defaults = rules.get("unit_defaults", {})
    unit_types = rules.get("unit_types", {})
    stances = rules.get("stances", {})
    for unit_id, unit in units.items():
        try:
            validate_identifier(unit_id, "Unit ID")
        except DLCValidationError as exc:
            errors.extend(exc.errors)
        if not isinstance(unit, dict):
            errors.append(f"Unit [{unit_id}] must be an object")
            continue
        for field in ("name", "faction"):
            if not str(unit.get(field, "")).strip():
                errors.append(f"Unit [{unit_id}] requires {field}")
        for field, limits in {
            "personnel": (0, None),
            "equipment_level": (0, None),
            "lon": (-180, 180),
            "lat": (-90, 90),
            "morale": (0, None),
        }.items():
            if field not in unit and field == "morale":
                continue
            try:
                _finite_number(unit.get(field), f"Unit [{unit_id}] {field}", minimum=limits[0], maximum=limits[1])
            except DLCValidationError as exc:
                errors.extend(exc.errors)

        unit_type = str(unit.get("unit_type", defaults.get("unit_type", "")))
        if not any(type_id.casefold() == unit_type.casefold() for type_id in unit_types):
            errors.append(f"Unit [{unit_id}] has unsupported unit_type [{unit_type}]")
        stance = str(unit.get("stance", defaults.get("stance", "")))
        if not any(stance_id.casefold() == stance.casefold() for stance_id in stances):
            errors.append(f"Unit [{unit_id}] has unsupported stance [{stance}]")
        capabilities = unit.get("capabilities", [])
        if not isinstance(capabilities, list) or not all(isinstance(item, str) and item.strip() for item in capabilities):
            errors.append(f"Unit [{unit_id}] capabilities must be a list of non-empty strings")

        weapon_id = unit.get("primary_weapon")
        if weapon_id not in weapons:
            errors.append(f"Unit [{unit_id}] references missing weapon [{weapon_id}]")
        composition = unit.get("composition", {})
        if not isinstance(composition, dict):
            errors.append(f"Unit [{unit_id}] composition must be an object")
            continue
        for battalion_id, count in composition.items():
            if battalion_id not in battalions:
                errors.append(f"Unit [{unit_id}] references missing battalion [{battalion_id}]")
            try:
                _finite_number(count, f"Unit [{unit_id}] battalion count [{battalion_id}]", minimum=0)
            except DLCValidationError as exc:
                errors.extend(exc.errors)


def load_dlc_package(dlc_id: Any) -> DLCPackage:
    directory = resolve_dlc_path(dlc_id)
    scenario = deepcopy(_json_object(directory / "scenario.json", "scenario.json"))
    weapons = deepcopy(_json_object(directory / "weapons.json", "weapons.json"))
    battalions = deepcopy(_json_object(directory / "battalions.json", "battalions.json"))
    errors: list[str] = []

    if not str(scenario.get("scenario_name", "")).strip():
        errors.append("scenario.json requires scenario_name")
    if not isinstance(scenario.get("committee"), dict):
        errors.append("scenario.json requires a committee object")
    if not isinstance(scenario.get("diplomacy_blocs"), list):
        errors.append("scenario.json diplomacy_blocs must be a list")

    map_config = _validate_map_config(directory, scenario, errors)
    rules_file = scenario.get("simulation_rules_file")
    try:
        rules_path = _safe_child(directory, rules_file, "simulation_rules_file", "file")
        source_rules = deepcopy(_json_object(rules_path, "simulation rules file"))
    except DLCValidationError as exc:
        errors.extend(exc.errors)
        source_rules = {}

    embedded_core_sections = sorted(CORE_RULE_SECTIONS.intersection(source_rules))
    if embedded_core_sections:
        errors.append(
            "rules.json must not redefine core doctrine sections: "
            + ", ".join(embedded_core_sections)
        )
    rules = deepcopy(source_rules)
    rules.update(get_core_doctrine())
    _validate_rules(rules, errors)
    _validate_registries(weapons, battalions, errors)

    units_file = scenario.get("initial_units_file", "units.json")
    try:
        units_path = _safe_child(directory, units_file, "initial_units_file", "file")
        units = deepcopy(_json_object(units_path, "initial units file"))
    except DLCValidationError as exc:
        errors.extend(exc.errors)
        units = {}
    _validate_units(units, weapons, battalions, rules, errors)

    if errors:
        raise DLCValidationError(errors)

    return DLCPackage(
        dlc_id=str(dlc_id),
        directory=directory,
        scenario=scenario,
        map_config=map_config,
        units=units,
        weapons=weapons,
        battalions=battalions,
        rules=rules,
        source_rules=source_rules,
    )


def scan_dlcs() -> list[dict[str, Any]]:
    if not DLC_ROOT.is_dir():
        return []

    results: list[dict[str, Any]] = []
    for directory in sorted((path for path in DLC_ROOT.iterdir() if path.is_dir()), key=lambda path: path.name.lower()):
        if directory.name.startswith("_"):
            continue
        entry: dict[str, Any] = {
            "id": directory.name,
            "name": directory.name,
            "desc": "",
            "valid": False,
            "errors": [],
        }
        try:
            scenario = _json_object(directory / "scenario.json", "scenario.json")
            entry["name"] = str(scenario.get("scenario_name", directory.name))
            entry["desc"] = str(scenario.get("description", "No background briefing data."))
            load_dlc_package(directory.name)
            entry["valid"] = True
        except DLCValidationError as exc:
            entry["errors"] = exc.errors
        results.append(entry)
    return results
