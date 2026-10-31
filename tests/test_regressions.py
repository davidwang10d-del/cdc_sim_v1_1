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
        self.use_real_dem = False
        self.road_matrix = None
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
        self.provinces = []

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
        metadata = self.sim.save_slot_metadata("broken")
        self.assertEqual(metadata["condition"], "invalid")
        self.assertFalse(metadata["can_load"])

    def test_checkpoint_os_errors_do_not_disclose_storage_paths(self):
        checkpoint = Path(self.temp_dir.name) / "save_private.json"
        checkpoint.write_text("{}", encoding="utf-8")
        private_path = str(checkpoint.resolve())
        with patch("builtins.open", side_effect=OSError(f"access denied: {private_path}")):
            loaded, message = self.sim.load_game("private")
            metadata = self.sim.save_slot_metadata("private")
        self.assertFalse(loaded)
        self.assertEqual(message, "Checkpoint could not be read")
        self.assertEqual(metadata["message"], "Checkpoint could not be read")
        self.assertNotIn(private_path, message)
        self.assertNotIn(private_path, metadata["message"])

    def test_manual_save_records_clear_checkpoint_metadata(self):
        self.sim.game_hours = 26.5
        filename = self.sim.save_game("slot_1")

        save_document = json.loads(filename.read_text(encoding="utf-8"))
        metadata = self.sim.save_slot_metadata("slot_1")
        self.assertIn("saved_at_utc", save_document)
        self.assertEqual(save_document["format_version"], 4)
        self.assertIn("province_politics", save_document)
        self.assertIn("installations", save_document)
        self.assertEqual(save_document["scenario_name"], self.sim.scenario_data["scenario_name"])
        self.assertEqual(metadata["condition"], "available")
        self.assertTrue(metadata["can_load"])
        self.assertEqual(metadata["game_hours"], 26.5)
        self.assertEqual(metadata["unit_count"], len(self.sim.units))
        self.assertEqual(metadata["installation_count"], len(self.sim.installations))

    def test_missing_gis_layers_report_their_safe_defaults(self):
        status = self.sim.get_gis_status()
        features = {feature["id"]: feature for feature in status["features"]}

        self.assertEqual(status["enabled_count"], 0)
        self.assertEqual(set(features), {"terrain_dem", "roads", "rivers", "provinces"})
        self.assertTrue(all(feature["mode"] == "default" for feature in features.values()))
        self.assertIn("Flat terrain", features["terrain_dem"]["detail"])
        self.assertIn("Base terrain movement", features["roads"]["detail"])
        self.assertIn("No river-crossing penalty", features["rivers"]["detail"])
        self.assertIn("Unknown/Unmapped", features["provinces"]["detail"])

    def test_mount_ignores_old_autosave_and_autosave_slot_is_disabled(self):
        self.sim.game_hours = 42.0
        manual_file = self.sim.save_game("legacy_source")
        shutil.copyfile(manual_file, Path(self.temp_dir.name) / "save_autosave.json")

        with self.assertRaisesRegex(ValueError, "Autosave is disabled"):
            self.sim.save_game("autosave")

        fresh = engine_module.SimulationEngine(
            "_template",
            log_file=os.devnull,
            storage_dir=self.temp_dir.name,
        )
        try:
            self.assertEqual(fresh.game_hours, 0.0)
            self.assertTrue(fresh.is_paused)
        finally:
            fresh.stop()

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

    def test_city_influence_blends_with_terrain_only_inside_its_area(self):
        self.sim.cities = [{
            "id": "test_city",
            "name": "Test City",
            "description": "",
            "lon": 0.0,
            "lat": 0.0,
            "area_km2": math.pi * 100.0,
            "influence_rate": 0.75,
        }]
        self.assertTrue(math.isclose(self.sim.get_terrain_complexity(0.0, 0.0), 0.75))
        self.assertTrue(math.isclose(self.sim.get_terrain_complexity(1.0, 0.0), 0.0))

        self.sim.cities[0]["influence_rate"] = 0.0
        self.assertTrue(math.isclose(self.sim.get_terrain_complexity(0.0, 0.0), 0.0))

    def test_city_edits_survive_manual_save_and_restore(self):
        city = self.sim.validate_city({
            "id": "new_york",
            "name": "New York",
            "description": "Major urban area",
            "lon": -74.006,
            "lat": 40.7128,
            "area_km2": 778.2,
            "influence_rate": 1,
        })
        self.sim.cities = [city]
        self.sim.save_game("city_state")
        self.sim.cities = []

        loaded, message = self.sim.load_game("city_state")

        self.assertTrue(loaded, message)
        self.assertEqual(self.sim.cities, [city])

    def test_faction_politics_survive_save_and_legacy_scores_migrate(self):
        self.sim.set_province_politics({
            "province": "Test Province", "faction": "FACTION_A",
            "civilian_sentiment": 0.25, "occupation": 0.7,
        })
        filename = self.sim.save_game("politics")
        self.sim.province_politics.clear()
        loaded, message = self.sim.load_game("politics")
        self.assertTrue(loaded, message)
        restored = self.sim.province_politics["Test Province"]["factions"]["FACTION_A"]
        self.assertEqual(restored["civilian_sentiment"], 0.25)
        self.assertEqual(restored["occupation"], 0.7)

        legacy = json.loads(filename.read_text(encoding="utf-8"))
        legacy["format_version"] = 2
        legacy.pop("province_politics")
        legacy["provinces"] = {"Legacy Province": -50}
        legacy_path = Path(self.temp_dir.name) / "save_legacy_politics.json"
        legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
        loaded, message = self.sim.load_game("legacy_politics")
        self.assertTrue(loaded, message)
        migrated = self.sim.province_politics["Legacy Province"]["factions"]["LEGACY"]
        self.assertEqual(migrated["civilian_sentiment"], -0.5)

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

    def test_weapon_attack_scales_with_battalions_and_changes_by_range_band(self):
        package = load_dlc_package("_template")
        one = next(iter(self.sim.units.values()))
        doubled_data = deepcopy(next(iter(package.units.values())))
        doubled_data["composition"] = {"general": 2}
        doubled_data["personnel"] = 2000
        doubled = unit_module.MilitaryUnit(
            "two_battalions",
            doubled_data,
            package.weapons,
            package.battalions,
            package.rules,
        )

        close_one = one.get_weapon_attack_totals(0.1, {"direct_fire"})
        close_two = doubled.get_weapon_attack_totals(0.1, {"direct_fire"})
        far_one = one.get_weapon_attack_totals(0.75, {"direct_fire"})
        outside = one.get_weapon_attack_totals(1.01, {"direct_fire"})

        self.assertAlmostEqual(close_two["soft_attack"], close_one["soft_attack"] * 2)
        self.assertAlmostEqual(close_two["hard_attack"], close_one["hard_attack"] * 2)
        self.assertLess(far_one["soft_attack"], close_one["soft_attack"])
        self.assertEqual(outside["soft_attack"], 0.0)
        self.assertEqual(doubled.to_dict()["weapon_loadout"][0]["quantity"], 2.0)
        self.assertNotIn("personnel_reference", package.rules["combat"]["direct"])

        full_strength = one.calculate_weapon_attack(0.1, 1.0, 0.0, 0.5, roles={"direct_fire"})
        one.personnel *= 0.5
        half_strength = one.calculate_weapon_attack(0.1, 1.0, 0.0, 0.5, roles={"direct_fire"})
        self.assertAlmostEqual(half_strength["effective_attack"], full_strength["effective_attack"] * 0.5)
        one.personnel *= 2.0
        quarter_frontage = one.calculate_weapon_attack(
            0.1,
            1.0,
            0.0,
            0.5,
            roles={"direct_fire"},
            engaged_personnel=one.nominal_personnel * 0.25,
        )
        self.assertAlmostEqual(quarter_frontage["effective_attack"], full_strength["effective_attack"] * 0.25)

    def test_only_in_range_weapons_fire_and_armor_generation_stays_separate(self):
        package = load_dlc_package("test")
        unit = unit_module.MilitaryUnit(
            "range_test",
            deepcopy(package.units["red_combined_arms"]),
            package.weapons,
            package.battalions,
            package.rules,
        )

        close = unit.calculate_weapon_attack(
            0.1, 0.5, 0.0, 0.25, roles={"direct_fire"}
        )
        far = unit.calculate_weapon_attack(
            25.0, 0.5, 0.0, 0.25, roles={"direct_fire"}
        )
        armored = unit.calculate_weapon_attack(
            0.1, 0.5, 10000.0, 0.25, roles={"direct_fire"}
        )

        self.assertGreater(len(close["weapons_used"]), 1)
        self.assertEqual(far["weapons_used"], ["field_howitzer"])
        self.assertAlmostEqual(armored["soft_component"], close["soft_component"])
        self.assertAlmostEqual(armored["hard_component"], close["hard_component"] * 0.25)
        self.assertGreater(unit.armor_generation, 0.0)
        self.assertEqual(unit.to_dict()["stats"]["armor_generation"], unit.armor_generation)
        self.assertTrue(all("generation" in weapon for weapon in unit.to_dict()["weapon_loadout"]))

    def test_bombardment_power_comes_from_weapon_groups_not_crew_headcount(self):
        package = load_dlc_package("_template")
        artillery_data = deepcopy(next(iter(package.units.values())))
        artillery_data.update({
            "unit_type": "ARTILLERY",
            "composition": {"artillery": 1},
            "primary_weapon": "standard_howitzer",
            "personnel": 300,
        })
        artillery = unit_module.MilitaryUnit(
            "weapon_artillery",
            artillery_data,
            package.weapons,
            package.battalions,
            package.rules,
        )
        target = list(self.sim.units.values())[1]
        artillery.lon = target.lon = 0.0
        artillery.lat = target.lat = 0.0
        artillery.target_lon = target.lon
        artillery.target_lat = target.lat
        self.sim.units[artillery.id] = artillery
        target.personnel = 5000.0
        first = self.sim.resolve_bombardment_tick(artillery, 0.5)

        target.personnel = 5000.0
        target.morale = 70.0
        target.suppression = 0.0
        artillery.personnel = 3000.0
        second = self.sim.resolve_bombardment_tick(artillery, 0.5)

        target.personnel = 5000.0
        target.morale = 70.0
        target.suppression = 0.0
        artillery.composition = {"artillery": 2}
        artillery.parse_composition()
        third = self.sim.resolve_bombardment_tick(artillery, 0.5)

        self.assertAlmostEqual(second["casualties"], first["casualties"])
        self.assertAlmostEqual(third["firepower"], first["firepower"] * 2)
        self.assertGreater(third["casualties"], second["casualties"])

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
        self.sim.province_politics.clear()
        self.sim.political_tick(1.0)
        politics = self.sim.province_politics["Test Province"]
        self.assertIn(first.faction, politics["factions"])
        self.assertGreater(politics["factions"][first.faction]["occupation"], 0.0)

    def test_close_hostile_armies_auto_acquire_contact_and_exchange_fire(self):
        first, second = list(self.sim.units.values())[:2]
        first.lon = second.lon = 0.0
        first.lat = second.lat = 0.0
        first.status = second.status = "MOVING"
        first.set_order_role("relocate")
        second.set_order_role("relocate")
        self.sim.detected_units.clear()
        personnel_before = (first.personnel, second.personnel)

        # Prevent the probabilistic sensor pass from acquiring either unit.
        # Physical close contact must still trigger self-defense for both.
        with patch.object(self.sim, "_try_detect", return_value=None):
            self.sim.combat_tick(0.1)
            self.sim.combat_tick(0.1)

        self.assertLess(first.personnel, personnel_before[0])
        self.assertLess(second.personnel, personnel_before[1])
        self.assertTrue(self.sim._is_detected_by(first.faction, second.id))
        self.assertTrue(self.sim._is_detected_by(second.faction, first.id))
        self.assertEqual(
            sum("[Close Combat]" in entry["message"] for entry in self.sim.structured_logs),
            1,
        )

    def test_moving_army_is_reported_in_live_province_politics_while_paused(self):
        first, *others = list(self.sim.units.values())
        for other in others:
            other.personnel = 0.0
        first.status = "MOVING"
        first.current_province = "Stale Province"
        self.sim.province_politics.clear()
        self.sim.is_paused = True

        self.sim.refresh_province_presence()

        record = self.sim.province_politics["Test Province"]["factions"][first.faction]
        self.assertEqual(first.current_province, "Test Province")
        self.assertEqual(record["military_presence"], 1.0)
        self.assertGreater(record["force_strength"], 0.0)
        self.assertEqual(record["occupation"], 0.0)

    def test_low_morale_never_creates_an_automatic_retreat_order(self):
        first, second = list(self.sim.units.values())[:2]
        first.lon = second.lon = 0.0
        first.lat = second.lat = 0.0
        first.status = second.status = "IDLE"
        first.stance = "STEALTH"
        second.stance = "AGGRESSIVE"
        first.morale = 0.0
        first.waypoints = []
        first.target_lon = first.target_lat = None

        self.sim.combat_tick(0.1)

        self.assertEqual(first.status, "IDLE")
        self.assertEqual(first.waypoints, [])
        self.assertIsNone(first.target_lon)
        self.assertIsNone(first.target_lat)

    def test_coordinate_support_missions_affect_unobserved_hostile_units(self):
        aircraft, target = list(self.sim.units.values())[:2]
        aircraft.unit_type = "AIR_FORCE"
        aircraft.aircraft_type = self.sim.rules["missions"]["airstrike"]["default_aircraft_type"]
        aircraft.composition = {"air_wing": 1}
        aircraft.primary_weapon = "air_ordnance"
        aircraft.personnel = self.sim.battalion_registry["air_wing"]["size"]
        aircraft.parse_composition()
        aircraft.lon = target.lon = 0.0
        aircraft.lat = target.lat = 0.0
        aircraft.target_lon = target.lon
        aircraft.target_lat = target.lat
        self.sim.detected_units = {}

        personnel_before = target.personnel
        airstrike_result = self.sim.resolve_airstrike_impact(aircraft)
        self.assertEqual(airstrike_result["targets_hit"], 1)
        self.assertGreater(airstrike_result["casualties"], 0)
        self.assertLess(target.personnel, personnel_before)

        target.personnel = personnel_before
        target.morale = 70.0
        target.suppression = 0.0
        aircraft.unit_type = "ARTILLERY"
        aircraft.composition = {"artillery": 1}
        aircraft.primary_weapon = "standard_howitzer"
        aircraft.parse_composition()
        aircraft.bombard_casualties = 0.0
        bombard_result = self.sim.resolve_bombardment_tick(aircraft, 0.5)
        self.assertEqual(bombard_result["targets_hit"], 1)
        self.assertGreater(bombard_result["casualties"], 0)
        self.assertLess(target.personnel, personnel_before)
        self.assertEqual(aircraft.bombard_casualties, bombard_result["casualties"])

    def test_airstrike_uses_area_exposure_and_strike_power_not_aircrew_headcount(self):
        aircraft, target = list(self.sim.units.values())[:2]
        aircraft.unit_type = "AIR_FORCE"
        aircraft.aircraft_type = self.sim.rules["missions"]["airstrike"]["default_aircraft_type"]
        aircraft.composition = {"air_wing": 1}
        aircraft.primary_weapon = "air_ordnance"
        aircraft.personnel = self.sim.battalion_registry["air_wing"]["size"]
        aircraft.parse_composition()
        aircraft.target_lon = target.lon
        aircraft.target_lat = target.lat
        strike_band = aircraft.weapon_registry["air_ordnance"]["range_bands"][0]
        strike_band["soft_attack"] = 400.0
        strike_band["hard_attack"] = 300.0
        aircraft.base_soft_attack = 1.0
        aircraft.base_hard_attack = 1.0
        aircraft.supply = 100.0
        aircraft.fatigue = 0.0
        aircraft.suppression = 0.0
        target.personnel = 12000.0
        target.morale = 90.0
        target.suppression = 0.0
        target.entrenchment = 0.0
        target.stance = "AGGRESSIVE"
        target.parse_composition()
        self.sim.detected_units[target.id] = {"ttl": 10.0, "factions": [aircraft.faction]}

        first = self.sim.resolve_airstrike_impact(aircraft)
        first_casualties = first["casualties"]
        self.assertGreater(first_casualties, 1000.0)
        self.assertLess(first_casualties, 1800.0)
        self.assertAlmostEqual(first["exposed_personnel"], 3600.0)
        self.assertGreater(first["morale_loss"], 4.0)
        self.assertLess(first["morale_loss"], 10.0)
        self.assertGreater(first["suppression"], 0.0)

        target.personnel = 12000.0
        target.morale = 90.0
        target.suppression = 0.0
        aircraft.personnel *= 10
        second = self.sim.resolve_airstrike_impact(aircraft)
        self.assertAlmostEqual(second["casualties"], first_casualties)

        target.personnel = 12000.0
        target.morale = 90.0
        target.suppression = 0.0
        strike_band["soft_attack"] = 4000.0
        strike_band["hard_attack"] = 3000.0
        personnel_before_cap = target.personnel
        capped = self.sim.resolve_airstrike_impact(aircraft)
        expected_cap = personnel_before_cap * self.sim.rules["missions"]["airstrike"]["maximum_casualty_fraction"]
        self.assertAlmostEqual(capped["casualties"], expected_cap)
        self.assertEqual(capped["casualty_cap_applied"], 1)

    def test_airstrike_hits_artillery_and_grounded_air_wings_but_skips_airborne_sorties(self):
        package = load_dlc_package("test")
        with tempfile.TemporaryDirectory() as directory:
            simulation = engine_module.SimulationEngine(
                "test",
                package=package,
                log_file=os.devnull,
                storage_dir=directory,
            )
            try:
                aircraft = simulation.units["blue_air_wing"]
                artillery = simulation.units["red_artillery"]
                aircraft.target_lon = artillery.lon
                aircraft.target_lat = artillery.lat
                artillery_before = artillery.personnel

                artillery_result = simulation.resolve_airstrike_impact(aircraft)

                self.assertEqual(artillery_result["targets_hit"], 1)
                self.assertGreater(artillery_result["casualties"], 0.0)
                self.assertLess(artillery.personnel, artillery_before)

                grounded_aircraft = simulation.units["red_air_wing"]
                aircraft.target_lon = grounded_aircraft.lon
                aircraft.target_lat = grounded_aircraft.lat
                grounded_before = grounded_aircraft.personnel

                grounded_result = simulation.resolve_airstrike_impact(aircraft)

                self.assertEqual(grounded_result["targets_hit"], 1)
                self.assertGreater(grounded_result["casualties"], 0.0)
                self.assertLess(grounded_aircraft.personnel, grounded_before)

                grounded_aircraft.personnel = grounded_before
                grounded_aircraft.status = "AIRSTRIKE_OUTBOUND"
                airborne_result = simulation.resolve_airstrike_impact(aircraft)
                self.assertEqual(airborne_result["targets_hit"], 0)
                self.assertEqual(grounded_aircraft.personnel, grounded_before)
            finally:
                simulation.stop()

    def test_personnel_remains_the_current_alive_count(self):
        unit = next(iter(self.sim.units.values()))
        unit.personnel = 1000.0
        unit.morale = 50.0
        unit.supply = 50.0
        unit.fatigue = 50.0
        unit.suppression = 50.0

        self.assertLess(unit.get_readiness(), 1.0)
        self.assertEqual(unit.to_dict()["personnel"], 1000.0)

        self.sim._apply_combat_effects(unit, casualties=125.0, org_loss=10.0, suppression=20.0)
        self.assertEqual(unit.personnel, 875.0)
        self.assertEqual(unit.to_dict()["personnel"], 875.0)
        self.assertNotIn("combat_effective_personnel", unit.to_dict())

        self.sim.save_game("alive_personnel")
        unit.personnel = 1.0
        loaded, message = self.sim.load_game("alive_personnel")
        self.assertTrue(loaded, message)
        restored = self.sim.units[unit.id]
        self.assertEqual(restored.personnel, 875.0)
        faction_state = next(record for record in self.sim.get_committee_state()["factions"] if record["faction"] == restored.faction)
        self.assertEqual(faction_state["active_personnel"], 875)
        self.assertIn("875 living personnel", self.sim.build_sitrep_markdown())

    def test_airborne_sortie_is_not_resolved_as_ground_direct_combat(self):
        aircraft, target = list(self.sim.units.values())[:2]
        aircraft.lon = target.lon = 0.0
        aircraft.lat = target.lat = 0.0
        aircraft.status = "AIRSTRIKE_RTB"
        aircraft.waypoints = [(1.0, 0.0)]
        self.sim.detected_units = {
            aircraft.id: {"ttl": 10.0, "factions": [target.faction]},
            target.id: {"ttl": 10.0, "factions": [aircraft.faction]},
        }
        before = (aircraft.personnel, aircraft.morale, target.personnel, target.morale)

        with patch.object(engine_module.random, "random", return_value=1.0):
            self.sim.combat_tick(0.5)

        self.assertEqual(
            (aircraft.personnel, aircraft.morale, target.personnel, target.morale),
            before,
        )

    def test_live_contact_expiry_is_silent_but_zero_personnel_is_reported(self):
        target = list(self.sim.units.values())[1]
        target.personnel = 100.0
        self.sim.detected_units = {target.id: {"ttl": 0.0, "factions": ["FACTION_A"]}}
        log_start = len(self.sim.structured_logs)

        with patch.object(engine_module.random, "random", return_value=1.0):
            self.sim.detection_tick(0.1)
        live_messages = [entry["message"] for entry in self.sim.structured_logs[log_start:]]
        self.assertFalse(any("vanished into the fog of war" in message for message in live_messages))

        target.personnel = 0.0
        self.sim.detected_units = {target.id: {"ttl": 0.0, "factions": ["FACTION_A"]}}
        with patch.object(engine_module.random, "random", return_value=1.0):
            self.sim.detection_tick(0.1)
        self.assertIn("vanished into the fog of war", self.sim.structured_logs[-1]["message"])

    def test_bombardment_finishes_after_applying_its_last_partial_tick(self):
        artillery, target = list(self.sim.units.values())[:2]
        artillery.lon = target.lon = 0.0
        artillery.lat = target.lat = 0.0
        artillery.target_lon = target.lon
        artillery.target_lat = target.lat
        artillery.status = "BOMBARDING"
        artillery.bombard_timer = 0.25
        artillery.bombard_casualties = 0.0
        artillery.supply = 100.0
        target_before = target.personnel

        artillery.update_position(1.0, self.sim)
        self.assertEqual(artillery.status, "BOMBARDING")
        self.sim.combat_tick(1.0)

        self.assertLess(target.personnel, target_before)
        self.assertEqual(artillery.status, "IDLE")
        self.assertIsNone(artillery.target_lon)
        self.assertFalse(hasattr(artillery, "bombard_timer"))

    def test_legacy_routing_save_is_loaded_without_retreating(self):
        original = next(iter(self.sim.units.values()))
        saved = original.to_dict()
        saved.update({
            "status": "ROUTING",
            "waypoints": [(original.lon + 1.0, original.lat + 1.0)],
            "target_lon": original.lon + 1.0,
            "target_lat": original.lat + 1.0,
        })

        restored = unit_module.MilitaryUnit(
            "legacy_routing",
            saved,
            self.sim.weapon_registry,
            self.sim.battalion_registry,
            self.sim.rules,
        )

        self.assertEqual(restored.status, self.sim.rules["unit_defaults"]["status"])
        self.assertEqual(restored.waypoints, [])
        self.assertIsNone(restored.target_lon)
        self.assertIsNone(restored.target_lat)
        self.assertTrue(restored.has_order_role(self.sim.rules["orders"]["default_role"]))

    def test_hostile_faction_presence_creates_contested_control(self):
        first, second = list(self.sim.units.values())[:2]
        first.current_province = second.current_province = "Test Province"
        first.status = second.status = "IDLE"
        self.sim.set_province_politics({
            "province": "Test Province", "faction": first.faction,
            "civilian_sentiment": 0.5, "occupation": 0.4,
        })
        self.sim.set_province_politics({
            "province": "Test Province", "faction": second.faction,
            "civilian_sentiment": -0.5, "occupation": 0.4,
        })

        self.sim.political_tick(1.0)

        state = self.sim.province_politics["Test Province"]
        self.assertTrue(state["contested"])
        self.assertIsNone(state["controller"])
        self.assertEqual(set(state["factions"]), {first.faction, second.faction})

    def test_civilian_sentiment_defaults_to_neutral_and_is_faction_specific(self):
        first, second = list(self.sim.units.values())[:2]
        self.sim.set_province_politics({
            "province": "Test Province", "faction": first.faction,
            "civilian_sentiment": 1, "occupation": 0,
        })
        self.sim.set_province_politics({
            "province": "Test Province", "faction": second.faction,
            "occupation": 0,
        })
        records = self.sim.province_politics["Test Province"]["factions"]
        self.assertEqual(records[first.faction]["civilian_sentiment"], 1)
        self.assertEqual(records[second.faction]["civilian_sentiment"], 0)
        with self.assertRaisesRegex(ValueError, "between -1 and 1"):
            self.sim.set_province_politics({
                "province": "Test Province", "faction": "Invalid",
                "civilian_sentiment": -1.1, "occupation": 0,
            })

    def test_assault_closes_through_ranged_contact_but_halts_at_close_contact(self):
        mover, enemy = list(self.sim.units.values())[:2]
        mover.lon = 0.0
        mover.lat = enemy.lat = 0.0
        enemy.lon = 0.033
        mover.status = "MOVING"
        mover.waypoints = [(1.0, 0.0)]
        self.sim.detected_units[enemy.id] = {"ttl": 10.0, "factions": [mover.faction]}

        mover.set_order_role("assault")
        mover.update_position(0.1, self.sim)
        self.assertGreater(mover.lon, 0.0)

        mover.lon = 0.0
        enemy.lon = 0.001
        mover.update_position(0.1, self.sim)
        self.assertEqual(mover.lon, 0.0)

        enemy.lon = 0.033
        mover.set_order_role("relocate")
        mover.update_position(0.1, self.sim)
        self.assertGreater(mover.lon, 0.0)

    def test_relocate_reroutes_around_detected_contact_and_keeps_destination(self):
        class AvoidanceRecordingMapEngine(FakeMapEngine):
            def __init__(self):
                super().__init__(None, None)
                self.path_calls = []

            def lonlat_to_grid(self, lon, lat):
                return round(float(lon) * 100), round(float(lat) * 100)

            def find_path(self, *, target_lon, target_lat, avoidance_zones=None, **kwargs):
                self.path_calls.append({
                    "target": (target_lon, target_lat),
                    "avoidance_zones": deepcopy(avoidance_zones),
                    "kwargs": kwargs,
                })
                return [(0.0, 0.2), (1.0, 0.2), (target_lon, target_lat)]

        mover, enemy = list(self.sim.units.values())[:2]
        mover.lon = mover.lat = 0.0
        mover.radius = 1.0
        mover.status = "MOVING"
        mover.set_order_role("relocate")
        mover.target_lon, mover.target_lat = 1.0, 0.0
        mover.waypoints = [(mover.target_lon, mover.target_lat)]
        enemy.lon, enemy.lat = 0.3, 0.0
        enemy.radius = 1.0
        enemy.direct_fire_range = 5.0
        map_engine = AvoidanceRecordingMapEngine()
        self.sim.map_engine = map_engine

        self.assertFalse(self.sim.refresh_relocation_route(mover))
        self.assertEqual(map_engine.path_calls, [])

        self.sim.detected_units[enemy.id] = {
            "ttl": 10.0,
            "factions": [mover.faction],
        }
        self.assertTrue(self.sim.refresh_relocation_route(mover))

        self.assertEqual(mover.waypoints, [(0.0, 0.2), (1.0, 0.2), (1.0, 0.0)])
        self.assertEqual((mover.target_lon, mover.target_lat), (1.0, 0.0))
        self.assertEqual(len(map_engine.path_calls), 1)
        zones = map_engine.path_calls[0]["avoidance_zones"]
        self.assertEqual([zone["id"] for zone in zones], [enemy.id])
        self.assertGreater(zones[0]["radius_km"], enemy.direct_fire_range)
        self.assertEqual(mover.relocation_avoidance_contacts[0]["id"], enemy.id)
        self.assertEqual(mover.relocation_reroute_count, 1)
        self.assertFalse(self.sim.refresh_relocation_route(mover))
        self.assertEqual(len(map_engine.path_calls), 1)

        self.sim.save_game("avoidance_route")
        loaded, message = self.sim.load_game("avoidance_route")
        self.assertTrue(loaded, message)
        restored = self.sim.units[mover.id]
        self.assertEqual((restored.target_lon, restored.target_lat), (1.0, 0.0))
        self.assertEqual(restored.relocation_avoidance_contacts[0]["id"], enemy.id)
        self.assertEqual(restored.relocation_reroute_count, 1)

    def test_automatic_contact_detours_apply_only_to_relocate(self):
        mover, enemy = list(self.sim.units.values())[:2]
        mover.lon = mover.lat = 0.0
        mover.status = "MOVING"
        mover.target_lon, mover.target_lat = 1.0, 0.0
        mover.waypoints = [(1.0, 0.0)]
        enemy.lon, enemy.lat = 0.3, 0.0
        self.sim.detected_units[enemy.id] = {
            "ttl": 10.0,
            "factions": [mover.faction],
        }

        for role in ("assault", "route"):
            mover.set_order_role(role)
            self.assertFalse(self.sim.refresh_relocation_route(mover, force=True))

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

    def test_persistent_fort_construction_consumes_supply_adds_cover_and_survives_save(self):
        builder = self.sim.units["faction_a_unit"]
        builder.supply = 100.0
        builder.fatigue = 0.0
        cover_before = self.sim._cover_multiplier(builder, 0.0)

        installation, resumed = self.sim.start_installation_construction(
            builder.id, "FORTIFICATION"
        )

        self.assertFalse(resumed)
        self.assertEqual(installation.status, "UNDER_CONSTRUCTION")
        self.assertEqual(builder.status, "CONSTRUCTING")
        self.sim.installation_tick(12.0)
        self.assertAlmostEqual(installation.construction_progress, 0.5)
        self.assertAlmostEqual(builder.supply, 85.0)
        self.assertGreater(builder.fatigue, 0.0)

        self.sim.installation_tick(12.0)
        self.assertEqual(installation.status, "OPERATIONAL")
        self.assertEqual(builder.status, "IDLE")
        self.assertLess(self.sim._cover_multiplier(builder, 0.0), cover_before)
        self.assertAlmostEqual(
            self.sim.get_installation_cover_bonus(builder),
            installation.profile["fortification_cover_bonus"],
        )

        self.sim.save_game("fort_site")
        installation.integrity = 0.0
        loaded, message = self.sim.load_game("fort_site")
        self.assertTrue(loaded, message)
        restored = self.sim.installations[installation.id]
        self.assertEqual(restored.status, "OPERATIONAL")
        self.assertEqual(restored.builder_unit_id, builder.id)

    def test_radar_site_detects_distant_targets_and_destroyed_site_stops(self):
        observer = self.sim.units["faction_a_unit"]
        target = self.sim.units["faction_b_unit"]
        target.lon = observer.lon + 1.0
        target.lat = observer.lat
        radar = engine_module.MilitaryInstallation(
            "faction_a_radar",
            {
                "type_id": "RADAR_SITE",
                "name": "Faction A Radar",
                "faction": observer.faction,
                "lon": observer.lon,
                "lat": observer.lat,
            },
            self.sim.rules["military_installations"]["types"],
        )
        self.sim.installations[radar.id] = radar

        with patch.object(engine_module.random, "random", return_value=0.0):
            self.sim.detection_tick(1.0)
        self.assertTrue(self.sim._is_detected_by(observer.faction, target.id))

        radar.apply_damage(radar.max_integrity)
        self.sim.detected_units.clear()
        with patch.object(engine_module.random, "random", return_value=0.0):
            self.sim.detection_tick(1.0)
        self.assertFalse(self.sim._is_detected_by(observer.faction, target.id))

    def test_detected_enemy_installation_takes_weapon_based_direct_fire(self):
        attacker = self.sim.units["faction_a_unit"]
        attacker.stance = "AGGRESSIVE"
        attacker.status = "IDLE"
        target = engine_module.MilitaryInstallation(
            "enemy_radar_target",
            {
                "type_id": "RADAR_SITE",
                "name": "Enemy Radar Target",
                "faction": "FACTION_B",
                "lon": attacker.lon + 0.001,
                "lat": attacker.lat,
            },
            self.sim.rules["military_installations"]["types"],
        )
        self.sim.installations[target.id] = target
        self.sim.detected_installations[target.id] = {
            "ttl": 10.0,
            "factions": [attacker.faction],
        }
        integrity_before = target.integrity

        self.sim._resolve_installation_direct_fire(1.0)

        self.assertLess(target.integrity, integrity_before)

    def test_airstrike_and_bombardment_damage_military_targets(self):
        package = load_dlc_package("test")
        with tempfile.TemporaryDirectory() as directory:
            simulation = engine_module.SimulationEngine(
                "test",
                package=package,
                log_file=os.devnull,
                storage_dir=directory,
            )
            try:
                target = simulation.installations["blue_forward_fort"]
                aircraft = simulation.units["red_air_wing"]
                aircraft.target_lon = target.lon
                aircraft.target_lat = target.lat
                simulation.detected_installations[target.id] = {
                    "ttl": 10.0,
                    "factions": [aircraft.faction],
                }

                airstrike_result = simulation.resolve_airstrike_impact(aircraft)
                self.assertEqual(airstrike_result["installations_hit"], 1)
                self.assertGreater(airstrike_result["installation_damage"], 0.0)

                target.integrity = target.max_integrity
                artillery = simulation.units["red_artillery"]
                artillery.lon = target.lon - 0.01
                artillery.lat = target.lat
                artillery.target_lon = target.lon
                artillery.target_lat = target.lat
                bombard_result = simulation.resolve_bombardment_tick(artillery, 0.5)
                self.assertEqual(bombard_result["installations_hit"], 1)
                self.assertGreater(bombard_result["installation_damage"], 0.0)
                self.assertLess(target.integrity, target.max_integrity)
            finally:
                simulation.stop()


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

    def test_gis_status_api_and_top_left_panel_expose_every_optional_layer(self):
        response = self.client.get("/api/gis_status")
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(
            {feature["id"] for feature in data["features"]},
            {"terrain_dem", "roads", "rivers", "provinces"},
        )

        dashboard = self.client.get("/")
        self.assertIn(b'id="gis-status-panel"', dashboard.data)
        self.assertIn(b'id="gis-status-list"', dashboard.data)
        self.assertIn(b"OFF means not installed or unreadable", dashboard.data)

    def test_zeus_console_has_close_control_and_plain_language_actions(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="zeus-close-button"', response.data)
        self.assertIn(b'onclick="toggleAdminConsole()"', response.data)
        self.assertIn(b"Apply temporary effect to selected unit", response.data)
        self.assertIn(b"Set personnel", response.data)
        self.assertIn(b"Mark as allied", response.data)
        self.assertIn(b"Mark as hostile", response.data)
        self.assertIn(b"does not issue an attack order", response.data)
        self.assertIn(b"City influence areas", response.data)
        self.assertIn(b'id="admin-city-influence_rate"', response.data)
        self.assertIn(b"Province politics and civilian sentiment", response.data)
        self.assertIn(b'id="admin-politics-civilian_sentiment"', response.data)

    def test_chair_can_add_update_and_delete_city_influence(self):
        payload = {
            "id": "metro",
            "name": "Metro",
            "description": "Dense center",
            "lon": 0,
            "lat": 0,
            "area_km2": 100,
            "influence_rate": 0.6,
        }
        added = self.client.post("/api/city", json=payload)
        self.assertEqual(added.status_code, 200)
        self.assertEqual(self.sim.cities[0]["influence_rate"], 0.6)

        payload.update({"original_id": "metro", "name": "Metro Updated", "influence_rate": 1})
        updated = self.client.post("/api/city", json=payload)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(self.sim.cities[0]["name"], "Metro Updated")
        first_unit = next(iter(self.sim.units.values()))
        first_unit.lon = first_unit.lat = 0
        state = self.client.get("/api/state").get_json()
        self.assertEqual(state["cities"][0]["influence_rate"], 1)
        self.assertEqual(state["units"][first_unit.id]["city_name"], "Metro Updated")

        deleted = self.client.post("/api/city", json={"action": "delete", "id": "metro"})
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.sim.cities, [])

    def test_city_api_rejects_out_of_range_influence(self):
        response = self.client.post("/api/city", json={
            "id": "invalid_city", "name": "Invalid", "lon": 0, "lat": 0,
            "area_km2": 10, "influence_rate": 1.1,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.sim.cities, [])

    def test_chair_can_edit_faction_specific_civilian_sentiment_and_occupation(self):
        payload = {
            "province": "Test Province",
            "faction": "FACTION_A",
            "civilian_sentiment": -0.75,
            "occupation": 0.6,
        }
        response = self.client.post("/api/province_politics", json=payload)
        self.assertEqual(response.status_code, 200)
        record = self.sim.province_politics["Test Province"]["factions"]["FACTION_A"]
        self.assertEqual(record["civilian_sentiment"], -0.75)
        self.assertEqual(record["occupation"], 0.6)

        state = self.client.get("/api/state").get_json()
        self.assertIn("FACTION_A", state["province_politics"]["Test Province"]["factions"])

        rejected = self.client.post("/api/province_politics", json={**payload, "civilian_sentiment": 1.1})
        self.assertEqual(rejected.status_code, 400)
        deleted = self.client.post("/api/province_politics", json={
            "action": "delete", "province": "Test Province", "faction": "FACTION_A",
        })
        self.assertEqual(deleted.status_code, 200)
        live_state = self.client.get("/api/state").get_json()["province_politics"]
        live_record = live_state["Test Province"]["factions"]["FACTION_A"]
        self.assertEqual(live_record["civilian_sentiment"], 0.0)
        self.assertGreater(live_record["military_presence"], 0.0)

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

    def test_accepted_commands_do_not_create_an_automatic_save(self):
        response = self.client.post("/api/command", json={"command": "speed 5"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse((Path(self.temp_dir.name) / "save_autosave.json").exists())

    def test_manual_checkpoint_api_lists_saves_and_restores_paused(self):
        self.sim.game_hours = 13.25
        saved = self.client.post("/api/save_game", json={"slot": "slot_1"})
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.get_json()["slot"]["can_load"])

        listed = self.client.get("/api/save_slots")
        slots = {item["slot"]: item for item in listed.get_json()["slots"]}
        self.assertTrue(listed.get_json()["manual_only"])
        self.assertEqual(slots["slot_1"]["game_hours"], 13.25)
        self.assertEqual(slots["slot_2"]["condition"], "empty")

        self.sim.game_hours = 99.0
        self.sim.is_paused = False
        restored = self.client.post("/api/load_game", json={"slot": "slot_1"})
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(self.sim.game_hours, 13.25)
        self.assertTrue(self.sim.is_paused)

    def test_save_api_rejects_hidden_or_automatic_slots(self):
        response = self.client.post("/api/save_game", json={"slot": "autosave"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["status"], "error")
        self.assertFalse((Path(self.temp_dir.name) / "save_autosave.json").exists())

    def test_existing_checkpoint_requires_explicit_overwrite(self):
        self.sim.game_hours = 2.0
        first = self.client.post("/api/save_game", json={"slot": "slot_1"})
        self.assertEqual(first.status_code, 200)

        self.sim.game_hours = 9.0
        rejected = self.client.post("/api/save_game", json={"slot": "slot_1"})
        self.assertEqual(rejected.status_code, 409)
        self.assertIn("confirm overwrite", rejected.get_json()["msg"])

        accepted = self.client.post(
            "/api/save_game",
            json={"slot": "slot_1", "overwrite": True},
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.get_json()["slot"]["game_hours"], 9.0)

    def test_scenario_reset_does_not_create_a_backup(self):
        self.sim.game_hours = 8.0
        response = self.client.post("/api/reset_scenario")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sim.game_hours, 0.0)
        self.assertTrue(self.sim.is_paused)
        self.assertEqual(list(Path(self.temp_dir.name).glob("save_*.json")), [])

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
        self.assertEqual(data["scenario"]["cities"], [])
        self.assertEqual(data["scenario"]["province_politics"], [])
        editor = self.client.get("/editor")
        self.assertIn(b"Province Politics", editor.data)
        self.assertIn(b"Civilian Sentiment", editor.data)

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
        live_unit = self.client.get("/api/state").get_json()["units"]["airdrop_test"]
        self.assertEqual(live_unit["personnel"], self.sim.units["airdrop_test"].personnel)
        self.assertNotIn("combat_effective_personnel", live_unit)
        self.assertNotIn("combat_readiness", live_unit)

        air_payload = dict(
            base_payload,
            id="airdrop_air",
            name="Air Support",
            unit_type="AIR_FORCE",
            aircraft_type="STEALTH_STRIKE",
            personnel=self.sim.battalion_registry["air_wing"]["size"],
            composition={"air_wing": 1},
            primary_weapon="air_ordnance",
        )
        air_unit = self.client.post("/api/edit_unit", json=air_payload)
        self.assertEqual(air_unit.status_code, 200, air_unit.get_json())
        air_unit_data = air_unit.get_json()["unit"]
        self.assertIn(self.sim.rules["missions"]["airstrike"]["capability"], air_unit_data["effective_capabilities"])
        self.assertEqual(air_unit_data["aircraft_type"], "STEALTH_STRIKE")
        self.assertEqual(air_unit_data["airstrike_profile"]["label"], "Stealth Strike Aircraft")
        self.assertLess(air_unit_data["airstrike_profile"]["aa_vulnerability_multiplier"], 1.0)
        deployed_aircraft = self.sim.units["airdrop_air"]
        deployed_aircraft.supply = 100.0
        deployed_aircraft.fatigue = 0.0
        strike = self.client.post("/api/command", json={"command": "airstrike airdrop_air 8 0"})
        self.assertEqual(strike.status_code, 200, strike.get_json())
        self.assertAlmostEqual(deployed_aircraft.supply, 100.0 - air_unit_data["airstrike_profile"]["supply_cost"])
        self.assertAlmostEqual(deployed_aircraft.fatigue, air_unit_data["airstrike_profile"]["fatigue_cost"])

    def test_support_mission_commands_enforce_lifecycle_range_and_costs(self):
        unit = next(iter(self.sim.units.values()))
        unit.capabilities = ["bombard", "airstrike"]
        unit.composition = {"artillery": 1, "air_wing": 1}
        unit.primary_weapon = "standard_howitzer"
        unit.parse_composition()
        unit.lon = 0.0
        unit.lat = 0.0
        unit.waypoints = [(5.0, 5.0)]
        unit.supply = float(self.sim.rules["missions"]["bombard"]["minimum_supply_to_start"])

        bombard = self.client.post("/api/command", json={"command": f"bombard {unit.id} 0.01 0"})
        self.assertEqual(bombard.status_code, 200, bombard.get_json())
        self.assertEqual(unit.status, "BOMBARDING")
        self.assertEqual(unit.waypoints, [])
        self.assertEqual(unit.bombard_timer, self.sim.rules["missions"]["bombard"]["duration_hours"])

        overlapping = self.client.post("/api/command", json={"command": f"airstrike {unit.id} 0.01 0"})
        self.assertEqual(overlapping.status_code, 400)
        self.assertIn("active support mission", overlapping.get_json()["msg"])

        self.client.post("/api/command", json={"command": f"halt {unit.id}"})
        airstrike_rules = self.sim.rules["missions"]["airstrike"]
        unit.supply = float(airstrike_rules["supply_cost"]) - 0.1
        low_supply = self.client.post("/api/command", json={"command": f"airstrike {unit.id} 0.01 0"})
        self.assertEqual(low_supply.status_code, 400)
        self.assertIn("requires", low_supply.get_json()["msg"])

        unit.supply = 100.0
        outside_range = self.client.post("/api/command", json={"command": f"airstrike {unit.id} 20 0"})
        self.assertEqual(outside_range.status_code, 400)
        self.assertIn("outside sortie range", outside_range.get_json()["msg"])

        supply_before = unit.supply
        fatigue_before = unit.fatigue
        launched = self.client.post("/api/command", json={"command": f"airstrike {unit.id} 2 0"})
        self.assertEqual(launched.status_code, 200, launched.get_json())
        self.assertEqual(unit.status, "AIRSTRIKE_OUTBOUND")
        self.assertAlmostEqual(unit.supply, supply_before - float(airstrike_rules["supply_cost"]))
        self.assertAlmostEqual(unit.fatigue, fatigue_before + float(airstrike_rules["fatigue_cost"]))
        empty_impact = self.sim.resolve_airstrike_impact(unit)
        self.assertEqual(empty_impact["targets_hit"], 0)
        self.assertAlmostEqual(unit.supply, supply_before - float(airstrike_rules["supply_cost"]))

    def test_relocate_assault_defend_and_fortify_commands_have_explicit_modes(self):
        unit_id = next(iter(self.sim.units))
        unit = self.sim.units[unit_id]
        unit.stance = "RECON"

        relocate = self.client.post("/api/command", json={"command": f"relocate {unit_id} 2 0"})
        self.assertEqual(relocate.status_code, 200)
        self.assertTrue(relocate.get_json()["queued"])
        self.assertTrue(relocate.get_json()["paused"])
        self.assertIn("press Run", relocate.get_json()["msg"])
        self.assertTrue(unit.has_order_role("relocate"))
        self.assertEqual(unit.status, "MOVING")
        self.assertEqual(unit.stance, "RECON")

        legacy_move = self.client.post("/api/command", json={"command": f"move {unit_id} 3 0"})
        self.assertEqual(legacy_move.status_code, 200)
        self.assertTrue(unit.has_order_role("relocate"))

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

    def test_build_command_creates_visible_persistent_project_and_enforces_builder_state(self):
        builder = self.sim.units["faction_a_unit"]
        response = self.client.post(
            "/api/command",
            json={"command": f"build {builder.id} FORTIFICATION"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["queued"])
        self.assertEqual(builder.status, "CONSTRUCTING")
        state = self.client.get("/api/state").get_json()
        self.assertEqual(len(state["installations"]), 1)
        self.assertEqual(
            state["units"][builder.id]["active_construction"]["type_id"],
            "FORTIFICATION",
        )
        installation = next(iter(state["installations"].values()))
        self.assertEqual(installation["status"], "UNDER_CONSTRUCTION")
        self.assertIn("fortification_cover_bonus", installation)

        conflicting = self.client.post(
            "/api/command",
            json={"command": f"build {builder.id} RADAR_SITE"},
        )
        self.assertEqual(conflicting.status_code, 400)
        self.assertIn("unfinished", conflicting.get_json()["msg"])

        moving_builder = self.sim.units["faction_b_unit"]
        moving_builder.status = "MOVING"
        moving_builder.waypoints = [(moving_builder.lon + 1.0, moving_builder.lat)]
        rejected = self.client.post(
            "/api/command",
            json={"command": f"build {moving_builder.id} RADAR_SITE"},
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("stationary", rejected.get_json()["msg"])


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

    def test_military_installation_types_and_starting_targets_are_dlc_data(self):
        template = load_dlc_package("_template")
        test_package = load_dlc_package("test")

        self.assertEqual(
            set(template.rules["military_installations"]["types"]),
            {"FORTIFICATION", "RADAR_SITE"},
        )
        self.assertEqual(len(test_package.scenario["military_installations"]), 2)
        self.assertEqual(
            {site["type_id"] for site in test_package.scenario["military_installations"]},
            {"FORTIFICATION", "RADAR_SITE"},
        )

    def test_unknown_starting_installation_and_invalid_construction_rules_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            dlc_root = Path(directory)
            broken = dlc_root / "broken_installations"
            shutil.copytree(resolve_dlc_path("_template"), broken)
            scenario_path = broken / "scenario.json"
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            scenario["military_installations"] = [{
                "id": "mystery_site",
                "type_id": "NOT_A_REAL_TYPE",
                "name": "Mystery Site",
                "faction": "FACTION_A",
                "lon": 0,
                "lat": 0,
            }]
            scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
            with patch.object(loader_module, "DLC_ROOT", dlc_root):
                with self.assertRaises(DLCValidationError) as context:
                    loader_module.load_dlc_package("broken_installations")
            self.assertIn("references unknown type [NOT_A_REAL_TYPE]", str(context.exception))

            scenario["military_installations"] = []
            scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
            rules_path = broken / "rules.json"
            rules = json.loads(rules_path.read_text(encoding="utf-8"))
            rules["military_installations"]["construction"]["stop_supply_threshold"] = 20
            rules["military_installations"]["construction"]["minimum_supply_to_start"] = 10
            rules_path.write_text(json.dumps(rules), encoding="utf-8")
            with patch.object(loader_module, "DLC_ROOT", dlc_root):
                with self.assertRaises(DLCValidationError) as context:
                    loader_module.load_dlc_package("broken_installations")
            self.assertIn("stop_supply_threshold must not exceed", str(context.exception))

    def test_aircraft_type_profiles_are_validated_as_dlc_data(self):
        with tempfile.TemporaryDirectory() as directory:
            dlc_root = Path(directory)
            broken = dlc_root / "broken_aircraft"
            shutil.copytree(resolve_dlc_path("_template"), broken)
            rules_path = broken / "rules.json"
            rules = json.loads(rules_path.read_text(encoding="utf-8"))
            del rules["missions"]["airstrike"]["aircraft_types"]["MULTIROLE_FIGHTER"]["accuracy_multiplier"]
            rules_path.write_text(json.dumps(rules), encoding="utf-8")
            with patch.object(loader_module, "DLC_ROOT", dlc_root):
                with self.assertRaises(DLCValidationError) as context:
                    loader_module.load_dlc_package("broken_aircraft")
            self.assertIn("Aircraft type [MULTIROLE_FIGHTER] accuracy_multiplier", str(context.exception))

    def test_test_dlc_air_wings_have_distinct_aircraft_behavior_and_performance(self):
        package = load_dlc_package("test")
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(engine_module, "MapEngine", FakeMapEngine), patch.object(
                engine_module, "ProvinceEngine", FakeProvinceEngine
            ):
                simulation = engine_module.SimulationEngine(
                    "test",
                    package=package,
                    log_file=os.devnull,
                    storage_dir=directory,
                )

            aircraft_ids = (
                "red_air_wing", "blue_air_wing", "green_air_wing", "gold_air_wing",
            )
            aircraft_types = {simulation.units[unit_id].aircraft_type for unit_id in aircraft_ids}
            self.assertEqual(
                aircraft_types,
                {"STRIKE_FIGHTER", "HEAVY_BOMBER", "CLOSE_AIR_SUPPORT", "STEALTH_STRIKE"},
            )

            profiles = {
                unit_id: simulation.units[unit_id].get_airstrike_parameters()
                for unit_id in aircraft_ids
            }
            self.assertGreater(
                profiles["blue_air_wing"]["sortie_range_km"],
                profiles["green_air_wing"]["sortie_range_km"],
            )
            self.assertGreater(
                profiles["gold_air_wing"]["cruise_speed_kmh"],
                profiles["blue_air_wing"]["cruise_speed_kmh"],
            )
            self.assertLess(
                profiles["gold_air_wing"]["aa_vulnerability_multiplier"],
                profiles["green_air_wing"]["aa_vulnerability_multiplier"],
            )
            self.assertGreater(
                profiles["gold_air_wing"]["unobserved_targeting_multiplier"],
                profiles["green_air_wing"]["unobserved_targeting_multiplier"],
            )

            air_defense = simulation.units["blue_combined_arms"]
            for unit_id in ("green_air_wing", "gold_air_wing"):
                aircraft = simulation.units[unit_id]
                aircraft.lon = air_defense.lon
                aircraft.lat = air_defense.lat
                aircraft.status = "AIRSTRIKE_OUTBOUND"
                aircraft.waypoints = [(aircraft.lon + 1.0, aircraft.lat)]
                aircraft.personnel = 600.0
                aircraft.supply = 100.0
                aircraft.fatigue = 0.0
                aircraft.suppression = 0.0
            with patch.object(unit_module.random, "random", return_value=0.004):
                simulation.units["green_air_wing"].update_position(0.01, simulation)
                simulation.units["gold_air_wing"].update_position(0.01, simulation)
            self.assertEqual(simulation.units["green_air_wing"].status, "NEUTRALIZED")
            self.assertEqual(simulation.units["gold_air_wing"].status, "AIRSTRIKE_OUTBOUND")
            for unit_id in ("green_air_wing", "gold_air_wing"):
                aircraft = simulation.units[unit_id]
                aircraft.personnel = 600.0
                aircraft.status = "IDLE"
                aircraft.waypoints = []

            target = simulation.units["blue_combined_arms"]
            target.faction = "TARGET"
            target.stance = "DEFENSIVE"
            target.entrenchment = 0.35
            target.parse_composition()
            strike_results = {}
            for unit_id in aircraft_ids:
                aircraft = simulation.units[unit_id]
                aircraft.supply = 100.0
                aircraft.fatigue = 0.0
                aircraft.suppression = 0.0
                aircraft.target_lon = target.lon
                aircraft.target_lat = target.lat
                target.personnel = 12000.0
                target.morale = 90.0
                target.suppression = 0.0
                simulation.detected_units[target.id] = {"ttl": 10.0, "factions": [aircraft.faction]}
                strike_results[unit_id] = simulation.resolve_airstrike_impact(aircraft)
            simulation.save_game("aircraft_profiles")
            simulation.units["red_air_wing"].aircraft_type = "HEAVY_BOMBER"
            loaded, message = simulation.load_game("aircraft_profiles")
            self.assertTrue(loaded, message)
            self.assertEqual(simulation.units["red_air_wing"].aircraft_type, "STRIKE_FIGHTER")
            simulation.stop()

        self.assertGreater(
            strike_results["blue_air_wing"]["casualties"],
            strike_results["green_air_wing"]["casualties"],
        )
        self.assertGreater(
            strike_results["red_air_wing"]["casualties"],
            strike_results["gold_air_wing"]["casualties"],
        )
        self.assertEqual(strike_results["blue_air_wing"]["aircraft_type"], "HEAVY_BOMBER")

    def test_test_dlc_artillery_is_mobile_and_air_force_uses_sorties_only(self):
        package = load_dlc_package("test")
        self.assertGreater(package.rules["unit_types"]["ARTILLERY"]["fixed_stats"]["speed_kmh"], 0)
        self.assertTrue(package.rules["unit_types"]["ARTILLERY"]["can_be_airstrike_target"])
        self.assertTrue(package.rules["unit_types"]["AIR_FORCE"]["can_be_airstrike_target"])
        self.assertFalse(package.rules["unit_types"]["AIR_FORCE"]["can_direct_combat"])

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(engine_module, "MapEngine", FakeMapEngine), patch.object(
                engine_module, "ProvinceEngine", FakeProvinceEngine
            ):
                simulation = engine_module.SimulationEngine(
                    "test",
                    package=package,
                    log_file=os.devnull,
                    storage_dir=directory,
                )
            artillery = simulation.units["red_artillery"]
            before = (artillery.lon, artillery.lat)
            artillery.status = "MOVING"
            artillery.set_order_role("relocate")
            artillery.waypoints = [(artillery.lon + 0.2, artillery.lat)]
            artillery.update_position(0.25, simulation)

            aircraft = simulation.units["red_air_wing"]
            target = simulation.units["blue_combined_arms"]
            strike_rules = simulation.rules["missions"]["airstrike"]
            aircraft.supply -= float(strike_rules["supply_cost"])
            aircraft.fatigue += float(strike_rules["fatigue_cost"])
            aircraft.target_lon = target.lon
            aircraft.target_lat = target.lat
            simulation.detected_units[target.id] = {"ttl": 10.0, "factions": [aircraft.faction]}
            strike_result = simulation.resolve_airstrike_impact(aircraft)
            simulation.stop()

        self.assertGreater(artillery.speed, 0.0)
        self.assertNotEqual((artillery.lon, artillery.lat), before)
        self.assertGreater(strike_result["casualties"], 900.0)
        self.assertLess(strike_result["casualties"], 1300.0)

    def test_missing_optional_gis_packages_do_not_block_dlc_mounting(self):
        with tempfile.TemporaryDirectory() as directory:
            dlc_root = Path(directory)
            campaign = dlc_root / "no_maps"
            shutil.copytree(resolve_dlc_path("_template"), campaign)
            scenario_path = campaign / "scenario.json"
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            scenario["map_config"].update({
                "dem_dir": "maps/not_downloaded_dem",
                "dem_file": "",
                "roads_file": "maps/not_downloaded_roads.tif",
                "rivers_file": "maps/not_downloaded_rivers.geojson",
                "provinces_file": "maps/not_downloaded_provinces.geojson",
            })
            scenario_path.write_text(json.dumps(scenario), encoding="utf-8")

            with patch.object(loader_module, "DLC_ROOT", dlc_root):
                package = loader_module.load_dlc_package("no_maps")

            self.assertTrue(package.map_config["dem_dir"].endswith("not_downloaded_dem"))
            self.assertTrue(package.map_config["roads_file"].endswith("not_downloaded_roads.tif"))
            self.assertFalse(Path(package.map_config["provinces_file"]).exists())

    def test_optional_gis_paths_still_cannot_escape_the_dlc(self):
        with tempfile.TemporaryDirectory() as directory:
            dlc_root = Path(directory)
            campaign = dlc_root / "unsafe_maps"
            shutil.copytree(resolve_dlc_path("_template"), campaign)
            scenario_path = campaign / "scenario.json"
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            scenario["map_config"]["roads_file"] = "../outside.geojson"
            scenario_path.write_text(json.dumps(scenario), encoding="utf-8")

            with patch.object(loader_module, "DLC_ROOT", dlc_root):
                with self.assertRaises(DLCValidationError) as context:
                    loader_module.load_dlc_package("unsafe_maps")
            self.assertIn("map_config.roads_file escapes", str(context.exception))

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

    def test_city_influence_is_validated_when_loading_a_dlc(self):
        with tempfile.TemporaryDirectory() as directory:
            dlc_root = Path(directory)
            broken = dlc_root / "broken"
            shutil.copytree(resolve_dlc_path("_template"), broken)
            scenario_path = broken / "scenario.json"
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            scenario["cities"] = [{
                "id": "city", "name": "City", "lon": 0, "lat": 0,
                "area_km2": 10, "influence_rate": 2,
            }]
            scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
            with patch.object(loader_module, "DLC_ROOT", dlc_root):
                with self.assertRaises(DLCValidationError) as context:
                    loader_module.load_dlc_package("broken")
            self.assertIn("influence_rate must be at most 1", str(context.exception))

    def test_province_civilian_sentiment_is_validated_when_loading_a_dlc(self):
        with tempfile.TemporaryDirectory() as directory:
            dlc_root = Path(directory)
            broken = dlc_root / "broken"
            shutil.copytree(resolve_dlc_path("_template"), broken)
            scenario_path = broken / "scenario.json"
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            scenario["province_politics"] = [{
                "province": "Province", "faction": "Faction",
                "civilian_sentiment": -2, "occupation": 0,
            }]
            scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
            with patch.object(loader_module, "DLC_ROOT", dlc_root):
                with self.assertRaises(DLCValidationError) as context:
                    loader_module.load_dlc_package("broken")
            self.assertIn("civilian_sentiment must be at least -1", str(context.exception))

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

    def test_offensive_stats_are_required_on_weapon_bands_not_battalions_or_unit_types(self):
        template = load_dlc_package("_template")
        for battalion in template.battalions.values():
            self.assertFalse({"soft", "hard", "ap"}.intersection(battalion))
            self.assertIn("weapons", battalion)
            self.assertIn("armor_generation", battalion)
        for profile in template.rules["unit_types"].values():
            if profile["stats_source"] == "fixed":
                self.assertFalse(
                    {"soft_attack", "hard_attack", "armor_piercing"}.intersection(profile["fixed_stats"])
                )

        with tempfile.TemporaryDirectory() as directory:
            dlc_root = Path(directory)
            broken = dlc_root / "broken"
            shutil.copytree(resolve_dlc_path("_template"), broken)
            battalions_path = broken / "battalions.json"
            battalions = json.loads(battalions_path.read_text(encoding="utf-8"))
            battalions["general"]["soft"] = 20
            battalions_path.write_text(json.dumps(battalions), encoding="utf-8")
            weapons_path = broken / "weapons.json"
            weapons = json.loads(weapons_path.read_text(encoding="utf-8"))
            del weapons["standard"]["generation"]
            weapons_path.write_text(json.dumps(weapons), encoding="utf-8")
            with patch.object(loader_module, "DLC_ROOT", dlc_root):
                with self.assertRaises(DLCValidationError) as context:
                    loader_module.load_dlc_package("broken")
            message = str(context.exception)
            self.assertIn("Weapon [standard] generation", message)
            self.assertIn("attack fields must move into weapon range_bands", message)

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

    def test_gis_avoidance_zone_creates_a_real_detour(self):
        config = {
            "grid_resolution": [81, 81],
            "dem_analysis_resolution": [81, 81],
            "bounds": {"min_lon": -1, "max_lon": 1, "min_lat": -1, "max_lat": 1},
            "fallback_elevation_m": 0,
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
        route_arguments = {
            "start_lon": -0.9,
            "start_lat": 0.0,
            "target_lon": 0.9,
            "target_lat": 0.0,
        }
        direct_route = map_engine.find_path(**route_arguments)
        avoided_route = map_engine.find_path(
            **route_arguments,
            avoidance_zones=[{
                "lon": 0.0,
                "lat": 0.0,
                "radius_km": 30.0,
                "cost_multiplier": 1000.0,
            }],
        )

        direct_clearance = min(
            engine_module.haversine_distance(lon, lat, 0.0, 0.0)
            for lon, lat in direct_route
        )
        avoided_clearance = min(
            engine_module.haversine_distance(lon, lat, 0.0, 0.0)
            for lon, lat in avoided_route
        )
        self.assertLess(direct_clearance, 1.0)
        self.assertGreaterEqual(avoided_clearance, 29.0)
        self.assertEqual(avoided_route[-1], (0.9, 0.0))


class FrontendRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).resolve().parents[1]
        cls.javascript = (cls.project_root / "static" / "js" / "tactical_engine.js").read_text(encoding="utf-8")
        cls.styles = (cls.project_root / "static" / "css" / "style.css").read_text(encoding="utf-8")
        cls.index = (cls.project_root / "templates" / "index.html").read_text(encoding="utf-8")
        cls.editor = (cls.project_root / "templates" / "cdc_editor.html").read_text(encoding="utf-8")

    def test_relocate_requires_explicit_targeting_and_has_no_box_zoom(self):
        self.assertIn("boxZoom: false", self.javascript)
        self.assertIn("let pendingAction = null", self.javascript)
        self.assertIn("if (!selectedUnitId || !pendingAction) return;", self.javascript)
        self.assertIn("setTargetingMode('relocate')", self.javascript)
        self.assertNotIn("setTargetingMode('move')", self.javascript)

    def test_province_click_does_not_draw_a_focus_rectangle(self):
        self.assertIn("className: 'province-boundary'", self.javascript)
        self.assertIn("#map .province-boundary:focus", self.styles)
        self.assertIn("outline: none !important", self.styles)

    def test_default_basemap_is_local_and_has_no_external_tile_services(self):
        self.assertIn("createLocalGridBasemap", self.javascript)
        self.assertIn("const localBasemap", self.javascript)
        self.assertNotIn("L.tileLayer", self.javascript)
        self.assertNotIn("openstreetmap.org", self.javascript.lower())
        self.assertNotIn("arcgisonline.com", self.javascript.lower())

    def test_paused_relocation_is_shown_as_queued_with_a_run_control(self):
        self.assertIn("ORDER QUEUED — TIMELINE PAUSED", self.javascript)
        self.assertIn("remainingRouteDistanceKm", self.javascript)
        self.assertIn("effective_movement_speed", self.javascript)
        self.assertIn("sendCommand('play')", self.javascript)

    def test_relocation_contact_avoidance_is_explained_and_displayed(self):
        self.assertIn("rerouting around detected threats", self.javascript)
        self.assertIn("relocation_avoidance", self.javascript)
        self.assertIn("CONTACT-AVOIDANCE ROUTE", self.javascript)

    def test_confirmation_card_is_promoted_and_has_a_dynamic_heading(self):
        self.assertIn("z-index: 1105", self.styles)
        self.assertIn("positionConfirmationPanel", self.javascript)
        self.assertIn('id="draft-confirmation-title"', self.index)
        self.assertIn('id="draft-instruction"', self.index)

    def test_tactical_panel_displays_morale(self):
        self.assertIn("uiText('Morale:', '士气：')", self.javascript)
        self.assertIn('class="morale-meter"', self.javascript)

    def test_tactical_panel_displays_current_alive_personnel(self):
        self.assertIn("uiText('Personnel Alive:', '当前兵力：')", self.javascript)
        self.assertIn('Math.floor(Number(u.personnel))', self.javascript)
        self.assertNotIn('combat_effective_personnel', self.javascript)
        self.assertNotIn('combat_readiness', self.javascript)

    def test_airdrop_panel_stays_above_gis_and_has_a_close_button(self):
        self.assertIn('id="deploy-close-button"', self.index)
        self.assertIn('id="dep-unit-type"', self.index)
        self.assertIn('z-index: 1104', self.styles)
        self.assertIn('.gis-status-panel', self.styles)

    def test_support_mission_ui_explains_range_cost_and_effect_area(self):
        self.assertIn("Bombard Area", self.javascript)
        self.assertIn("Launch Airstrike", self.javascript)
        self.assertIn("sortie_range_km", self.javascript)
        self.assertIn("maximum_casualty_fraction", self.javascript)
        self.assertIn("draftImpactCircle", self.javascript)
        self.assertIn('id="draft-authorize-button"', self.index)
        self.assertIn("airstrikePerformance", self.javascript)
        self.assertIn("Aircraft Type:", self.javascript)
        self.assertIn('id="dep-aircraft-type"', self.index)

    def test_weapon_loadout_and_separate_armor_generation_are_clear_in_the_ui(self):
        self.assertIn('id="dep-weapons-display"', self.index)
        self.assertNotIn('id="dep-weapon"', self.index)
        self.assertIn("selectedUnit.bombard_range", self.javascript)
        self.assertIn("Weapon Groups:", self.javascript)
        self.assertIn("Armor Gen", self.javascript)
        self.assertIn("range_bands", self.editor)
        self.assertIn("armor_generation", self.editor)
        self.assertIn("Mounted Weapon Groups per Battalion", self.editor)
        self.assertIn("每营配属武器组", self.editor)
        self.assertNotIn('batInput(id,"soft"', self.editor)

    def test_military_targets_have_persistent_markers_selection_and_one_click_targeting(self):
        self.assertIn("window.installationMarkersMap", self.javascript)
        self.assertIn("refreshInstallationsSmoothly", self.javascript)
        self.assertIn("updateInstallationHUD", self.javascript)
        self.assertIn("Installation integrity", self.javascript)
        self.assertIn("mapClickHandler({latlng:", self.javascript)
        self.assertIn("selected-installation", self.styles)
        self.assertIn("Military Target", self.javascript)

    def test_nearby_unit_and_installation_icons_use_a_five_kilometer_chooser(self):
        self.assertIn("const NEARBY_SELECTION_RADIUS_KM = 5", self.javascript)
        self.assertIn("buildNearbyMapSelectionCandidates", self.javascript)
        self.assertIn("handleSelectableMarkerClick('unit', uid, e)", self.javascript)
        self.assertIn("handleSelectableMarkerClick('installation', installationId, event)", self.javascript)
        self.assertIn('id="nearby-selection-panel"', self.index)
        self.assertIn('id="nearby-selection-list"', self.index)
        self.assertIn(".nearby-selection-option", self.styles)
        self.assertIn("z-index: 1110", self.styles)
        self.assertIn("mapClickHandler({latlng:", self.javascript)

    def test_construction_ui_distinguishes_persistent_sites_from_temporary_fieldworks(self):
        self.assertIn("Build at Current Position", self.javascript)
        self.assertIn("startInstallationConstruction", self.javascript)
        self.assertIn("Fortify</strong> only prepares temporary fieldworks", self.javascript)
        self.assertIn("installation_cover_bonus", self.javascript)
        self.assertIn('data-en="9. Military Targets" data-zh="9. 军事目标"', self.editor)
        self.assertIn("renderInstallations", self.editor)
        self.assertIn("scenario.military_installations", self.editor)


if __name__ == "__main__":
    unittest.main()
