import time
import math
import os
import json
import random
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
import threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from gis import MapEngine, ProvinceEngine, haversine_distance
from app import MilitaryUnit
from installations import MilitaryInstallation
from dlc_loader import DLCPackage, PROJECT_ROOT, load_dlc_package, validate_identifier


_SAVE_SLOT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
# ==========================================
# 2. Grand Strategy Simulation Engine (Tactical Maneuver Edition)
# ==========================================
class SimulationEngine:
    def __init__(self, dlc_id, log_file=None, storage_dir=None, package: DLCPackage | None = None):
        """
        [Architecture] Universal DLC Mounting Engine
        [Logic] Dynamically concatenates relative paths based on dlc_id, reads the corresponding 
                campaign's JSON configuration, and achieves "Hot-Swapping" capability 
                (e.g., instantly switching to Middle East, Taiwan Strait, Eastern Europe).
        """
        package = package or load_dlc_package(dlc_id)
        self.dlc_dir = str(package.directory)
        self.dlc_id = package.dlc_id
        self.scenario_data = deepcopy(package.scenario)
        self.initial_cities = deepcopy(self.scenario_data.get("cities", []))
        self.initial_province_politics = deepcopy(self.scenario_data.get("province_politics", []))
        self.initial_installations_data = deepcopy(
            self.scenario_data.get("military_installations", [])
        )
        self.initial_units_data = deepcopy(package.units)
        self.weapon_registry = deepcopy(package.weapons)
        self.battalion_registry = deepcopy(package.battalions)
        self.rules = deepcopy(package.rules)
        self.storage_dir = Path(storage_dir or PROJECT_ROOT).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = str(Path(log_file).resolve()) if log_file and log_file != os.devnull else (log_file or str(self.storage_dir / "battle_log.txt"))
        self.lock = threading.RLock()
        self._stop_event = threading.Event()

        print(f"\n=== 🌐 Initializing Grand Strategy Engine | Mounting Theater: [{dlc_id}] ===")

        map_config = deepcopy(package.map_config)
        self.map_config = deepcopy(map_config)

        # Feed the dynamic path configuration to the GIS engine
        self.map_engine = MapEngine(map_config, self.rules["geography"])
        self.prov_engine = ProvinceEngine(
            map_config.get("provinces_file", ""),
            map_config.get("province_name_property", ""),
        )
        
        self.province_politics = {}
        self.units = {}
        self.installations = {}
        self.structured_logs = []
        self.committee_records = []
        self.cities = []
        
        self.detected_units = {}
        self.detected_installations = {}
        self._active_close_engagements = set()
        self.diplomacy = {}
        self.committee_config = self._build_committee_config()
        
        self.time_multiplier = float(self.rules["clock"]["default_time_multiplier"])
        self.is_paused = True
        self.game_hours = 0.0
        
        self._init_log_file()
            
        # Mounting a DLC always starts from its authored scenario. Persistence is
        # deliberately manual so an old checkpoint can never replace a fresh
        # committee session without the chair choosing Restore.
        self.load_initial_scenario()

    def _build_committee_config(self):
        return deepcopy(self.scenario_data["committee"])

    @staticmethod
    def _gis_matrix_has_data(matrix):
        if matrix is None:
            return False
        try:
            matrix_any = getattr(matrix, "any", None)
            if callable(matrix_any):
                return bool(matrix_any())
            return any(any(row) if hasattr(row, "__iter__") else bool(row) for row in matrix)
        except (TypeError, ValueError):
            return False

    def get_gis_status(self):
        """Describe optional GIS inputs and the safe default active for each one."""
        fallback_elevation = float(self.map_config.get("fallback_elevation_m", 0.0))
        terrain_configured = bool(self.map_config.get("dem_dir") or self.map_config.get("dem_file"))
        roads_configured = bool(self.map_config.get("roads_file"))
        rivers_configured = bool(self.map_config.get("rivers_file"))
        provinces_configured = bool(self.map_config.get("provinces_file"))

        terrain_enabled = bool(getattr(self.map_engine, "use_real_dem", False))
        roads_enabled = self._gis_matrix_has_data(getattr(self.map_engine, "road_matrix", None))
        rivers_enabled = self._gis_matrix_has_data(getattr(self.map_engine, "river_matrix", None))
        province_count = len(getattr(self.prov_engine, "provinces", []) or [])
        provinces_enabled = province_count > 0

        features = [
            {
                "id": "terrain_dem",
                "label": "Terrain DEM",
                "enabled": terrain_enabled,
                "configured": terrain_configured,
                "mode": "installed" if terrain_enabled else "default",
                "detail": "Installed elevation controls terrain cost and line of sight." if terrain_enabled else f"Flat terrain at {fallback_elevation:g} m with unobstructed default line of sight.",
                "warning": "Configured terrain DEM is unavailable; the flat-terrain default is active." if terrain_configured and not terrain_enabled else None,
            },
            {
                "id": "roads",
                "label": "Road network",
                "enabled": roads_enabled,
                "configured": roads_configured,
                "mode": "installed" if roads_enabled else "default",
                "detail": "Installed roads modify route finding and movement cost." if roads_enabled else "Base terrain movement cost is used everywhere.",
                "warning": "Configured road data is unavailable or empty; base movement costs are active." if roads_configured and not roads_enabled else None,
            },
            {
                "id": "rivers",
                "label": "River network",
                "enabled": rivers_enabled,
                "configured": rivers_configured,
                "mode": "installed" if rivers_enabled else "default",
                "detail": "Installed rivers apply crossing penalties during route finding." if rivers_enabled else "No river-crossing penalty is applied.",
                "warning": "Configured river data is unavailable or empty; river penalties are disabled." if rivers_configured and not rivers_enabled else None,
            },
            {
                "id": "provinces",
                "label": "Province boundaries",
                "enabled": provinces_enabled,
                "configured": provinces_configured,
                "mode": "installed" if provinces_enabled else "default",
                "detail": f"{province_count} province boundaries provide location and political shading." if provinces_enabled else "Locations use Unknown/Unmapped and boundary shading is disabled.",
                "warning": "Configured province data is unavailable or empty; unmapped defaults are active." if provinces_configured and not provinces_enabled else None,
            },
        ]
        return {
            "fallback_elevation_m": fallback_elevation,
            "enabled_count": sum(1 for feature in features if feature["enabled"]),
            "features": features,
        }

    def log_event(self, message, faction="SYSTEM", msg_type="system"):
        d = int(self.game_hours // 24)
        h = int(self.game_hours % 24)
        m = int((self.game_hours * 60) % 60)
        s = int((self.game_hours * 3600) % 60)
        
        timestamp = f"[D{d:02d} {h:02d}:{m:02d}:{s:02d}] "
        full_msg = timestamp + message
        
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(full_msg + "\n")
        except OSError:
            pass
        print(full_msg)
        
        self.structured_logs.append({
            "timestamp": f"D{d:02d} {h:02d}:{m:02d}:{s:02d}", 
            "faction": faction, 
            "message": message, 
            "type": msg_type
        })
        self.structured_logs = self.structured_logs[-int(self.rules["state_limits"]["structured_logs"]):]

    def _init_log_file(self):
        header = f"=== CDC Classified Simulation Physics Log | Campaign: {self.scenario_data.get('scenario_name', 'Universal')} ===\n"
        candidates = [
            self.log_file,
            str(self.storage_dir / f"battle_log_{self.dlc_id}.txt"),
        ]
        for candidate in candidates:
            try:
                with open(candidate, 'a', encoding='utf-8') as f:
                    f.write(header)
                self.log_file = candidate
                return
            except OSError:
                continue
        self.log_file = os.devnull

    def set_alliance(self, f1, f2, allied=True):
        if f1 not in self.diplomacy: 
            self.diplomacy[f1] = {}
        if f2 not in self.diplomacy: 
            self.diplomacy[f2] = {}
            
        self.diplomacy[f1][f2] = {"allied": allied}
        self.diplomacy[f2][f1] = {"allied": allied}

    def is_allied(self, f1, f2):
        if f1 == f2: 
            return True
        return self.diplomacy.get(f1, {}).get(f2, {}).get("allied", False)

    def load_initial_scenario(self):
        with self.lock:
            fresh_units = {
                unit_id: MilitaryUnit(
                    unit_id,
                    deepcopy(unit_data),
                    self.weapon_registry,
                    self.battalion_registry,
                    self.rules,
                )
                for unit_id, unit_data in self.initial_units_data.items()
            }
            for unit in fresh_units.values():
                unit.altitude = self.map_engine.get_elevation(unit.lon, unit.lat)
                unit.current_province = self.prov_engine.get_province(unit.lon, unit.lat)

            fresh_installations = {}
            for installation_data in self.initial_installations_data:
                installation_id = installation_data["id"]
                installation = MilitaryInstallation(
                    installation_id,
                    deepcopy(installation_data),
                    self.rules["military_installations"]["types"],
                )
                installation.altitude = self.map_engine.get_elevation(
                    installation.lon, installation.lat
                )
                installation.current_province = self.prov_engine.get_province(
                    installation.lon, installation.lat
                )
                fresh_installations[installation_id] = installation

            self.units = fresh_units
            self.installations = fresh_installations
            self.province_politics = {}
            self.detected_units = {}
            self.detected_installations = {}
            self._active_close_engagements = set()
            self.committee_records = []
            self.cities = deepcopy(self.initial_cities)
            self.diplomacy = {}
            self.game_hours = 0.0
            self.time_multiplier = float(self.rules["clock"]["default_time_multiplier"])
            self.is_paused = True

            # Diplomacy and faction membership are supplied by the active DLC.
            for bloc in self.scenario_data.get("diplomacy_blocs", []):
                members = bloc.get("members", [])
                for m1 in members:
                    for m2 in members:
                        self.set_alliance(m1, m2, True)

            for entry in self.initial_province_politics:
                self.set_province_politics(entry)
            self.refresh_province_presence()

            self.log_event(f"🔄 [System] Initial tactical scenario [{self.scenario_data.get('scenario_name', 'Unknown')}] loaded successfully.", faction="SYSTEM")

    def _save_path(self, slot_name):
        if not isinstance(slot_name, str) or not _SAVE_SLOT_PATTERN.fullmatch(slot_name):
            raise ValueError("Save slot must use 1-32 letters, numbers, dashes, or underscores")
        if slot_name.lower() == "autosave":
            raise ValueError("Autosave is disabled; choose a manual checkpoint")
        return self.storage_dir / f"save_{slot_name}.json"

    def save_game(self, slot_name):
        filename = self._save_path(slot_name)
        temp_filename = filename.with_suffix(filename.suffix + ".tmp")
        with self.lock:
            self.refresh_province_presence()
            save_data = {
                "format_version": 4,
                "dlc_id": self.dlc_id,
                "scenario_name": self.scenario_data.get("scenario_name", self.dlc_id),
                "rules_schema_version": self.rules["schema_version"],
                "saved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "game_hours": self.game_hours,
                "time_multiplier": self.time_multiplier,
                "is_paused": self.is_paused,
                "province_politics": self.province_politics,
                "detected_units": self.detected_units,
                "detected_installations": self.detected_installations,
                "committee_records": self.committee_records,
                "cities": self.cities,
                "structured_logs": self.structured_logs,
                "diplomacy": self.diplomacy,
                "units": {k: v.to_dict() for k, v in self.units.items()},
                "installations": {k: v.to_dict() for k, v in self.installations.items()},
            }
            try:
                with open(temp_filename, 'w', encoding='utf-8') as f:
                    json.dump(save_data, f, ensure_ascii=False, indent=2, allow_nan=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_filename, filename)
            finally:
                try:
                    temp_filename.unlink(missing_ok=True)
                except OSError:
                    pass

            self.log_event(f"💾 [System] Battle state manually saved to: [{slot_name}]", faction="SYSTEM")
        return filename

    def save_slot_metadata(self, slot_name):
        """Return display-safe metadata without changing the active simulation."""
        filename = self._save_path(slot_name)
        result = {
            "slot": slot_name,
            "exists": filename.exists(),
            "can_load": False,
            "condition": "empty",
            "message": "Empty checkpoint",
            "saved_at_utc": None,
            "game_hours": None,
            "unit_count": None,
            "installation_count": None,
            "dlc_id": None,
            "scenario_name": None,
            "legacy": False,
        }
        if not result["exists"]:
            return result

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                save_data = json.load(f)
            if not isinstance(save_data, dict):
                raise ValueError("Save root must be an object")

            format_version = save_data.get("format_version", 1)
            if isinstance(format_version, bool) or format_version not in (1, 2, 3, 4):
                raise ValueError(f"Unsupported save format [{format_version}]")

            game_hours = float(save_data.get("game_hours", 0.0))
            time_multiplier = float(save_data.get("time_multiplier", 1.0))
            raw_units = save_data.get("units", {})
            if not math.isfinite(game_hours) or game_hours < 0:
                raise ValueError("Save has invalid game time")
            if not math.isfinite(time_multiplier) or time_multiplier <= 0:
                raise ValueError("Save has invalid time multiplier")
            if not isinstance(raw_units, dict):
                raise ValueError("Save units must be an object")

            saved_at = save_data.get("saved_at_utc")
            if not isinstance(saved_at, str) or not saved_at.strip():
                saved_at = datetime.fromtimestamp(filename.stat().st_mtime, tz=timezone.utc).isoformat(
                    timespec="seconds"
                ).replace("+00:00", "Z")

            saved_dlc = save_data.get("dlc_id")
            saved_schema = save_data.get("rules_schema_version")
            result.update({
                "saved_at_utc": saved_at,
                "game_hours": game_hours,
                "unit_count": len(raw_units),
                "installation_count": len(save_data.get("installations", {})),
                "dlc_id": saved_dlc,
                "scenario_name": save_data.get("scenario_name") or saved_dlc,
                "legacy": not bool(saved_dlc),
            })
            if saved_dlc and saved_dlc != self.dlc_id:
                result.update({
                    "condition": "wrong_dlc",
                    "message": f"Saved for DLC [{saved_dlc}]",
                })
            elif saved_schema is not None and saved_schema != self.rules["schema_version"]:
                result.update({
                    "condition": "incompatible_rules",
                    "message": "Rules version is incompatible",
                })
            else:
                result.update({
                    "can_load": True,
                    "condition": "available",
                    "message": "Legacy checkpoint (DLC not recorded)" if not saved_dlc else "Ready to restore",
                })
        except OSError:
            result.update({
                "condition": "invalid",
                "message": "Checkpoint could not be read",
            })
        except (OverflowError, json.JSONDecodeError, TypeError, ValueError) as exc:
            result.update({
                "condition": "invalid",
                "message": f"Invalid checkpoint: {exc}",
            })
        return result

    def load_game(self, slot_name):
        try:
            filename = self._save_path(slot_name)
        except ValueError as exc:
            return False, str(exc)
        if not filename.exists():
            return False, f"Save file not found: {filename.name}"

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                save_data = json.load(f)
            if not isinstance(save_data, dict):
                raise ValueError("Save root must be an object")

            format_version = save_data.get("format_version", 1)
            if isinstance(format_version, bool) or format_version not in (1, 2, 3, 4):
                raise ValueError(f"Unsupported save format [{format_version}]")

            saved_dlc = save_data.get("dlc_id")
            if saved_dlc and saved_dlc != self.dlc_id:
                return False, f"Save belongs to DLC [{saved_dlc}], current DLC is [{self.dlc_id}]"
            saved_rules_schema = save_data.get("rules_schema_version")
            if saved_rules_schema is not None and saved_rules_schema != self.rules["schema_version"]:
                return False, "Save uses an incompatible DLC rules schema"

            game_hours = float(save_data.get("game_hours", 0.0))
            time_multiplier = float(save_data.get("time_multiplier", 1.0))
            if not math.isfinite(game_hours) or game_hours < 0:
                raise ValueError("Save has invalid game time")
            if not math.isfinite(time_multiplier) or time_multiplier <= 0:
                raise ValueError("Save has invalid time multiplier")

            raw_units = save_data.get("units", {})
            if not isinstance(raw_units, dict):
                raise ValueError("Save units must be an object")
            restored_units = {}
            for unit_id, unit_data in raw_units.items():
                safe_unit_id = validate_identifier(unit_id, "Saved unit ID")
                restored_units[safe_unit_id] = MilitaryUnit(
                    safe_unit_id,
                    unit_data,
                    self.weapon_registry,
                    self.battalion_registry,
                    self.rules,
                )

            raw_installations = save_data.get(
                "installations",
                self.initial_installations_data if format_version < 4 else {},
            )
            if isinstance(raw_installations, list):
                installation_items = []
                for item in raw_installations:
                    if not isinstance(item, dict):
                        raise ValueError("Save installations list must contain objects")
                    installation_items.append((item.get("id"), item))
            elif isinstance(raw_installations, dict):
                installation_items = list(raw_installations.items())
            else:
                raise ValueError("Save installations must be an object or list")
            restored_installations = {}
            for installation_id, installation_data in installation_items:
                safe_installation_id = validate_identifier(
                    installation_id, "Saved installation ID"
                )
                if safe_installation_id in restored_units:
                    raise ValueError(
                        f"Saved installation ID [{safe_installation_id}] conflicts with a unit"
                    )
                installation = MilitaryInstallation(
                    safe_installation_id,
                    installation_data,
                    self.rules["military_installations"]["types"],
                )
                installation.altitude = self.map_engine.get_elevation(
                    installation.lon, installation.lat
                )
                installation.current_province = self.prov_engine.get_province(
                    installation.lon, installation.lat
                )
                restored_installations[safe_installation_id] = installation

            raw_province_politics = save_data.get("province_politics", save_data.get("provinces", {}))
            detected_units = save_data.get("detected_units", {})
            detected_installations = save_data.get("detected_installations", {})
            committee_records = save_data.get("committee_records", [])
            raw_cities = save_data.get("cities", self.initial_cities)
            structured_logs = save_data.get("structured_logs", self.structured_logs)
            diplomacy = save_data.get("diplomacy", {})
            if (
                not isinstance(raw_province_politics, dict)
                or not isinstance(detected_units, dict)
                or not isinstance(detected_installations, dict)
                or not isinstance(diplomacy, dict)
            ):
                raise ValueError("Save contains invalid map, detection, or diplomacy state")
            if not isinstance(committee_records, list) or not isinstance(structured_logs, list):
                raise ValueError("Save contains invalid committee or log records")
            if not isinstance(raw_cities, list):
                raise ValueError("Save cities must be a list")
            restored_cities = [self.validate_city(city) for city in raw_cities]
            if len({city["id"] for city in restored_cities}) != len(restored_cities):
                raise ValueError("Save contains duplicate city IDs")
            restored_province_politics = self.validate_province_politics_state(raw_province_politics)
        except OSError:
            return False, "Checkpoint could not be read"
        except (OverflowError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            return False, f"Save is invalid: {exc}"

        # Commit only after every field and unit has been parsed successfully.
        with self.lock:
            self.game_hours = game_hours
            self.time_multiplier = time_multiplier
            # Loading is always fail-safe: chairs explicitly resume when ready.
            self.is_paused = True
            self.province_politics = restored_province_politics
            self.detected_units = detected_units
            self.detected_installations = detected_installations
            self._active_close_engagements = set()
            self.committee_records = committee_records[-int(self.rules["state_limits"]["committee_records"]):]
            self.cities = restored_cities
            self.structured_logs = structured_logs[-int(self.rules["state_limits"]["structured_logs"]):]
            self.diplomacy = diplomacy
            self.units = restored_units
            self.installations = restored_installations
            self.refresh_province_presence()
            self.log_event(f"📂 [System] Save file awakened: [{slot_name}]", faction="SYSTEM")
        return True, "Load successful"

    def stop(self):
        """Request a clean shutdown of this engine's heartbeat loop."""
        self._stop_event.set()

    @property
    def is_stopped(self):
        return self._stop_event.is_set()

    def _clamp(self, value, low, high):
        return max(low, min(high, value))

    def get_builder_project(self, unit_id):
        return next(
            (
                installation
                for installation in self.installations.values()
                if installation.builder_unit_id == unit_id
                and installation.status == "UNDER_CONSTRUCTION"
            ),
            None,
        )

    def _next_installation_id(self, type_id):
        base = re.sub(r"[^a-z0-9_]+", "_", str(type_id).lower()).strip("_") or "site"
        index = 1
        while True:
            candidate = f"inst_{base}_{index:04d}"
            if candidate not in self.installations and candidate not in self.units:
                return candidate
            index += 1

    def start_installation_construction(self, unit_id, requested_type_id):
        if unit_id not in self.units:
            raise ValueError("Builder unit not found")
        unit = self.units[unit_id]
        if unit.personnel <= 0:
            raise ValueError("A neutralized unit cannot build an installation")
        if not self.rules["unit_types"][unit.unit_type]["can_direct_combat"]:
            raise ValueError("This unit type cannot construct a ground installation")
        if unit.status in {"MOVING", "BOMBARDING", "AIRSTRIKE_OUTBOUND", "AIRSTRIKE_RTB"} or unit.waypoints:
            raise ValueError("The builder must be stationary and free of an active support mission")

        types = self.rules["military_installations"]["types"]
        type_id = next(
            (candidate for candidate in types if candidate.casefold() == str(requested_type_id).casefold()),
            None,
        )
        if type_id is None:
            raise ValueError(f"Unknown military installation type [{requested_type_id}]")
        profile = types[type_id]
        required_capability = str(profile.get("builder_capability", "")).strip()
        if required_capability and not unit.has_capability(required_capability):
            raise ValueError(
                f"Building {profile['label']} requires capability [{required_capability}]"
            )

        construction = self.rules["military_installations"]["construction"]
        active_projects = [
            installation
            for installation in self.installations.values()
            if installation.builder_unit_id == unit_id
            and installation.status == "UNDER_CONSTRUCTION"
        ]
        if active_projects:
            existing = active_projects[0]
            if existing.type_id != type_id:
                raise ValueError(
                    f"{unit.name} already has an unfinished {existing.profile['label']} project"
                )
            unit.status = "CONSTRUCTING"
            unit.set_order_role("hold")
            self.log_event(
                f"🏗️ [Construction Resumed] {unit.name} resumed work on {existing.name}.",
                faction=unit.faction,
                msg_type="move",
            )
            return existing, True
        if len(active_projects) >= int(construction["maximum_projects_per_builder"]):
            raise ValueError("This unit has reached its active construction-project limit")
        if unit.supply < float(construction["minimum_supply_to_start"]):
            raise ValueError(
                f"Construction requires at least {float(construction['minimum_supply_to_start']):g}% supply"
            )
        minimum_separation = float(construction["minimum_separation_km"])
        for installation in self.installations.values():
            if installation.status == "DESTROYED":
                continue
            distance = haversine_distance(unit.lon, unit.lat, installation.lon, installation.lat)
            if distance < minimum_separation:
                raise ValueError(
                    f"Another military installation is only {distance:.2f} km away; "
                    f"minimum separation is {minimum_separation:g} km"
                )

        installation_id = self._next_installation_id(type_id)
        sequence = sum(1 for site in self.installations.values() if site.type_id == type_id) + 1
        installation = MilitaryInstallation(
            installation_id,
            {
                "type_id": type_id,
                "name": f"{unit.faction} {profile['label']} {sequence}",
                "faction": unit.faction,
                "lon": unit.lon,
                "lat": unit.lat,
                "construction_progress": 0.0,
                "builder_unit_id": unit.id,
                "altitude": self.map_engine.get_elevation(unit.lon, unit.lat),
                "current_province": self.prov_engine.get_province(unit.lon, unit.lat),
            },
            types,
        )
        self.installations[installation_id] = installation
        unit.waypoints = []
        unit.target_lon = unit.target_lat = None
        unit.status = "CONSTRUCTING"
        unit.set_order_role("hold")
        unit.entrenchment = float(self.rules["unit_defaults"]["entrenchment"])
        self.log_event(
            f"🏗️ [Construction Started] {unit.name} began {installation.name} at "
            f"{unit.lon:.4f}, {unit.lat:.4f}; planned duration "
            f"{float(profile['construction_hours']):g} hours.",
            faction=unit.faction,
            msg_type="move",
        )
        return installation, False

    def installation_tick(self, dt):
        if dt <= 0:
            return
        construction = self.rules["military_installations"]["construction"]
        resources = self.rules["resources"]
        resource_min = float(resources["minimum"])
        resource_max = float(resources["maximum"])
        work_radius = float(construction["work_radius_km"])
        stop_supply = float(construction["stop_supply_threshold"])
        suppression_span = max(1.0, resource_max - resource_min)

        for installation in self.installations.values():
            if installation.status != "UNDER_CONSTRUCTION":
                continue
            builder = self.units.get(installation.builder_unit_id)
            if builder is None or builder.personnel <= 0 or not self.is_allied(builder.faction, installation.faction):
                continue
            if builder.status != "CONSTRUCTING" or builder.waypoints:
                continue
            distance = haversine_distance(builder.lon, builder.lat, installation.lon, installation.lat)
            if distance > work_radius or builder.supply <= stop_supply:
                continue

            profile = installation.profile
            build_hours = float(profile["construction_hours"])
            total_supply_cost = float(profile["construction_supply_cost"])
            suppression_ratio = self._clamp(
                (builder.suppression - resource_min) / suppression_span, 0.0, 1.0
            )
            efficiency = max(
                0.0,
                1.0
                - suppression_ratio * float(construction["suppression_build_penalty"]),
            )
            if efficiency <= 0:
                continue

            active_hours = float(dt)
            supply_per_progress = total_supply_cost
            if supply_per_progress > 0:
                affordable_progress = max(0.0, builder.supply - stop_supply) / supply_per_progress
                active_hours = min(active_hours, affordable_progress * build_hours / efficiency)
            remaining_progress = 1.0 - installation.construction_progress
            active_hours = min(active_hours, remaining_progress * build_hours / efficiency)
            if active_hours <= 0:
                continue

            progress_delta = active_hours / build_hours * efficiency
            installation.construction_progress = min(
                1.0, installation.construction_progress + progress_delta
            )
            builder.supply = max(
                resource_min, builder.supply - total_supply_cost * progress_delta
            )
            builder.fatigue = min(
                resource_max,
                builder.fatigue + float(construction["fatigue_per_hour"]) * active_hours,
            )

            if installation.is_operational:
                if builder.status == "CONSTRUCTING":
                    builder.status = "IDLE"
                self.log_event(
                    f"✅ [Installation Operational] {installation.name} is complete and active.",
                    faction=installation.faction,
                    msg_type="move",
                )

    def apply_installation_damage(self, installation, amount, source_name, attack_kind):
        was_destroyed = installation.status == "DESTROYED"
        actual = installation.apply_damage(amount)
        if actual > 0 and not was_destroyed and installation.status == "DESTROYED":
            builder = self.units.get(installation.builder_unit_id)
            if builder is not None and builder.status == "CONSTRUCTING":
                builder.status = "IDLE"
            self.log_event(
                f"💥 [Military Target Destroyed] {installation.name} was destroyed by "
                f"{source_name} ({attack_kind}).",
                faction=installation.faction,
                msg_type="combat",
            )
        return actual

    @staticmethod
    def validate_province_politics_entry(data):
        if not isinstance(data, dict):
            raise ValueError("Province politics entry must be an object")
        province = str(data.get("province", "")).strip()
        faction = str(data.get("faction", "")).strip()
        if not province:
            raise ValueError("Province is required")
        if not faction:
            raise ValueError("Faction is required")

        def number(field, minimum, maximum):
            try:
                value = float(data.get(field, 0))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field.replace('_', ' ').title()} must be a number") from exc
            if not math.isfinite(value) or value < minimum or value > maximum:
                raise ValueError(f"{field.replace('_', ' ').title()} must be between {minimum:g} and {maximum:g}")
            return value

        return {
            "province": province[:120],
            "faction": faction[:120],
            "civilian_sentiment": number("civilian_sentiment", -1.0, 1.0),
            "occupation": number("occupation", 0.0, 1.0),
        }

    @staticmethod
    def _default_political_record(civilian_sentiment=0.0, occupation=0.0):
        return {
            "civilian_sentiment": float(civilian_sentiment),
            "occupation": float(occupation),
            "military_presence": 0.0,
            "force_strength": 0.0,
            "influence": 0.0,
        }

    def set_province_politics(self, data):
        entry = self.validate_province_politics_entry(data)
        state = self.province_politics.setdefault(entry["province"], {
            "factions": {}, "controller": None, "contested": False,
        })
        record = state["factions"].setdefault(entry["faction"], self._default_political_record())
        record["civilian_sentiment"] = entry["civilian_sentiment"]
        record["occupation"] = entry["occupation"]
        self.recalculate_province_control(entry["province"])
        return entry

    def remove_province_politics(self, province, faction):
        state = self.province_politics.get(province)
        if not state or faction not in state.get("factions", {}):
            return False
        del state["factions"][faction]
        if not state["factions"]:
            del self.province_politics[province]
        else:
            self.recalculate_province_control(province)
        return True

    def validate_province_politics_state(self, raw_state):
        """Validate current saves and migrate the former flat province score."""
        restored = {}
        for raw_province, raw_value in raw_state.items():
            province = str(raw_province).strip()[:120]
            if not province:
                raise ValueError("Province politics contains an empty province name")
            if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
                legacy_value = float(raw_value)
                if not math.isfinite(legacy_value):
                    raise ValueError(f"Legacy province influence [{province}] must be finite")
                if abs(legacy_value) > 1:
                    legacy_value /= 100.0
                legacy_value = self._clamp(legacy_value, -1.0, 1.0)
                restored[province] = {
                    "factions": {
                        "LEGACY": self._default_political_record(
                            civilian_sentiment=legacy_value,
                            occupation=max(0.0, legacy_value),
                        )
                    },
                    "controller": None,
                    "contested": False,
                }
                continue
            if not isinstance(raw_value, dict) or not isinstance(raw_value.get("factions"), dict):
                raise ValueError(f"Province politics [{province}] must contain faction records")
            state = {"factions": {}, "controller": None, "contested": False}
            for raw_faction, raw_record in raw_value["factions"].items():
                faction = str(raw_faction).strip()[:120]
                if not faction or not isinstance(raw_record, dict):
                    raise ValueError(f"Province politics [{province}] has an invalid faction record")
                entry = self.validate_province_politics_entry({
                    "province": province,
                    "faction": faction,
                    "civilian_sentiment": raw_record.get("civilian_sentiment", 0),
                    "occupation": raw_record.get("occupation", 0),
                })
                record = self._default_political_record(entry["civilian_sentiment"], entry["occupation"])
                for field in ("military_presence", "force_strength"):
                    value = float(raw_record.get(field, 0))
                    if not math.isfinite(value) or value < 0 or value > 1:
                        raise ValueError(f"Province politics [{province}] {field} must be between 0 and 1")
                    record[field] = value
                state["factions"][faction] = record
            restored[province] = state
        return restored

    def recalculate_province_control(self, province):
        state = self.province_politics.get(province)
        if not state:
            return
        rules = self.rules["political_influence"]
        minimum = float(rules["minimum"])
        maximum = float(rules["maximum"])
        threshold = float(rules["contested_threshold"])
        contenders = []
        for faction, record in state["factions"].items():
            sentiment = self._clamp(float(record.get("civilian_sentiment", 0)), minimum, maximum)
            occupation = self._clamp(float(record.get("occupation", 0)), 0.0, 1.0)
            # Occupation fills the remaining distance toward support while never
            # erasing absolute civilian opposition (-1).
            record["influence"] = self._clamp(
                sentiment + occupation * (1.0 - abs(sentiment)),
                minimum,
                maximum,
            )
            if max(occupation, float(record.get("military_presence", 0))) >= threshold:
                contenders.append(faction)

        state["contested"] = any(
            not self.is_allied(first, second)
            for index, first in enumerate(contenders)
            for second in contenders[index + 1:]
        )
        ranked = sorted(
            state["factions"].items(),
            key=lambda item: (float(item[1].get("occupation", 0)), float(item[1].get("influence", 0))),
            reverse=True,
        )
        controller = None
        if ranked and not state["contested"]:
            leading_faction, leading_record = ranked[0]
            hostile_occupation = max(
                (
                    float(record.get("occupation", 0))
                    for faction, record in ranked[1:]
                    if not self.is_allied(leading_faction, faction)
                ),
                default=0.0,
            )
            if (
                float(leading_record.get("occupation", 0)) >= float(rules["control_threshold"])
                and float(leading_record.get("occupation", 0)) - hostile_occupation >= float(rules["control_margin"])
            ):
                controller = leading_faction
        state["controller"] = controller

    def recalculate_all_province_control(self):
        for province in list(self.province_politics):
            self.recalculate_province_control(province)

    def get_province_politics_state(self):
        return deepcopy(self.province_politics)

    @staticmethod
    def validate_city(data):
        """Validate and normalize mutable city state from saves or Chair edits."""
        if not isinstance(data, dict):
            raise ValueError("City must be an object")
        try:
            city_id = validate_identifier(data.get("id"), "City ID")
        except Exception as exc:
            raise ValueError(str(exc)) from exc
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("City name is required")

        def number(field, minimum=None, maximum=None):
            try:
                value = float(data.get(field, 0))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"City {field} must be a number") from exc
            if not math.isfinite(value):
                raise ValueError(f"City {field} must be finite")
            if minimum is not None and value < minimum:
                raise ValueError(f"City {field} must be at least {minimum:g}")
            if maximum is not None and value > maximum:
                raise ValueError(f"City {field} must be at most {maximum:g}")
            return value

        return {
            "id": city_id,
            "name": name[:120],
            "description": str(data.get("description", "")).strip()[:500],
            "lon": number("lon", -180, 180),
            "lat": number("lat", -90, 90),
            "area_km2": number("area_km2", 0),
            "influence_rate": number("influence_rate", 0, 1),
        }

    @staticmethod
    def city_radius_km(city):
        return math.sqrt(max(0.0, float(city.get("area_km2", 0.0))) / math.pi)

    def get_city_context(self, lon, lat):
        """Return the strongest city area covering a coordinate."""
        strongest = None
        strongest_rate = 0.0
        for city in self.cities:
            radius_km = self.city_radius_km(city)
            if radius_km <= 0 or haversine_distance(lon, lat, city["lon"], city["lat"]) > radius_km:
                continue
            rate = float(city.get("influence_rate", 0.0))
            if strongest is None or rate > strongest_rate:
                strongest = city
                strongest_rate = rate
        if strongest is None:
            return {"id": None, "name": None, "influence_rate": 0.0}
        return {
            "id": strongest["id"],
            "name": strongest["name"],
            "influence_rate": strongest_rate,
        }

    def get_terrain_complexity(self, lon, lat):
        """Blend natural terrain with the strongest city influence at a point."""
        natural = self._clamp(float(self.map_engine.get_terrain_complexity(lon, lat)), 0.0, 1.0)
        city_rate = self.get_city_context(lon, lat)["influence_rate"]
        return self._clamp(natural + (1.0 - natural) * city_rate, 0.0, 1.0)

    def get_city_state(self):
        return [dict(city, radius_km=self.city_radius_km(city)) for city in self.cities]

    def get_installation_state(self):
        state = {}
        for installation_id, installation in self.installations.items():
            record = installation.to_dict()
            detection = self.detected_installations.get(installation_id, {})
            record["detected_by"] = list(detection.get("factions", [])) if isinstance(detection, dict) else []
            state[installation_id] = record
        return state

    def _committee_timestamp(self):
        d = int(self.game_hours // 24)
        h = int(self.game_hours % 24)
        m = int((self.game_hours * 60) % 60)
        return f"D{d:02d} {h:02d}:{m:02d}"

    def get_committee_state(self):
        factions = {}
        for unit in self.units.values():
            rec = factions.setdefault(unit.faction, {
                "faction": unit.faction,
                "units": 0,
                "active_personnel": 0,
                "average_morale": 0.0,
                "average_supply": 0.0,
                "visible_losses": 0,
                "operational_installations": 0,
                "construction_sites": 0,
                "destroyed_installations": 0,
            })
            rec["units"] += 1
            rec["active_personnel"] += int(max(0, unit.personnel))
            rec["average_morale"] += getattr(unit, "morale", 0.0)
            rec["average_supply"] += unit.supply
            if unit.personnel <= 0:
                rec["visible_losses"] += 1

        for installation in self.installations.values():
            rec = factions.setdefault(installation.faction, {
                "faction": installation.faction,
                "units": 0,
                "active_personnel": 0,
                "average_morale": 0.0,
                "average_supply": 0.0,
                "visible_losses": 0,
                "operational_installations": 0,
                "construction_sites": 0,
                "destroyed_installations": 0,
            })
            if installation.status == "OPERATIONAL":
                rec["operational_installations"] += 1
            elif installation.status == "UNDER_CONSTRUCTION":
                rec["construction_sites"] += 1
            else:
                rec["destroyed_installations"] += 1

        for rec in factions.values():
            unit_count = max(1, rec["units"])
            rec["average_morale"] = round(rec["average_morale"] / unit_count, 1)
            rec["average_supply"] = round(rec["average_supply"] / unit_count, 1)

        public_records = [r for r in self.committee_records if r.get("public", True)]
        return {
            "status": "ok",
            "scenario": self.scenario_data.get("scenario_name", "Unknown"),
            "committee": self.committee_config,
            "game_time": self._committee_timestamp(),
            "factions": sorted(factions.values(), key=lambda r: r["faction"]),
            "public_records": public_records[-int(self.rules["state_limits"]["public_sitrep_records"]):],
            "staff_records": self.committee_records[-int(self.rules["state_limits"]["staff_sitrep_records"]):]
        }

    def adjudicate_directive(self, data):
        if not isinstance(data, dict):
            raise ValueError("Directive must be a JSON object")
        directive_rules = self.rules["directives"]
        resources = self.rules["resources"]
        default_title = directive_rules["default_title"]
        default_faction = directive_rules["default_faction"]
        title = str(data.get("title", default_title)).strip() or default_title
        body = str(data.get("body", "")).strip()
        faction = str(data.get("faction", default_faction)).strip() or default_faction
        effect_type = str(data.get("effect_type", "none")).strip().lower()
        value = float(data.get("value", 0.0) or 0.0)
        duration = float(data.get("duration_hours", directive_rules["default_duration_hours"]) or directive_rules["default_duration_hours"])
        public_value = data.get("public", True)
        if not isinstance(public_value, bool):
            raise ValueError("Directive visibility must be true or false")
        public = public_value
        allowed_effects = set(directive_rules["allowed_effects"])
        if effect_type not in allowed_effects:
            raise ValueError(f"Unsupported directive effect [{effect_type}]")
        if not math.isfinite(value):
            raise ValueError("Directive value must be finite")
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Directive duration must be greater than zero")
        if effect_type in {"combat_modifier", "speed_modifier"} and value < 0:
            raise ValueError("Directive multipliers cannot be negative")

        affected = 0
        for unit in self.units.values():
            if faction != default_faction and unit.faction != faction:
                continue
            if effect_type == "morale":
                unit.morale = self._clamp(unit.morale + value, float(resources["minimum"]), unit.max_org)
                affected += 1
            elif effect_type == "supply":
                unit.supply = self._clamp(unit.supply + value, float(resources["minimum"]), float(resources["maximum"]))
                affected += 1
            elif effect_type == "fatigue":
                unit.fatigue = self._clamp(unit.fatigue + value, float(resources["minimum"]), float(resources["maximum"]))
                affected += 1
            elif effect_type in ["combat_modifier", "speed_modifier"]:
                mod_type = "combat" if effect_type == "combat_modifier" else "speed"
                unit.modifiers.append({
                    "name": title,
                    "type": mod_type,
                    "value": value,
                    "duration": duration
                })
                affected += 1

        record = {
            "timestamp": self._committee_timestamp(),
            "title": title,
            "body": body,
            "faction": faction,
            "effect_type": effect_type,
            "value": value,
            "duration_hours": duration,
            "affected_units": affected,
            "public": public
        }
        self.committee_records.append(record)
        self.committee_records = self.committee_records[-int(self.rules["state_limits"]["committee_records"]):]

        visibility = "Public" if public else "Staff-only"
        self.log_event(f"[{visibility} Crisis Update] {title} ({faction}, {affected} units affected)", faction="COMMITTEE", msg_type="system")
        return record

    def build_sitrep_markdown(self, include_private=False):
        state = self.get_committee_state()
        lines = [
            f"# {state['committee'].get('committee_name', state['scenario'])} SITREP",
            f"Time: {state['game_time']}",
            "",
            "## Faction Status"
        ]
        for rec in state["factions"]:
            lines.append(
                f"- {rec['faction']}: {rec['active_personnel']} living personnel, "
                f"{rec['units']} units, morale {rec['average_morale']}%, supply {rec['average_supply']}%; "
                f"military sites {rec['operational_installations']} operational, "
                f"{rec['construction_sites']} under construction, "
                f"{rec['destroyed_installations']} destroyed"
            )
        lines.extend(["", "## Crisis Updates"])
        records = state["staff_records"] if include_private else state["public_records"]
        if not records:
            lines.append("- No adjudicated committee updates yet.")
        for rec in records:
            visibility = "public" if rec.get("public", True) else "staff-only"
            lines.append(f"- {rec['timestamp']} [{visibility}] {rec['title']}: {rec.get('body', '')}")
        return "\n".join(lines) + "\n"

    def _is_detected_by(self, observer_faction, target_id):
        record = self.detected_units.get(target_id)
        if record is None:
            return False
        if isinstance(record, (int, float)):
            return record > 0
        factions = record.get("factions", [])
        return any(self.is_allied(observer_faction, spotting_faction) for spotting_faction in factions)

    @staticmethod
    def _route_segment_distance_km(point_lon, point_lat, start, end):
        """Approximate the shortest surface distance from a point to a route segment."""
        start_lon, start_lat = start
        end_lon, end_lat = end
        reference_latitude = math.radians((point_lat + start_lat + end_lat) / 3.0)
        km_per_lon_degree = 111.320 * max(0.01, abs(math.cos(reference_latitude)))
        km_per_lat_degree = 110.574
        start_x = (start_lon - point_lon) * km_per_lon_degree
        start_y = (start_lat - point_lat) * km_per_lat_degree
        end_x = (end_lon - point_lon) * km_per_lon_degree
        end_y = (end_lat - point_lat) * km_per_lat_degree
        delta_x = end_x - start_x
        delta_y = end_y - start_y
        segment_length_squared = delta_x * delta_x + delta_y * delta_y
        if segment_length_squared <= 1e-12:
            return math.hypot(start_x, start_y)
        projection = -((start_x * delta_x) + (start_y * delta_y)) / segment_length_squared
        projection = max(0.0, min(1.0, projection))
        closest_x = start_x + projection * delta_x
        closest_y = start_y + projection * delta_y
        return math.hypot(closest_x, closest_y)

    def _relocation_threat_zones(self, unit):
        orders = self.rules["orders"]
        contact_distance = float(
            self.rules["combat"]["direct"]["minimum_engagement_distance_km"]
        )
        safety_margin = float(orders["relocate_avoidance_margin_km"])
        cost_multiplier = float(orders["relocate_avoidance_cost_multiplier"])
        airborne_statuses = {"AIRSTRIKE_OUTBOUND", "AIRSTRIKE_RTB"}
        zones = []
        for hostile in self.units.values():
            if (
                hostile.id == unit.id
                or hostile.personnel <= 0
                or hostile.status in airborne_statuses
                or self.is_allied(unit.faction, hostile.faction)
                or not self._is_detected_by(unit.faction, hostile.id)
            ):
                continue
            hostile_profile = self.rules["unit_types"][hostile.unit_type]
            weapon_reach = (
                float(hostile.direct_fire_range)
                if hostile_profile["can_direct_combat"]
                else 0.0
            )
            radius_km = (
                float(unit.radius)
                + float(hostile.radius)
                + max(contact_distance, weapon_reach)
                + safety_margin
            )
            zones.append({
                "id": hostile.id,
                "name": hostile.name,
                "lon": float(hostile.lon),
                "lat": float(hostile.lat),
                "radius_km": radius_km,
                "cost_multiplier": cost_multiplier,
            })
        return zones

    def _remaining_route_intersects_zone(self, unit, zone):
        points = [(float(unit.lon), float(unit.lat))] + [
            (float(waypoint[0]), float(waypoint[1]))
            for waypoint in unit.waypoints
        ]
        return any(
            self._route_segment_distance_km(
                float(zone["lon"]),
                float(zone["lat"]),
                start,
                end,
            ) <= float(zone["radius_km"])
            for start, end in zip(points, points[1:])
        )

    def _relocation_threat_signature(self, zones):
        records = []
        for zone in zones:
            if hasattr(self.map_engine, "lonlat_to_grid"):
                position = self.map_engine.lonlat_to_grid(zone["lon"], zone["lat"])
            else:
                position = (round(zone["lon"], 3), round(zone["lat"], 3))
            records.append((zone["id"], position, round(zone["radius_km"], 1)))
        return tuple(sorted(records, key=lambda record: record[0]))

    def refresh_relocation_route(self, unit, force=False):
        """Replace a Relocate route when a detected hostile threatens its path."""
        orders = self.rules["orders"]
        if (
            not orders["relocate_avoids_detected_contact"]
            or unit.status != "MOVING"
            or not unit.has_order_role("relocate")
            or not unit.waypoints
            or unit.target_lon is None
            or unit.target_lat is None
        ):
            return False

        zones = self._relocation_threat_zones(unit)
        blocking_zones = [
            zone for zone in zones
            if self._remaining_route_intersects_zone(unit, zone)
        ]
        if not blocking_zones:
            return False

        signature = self._relocation_threat_signature(zones)
        previous_signature = getattr(unit, "_relocation_avoidance_signature", None)
        last_reroute_hour = float(
            getattr(unit, "_relocation_last_reroute_hour", -math.inf)
        )
        cooldown = float(orders["relocate_reroute_cooldown_hours"])
        if not force:
            if signature == previous_signature:
                return False
            if self.game_hours - last_reroute_hour < cooldown:
                return False

        destination = (float(unit.target_lon), float(unit.target_lat))
        route = self.map_engine.find_path(
            start_lon=unit.lon,
            start_lat=unit.lat,
            target_lon=destination[0],
            target_lat=destination[1],
            unit_composition=unit.composition,
            unit_capabilities=unit.get_capabilities(),
            avoidance_zones=zones,
        )
        parsed_route = []
        for point in route if isinstance(route, list) else []:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                continue
            try:
                lon, lat = float(point[0]), float(point[1])
            except (TypeError, ValueError):
                continue
            if math.isfinite(lon) and math.isfinite(lat):
                parsed_route.append((lon, lat))
        arrival_distance = float(self.rules["movement"]["arrival_distance_km"])
        while parsed_route and haversine_distance(
            unit.lon, unit.lat, parsed_route[0][0], parsed_route[0][1]
        ) < arrival_distance:
            parsed_route.pop(0)
        if not parsed_route:
            parsed_route = [destination]
        elif parsed_route[-1] != destination:
            parsed_route.append(destination)

        unit.waypoints = parsed_route
        unit.relocation_avoidance_contacts = [
            {
                "id": zone["id"],
                "name": zone["name"],
                "radius_km": round(float(zone["radius_km"]), 2),
            }
            for zone in zones
        ]
        unit.relocation_reroute_count = int(
            getattr(unit, "relocation_reroute_count", 0)
        ) + 1
        unit._relocation_avoidance_signature = signature
        unit._relocation_last_reroute_hour = float(self.game_hours)
        blocker_names = ", ".join(zone["name"] for zone in blocking_zones[:3])
        if len(blocking_zones) > 3:
            blocker_names += f" and {len(blocking_zones) - 3} more"
        self.log_event(
            f"🧭 [Contact Avoidance] {unit.name} rerouted around {blocker_names} "
            f"while retaining its original destination.",
            faction=unit.faction,
            msg_type="move",
        )
        return True

    def _is_installation_detected_by(self, observer_faction, target_id):
        record = self.detected_installations.get(target_id)
        if record is None:
            return False
        if isinstance(record, (int, float)):
            return record > 0
        factions = record.get("factions", [])
        return any(
            self.is_allied(observer_faction, spotting_faction)
            for spotting_faction in factions
        )

    def _record_detection(self, collection, target_id, observer_faction):
        record = collection.get(target_id)
        new_contact = record is None or (
            isinstance(record, dict)
            and observer_faction not in record.get("factions", [])
        )
        if not isinstance(record, dict):
            record = {"ttl": 0.0, "factions": []}
        if observer_faction not in record["factions"]:
            record["factions"].append(observer_faction)
        record["ttl"] = max(
            float(record.get("ttl", 0.0)),
            float(self.rules["detection"]["contact_ttl_hours"]),
        )
        collection[target_id] = record
        return new_contact

    def get_unit_visibility(self, unit):
        rules = self.rules["detection"]
        base_vis = max(
            float(rules["base_visibility_minimum"]),
            math.sqrt(max(unit.personnel, 1.0) / float(rules["personnel_reference"])),
        )
        stance_mod = float(self.rules["stances"][unit.stance]["visibility_multiplier"])
        status_mod = float(
            rules["status_visibility_multipliers"].get(
                unit.status,
                rules["default_status_visibility_multiplier"],
            )
        )
        tc = self.get_terrain_complexity(unit.lon, unit.lat)
        terrain_hide_factor = max(
            float(rules["terrain_hide_minimum"]),
            1.0 - tc * float(rules["terrain_hide_strength"]),
        )
        return max(
            float(rules["final_visibility_minimum"]),
            base_vis * stance_mod * status_mod * terrain_hide_factor,
        )

    def get_unit_recon_power(self, observer):
        profile = self.rules["unit_types"][observer.unit_type]
        recon_score = float(profile["detection"]["base_recon"])
        recon_score += sum(
            float(observer.battalion_registry[battalion_id]["recon_power"]) * count
            for battalion_id, count in observer.composition.items()
        )
        recon_score *= float(self.rules["stances"][observer.stance]["recon_multiplier"])
        return max(float(self.rules["detection"]["minimum_recon_power"]), recon_score * observer.equipment_level)

    def _try_detect(self, observer, target, edge_dist, dt):
        observer_profile = self.rules["unit_types"][observer.unit_type]
        target_profile = self.rules["unit_types"][target.unit_type]
        detection = self.rules["detection"]
        max_range = float(observer_profile["detection"]["max_range_km"])
        if edge_dist > max_range: 
            return 
            
        if observer_profile["detection"]["requires_line_of_sight"] and target_profile["detection"]["requires_line_of_sight"]:
            if not self.map_engine.check_line_of_sight(observer.lon, observer.lat, target.lon, target.lat):
                return
            
        recon = self.get_unit_recon_power(observer)
        visibility = self.get_unit_visibility(target)
        safe_dist = max(float(detection["minimum_distance_km"]), edge_dist)
        
        prob = (
            (recon * visibility)
            / (safe_dist ** float(detection["distance_exponent"]))
            * dt
            * float(detection["probability_scale"])
        )
        
        if random.random() < prob:
            new_contact = self._record_detection(
                self.detected_units, target.id, observer.faction
            )
            if new_contact:
                if float(self.rules["stances"][target.stance]["visibility_multiplier"]) < 1.0:
                    self.log_event(f"👁️ [Intel] {observer.name} saw through concealment and acquired {target.name}.", faction=observer.faction)
                else:
                    self.log_event(f"📡 [Contact] {observer.name}'s vanguard radar detected the outline of {target.name}.", faction=observer.faction)
    def _try_detect_installation(self, observer, installation, edge_dist, dt):
        if installation.status == "DESTROYED":
            return
        observer_profile = self.rules["unit_types"][observer.unit_type]
        detection = self.rules["detection"]
        maximum_range = float(observer_profile["detection"]["max_range_km"])
        if edge_dist > maximum_range:
            return
        if observer_profile["detection"]["requires_line_of_sight"]:
            if not self.map_engine.check_line_of_sight(
                observer.lon, observer.lat, installation.lon, installation.lat
            ):
                return
        recon = self.get_unit_recon_power(observer)
        construction_visibility = max(0.25, installation.construction_progress)
        visibility = float(installation.profile["visibility"]) * construction_visibility
        safe_distance = max(float(detection["minimum_distance_km"]), edge_dist)
        probability = (
            recon
            * visibility
            / (safe_distance ** float(detection["distance_exponent"]))
            * dt
            * float(detection["probability_scale"])
        )
        if random.random() < probability:
            if self._record_detection(
                self.detected_installations, installation.id, observer.faction
            ):
                self.log_event(
                    f"📍 [Military Target Located] {observer.name} identified "
                    f"{installation.name} ({installation.profile['label']}).",
                    faction=observer.faction,
                    msg_type="system",
                )

    def _radar_detection_tick(self, dt):
        if dt <= 0:
            return
        for radar in self.installations.values():
            if not radar.is_operational or float(radar.profile["radar_range_km"]) <= 0:
                continue
            radar_range = float(radar.profile["radar_range_km"])
            radar_power = float(radar.profile["radar_recon_power"])
            base_rate = float(radar.profile["radar_detection_probability_per_hour"])
            requires_los = bool(radar.profile["radar_requires_line_of_sight"])

            def radar_acquires(target_lon, target_lat, target_radius, visibility):
                edge_distance = max(
                    0.0,
                    haversine_distance(radar.lon, radar.lat, target_lon, target_lat)
                    - float(radar.profile["radius_km"])
                    - target_radius,
                )
                if edge_distance > radar_range:
                    return False
                if requires_los and not self.map_engine.check_line_of_sight(
                    radar.lon, radar.lat, target_lon, target_lat
                ):
                    return False
                range_factor = max(0.1, 1.0 - edge_distance / radar_range)
                power_factor = self._clamp(radar_power / 10.0, 0.25, 2.0)
                rate = base_rate * range_factor * power_factor * max(0.1, visibility)
                return random.random() < 1.0 - math.exp(-rate * dt)

            for target in self.units.values():
                if target.personnel <= 0 or self.is_allied(radar.faction, target.faction):
                    continue
                if radar_acquires(
                    target.lon,
                    target.lat,
                    target.radius,
                    self.get_unit_visibility(target),
                ):
                    if self._record_detection(
                        self.detected_units, target.id, radar.faction
                    ):
                        self.log_event(
                            f"📡 [Radar Contact] {radar.name} acquired {target.name}.",
                            faction=radar.faction,
                            msg_type="system",
                        )
            for target in self.installations.values():
                if (
                    target.id == radar.id
                    or target.status == "DESTROYED"
                    or self.is_allied(radar.faction, target.faction)
                ):
                    continue
                visibility = float(target.profile["visibility"]) * max(
                    0.25, target.construction_progress
                )
                if radar_acquires(
                    target.lon, target.lat, float(target.profile["radius_km"]), visibility
                ):
                    if self._record_detection(
                        self.detected_installations, target.id, radar.faction
                    ):
                        self.log_event(
                            f"📡 [Radar Target] {radar.name} located {target.name}.",
                            faction=radar.faction,
                            msg_type="system",
                        )

    def detection_tick(self, dt):
        for uid in list(self.detected_units.keys()):
            record = self.detected_units[uid]
            if isinstance(record, dict):
                record["ttl"] = record.get("ttl", 0.0) - dt
                expired = record["ttl"] <= 0
            else:
                self.detected_units[uid] -= dt
                expired = self.detected_units[uid] <= 0
            if expired:
                del self.detected_units[uid]
                # Routine sensor-track expiry is normal and should not flood the
                # theater feed. Report disappearance only after the formation
                # has no personnel left.
                if uid in self.units and self.units[uid].personnel <= 0:
                    self.log_event(f"🌫️ [Contact Lost] {self.units[uid].name} vanished into the fog of war.", faction="SYSTEM", msg_type="system")

        for installation_id in list(self.detected_installations.keys()):
            record = self.detected_installations[installation_id]
            if isinstance(record, dict):
                record["ttl"] = float(record.get("ttl", 0.0)) - dt
                expired = record["ttl"] <= 0
            else:
                self.detected_installations[installation_id] -= dt
                expired = self.detected_installations[installation_id] <= 0
            if expired:
                del self.detected_installations[installation_id]

        ulist = list(self.units.values())
        for i in range(len(ulist)):
            for j in range(i + 1, len(ulist)):
                u1, u2 = ulist[i], ulist[j]
                if self.is_allied(u1.faction, u2.faction) or u1.personnel <= 0 or u2.personnel <= 0:
                    continue
                
                # Edge distance calculation
                center_dist = haversine_distance(u1.lon, u1.lat, u2.lon, u2.lat)
                edge_dist = max(0.0, center_dist - u1.radius - u2.radius)
                
                self._try_detect(u1, u2, edge_dist, dt)
                self._try_detect(u2, u1, edge_dist, dt)

        for observer in self.units.values():
            if observer.personnel <= 0:
                continue
            for installation in self.installations.values():
                if self.is_allied(observer.faction, installation.faction):
                    continue
                edge_dist = max(
                    0.0,
                    haversine_distance(
                        observer.lon, observer.lat, installation.lon, installation.lat
                    )
                    - observer.radius
                    - float(installation.profile["radius_km"]),
                )
                self._try_detect_installation(observer, installation, edge_dist, dt)

        self._radar_detection_tick(dt)

    def is_crossing_river(self, u1, u2):
        if getattr(self.map_engine, 'river_matrix', None) is None: 
            return False
            
        steps = int(self.rules["combat"]["direct"]["river_probe_steps"])
        for i in range(1, steps):
            ratio = i / steps
            slon = u1.lon + (u2.lon - u1.lon) * ratio
            slat = u1.lat + (u2.lat - u1.lat) * ratio
            
            x, y = self.map_engine.lonlat_to_grid(slon, slat)
            if self.map_engine.river_matrix[y][x] == 1:
                return True
        return False

    def tactical_aura_tick(self, dt):
        support = self.rules["tactical_support"]
        for u in self.units.values():
            u.dynamic_eq_modifier = 1.0

        ulist = list(self.units.values())
        for i in range(len(ulist)):
            for j in range(i + 1, len(ulist)):
                u1, u2 = ulist[i], ulist[j]
                
                center_dist = haversine_distance(u1.lon, u1.lat, u2.lon, u2.lat)
                edge_dist = max(0.0, center_dist - u1.radius - u2.radius)
                
                if self.is_allied(u1.faction, u2.faction) and edge_dist <= float(support["range_km"]):
                    if u1.has_capability(support["capability"]) and u1.equipment_level >= float(support["minimum_equipment_level"]):
                        u2.dynamic_eq_modifier = max(u2.dynamic_eq_modifier, float(support["equipment_multiplier"]))
                    if u2.has_capability(support["capability"]) and u2.equipment_level >= float(support["minimum_equipment_level"]):
                        u1.dynamic_eq_modifier = max(u1.dynamic_eq_modifier, float(support["equipment_multiplier"]))

        for u in self.units.values():
            u.parse_composition()

    def _collect_province_force_presence(self):
        """Return physical and occupation-eligible forces at their live coordinates."""
        rules = self.rules["political_influence"]
        physical_presence = {}
        occupation_presence = {}
        for u in self.units.values():
            if u.personnel <= 0:
                continue
            # Never trust the cached province here. Paused simulations, restored
            # saves, chair edits, and boundary crossings can all make it stale.
            prov = str(self.prov_engine.get_province(u.lon, u.lat) or "Unknown")
            u.current_province = prov
            if prov in rules["excluded_province_names"] or any(prov.startswith(prefix) for prefix in rules["excluded_province_prefixes"]):
                continue
            faction_weight = float(rules["faction_weights"].get(u.faction, rules["default_faction_weight"]))
            if faction_weight <= 0:
                continue
            stance_weight = float(self.rules["stances"][u.stance]["political_presence_multiplier"])
            weight = u.personnel * u.equipment_level * stance_weight * faction_weight
            factions = physical_presence.setdefault(prov, {})
            factions[u.faction] = factions.get(u.faction, 0.0) + weight
            if u.status not in rules["excluded_statuses"]:
                eligible = occupation_presence.setdefault(prov, {})
                eligible[u.faction] = eligible.get(u.faction, 0.0) + weight

        return physical_presence, occupation_presence

    def _update_province_politics(self, dt, evolve_occupation):
        rules = self.rules["political_influence"]
        if not rules["enabled"]:
            return
        physical_presence, occupation_presence = self._collect_province_force_presence()

        all_provinces = set(self.province_politics) | set(physical_presence) | set(occupation_presence)
        reference = float(rules["personnel_reference"])
        gain_rate = float(rules["occupation_gain_per_hour"])
        decay_rate = float(rules["occupation_decay_per_hour"])
        for province in all_provinces:
            state = self.province_politics.setdefault(province, {
                "factions": {}, "controller": None, "contested": False,
            })
            raw_physical = physical_presence.get(province, {})
            raw_occupation = occupation_presence.get(province, {})
            for faction in set(raw_physical) | set(raw_occupation):
                state["factions"].setdefault(faction, self._default_political_record())

            total_physical = sum(raw_physical.values())
            total_occupation = sum(raw_occupation.values())
            for faction, record in state["factions"].items():
                faction_force = raw_physical.get(faction, 0.0)
                presence_share = faction_force / total_physical if total_physical > 0 else 0.0
                force_strength = min(1.0, faction_force / reference)
                record["military_presence"] = presence_share
                record["force_strength"] = force_strength

                if evolve_occupation:
                    eligible_force = raw_occupation.get(faction, 0.0)
                    target_occupation = eligible_force / total_occupation if total_occupation > 0 else 0.0
                    occupation = float(record.get("occupation", 0.0))
                    if target_occupation > occupation:
                        occupation += min(
                            target_occupation - occupation,
                            gain_rate * min(1.0, eligible_force / reference) * dt,
                        )
                    elif target_occupation < occupation:
                        occupation -= min(
                            occupation - target_occupation,
                            decay_rate * dt,
                        )
                    record["occupation"] = self._clamp(occupation, 0.0, 1.0)

            self.recalculate_province_control(province)

    def refresh_province_presence(self):
        """Synchronize map politics immediately without advancing occupation time."""
        self._update_province_politics(0.0, evolve_occupation=False)

    def political_tick(self, dt):
        self._update_province_politics(dt, evolve_occupation=True)

    def get_installation_cover_bonus(self, target):
        bonus = 0.0
        for installation in self.installations.values():
            if not installation.is_operational or not self.is_allied(
                target.faction, installation.faction
            ):
                continue
            profile = installation.profile
            candidate = float(profile["fortification_cover_bonus"])
            if candidate <= 0:
                continue
            distance = max(
                0.0,
                haversine_distance(
                    target.lon, target.lat, installation.lon, installation.lat
                )
                - target.radius
                - float(profile["radius_km"]),
            )
            if distance <= float(profile["effect_radius_km"]):
                bonus = max(bonus, candidate)
        return bonus

    def _cover_multiplier(self, target, terrain_complexity, indirect=False):
        rules = self.rules["combat"]["cover"]
        stance = self.rules["stances"][target.stance]
        posture_cover = float(stance["base_cover"])
        if target.uses_prepared_defense():
            posture_cover += min(
                float(rules["entrenchment_cap"]),
                target.entrenchment * float(rules["entrenchment_effect"]),
            )
        if target.status == "MOVING":
            posture_cover += float(rules["moving_modifier"])
        posture_cover += self.get_installation_cover_bonus(target)

        terrain_effect = rules["terrain_indirect_effect"] if indirect else rules["terrain_direct_effect"]
        terrain_cover = min(float(rules["terrain_cap"]), terrain_complexity * float(terrain_effect))
        cover = self._clamp(posture_cover + terrain_cover, float(rules["cover_minimum"]), float(rules["cover_maximum"]))
        return self._clamp(
            1.0 - cover,
            float(rules["damage_multiplier_minimum"]),
            float(rules["damage_multiplier_maximum"]),
        )

    def _apply_combat_effects(self, target, casualties, org_loss, suppression):
        if casualties <= 0 and org_loss <= 0 and suppression <= 0:
            return
        resource_min = float(self.rules["resources"]["minimum"])
        resource_max = float(self.rules["resources"]["maximum"])
        target.personnel = max(0.0, target.personnel - casualties)
        if target.personnel > 0:
            target.morale = max(resource_min, target.morale - org_loss)
            target.suppression = min(resource_max, target.suppression + suppression)

    def _installation_terrain_damage_multiplier(self, installation):
        rules = self.rules["military_installations"]["damage"]
        terrain_complexity = self.get_terrain_complexity(
            installation.lon, installation.lat
        )
        terrain_cover = min(
            float(rules["terrain_cover_cap"]),
            terrain_complexity * float(rules["terrain_cover_effect"]),
        )
        return max(0.0, 1.0 - terrain_cover)

    def _resolve_installation_direct_fire(self, delta_time_hours):
        if delta_time_hours <= 0:
            return
        direct = self.rules["combat"]["direct"]
        damage_rules = self.rules["military_installations"]["damage"]
        contact_distance = float(direct["minimum_engagement_distance_km"])
        for attacker in self.units.values():
            unit_profile = self.rules["unit_types"][attacker.unit_type]
            if attacker.personnel <= 0 or not unit_profile["can_direct_combat"]:
                continue
            stance = self.rules["stances"][attacker.stance]
            for installation in self.installations.values():
                if installation.status == "DESTROYED" or self.is_allied(
                    attacker.faction, installation.faction
                ):
                    continue
                edge_distance = max(
                    0.0,
                    haversine_distance(
                        attacker.lon,
                        attacker.lat,
                        installation.lon,
                        installation.lat,
                    )
                    - attacker.radius
                    - float(installation.profile["radius_km"]),
                )
                if edge_distance > max(attacker.direct_fire_range, contact_distance):
                    continue
                has_contact = self._is_installation_detected_by(
                    attacker.faction, installation.id
                ) or edge_distance <= contact_distance
                if not has_contact:
                    continue
                order_role = attacker.order_role()
                movement_withholds_fire = (
                    order_role == "relocate"
                    and not self.rules["orders"]["relocate_allows_stance_fire"]
                ) or (
                    order_role == "route"
                    and not self.rules["orders"]["route_allows_stance_fire"]
                )
                if edge_distance > contact_distance and (
                    not stance["allows_ranged_fire"] or movement_withholds_fire
                ):
                    continue
                has_line_of_sight = self.map_engine.check_line_of_sight(
                    attacker.lon,
                    attacker.lat,
                    installation.lon,
                    installation.lat,
                )
                attack = attacker.calculate_weapon_attack(
                    edge_distance,
                    float(installation.profile["softness"]),
                    float(installation.profile["armor"]),
                    float(direct["failed_penetration_multiplier"]),
                    roles={"direct_fire"},
                    indirect_without_los_multiplier=float(
                        direct["indirect_without_los_multiplier"]
                    ),
                    has_line_of_sight=has_line_of_sight,
                )
                firepower = float(attack["effective_attack"])
                if firepower <= 0:
                    continue
                damage = (
                    firepower
                    * attacker.get_terrain_efficiency(
                        self.get_terrain_complexity(attacker.lon, attacker.lat)
                    )
                    * float(direct["attack_scale"])
                    * float(damage_rules["direct_integrity_coefficient"])
                    * float(installation.profile["direct_damage_multiplier"])
                    * self._installation_terrain_damage_multiplier(installation)
                    * delta_time_hours
                )
                self.apply_installation_damage(
                    installation, damage, attacker.name, "direct fire"
                )

    def resolve_airstrike_impact(self, aircraft):
        aircraft_profile = aircraft.get_airstrike_parameters()
        result = {
            "targets_hit": 0,
            "casualties": 0.0,
            "morale_loss": 0.0,
            "suppression": 0.0,
            "neutralized": 0,
            "exposed_personnel": 0.0,
            "casualty_cap_applied": 0,
            "installations_hit": 0,
            "installation_damage": 0.0,
            "installations_destroyed": 0,
            "aircraft_type": aircraft_profile["aircraft_type"],
            "aircraft_label": aircraft_profile["label"],
            "attack_profile": aircraft_profile["attack_profile"],
        }
        if aircraft.target_lon is None or aircraft.target_lat is None:
            return result

        airstrike = self.rules["missions"]["airstrike"]
        blast_radius = float(aircraft_profile["blast_radius_km"])
        airborne_statuses = {"AIRSTRIKE_OUTBOUND", "AIRSTRIKE_RTB"}
        for target in self.units.values():
            target_profile = self.rules["unit_types"][target.unit_type]
            if (
                target.personnel <= 0
                or target.status in airborne_statuses
                or not target_profile["can_be_airstrike_target"]
                or self.is_allied(aircraft.faction, target.faction)
            ):
                continue

            center_dist = haversine_distance(aircraft.target_lon, aircraft.target_lat, target.lon, target.lat)
            edge_dist = max(0.0, center_dist - target.radius)
            if edge_dist > blast_radius:
                continue

            tc = self.get_terrain_complexity(target.lon, target.lat)
            aim_factor = self._clamp(1.0 - (edge_dist / blast_radius), float(airstrike["minimum_aim_factor"]), 1.0)
            if not self._is_detected_by(aircraft.faction, target.id):
                # A coordinate strike still has physical effects without a live
                # contact, but incomplete observation is modified by both the
                # campaign baseline and the aircraft type's sensor/delivery fit.
                aim_factor *= min(
                    1.0,
                    float(airstrike["unobserved_accuracy_multiplier"])
                    * float(aircraft_profile["unobserved_targeting_multiplier"]),
                )
            cover = self._cover_multiplier(target, tc, indirect=True)
            # Aircrew and ground-staff headcount is not ordnance. Estimate how
            # much of the target formation lies inside the weapon-effect area,
            # then apply the selected DLC aircraft type's target specialization,
            # accuracy, and payload to those exposed troops.  The campaign-level
            # casualty ceiling prevents one sortie from erasing a formation.
            strike_attack = aircraft.calculate_weapon_attack(
                edge_dist,
                target.softness,
                target.armor,
                float(self.rules["combat"]["direct"]["failed_penetration_multiplier"]),
                roles={"airstrike"},
                soft_multiplier=float(aircraft_profile["soft_target_multiplier"]),
                hard_multiplier=float(aircraft_profile["hard_target_multiplier"]),
            )
            strike_power = float(strike_attack["effective_attack"])
            if strike_power <= 0:
                continue
            personnel_before = target.personnel
            formation_radius = max(float(target.radius), 0.001)
            exposure_fraction = min(1.0, (blast_radius / formation_radius) ** 2)
            exposed_personnel = personnel_before * exposure_fraction
            strike_factor = strike_power / float(airstrike["strike_power_reference"])
            uncapped_casualties = (
                exposed_personnel
                * strike_factor
                * aircraft.get_readiness()
                * float(airstrike["casualty_coefficient"])
                * aim_factor
                * cover
                * float(aircraft_profile["accuracy_multiplier"])
                * float(aircraft_profile["payload_multiplier"])
            )
            casualty_cap = personnel_before * float(airstrike["maximum_casualty_fraction"])
            casualties = min(uncapped_casualties, casualty_cap)
            morale_before = target.morale
            suppression_before = target.suppression
            actual_casualties = min(personnel_before, max(0.0, casualties))
            org_loss = (
                float(airstrike["organization_base"])
                + actual_casualties
                / max(personnel_before, 1.0)
                * float(airstrike["organization_casualty_multiplier"])
            ) * float(aircraft_profile["morale_shock_multiplier"])
            suppression = (
                float(airstrike["suppression"])
                * aim_factor
                * float(aircraft_profile["suppression_multiplier"])
            )
            self._apply_combat_effects(target, actual_casualties, org_loss, suppression)
            result["targets_hit"] += 1
            result["casualties"] += actual_casualties
            result["morale_loss"] += max(0.0, morale_before - target.morale)
            result["suppression"] += max(0.0, target.suppression - suppression_before)
            result["exposed_personnel"] += exposed_personnel
            if uncapped_casualties > casualty_cap:
                result["casualty_cap_applied"] += 1
            if personnel_before > 0 and target.personnel <= 0:
                result["neutralized"] += 1
                self.log_event(f"[Unit Neutralized] {target.name} was neutralized by an airstrike.", faction=target.faction, msg_type="combat")

        installation_damage = self.rules["military_installations"]["damage"]
        for installation in self.installations.values():
            if installation.status == "DESTROYED" or self.is_allied(
                aircraft.faction, installation.faction
            ):
                continue
            edge_dist = max(
                0.0,
                haversine_distance(
                    aircraft.target_lon,
                    aircraft.target_lat,
                    installation.lon,
                    installation.lat,
                )
                - float(installation.profile["radius_km"]),
            )
            if edge_dist > blast_radius:
                continue
            aim_factor = self._clamp(
                1.0 - edge_dist / blast_radius,
                float(airstrike["minimum_aim_factor"]),
                1.0,
            )
            if not self._is_installation_detected_by(
                aircraft.faction, installation.id
            ):
                aim_factor *= min(
                    1.0,
                    float(airstrike["unobserved_accuracy_multiplier"])
                    * float(aircraft_profile["unobserved_targeting_multiplier"]),
                )
            attack = aircraft.calculate_weapon_attack(
                edge_dist,
                float(installation.profile["softness"]),
                float(installation.profile["armor"]),
                float(self.rules["combat"]["direct"]["failed_penetration_multiplier"]),
                roles={"airstrike"},
                soft_multiplier=float(aircraft_profile["soft_target_multiplier"]),
                hard_multiplier=float(aircraft_profile["hard_target_multiplier"]),
            )
            firepower = float(attack["effective_attack"])
            if firepower <= 0:
                continue
            was_operational = installation.status != "DESTROYED"
            damage = (
                firepower
                * aircraft.get_readiness()
                * aim_factor
                * float(aircraft_profile["accuracy_multiplier"])
                * float(aircraft_profile["payload_multiplier"])
                * float(installation_damage["airstrike_integrity_coefficient"])
                * float(installation.profile["airstrike_damage_multiplier"])
                * self._installation_terrain_damage_multiplier(installation)
            )
            actual = self.apply_installation_damage(
                installation, damage, aircraft.name, "airstrike"
            )
            if actual > 0:
                result["installations_hit"] += 1
                result["installation_damage"] += actual
                if was_operational and installation.status == "DESTROYED":
                    result["installations_destroyed"] += 1

        return result

    def resolve_bombardment_tick(self, artillery, active_hours):
        """Apply coordinate-area fire for the supplied active mission time."""
        result = {
            "targets_hit": 0,
            "casualties": 0.0,
            "neutralized": 0,
            "firepower": 0.0,
            "installations_hit": 0,
            "installation_damage": 0.0,
            "installations_destroyed": 0,
        }
        if active_hours <= 0 or artillery.target_lon is None or artillery.target_lat is None:
            return result

        bombard = self.rules["missions"]["bombard"]
        blast_radius = float(bombard["blast_radius_km"])
        fire_distance = haversine_distance(
            artillery.lon,
            artillery.lat,
            artillery.target_lon,
            artillery.target_lat,
        )
        for target in self.units.values():
            if target.personnel <= 0 or self.is_allied(artillery.faction, target.faction):
                continue
            center_dist = haversine_distance(artillery.target_lon, artillery.target_lat, target.lon, target.lat)
            edge_dist = max(0.0, center_dist - target.radius)
            if edge_dist > blast_radius:
                continue

            tc = self.get_terrain_complexity(target.lon, target.lat)
            aim_factor = self._clamp(
                1.0 - (edge_dist / blast_radius),
                float(bombard["minimum_aim_factor"]),
                1.0,
            )
            if not self._is_detected_by(artillery.faction, target.id):
                aim_factor *= float(bombard["unobserved_accuracy_multiplier"])
            cover = self._cover_multiplier(target, tc, indirect=True)
            attack = artillery.calculate_weapon_attack(
                fire_distance,
                target.softness,
                target.armor,
                float(self.rules["combat"]["direct"]["failed_penetration_multiplier"]),
                roles={"bombard"},
                require_indirect=True,
            )
            firepower = float(attack["effective_attack"])
            if firepower <= 0:
                continue
            casualties = (
                artillery.get_terrain_efficiency(tc)
                * float(bombard["terrain_efficiency_multiplier"])
                * firepower
                * artillery.get_readiness()
                * active_hours
                * float(bombard["casualty_coefficient"])
                * aim_factor
                * cover
            )
            personnel_before = target.personnel
            actual_casualties = min(personnel_before, max(0.0, casualties))
            org_loss = (
                float(bombard["organization_base_per_hour"]) * active_hours * aim_factor
                + (actual_casualties / max(personnel_before, 1.0)) * float(bombard["organization_casualty_multiplier"])
            )
            self._apply_combat_effects(
                target,
                actual_casualties,
                org_loss,
                float(bombard["suppression_per_hour"]) * active_hours * aim_factor,
            )
            result["targets_hit"] += 1
            result["casualties"] += actual_casualties
            result["firepower"] += firepower
            artillery.bombard_casualties += actual_casualties
            if personnel_before > 0 and target.personnel <= 0:
                result["neutralized"] += 1
                self.log_event(f"[Unit Neutralized] {target.name} was neutralized by bombardment.", faction=target.faction, msg_type="combat")

        installation_damage = self.rules["military_installations"]["damage"]
        for installation in self.installations.values():
            if installation.status == "DESTROYED" or self.is_allied(
                artillery.faction, installation.faction
            ):
                continue
            edge_dist = max(
                0.0,
                haversine_distance(
                    artillery.target_lon,
                    artillery.target_lat,
                    installation.lon,
                    installation.lat,
                )
                - float(installation.profile["radius_km"]),
            )
            if edge_dist > blast_radius:
                continue
            aim_factor = self._clamp(
                1.0 - edge_dist / blast_radius,
                float(bombard["minimum_aim_factor"]),
                1.0,
            )
            if not self._is_installation_detected_by(
                artillery.faction, installation.id
            ):
                aim_factor *= float(bombard["unobserved_accuracy_multiplier"])
            attack = artillery.calculate_weapon_attack(
                fire_distance,
                float(installation.profile["softness"]),
                float(installation.profile["armor"]),
                float(self.rules["combat"]["direct"]["failed_penetration_multiplier"]),
                roles={"bombard"},
                require_indirect=True,
            )
            firepower = float(attack["effective_attack"])
            if firepower <= 0:
                continue
            was_operational = installation.status != "DESTROYED"
            damage = (
                artillery.get_terrain_efficiency(
                    self.get_terrain_complexity(installation.lon, installation.lat)
                )
                * firepower
                * artillery.get_readiness()
                * active_hours
                * aim_factor
                * float(installation_damage["bombard_integrity_coefficient"])
                * float(installation.profile["bombard_damage_multiplier"])
                * self._installation_terrain_damage_multiplier(installation)
            )
            actual = self.apply_installation_damage(
                installation, damage, artillery.name, "bombardment"
            )
            if actual > 0:
                result["installations_hit"] += 1
                result["installation_damage"] += actual
                result["firepower"] += firepower
                artillery.bombard_installation_damage += actual
                if was_operational and installation.status == "DESTROYED":
                    result["installations_destroyed"] += 1
                    artillery.bombard_installations_destroyed += 1

        return result

    def _finish_bombardment(self, artillery, reason):
        effect_parts = []
        if artillery.bombard_casualties > 0:
            effect_parts.append(f"estimated casualties {artillery.bombard_casualties:.0f}")
        if artillery.bombard_installation_damage > 0:
            effect_parts.append(
                f"military-target integrity damage {artillery.bombard_installation_damage:.0f}"
            )
        if artillery.bombard_installations_destroyed > 0:
            effect_parts.append(
                f"installations destroyed {artillery.bombard_installations_destroyed}"
            )
        effects = "; ".join(effect_parts) if effect_parts else "no hostile target affected"
        self.log_event(
            f"🛑 [Fire Mission] {artillery.name} ceased fire: {reason}; {effects}.",
            faction=artillery.faction,
            msg_type="combat",
        )
        artillery.status = "IDLE" if artillery.personnel > 0 else "NEUTRALIZED"
        artillery.waypoints = []
        artillery.target_lon = artillery.target_lat = None
        artillery.base_lon = artillery.base_lat = None
        artillery.set_order_role("hold")
        artillery.bombard_casualties = 0.0
        artillery.bombard_installation_damage = 0.0
        artillery.bombard_installations_destroyed = 0
        for attribute in ("bombard_timer", "_bombard_effective_hours", "_bombard_completion_reason"):
            if hasattr(artillery, attribute):
                delattr(artillery, attribute)

    def combat_tick(self, delta_time_hours):
        self.detection_tick(delta_time_hours)
        close_engagements_now = set()

        for u in self.units.values():
            if u.status != "BOMBARDING":
                continue
            if u.personnel <= 0:
                self._finish_bombardment(u, "firing unit neutralized")
                continue
            active_hours = float(getattr(u, "_bombard_effective_hours", delta_time_hours))
            self.resolve_bombardment_tick(u, active_hours)
            if hasattr(u, "_bombard_effective_hours"):
                delattr(u, "_bombard_effective_hours")
            completion_reason = getattr(u, "_bombard_completion_reason", None)
            if completion_reason:
                self._finish_bombardment(u, completion_reason)
        unit_list = list(self.units.values())
        for i in range(len(unit_list)):
            for j in range(i + 1, len(unit_list)):
                u1 = unit_list[i]
                u2 = unit_list[j]
                direct = self.rules["combat"]["direct"]
                profile1 = self.rules["unit_types"][u1.unit_type]
                profile2 = self.rules["unit_types"][u2.unit_type]
                stance1 = self.rules["stances"][u1.stance]
                stance2 = self.rules["stances"][u2.stance]
                contact_distance = float(direct["minimum_engagement_distance_km"])
                
                if self.is_allied(u1.faction, u2.faction) or u1.personnel <= 0 or u2.personnel <= 0: 
                    continue
                # Sorties use the dedicated airstrike-impact and air-defense
                # systems. Treating an aircraft marker as a ground formation
                # caused implausible personnel and morale attrition in transit.
                airborne_statuses = {"AIRSTRIKE_OUTBOUND", "AIRSTRIKE_RTB"}
                if u1.status in airborne_statuses or u2.status in airborne_statuses:
                    continue
                    
                center_dist = haversine_distance(u1.lon, u1.lat, u2.lon, u2.lat)
                edge_dist = max(0.0, center_dist - u1.radius - u2.radius)
                
                max_engage_dist = max(u1.direct_fire_range, u2.direct_fire_range, contact_distance)
                if edge_dist > max_engage_dist:
                    continue

                u1_can_see = self._is_detected_by(u1.faction, u2.id)
                u2_can_see = self._is_detected_by(u2.faction, u1.id)
                close_contact = edge_dist <= contact_distance
                
                # 🏔️ 3D Physics: Detect real mountain blockage between two points
                has_los = self.map_engine.check_line_of_sight(u1.lon, u1.lat, u2.lon, u2.lat)
                # Once formation footprints meet, both sides necessarily know
                # about the immediate threat. Previously close-contact
                # self-defense was enabled below, but its attack multiplier was
                # still zero when the probabilistic detection tick had not yet
                # succeeded. The result was overlapping hostile markers that
                # exchanged no fire.
                if close_contact:
                    self._record_detection(
                        self.detected_units, u2.id, u1.faction
                    )
                    self._record_detection(
                        self.detected_units, u1.id, u2.faction
                    )
                    u1_can_see = True
                    u2_can_see = True
                effective_los = has_los or close_contact
                
                u1_has_indirect_at_range = u1.get_max_weapon_range({"direct_fire"}, require_indirect=True) >= edge_dist
                u2_has_indirect_at_range = u2.get_max_weapon_range({"direct_fire"}, require_indirect=True) >= edge_dist

                if not effective_los and not u1_has_indirect_at_range and not u2_has_indirect_at_range:
                    continue

                if not u1_can_see and not u2_can_see and not close_contact:
                    continue 
                    
                order_rules = self.rules["orders"]
                stationary_statuses = {
                    "IDLE",
                    order_rules["defending_status"],
                    order_rules["fortifying_status"],
                }

                def order_allows_ranged_fire(unit):
                    if unit.status in stationary_statuses:
                        return True
                    if unit.has_order_role("assault"):
                        return True
                    if unit.has_order_role("relocate"):
                        return order_rules["relocate_allows_stance_fire"]
                    if unit.has_order_role("route"):
                        return order_rules["route_allows_stance_fire"]
                    return False

                tc = self.get_terrain_complexity(u1.lon, u1.lat)
                cw = max(
                    float(direct["frontage_minimum_personnel"]),
                    float(direct["frontage_maximum_personnel"]) - tc * float(direct["frontage_terrain_reduction"]),
                )
                eff_p1 = u1.personnel if profile1["uncapped_frontage"] else min(u1.personnel, cw)
                eff_p2 = u2.personnel if profile2["uncapped_frontage"] else min(u2.personnel, cw)

                attack_profile1 = u1.calculate_weapon_attack(
                    edge_dist,
                    u2.softness,
                    u2.armor,
                    float(direct["failed_penetration_multiplier"]),
                    roles={"direct_fire"},
                    indirect_without_los_multiplier=float(direct["indirect_without_los_multiplier"]),
                    has_line_of_sight=effective_los,
                    engaged_personnel=eff_p1,
                )
                attack_profile2 = u2.calculate_weapon_attack(
                    edge_dist,
                    u1.softness,
                    u1.armor,
                    float(direct["failed_penetration_multiplier"]),
                    roles={"direct_fire"},
                    indirect_without_los_multiplier=float(direct["indirect_without_los_multiplier"]),
                    has_line_of_sight=effective_los,
                    engaged_personnel=eff_p2,
                )
                u1_has_fire = attack_profile1["effective_attack"] > 0
                u2_has_fire = attack_profile2["effective_attack"] > 0

                u1_engages = False
                if profile1["can_direct_combat"] and u1_has_fire and close_contact and order_rules["close_contact_self_defense"]:
                    u1_engages = True
                elif profile1["can_direct_combat"] and u1_has_fire and u1_can_see and edge_dist <= u1.direct_fire_range:
                    if effective_los or u1_has_indirect_at_range:
                        if stance1["allows_ranged_fire"] and order_allows_ranged_fire(u1):
                            u1_engages = True
                        
                u2_engages = False
                if profile2["can_direct_combat"] and u2_has_fire and close_contact and order_rules["close_contact_self_defense"]:
                    u2_engages = True
                elif profile2["can_direct_combat"] and u2_has_fire and u2_can_see and edge_dist <= u2.direct_fire_range:
                    if effective_los or u2_has_indirect_at_range:
                        if stance2["allows_ranged_fire"] and order_allows_ranged_fire(u2):
                            u2_engages = True

                if not u1_engages and not u2_engages:
                    continue
                engagement_key = tuple(sorted((u1.id, u2.id)))
                if close_contact:
                    close_engagements_now.add(engagement_key)
                if close_contact and engagement_key not in self._active_close_engagements:
                    self.log_event(
                        f"⚔️ [Close Combat] {u1.name} and {u2.name} entered direct combat.",
                        faction="SYSTEM",
                        msg_type="combat",
                    )
                    
                river_crossed = self.is_crossing_river(u1, u2)
                atk1_mult = 1.0 if u1_can_see else 0.0 
                atk2_mult = 1.0 if u2_can_see else 0.0
                
                log_probability = min(1.0, float(direct["unopposed_log_probability_per_hour"]) * delta_time_hours)
                if u1_can_see and not u2_can_see and u1_engages and random.random() < log_probability:
                    self.log_event(f"[Unopposed Fire] {u1.name} engaged {u2.name} before the opposing unit acquired contact.", faction=u1.faction, msg_type="combat")
                elif u2_can_see and not u1_can_see and u2_engages and random.random() < log_probability:
                    self.log_event(f"[Unopposed Fire] {u2.name} engaged {u1.name} before the opposing unit acquired contact.", faction=u2.faction, msg_type="combat")

                if river_crossed:
                    if u1_engages and u2.status != "MOVING" and u1.waypoints:
                        penalty = float(direct["river_engineer_multiplier"]) if u1.has_capability(direct["river_engineer_capability"]) else float(direct["river_crossing_multiplier"])
                        atk1_mult *= penalty
                        if u2_can_see and random.random() < log_probability:
                            self.log_event(f"💥 [River Crossing] {u1.name} met fierce resistance while crossing the river!", faction=u1.faction, msg_type="combat")
                    elif u2_engages and u1.status != "MOVING" and u2.waypoints:
                        penalty = float(direct["river_engineer_multiplier"]) if u2.has_capability(direct["river_engineer_capability"]) else float(direct["river_crossing_multiplier"])
                        atk2_mult *= penalty
                        if u1_can_see and random.random() < log_probability:
                            self.log_event(f"💥 [River Crossing] {u2.name} met fierce resistance while crossing the river!", faction=u2.faction, msg_type="combat")
                
                eff1 = u1.get_terrain_efficiency(tc)
                eff2 = u2.get_terrain_efficiency(tc)
                
                alt_diff = getattr(u1, 'altitude', 0.0) - getattr(u2, 'altitude', 0.0)
                elevation_threshold = float(direct["elevation_advantage_threshold_m"])
                elevation_multiplier = float(direct["elevation_advantage_multiplier"])
                if alt_diff > elevation_threshold:
                    eff1 *= elevation_multiplier
                elif alt_diff < -elevation_threshold:
                    eff2 *= elevation_multiplier
                
                atk1 = float(attack_profile1["effective_attack"])
                atk2 = float(attack_profile2["effective_attack"])
                u1_indirect = attack_profile1["indirect_component"] > 0 and attack_profile1["direct_component"] <= 0
                u2_indirect = attack_profile2["indirect_component"] > 0 and attack_profile2["direct_component"] <= 0

                def1 = (u1.base_breakthrough if u1.status == "MOVING" else u1.base_defense) * eff1
                def2 = (u2.base_breakthrough if u2.status == "MOVING" else u2.base_defense) * eff2
                
                attack_scale = float(direct["attack_scale"])
                final_atk1 = (atk1 * eff1 * atk1_mult * attack_scale) if u1_engages else 0.0
                final_atk2 = (atk2 * eff2 * atk2_mult * attack_scale) if u2_engages else 0.0
                final_atk1 *= float(profile1["outgoing_direct_fire_multiplier"]) * float(profile2["incoming_direct_fire_multiplier"])
                final_atk2 *= float(profile2["outgoing_direct_fire_multiplier"]) * float(profile1["incoming_direct_fire_multiplier"])

                def calc_hits(a, d):
                    return (
                        min(a, d) * float(direct["defended_hit_coefficient"])
                        + max(0.0, a - d) * float(direct["overmatch_hit_coefficient"])
                    )

                cover1 = self._cover_multiplier(u1, tc, indirect=(u2_indirect and not effective_los))
                cover2 = self._cover_multiplier(u2, tc, indirect=(u1_indirect and not effective_los))
                casualty_time_multiplier = float(direct["casualty_time_multiplier"])
                h2 = calc_hits(final_atk1, def2) * delta_time_hours * casualty_time_multiplier * cover2
                h1 = calc_hits(final_atk2, def1) * delta_time_hours * casualty_time_multiplier * cover1

                morale_scale = float(self.rules["readiness"]["morale_scale"])
                org_casualty = float(direct["organization_casualty_multiplier"])
                org_pressure = float(direct["organization_pressure_multiplier"])
                org_loss1 = (h1 / max(u1.personnel, 1.0)) * morale_scale * org_casualty + (final_atk2 / max(def1 + 1.0, 1.0)) * delta_time_hours * org_pressure
                org_loss2 = (h2 / max(u2.personnel, 1.0)) * morale_scale * org_casualty + (final_atk1 / max(def2 + 1.0, 1.0)) * delta_time_hours * org_pressure
                suppression_cap = float(direct["suppression_cap"])
                suppression_multiplier = float(direct["suppression_attack_multiplier"])
                self._apply_combat_effects(u1, h1, org_loss1, min(suppression_cap, final_atk2 * delta_time_hours * suppression_multiplier))
                self._apply_combat_effects(u2, h2, org_loss2, min(suppression_cap, final_atk1 * delta_time_hours * suppression_multiplier))

                if u1.personnel == 0: 
                    self.log_event(f"[Unit Neutralized] {u1.name} is no longer combat effective.", faction=u1.faction, msg_type="combat")
                if u2.personnel == 0: 
                    self.log_event(f"[Unit Neutralized] {u2.name} is no longer combat effective.", faction=u2.faction, msg_type="combat")

        self._resolve_installation_direct_fire(delta_time_hours)
        self._active_close_engagements = close_engagements_now

    def run_clock(self):
        last_time = time.time()
        while not self._stop_event.is_set():
            try:
                current_time = time.time()
                dt_real = current_time - last_time
                last_time = current_time

                with self.lock:
                    if not self.is_paused:
                        dt_game_hours = (
                            dt_real
                            * (float(self.rules["clock"]["game_seconds_per_real_second"]) / 3600.0)
                            * self.time_multiplier
                        )
                        self.game_hours += dt_game_hours

                        for u in list(self.units.values()):
                            u.update_position(dt_game_hours, self)

                        self.installation_tick(dt_game_hours)
                        self.tactical_aura_tick(dt_game_hours)
                        self.political_tick(dt_game_hours)
                        self.combat_tick(dt_game_hours)
                    
            except Exception as e:
                # Engine Crash Tolerance: Do not let the thread die on error, print stack and enter next loop
                print(f"\n🚨 [System Alert] Physics engine anomaly detected, auto-resetting heartbeat: {e}")
                import traceback
                traceback.print_exc()
                
            # Waiting on the stop event makes DLC remounts terminate promptly.
            self._stop_event.wait(float(self.rules["clock"]["heartbeat_interval_seconds"]))
