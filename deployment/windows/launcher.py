"""Installed Windows entry point for the private beta.

The tester launches this module through a frozen executable.  It configures
writable user data, applies the external content root, starts one Waitress
process, waits for readiness, and opens the browser.  The source checkout and
Flask development server are not part of the tester workflow.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
import argparse
import ctypes
import io
import json
import logging
import os
import sys
import webbrowser


SOURCE_ROOT = Path(__file__).resolve().parents[2]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from beta_runtime import (  # noqa: E402
    ConfigurationError,
    load_runtime_config,
    prepare_runtime_directories,
    record_runtime_exception,
)


_MUTEX_HANDLE = None


def resource_root() -> Path:
    """Return the immutable resource root in source and PyInstaller builds."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root).resolve()
    return SOURCE_ROOT


def browser_host(host: str) -> str:
    if host in {"0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    return host


def dashboard_url(host: str, port: int) -> str:
    visible_host = browser_host(host)
    if ":" in visible_host and not visible_host.startswith("["):
        visible_host = f"[{visible_host}]"
    return f"http://{visible_host}:{port}/"


def acquire_single_instance() -> bool:
    """Use a per-user Windows mutex; other platforms rely on the port bind."""
    global _MUTEX_HANDLE
    if os.name != "nt":
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, "Local\\CDC-Sim-Private-Beta")
    error = ctypes.get_last_error()
    if not handle:
        raise OSError(error, "Could not create the CDC Sim launch mutex")
    _MUTEX_HANDLE = handle
    return error != 183  # ERROR_ALREADY_EXISTS


def release_single_instance() -> None:
    global _MUTEX_HANDLE
    if os.name == "nt" and _MUTEX_HANDLE:
        with suppress(Exception):
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
            kernel32.CloseHandle.restype = ctypes.c_bool
            kernel32.CloseHandle(_MUTEX_HANDLE)
    _MUTEX_HANDLE = None


def _show_fatal(message: str) -> None:
    if os.name == "nt":
        with suppress(Exception):
            ctypes.windll.user32.MessageBoxW(None, message, "CDC Sim could not start", 0x10)
            return
    print(message, file=sys.stderr)


def configure_application():
    """Load the validated runtime and apply it before importing the server."""
    root = resource_root()
    os.environ.setdefault("CDC_CONTENT_DIR", str(root / "dlc"))
    config = prepare_runtime_directories(load_runtime_config())

    # These assignments preserve compatibility with modules that still import
    # the legacy constants. The server uses its explicit runtime configuration.
    import dlc_loader

    dlc_loader.PROJECT_ROOT = config.session_dir
    dlc_loader.DLC_ROOT = config.content_dir
    import engine

    engine.PROJECT_ROOT = config.session_dir
    import server
    if server.RUNTIME_CONFIG.allow_remote:
        raise ConfigurationError("The installed private beta must remain bound to this computer")

    return server, server.RUNTIME_CONFIG, server.BUILD_INFO, server.RUNTIME_LOGGER


def run_self_test() -> int:
    """Exercise packaged resources and core routes without opening a socket."""
    server, config, build, logger = configure_application()
    checks: dict[str, object] = {"version": build.version, "content": str(config.content_dir.name)}
    try:
        import gis
        import waitress  # noqa: F401 - confirms the packaged production server is present
        if not gis.HAS_RASTERIO:
            raise RuntimeError("The packaged build cannot load Rasterio GIS support")
        with server.app.test_client() as client:
            for route in ("/api/health", "/api/version", "/", "/status", "/editor"):
                response = client.get(route)
                if response.status_code != 200:
                    raise RuntimeError(f"Self-test route failed: {route} ({response.status_code})")
                if route == "/api/health" and response.get_json().get("status") != "ok":
                    raise RuntimeError("Packaged readiness checks did not pass")
            packages = client.get("/api/list_dlcs").get_json()
            expected_scenario = os.environ.get("CDC_SELF_TEST_SCENARIO", "test")
            ready = next(
                (item for item in packages if item.get("id") == expected_scenario and item.get("valid") is True),
                None,
            )
            if ready is None:
                raise RuntimeError("The expected packaged self-test scenario is not ready")
            mounted = client.post("/api/mount_dlc", json={"dlc_id": ready["id"]})
            if mounted.status_code != 200:
                raise RuntimeError(f"Packaged scenario failed to mount ({mounted.status_code})")
            saved = client.post("/api/save_game", json={"slot": "slot_1"})
            if saved.status_code != 200:
                raise RuntimeError(f"Packaged checkpoint failed ({saved.status_code})")
            local_header = {"X-CDC-Requested-With": "CDC-Sim-UI"}
            backup = client.post("/api/session_backup", headers=local_header)
            if backup.status_code != 200 or backup.mimetype != "application/zip":
                raise RuntimeError(f"Packaged backup export failed ({backup.status_code})")
            restored = client.post(
                "/api/session_backup/restore",
                data={"confirmation": "RESTORE", "backup": (io.BytesIO(backup.data), "backup.zip")},
                headers=local_header,
                content_type="multipart/form-data",
            )
            if restored.status_code != 200:
                raise RuntimeError(f"Packaged backup restore failed ({restored.status_code})")
            checks.update({"scenario": ready["id"], "routes": 5, "checkpoint": True, "backup": True})
        if server.engine is not None:
            server.engine.stop()
        print(json.dumps({"status": "ok", "checks": checks}, sort_keys=True))
        logger.info("Packaged self-test passed", extra={"event": "release.self_test_passed"})
        return 0
    except Exception as exc:
        support_id = record_runtime_exception(
            logger, exc, operation="release.self_test_failed", context={"stage": "installed"}
        )
        print(json.dumps({"status": "error", "support_id": support_id}), file=sys.stderr)
        if server.engine is not None:
            server.engine.stop()
        return 1


def run_server() -> int:
    server = None
    logger = None
    try:
        server, config, build, logger = configure_application()
        url = dashboard_url(config.host, config.port)
        if not acquire_single_instance():
            if config.open_browser:
                webbrowser.open(url, new=1)
            print("CDC Sim is already running. The existing dashboard was opened.")
            return 0

        print(f"CDC Sim {build.version} is starting.")
        print(f"Your dashboard will open automatically: {url}")
        print("Keep this window open. Press Ctrl+C here to stop CDC Sim after saving a checkpoint.")
        logger.info(
            "Runtime starting",
            extra={"event": "runtime.starting", "details": {"profile": config.profile}},
        )
        server.schedule_browser_open()

        from waitress import serve

        serve(
            server.app,
            host=config.host,
            port=config.port,
            threads=8,
            ident="CDC-Sim",
            expose_tracebacks=False,
            clear_untrusted_proxy_headers=True,
            max_request_header_size=64 * 1024,
            max_request_body_size=70 * 1024 * 1024,
            connection_limit=100,
            channel_timeout=120,
        )
        return 0
    except KeyboardInterrupt:
        if logger:
            logger.info("Runtime stopped by operator", extra={"event": "runtime.stopped"})
        return 0
    except (ConfigurationError, ImportError, OSError, RuntimeError, ValueError) as exc:
        if logger:
            support_id = record_runtime_exception(
                logger, exc, operation="runtime.start_failed", context={"stage": "startup"}
            )
            message = f"CDC Sim could not start. Support ID: {support_id}"
        else:
            message = "CDC Sim could not start. Check the installation and runtime configuration."
        _show_fatal(message)
        return 1
    finally:
        if server is not None and server.engine is not None:
            server.engine.stop()
        logging.shutdown()
        release_single_instance()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--self-test", action="store_true")
    arguments, unknown = parser.parse_known_args(argv)
    if unknown:
        _show_fatal("CDC Sim received an unsupported launch option.")
        return 2
    return run_self_test() if arguments.self_test else run_server()


if __name__ == "__main__":
    raise SystemExit(main())

