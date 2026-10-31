import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from beta_backup import (
    BackupError, create_backup, inspect_backup, migrate_legacy_checkpoints, restore_backup,
)


def save_bytes(dlc="demo", marker=1):
    return json.dumps({
        "format_version": 4, "dlc_id": dlc, "rules_schema_version": 1,
        "game_hours": marker, "units": {}, "installations": {},
    }).encode()


class BetaBackupTests(unittest.TestCase):
    def test_backup_round_trip_restores_only_validated_checkpoints(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"; target = Path(temporary) / "target"
            source.mkdir(); target.mkdir()
            (source / "save_slot_1.json").write_bytes(save_bytes(marker=12))
            (source / "battle_log.txt").write_text("committee log", encoding="utf-8")
            artifact = create_backup(source, "demo", "Demo", "1.2.3")
            self.assertRegex(artifact.filename, r"^cdc-sim-demo-\d{8}-\d{6}Z\.zip$")
            manifest, saves = inspect_backup(artifact.data, "demo")
            self.assertEqual(manifest["product_version"], "1.2.3")
            self.assertEqual(set(saves), {"save_slot_1.json"})
            restored = restore_backup(target, artifact.data, "demo")
            self.assertEqual(restored, ["save_slot_1.json"])
            self.assertEqual(json.loads((target / restored[0]).read_text())["game_hours"], 12)
            self.assertFalse((target / "battle_log.txt").exists())

    def test_backup_requires_checkpoint_and_matching_scenario(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(BackupError, "at least one"):
                create_backup(root, "demo", "Demo", "1.0.0")
            (root / "save_slot_1.json").write_bytes(save_bytes("other"))
            with self.assertRaisesRegex(BackupError, "belongs"):
                create_backup(root, "demo", "Demo", "1.0.0")

    def test_import_rejects_tamper_extra_paths_duplicates_and_wrong_scenario(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "save_slot_1.json").write_bytes(save_bytes())
            artifact = create_backup(root, "demo", "Demo", "1.0.0")
            with self.assertRaisesRegex(BackupError, "belongs"):
                inspect_backup(artifact.data, "other")

            malformed_manifest = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(artifact.data)) as source, zipfile.ZipFile(malformed_manifest, "w") as target:
                for info in source.infolist():
                    data = source.read(info)
                    if info.filename == "backup.json":
                        manifest = json.loads(data)
                        manifest["restorable_files"] = [{}]
                        data = json.dumps(manifest).encode()
                    target.writestr(info, data)
            with self.assertRaisesRegex(BackupError, "restorable-file inventory"):
                inspect_backup(malformed_manifest.getvalue(), "demo")
            cases = [
                [("backup.json", b"{}"), ("../escape.py", b"x")],
                [("backup.json", b"{}"), ("SAVE_SLOT_1.JSON", b"{}"), ("save_slot_1.json", b"{}")],
            ]
            for entries in cases:
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w") as archive:
                    for name, data in entries:
                        archive.writestr(name, data)
                with self.assertRaises(BackupError):
                    inspect_backup(buffer.getvalue(), "demo")
            tampered = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(artifact.data)) as source, zipfile.ZipFile(tampered, "w") as target:
                for info in source.infolist():
                    data = source.read(info)
                    target.writestr(info.filename, b"changed" if info.filename == "save_slot_1.json" else data)
            with self.assertRaisesRegex(BackupError, "changed"):
                inspect_backup(tampered.getvalue(), "demo")

    def test_legacy_checkpoint_migration_copies_only_matching_scenario_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); legacy = root / "legacy"; target = root / "sessions"
            legacy.mkdir()
            (legacy / "save_slot_1.json").write_bytes(save_bytes("demo", 4))
            (legacy / "save_slot_2.json").write_bytes(save_bytes("other", 8))
            self.assertEqual(migrate_legacy_checkpoints(legacy, target, "demo"), ["save_slot_1.json"])
            self.assertTrue((legacy / "save_slot_1.json").exists())
            self.assertFalse((target / "save_slot_2.json").exists())
            (target / "save_slot_1.json").write_bytes(save_bytes("demo", 9))
            self.assertEqual(migrate_legacy_checkpoints(legacy, target, "demo"), [])
            self.assertEqual(json.loads((target / "save_slot_1.json").read_text())["game_hours"], 9)

    def test_restore_rolls_back_all_checkpoints_when_a_replace_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / "source"; target = root / "target"
            source.mkdir(); target.mkdir()
            for slot, marker in ((1, 10), (2, 20)):
                (source / f"save_slot_{slot}.json").write_bytes(save_bytes("demo", marker))
                (target / f"save_slot_{slot}.json").write_bytes(save_bytes("demo", marker + 1))
            archive = create_backup(source, "demo", "Demo", "1.0.0").data
            original_replace = __import__("os").replace

            def fail_second_new_file(src, dst):
                if Path(dst).name == "save_slot_2.json" and ".restore-" in Path(src).name:
                    raise OSError("simulated storage failure")
                return original_replace(src, dst)

            with patch("beta_backup.os.replace", side_effect=fail_second_new_file):
                with self.assertRaisesRegex(BackupError, "retained"):
                    restore_backup(target, archive, "demo")
            self.assertEqual(json.loads((target / "save_slot_1.json").read_text())["game_hours"], 11)
            self.assertEqual(json.loads((target / "save_slot_2.json").read_text())["game_hours"], 21)

    def test_restore_validates_everything_before_replacing_existing_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = save_bytes(marker=2)
            (root / "save_slot_1.json").write_bytes(old)
            with self.assertRaises(BackupError):
                restore_backup(root, b"not a zip", "demo")
            self.assertEqual((root / "save_slot_1.json").read_bytes(), old)


if __name__ == "__main__":
    unittest.main()

