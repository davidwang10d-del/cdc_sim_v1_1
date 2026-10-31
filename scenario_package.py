"""Versioned data-only packages and chair-run scenario cards.

This module never executes package code or applies simulation effects.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re

PACKAGE_FILES = {
    "scenario": "scenario.json", "rules": "rules.json", "units": "units.json",
    "weapons": "weapons.json", "battalions": "battalions.json",
    "objectives": "objectives.json", "events": "events.json",
}
CAPABILITIES = frozenset({"chair_objectives.v1", "chair_events.v1"})
EFFECTS = frozenset({"none", "morale", "supply", "fatigue", "combat_modifier", "speed_modifier"})
ID_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$")
VERSION_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_FILES = 4096
MAX_PACKAGE_BYTES = 4 * 1024 * 1024 * 1024
DATA_SUFFIXES = {".json", ".geojson", ".tif", ".tiff", ".hgt", ".png", ".jpg", ".jpeg", ".webp", ".md", ".txt"}


class ScenarioPackageError(ValueError):
    pass


def _object(value, label, required, optional=()):
    if not isinstance(value, dict):
        raise ScenarioPackageError(f"{label} must be an object")
    missing = set(required) - value.keys()
    unknown = value.keys() - set(required) - set(optional)
    if missing:
        raise ScenarioPackageError(f"{label} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise ScenarioPackageError(f"{label} has unsupported fields: {', '.join(sorted(unknown))}")


def _text(value, label, maximum=160, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()) or len(value) > maximum:
        raise ScenarioPackageError(f"{label} must be {'0' if empty else '1'}-{maximum} characters")
    return value


def _identifier(value, label):
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value) or value in {'.', '..'}:
        raise ScenarioPackageError(f"{label} must be a safe 1-64 character identifier")
    return value


def _number(value, label, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioPackageError(f"{label} must be a finite number")
    if not minimum <= value <= maximum or not math.isfinite(value):
        raise ScenarioPackageError(f"{label} must be between {minimum:g} and {maximum:g}")


def _version_one(value, label):
    if type(value) is not int or value != 1:
        raise ScenarioPackageError(f"Unsupported {label}; expected integer 1")


def new_manifest(package_id, name, publisher="Your organization"):
    return {
        "schema_version": 1, "id": package_id, "version": "1.0.0", "name": name,
        "description": "A custom MUN crisis scenario.", "publisher": publisher,
        "license": "Specify your distribution terms before publishing.",
        "engine_api_version": 1, "required_capabilities": sorted(CAPABILITIES),
        "files": dict(PACKAGE_FILES),
    }


def empty_objectives():
    return {"schema_version": 1, "objectives": []}


def empty_events():
    return {"schema_version": 1, "events": []}


def validate_manifest(manifest):
    _object(manifest, "package.json", {
        "schema_version", "id", "version", "name", "description", "publisher", "license",
        "engine_api_version", "required_capabilities", "files",
    }, {"content_hashes"})
    _version_one(manifest["schema_version"], "package schema version")
    _version_one(manifest["engine_api_version"], "engine package API version")
    _identifier(manifest["id"], "Package ID")
    if not isinstance(manifest["version"], str) or len(manifest["version"]) > 32 or not VERSION_PATTERN.fullmatch(manifest["version"]):
        raise ScenarioPackageError("Package version must use major.minor.patch, for example 1.0.0")
    for key in ("name", "publisher"):
        _text(manifest[key], f"Package {key}")
    _text(manifest["description"], "Package description", 2000, empty=True)
    _text(manifest["license"], "Package license", 1000)
    capabilities = manifest["required_capabilities"]
    if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
        raise ScenarioPackageError("required_capabilities must be a list of strings")
    if len(capabilities) != len(set(capabilities)) or set(capabilities) - CAPABILITIES:
        raise ScenarioPackageError("Package requires duplicate or unsupported capabilities")
    if manifest["files"] != PACKAGE_FILES:
        raise ScenarioPackageError("Package files must use the seven canonical JSON paths")
    if "content_hashes" in manifest:
        hashes = manifest["content_hashes"]
        if not isinstance(hashes, dict) or len(hashes) > MAX_FILES:
            raise ScenarioPackageError("content_hashes must be a bounded file-to-SHA256 object")
        for name, digest in hashes.items():
            safe_relative_path(name)
            if name == "package.json" or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ScenarioPackageError(f"Invalid content hash entry [{name}]")
        if not set(PACKAGE_FILES.values()).issubset(hashes):
            raise ScenarioPackageError("content_hashes must cover every JSON payload")


def known_factions(scenario, units, rules):
    factions = {str(rules["directives"]["default_faction"])}
    factions.update(unit["faction"] for unit in units.values())
    blocs = scenario.get("diplomacy_blocs", [])
    roles = scenario.get("committee", {}).get("delegate_roles", [])
    if not isinstance(blocs, list) or not isinstance(roles, list):
        raise ScenarioPackageError("diplomacy_blocs and committee.delegate_roles must be lists")
    for bloc in blocs:
        if not isinstance(bloc, dict):
            continue
        members = bloc.get("members", [])
        if not isinstance(members, list) or not all(isinstance(member, str) for member in members):
            raise ScenarioPackageError("Every diplomacy bloc members field must be a list of faction strings")
        factions.update(members)
    for role in roles:
        if isinstance(role, dict) and isinstance(role.get("faction"), str):
            factions.add(role["faction"])
    return factions


def _cards(document, key):
    _object(document, f"{key}.json", {"schema_version", key})
    _version_one(document["schema_version"], f"{key} schema version")
    cards = document[key]
    if not isinstance(cards, list) or len(cards) > 500:
        raise ScenarioPackageError(f"{key} must contain at most 500 cards")
    return cards


def validate_package_documents(manifest, objectives, events, scenario, units, rules):
    validate_manifest(manifest)
    if scenario.get("initial_units_file", "units.json") != "units.json" or scenario.get("simulation_rules_file") != "rules.json":
        raise ScenarioPackageError("Versioned packages must reference units.json and rules.json in scenario.json")
    objective_cards, event_cards = _cards(objectives, "objectives"), _cards(events, "events")
    factions = known_factions(scenario, units, rules)
    for cards, capability in ((objective_cards, "chair_objectives.v1"), (event_cards, "chair_events.v1")):
        if cards and capability not in manifest["required_capabilities"]:
            raise ScenarioPackageError(f"Package must declare required capability [{capability}]")
    for kind, cards in (("Objective", objective_cards), ("Event", event_cards)):
        seen = set()
        for card in cards:
            required = {"id", "title", "faction"}
            required |= {"description", "success_criteria", "points"} if kind == "Objective" else {"body", "trigger_note", "effect_type", "value", "duration_hours", "public"}
            _object(card, kind, required)
            card_id = _identifier(card["id"], f"{kind} ID")
            if card_id in seen:
                raise ScenarioPackageError(f"Duplicate {kind.lower()} ID [{card_id}]")
            seen.add(card_id)
            _text(card["title"], f"{kind} title")
            if not isinstance(card["faction"], str) or card["faction"] not in factions:
                raise ScenarioPackageError(f"{kind} [{card_id}] references unknown faction")
            if kind == "Objective":
                _text(card["description"], "Objective description", 4000, empty=True)
                _text(card["success_criteria"], "Objective success criteria", 4000)
                _number(card["points"], "Objective points", 0, 1_000_000)
            else:
                _text(card["body"], "Event body", 4000)
                _text(card["trigger_note"], "Event trigger note", 4000)
                effect = card["effect_type"]
                if not isinstance(effect, str) or effect not in EFFECTS or effect not in rules["directives"]["allowed_effects"]:
                    raise ScenarioPackageError(f"Event [{card_id}] has an unsupported effect")
                _number(card["value"], "Event value", -1_000_000, 1_000_000)
                if effect in {"combat_modifier", "speed_modifier"}:
                    _number(card["value"], "Event multiplier", 0, 100)
                _number(card["duration_hours"], "Event duration", 0, 87600)
                if card["duration_hours"] == 0:
                    raise ScenarioPackageError("Event duration must be greater than zero")
                if type(card["public"]) is not bool:
                    raise ScenarioPackageError("Event visibility must be true or false")


def safe_relative_path(name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name or "\x00" in name:
        raise ScenarioPackageError("Package paths must use safe relative forward-slash paths")
    parts = name.split("/")
    if PurePosixPath(name).is_absolute() or PureWindowsPath(name).drive or any(p in {'', '.', '..'} for p in parts):
        raise ScenarioPackageError(f"Unsafe package path [{name}]")
    for part in parts:
        if part.endswith((".", " ")) or any(ord(ch) < 32 or ch in '<>\"|?*' for ch in part):
            raise ScenarioPackageError(f"Unsafe package path [{name}]")
        stem = part.split(".")[0].upper()
        if stem in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(?:COM|LPT)[1-9]", stem):
            raise ScenarioPackageError(f"Reserved package path [{name}]")
    return name


def _contained_file(directory, name):
    safe_relative_path(name)
    root = Path(directory).resolve()
    child = root.joinpath(*name.split("/"))
    if child.is_symlink():
        raise ScenarioPackageError(f"Package symlinks are not supported [{name}]")
    try:
        child.resolve().relative_to(root)
    except ValueError as exc:
        raise ScenarioPackageError(f"Package path escapes its directory [{name}]") from exc
    if not child.is_file():
        raise ScenarioPackageError(f"Missing package file [{name}]")
    return child


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ScenarioPackageError(f"Duplicate JSON field [{key}]")
        result[key] = value
    return result


def read_json_document(directory, name):
    path = _contained_file(directory, name)
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ScenarioPackageError(f"JSON document too large [{name}]")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_pairs)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise ScenarioPackageError(f"Cannot read {name}: {exc}") from exc


def package_files(directory):
    root = Path(directory).resolve()
    names, folded, total = [], set(), 0
    for child in sorted(root.rglob("*")):
        name = child.relative_to(root).as_posix()
        safe_relative_path(name)
        if child.is_symlink() or (hasattr(child, "is_junction") and child.is_junction()):
            raise ScenarioPackageError(f"Package links are not supported [{name}]")
        if name.casefold() in folded:
            raise ScenarioPackageError(f"Case-colliding package paths [{name}]")
        folded.add(name.casefold())
        if child.is_dir():
            continue
        if not child.is_file():
            raise ScenarioPackageError(f"Unsupported package entry [{name}]")
        allowed_root = set(PACKAGE_FILES.values()) | {"package.json", "README.md", "ATTRIBUTION.md", "LICENSE.txt"}
        is_asset = len(child.relative_to(root).parts) > 1 and child.relative_to(root).parts[0] in {"maps", "assets", "briefings"}
        if name not in allowed_root and not (is_asset and child.suffix.lower() in DATA_SUFFIXES):
            raise ScenarioPackageError(f"Unsupported package file [{name}]; include only scenario data and approved assets")
        _contained_file(root, name)
        total += child.stat().st_size
        names.append(name)
        if len(names) > MAX_FILES or total > MAX_PACKAGE_BYTES:
            raise ScenarioPackageError("Package exceeds file-count or expanded-size limits")
    return names


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_package_extensions(directory, scenario, units, rules):
    directory = Path(directory)
    if not (directory / "package.json").exists():
        if any((directory / name).exists() for name in ("objectives.json", "events.json")):
            raise ScenarioPackageError("Objectives/events files require package.json; they cannot be silently ignored")
        return None, empty_objectives(), empty_events()
    manifest = read_json_document(directory, "package.json")
    objectives = read_json_document(directory, "objectives.json")
    events = read_json_document(directory, "events.json")
    validate_package_documents(manifest, objectives, events, scenario, units, rules)
    names = package_files(directory)
    if "content_hashes" in manifest:
        hashes = manifest["content_hashes"]
        if set(hashes) != set(names) - {"package.json"}:
            raise ScenarioPackageError("Content hash inventory does not match the package files")
        for name, expected in hashes.items():
            if file_digest(_contained_file(directory, name)) != expected:
                raise ScenarioPackageError(f"Content hash mismatch [{name}]")
    return deepcopy(manifest), deepcopy(objectives), deepcopy(events)
