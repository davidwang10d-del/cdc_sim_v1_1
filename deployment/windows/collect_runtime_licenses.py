"""Collect exact license notices for the Python distributions used at runtime."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path, PurePosixPath
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
import argparse
import shutil


NOTICE_PREFIXES = ("license", "copying", "notice", "authors")
MAX_NOTICE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024


class NoticeCollectionError(RuntimeError):
    pass


def runtime_roots(requirements_path: Path) -> list[str]:
    roots: list[str] = []
    for raw_line in requirements_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        roots.append(canonicalize_name(requirement.name))
    if not roots:
        raise NoticeCollectionError("Runtime requirements list is empty")
    return roots


def dependency_closure(roots: list[str]) -> list[metadata.Distribution]:
    installed = {}
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            installed[canonicalize_name(name)] = distribution

    selected = {}
    pending = list(roots)
    while pending:
        name = pending.pop()
        if name in selected:
            continue
        distribution = installed.get(name)
        if distribution is None:
            raise NoticeCollectionError(f"Runtime distribution is not installed: {name}")
        selected[name] = distribution
        for raw_requirement in distribution.requires or ():
            requirement = Requirement(raw_requirement)
            if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
                continue
            pending.append(canonicalize_name(requirement.name))
    return [selected[name] for name in sorted(selected)]


def notice_files(distribution: metadata.Distribution) -> list[tuple[PurePosixPath, Path]]:
    result = []
    for entry in distribution.files or ():
        relative = PurePosixPath(str(entry).replace("\\", "/"))
        if any(part in {"", ".", ".."} for part in relative.parts):
            continue
        if not relative.name.casefold().startswith(NOTICE_PREFIXES):
            continue
        source = Path(distribution.locate_file(entry)).resolve()
        if not source.is_file() or source.is_symlink():
            continue
        size = source.stat().st_size
        if size > MAX_NOTICE_BYTES:
            raise NoticeCollectionError(f"License notice is unexpectedly large: {source}")
        result.append((relative, source))
    return sorted(result, key=lambda item: item[0].as_posix().casefold())


def collect(requirements_path: Path, output_path: Path) -> Path:
    output = output_path.resolve()
    if output.exists():
        raise NoticeCollectionError(f"Notice output already exists: {output}")
    output.mkdir(parents=True)

    index_lines = [
        "CDC Sim runtime third-party license index",
        "",
        "These notices correspond to the exact Python environment used for this build.",
        "Browser-library notices are stored under _internal/static/vendor.",
        "",
    ]
    total_bytes = 0
    distributions = dependency_closure(runtime_roots(requirements_path))
    for distribution in distributions:
        project_name = distribution.metadata.get("Name") or "unknown"
        version = distribution.version
        directory_name = f"{canonicalize_name(project_name)}-{version}"
        records = notice_files(distribution)
        if not records:
            raise NoticeCollectionError(
                f"Installed runtime distribution has no discoverable license notice: {project_name} {version}"
            )
        expression = distribution.metadata.get("License-Expression")
        declared = expression or distribution.metadata.get("License") or "See copied notice files"
        declared = " ".join(str(declared).split())
        index_lines.append(f"{project_name} {version}")
        index_lines.append(f"  Declared license: {declared[:500]}")
        for relative, source in records:
            destination = output / directory_name / Path(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            total_bytes += destination.stat().st_size
            if total_bytes > MAX_TOTAL_BYTES:
                raise NoticeCollectionError("Runtime license notices exceed the size limit")
            index_lines.append(f"  Notice: {directory_name}/{relative.as_posix()}")
        index_lines.append("")

    index = output / "INDEX.txt"
    index.write_text("\n".join(index_lines).rstrip() + "\n", encoding="utf-8", newline="\n")
    return index


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    index = collect(Path(args.requirements).resolve(), Path(args.output).resolve())
    print(index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
