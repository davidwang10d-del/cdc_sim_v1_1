"""Create, validate and build data-only scenario packs; no publishing or billing."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

from dlc_loader import load_dlc_directory
from scenario_package import file_digest, new_manifest, package_files, validate_manifest


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def scaffold_package(destination, package_id, name, publisher):
    destination = Path(destination)
    manifest = new_manifest(package_id, name, publisher)
    validate_manifest(manifest)
    if destination.exists():
        raise ValueError("Destination already exists; choose an empty new directory")
    template = Path(__file__).resolve().parent / "dlc" / "_template"
    # Validate and copy only the authored template, never runtime/customer files.
    load_dlc_directory(template, "_template")
    files = package_files(template)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cdc-pack-", dir=destination.parent) as staging:
        staged = Path(staging) / "package"
        staged.mkdir()
        for relative in files:
            target = staged / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(template / relative, target)
        _write_json(staged / "package.json", manifest)
        scenario = json.loads((staged / "scenario.json").read_text(encoding="utf-8"))
        scenario["scenario_name"] = name
        scenario["committee"]["committee_name"] = name
        _write_json(staged / "scenario.json", scenario)
        _write_json(staged / "objectives.json", {"schema_version": 1, "objectives": [{
            "id": "ceasefire", "title": "Negotiate a ceasefire", "description": "A political objective for all delegations.",
            "faction": "GLOBAL", "success_criteria": "The chair confirms every delegation has accepted the ceasefire.", "points": 10,
        }]})
        _write_json(staged / "events.json", {"schema_version": 1, "events": [{
            "id": "relief-offer", "title": "Relief agency offers assistance", "body": "Aid is available if delegations agree on safe access.",
            "trigger_note": "Chair may introduce this after the first diplomatic round.", "faction": "GLOBAL",
            "effect_type": "none", "value": 0, "duration_hours": 12, "public": True,
        }]})
        load_dlc_directory(staged, package_id)
        if destination.exists():
            raise ValueError("Destination already exists")
        staged.rename(destination)
    return destination


def build_package(source, output):
    source, output = Path(source), Path(output)
    if source.is_symlink():
        raise ValueError("Build source must not be a symlink")
    source = source.resolve()
    output = output.resolve()
    if output.exists():
        raise ValueError("Output already exists; never overwrite a released package")
    if output == source or source in output.parents:
        raise ValueError("Build output must be outside the scenario directory")
    package = load_dlc_directory(source)
    if package.manifest is None:
        raise ValueError("Build requires package.json; create a versioned scenario first")
    names = package_files(source)
    # Stage a stable snapshot, then validate those exact bytes before archiving.
    with tempfile.TemporaryDirectory(prefix="cdc-build-") as temporary:
        staged = Path(temporary) / "package"
        staged.mkdir()
        for name in names:
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)
        snapshot = load_dlc_directory(staged)
        manifest = deepcopy(snapshot.manifest)
        manifest["content_hashes"] = {name: file_digest(staged / name) for name in names if name != "package.json"}
        _write_json(staged / "package.json", manifest)
        load_dlc_directory(staged)
        archive = Path(temporary) / "package.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for name in sorted(names):
                info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                with bundle.open(info, "w", force_zip64=True) as target, (staged / name).open("rb") as origin:
                    shutil.copyfileobj(origin, target)
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with output.open("xb") as target, archive.open("rb") as origin:
                shutil.copyfileobj(origin, target)
                target.flush()
                os.fsync(target.fileno())
        except FileExistsError:
            raise ValueError("Output already exists; never overwrite a released package") from None
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("init", help="Create a new scenario using the editor template")
    create.add_argument("destination", type=Path)
    create.add_argument("--id", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--publisher", required=True)
    validate = commands.add_parser("validate", help="Validate a scenario without mounting it")
    validate.add_argument("source", type=Path)
    build = commands.add_parser("build", help="Build a validated ZIP with content hashes")
    build.add_argument("source", type=Path)
    build.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = scaffold_package(args.destination, args.id, args.name, args.publisher)
            print(f"Scenario created: {result}")
        elif args.command == "validate":
            package = load_dlc_directory(args.source)
            label = f"{package.manifest['id']} {package.manifest['version']}" if package.manifest else package.dlc_id
            print(f"Valid scenario: {label}")
        else:
            print(f"Package built: {build_package(args.source, args.output)}")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Scenario package rejected: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
