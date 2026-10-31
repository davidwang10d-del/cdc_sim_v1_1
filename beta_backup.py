"""Create and restore bounded CDC Sim committee backups.

Backups contain customer session data only. They never contain engine source,
scenario-pack source, configuration secrets, or executable files.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

BACKUP_SCHEMA_VERSION = 1
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
SAVE_NAMES = ("save_slot_1.json", "save_slot_2.json", "save_slot_3.json")
LOG_NAME = "battle_log.txt"
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$")


class BackupError(ValueError):
    """A backup is missing, incompatible, unsafe, or corrupt."""


@dataclass(frozen=True)
class BackupArtifact:
    filename: str
    data: bytes


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_id(value: object) -> str:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value) or value in {".", ".."}:
        raise BackupError("Backup scenario ID is invalid")
    return value


def _json_object(data: bytes, label: str) -> dict:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise BackupError(f"{label} contains duplicate field [{key}]")
            result[key] = value
        return result

    try:
        value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_pairs)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise BackupError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise BackupError(f"{label} must contain a JSON object")
    return value


def _read_session_file(root: Path, name: str) -> bytes | None:
    path = root / name
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.resolve().parent != root:
        raise BackupError(f"Session file [{name}] is not a regular local file")
    size = path.stat().st_size
    if size > MAX_MEMBER_BYTES:
        raise BackupError(f"Session file [{name}] exceeds the backup limit")
    return path.read_bytes()


def _validate_save(data: bytes, name: str, expected_dlc_id: str) -> dict:
    save = _json_object(data, name)
    version = save.get("format_version", 1)
    if isinstance(version, bool) or version not in (1, 2, 3, 4):
        raise BackupError(f"{name} uses unsupported save format [{version}]")
    saved_dlc = save.get("dlc_id")
    if saved_dlc is not None and saved_dlc != expected_dlc_id:
        raise BackupError(f"{name} belongs to scenario [{saved_dlc}]")
    return save


def create_backup(
    storage_dir: str | Path,
    dlc_id: str,
    scenario_name: str,
    product_version: str,
    *,
    created_at: datetime | None = None,
) -> BackupArtifact:
    """Return an in-memory ZIP containing validated checkpoints and a manifest."""
    dlc_id = _safe_id(dlc_id)
    root = Path(storage_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    created = (created_at or _utc_now()).astimezone(timezone.utc)
    payloads: dict[str, bytes] = {}
    for name in SAVE_NAMES:
        data = _read_session_file(root, name)
        if data is not None:
            _validate_save(data, name, dlc_id)
            payloads[name] = data
    if not payloads:
        raise BackupError("Save at least one manual checkpoint before downloading a backup")

    if sum(map(len, payloads.values())) > MAX_TOTAL_BYTES:
        raise BackupError("Expanded checkpoint data exceeds the backup limit")
    omitted: list[str] = []
    try:
        log = _read_session_file(root, LOG_NAME)
    except BackupError:
        log = None
        omitted.append(LOG_NAME)
    if log is not None:
        if sum(map(len, payloads.values())) + len(log) <= MAX_TOTAL_BYTES:
            payloads[LOG_NAME] = log
        else:
            omitted.append(LOG_NAME)

    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
    manifest = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "created_at_utc": created.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "product_version": str(product_version),
        "dlc_id": dlc_id,
        "scenario_name": str(scenario_name),
        "files": hashes,
        "restorable_files": [name for name in SAVE_NAMES if name in payloads],
        "omitted_files": omitted,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        entries = {"backup.json": json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")}
        entries.update(payloads)
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, entries[name])
    data = buffer.getvalue()
    if len(data) > MAX_ARCHIVE_BYTES:
        raise BackupError("Backup exceeds the archive limit")
    stamp = created.strftime("%Y%m%d-%H%M%SZ")
    return BackupArtifact(f"cdc-sim-{dlc_id}-{stamp}.zip", data)


def inspect_backup(archive_data: bytes, expected_dlc_id: str) -> tuple[dict, dict[str, bytes]]:
    """Validate an untrusted backup entirely before returning restorable files."""
    expected_dlc_id = _safe_id(expected_dlc_id)
    if not isinstance(archive_data, bytes) or not archive_data or len(archive_data) > MAX_ARCHIVE_BYTES:
        raise BackupError("Backup file is empty or exceeds 64 MiB")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            allowed = {"backup.json", LOG_NAME, *SAVE_NAMES}
            if len(names) != len(set(name.casefold() for name in names)):
                raise BackupError("Backup contains duplicate or case-colliding names")
            if "backup.json" not in names or not set(names).issubset(allowed):
                raise BackupError("Backup contains unsupported files")
            if any(info.is_dir() or info.flag_bits & 0x1 for info in infos):
                raise BackupError("Backup directories and encrypted entries are not supported")
            total = 0
            for info in infos:
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise BackupError("Backup links are not supported")
                if info.file_size > MAX_MEMBER_BYTES:
                    raise BackupError(f"Backup member [{info.filename}] exceeds the limit")
                total += info.file_size
                if total > MAX_TOTAL_BYTES:
                    raise BackupError("Expanded backup exceeds 64 MiB")
            payloads = {info.filename: archive.read(info) for info in infos}
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise BackupError("Backup is not a readable ZIP archive") from exc

    manifest = _json_object(payloads.pop("backup.json"), "backup.json")
    required = {
        "schema_version", "created_at_utc", "product_version", "dlc_id",
        "scenario_name", "files", "restorable_files", "omitted_files",
    }
    if set(manifest) != required or manifest["schema_version"] != BACKUP_SCHEMA_VERSION:
        raise BackupError("Backup manifest format is unsupported")

    manifest_dlc_id = _safe_id(manifest["dlc_id"])
    if manifest_dlc_id != expected_dlc_id:
        raise BackupError("Backup belongs to a different scenario")
    for field, maximum in (("product_version", 80), ("scenario_name", 500)):
        value = manifest[field]
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise BackupError(f"Backup manifest {field} is invalid")
    created_at = manifest["created_at_utc"]
    if not isinstance(created_at, str) or not created_at.endswith("Z"):
        raise BackupError("Backup creation time is invalid")
    try:
        datetime.fromisoformat(created_at[:-1] + "+00:00")
    except ValueError as exc:
        raise BackupError("Backup creation time is invalid") from exc

    files = manifest["files"]
    if not isinstance(files, dict) or set(files) != set(payloads):
        raise BackupError("Backup file inventory does not match its contents")

    restorable = manifest["restorable_files"]
    if (
        not isinstance(restorable, list)
        or not restorable
        or not all(isinstance(name, str) and name in SAVE_NAMES for name in restorable)
        or len(restorable) != len(set(restorable))
        or set(restorable) != set(payloads).intersection(SAVE_NAMES)
    ):
        raise BackupError("Backup restorable-file inventory is invalid")

    omitted = manifest["omitted_files"]
    if (
        not isinstance(omitted, list)
        or not all(isinstance(name, str) and name == LOG_NAME for name in omitted)
        or len(omitted) != len(set(omitted))
    ):
        raise BackupError("Backup omitted-file inventory is invalid")
    for name, data in payloads.items():
        digest = files.get(name)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise BackupError(f"Backup hash for [{name}] is invalid")
        if hashlib.sha256(data).hexdigest() != digest:
            raise BackupError(f"Backup content changed [{name}]")
        if name in SAVE_NAMES:
            _validate_save(data, name, expected_dlc_id)
    return manifest, {name: payloads[name] for name in SAVE_NAMES if name in payloads}



def migrate_legacy_checkpoints(
    legacy_dir: str | Path, storage_dir: str | Path, expected_dlc_id: str
) -> list[str]:
    """Copy compatible project-root checkpoints once, leaving originals untouched."""
    expected_dlc_id = _safe_id(expected_dlc_id)
    source = Path(legacy_dir).resolve()
    target = Path(storage_dir).resolve()
    if source == target or not source.is_dir():
        return []
    target.mkdir(parents=True, exist_ok=True)
    migrated: list[str] = []
    for name in SAVE_NAMES:
        destination = target / name
        if destination.exists():
            continue
        try:
            data = _read_session_file(source, name)
            if data is None:
                continue
            _validate_save(data, name, expected_dlc_id)
        except BackupError:
            continue
        handle = tempfile.NamedTemporaryFile(
            prefix=f".{name}.migration-", suffix=".tmp", dir=target, delete=False
        )
        temporary = Path(handle.name)
        try:
            with handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if not destination.exists():
                os.replace(temporary, destination)
                migrated.append(name)
        finally:
            temporary.unlink(missing_ok=True)
    return migrated


def restore_backup(storage_dir: str | Path, archive_data: bytes, expected_dlc_id: str) -> list[str]:
    """Replace checkpoints as one transaction after the complete archive validates."""
    _, saves = inspect_backup(archive_data, expected_dlc_id)
    root = Path(storage_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    new_paths: dict[str, Path] = {}
    old_paths: dict[str, Path] = {}
    applied: list[str] = []
    try:
        for name, data in saves.items():
            handle = tempfile.NamedTemporaryFile(
                prefix=f".{name}.restore-", suffix=".tmp", dir=root, delete=False
            )
            with handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            new_paths[name] = Path(handle.name)
            destination = root / name
            if destination.exists():
                old = tempfile.NamedTemporaryFile(
                    prefix=f".{name}.previous-", suffix=".tmp", dir=root, delete=False
                )
                old.close()
                old_path = Path(old.name)
                shutil.copyfile(destination, old_path)
                with old_path.open("r+b") as previous:
                    previous.flush()
                    os.fsync(previous.fileno())
                old_paths[name] = old_path
        try:
            for name in sorted(new_paths):
                os.replace(new_paths[name], root / name)
                applied.append(name)
        except OSError as exc:
            rollback_failed = False
            for name in reversed(applied):
                try:
                    if name in old_paths:
                        os.replace(old_paths[name], root / name)
                    else:
                        (root / name).unlink(missing_ok=True)
                except OSError:
                    rollback_failed = True
            detail = " and rollback was incomplete" if rollback_failed else "; existing checkpoints were retained"
            raise BackupError(f"Backup restore could not be completed{detail}") from exc
        return sorted(saves)
    finally:
        for path in (*new_paths.values(), *old_paths.values()):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

