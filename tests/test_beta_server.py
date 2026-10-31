from __future__ import annotations

import io
import json
from pathlib import Path
import re
import tempfile
import threading
import unittest
from unittest.mock import patch

import server


class _Session:
    def __init__(self, storage_dir):
        self.storage_dir = Path(storage_dir)
        self.dlc_id = "demo"
        self.scenario_data = {"scenario_name": "Demo"}
        self.lock = threading.RLock()
        self.is_paused = False


def _save(marker):
    return {
        "format_version": 4,
        "dlc_id": "demo",
        "rules_schema_version": 1,
        "game_hours": marker,
        "units": {},
        "installations": {},
    }


class BetaServerTests(unittest.TestCase):
    def setUp(self):
        self.old_engine = server.engine
        self.client = server.app.test_client()
        self.local_headers = {"X-CDC-Requested-With": "CDC-Sim-UI"}
        self.temporary = tempfile.TemporaryDirectory()
        server.engine = _Session(self.temporary.name)

    def tearDown(self):
        server.engine = self.old_engine
        self.temporary.cleanup()

    def test_public_health_and_version_do_not_disclose_install_paths(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("build", payload)
        self.assertIn("checks", payload)
        serialized = json.dumps(payload).lower()
        self.assertNotIn("cwd", serialized)
        self.assertNotIn("venv", serialized)
        self.assertNotIn("source_revision", serialized)
        self.assertEqual(response.headers["X-CDC-Sim-Version"], payload["build"]["version"])

    def test_support_diagnostics_requires_local_ui_request(self):
        denied = self.client.post("/api/support_diagnostics")
        self.assertEqual(denied.status_code, 403)
        remote = self.client.post(
            "/api/support_diagnostics",
            headers=self.local_headers,
            environ_base={"REMOTE_ADDR": "192.0.2.10"},
        )
        self.assertEqual(remote.status_code, 403)
        allowed = self.client.post("/api/support_diagnostics", headers=self.local_headers)
        self.assertEqual(allowed.status_code, 200)
        serialized = json.dumps(allowed.get_json())
        self.assertNotIn(str(server.RUNTIME_CONFIG.data_dir), serialized)

    def test_session_backup_export_and_restore_are_validated_and_explicit(self):
        save_path = Path(self.temporary.name) / "save_slot_1.json"
        save_path.write_text(json.dumps(_save(7)), encoding="utf-8")
        exported = self.client.post("/api/session_backup", headers=self.local_headers)
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.mimetype, "application/zip")
        self.assertIn("cdc-sim-demo-", exported.headers["Content-Disposition"])

        save_path.write_text(json.dumps(_save(99)), encoding="utf-8")
        missing_confirmation = self.client.post(
            "/api/session_backup/restore",
            headers=self.local_headers,
            data={"backup": (io.BytesIO(exported.data), "backup.zip")},
        )
        self.assertEqual(missing_confirmation.status_code, 400)
        self.assertEqual(json.loads(save_path.read_text())["game_hours"], 99)

        restored = self.client.post(
            "/api/session_backup/restore",
            headers=self.local_headers,
            data={
                "confirmation": "RESTORE",
                "backup": (io.BytesIO(exported.data), "backup.zip"),
            },
        )
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(json.loads(save_path.read_text())["game_hours"], 7)
        self.assertTrue(server.engine.is_paused)

    def test_unexpected_errors_return_support_id_without_exception_text(self):
        with patch.object(server, "load_dlc_package", side_effect=RuntimeError("private customer secret")):
            response = self.client.post("/api/mount_dlc", json={"dlc_id": "demo"})
        self.assertEqual(response.status_code, 500)
        payload = response.get_json()
        self.assertRegex(payload["support_id"], r"^ERR-[A-F0-9]{12}$")
        self.assertIn(payload["support_id"], payload["msg"])
        self.assertNotIn("private customer secret", json.dumps(payload))

    def test_api_errors_keep_english_and_add_chinese_ui_copy(self):
        response = self.client.post("/api/support_diagnostics")
        self.assertEqual(response.status_code, 403)
        payload = response.get_json()
        self.assertEqual(
            payload["msg"],
            "This support action is available only from the local CDC Sim interface",
        )
        self.assertIn("本机 CDC Sim", payload["msg_zh"])
        self.assertIn("支持编号：ERR-ABC123", server.api_message_zh("The scenario could not be opened. Support ID: ERR-ABC123"))
        self.assertEqual(server.api_message_zh("Longitude must be a number"), "经度必须是数字。")
        self.assertEqual(
            server.api_message_zh("Checkpoint [slot_1] already contains a save; confirm overwrite"),
            "检查点 [slot_1] 已有存档；请确认覆盖。",
        )
        self.assertEqual(
            server.api_message_zh(
                "Relocate order issued to Alpha One using Defensive posture; "
                "queued while the simulation is paused — press Run to begin movement",
                failure=False,
            ),
            "已向 Alpha One 下达“安全转移”命令，战斗方式为“防守优先”；"
            "推演已暂停，按“运行”后开始移动。",
        )
        self.assertEqual(
            server.api_message_zh("Target is outside bombard range (90.0km > 50.0km)"),
            "目标超出炮击范围（90.0 公里 > 50.0 公里）。",
        )
        self.assertEqual(
            server.api_message_zh("Save at least one manual checkpoint before downloading a backup"),
            "下载备份前，请至少保存一个手动检查点。",
        )

    def test_beta_pages_use_local_libraries_and_visible_recovery_controls(self):
        index = self.client.get("/").get_data(as_text=True)
        status = self.client.get("/status").get_data(as_text=True)
        editor = self.client.get("/editor").get_data(as_text=True)
        self.assertIn("/static/vendor/leaflet/leaflet.js", index)
        self.assertIn("/static/vendor/leaflet/leaflet.css", index)
        self.assertIn("/static/vendor/jszip/jszip.min.js", editor)
        self.assertNotRegex(index + editor, r'<(?:script|link)[^>]+https?://')
        self.assertIn("connection-banner", index)
        self.assertIn("Local map", index)
        self.assertNotIn("map-service-banner", index)
        self.assertIn("Download backup", index)
        self.assertIn(server.BUILD_INFO.version, index)
        self.assertIn(server.BUILD_INFO.build_id, status)
        self.assertIn("Copy diagnostics", status)


if __name__ == "__main__":
    unittest.main()

