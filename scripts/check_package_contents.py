"""Refuse publication of packages containing local operator files."""

import argparse
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

FORBIDDEN = {"BRIEF.md", ".env", ".mcp.json", ".superpowers", ".venv", "local_maps"}


def check_package(path: Path) -> None:
    if path.name.endswith(".whl"):
        with zipfile.ZipFile(path) as wheel:
            names = wheel.namelist()
    else:
        with tarfile.open(path, encoding="utf-8") as source:
            names = source.getnames()
    for name in names:
        parts = PurePosixPath(name).parts
        if FORBIDDEN.intersection(parts) or any(part.endswith(".local.md") for part in parts):
            raise ValueError(f"Package contains a local-only file: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    directory = parser.parse_args().directory
    packages = [*directory.glob("*.whl"), *directory.glob("*.tar.gz")]
    if not any(p.name.endswith(".whl") for p in packages) or not any(p.name.endswith(".tar.gz") for p in packages):
        raise ValueError("Expected a wheel and a source distribution")
    for package in packages:
        check_package(package)
    print(f"Package privacy check passed for {len(packages)} artifacts.")


if __name__ == "__main__":
    main()
