import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.updater import _extract_zip_safely, _verify_manifest


class UpdaterSafetyTests(unittest.TestCase):
    def test_safe_zip_extraction_stays_inside_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "update"
            destination.mkdir()
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("nested/app.exe", b"binary")
            archive.seek(0)

            with zipfile.ZipFile(archive) as zf:
                _extract_zip_safely(zf, destination)

            self.assertEqual((destination / "nested" / "app.exe").read_bytes(), b"binary")

    def test_zip_slip_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "update"
            destination.mkdir()
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../outside.txt", b"should not be written")
            archive.seek(0)

            with zipfile.ZipFile(archive) as zf:
                with self.assertRaises(zipfile.BadZipFile):
                    _extract_zip_safely(zf, destination)

            self.assertFalse((Path(tmp) / "outside.txt").exists())

    def test_manifest_requires_exact_file_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = root / "ConstructionAccounting.exe"
            payload.write_bytes(b"binary")
            digest = hashlib.sha256(payload.read_bytes()).hexdigest()
            (root / "file_manifest.json").write_text(
                json.dumps({"files": {payload.name: digest}}),
                encoding="utf-8",
            )

            self.assertTrue(_verify_manifest(root))

            (root / "unexpected.dll").write_bytes(b"extra")
            self.assertFalse(_verify_manifest(root))

    def test_manifest_rejects_invalid_root_and_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "file_manifest.json"

            manifest.write_text("[]", encoding="utf-8")
            self.assertFalse(_verify_manifest(root))

            manifest.write_text(
                json.dumps({"files": {"../outside.exe": "0" * 64}}),
                encoding="utf-8",
            )
            self.assertFalse(_verify_manifest(root))


if __name__ == "__main__":
    unittest.main()
