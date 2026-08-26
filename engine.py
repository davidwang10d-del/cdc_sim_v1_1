import time
import math
import os
import json
import random
import sys
from copy import deepcopy
from pathlib import Path
import re
import threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from gis import MapEngine, ProvinceEngine, haversine_distance
from app import MilitaryUnit
from dlc_loader import DLCPackage, PROJECT_ROOT, load_dlc_package, validate_identifier


_SAVE_SLOT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_EARTH_RADIUS_KM = 6371.0


def destination_point(lon, lat, bearing_radians, distance_km):
    """Return a point a geodesic distance from a longitude/latitude pair."""
    angular_distance = distance_km / _EARTH_RADIUS_KM
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing_radians)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing_radians) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lon2), math.degrees(lat2)

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
        
        self.province_influence = {}
        self.units = {}
        self.structured_logs = []
        self.committee_records = []
        
        self.detected_units = {} 
        self.diplomacy = {}
        self.committee_config = self._build_committee_config()
        
        self.time_multiplier = float(self.rules["clock"]["default_time_multiplier"])
        self.is_paused = True
        self.game_hours = 0.0
        
        self._init_log_file()
            
        if self._save_path("autosave").exists():
            loaded, _ = self.load_game("autosave")
            if not loaded:
                self.load_initial_scenario()
        else:
            self.load_initial_scenario()

    def _build_committee_config(self):
        return deepcopy(self.scenario_data["committee"])

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

            self.units = fresh_units
            self.province_influence = {}
            self.detected_units = {}
            self.committee_records = []
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

            self.log_event(f"🔄 [System] Initial tactical scenario [{self.scenario_data.get('scenario_name', 'Unknown')}] loaded successfully.", faction="SYSTEM")

    def _save_path(self, slot_name):
        if not isinstance(slot_name, str) or not _SAVE_SLOT_PATTERN.fullmatch(slot_name):
            raise ValueError("Save slot must use 1-32 letters, numbers, dashes, or underscores")
        return self.storage_dir / f"save_{slot_name}.json"

    def save_game(self, slot_name):
        filename = self._save_path(slot_name)
        temp_filename = filename.with_suffix(filename.suffix + ".tmp")
        with self.lock:
            save_data = {
                "format_version": 2,
                "dlc_id": self.dlc_id,
                "rules_schema_version": self.rules["schema_version"],
                "game_hours": self.game_hours,
                "time_multiplier": self.time_multiplier,
                "is_paused": self.is_paused,
                "provinces": self.province_influence,
                "detected_units": self.detected_units,
                "committee_records": self.committee_records,
                "structured_logs": self.structured_logs,
                "diplomacy": self.diplomacy,
                "units": {k: v.to_dict() for k, v in self.units.items()},
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

            if slot_name != "autosave":
                self.log_event(f"💾 [System] Battle state backed up to: [{slot_name}]", faction="SYSTEM")
        return filename

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

            provinces = save_data.get("provinces", {})
            detected_units = save_data.get("detected_units", {})
            committee_records = save_data.get("committee_records", [])
            structured_logs = save_data.get("structured_logs", self.structured_logs)
            diplomacy = save_data.get("diplomacy", {})
            if not isinstance(provinces, dict) or not isinstance(detected_units, dict) or not isinstance(diplomacy, dict):
                raise ValueError("Save contains invalid map, detection, or diplomacy state")
            if not isinstance(committee_records, list) or not isinstance(structured_logs, list):
                raise ValueError("Save contains invalid committee or log records")
        except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            return False, f"Save is invalid: {exc}"

        # Commit only after every field and unit has been parsed successfully.
        with self.lock:
            self.game_hours = game_hours
            self.time_multiplier = time_multiplier
            # Loading is always fail-safe: chairs explicitly resume when ready.
            self.is_paused = True
            self.province_influence = provinces
            self.detected_units = detected_units
            self.committee_records = committee_records[-int(self.rules["state_limits"]["committee_records"]):]
            self.structured_logs = structured_logs[-int(self.rules["state_limits"]["structured_logs"]):]
            self.diplomacy = diplomacy
            self.units = restored_units
            self.log_event(f"📂 [System] Save file awakened: [{slot_name}]", faction="SYSTEM")
        return True, "Load successful"

    def save_state(self):
        self.save_game("autosave")

    def stop(self):
        """Request a clean shutdown of this engine's heartbeat loop."""
        self._stop_event.set()

    @property
    def is_stopped(self):
        return self._stop_event.is_set()

    def _clamp(self, value, low, high):
        return max(low, min(high, value))

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
                "visible_losses": 0
            })
            rec["units"] += 1
            rec["active_personnel"] += int(max(0, unit.personnel))
            rec["average_morale"] += getattr(unit, "morale", 0.0)
            rec["average_supply"] += unit.supply
            if unit.personnel <= 0:
                rec["visible_losses"] += 1

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
                f"- {rec['faction']}: {rec['active_personnel']} personnel, "
                f"{rec['units']} units, morale {rec['average_morale']}%, supply {rec['average_supply']}%"
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
        tc = self.map_engine.get_terrain_complexity(unit.lon, unit.lat)
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
            record = self.detected_units.get(target.id)
            new_contact = record is None or (isinstance(record, dict) and observer.faction not in record.get("factions", []))
            if new_contact:
                if self.rules["stances"][target.stance]["auto_evasion"]:
                    self.log_event(f"👁️ [Intel] {observer.name} saw through the cover and locked onto the stealthed {target.name}!", faction=observer.faction)
                else:
                    self.log_event(f"📡 [Contact] {observer.name}'s vanguard radar detected the outline of {target.name}.", faction=observer.faction)
            if not isinstance(record, dict):
                record = {"ttl": 0.0, "factions": []}
            if observer.faction not in record["factions"]:
                record["factions"].append(observer.faction)
            record["ttl"] = max(record["ttl"], float(detection["contact_ttl_hours"]))
            self.detected_units[target.id] = record

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
                if uid in self.units:
                    self.log_event(f"🌫️ [Contact Lost] {self.units[uid].name} vanished into the fog of war.", faction="SYSTEM", msg_type="system")

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

    def political_tick(self, dt):
        rules = self.rules["political_influence"]
        if not rules["enabled"]:
            return
        fp = {}
        for u in self.units.values():
            if u.personnel <= 0 or u.status in rules["excluded_statuses"]:
                continue
            prov = u.current_province
            if prov in rules["excluded_province_names"] or any(prov.startswith(prefix) for prefix in rules["excluded_province_prefixes"]):
                continue
            faction_weight = float(rules["faction_weights"].get(u.faction, rules["default_faction_weight"]))
            stance_weight = float(self.rules["stances"][u.stance]["political_presence_multiplier"])
            weight = u.personnel * u.equipment_level * stance_weight * faction_weight
            if prov not in fp: 
                fp[prov] = 0.0
            fp[prov] += weight 

        for prov, net_force in fp.items():
            if prov not in self.province_influence: 
                self.province_influence[prov] = 0.0
                
            shift = (
                net_force
                / float(rules["personnel_reference"])
                * float(rules["shift_per_reference_unit_hour"])
                * dt
            )
            old_infl = self.province_influence[prov]
            new_infl = max(float(rules["minimum"]), min(float(rules["maximum"]), old_infl + shift))
            self.province_influence[prov] = new_infl

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

    def resolve_airstrike_impact(self, aircraft):
        if aircraft.target_lon is None or aircraft.target_lat is None:
            return

        airstrike = self.rules["missions"]["airstrike"]
        routing = self.rules["combat"]["routing"]
        resources = self.rules["resources"]
        blast_radius = float(airstrike["blast_radius_km"])
        hit_any = False
        for target in self.units.values():
            target_profile = self.rules["unit_types"][target.unit_type]
            if target.personnel <= 0 or not target_profile["can_be_airstrike_target"] or self.is_allied(aircraft.faction, target.faction):
                continue
            if not self._is_detected_by(aircraft.faction, target.id):
                continue

            center_dist = haversine_distance(aircraft.target_lon, aircraft.target_lat, target.lon, target.lat)
            edge_dist = max(0.0, center_dist - target.radius)
            if edge_dist > blast_radius:
                continue

            tc = self.map_engine.get_terrain_complexity(target.lon, target.lat)
            aim_factor = self._clamp(1.0 - (edge_dist / blast_radius), float(airstrike["minimum_aim_factor"]), 1.0)
            cover = self._cover_multiplier(target, tc, indirect=True)
            casualties = aircraft.personnel * aircraft.equipment_level * float(airstrike["casualty_coefficient"]) * aim_factor * cover
            org_loss = float(airstrike["organization_base"]) + casualties / max(target.personnel, 1.0) * float(airstrike["organization_casualty_multiplier"])
            suppression = float(airstrike["suppression"]) * aim_factor
            self._apply_combat_effects(target, casualties, org_loss, suppression)
            hit_any = True

            if target.personnel > 0 and target.morale < float(routing["morale_threshold"]) and target.status != "ROUTING":
                self._route_unit(
                    target,
                    f"[Airstrike] {target.name} broke contact after a close air attack.",
                )

        if hit_any:
            aircraft.fatigue = min(float(resources["maximum"]), aircraft.fatigue + float(airstrike["fatigue_cost"]))
            aircraft.supply = max(float(resources["minimum"]), aircraft.supply - float(airstrike["supply_cost"]))

    def _route_unit(self, unit, message):
        """Put a broken unit on a concrete fallback route instead of leaving it stuck."""
        routing = self.rules["combat"]["routing"]
        unit.status = "ROUTING"
        unit.stance = routing["stance"]
        unit.set_order_role("hold")
        bearing = random.uniform(0.0, 2.0 * math.pi)
        retreat_distance = random.uniform(float(routing["retreat_min_km"]), float(routing["retreat_max_km"]))
        destination = destination_point(unit.lon, unit.lat, bearing, retreat_distance)
        unit.waypoints = [destination]
        unit.target_lon, unit.target_lat = destination
        self.log_event(message, faction=unit.faction, msg_type="combat")

    def combat_tick(self, delta_time_hours):
        self.detection_tick(delta_time_hours)
        evasion = self.rules["combat"]["evasion"]
        routing = self.rules["combat"]["routing"]
        bombard = self.rules["missions"]["bombard"]
        
        for u in self.units.values():
            if u.personnel <= 0 or not self.rules["unit_types"][u.unit_type]["can_direct_combat"]:
                continue
                
            visible_enemies = []
            for uid in self.detected_units:
                if uid in self.units and self._is_detected_by(u.faction, uid) and self.units[uid].personnel > 0 and not self.is_allied(u.faction, self.units[uid].faction):
                    center_dist = haversine_distance(u.lon, u.lat, self.units[uid].lon, self.units[uid].lat)
                    edge_dist = max(0.0, center_dist - u.radius - self.units[uid].radius)
                    visible_enemies.append((edge_dist, self.units[uid]))
                    
            if not visible_enemies: 
                continue
                
            visible_enemies.sort(key=lambda x: x[0])
            nearest_edge_dist, nearest_enemy = visible_enemies[0]

            stance_profile = self.rules["stances"][u.stance]
            if stance_profile["auto_evasion"] and nearest_edge_dist <= u.active_fire_range * float(evasion["trigger_range_fraction"]):
                if u.status != "MOVING": 
                    ea = math.atan2(u.lat - nearest_enemy.lat, u.lon - nearest_enemy.lon)
                    retreat_distance = random.uniform(float(evasion["retreat_min_km"]), float(evasion["retreat_max_km"]))
                    destination = destination_point(u.lon, u.lat, ea, retreat_distance)
                    u.waypoints = [destination]
                    u.target_lon, u.target_lat = destination
                    u.status = "MOVING"
                    u.set_order_role("relocate")
                    if random.random() < min(1.0, float(evasion["log_probability_per_hour"]) * delta_time_hours):
                        self.log_event(f"🥷 [Tactical Evasion] {u.name} completed the ambush and is falling back under cover!", faction=u.faction, msg_type="combat")

        for u in self.units.values():
            if u.status == "BOMBARDING" and u.personnel > 0:
                for target in self.units.values():
                    if target.personnel > 0 and not self.is_allied(u.faction, target.faction):
                        center_dist = haversine_distance(u.target_lon, u.target_lat, target.lon, target.lat)
                        blast_radius = float(bombard["blast_radius_km"])
                        if self._is_detected_by(u.faction, target.id) and max(0.0, center_dist - target.radius) <= blast_radius:
                            tc = self.map_engine.get_terrain_complexity(target.lon, target.lat)
                            aim_factor = self._clamp(
                                1.0 - (max(0.0, center_dist - target.radius) / blast_radius),
                                float(bombard["minimum_aim_factor"]),
                                1.0,
                            )
                            cover = self._cover_multiplier(target, tc, indirect=True)
                            cas = (
                                u.get_terrain_efficiency(tc)
                                * float(bombard["terrain_efficiency_multiplier"])
                                * u.personnel
                                * delta_time_hours
                                * float(bombard["casualty_coefficient"])
                                * aim_factor
                                * cover
                            )
                            org_loss = (
                                float(bombard["organization_base_per_hour"]) * delta_time_hours * aim_factor
                                + (cas / max(target.personnel, 1.0)) * float(bombard["organization_casualty_multiplier"])
                            )
                            self._apply_combat_effects(
                                target,
                                cas,
                                org_loss,
                                float(bombard["suppression_per_hour"]) * delta_time_hours * aim_factor,
                            )
                            if target.personnel > 0 and target.morale < float(routing["morale_threshold"]) and target.status != "ROUTING":
                                self._route_unit(
                                    target,
                                    f"🌪️ [Position Collapse] {target.name} suffered precision bombardment; the defense line routed!",
                                )

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
                    
                center_dist = haversine_distance(u1.lon, u1.lat, u2.lon, u2.lat)
                edge_dist = max(0.0, center_dist - u1.radius - u2.radius)
                
                max_engage_dist = max(u1.active_fire_range, u2.active_fire_range, contact_distance)
                if edge_dist > max_engage_dist:
                    continue

                u1_can_see = self._is_detected_by(u1.faction, u2.id)
                u2_can_see = self._is_detected_by(u2.faction, u1.id)
                
                # 🏔️ 3D Physics: Detect real mountain blockage between two points
                has_los = self.map_engine.check_line_of_sight(u1.lon, u1.lat, u2.lon, u2.lat)
                
                u1_indirect = u1.indirect_fire
                u2_indirect = u2.indirect_fire
                
                if not has_los and not u1_indirect and not u2_indirect:
                    continue

                if not u1_can_see and not u2_can_see and edge_dist > contact_distance:
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

                u1_engages = False
                if profile1["can_direct_combat"] and edge_dist <= contact_distance and order_rules["close_contact_self_defense"]:
                    u1_engages = True
                elif profile1["can_direct_combat"] and u1_can_see and edge_dist <= u1.active_fire_range:
                    if has_los or u1_indirect:
                        if stance1["allows_ranged_fire"] and order_allows_ranged_fire(u1):
                            u1_engages = True
                        
                u2_engages = False
                if profile2["can_direct_combat"] and edge_dist <= contact_distance and order_rules["close_contact_self_defense"]:
                    u2_engages = True
                elif profile2["can_direct_combat"] and u2_can_see and edge_dist <= u2.active_fire_range:
                    if has_los or u2_indirect:
                        if stance2["allows_ranged_fire"] and order_allows_ranged_fire(u2):
                            u2_engages = True

                if not u1_engages and not u2_engages:
                    continue
                    
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
                
                tc = self.map_engine.get_terrain_complexity(u1.lon, u1.lat)
                cw = max(
                    float(direct["frontage_minimum_personnel"]),
                    float(direct["frontage_maximum_personnel"]) - tc * float(direct["frontage_terrain_reduction"]),
                )
                
                eff_p1 = u1.personnel if profile1["uncapped_frontage"] else min(u1.personnel, cw)
                eff_p2 = u2.personnel if profile2["uncapped_frontage"] else min(u2.personnel, cw)
                
                eff1 = u1.get_terrain_efficiency(tc)
                eff2 = u2.get_terrain_efficiency(tc)
                
                alt_diff = getattr(u1, 'altitude', 0.0) - getattr(u2, 'altitude', 0.0)
                elevation_threshold = float(direct["elevation_advantage_threshold_m"])
                elevation_multiplier = float(direct["elevation_advantage_multiplier"])
                if alt_diff > elevation_threshold:
                    eff1 *= elevation_multiplier
                elif alt_diff < -elevation_threshold:
                    eff2 *= elevation_multiplier
                
                atk1 = (u1.base_soft_attack * u2.softness) + (u1.base_hard_attack * (1.0 - u2.softness))
                if u1.ap < u2.armor: 
                    atk1 *= float(direct["failed_penetration_multiplier"])
                    
                atk2 = (u2.base_soft_attack * u1.softness) + (u2.base_hard_attack * (1.0 - u1.softness))
                if u2.ap < u1.armor: 
                    atk2 *= float(direct["failed_penetration_multiplier"])

                def1 = (u1.base_breakthrough if u1.status in ["MOVING", "ROUTING"] else u1.base_defense) * eff1
                def2 = (u2.base_breakthrough if u2.status in ["MOVING", "ROUTING"] else u2.base_defense) * eff2
                
                personnel_reference = float(direct["personnel_reference"])
                attack_scale = float(direct["attack_scale"])
                final_atk1 = (atk1 * eff1 * (eff_p1 / personnel_reference) * atk1_mult * attack_scale) if u1_engages else 0.0
                final_atk2 = (atk2 * eff2 * (eff_p2 / personnel_reference) * atk2_mult * attack_scale) if u2_engages else 0.0
                final_atk1 *= float(profile1["outgoing_direct_fire_multiplier"]) * float(profile2["incoming_direct_fire_multiplier"])
                final_atk2 *= float(profile2["outgoing_direct_fire_multiplier"]) * float(profile1["incoming_direct_fire_multiplier"])

                if u1_indirect and not has_los:
                    final_atk1 *= float(direct["indirect_without_los_multiplier"])
                if u2_indirect and not has_los:
                    final_atk2 *= float(direct["indirect_without_los_multiplier"])

                def calc_hits(a, d):
                    return (
                        min(a, d) * float(direct["defended_hit_coefficient"])
                        + max(0.0, a - d) * float(direct["overmatch_hit_coefficient"])
                    )

                cover1 = self._cover_multiplier(u1, tc, indirect=(u2_indirect and not has_los))
                cover2 = self._cover_multiplier(u2, tc, indirect=(u1_indirect and not has_los))
                casualty_time_multiplier = float(direct["casualty_time_multiplier"])
                h2 = calc_hits(final_atk1, def2) * delta_time_hours * casualty_time_multiplier * cover2
                h1 = calc_hits(final_atk2, def1) * delta_time_hours * casualty_time_multiplier * cover1

                if u1.status == "ROUTING" and not routing["can_deal_damage"]:
                    h2 = 0 
                if u2.status == "ROUTING" and not routing["can_deal_damage"]:
                    h1 = 0

                morale_scale = float(self.rules["readiness"]["morale_scale"])
                org_casualty = float(direct["organization_casualty_multiplier"])
                org_pressure = float(direct["organization_pressure_multiplier"])
                org_loss1 = (h1 / max(u1.personnel, 1.0)) * morale_scale * org_casualty + (final_atk2 / max(def1 + 1.0, 1.0)) * delta_time_hours * org_pressure
                org_loss2 = (h2 / max(u2.personnel, 1.0)) * morale_scale * org_casualty + (final_atk1 / max(def2 + 1.0, 1.0)) * delta_time_hours * org_pressure
                suppression_cap = float(direct["suppression_cap"])
                suppression_multiplier = float(direct["suppression_attack_multiplier"])
                self._apply_combat_effects(u1, h1, org_loss1, min(suppression_cap, final_atk2 * delta_time_hours * suppression_multiplier))
                self._apply_combat_effects(u2, h2, org_loss2, min(suppression_cap, final_atk1 * delta_time_hours * suppression_multiplier))

                # 🟢 Fixed and enabled organization collapse and routing logic
                for tu in [u1, u2]:
                    if tu.personnel > 0 and tu.morale < float(routing["morale_threshold"]) and tu.status not in ["ROUTING", "AIRSTRIKE_OUTBOUND", "AIRSTRIKE_RTB"]:
                        self._route_unit(
                            tu,
                            f"🌪️ [Line Collapse] {tu.name} organization depleted! Remnants dropped their gear and are routing to the rear!",
                        )

                if u1.personnel == 0: 
                    self.log_event(f"[Unit Neutralized] {u1.name} is no longer combat effective.", faction=u1.faction, msg_type="combat")
                if u2.personnel == 0: 
                    self.log_event(f"[Unit Neutralized] {u2.name} is no longer combat effective.", faction=u2.faction, msg_type="combat")

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
