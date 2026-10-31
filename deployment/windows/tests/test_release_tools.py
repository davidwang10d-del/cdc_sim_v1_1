from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import copy
import json
import sys
import unittest


WINDOWS_DIR = Path(__file__).resolve().parents[1]
ROOT = WINDOWS_DIR.parents[1]
sys.path.insert(0, str(WINDOWS_DIR))

from release_tools import (
    ReleaseValidationError,
    load_release_config,
    pyinstaller_data,
    validate_bundle,
    validate_source,
    verify_manifest,
    write_manifest,
)


class WindowsReleasePolicyTests(unittest.TestCase):
    def test_repository_release_config_is_strict_and_excludes_private_content(self):
        config = load_release_config(WINDOWS_DIR / "release_config.json")
        self.assertEqual(config["architecture"], "x64")
        self.assertGreaterEqual(len([item for item in config["bundled_scenarios"] if not item.startswith("_")]), 1)

    def test_source_policy_validates_allowlist_and_reports_current_external_assets(self):
        result = validate_source(ROOT, WINDOWS_DIR / "release_config.json", beta=False)
        self.assertEqual(result["status"], "ok")
        for scenario_id in load_release_config(WINDOWS_DIR / "release_config.json")["bundled_scenarios"]:
            self.assertIn(scenario_id, result["scenarios"])
        self.assertEqual(result["unapproved_runtime_services"], [])
        self.assertEqual(result["prohibited_product_license_references"], [])
        with self.assertRaisesRegex(ReleaseValidationError, "finalized, legally reviewed EULA"):
            validate_source(ROOT, WINDOWS_DIR / "release_config.json", beta=True)

    def test_pyinstaller_inputs_are_individual_allowlisted_files(self):
        entries = pyinstaller_data(ROOT, WINDOWS_DIR / "release_config.json", ROOT / "build_info.json")
        sources = [Path(source).resolve() for source, _ in entries]
        self.assertTrue(any(path.name == "index.html" for path in sources))
        self.assertTrue(any("dlc" in path.parts and "test" in path.parts for path in sources))
        allowed = {item.casefold() for item in load_release_config(WINDOWS_DIR / "release_config.json")["bundled_scenarios"]}
        for source in sources:
            folded = tuple(part.casefold() for part in source.parts)
            if "dlc" in folded:
                self.assertIn(folded[folded.index("dlc") + 1], allowed)
        self.assertFalse(any(path.suffix.casefold() in {".py", ".pyc"} for path in sources))
        self.assertIn((ROOT / "EULA.txt").resolve(), sources)
        self.assertIn((ROOT / "THIRD-PARTY-NOTICES.txt").resolve(), sources)
        self.assertNotIn((ROOT / "LICENSE").resolve(), sources)
        self.assertFalse(any(path.name == "dem_scanner.py" for path in sources))

    def test_config_refuses_unsafe_scenario_identifier(self):
        with TemporaryDirectory() as temporary:
            document = load_release_config(WINDOWS_DIR / "release_config.json")
            document["bundled_scenarios"].append("../customer-content")
            path = Path(temporary) / "release.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ReleaseValidationError, "Invalid bundled scenario ID"):
                load_release_config(path)

    def test_bundle_manifest_detects_tampering_and_forbidden_source(self):
        config = load_release_config(WINDOWS_DIR / "release_config.json")
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            bundle = base / "bundle"
            internal = bundle / "_internal"
            required = [
                bundle / config["executable_name"],
                internal / "build_info.json",
                internal / "EULA.txt",
                internal / "THIRD-PARTY-NOTICES.txt",
                internal / "third-party-licenses" / "INDEX.txt",
                internal / "templates" / "index.html",
                internal / "templates" / "status.html",
                internal / "static" / "css" / "style.css",
                internal / "static" / "js" / "tactical_engine.js",
                internal / "static" / "vendor" / "leaflet" / "leaflet.css",
                internal / "static" / "vendor" / "leaflet" / "leaflet.js",
                internal / "static" / "vendor" / "leaflet" / "LICENSE",
                internal / "static" / "vendor" / "leaflet" / "images" / "marker-icon.png",
                internal / "static" / "vendor" / "leaflet" / "images" / "marker-icon-2x.png",
                internal / "static" / "vendor" / "leaflet" / "images" / "marker-shadow.png",
                internal / "static" / "vendor" / "jszip" / "jszip.min.js",
                internal / "static" / "vendor" / "jszip" / "LICENSE-MIT.txt",
                internal / "static" / "vendor" / "jszip" / "PAKO-LICENSE-MIT.txt",
                internal / "static" / "vendor" / "jszip" / "PAKO-ZLIB-LICENSE.txt",
                internal / "static" / "vendor" / "README.md",
            ]
            for scenario_id in config["bundled_scenarios"]:
                required.extend(
                    internal / "dlc" / scenario_id / name
                    for name in ("scenario.json", "units.json", "weapons.json", "battalions.json", "rules.json")
                )
            for path in required:
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.name == "EULA.txt":
                    path.write_text((ROOT / "EULA.txt").read_text(encoding="utf-8"), encoding="utf-8")
                elif path.name == "build_info.json":
                    build = json.loads((ROOT / "build_info.json").read_text(encoding="utf-8"))
                    build.update(
                        {
                            "build_id": "beta-0123456789ab",
                            "source_revision": "0123456789abcdef0123456789abcdef01234567",
                            "built_at_utc": "2026-09-12T12:00:00Z",
                        }
                    )
                    path.write_text(json.dumps(build), encoding="utf-8")
                else:
                    path.write_bytes(b"fixture")
            public_ca = internal / "certifi" / "cacert.pem"
            public_ca.parent.mkdir(parents=True, exist_ok=True)
            public_ca.write_text("public trust anchors", encoding="utf-8")
            self.assertEqual(validate_bundle(bundle, WINDOWS_DIR / "release_config.json")["status"], "ok")
            legacy_license = internal / "LICENSE"
            legacy_license.write_text("legacy project terms", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseValidationError, "legacy project GPL license"):
                validate_bundle(bundle, WINDOWS_DIR / "release_config.json")
            legacy_license.unlink()
            prohibited_option = internal / "static" / "vendor" / "jszip" / "unexpected-license.txt"
            prohibited_option.write_text("GNU GENERAL PUBLIC LICENSE", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseValidationError, "prohibited copyleft"):
                validate_bundle(bundle, WINDOWS_DIR / "release_config.json")
            prohibited_option.unlink()
            packaged_build_info = internal / "build_info.json"
            stamped_build = packaged_build_info.read_text(encoding="utf-8")
            placeholder = json.loads(stamped_build)
            placeholder.update({"build_id": "development", "source_revision": "unknown", "built_at_utc": None})
            packaged_build_info.write_text(json.dumps(placeholder), encoding="utf-8")
            with self.assertRaisesRegex(ReleaseValidationError, "unstamped build metadata"):
                validate_bundle(bundle, WINDOWS_DIR / "release_config.json")
            packaged_build_info.write_text(stamped_build, encoding="utf-8")
            extra_scenario = internal / "dlc" / "unselected-customer" / "scenario.json"
            extra_scenario.parent.mkdir(parents=True, exist_ok=True)
            extra_scenario.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseValidationError, "unselected scenario"):
                validate_bundle(bundle, WINDOWS_DIR / "release_config.json")
            extra_scenario.unlink()
            secret_key = internal / "customer-private.pem"
            secret_key.write_text("secret", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseValidationError, "secret material"):
                validate_bundle(bundle, WINDOWS_DIR / "release_config.json")
            secret_key.unlink()
            manifest = write_manifest(
                bundle,
                WINDOWS_DIR / "release_config.json",
                packaged_build_info,
                base / "release-manifest.json",
            )
            self.assertEqual(verify_manifest(bundle, manifest)["status"], "ok")
            required[-1].write_bytes(b"changed")
            with self.assertRaisesRegex(ReleaseValidationError, "changed"):
                verify_manifest(bundle, manifest)
            exposed = internal / "server.py"
            exposed.write_text("secret source", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseValidationError, "exposes source"):
                validate_bundle(bundle, WINDOWS_DIR / "release_config.json")


if __name__ == "__main__":
    unittest.main()
