"""Print the single canonical application version for build scripts."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "src" / "versioning.py"
VERSION_RE = re.compile(
    r"(?m)^APP_VERSION\s*=\s*['\"](?P<version>[^'\"]+)['\"]\s*$"
)
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


def read_app_version(path: Path = VERSION_FILE) -> str:
    matches = VERSION_RE.findall(path.read_text(encoding="utf-8"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one APP_VERSION assignment in {path}")
    version = matches[0]
    if not SEMVER_RE.fullmatch(version):
        raise RuntimeError(f"invalid semantic version in {path}: {version!r}")
    return version


def main() -> int:
    try:
        print(read_app_version())
    except (OSError, UnicodeError, RuntimeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
