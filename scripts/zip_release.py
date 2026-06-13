"""Create release zip for PyInstaller build output."""
import os
import sys
import zipfile
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("Usage: python zip_release.py <build_dir> [version]")
        sys.exit(1)
    build_dir = Path(sys.argv[1])
    version = sys.argv[2] if len(sys.argv) > 2 else "1.0.1"
    if not build_dir.is_dir():
        print(f"Error: directory not found {build_dir}", file=sys.stderr)
        sys.exit(1)

    zip_name = f"ConstructionAccounting-{version}.zip"
    zip_path = build_dir.parent / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(build_dir):
            root_path = Path(root)
            for f in files:
                if f == "file_manifest.json" and root_path != build_dir:
                    continue
                fp = root_path / f
                rel = fp.relative_to(build_dir).as_posix()
                zf.write(fp, rel)
    print(f"Created: {zip_path}")


if __name__ == "__main__":
    main()
