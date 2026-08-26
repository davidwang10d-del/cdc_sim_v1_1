from flask import Flask, jsonify, request, render_template, Response
import threading
import os
import logging
import sys
import importlib.util
import math

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Import core components and validated DLC packages
from app import MilitaryUnit
from engine import SimulationEngine
from gis import haversine_distance 
from dlc_loader import (
    DLCValidationError,
    PROJECT_ROOT,
    load_dlc_package,
    scan_dlcs,
    validate_identifier,
)

# Disable Flask's default verbose logging to keep the simulation console clean
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

# 🟢 Global variables: Engine and physics thread initialized as empty shells
engine = None
physics_thread = None
engine_guard = threading.RLock()


class APIInputError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def api_error(message, status_code=400):
    return jsonify({"status": "error", "msg": str(message)}), status_code


def json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIInputError("Request body must be a JSON object")
    return data


def finite_number(value, label, minimum=None, maximum=None):
    if isinstance(value, bool):
        raise APIInputError(f"{label} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise APIInputError(f"{label} must be a number") from exc
    if not math.isfinite(number):
        raise APIInputError(f"{label} must be finite")
    if minimum is not None and number < minimum:
        raise APIInputError(f"{label} must be at least {minimum:g}")
    if maximum is not None and number > maximum:
        raise APIInputError(f"{label} must be at most {maximum:g}")
    return number


def coordinates(lon, lat):
    return (
        finite_number(lon, "Longitude", -180.0, 180.0),
        finite_number(lat, "Latitude", -90.0, 90.0),
    )


def mounted_engine():
    active = engine
    if active is None:
        raise APIInputError("System is idling, please mount a campaign first", 409)
    return active

def start_physics_thread(target_engine=None):
    """Delay activation of the physics timeline after mounting a DLC"""
    global physics_thread
    target_engine = target_engine or engine
    if target_engine is None:
        raise RuntimeError("Cannot start physics without an engine")
    if physics_thread is None or not physics_thread.is_alive():
        def run_physics():
            print("⚙️ [Physics Engine] Core heartbeat thread activated, theater timeline is now flowing.")
            target_engine.run_clock()
            
        physics_thread = threading.Thread(target=run_physics, daemon=True)
        physics_thread.start()

# ==========================================
# 1. Frontend Page Routing
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/zh')
def index_zh():
    return render_template('index.html', force_lang='zh')

@app.route('/status')
def status_page():
    return render_template('status.html')

@app.route('/editor')
def editor_page():
    return render_template('cdc_editor.html')


@app.route('/api/editor_template', methods=['GET'])
def editor_template():
    """Serve battle data separately from the core command doctrine."""
    try:
        package = load_dlc_package("_template")
        return jsonify({
            "status": "ok",
            "scenario": package.scenario,
            "units": package.units,
            "battalions": package.battalions,
            "weapons": package.weapons,
            "rules": package.source_rules,
            "doctrine": {
                "orders": package.rules["orders"],
                "stances": package.rules["stances"],
            },
        })
    except DLCValidationError as exc:
        return api_error(f"Editor template is invalid: {exc}", 500)

@app.route('/chair_guide')
def chair_guide_page():
    return render_template('chair_guide.html')

@app.route('/chair_guide_zh')
def chair_guide_zh_page():
    return render_template('chair_guide_zh.html')

@app.route('/api/health', methods=['GET'])
def health_check():
    packages = ["flask", "numpy", "PIL", "rasterio", "requests", "matplotlib"]
    package_state = {
        pkg: importlib.util.find_spec(pkg) is not None
        for pkg in packages
    }
    return jsonify({
        "status": "ok" if all(package_state.values()) else "missing_dependencies",
        "python": sys.version.split()[0],
        "cwd": str(PROJECT_ROOT),
        "packages": package_state,
        "venv": sys.prefix
    })

# ==========================================
# 2. DLC Bootloader
# ==========================================
@app.route('/api/list_dlcs', methods=['GET'])
def list_dlcs():
    """Scan the dlc folder to retrieve all campaign modules"""
    return jsonify(scan_dlcs())

@app.route('/api/mount_dlc', methods=['POST'])
def mount_dlc():
    """Ignition: Mount the specified DLC, inject physical laws, and start the heartbeat"""
    global engine, physics_thread
    try:
        data = json_object()
        dlc_id = data.get("dlc_id")
        package = load_dlc_package(dlc_id)

        # Build completely before disturbing the currently running committee.
        candidate = SimulationEngine(package.dlc_id, package=package)
        with engine_guard:
            previous_engine = engine
            previous_thread = physics_thread
            if previous_engine is not None:
                previous_engine.stop()
            if previous_thread is not None and previous_thread.is_alive():
                previous_thread.join(timeout=2.0)
            engine = candidate
            physics_thread = None
            start_physics_thread(candidate)

        factions = sorted({unit.faction for unit in candidate.units.values()})
        mount_warnings = []
        if (candidate.map_config.get("dem_dir") or candidate.map_config.get("dem_file")) and not candidate.map_engine.use_real_dem:
            mount_warnings.append("Configured elevation data failed to load; flat fallback terrain is active.")
        if candidate.map_config.get("roads_file") and not candidate.map_engine.road_matrix.any():
            mount_warnings.append("Configured road data produced no usable road nodes.")
        if candidate.map_config.get("rivers_file") and not candidate.map_engine.river_matrix.any():
            mount_warnings.append("Configured river data produced no usable river segments.")
        if candidate.map_config.get("provinces_file") and not candidate.prov_engine.provinces:
            mount_warnings.append("Configured province data produced no usable provinces.")
        return jsonify({
            "status": "ok", 
            "config": {
                "name": candidate.scenario_data.get("scenario_name"),
                "center": candidate.scenario_data["map_center"],
                "zoom": candidate.scenario_data["map_zoom"],
                "factions": factions,
                "warnings": mount_warnings,
                "rules_schema_version": candidate.rules["schema_version"],
            }
        })
    except APIInputError as exc:
        return api_error(exc, exc.status_code)
    except DLCValidationError as exc:
        return api_error(f"Mount rejected: {exc}", 400)
    except Exception as exc:
        app.logger.exception("DLC mount failed")
        return api_error(f"Mount failed: {exc}", 500)

# ==========================================
# 3. Geography and Dashboard State Synchronization
# ==========================================
@app.route('/geojson')
def get_geojson():
    active = engine
    if not active:
        return jsonify({"type": "FeatureCollection", "features": []})
    # Dynamically read the province boundaries of the current DLC
    prov_file = active.map_config.get("provinces_file", "")
    if os.path.exists(prov_file):
        try:
            with open(prov_file, 'r', encoding='utf-8') as f:
                import json
                geojson = json.load(f)
            name_property = active.map_config.get("province_name_property", "")
            for feature in geojson.get("features", []):
                properties = feature.setdefault("properties", {})
                name = properties.get(name_property) if name_property else None
                if not name:
                    name = next((value for value in properties.values() if isinstance(value, str) and value.strip()), "Unknown")
                properties["cdc_name"] = str(name)
            return jsonify(geojson)
        except (OSError, ValueError):
            app.logger.exception("Mounted province file could not be read")
    return jsonify({"type": "FeatureCollection", "features": []})

@app.route('/api/registry', methods=['GET'])
def get_registry():
    active = engine
    return jsonify({
        "weapons": active.weapon_registry if active else {},
        "battalions": active.battalion_registry if active else {},
        "rules": active.rules if active else {},
    })

@app.route('/api/state', methods=['GET'])
def get_state():
    active = engine
    if not active:
        return jsonify({"status": "unmounted"})
    with active.lock:
        units_data = {u_id: unit.to_dict() for u_id, unit in active.units.items()}
        return jsonify({
            "status": "ok",
            "time": {
                "day": int(active.game_hours // 24),
                "hour": int(active.game_hours % 24),
                "minute": int((active.game_hours * 60) % 60),
                "second": int((active.game_hours * 3600) % 60),
                "multiplier": active.time_multiplier,
                "paused": active.is_paused,
            },
            "units": units_data,
            "provinces": active.province_influence,
            "latest_logs": active.structured_logs[-int(active.rules["state_limits"]["state_feed_logs"]):],
        })

@app.route('/api/logs', methods=['GET'])
def get_logs():
    active = engine
    if not active:
        return jsonify({"logs": []})
    with active.lock:
        return jsonify({"logs": list(active.structured_logs)})

@app.route('/api/committee', methods=['GET'])
def get_committee_state():
    active = engine
    if not active:
        return jsonify({"status": "unmounted"})
    with active.lock:
        return jsonify(active.get_committee_state())

@app.route('/api/committee/adjudicate', methods=['POST'])
def adjudicate_committee_directive():
    try:
        active = mounted_engine()
        data = json_object()
        with active.lock:
            record = active.adjudicate_directive(data)
            active.save_state()
        return jsonify({"status": "ok", "record": record})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)
    except (TypeError, ValueError) as exc:
        return api_error(f"Adjudication failed: {exc}", 400)

@app.route('/api/committee/sitrep', methods=['GET'])
def export_committee_sitrep():
    active = engine
    if not active:
        return jsonify({"status": "unmounted"})
    include_private = request.args.get("private", "0") in ["1", "true", "yes"]
    with active.lock:
        markdown = active.build_sitrep_markdown(include_private=include_private)
    return Response(markdown, mimetype="text/markdown")

@app.route('/api/terrain', methods=['GET'])
def get_terrain():
    try:
        active = mounted_engine()
        lon, lat = coordinates(request.args.get('lon'), request.args.get('lat'))
        tc = active.map_engine.get_terrain_complexity(lon, lat)
        return jsonify({"status": "ok", "complexity": round(tc, 2)})
    except APIInputError as exc:
        return jsonify({"status": "error", "msg": str(exc), "complexity": 0.0}), exc.status_code

@app.route('/api/roads_overlay')
def get_roads_overlay():
    active = engine
    if not active:
        return jsonify({"type": "FeatureCollection", "features": []})
    return jsonify(active.map_engine.export_road_geojson())

# ==========================================
# 4. Tactical Commands and Backend Intervention Core
# ==========================================
@app.route('/api/command', methods=['POST'])
def execute_command():
    try:
        active = mounted_engine()
        data = json_object()
        command_text = data.get("command")
        if not isinstance(command_text, str) or not command_text.strip():
            raise APIInputError("Command is empty")
        parts = command_text.strip().split()
        cmd = parts[0].lower()
        waypoints_data = data.get("waypoints", [])
        message = "Execution successful"

        with active.lock:
            if cmd in {"play", "pause"}:
                if len(parts) != 1:
                    raise APIInputError(f"{cmd} does not accept arguments")
                active.is_paused = cmd == "pause"
                message = "Simulation paused" if active.is_paused else "Simulation resumed"
                active.log_event(
                    "⏸️ [System] Suspending simulation." if active.is_paused else "▶️ [System] Resuming simulation.",
                    faction="SYSTEM",
                    msg_type="system",
                )

            elif cmd == "speed":
                if len(parts) != 2:
                    raise APIInputError("Usage: speed <multiplier>")
                clock_rules = active.rules["clock"]
                multiplier = finite_number(
                    parts[1],
                    "Speed multiplier",
                    float(clock_rules["speed_multiplier_min"]),
                    float(clock_rules["speed_multiplier_max"]),
                )
                active.time_multiplier = multiplier
                message = f"Simulation speed set to {multiplier:g}x"
                active.log_event(f"[System] Simulation speed set to {multiplier:g}x.", faction="SYSTEM", msg_type="system")

            elif cmd in {"move", "attack", "route"}:
                if len(parts) < 2:
                    raise APIInputError(f"Usage: {cmd} <unit_id> <longitude> <latitude>")
                unit_id = parts[1]
                if unit_id not in active.units:
                    raise APIInputError("Unit not found", 404)
                unit = active.units[unit_id]
                if unit.personnel <= 0:
                    raise APIInputError("A neutralized unit cannot receive movement orders")
                if cmd == "attack" and not active.rules["unit_types"][unit.unit_type]["can_direct_combat"]:
                    raise APIInputError("This unit type cannot receive a ground-assault order")

                targets = []
                if waypoints_data:
                    if not isinstance(waypoints_data, list):
                        raise APIInputError("Waypoints must be a list")
                    max_waypoints = int(active.rules["movement"]["max_route_waypoints"])
                    if len(waypoints_data) > max_waypoints:
                        raise APIInputError(f"A route may contain at most {max_waypoints} waypoints")
                    if cmd != "route" and len(waypoints_data) > 1:
                        raise APIInputError(f"{cmd} accepts one destination; use route for multiple waypoints")
                    for waypoint in waypoints_data:
                        if not isinstance(waypoint, dict):
                            raise APIInputError("Each waypoint must contain lon and lat")
                        targets.append(coordinates(waypoint.get("lon"), waypoint.get("lat")))
                elif len(parts) == 4:
                    targets.append(coordinates(parts[2], parts[3]))
                else:
                    raise APIInputError("Target coordinates not provided")
                if not targets:
                    raise APIInputError("Target coordinates not provided")

                full_path = []
                current_lon, current_lat = unit.lon, unit.lat
                for target_lon, target_lat in targets:
                    segment = active.map_engine.find_path(
                        start_lon=current_lon,
                        start_lat=current_lat,
                        target_lon=target_lon,
                        target_lat=target_lat,
                        unit_composition=unit.composition,
                        unit_capabilities=unit.get_capabilities(),
                    )
                    if not isinstance(segment, list):
                        raise RuntimeError("Pathfinder returned an invalid route")
                    parsed_segment = [coordinates(point[0], point[1]) for point in segment if isinstance(point, (list, tuple)) and len(point) == 2]
                    if len(parsed_segment) > 1 and haversine_distance(current_lon, current_lat, parsed_segment[0][0], parsed_segment[0][1]) < float(active.rules["movement"]["arrival_distance_km"]):
                        parsed_segment.pop(0)
                    full_path.extend(parsed_segment)
                    current_lon, current_lat = target_lon, target_lat
                if not full_path:
                    full_path = [targets[-1]]

                unit.waypoints = full_path
                unit.target_lon, unit.target_lat = targets[-1]
                unit.status = "MOVING"
                unit.set_order_role({"move": "relocate", "route": "route", "attack": "assault"}[cmd])
                unit.entrenchment = float(active.rules["unit_defaults"]["entrenchment"])
                if hasattr(unit, "bombard_timer"):
                    delattr(unit, "bombard_timer")
                order_profile = active.rules["orders"]["modes"][unit.order_role()]
                posture_label = active.rules["stances"][unit.stance]["label"]
                message = f"{order_profile['label']} order issued to {unit.name} using {posture_label} posture"
                if cmd == "attack":
                    active.log_event(f"⚔️ [Assault] {unit.name} is advancing toward the objective and will halt at detected contact.", faction=unit.faction, msg_type="combat")
                elif cmd == "route":
                    active.log_event(f"🗺️ [Planned Route] {unit.name} received a holding-fire route with {len(targets)} waypoints.", faction=unit.faction, msg_type="move")
                else:
                    active.log_event(f"🚀 [Relocate] {unit.name} is moving directly to the objective without initiating ranged combat.", faction=unit.faction, msg_type="move")

            elif cmd in {"airstrike", "bombard"}:
                if len(parts) != 4:
                    raise APIInputError(f"Usage: {cmd} <unit_id> <longitude> <latitude>")
                unit_id = parts[1]
                if unit_id not in active.units:
                    raise APIInputError("Unit not found", 404)
                target_lon, target_lat = coordinates(parts[2], parts[3])
                unit = active.units[unit_id]

                if cmd == "airstrike":
                    capability = active.rules["missions"]["airstrike"]["capability"]
                    if not unit.has_capability(capability):
                        raise APIInputError(f"This unit has no {capability} capability in its DLC data")
                    unit.base_lon, unit.base_lat = unit.lon, unit.lat
                    unit.target_lon, unit.target_lat = target_lon, target_lat
                    unit.waypoints = [(target_lon, target_lat)]
                    unit.status = "AIRSTRIKE_OUTBOUND"
                    unit.set_order_role("hold")
                    active.log_event(f"🛫 [Strike] {unit.name} scrambled and is flying towards the target zone.", faction=unit.faction, msg_type="combat")
                else:
                    bombard_rules = active.rules["missions"]["bombard"]
                    if not unit.has_capability(bombard_rules["capability"]):
                        raise APIInputError("This unit has no bombard capability in its DLC data")
                    fire_dist = haversine_distance(unit.lon, unit.lat, target_lon, target_lat)
                    if fire_dist > unit.active_fire_range:
                        raise APIInputError(f"Target is outside weapon range ({fire_dist:.1f}km > {unit.active_fire_range:.1f}km)")
                    if unit.supply <= float(bombard_rules["minimum_supply_to_start"]):
                        raise APIInputError("Unit lacks ammunition/supply for a fire mission")
                    unit.target_lon, unit.target_lat = target_lon, target_lat
                    unit.status = "BOMBARDING"
                    unit.set_order_role("hold")
                    active.log_event(f"☄️ [Firepower] {unit.name} initiated artillery bombardment.", faction=unit.faction, msg_type="combat")

            elif cmd in {"defend", "fortify"}:
                if len(parts) != 2:
                    raise APIInputError(f"Usage: {cmd} <unit_id>")
                unit_id = parts[1]
                if unit_id not in active.units:
                    raise APIInputError("Unit not found", 404)
                unit = active.units[unit_id]
                if unit.personnel <= 0:
                    raise APIInputError("A neutralized unit cannot prepare a defense")
                if not active.rules["unit_types"][unit.unit_type]["can_direct_combat"]:
                    raise APIInputError("This unit type cannot prepare a ground-defense position")

                defense = active.rules["defense"]
                if cmd == "fortify" and unit.supply < float(defense["minimum_supply_to_start"]):
                    raise APIInputError(
                        f"Fortification requires at least {float(defense['minimum_supply_to_start']):g}% supply"
                    )

                unit.waypoints = []
                unit.target_lon = None
                unit.target_lat = None
                unit.set_order_role(cmd)
                order_rules = active.rules["orders"]
                unit.status = order_rules["fortifying_status"] if cmd == "fortify" else order_rules["defending_status"]
                stance_label = active.rules["stances"][unit.stance]["label"]
                if hasattr(unit, "bombard_timer"):
                    delattr(unit, "bombard_timer")
                if cmd == "fortify":
                    message = f"{unit.name} is fortifying in {stance_label} stance"
                    active.log_event(
                        f"🛠️ [Fortify] {unit.name} began accelerated fieldwork construction in {stance_label} stance; supply and fatigue costs are active.",
                        faction=unit.faction,
                        msg_type="move",
                    )
                else:
                    message = f"{unit.name} is defending in {stance_label} stance"
                    active.log_event(
                        f"🛡️ [Defend] {unit.name} began preparing its position in {stance_label} stance.",
                        faction=unit.faction,
                        msg_type="move",
                    )

            elif cmd == "stance":
                if len(parts) != 3:
                    raise APIInputError("Usage: stance <unit_id> <stance_id>")
                unit_id = parts[1]
                if unit_id not in active.units:
                    raise APIInputError("Unit not found", 404)
                unit = active.units[unit_id]
                requested_stance = parts[2]
                stance_id = next(
                    (
                        candidate
                        for candidate in active.rules["stances"]
                        if candidate.casefold() == requested_stance.casefold()
                    ),
                    None,
                )
                if stance_id is None:
                    allowed = ", ".join(active.rules["stances"])
                    raise APIInputError(f"Unknown combat stance [{requested_stance}]. Choose: {allowed}")
                unit.stance = stance_id
                stance_label = active.rules["stances"][stance_id]["label"]
                order_label = active.rules["orders"]["modes"][unit.order_role()]["label"]
                message = f"{unit.name} will execute {order_label} in {stance_label} stance"
                active.log_event(
                    f"🧭 [Stance] {unit.name} changed to {stance_label} while retaining its {order_label} order.",
                    faction=unit.faction,
                    msg_type="move",
                )

            elif cmd == "halt":
                if len(parts) != 2 or parts[1] not in active.units:
                    raise APIInputError("Usage: halt <unit_id>")
                unit = active.units[parts[1]]
                unit.waypoints = []
                unit.target_lon = None
                unit.target_lat = None
                unit.set_order_role("hold")
                unit.status = "IDLE"
                if hasattr(unit, "bombard_timer"):
                    delattr(unit, "bombard_timer")
                message = f"{unit.name} halted"

            else:
                raise APIInputError(f"Unknown command [{cmd}]")

            active.save_state()
        return jsonify({"status": "ok", "msg": message})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)
    except Exception as exc:
        app.logger.exception("Command execution failed")
        return api_error(f"Command failed: {exc}", 500)

@app.route('/api/edit_unit', methods=['POST'])
def edit_unit():
    try:
        active = mounted_engine()
        data = json_object()
        try:
            unit_id = validate_identifier(data.get("id"), "Unit ID")
        except DLCValidationError as exc:
            raise APIInputError(str(exc)) from exc
        name = str(data.get("name", "")).strip()
        faction = str(data.get("faction", "")).strip()
        if not name or not faction:
            raise APIInputError("Unit name and faction are required")
        center = active.scenario_data["map_center"]
        lon, lat = coordinates(data.get("lon", center[1]), data.get("lat", center[0]))
        primary_weapon = data.get("primary_weapon") or next(iter(active.weapon_registry), None)
        defaults = active.rules["unit_defaults"]
        resources = active.rules["resources"]
        resource_min = float(resources["minimum"])
        resource_max = float(resources["maximum"])
        unit_data = {
            "name": name,
            "faction": faction,
            "icon": str(data.get("icon", "")),
            "personnel": finite_number(data.get("personnel", defaults["personnel"]), "Personnel", 1),
            "equipment_level": finite_number(data.get("equipment_level", defaults["equipment_level"]), "Equipment level", 0),
            "lon": lon,
            "lat": lat,
            "unit_type": str(data.get("unit_type", defaults["unit_type"])),
            "capabilities": data.get("capabilities", []),
            "composition": data.get("composition", {}),
            "primary_weapon": primary_weapon,
            "morale": finite_number(data.get("morale", defaults["morale"]), "Morale", resource_min, resource_max),
            "stance": str(data.get("stance", defaults["stance"])),
            "supply": finite_number(data.get("supply", defaults["supply"]), "Supply", resource_min, resource_max),
            "fatigue": finite_number(data.get("fatigue", defaults["fatigue"]), "Fatigue", resource_min, resource_max),
            "suppression": finite_number(data.get("suppression", defaults["suppression"]), "Suppression", resource_min, resource_max),
        }
        new_unit = MilitaryUnit(unit_id, unit_data, active.weapon_registry, active.battalion_registry, active.rules)
        new_unit.altitude = active.map_engine.get_elevation(new_unit.lon, new_unit.lat)
        new_unit.current_province = active.prov_engine.get_province(new_unit.lon, new_unit.lat)
        with active.lock:
            if unit_id in active.units:
                raise APIInputError("Unit ID conflict", 409)
            active.units[unit_id] = new_unit
            active.log_event(
                f"🚩 [Armed Mobilization] {new_unit.name} (Equipment: {new_unit.weapon_name}) arrived in the theater at {int(new_unit.altitude)} meters.",
                faction=new_unit.faction,
                msg_type="system",
            )
            active.save_state()
        return jsonify({"status": "ok", "unit": new_unit.to_dict()})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)
    except (TypeError, ValueError) as exc:
        return api_error(f"Unit rejected: {exc}", 400)

@app.route('/api/admin_edit', methods=['POST'])
def admin_edit():
    try:
        active = mounted_engine()
        data = json_object()
        original_id = data.get("original_id")
        new_id = data.get("id", original_id)
        try:
            new_id = validate_identifier(new_id, "Unit ID")
        except DLCValidationError as exc:
            raise APIInputError(str(exc)) from exc
        with active.lock:
            if original_id not in active.units:
                raise APIInputError("Unit not found", 404)
            if new_id != original_id and new_id in active.units:
                raise APIInputError("Unit ID conflict", 409)
            current = active.units[original_id]
            candidate_data = current.to_dict()
            for field in ("name", "faction", "icon", "unit_type", "composition", "capabilities", "primary_weapon", "stance"):
                if field in data:
                    candidate_data[field] = data[field]
            resource_min = float(active.rules["resources"]["minimum"])
            resource_max = float(active.rules["resources"]["maximum"])
            for field, minimum, maximum in (
                ("personnel", 0, None),
                ("equipment_level", 0, None),
                ("supply", resource_min, resource_max),
                ("fatigue", resource_min, resource_max),
                ("suppression", resource_min, resource_max),
                ("morale", resource_min, resource_max),
            ):
                if field in data:
                    candidate_data[field] = finite_number(data[field], field.replace("_", " ").title(), minimum, maximum)
            if "lon" in data or "lat" in data:
                candidate_data["lon"], candidate_data["lat"] = coordinates(data.get("lon", current.lon), data.get("lat", current.lat))
            if not str(candidate_data.get("name", "")).strip() or not str(candidate_data.get("faction", "")).strip():
                raise APIInputError("Unit name and faction cannot be empty")

            replacement = MilitaryUnit(new_id, candidate_data, active.weapon_registry, active.battalion_registry, active.rules)
            replacement.altitude = active.map_engine.get_elevation(replacement.lon, replacement.lat)
            replacement.current_province = active.prov_engine.get_province(replacement.lon, replacement.lat)

            if original_id != new_id:
                active.units.pop(original_id)
                if original_id in active.detected_units:
                    active.detected_units[new_id] = active.detected_units.pop(original_id)
            active.units[new_id] = replacement
            active.log_event(f"[Chair Override] {replacement.name} was updated by crisis staff.", faction="COMMITTEE", msg_type="system")
            active.save_state()
        return jsonify({"status": "ok", "unit": replacement.to_dict()})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)
    except (TypeError, ValueError) as exc:
        return api_error(f"Unit update rejected: {exc}", 400)

@app.route('/api/modifier', methods=['POST'])
def add_modifier():
    try:
        active = mounted_engine()
        data = json_object()
        unit_id = data.get('id')
        mod_type = str(data.get('type', '')).lower()
        modifier_rules = active.rules["modifiers"]
        allowed_types = modifier_rules["allowed_types"]
        if mod_type not in allowed_types:
            raise APIInputError(f"Modifier type must be one of: {', '.join(allowed_types)}")
        value = finite_number(
            data.get('value', modifier_rules["default_value"]),
            "Modifier value",
            float(modifier_rules["value_minimum"]),
            float(modifier_rules["value_maximum"]),
        )
        duration = finite_number(
            data.get('duration', modifier_rules["default_duration_hours"]),
            "Modifier duration",
            float(modifier_rules["duration_minimum_hours"]),
            float(modifier_rules["duration_maximum_hours"]),
        )
        name = str(data.get('name') or modifier_rules["default_name"]).strip()[:120]
        with active.lock:
            if unit_id not in active.units:
                raise APIInputError("Unit not found", 404)
            unit = active.units[unit_id]
            unit.modifiers.append({"name": name, "type": mod_type, "value": value, "duration": duration})
            active.log_event(f"[Chair Override] {name} applied to {unit.name}: {mod_type} x{value:g} for {duration:g} hours.", faction="COMMITTEE", msg_type="system")
            active.save_state()
        return jsonify({"status": "ok"})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)

@app.route('/api/set_influence', methods=['POST'])
def set_influence():
    try:
        active = mounted_engine()
        data = json_object()
        province = str(data.get('province', '')).strip()
        if not province:
            raise APIInputError("Province is required")
        influence_rules = active.rules["political_influence"]
        influence = finite_number(
            data.get('influence', 0),
            "Influence",
            float(influence_rules["minimum"]),
            float(influence_rules["maximum"]),
        )
        with active.lock:
            active.province_influence[province] = influence
            active.save_state()
        return jsonify({"status": "ok"})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)

@app.route('/api/diplomacy', methods=['POST'])
def set_diplomacy():
    try:
        active = mounted_engine()
        data = json_object()
        faction_one = str(data.get('f1', '')).strip()
        faction_two = str(data.get('f2', '')).strip()
        allied = data.get('allied')
        if not faction_one or not faction_two:
            raise APIInputError("Both factions are required")
        if faction_one == faction_two:
            raise APIInputError("Diplomacy requires two different factions")
        if not isinstance(allied, bool):
            raise APIInputError("allied must be true or false")
        with active.lock:
            active.set_alliance(faction_one, faction_two, allied)
            action = "signed" if allied else "abrogated"
            active.log_event(f"🤝 [Diplomatic Radar] {faction_one} and {faction_two} {action} a bilateral non-aggression pact.", faction="SYSTEM")
            active.save_state()
        return jsonify({"status": "ok"})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)

@app.route('/api/save_game', methods=['POST'])
def save_game_api():
    try:
        active = mounted_engine()
        slot = json_object().get("slot", "manual_save")
        active.save_game(slot)
        return jsonify({"status": "ok"})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)
    except (OSError, TypeError, ValueError) as exc:
        return api_error(f"Save failed: {exc}", 400)

@app.route('/api/load_game', methods=['POST'])
def load_game_api():
    try:
        active = mounted_engine()
        slot = json_object().get("slot", "default")
        if slot == "initial_reset":
            active.load_initial_scenario()
            active.save_state()
            return jsonify({"status": "ok", "msg": "System hard reset, rolled back to the scenario's initial state and paused."})
        success, msg = active.load_game(slot)
        if not success:
            return api_error(msg, 400)
        return jsonify({"status": "ok", "msg": msg})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 [CDC Theater Core] Global Strategic Simulation Architecture v3.0 ready")
    print("🌐 Listening on port: 5000 | Awaiting campaign DLC mount command from dashboard...")
    print("="*60 + "\n")
    host = os.environ.get("CDC_HOST", "127.0.0.1")
    port = int(os.environ.get("CDC_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
