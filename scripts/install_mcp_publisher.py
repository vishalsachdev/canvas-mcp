"""Install a versioned publisher only after verifying its pinned archive digest."""

import argparse
import hashlib
import hmac
import os
import re
import tarfile
import tempfile
import urllib.request
from pathlib import Path

MAX_BYTES = 64 * 1024 * 1024


def install_publisher(version: str, sha256: str, destination: Path) -> None:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", version):
        raise ValueError("Publisher version must be an explicit release tag")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("Publisher checksum must be a SHA-256 digest")
    url = f"https://github.com/modelcontextprotocol/registry/releases/download/{version}/mcp-publisher_linux_amd64.tar.gz"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        archive_path = Path(directory) / "publisher.tar.gz"
        digest, size = hashlib.sha256(), 0
        with urllib.request.urlopen(url, timeout=30) as response, archive_path.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("Publisher archive exceeds size limit")
                digest.update(chunk)
                output.write(chunk)
        if not hmac.compare_digest(digest.hexdigest(), sha256):
            raise ValueError("Publisher archive checksum mismatch; nothing installed")
        executable = Path(directory) / "mcp-publisher"
        with tarfile.open(archive_path, "r|gz", encoding="utf-8") as archive:
            expanded = 0
            for count, member in enumerate(archive):
                expanded += member.size
                if count >= 1000 or expanded > MAX_BYTES:
                    raise ValueError("Publisher archive contents exceed size limit")
                if member.name != "mcp-publisher":
                    continue
                if not member.isfile():
                    raise ValueError("Publisher must be a regular file")
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("Publisher executable is missing")
                with source, executable.open("wb") as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
                break
            else:
                raise ValueError("Publisher executable is missing")
        executable.chmod(0o755)
        os.replace(executable, destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    install_publisher(args.version, args.sha256, args.destination)


if __name__ == "__main__":
    main()
