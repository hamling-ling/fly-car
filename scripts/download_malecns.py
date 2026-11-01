#!/usr/bin/env python3
"""Download the MaleCNS v1.0 flat tables this repository reads.

The files land in data/malecns/ and are gitignored. A file whose size already
matches the bucket is left in place. A shorter file is resumed.

This is not the whole public release. The electron-microscopy volume,
skeletons, and the partner table are not used for the camera map. The four
tables below are the annotations, transmitters, connection weights, and
synapse coordinates.

Source: https://male-cns.janelia.org/download/
License: CC BY 4.0
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "malecns"
BASE = "https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome"

FILES = (
    "body-annotations-male-cns-v1.0-minconf-0.5.feather",
    "body-neurotransmitters-male-cns-v1.0.feather",
    "connectome-weights-male-cns-v1.0-minconf-0.5.feather",
    "syn-points-male-cns-v1.0-minconf-0.5.feather",
)


def plan(local: int | None, remote: int | None) -> str:
    """Return skip, resume, download, or larger."""
    if local is None:
        return "download"
    if remote is None:
        return "skip"
    if local == remote:
        return "skip"
    if local < remote:
        return "resume"
    return "larger"


def content_length(url: str) -> int | None:
    completed = subprocess.run(
        ["curl", "-fsI", "-L", url],
        check=True,
        capture_output=True,
        text=True,
    )
    length = None
    for line in completed.stdout.splitlines():
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
    return length


def fetch(name: str, *, force: bool) -> None:
    dest = DATA / name
    url = f"{BASE}/{name}"
    remote = content_length(url)
    local = dest.stat().st_size if dest.exists() else None
    action = "download" if force and local is not None else plan(local, remote)
    if action == "skip":
        print(f"skip {name} ({local} bytes)")
        return
    if force and dest.exists():
        dest.unlink()
        action = "download"
    if action == "larger":
        raise SystemExit(f"{dest} is {local} bytes, but the bucket lists {remote}.")
    DATA.mkdir(parents=True, exist_ok=True)
    print(f"{action} {name}", flush=True)
    subprocess.run(
        ["curl", "-L", "--fail", "--retry", "3", "-C", "-", "-o", str(dest), url],
        check=True,
    )
    written = dest.stat().st_size
    if remote is not None and written != remote:
        raise SystemExit(f"{dest} is {written} bytes after curl, bucket lists {remote}.")
    print(f"wrote {dest.relative_to(ROOT)} ({written} bytes)")


def main() -> None:
    force = "--force" in sys.argv[1:]
    for name in FILES:
        fetch(name, force=force)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
