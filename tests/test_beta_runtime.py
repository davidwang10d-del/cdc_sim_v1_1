"""Focused tests for private-beta runtime support boundaries."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import logging
import unittest
from unittest.mock import patch

from beta_runtime import (
    ConfigurationError,
    configure_runtime_logging,
    load_build_info,
    load_runtime_config,
    prepare_runtime_directories,
    public_health_payload,
    record_runtime_exception,
    support_diagnostics,
)


ROOT = Path(__file__).resolve().parents[1]


class BetaRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.content = self.root / "content"
        self.content.mkdir()
        self.environment = {
            "LOCALAPPDATA": str(self.root / "local-data"),
            "CDC_CONTENT_DIR": str(self.content),
        }

    def tearDown(self):
        for name in tuple(logging.Logger.manager.loggerDict):
            if name.startswith("cdc_sim_test."):
                logger = logging.getLogger(name)
                for handler in list(logger.handlers):
                    logger.removeHandler(handler)
                    handler.close()
        self.temporary.cleanup()

    def test_repository_build_metadata_is_valid_and_versioned(self):
        info = load_build_info(ROOT / "build_info.json")
        self.assertEqual(info.product, "CDC Sim")
        self.assertEqual(info.version, "1.1.0-beta.1")
        self.assertEqual(info.scenario_api_version, 1)
        self.assertNotIn("source_revision", info.public_dict())

    def test_build_metadata_rejects_duplicate_or_unknown_fields(self):
        duplicate = self.root / "duplicate.json"
        duplicate.write_text(
            '{"schema_version":1,"schema_version":1,"product":"CDC Sim"}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ConfigurationError, "duplicate field"):
            load_build_info(duplicate)

        document = json.loads((ROOT / "build_info.json").read_text(encoding="utf-8"))
        document["untrusted"] = True
        unknown = self.root / "unknown.json"
        unknown.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ConfigurationError, "unknown untrusted"):
            load_build_info(unknown)

    def test_build_metadata_wraps_parser_recursion_failure(self):
        nested = self.root / "nested.json"
        nested.write_text('{"schema_version": 1}', encoding="utf-8")
        with patch("beta_runtime.json.loads", side_effect=RecursionError):
            with self.assertRaisesRegex(ConfigurationError, "not valid UTF-8 JSON"):
                load_build_info(nested)

    def test_runtime_defaults_separate_install_content_and_user_data(self):
        config = load_runtime_config(environ=self.environment)
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 5000)
        self.assertFalse(config.allow_remote)
        self.assertEqual(config.data_dir, (self.root / "local-data" / "CDC Sim").resolve())
        self.assertEqual(config.content_dir, self.content.resolve())
        self.assertNotEqual(config.data_dir, config.content_dir)
        self.assertEqual(config.session_dir.parent, config.data_dir)

    def test_json_config_is_relative_to_itself_and_environment_has_precedence(self):
        config_directory = self.root / "configuration"
        config_directory.mkdir()
        config_path = config_directory / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "profile": "development",
                    "data_dir": "state",
                    "content_dir": "packs",
                    "port": 5100,
                    "open_browser": False,
                }
            ),
            encoding="utf-8",
        )
        environment = {**self.environment, "CDC_PORT": "5200", "CDC_LOG_LEVEL": "warning"}
        config = load_runtime_config(config_path, environ=environment)
        self.assertEqual(config.profile, "development")
        self.assertEqual(config.data_dir, (config_directory / "state").resolve())
        self.assertEqual(config.content_dir, self.content.resolve())
        self.assertEqual(config.port, 5200)
        self.assertEqual(config.log_level, "WARNING")
        self.assertFalse(config.open_browser)

    def test_default_config_is_discovered_under_an_overridden_data_root(self):
        data_root = self.root / "configured-data"
        data_root.mkdir()
        (data_root / "config.json").write_text(
            json.dumps({"schema_version": 1, "port": 5300}), encoding="utf-8"
        )
        config = load_runtime_config(
            environ={
                "LOCALAPPDATA": str(self.root / "unused"),
                "CDC_DATA_DIR": str(data_root),
                "CDC_CONTENT_DIR": str(self.content),
            }
        )
        self.assertEqual(config.config_file, (data_root / "config.json").resolve())
        self.assertEqual(config.data_dir, data_root.resolve())
        self.assertEqual(config.port, 5300)

    def test_remote_binding_requires_an_explicit_gate(self):
        with self.assertRaisesRegex(ConfigurationError, "Remote binding is disabled"):
            load_runtime_config(environ={**self.environment, "CDC_HOST": "0.0.0.0"})
        config = load_runtime_config(
            environ={
                **self.environment,
                "CDC_HOST": "0.0.0.0",
                "CDC_ALLOW_REMOTE": "true",
            }
        )
        self.assertTrue(config.allow_remote)
        self.assertEqual(config.host, "0.0.0.0")

    def test_configuration_rejects_unknown_fields_and_bad_scalar_types(self):
        cases = [
            ({"schema_version": 1, "password": "do-not-accept-secrets"}, "unknown fields"),
            ({"schema_version": 1, "port": True}, "port must be an integer"),
            ({"schema_version": 1, "open_browser": 1}, "open_browser must be true or false"),
            ({"schema_version": 2}, "schema_version must be integer 1"),
        ]
        for index, (document, message) in enumerate(cases):
            with self.subTest(index=index):
                path = self.root / f"bad-{index}.json"
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaisesRegex(ConfigurationError, message):
                    load_runtime_config(path, environ=self.environment)

    def test_runtime_rejects_overlapping_content_and_customer_data(self):
        data_root = self.root / "shared"
        with self.assertRaisesRegex(ConfigurationError, "non-overlapping"):
            load_runtime_config(environ={
                **self.environment,
                "CDC_DATA_DIR": str(data_root),
                "CDC_CONTENT_DIR": str(data_root / "content"),
            })

    def test_prepare_runtime_directories_creates_the_writable_boundary(self):
        config = load_runtime_config(environ=self.environment)
        prepare_runtime_directories(config)
        self.assertTrue(config.data_dir.is_dir())
        self.assertTrue(config.session_dir.is_dir())
        self.assertTrue(config.log_dir.is_dir())
        self.assertTrue(config.support_dir.is_dir())
        self.assertFalse(any(config.data_dir.rglob(".write-test-*")))

    def test_structured_logger_redacts_common_credentials_and_customer_paths(self):
        config = prepare_runtime_directories(load_runtime_config(environ=self.environment))
        info = load_build_info(ROOT / "build_info.json")
        logger = configure_runtime_logging(
            config, info, logger_name="cdc_sim_test.redaction", console=False
        )
        logger.warning(
            "authorization=Bearer abc.def.ghi contact=chair@example.org path=C:\\Users\\Alice\\case.json",
            extra={
                "event": "request.rejected",
                "details": {"api_key": "top-secret", "email": "user@example.org"},
            },
        )
        for handler in logger.handlers:
            handler.flush()
        text = (config.log_dir / "cdc-sim.jsonl").read_text(encoding="utf-8")
        record = json.loads(text)
        self.assertEqual(record["event"], "request.rejected")
        self.assertNotIn("abc.def.ghi", text)
        self.assertNotIn("top-secret", text)
        self.assertNotIn("chair@example.org", text)
        self.assertNotIn("user@example.org", text)
        self.assertNotIn("Alice", text)
        self.assertIn("[REDACTED]", text)

    def test_structured_log_rotation_is_bounded(self):
        environment = {
            **self.environment,
            "CDC_LOG_MAX_BYTES": str(64 * 1024),
            "CDC_LOG_BACKUP_COUNT": "1",
        }
        config = prepare_runtime_directories(load_runtime_config(environ=environment))
        info = load_build_info(ROOT / "build_info.json")
        logger = configure_runtime_logging(
            config, info, logger_name="cdc_sim_test.rotation", console=False
        )
        for index in range(40):
            logger.info("x" * 4000, extra={"event": "rotation.test", "details": {"index": index}})
        for handler in logger.handlers:
            handler.flush()
        current = config.log_dir / "cdc-sim.jsonl"
        previous = config.log_dir / "cdc-sim.jsonl.1"
        self.assertTrue(current.is_file())
        self.assertTrue(previous.is_file())
        self.assertFalse((config.log_dir / "cdc-sim.jsonl.2").exists())
        self.assertLessEqual(current.stat().st_size, config.log_max_bytes)
        self.assertLessEqual(previous.stat().st_size, config.log_max_bytes)

    def test_exception_record_uses_correlation_id_without_exception_message(self):
        config = prepare_runtime_directories(load_runtime_config(environ=self.environment))
        info = load_build_info(ROOT / "build_info.json")
        logger = configure_runtime_logging(
            config, info, logger_name="cdc_sim_test.exception", console=False
        )
        try:
            raise RuntimeError("Customer Falcon password=classified")
        except RuntimeError as exc:
            support_id = record_runtime_exception(
                logger,
                exc,
                operation="scenario.mount_failed",
                context={
                    "customer_email": "chair@example.org",
                    "customer_name": "Falcon Organization",
                    "token": "classified",
                },
            )
        for handler in logger.handlers:
            handler.flush()
        text = (config.log_dir / "cdc-sim.jsonl").read_text(encoding="utf-8")
        record = json.loads(text)
        self.assertRegex(support_id, r"^ERR-[A-F0-9]{12}$")
        self.assertEqual(record["support_id"], support_id)
        self.assertEqual(record["exception_type"], "RuntimeError")
        self.assertNotIn("Falcon", text)
        self.assertNotIn("Organization", text)
        self.assertNotIn("classified", text)
        self.assertNotIn(str(self.root), text)
        self.assertEqual(record["details"]["context"]["token"], "[REDACTED]")

    def test_public_health_exposes_version_and_boolean_checks_only(self):
        info = load_build_info(ROOT / "build_info.json")
        payload = public_health_payload(
            info, ready=True, checks={"dependencies": True, "content": True}
        )
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["build"]["version"], info.version)
        serialized = json.dumps(payload)
        self.assertNotIn("source_revision", serialized)
        self.assertNotIn("cwd", serialized)
        self.assertNotIn("python", serialized)
        with self.assertRaisesRegex(ValueError, "must be boolean"):
            public_health_payload(info, checks={"dependencies": "yes"})

    def test_support_diagnostics_contains_no_paths_or_environment_values(self):
        config = prepare_runtime_directories(load_runtime_config(environ=self.environment))
        info = load_build_info(ROOT / "build_info.json")
        payload = support_diagnostics(config, info, checks={"content": True})
        serialized = json.dumps(payload)
        self.assertEqual(payload["schema_version"], 1)
        self.assertTrue(payload["storage"]["data"]["accessible"])
        self.assertTrue(payload["storage"]["content"]["accessible"])
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("LOCALAPPDATA", serialized)
        self.assertNotIn("CDC_CONTENT_DIR", serialized)
        self.assertNotIn("username", serialized.lower())


if __name__ == "__main__":
    unittest.main()
