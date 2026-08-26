import json
import math
import os
import shutil
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import app as unit_module
import dlc_loader as loader_module
import engine as engine_module
from dlc_loader import DLCValidationError, load_dlc_package, resolve_dlc_path, scan_dlcs
from gis import MapEngine
import server


class FakeMapEngine:
    def __init__(self, _config, _geography_rules):
        self.river_matrix = None

    def get_elevation(self, _lon, _lat):
        return 0.0

    def get_terrain_complexity(self, _lon, _lat):
        return 0.0

    def check_line_of_sight(self, *_args):
        return True

    def find_path(self, *, target_lon, target_lat, **_kwargs):
        return [(target_lon, target_lat)]

    def export_road_geojson(self):
        return {"type": "FeatureCollection", "features": []}


class FakeProvinceEngine:
    def __init__(self, *_args):
        pass

    def get_province(self, _lon, _lat):
        return "Test Province"


class EngineRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.map_patch = patch.object(engine_module, "MapEngine", FakeMapEngine)
        self.province_patch = patch.object(engine_module, "ProvinceEngine", FakeProvinceEngine)
        self.map_patch.start()
        self.province_patch.start()
        self.sim = engine_module.SimulationEngine(
            "_template",
            log_file=os.devnull,
            storage_dir=self.temp_dir.name,
        )

    def tearDown(self):
        self.sim.stop()
        self.province_patch.stop()
        self.map_patch.stop()
        self.temp_dir.cleanup()

    def test_idle_recovery_does_not_reduce_morale_above_recovery_cap(self):
        unit = next(iter(self.sim.units.values()))
        self.assertGreater(unit.morale, unit.max_org)
        before = unit.morale
        unit.status = "IDLE"
        unit.update_position(0.25, self.sim)
        self.assertEqual(unit.morale, before)

    def test_save_load_restores_active_mission_fields_and_pauses(self):
        unit = next(iter(self.sim.units.values()))
        unit.status = "AIRSTRIKE_OUTBOUND"
        unit.set_order_role("assault")
        unit.base_lon, unit.base_lat = unit.lon, unit.lat
        unit.target_lon, unit.target_lat = unit.lon + 1.0, unit.lat + 1.0
        unit.waypoints = [(unit.target_lon, unit.target_lat)]
        self.sim.is_paused = False
        self.sim.save_game("mission")

        unit.status = "IDLE"
        unit.set_order_role("hold")
        unit.base_lon = unit.base_lat = None
        unit.waypoints = []
        loaded, message = self.sim.load_game("mission")

        self.assertTrue(loaded, message)
        restored = self.sim.units[unit.id]
        self.assertEqual(restored.status, "AIRSTRIKE_OUTBOUND")
        self.assertTrue(restored.is_attack_move)
        self.assertTrue(restored.has_order_role("assault"))
        self.assertIsNotNone(restored.base_lon)
        self.assertEqual(restored.waypoints, [(unit.target_lon, unit.target_lat)])
        self.assertTrue(self.sim.is_paused)

    def test_corrupt_save_does_not_partially_replace_live_state(self):
        self.sim.game_hours = 7.5
        original_ids = list(self.sim.units)
        (Path(self.temp_dir.name) / "save_broken.json").write_text("{not json", encoding="utf-8")
        loaded, _message = self.sim.load_game("broken")
        self.assertFalse(loaded)
        self.assertEqual(self.sim.game_hours, 7.5)
        self.assertEqual(list(self.sim.units), original_ids)

    def test_heartbeat_can_be_stopped_for_remount(self):
        worker = threading.Thread(target=self.sim.run_clock)
        worker.start()
        time.sleep(0.05)
        self.sim.stop()
        worker.join(timeout=0.5)
        self.assertFalse(worker.is_alive())

    def test_recovery_rate_comes_from_the_dlc_rules(self):
        package = load_dlc_package("_template")
        custom_rules = deepcopy(package.rules)
        custom_rules["recovery"]["idle_morale_per_hour"] = 8.0
        custom_package = replace(package, rules=custom_rules)
        with tempfile.TemporaryDirectory() as directory:
            simulation = engine_module.SimulationEngine(
                "_template",
                package=custom_package,
                log_file=os.devnull,
                storage_dir=directory,
            )
            try:
                unit = next(iter(simulation.units.values()))
                unit.morale = 0.0
                unit.status = "IDLE"
                unit.update_position(0.5, simulation)
                self.assertEqual(unit.morale, 4.0)
            finally:
                simulation.stop()

    def test_fixed_unit_profile_comes_from_the_dlc_rules(self):
        package = load_dlc_package("_template")
        unit_data = deepcopy(next(iter(package.units.values())))
        unit_data["unit_type"] = "AIR_FORCE"
        unit_data["composition"] = {}
        unit = unit_module.MilitaryUnit(
            "rule_air_unit",
            unit_data,
            package.weapons,
            package.battalions,
            package.rules,
        )
        profile = package.rules["unit_types"]["AIR_FORCE"]
        self.assertEqual(unit.speed, profile["fixed_stats"]["speed_kmh"])
        self.assertEqual(unit.active_fire_range, profile["fire_range_km"])
        self.assertIn(package.rules["missions"]["airstrike"]["capability"], unit.get_capabilities())

    def test_combat_and_political_rules_execute_without_core_type_ids(self):
        first, second = list(self.sim.units.values())[:2]
        first.lon = second.lon = 0.0
        first.lat = second.lat = 0.0
        first.current_province = second.current_province = "Test Province"
        first.status = second.status = "IDLE"
        before = first.personnel + second.personnel
        self.sim.combat_tick(0.1)
        self.assertLess(first.personnel + second.personnel, before)

        second.personnel = 0.0
        self.sim.province_influence.clear()
        self.sim.political_tick(1.0)
        self.assertGreater(self.sim.province_influence["Test Province"], 0.0)

    def test_relocate_advances_but_assault_halts_at_detected_contact(self):
        mover, enemy = list(self.sim.units.values())[:2]
        mover.lon = 0.0
        mover.lat = enemy.lat = 0.0
        enemy.lon = 0.033
        mover.status = "MOVING"
        mover.waypoints = [(1.0, 0.0)]
        self.sim.detected_units[enemy.id] = {"ttl": 10.0, "factions": [mover.faction]}

        mover.set_order_role("assault")
        mover.update_position(0.1, self.sim)
        self.assertEqual(mover.lon, 0.0)

        mover.set_order_role("relocate")
        mover.update_position(0.1, self.sim)
        self.assertGreater(mover.lon, 0.0)

    def test_relocating_unit_holds_ranged_fire_while_defender_returns_fire(self):
        mover, defender = list(self.sim.units.values())[:2]
        mover.lon = 0.0
        mover.lat = defender.lat = 0.0
        defender.lon = 0.033
        mover.status = "MOVING"
        mover.waypoints = [(1.0, 0.0)]
        mover.set_order_role("relocate")
        defender.status = "IDLE"
        defender.set_order_role("hold")
        self.sim.detected_units = {
            mover.id: {"ttl": 10.0, "factions": [defender.faction]},
            defender.id: {"ttl": 10.0, "factions": [mover.faction]},
        }
        mover_before = mover.personnel
        defender_before = defender.personnel

        with patch.object(engine_module.random, "random", return_value=1.0):
            self.sim.combat_tick(0.1)

        self.assertLess(mover.personnel, mover_before)
        self.assertEqual(defender.personnel, defender_before)

    def test_fortification_consumes_resources_and_completes_as_defense(self):
        unit = next(iter(self.sim.units.values()))
        defense = self.sim.rules["defense"]
        maximum = float(self.sim.rules["recovery"]["maximum_entrenchment"])
        unit.supply = 50.0
        unit.fatigue = 0.0
        unit.entrenchment = maximum - 0.05
        unit.status = self.sim.rules["orders"]["fortifying_status"]
        unit.stance = "AGGRESSIVE"
        unit.set_order_role("fortify")

        unit.update_position(1.0, self.sim)

        self.assertEqual(unit.entrenchment, maximum)
        self.assertLess(unit.supply, 50.0)
        self.assertGreater(unit.fatigue, 0.0)
        self.assertEqual(unit.status, self.sim.rules["orders"]["defending_status"])
        self.assertTrue(unit.has_order_role("defend"))
        self.assertEqual(unit.stance, "AGGRESSIVE")

        self.sim.save_game("prepared_defense")
        unit.entrenchment = 0.0
        unit.status = "IDLE"
        unit.set_order_role("hold")
        loaded, message = self.sim.load_game("prepared_defense")
        self.assertTrue(loaded, message)
        restored = self.sim.units[unit.id]
        self.assertEqual(restored.entrenchment, maximum)
        self.assertEqual(restored.status, self.sim.rules["orders"]["defending_status"])
        self.assertTrue(restored.has_order_role("defend"))


class ServerRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.map_patch = patch.object(engine_module, "MapEngine", FakeMapEngine)
        self.province_patch = patch.object(engine_module, "ProvinceEngine", FakeProvinceEngine)
        self.map_patch.start()
        self.province_patch.start()
        self.sim = engine_module.SimulationEngine(
            "_template",
            log_file=os.devnull,
            storage_dir=self.temp_dir.name,
        )
        server.engine = self.sim
        server.physics_thread = None
        self.client = server.app.test_client()

    def tearDown(self):
        self.sim.stop()
        server.engine = None
        server.physics_thread = None
        self.province_patch.stop()
        self.map_patch.stop()
        self.temp_dir.cleanup()

    def test_status_page_exists(self):
        response = self.client.get("/status")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"readiness check", response.data)

    def test_malformed_and_unknown_commands_are_errors(self):
        cases = [
            (None, 400),
            ({"command": "speed"}, 400),
            ({"command": "speed nan"}, 400),
            ({"command": "speed -1"}, 400),
            ({"command": "unknown"}, 400),
            ({"command": "stance missing RECON"}, 404),
        ]
        for payload, expected_status in cases:
            with self.subTest(payload=payload):
                response = self.client.post("/api/command", json=payload)
                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(response.get_json()["status"], "error")

    def test_valid_speed_and_stance_commands_apply(self):
        unit_id = next(iter(self.sim.units))
        self.sim.units[unit_id].set_order_role("assault")
        speed_response = self.client.post("/api/command", json={"command": "speed 5"})
        stance_response = self.client.post("/api/command", json={"command": f"stance {unit_id} RECON"})
        self.assertEqual(speed_response.status_code, 200)
        self.assertEqual(stance_response.status_code, 200)
        self.assertEqual(self.sim.time_multiplier, 5.0)
        self.assertEqual(self.sim.units[unit_id].stance, "RECON")
        self.assertTrue(self.sim.units[unit_id].has_order_role("assault"))

    def test_admin_rename_conflict_preserves_both_units(self):
        first_id, second_id = list(self.sim.units)[:2]
        first_personnel = self.sim.units[first_id].personnel
        response = self.client.post(
            "/api/admin_edit",
            json={"original_id": first_id, "id": second_id, "personnel": 1},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn(first_id, self.sim.units)
        self.assertIn(second_id, self.sim.units)
        self.assertEqual(self.sim.units[first_id].personnel, first_personnel)

    def test_editor_template_is_loaded_from_dlc(self):
        response = self.client.get("/api/editor_template")
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "ok")
        self.assertIn("scenario", data)
        self.assertIn("units", data)
        self.assertEqual(data["rules"]["schema_version"], 1)
        self.assertNotIn("orders", data["rules"])
        self.assertNotIn("stances", data["rules"])
        self.assertIn("orders", data["doctrine"])
        self.assertIn("stances", data["doctrine"])

    def test_registry_exposes_active_dlc_rules(self):
        response = self.client.get("/api/registry")
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["rules"]["schema_version"], 1)
        self.assertIn(self.sim.rules["unit_defaults"]["stance"], data["rules"]["stances"])

    def test_airdrop_rejects_zero_strength_and_returns_visible_unit_data(self):
        base_payload = {
            "id": "airdrop_test",
            "name": "Airdrop Test",
            "faction": "FACTION_A",
            "personnel": 0,
            "equipment_level": 1,
            "lon": 0,
            "lat": 0,
            "unit_type": "ARMY",
            "stance": "DEFENSIVE",
            "composition": {"general": 1},
            "primary_weapon": "standard",
        }
        rejected = self.client.post("/api/edit_unit", json=base_payload)
        self.assertEqual(rejected.status_code, 400)

        base_payload["personnel"] = self.sim.battalion_registry["general"]["size"]
        accepted = self.client.post("/api/edit_unit", json=base_payload)
        data = accepted.get_json()
        self.assertEqual(accepted.status_code, 200)
        self.assertGreater(data["unit"]["personnel"], 0)
        self.assertEqual(data["unit"]["order_mode"], self.sim.units["airdrop_test"].order_id("hold"))
        self.assertIn("airdrop_test", self.client.get("/api/state").get_json()["units"])

    def test_move_assault_defend_and_fortify_commands_have_explicit_modes(self):
        unit_id = next(iter(self.sim.units))
        unit = self.sim.units[unit_id]
        unit.stance = "RECON"

        move = self.client.post("/api/command", json={"command": f"move {unit_id} 2 0"})
        self.assertEqual(move.status_code, 200)
        self.assertTrue(unit.has_order_role("relocate"))
        self.assertEqual(unit.status, "MOVING")
        self.assertEqual(unit.stance, "RECON")

        assault = self.client.post("/api/command", json={"command": f"attack {unit_id} 2 0"})
        self.assertEqual(assault.status_code, 200)
        self.assertTrue(unit.has_order_role("assault"))
        self.assertEqual(unit.stance, "RECON")

        defend = self.client.post("/api/command", json={"command": f"defend {unit_id}"})
        self.assertEqual(defend.status_code, 200)
        self.assertTrue(unit.has_order_role("defend"))
        self.assertEqual(unit.status, self.sim.rules["orders"]["defending_status"])
        self.assertEqual(unit.stance, "RECON")

        unit.supply = float(self.sim.rules["defense"]["minimum_supply_to_start"])
        fortify = self.client.post("/api/command", json={"command": f"fortify {unit_id}"})
        self.assertEqual(fortify.status_code, 200)
        self.assertTrue(unit.has_order_role("fortify"))
        self.assertEqual(unit.status, self.sim.rules["orders"]["fortifying_status"])
        self.assertEqual(unit.stance, "RECON")


class LoaderAndGISRegressionTests(unittest.TestCase):
    def test_dlc_path_traversal_is_rejected(self):
        with self.assertRaises(DLCValidationError):
            resolve_dlc_path("../afghan")

    def test_template_is_valid_but_not_listed_as_a_campaign(self):
        package = load_dlc_package("_template")
        self.assertEqual(package.dlc_id, "_template")
        self.assertEqual(package.rules["schema_version"], 1)
        self.assertNotIn("orders", package.source_rules)
        self.assertNotIn("stances", package.source_rules)
        self.assertIn("orders", package.rules)
        self.assertIn("stances", package.rules)
        self.assertNotIn("_template", [entry["id"] for entry in scan_dlcs()])

    def test_dlc_cannot_override_core_command_doctrine(self):
        with tempfile.TemporaryDirectory() as directory:
            dlc_root = Path(directory)
            broken = dlc_root / "broken"
            shutil.copytree(resolve_dlc_path("_template"), broken)
            rules_path = broken / "rules.json"
            rules = json.loads(rules_path.read_text(encoding="utf-8"))
            rules["stances"] = {"CUSTOM": {}}
            rules_path.write_text(json.dumps(rules), encoding="utf-8")
            with patch.object(loader_module, "DLC_ROOT", dlc_root):
                with self.assertRaises(DLCValidationError) as context:
                    loader_module.load_dlc_package("broken")
            self.assertIn("must not redefine core doctrine sections", str(context.exception))

    def test_every_package_receives_an_isolated_copy_of_core_doctrine(self):
        template = load_dlc_package("_template")
        afghan = load_dlc_package("afghan")
        self.assertEqual(template.rules["orders"], afghan.rules["orders"])
        self.assertEqual(template.rules["stances"], afghan.rules["stances"])

        template.rules["stances"]["RECON"]["movement_multiplier"] = 99
        fresh = load_dlc_package("_template")
        self.assertEqual(fresh.rules["stances"]["RECON"]["movement_multiplier"], 1.15)

    def test_incomplete_rules_are_rejected_before_mount(self):
        with tempfile.TemporaryDirectory() as directory:
            dlc_root = Path(directory)
            broken = dlc_root / "broken"
            shutil.copytree(resolve_dlc_path("_template"), broken)
            rules_path = broken / "rules.json"
            rules = json.loads(rules_path.read_text(encoding="utf-8"))
            del rules["combat"]["direct"]["attack_scale"]
            rules_path.write_text(json.dumps(rules), encoding="utf-8")
            with patch.object(loader_module, "DLC_ROOT", dlc_root):
                with self.assertRaises(DLCValidationError) as context:
                    loader_module.load_dlc_package("broken")
            self.assertIn("combat.direct.attack_scale", str(context.exception))

    def test_battalion_complements_are_required_for_deployment_estimates(self):
        with tempfile.TemporaryDirectory() as directory:
            dlc_root = Path(directory)
            broken = dlc_root / "broken"
            shutil.copytree(resolve_dlc_path("_template"), broken)
            battalions_path = broken / "battalions.json"
            battalions = json.loads(battalions_path.read_text(encoding="utf-8"))
            del battalions["general"]["size"]
            battalions_path.write_text(json.dumps(battalions), encoding="utf-8")
            with patch.object(loader_module, "DLC_ROOT", dlc_root):
                with self.assertRaises(DLCValidationError) as context:
                    loader_module.load_dlc_package("broken")
            self.assertIn("Battalion [general] size", str(context.exception))

        afghan = load_dlc_package("afghan")
        self.assertTrue(all(float(profile["size"]) > 0 for profile in afghan.battalions.values()))

    def test_missing_center_is_derived_from_dlc_bounds(self):
        package = load_dlc_package("afghan")
        self.assertEqual(package.scenario["map_center"], [34.0, 67.5])

    def test_registry_activation_is_atomic(self):
        old_weapons = dict(unit_module.WEAPON_REGISTRY)
        old_battalions = dict(unit_module.BATTALION_REGISTRY)
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "weapons.json").write_text(json.dumps({"w": {"name": "W", "range": 1}}), encoding="utf-8")
                (root / "battalions.json").write_text(json.dumps({"b": {"name": "B"}}), encoding="utf-8")
                unit_module.load_dlc_registries(root)
                activated_weapons = dict(unit_module.WEAPON_REGISTRY)
                activated_battalions = dict(unit_module.BATTALION_REGISTRY)
                (root / "battalions.json").write_text("{broken", encoding="utf-8")
                with self.assertRaises(json.JSONDecodeError):
                    unit_module.load_dlc_registries(root)
                self.assertEqual(unit_module.WEAPON_REGISTRY, activated_weapons)
                self.assertEqual(unit_module.BATTALION_REGISTRY, activated_battalions)
        finally:
            unit_module.WEAPON_REGISTRY.clear()
            unit_module.WEAPON_REGISTRY.update(old_weapons)
            unit_module.BATTALION_REGISTRY.clear()
            unit_module.BATTALION_REGISTRY.update(old_battalions)

    def test_grid_boundaries_round_trip_and_fallback_is_configured(self):
        config = {
            "grid_resolution": [20, 20],
            "dem_analysis_resolution": [40, 40],
            "bounds": {"min_lon": -2, "max_lon": 3, "min_lat": -4, "max_lat": 5},
            "fallback_elevation_m": 42,
            "terrain_elevation_scale_m": 5000,
            "terrain_cost_multiplier": 50,
            "terrain_cost_exponent": 2,
            "pathing": {
                "road_cost": 0.5,
                "river_penalty_default": 50,
                "river_penalty_heavy": 500,
                "river_penalty_engineer": 10,
            },
            "dem_dir": "",
            "dem_file": "",
            "roads_file": "",
            "rivers_file": "",
        }
        geography_rules = load_dlc_package("_template").rules["geography"]
        map_engine = MapEngine(config, geography_rules)
        self.assertEqual(map_engine.grid_to_lonlat(*map_engine.lonlat_to_grid(3, -4)), (3.0, -4.0))
        self.assertEqual(map_engine.get_elevation(0, 0), 42.0)
        self.assertTrue(math.isclose(map_engine.get_terrain_complexity(0, 0), 0.0))


if __name__ == "__main__":
    unittest.main()
