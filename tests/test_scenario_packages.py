"""Behavioral coverage for versioned, data-only scenario packs."""

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import dlc_loader
from dlc_loader import DLCValidationError, load_dlc_directory, load_dlc_package
import engine as engine_module
from scenario_pack import build_package, scaffold_package
import scenario_package
import server


TEMPLATE = Path(__file__).resolve().parents[1] / "dlc" / "_template"
PAYLOAD_FILES = {
    "scenario": "scenario.json", "rules": "rules.json", "units": "units.json",
    "weapons": "weapons.json", "battalions": "battalions.json",
    "objectives": "objectives.json", "events": "events.json",
}


class FlatMap:
    def __init__(self, *_args):
        self.use_real_dem = False
        self.road_matrix = None
        self.river_matrix = None

    def get_elevation(self, *_args):
        return 0.0

    def get_terrain_complexity(self, *_args):
        return 0.0

    def check_line_of_sight(self, *_args):
        return True


class EmptyProvinces:
    def __init__(self, *_args):
        self.provinces = []

    def get_province(self, *_args):
        return "Test Province"


class ScenarioPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "scenario"
        self.source.mkdir()
        self.documents = {
            key: json.loads((TEMPLATE / filename).read_text(encoding="utf-8"))
            for key, filename in PAYLOAD_FILES.items()
            if key not in {"objectives", "events"}
        }
        self.documents.update({
            "package": {
                "schema_version": 1,
                "id": "beta-crisis",
                "version": "1.2.3",
                "name": "Beta Crisis",
                "description": "A scenario authored entirely as data.",
                "publisher": "Test MUN Organization",
                "license": "Private test fixture",
                "engine_api_version": 1,
                "required_capabilities": ["chair_objectives.v1", "chair_events.v1"],
                "files": deepcopy(PAYLOAD_FILES),
            },
            "objectives": {"schema_version": 1, "objectives": [{
                "id": "ceasefire", "title": "Agree to a ceasefire",
                "description": "Negotiate a political settlement.", "faction": "FACTION_A",
                "success_criteria": "The chair confirms the agreement.", "points": 10,
            }]},
            "events": {"schema_version": 1, "events": [{
                "id": "supply-interruption", "title": "Supply interruption",
                "body": "The convoy has been delayed.",
                "trigger_note": "The chair may introduce this after negotiations.",
                "faction": "FACTION_A", "effect_type": "supply", "value": -15,
                "duration_hours": 12, "public": False,
            }]},
        })
        self.write_documents()

    def write_documents(self, documents=None):
        for key, value in (documents or self.documents).items():
            (self.source / f"{key}.json").write_text(
                json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8",
            )

    def assert_rejected(self, documents):
        self.write_documents(documents)
        with self.assertRaises(DLCValidationError):
            load_dlc_directory(self.source)

    def make_simulation(self, package=None):
        self.enterContext(patch.object(engine_module, "MapEngine", FlatMap))
        self.enterContext(patch.object(engine_module, "ProvinceEngine", EmptyProvinces))
        simulation = engine_module.SimulationEngine(
            "beta-crisis", package=package or load_dlc_directory(self.source),
            log_file=os.devnull, storage_dir=self.root / "session",
        )
        self.addCleanup(simulation.stop)
        return simulation

    def test_versioned_package_loads_all_existing_simulation_data(self):
        package = load_dlc_directory(self.source)
        self.assertEqual(package.manifest, self.documents["package"])
        self.assertEqual(package.objectives, self.documents["objectives"])
        self.assertEqual(package.events, self.documents["events"])
        self.assertEqual(set(package.units), set(self.documents["units"]))
        self.assertEqual(set(package.weapons), set(self.documents["weapons"]))
        self.assertEqual(set(package.battalions), set(self.documents["battalions"]))
        self.assertEqual(package.scenario["map_config"]["bounds"], self.documents["scenario"]["map_config"]["bounds"])
        self.assertEqual(package.scenario["diplomacy_blocs"], self.documents["scenario"]["diplomacy_blocs"])

    def test_existing_id_loader_remains_compatible(self):
        with patch.object(dlc_loader, "DLC_ROOT", self.root):
            package = load_dlc_package("scenario")
        self.assertEqual(package.manifest["id"], "beta-crisis")
        self.assertEqual(set(package.units), set(self.documents["units"]))

    def test_genuine_legacy_package_loads_without_new_documents(self):
        for name in ("package.json", "objectives.json", "events.json"):
            (self.source / name).unlink()
        package = load_dlc_directory(self.source, "legacy")
        self.assertIsNone(package.manifest)
        self.assertEqual(package.objectives, {"schema_version": 1, "objectives": []})
        self.assertEqual(package.events, {"schema_version": 1, "events": []})
        self.assertEqual(set(package.units), set(self.documents["units"]))

    def test_extension_documents_cannot_be_silently_treated_as_legacy(self):
        (self.source / "package.json").unlink()
        with self.assertRaises(DLCValidationError):
            load_dlc_directory(self.source)

    def test_incompatible_or_malformed_manifest_is_rejected(self):
        cases = [
            ("schema_version", 2), ("schema_version", True),
            ("engine_api_version", 2), ("engine_api_version", "1"),
            ("version", "1.2"), ("version", "01.2.3"), ("version", 1),
            ("id", "../outside"), ("id", "x" * 65), ("id", ""),
            ("required_capabilities", ["automatic_events.v1"]),
            ("required_capabilities", ["chair_events.v1", "chair_events.v1"]),
            ("required_capabilities", "chair_events.v1"),
            ("publisher", ""), ("license", ""), ("script", "execute.py"),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                documents = deepcopy(self.documents)
                documents["package"][field] = value
                self.assert_rejected(documents)

    def test_required_card_capabilities_must_be_declared(self):
        for capability in ("chair_objectives.v1", "chair_events.v1"):
            with self.subTest(capability=capability):
                documents = deepcopy(self.documents)
                documents["package"]["required_capabilities"].remove(capability)
                self.assert_rejected(documents)

    def test_manifest_paths_cannot_escape_or_override_payload_locations(self):
        for path in ("../outside.json", "/outside.json", "C:/outside.json", "nested/units.json", "..\\outside.json"):
            with self.subTest(path=path):
                documents = deepcopy(self.documents)
                documents["package"]["files"]["units"] = path
                self.assert_rejected(documents)

    def test_invalid_objectives_are_rejected(self):
        cases = [
            ("faction", "UNKNOWN"), ("points", -1), ("points", 1_000_001),
            ("points", True), ("points", "10"), ("points", float("nan")),
            ("success_criteria", ""), ("script", "calculate_score()"),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                documents = deepcopy(self.documents)
                documents["objectives"]["objectives"][0][field] = value
                self.assert_rejected(documents)

    def test_invalid_event_values_and_executable_fields_are_rejected(self):
        cases = [
            ("faction", "UNKNOWN"), ("effect_type", "execute_script"),
            ("value", 1_000_001), ("value", -1_000_001), ("value", True),
            ("value", "5"), ("value", float("inf")),
            ("duration_hours", 0), ("duration_hours", -1),
            ("duration_hours", 87601), ("duration_hours", True),
            ("public", "false"), ("public", 0),
            ("trigger", {"game_hours": 4}), ("script", "import os"),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                documents = deepcopy(self.documents)
                documents["events"]["events"][0][field] = value
                self.assert_rejected(documents)

    def test_event_multipliers_and_scenario_effect_permissions_are_enforced(self):
        for effect in ("combat_modifier", "speed_modifier"):
            for value in (-0.1, 100.1):
                with self.subTest(effect=effect, value=value):
                    documents = deepcopy(self.documents)
                    documents["events"]["events"][0].update(effect_type=effect, value=value)
                    self.assert_rejected(documents)
        documents = deepcopy(self.documents)
        documents["rules"]["directives"]["allowed_effects"].remove("supply")
        self.assert_rejected(documents)

    def test_duplicate_card_ids_and_unsupported_document_versions_are_rejected(self):
        for kind in ("objectives", "events"):
            with self.subTest(kind=kind, invalid="duplicate"):
                documents = deepcopy(self.documents)
                documents[kind][kind].append(deepcopy(documents[kind][kind][0]))
                self.assert_rejected(documents)
            with self.subTest(kind=kind, invalid="schema"):
                documents = deepcopy(self.documents)
                documents[kind]["schema_version"] = 2
                self.assert_rejected(documents)

    def test_cards_can_reference_political_roles_bloc_members_and_global_scope(self):
        documents = deepcopy(self.documents)
        documents["scenario"]["committee"]["delegate_roles"].append({
            "faction": "CIVILIAN_COUNCIL", "role": "Civilian Council", "briefing": "Negotiate.",
        })
        documents["scenario"]["diplomacy_blocs"].append({"bloc_name": "Observers", "members": ["OBSERVERS"]})
        for faction in ("CIVILIAN_COUNCIL", "OBSERVERS", documents["rules"]["directives"]["default_faction"]):
            with self.subTest(faction=faction):
                documents["objectives"]["objectives"][0]["faction"] = faction
                documents["events"]["events"][0]["faction"] = faction
                self.write_documents(documents)
                package = load_dlc_directory(self.source)
                self.assertEqual(package.events["events"][0]["faction"], faction)

    def test_cards_are_inert_until_a_chair_adjudicates_an_event(self):
        simulation = self.make_simulation()
        self.assertEqual(simulation.committee_config["package_metadata"]["id"], "beta-crisis")
        self.assertEqual(simulation.committee_config["objectives"], self.documents["objectives"]["objectives"])
        self.assertEqual(simulation.committee_config["events"], self.documents["events"]["events"])
        self.assertEqual(simulation.game_hours, 0)
        self.assertEqual(simulation.committee_records, [])
        self.assertEqual(simulation.units["faction_a_unit"].supply, 100)
        self.assertEqual(simulation.units["faction_b_unit"].supply, 100)
        card = self.documents["events"]["events"][0]
        record = simulation.adjudicate_directive(card)
        self.assertEqual(record["affected_units"], 1)
        self.assertEqual(simulation.units["faction_a_unit"].supply, 85)
        self.assertEqual(simulation.units["faction_b_unit"].supply, 100)
        self.assertFalse(record["public"])
        self.assertEqual(len(simulation.committee_records), 1)

    def test_extreme_numbers_are_validation_errors(self):
        for target in ("objective", "unit"):
            with self.subTest(target=target):
                documents = deepcopy(self.documents)
                if target == "objective":
                    documents["objectives"]["objectives"][0]["points"] = 10 ** 1000
                else:
                    documents["units"]["faction_a_unit"]["morale"] = 10 ** 1000
                self.assert_rejected(documents)

    def test_core_json_rejects_duplicate_keys_and_oversized_documents(self):
        scenario_path = self.source / "scenario.json"
        original = scenario_path.read_text(encoding="utf-8")
        scenario_path.write_text('{"scenario_name": "Ambiguous",' + original[1:], encoding="utf-8")
        with self.assertRaisesRegex(DLCValidationError, "Duplicate JSON field"):
            load_dlc_directory(self.source)
        self.write_documents()
        with patch.object(scenario_package, "MAX_JSON_BYTES", scenario_path.stat().st_size - 1):
            with self.assertRaisesRegex(DLCValidationError, "too large.*scenario.json"):
                load_dlc_directory(self.source)

    def test_scaffold_and_deterministic_build_round_trip(self):
        destination = self.root / "customer-scenario"
        scaffold_package(destination, "customer-crisis", "Customer Crisis", "Example MUN")
        authored = load_dlc_directory(destination)
        self.assertEqual(authored.manifest["id"], "customer-crisis")
        self.assertEqual(authored.manifest["publisher"], "Example MUN")
        self.assertEqual(authored.scenario["scenario_name"], "Customer Crisis")
        first = build_package(destination, self.root / "first.zip")
        second = build_package(destination, self.root / "second.zip")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        extracted = self.root / "installed"
        with zipfile.ZipFile(first) as archive:
            archive.extractall(extracted)
            self.assertTrue(set(PAYLOAD_FILES.values()).issubset(archive.namelist()))
            self.assertFalse(any(name.endswith(".py") for name in archive.namelist()))
        installed = load_dlc_directory(extracted)
        self.assertEqual(installed.manifest["version"], authored.manifest["version"])
        self.assertEqual(installed.units, authored.units)
        self.assertEqual(set(installed.manifest["content_hashes"]), {
            path.relative_to(extracted).as_posix() for path in extracted.rglob("*")
            if path.is_file() and path.name != "package.json"
        })
        self.assertNotIn("content_hashes", json.loads((destination / "package.json").read_text(encoding="utf-8")))

    def test_built_package_rejects_changed_or_added_payload(self):
        output = build_package(self.source, self.root / "release.zip")
        for alteration in ("changed", "added"):
            with self.subTest(alteration=alteration):
                installed = self.root / alteration
                with zipfile.ZipFile(output) as archive:
                    archive.extractall(installed)
                if alteration == "changed":
                    path = installed / "units.json"
                    units = json.loads(path.read_text(encoding="utf-8"))
                    units["faction_a_unit"]["personnel"] += 1
                    path.write_text(json.dumps(units), encoding="utf-8")
                else:
                    (installed / "README.md").write_text("Untracked content", encoding="utf-8")
                with self.assertRaises(DLCValidationError):
                    load_dlc_directory(installed)

    def test_build_and_scaffold_never_overwrite_existing_content(self):
        output = self.root / "release.zip"
        output.write_bytes(b"previous release")
        with self.assertRaises(ValueError):
            build_package(self.source, output)
        self.assertEqual(output.read_bytes(), b"previous release")
        with self.assertRaises(ValueError):
            build_package(self.source, self.source / "release.zip")
        original = (self.source / "scenario.json").read_bytes()
        with self.assertRaises(ValueError):
            scaffold_package(self.source, "new", "New Crisis", "MUN")
        self.assertEqual((self.source / "scenario.json").read_bytes(), original)

    def test_build_rejects_executable_content_and_does_not_create_output(self):
        for name in ("startup.py", "assets/startup.js", "maps/terrain.exe"):
            with self.subTest(name=name):
                path = self.source / name
                path.parent.mkdir(exist_ok=True)
                path.write_text("untrusted executable", encoding="utf-8")
                try:
                    with self.assertRaises(ValueError):
                        build_package(self.source, self.root / "unsafe.zip")
                    self.assertFalse((self.root / "unsafe.zip").exists())
                finally:
                    path.unlink()

    def test_package_rejects_symlinked_assets(self):
        external = self.root / "outside.json"
        external.write_text("{}", encoding="utf-8")
        (self.source / "maps").mkdir()
        link = self.source / "maps" / "borrowed.json"
        try:
            link.symlink_to(external)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"This environment cannot create symlinks: {error}")
        with self.assertRaises(ValueError):
            build_package(self.source, self.root / "linked.zip")
        self.assertFalse((self.root / "linked.zip").exists())

    def test_editor_validation_preserves_the_running_session(self):
        simulation = self.make_simulation()
        simulation.game_hours = 19.5
        simulation.units["faction_a_unit"].supply = 42
        self.enterContext(patch.object(server, "engine", simulation))
        client = server.app.test_client()
        for valid in (True, False):
            with self.subTest(valid=valid):
                documents = deepcopy(self.documents)
                if not valid:
                    documents["events"]["events"][0]["faction"] = "UNKNOWN"
                response = client.post("/api/editor_validate", json=documents)
                self.assertEqual(response.status_code, 200 if valid else 400, response.get_json())
                self.assertEqual(response.get_json()["status"], "ok" if valid else "error")
                self.assertIs(server.engine, simulation)
                self.assertEqual(simulation.game_hours, 19.5)
                self.assertEqual(simulation.units["faction_a_unit"].supply, 42)
                self.assertEqual(simulation.committee_records, [])

    def test_editor_validation_reports_malformed_and_missing_documents(self):
        client = server.app.test_client()
        for payload in (None, [], {"scenario": {}}, {**self.documents, "events": None}):
            with self.subTest(payload_type=type(payload).__name__):
                response = client.post("/api/editor_validate", json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["status"], "error")

    def test_deeply_nested_editor_json_is_rejected_without_server_error(self):
        client = server.app.test_client()
        body = '{"scenario":' + '[' * 2000 + '0' + ']' * 2000 + '}'
        response = client.post("/api/editor_validate", data=body, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["status"], "error")

    def test_editor_template_contains_valid_package_documents(self):
        client = server.app.test_client()
        response = client.get("/api/editor_template")
        self.assertEqual(response.status_code, 200)
        template = response.get_json()
        for key in ("package", "objectives", "events"):
            self.assertIn(key, template)
        payload = {key: template[key] for key in ("package", *PAYLOAD_FILES)}
        validated = client.post("/api/editor_validate", json=payload)
        self.assertEqual(validated.status_code, 200, validated.get_json())


if __name__ == "__main__":
    unittest.main()
