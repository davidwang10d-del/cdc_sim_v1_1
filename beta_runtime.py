"""Private-beta runtime configuration, build identity, and safe diagnostics.

This module has no Flask or simulation-engine dependency.  The application entry
point can adopt it incrementally while the engine continues to accept explicit
``storage_dir`` and ``log_file`` values.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Mapping
import ipaddress
import json
import logging
import math
import os
import platform
import re
import sys
import uuid


_MODULE_ROOT = Path(__file__).resolve().parent
_BUILD_INFO_PATH = _MODULE_ROOT / "build_info.json"
_MAX_CONFIG_BYTES = 64 * 1024
_PROFILES = {"development", "private-beta", "organization"}
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_CONFIG_KEYS = {
    "schema_version",
    "profile",
    "host",
    "port",
    "data_dir",
    "content_dir",
    "log_level",
    "log_max_bytes",
    "log_backup_count",
    "open_browser",
    "allow_remote",
}
_ENV_KEYS = {
    "profile": "CDC_PROFILE",
    "host": "CDC_HOST",
    "port": "CDC_PORT",
    "data_dir": "CDC_DATA_DIR",
    "content_dir": "CDC_CONTENT_DIR",
    "log_level": "CDC_LOG_LEVEL",
    "log_max_bytes": "CDC_LOG_MAX_BYTES",
    "log_backup_count": "CDC_LOG_BACKUP_COUNT",
    "open_browser": "CDC_OPEN_BROWSER",
    "allow_remote": "CDC_ALLOW_REMOTE",
}
_HOSTNAME_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*$"
)
_SEMVER_PATTERN = re.compile(
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_CHECK_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_OPERATION_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_SECRET_KEY_PATTERN = re.compile(
    r"(?i)(?:authorization|cookie|credential|password|passwd|secret|session|token|api[_-]?key|private[_-]?key|customer|tenant|organization|user(?:name|_id)?|email|scenario|faction|unit|request[_-]?body|payload)"
)
_SECRET_VALUE_PATTERN = re.compile(
    r"(?i)\b(authorization|cookie|credential|password|passwd|secret|session|token|api[-_]?key|private[-_]?key)"
    r"\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+=*")
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_WINDOWS_PATH_PATTERN = re.compile(r"(?i)(?<![A-Za-z0-9])(?:[A-Z]:\\|\\\\)[^\r\n\t\"']+")
_POSIX_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9.])/(?:home|Users|var|tmp|opt|srv)/[^\r\n\t\"']+")


class ConfigurationError(ValueError):
    """Raised when beta runtime configuration or build metadata is invalid."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        if path.stat().st_size > _MAX_CONFIG_BYTES:
            raise ConfigurationError(f"{label} exceeds the 64 KiB limit")
        raw = path.read_text(encoding="utf-8-sig")
    except ConfigurationError:
        raise
    except OSError as exc:
        raise ConfigurationError(f"Cannot read {label}: {path.name}") from exc

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ConfigurationError(f"{label} contains duplicate field: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicates)
    except ConfigurationError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ConfigurationError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ConfigurationError(f"{label} must contain a JSON object")
    return value


def _strict_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ConfigurationError(f"{label} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ConfigurationError(f"{label} must be an integer") from exc
    if isinstance(value, float) and not value.is_integer():
        raise ConfigurationError(f"{label} must be an integer")
    if isinstance(value, str) and str(parsed) != value.strip():
        raise ConfigurationError(f"{label} must be an integer")
    if not minimum <= parsed <= maximum:
        raise ConfigurationError(f"{label} must be between {minimum} and {maximum}")
    return parsed


def _strict_bool(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ConfigurationError(f"{label} must be true or false")


def _safe_text(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value.strip()):
        raise ConfigurationError(f"{label} has an invalid value")
    return value.strip()


def _resolved_path(value: Any, label: str, base: Path) -> Path:
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise ConfigurationError(f"{label} must be a non-empty path")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        return candidate.resolve(strict=False)
    except OSError as exc:
        raise ConfigurationError(f"{label} cannot be resolved") from exc


def _default_data_dir(environment: Mapping[str, str]) -> Path:
    if os.name == "nt":
        base = environment.get("LOCALAPPDATA") or environment.get("APPDATA")
        if base:
            return Path(base).expanduser().resolve(strict=False) / "CDC Sim"
        return Path.home().resolve() / "AppData" / "Local" / "CDC Sim"
    xdg_data = environment.get("XDG_DATA_HOME")
    if xdg_data:
        return Path(xdg_data).expanduser().resolve(strict=False) / "cdc-sim"
    return Path.home().resolve() / ".local" / "share" / "cdc-sim"


def _is_loopback(host: str) -> bool:
    normalized = host.rstrip(".").lower()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _validate_host(value: Any, allow_remote: bool) -> str:
    if not isinstance(value, str):
        raise ConfigurationError("host must be a hostname or IP address")
    host = value.strip()
    if not host or "://" in host or any(char in host for char in "/\\?#@"):
        raise ConfigurationError("host must be a hostname or IP address")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not _HOSTNAME_PATTERN.fullmatch(host):
            raise ConfigurationError("host must be a valid hostname or IP address")
    if not allow_remote and not _is_loopback(host):
        raise ConfigurationError(
            "Remote binding is disabled; set allow_remote explicitly only for an authenticated deployment"
        )
    return host


@dataclass(frozen=True)
class BuildInfo:
    product: str
    version: str
    channel: str
    build_id: str
    source_revision: str
    built_at_utc: str | None
    scenario_api_version: int

    def public_dict(self) -> dict[str, Any]:
        return {
            "product": self.product,
            "version": self.version,
            "channel": self.channel,
            "build_id": self.build_id,
            "scenario_api_version": self.scenario_api_version,
        }

    def support_dict(self) -> dict[str, Any]:
        return {
            **self.public_dict(),
            "source_revision": self.source_revision,
            "built_at_utc": self.built_at_utc,
        }


def load_build_info(path: str | os.PathLike[str] | None = None) -> BuildInfo:
    """Load immutable metadata stamped into an installer or development build."""
    source = Path(path).expanduser().resolve() if path is not None else _BUILD_INFO_PATH
    document = _json_object(source, "build metadata")
    expected = {
        "schema_version",
        "product",
        "version",
        "channel",
        "build_id",
        "source_revision",
        "built_at_utc",
        "scenario_api_version",
    }
    unknown = set(document) - expected
    missing = expected - set(document)
    if unknown or missing:
        detail = []
        if missing:
            detail.append(f"missing {', '.join(sorted(missing))}")
        if unknown:
            detail.append(f"unknown {', '.join(sorted(unknown))}")
        raise ConfigurationError(f"Build metadata fields are invalid: {'; '.join(detail)}")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise ConfigurationError("build metadata schema_version must be integer 1")
    product = document["product"]
    if not isinstance(product, str) or not 1 <= len(product.strip()) <= 80:
        raise ConfigurationError("build metadata product must be 1 to 80 characters")
    version = _safe_text(document["version"], "build metadata version", _SEMVER_PATTERN)
    channel = _safe_text(document["channel"], "build metadata channel", _TOKEN_PATTERN)
    build_id = _safe_text(document["build_id"], "build metadata build_id", _TOKEN_PATTERN)
    source_revision = _safe_text(
        document["source_revision"], "build metadata source_revision", _TOKEN_PATTERN
    )
    built_at = document["built_at_utc"]
    if built_at is not None:
        if not isinstance(built_at, str) or not built_at.endswith("Z"):
            raise ConfigurationError("build metadata built_at_utc must be null or an ISO-8601 UTC time")
        try:
            datetime.fromisoformat(built_at[:-1] + "+00:00")
        except ValueError as exc:
            raise ConfigurationError(
                "build metadata built_at_utc must be null or an ISO-8601 UTC time"
            ) from exc
    scenario_api_version = _strict_int(
        document["scenario_api_version"], "build metadata scenario_api_version", 1, 999
    )
    return BuildInfo(
        product=product.strip(),
        version=version,
        channel=channel,
        build_id=build_id,
        source_revision=source_revision,
        built_at_utc=built_at,
        scenario_api_version=scenario_api_version,
    )


@dataclass(frozen=True)
class RuntimeConfig:
    profile: str
    host: str
    port: int
    data_dir: Path
    content_dir: Path
    log_level: str
    log_max_bytes: int
    log_backup_count: int
    open_browser: bool
    allow_remote: bool
    config_file: Path | None = None

    @property
    def session_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def support_dir(self) -> Path:
        return self.data_dir / "support"


def load_runtime_config(
    config_path: str | os.PathLike[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> RuntimeConfig:
    """Load defaults, optional JSON configuration, then approved environment overrides."""
    environment = dict(os.environ if environ is None else environ)
    explicit_config = config_path is not None or bool(environment.get("CDC_CONFIG_FILE"))
    default_data = _default_data_dir(environment)
    config_home = default_data
    if environment.get("CDC_DATA_DIR"):
        config_home = _resolved_path(environment["CDC_DATA_DIR"], "CDC_DATA_DIR", Path.cwd())
    requested_config = config_path or environment.get("CDC_CONFIG_FILE")
    if requested_config is None:
        candidate = config_home / "config.json"
        source = candidate if candidate.is_file() else None
    else:
        source = Path(requested_config).expanduser().resolve()
        if not source.is_file():
            raise ConfigurationError(f"Runtime configuration file does not exist: {source.name}")

    settings: dict[str, Any] = {
        "profile": "private-beta",
        "host": "127.0.0.1",
        "port": 5000,
        "data_dir": default_data,
        "content_dir": _MODULE_ROOT / "dlc",
        "log_level": "INFO",
        "log_max_bytes": 5 * 1024 * 1024,
        "log_backup_count": 5,
        "open_browser": True,
        "allow_remote": False,
    }

    if source is not None:
        document = _json_object(source, "runtime configuration")
        unknown = set(document) - _CONFIG_KEYS
        if unknown:
            raise ConfigurationError(
                f"Runtime configuration contains unknown fields: {', '.join(sorted(unknown))}"
            )
        if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
            raise ConfigurationError("runtime configuration schema_version must be integer 1")
        settings.update({key: value for key, value in document.items() if key != "schema_version"})
        for field in ("data_dir", "content_dir"):
            if field in document:
                settings[field] = _resolved_path(document[field], field, source.parent)
    elif explicit_config:
        raise ConfigurationError("Runtime configuration file is required but unavailable")

    for field, environment_key in _ENV_KEYS.items():
        if environment_key not in environment:
            continue
        value: Any = environment[environment_key]
        if field in {"data_dir", "content_dir"}:
            value = _resolved_path(value, environment_key, Path.cwd())
        settings[field] = value

    profile = settings["profile"]
    if not isinstance(profile, str) or profile.strip().lower() not in _PROFILES:
        raise ConfigurationError(f"profile must be one of: {', '.join(sorted(_PROFILES))}")
    profile = profile.strip().lower()
    allow_remote = _strict_bool(settings["allow_remote"], "allow_remote")
    host = _validate_host(settings["host"], allow_remote)
    port = _strict_int(settings["port"], "port", 1, 65535)
    log_level = str(settings["log_level"]).strip().upper()
    if log_level not in _LOG_LEVELS:
        raise ConfigurationError(f"log_level must be one of: {', '.join(sorted(_LOG_LEVELS))}")
    log_max_bytes = _strict_int(
        settings["log_max_bytes"], "log_max_bytes", 64 * 1024, 100 * 1024 * 1024
    )
    log_backup_count = _strict_int(settings["log_backup_count"], "log_backup_count", 1, 20)
    open_browser = _strict_bool(settings["open_browser"], "open_browser")
    data_dir = (
        settings["data_dir"]
        if isinstance(settings["data_dir"], Path)
        else _resolved_path(settings["data_dir"], "data_dir", source.parent if source else Path.cwd())
    )
    content_dir = (
        settings["content_dir"]
        if isinstance(settings["content_dir"], Path)
        else _resolved_path(
            settings["content_dir"], "content_dir", source.parent if source else Path.cwd()
        )
    )
    if data_dir == content_dir or data_dir in content_dir.parents or content_dir in data_dir.parents:
        raise ConfigurationError("data_dir and content_dir must be separate, non-overlapping directories")
    return RuntimeConfig(
        profile=profile,
        host=host,
        port=port,
        data_dir=data_dir,
        content_dir=content_dir,
        log_level=log_level,
        log_max_bytes=log_max_bytes,
        log_backup_count=log_backup_count,
        open_browser=open_browser,
        allow_remote=allow_remote,
        config_file=source,
    )


def prepare_runtime_directories(config: RuntimeConfig) -> RuntimeConfig:
    """Create and verify the writable product-data directories."""
    for directory in (config.data_dir, config.session_dir, config.log_dir, config.support_dir):
        try:
            if directory.exists() and not directory.is_dir():
                raise ConfigurationError(f"Runtime path is not a directory: {directory.name}")
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / f".write-test-{uuid.uuid4().hex}"
            try:
                with probe.open("xb") as handle:
                    handle.write(b"ok")
                    handle.flush()
                    os.fsync(handle.fileno())
            finally:
                probe.unlink(missing_ok=True)
        except ConfigurationError:
            raise
        except OSError as exc:
            raise ConfigurationError(f"Runtime directory is not writable: {directory.name}") from exc
    return config


def _redact_text(value: str) -> str:
    text = value[:4000]
    text = _BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    text = _SECRET_VALUE_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = _EMAIL_PATTERN.sub("[EMAIL]", text)
    text = _WINDOWS_PATH_PATTERN.sub("[PATH]", text)
    text = _POSIX_PATH_PATTERN.sub("[PATH]", text)
    return text


def _sanitize(value: Any, depth: int = 0) -> Any:
    if depth > 5:
        return "[TRUNCATED]"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else "[NON-FINITE]"
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 50:
                result["truncated"] = True
                break
            safe_key = str(key)[:80]
            result[safe_key] = (
                "[REDACTED]" if _SECRET_KEY_PATTERN.search(safe_key) else _sanitize(item, depth + 1)
            )
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        return [_sanitize(item, depth + 1) for item in items[:50]]
    return f"<{type(value).__name__}>"


class _JsonLogFormatter(logging.Formatter):
    def __init__(self, build_info: BuildInfo):
        super().__init__()
        self.build_info = build_info

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "event": _redact_text(str(getattr(record, "event", "runtime.message"))),
            "message": _redact_text(record.getMessage()),
            "product_version": self.build_info.version,
            "build_id": self.build_info.build_id,
        }
        for field in ("support_id", "exception_type", "frames", "details"):
            if hasattr(record, field):
                payload[field] = _sanitize(getattr(record, field))
        return json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class _PrivateRotatingFileHandler(RotatingFileHandler):
    def _open(self):
        stream = super()._open()
        try:
            os.chmod(self.baseFilename, 0o600)
        except OSError:
            pass
        return stream


def configure_runtime_logging(
    config: RuntimeConfig,
    build_info: BuildInfo,
    *,
    logger_name: str = "cdc_sim",
    console: bool = True,
) -> logging.Logger:
    """Create an idempotent rotating JSON logger with no network handler."""
    config.log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, config.log_level))
    logger.propagate = False
    for handler in list(logger.handlers):
        if getattr(handler, "_cdc_beta_runtime", False):
            logger.removeHandler(handler)
            handler.close()
    formatter = _JsonLogFormatter(build_info)
    file_handler = _PrivateRotatingFileHandler(
        config.log_dir / "cdc-sim.jsonl",
        maxBytes=config.log_max_bytes,
        backupCount=config.log_backup_count,
        encoding="utf-8",
        delay=True,
    )
    file_handler.setFormatter(formatter)
    file_handler._cdc_beta_runtime = True  # type: ignore[attr-defined]
    logger.addHandler(file_handler)
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler._cdc_beta_runtime = True  # type: ignore[attr-defined]
        logger.addHandler(console_handler)
    return logger


def record_runtime_exception(
    logger: logging.Logger,
    exception: BaseException,
    *,
    operation: str,
    context: Mapping[str, Any] | None = None,
) -> str:
    """Log a support-safe failure record and return its user-facing correlation ID.

    Exception messages and source lines are deliberately excluded because they
    commonly contain file paths, scenario content, request bodies, or secrets.
    """
    if not _OPERATION_PATTERN.fullmatch(operation):
        raise ValueError("operation must be a stable lowercase identifier")
    support_id = f"ERR-{uuid.uuid4().hex[:12].upper()}"
    frames: list[dict[str, Any]] = []
    traceback_cursor = exception.__traceback__
    while traceback_cursor is not None:
        frame = traceback_cursor.tb_frame
        frames.append(
            {
                "file": Path(frame.f_code.co_filename).name,
                "function": frame.f_code.co_name,
                "line": traceback_cursor.tb_lineno,
            }
        )
        traceback_cursor = traceback_cursor.tb_next
    logger.error(
        "Runtime operation failed",
        extra={
            "event": operation,
            "support_id": support_id,
            "exception_type": type(exception).__name__,
            "frames": frames[-8:],
            "details": {"context": _sanitize(context or {})},
        },
    )
    return support_id


def _validated_checks(checks: Mapping[str, bool] | None) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for key, value in (checks or {}).items():
        if not isinstance(key, str) or not _CHECK_PATTERN.fullmatch(key):
            raise ValueError("diagnostic check names must be stable lowercase identifiers")
        if type(value) is not bool:
            raise ValueError(f"diagnostic check {key} must be boolean")
        result[key] = value
    return dict(sorted(result.items()))


def public_health_payload(
    build_info: BuildInfo,
    *,
    ready: bool = True,
    checks: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Return health data safe for an unauthenticated local readiness endpoint."""
    if type(ready) is not bool:
        raise ValueError("ready must be boolean")
    safe_checks = _validated_checks(checks)
    healthy = ready and all(safe_checks.values())
    return {
        "status": "ok" if healthy else "attention",
        "build": build_info.public_dict(),
        "checks": safe_checks,
    }


def _directory_state(path: Path, *, writable: bool) -> dict[str, bool]:
    exists = path.is_dir()
    mode = os.W_OK if writable else os.R_OK
    return {"exists": exists, "accessible": exists and os.access(path, mode)}


def support_diagnostics(
    config: RuntimeConfig,
    build_info: BuildInfo,
    *,
    checks: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Return local support facts without paths, identities, content, or environment data."""
    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "build": build_info.support_dict(),
        "runtime": {
            "profile": config.profile,
            "python_version": platform.python_version(),
            "platform": platform.system() or "Unknown",
            "architecture": platform.machine() or "Unknown",
            "frozen_build": bool(getattr(sys, "frozen", False)),
            "loopback_only": not config.allow_remote,
            "port": config.port,
            "open_browser": config.open_browser,
            "log_level": config.log_level,
        },
        "storage": {
            "data": _directory_state(config.data_dir, writable=True),
            "sessions": _directory_state(config.session_dir, writable=True),
            "logs": _directory_state(config.log_dir, writable=True),
            "support": _directory_state(config.support_dir, writable=True),
            "content": _directory_state(config.content_dir, writable=False),
        },
        "checks": _validated_checks(checks),
    }


__all__ = [
    "BuildInfo",
    "ConfigurationError",
    "RuntimeConfig",
    "configure_runtime_logging",
    "load_build_info",
    "load_runtime_config",
    "prepare_runtime_directories",
    "public_health_payload",
    "record_runtime_exception",
    "support_diagnostics",
]
