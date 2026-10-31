"""Build-time policy checks for the Windows private-beta artifact."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
import argparse
import hashlib
import json
import re
import sys


MAX_RELEASE_FILES = 20_000
MAX_RELEASE_BYTES = 4 * 1024 * 1024 * 1024
SCENARIO_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$")
SEMVER = re.compile(
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
BUILD_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
GIT_REVISION = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
UI_SUFFIXES = {".css", ".html", ".ico", ".jpeg", ".jpg", ".js", ".json", ".markdown", ".md", ".png", ".svg", ".txt", ".webp", ".woff", ".woff2"}
SCENARIO_SUFFIXES = {".geojson", ".hgt", ".jpeg", ".jpg", ".json", ".md", ".png", ".tif", ".tiff", ".txt", ".webp"}
FORBIDDEN_RELEASE_SUFFIXES = {".env", ".key", ".pem", ".py", ".pyc", ".pyo", ".pdb"}
FORBIDDEN_PARTS = {".git", ".venv", "__pycache__"}
EXTERNAL_ASSET = re.compile(
    r"<(?:script|link)\b[^>]+(?:src|href)\s*=\s*[\"'](?:https?:)?//", re.IGNORECASE
)
UNAPPROVED_RUNTIME_SERVICES = {
    "portal.opentopography.org",
    "server.arcgisonline.com",
    "tile.openstreetmap.org",
}
PROHIBITED_PRODUCT_LICENSE_MARKERS = (
    "GNU GENERAL PUBLIC LICENSE",
    " GPLV2",
    " GPLV3",
    "GPL-2.0",
    "GPL-3.0",
    "GPL VERSION",
)
PRODUCT_TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".markdown", ".md", ".txt"}


class ReleaseValidationError(ValueError):
    """The configured source or assembled release violates release policy."""


def _json_object(path: Path, label: str) -> dict[str, Any]:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ReleaseValidationError(f"{label} contains duplicate field [{key}]")
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseValidationError(f"Cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseValidationError(f"{label} must contain a JSON object")
    return value


def load_release_config(path: str | Path) -> dict[str, Any]:
    config = _json_object(Path(path).resolve(), "release configuration")
    required = {
        "schema_version", "product_name", "bundle_name", "executable_name", "publisher",
        "architecture", "app_id", "bundled_scenarios", "required_visible_scenarios",
        "supported_windows",
    }
    if set(config) != required or config.get("schema_version") != 1:
        raise ReleaseValidationError("Release configuration fields or schema version are invalid")
    for field in ("product_name", "bundle_name", "executable_name", "publisher", "architecture", "app_id"):
        if not isinstance(config[field], str) or not config[field].strip():
            raise ReleaseValidationError(f"Release configuration [{field}] must be text")
    for field in ("bundle_name", "executable_name"):
        if Path(config[field]).name != config[field] or config[field] in {".", ".."}:
            raise ReleaseValidationError(f"Release configuration [{field}] must be a safe file name")
    if not config["executable_name"].casefold().endswith(".exe"):
        raise ReleaseValidationError("Release executable_name must end in .exe")
    if config["architecture"] != "x64":
        raise ReleaseValidationError("This workflow supports only the reviewed x64 architecture")
    if not re.fullmatch(r"\{[0-9A-Fa-f-]{36}\}", config["app_id"]):
        raise ReleaseValidationError("Release app_id must be a braced GUID")
    scenarios = config["bundled_scenarios"]
    if not isinstance(scenarios, list) or not scenarios:
        raise ReleaseValidationError("At least one bundled scenario must be explicitly allowlisted")
    if len(scenarios) != len({str(item).casefold() for item in scenarios}):
        raise ReleaseValidationError("Bundled scenario IDs must be unique")
    for scenario_id in scenarios:
        if not isinstance(scenario_id, str) or not SCENARIO_ID.fullmatch(scenario_id) or scenario_id in {".", ".."}:
            raise ReleaseValidationError(f"Invalid bundled scenario ID [{scenario_id}]")
    required_visible = config["required_visible_scenarios"]
    if type(required_visible) is not int or required_visible < 1:
        raise ReleaseValidationError("required_visible_scenarios must be a positive integer")
    if len([item for item in scenarios if not item.startswith("_")]) < required_visible:
        raise ReleaseValidationError("The release allowlist has too few visible scenarios")
    systems = config["supported_windows"]
    if not isinstance(systems, list) or not systems or not all(isinstance(item, str) and item for item in systems):
        raise ReleaseValidationError("supported_windows must list at least one supported system")
    return config


def load_build_metadata(path: str | Path, *, release_artifact: bool) -> dict[str, Any]:
    build = _json_object(Path(path).resolve(), "build metadata")
    expected = {
        "schema_version", "product", "version", "channel", "build_id",
        "source_revision", "built_at_utc", "scenario_api_version",
    }
    if set(build) != expected:
        raise ReleaseValidationError("Build metadata fields are invalid")
    if type(build["schema_version"]) is not int or build["schema_version"] != 1:
        raise ReleaseValidationError("Build metadata schema version is invalid")
    if not isinstance(build["product"], str) or not 1 <= len(build["product"].strip()) <= 80:
        raise ReleaseValidationError("Build metadata product is invalid")
    if not isinstance(build["version"], str) or not SEMVER.fullmatch(build["version"]):
        raise ReleaseValidationError("Build metadata version is invalid")
    for field in ("channel", "build_id", "source_revision"):
        if not isinstance(build[field], str) or not BUILD_TOKEN.fullmatch(build[field]):
            raise ReleaseValidationError(f"Build metadata {field} is invalid")
    if type(build["scenario_api_version"]) is not int or not 1 <= build["scenario_api_version"] <= 999:
        raise ReleaseValidationError("Build metadata scenario API version is invalid")
    built_at = build["built_at_utc"]
    if built_at is not None:
        if not isinstance(built_at, str) or not built_at.endswith("Z"):
            raise ReleaseValidationError("Build metadata build time is invalid")
        try:
            datetime.fromisoformat(built_at[:-1] + "+00:00")
        except ValueError as exc:
            raise ReleaseValidationError("Build metadata build time is invalid") from exc
    if release_artifact:
        if build["channel"] not in {"qa", "private-beta"}:
            raise ReleaseValidationError("Release build channel is invalid")
        if built_at is None or build["build_id"] == "development":
            raise ReleaseValidationError("Release contains unstamped build metadata")
        revision = build["source_revision"]
        if revision != "unknown" and not GIT_REVISION.fullmatch(revision):
            raise ReleaseValidationError("Release source revision is invalid")
        if build["channel"] == "private-beta":
            if not GIT_REVISION.fullmatch(revision):
                raise ReleaseValidationError("Private beta requires an identifiable source revision")
            if build["build_id"] != f"beta-{revision[:12]}":
                raise ReleaseValidationError("Private beta build ID does not match its source revision")
    return build


def _safe_files(root: Path, relative: str, suffixes: set[str]) -> list[Path]:
    source = (root / relative).resolve()
    if not source.is_dir() or source.is_symlink():
        raise ReleaseValidationError(f"Required resource directory is missing or linked: {relative}")
    files: list[Path] = []
    case_names: set[str] = set()
    for path in sorted(source.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink():
            raise ReleaseValidationError(f"Resource links are forbidden: {path.relative_to(root)}")
        if not path.is_file():
            continue
        resolved = path.resolve()
        try:
            resolved.relative_to(source)
        except ValueError as exc:
            raise ReleaseValidationError(f"Resource escapes its root: {path}") from exc
        name = path.relative_to(root).as_posix()
        folded = name.casefold()
        if folded in case_names:
            raise ReleaseValidationError(f"Resource paths collide by case: {name}")
        case_names.add(folded)
        if path.suffix.casefold() not in suffixes and path.name.casefold() not in {"license", "copying"}:
            raise ReleaseValidationError(f"Unsupported release resource: {name}")
        files.append(path)
    if not files:
        raise ReleaseValidationError(f"Resource directory is empty: {relative}")
    return files


def validate_eula(path: str | Path, *, final: bool) -> str:
    source = Path(path).resolve()
    try:
        text = source.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ReleaseValidationError(f"Cannot read product EULA: {source}") from exc
    if not 1_000 <= len(text) <= 128_000:
        raise ReleaseValidationError("Product EULA length is invalid")
    required_terms = (
        "END USER LICENSE AGREEMENT",
        "THIRD-PARTY",
        "CUSTOMER CONTENT",
        "LIMITATION OF LIABILITY",
    )
    missing = [term for term in required_terms if term not in text.upper()]
    if missing:
        raise ReleaseValidationError("Product EULA is missing required sections: " + ", ".join(missing))
    if final:
        unfinished = ("DRAFT", "LEGAL REVIEW REQUIRED", "[LICENSOR", "[GOVERNING", "[SUPPORT")
        if any(marker in text.upper() for marker in unfinished):
            raise ReleaseValidationError("A beta build requires a finalized, legally reviewed EULA")
    return text


def validate_source(root: str | Path, config_path: str | Path, *, beta: bool) -> dict[str, Any]:
    root = Path(root).resolve()
    config = load_release_config(config_path)
    # LICENSE remains an audit input recording the historical public grant. It is
    # deliberately absent from pyinstaller_data() and every commercial artifact.
    required = ["app.py", "engine.py", "gis.py", "server.py", "dlc_loader.py", "beta_runtime.py", "beta_backup.py", "build_info.json", "LICENSE", "EULA.txt", "THIRD-PARTY-NOTICES.txt"]
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise ReleaseValidationError(f"Required build inputs are missing: {', '.join(missing)}")
    validate_eula(root / "EULA.txt", final=beta)
    _safe_files(root, "templates", UI_SUFFIXES)
    _safe_files(root, "static", UI_SUFFIXES)

    # Validate every selected package through the same boundary used at runtime.
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from dlc_loader import load_dlc_package

    for scenario_id in config["bundled_scenarios"]:
        scenario = root / "dlc" / scenario_id
        _safe_files(root, f"dlc/{scenario_id}", SCENARIO_SUFFIXES)
        load_dlc_package(scenario_id, root / "dlc")

    external_assets: list[str] = []
    for template in sorted((root / "templates").glob("*.html")):
        if EXTERNAL_ASSET.search(template.read_text(encoding="utf-8-sig")):
            external_assets.append(template.name)
    if beta and external_assets:
        raise ReleaseValidationError(
            "Beta runtime assets must be local; external script/stylesheet URLs remain in: "
            + ", ".join(external_assets)
        )
    service_references: list[str] = []
    runtime_sources = [
        *sorted((root / "templates").rglob("*.html")),
        *sorted((root / "static" / "js").rglob("*.js")),
        *sorted((root / "static" / "css").rglob("*.css")),
    ]
    for resource in runtime_sources:
        content = resource.read_text(encoding="utf-8-sig").casefold()
        for service in sorted(UNAPPROVED_RUNTIME_SERVICES):
            if service in content:
                service_references.append(f"{resource.relative_to(root).as_posix()}: {service}")
    if service_references:
        raise ReleaseValidationError(
            "Commercial runtime references an unapproved external service: "
            + ", ".join(service_references)
        )

    prohibited_license_references: list[str] = []
    product_text_files = [root / "EULA.txt"]
    for relative in ("templates", "static"):
        product_text_files.extend(
            item for item in sorted((root / relative).rglob("*"))
            if item.is_file()
            and (
                item.suffix.casefold() in PRODUCT_TEXT_SUFFIXES
                or item.name.casefold() in {"license", "copying"}
            )
        )
    for resource in product_text_files:
        content = resource.read_text(encoding="utf-8-sig").upper()
        if any(marker in content for marker in PROHIBITED_PRODUCT_LICENSE_MARKERS):
            prohibited_license_references.append(resource.relative_to(root).as_posix())
    if prohibited_license_references:
        raise ReleaseValidationError(
            "Commercial product resources contain a prohibited copyleft license option or text: "
            + ", ".join(prohibited_license_references)
        )
    return {
        "status": "ok",
        "scenarios": config["bundled_scenarios"],
        "external_runtime_assets": external_assets,
        "unapproved_runtime_services": service_references,
        "prohibited_product_license_references": prohibited_license_references,
    }


def pyinstaller_data(root: str | Path, config_path: str | Path, build_info: str | Path) -> list[tuple[str, str]]:
    """Return individual data entries so unrelated local files never enter a build."""
    root = Path(root).resolve()
    config = load_release_config(config_path)
    entries: list[tuple[str, str]] = []
    for relative in ("templates", "static"):
        for file in _safe_files(root, relative, UI_SUFFIXES):
            destination = file.relative_to(root).parent.as_posix()
            entries.append((str(file), destination))
    for scenario_id in config["bundled_scenarios"]:
        relative = f"dlc/{scenario_id}"
        for file in _safe_files(root, relative, SCENARIO_SUFFIXES):
            destination = file.relative_to(root).parent.as_posix()
            entries.append((str(file), destination))
    entries.extend(
        [
            (str(Path(build_info).resolve()), "."),
            (str((root / "EULA.txt").resolve()), "."),
            (str((root / "THIRD-PARTY-NOTICES.txt").resolve()), "."),
        ]
    )
    return entries


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _release_files(bundle: Path) -> list[Path]:
    if not bundle.is_dir() or bundle.is_symlink():
        raise ReleaseValidationError("Release bundle is missing or linked")
    files: list[Path] = []
    names: set[str] = set()
    total = 0
    for path in sorted(bundle.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink():
            raise ReleaseValidationError(f"Release contains a link: {path.relative_to(bundle)}")
        if not path.is_file():
            continue
        name = path.relative_to(bundle).as_posix()
        pure = PurePosixPath(name)
        folded = name.casefold()
        if folded in names:
            raise ReleaseValidationError(f"Release paths collide by case: {name}")
        names.add(folded)
        parts = {part.casefold() for part in pure.parts}
        if parts.intersection(FORBIDDEN_PARTS):
            raise ReleaseValidationError(f"Release contains forbidden content: {name}")
        public_ca_bundle = folded == "_internal/certifi/cacert.pem"
        if pure.suffix.casefold() in FORBIDDEN_RELEASE_SUFFIXES and not public_ca_bundle:
            raise ReleaseValidationError(f"Release exposes source, debug, or secret material: {name}")
        lower_name = pure.name.casefold()
        if lower_name.startswith("save_") or lower_name.startswith("battle_log"):
            raise ReleaseValidationError(f"Release contains customer/runtime data: {name}")
        total += path.stat().st_size
        if len(files) >= MAX_RELEASE_FILES or total > MAX_RELEASE_BYTES:
            raise ReleaseValidationError("Release exceeds the file-count or size safety limit")
        files.append(path)
    return files


def validate_bundle(bundle_path: str | Path, config_path: str | Path) -> dict[str, Any]:
    bundle = Path(bundle_path).resolve()
    config = load_release_config(config_path)
    files = _release_files(bundle)
    allowed_scenarios = {item.casefold() for item in config["bundled_scenarios"]}
    for file in files:
        relative_parts = file.relative_to(bundle).parts
        folded_parts = tuple(part.casefold() for part in relative_parts)
        if len(folded_parts) >= 3 and folded_parts[:2] == ("_internal", "dlc"):
            if folded_parts[2] not in allowed_scenarios:
                raise ReleaseValidationError(
                    f"Release contains an unselected scenario: {relative_parts[2]}"
                )
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
            (internal / "dlc" / scenario_id / name)
            for name in ("scenario.json", "units.json", "weapons.json", "battalions.json", "rules.json")
        )
    missing = [str(path.relative_to(bundle)) for path in required if not path.is_file()]
    if missing:
        raise ReleaseValidationError(f"Release is incomplete: {', '.join(missing)}")
    if (internal / "LICENSE").exists():
        raise ReleaseValidationError("Release contains the legacy project GPL license as product terms")
    validate_eula(internal / "EULA.txt", final=False)
    product_roots = (internal / "templates", internal / "static")
    product_text_files = [internal / "EULA.txt"]
    for product_root in product_roots:
        product_text_files.extend(
            item for item in sorted(product_root.rglob("*"))
            if item.is_file()
            and (
                item.suffix.casefold() in PRODUCT_TEXT_SUFFIXES
                or item.name.casefold() in {"license", "copying"}
            )
        )
    prohibited = []
    for resource in product_text_files:
        content = resource.read_text(encoding="utf-8-sig").upper()
        if any(marker in content for marker in PROHIBITED_PRODUCT_LICENSE_MARKERS):
            prohibited.append(resource.relative_to(bundle).as_posix())
    if prohibited:
        raise ReleaseValidationError(
            "Release contains a prohibited copyleft license option or text: " + ", ".join(prohibited)
        )
    build = load_build_metadata(internal / "build_info.json", release_artifact=True)
    if build["product"] != config["product_name"]:
        raise ReleaseValidationError("Build metadata product does not match the release configuration")
    return {"status": "ok", "file_count": len(files), "bytes": sum(path.stat().st_size for path in files)}


def write_manifest(
    bundle_path: str | Path,
    config_path: str | Path,
    build_info_path: str | Path,
    output_path: str | Path,
) -> Path:
    bundle = Path(bundle_path).resolve()
    config = load_release_config(config_path)
    validate_bundle(bundle, config_path)
    build = load_build_metadata(build_info_path, release_artifact=True)
    bundled_build = load_build_metadata(bundle / "_internal" / "build_info.json", release_artifact=True)
    if build != bundled_build:
        raise ReleaseValidationError("Manifest build metadata does not match the packaged build")
    files = _release_files(bundle)
    manifest = {
        "schema_version": 1,
        "product": config["product_name"],
        "version": build["version"],
        "channel": build["channel"],
        "build_id": build["build_id"],
        "source_revision": build["source_revision"],
        "built_at_utc": build["built_at_utc"],
        "scenario_api_version": build["scenario_api_version"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "platform": "windows-x64",
        "bundle": config["bundle_name"],
        "files": {
            path.relative_to(bundle).as_posix(): {
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in files
        },
    }
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return output


def verify_manifest(bundle_path: str | Path, manifest_path: str | Path) -> dict[str, Any]:
    bundle = Path(bundle_path).resolve()
    manifest = _json_object(Path(manifest_path).resolve(), "release manifest")
    records = manifest.get("files")
    if not isinstance(records, dict):
        raise ReleaseValidationError("Release manifest file inventory is missing")
    actual = {path.relative_to(bundle).as_posix(): path for path in _release_files(bundle)}
    if set(actual) != set(records):
        raise ReleaseValidationError("Release manifest does not match the bundle inventory")
    for name, path in actual.items():
        record = records[name]
        if not isinstance(record, dict) or set(record) != {"sha256", "bytes"}:
            raise ReleaseValidationError(f"Release manifest record is invalid: {name}")
        if record["bytes"] != path.stat().st_size or record["sha256"] != sha256(path):
            raise ReleaseValidationError(f"Release file changed after assembly: {name}")
    return {"status": "ok", "file_count": len(actual)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CDC Sim Windows release policy")
    commands = parser.add_subparsers(dest="command", required=True)
    source = commands.add_parser("source")
    source.add_argument("--root", required=True)
    source.add_argument("--config", required=True)
    source.add_argument("--beta", action="store_true")
    bundle = commands.add_parser("bundle")
    bundle.add_argument("--path", required=True)
    bundle.add_argument("--config", required=True)
    manifest = commands.add_parser("manifest")
    manifest.add_argument("--path", required=True)
    manifest.add_argument("--config", required=True)
    manifest.add_argument("--build-info", required=True)
    manifest.add_argument("--output", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--path", required=True)
    verify.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "source":
            result = validate_source(args.root, args.config, beta=args.beta)
        elif args.command == "bundle":
            result = validate_bundle(args.path, args.config)
        elif args.command == "manifest":
            output = write_manifest(args.path, args.config, args.build_info, args.output)
            result = {"status": "ok", "manifest": str(output)}
        else:
            result = verify_manifest(args.path, args.manifest)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ReleaseValidationError, ValueError) as exc:
        print(f"Release validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

