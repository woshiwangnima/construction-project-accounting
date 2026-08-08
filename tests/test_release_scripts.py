import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_manifest import main as generate_manifest_main  # noqa: E402
from zip_release import create_release_zip, validate_release_dir  # noqa: E402


class ReleaseScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="cpa_release_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def _make_bundle(self, version="1.2.3", platform="win64") -> Path:
        bundle = self.temp_dir / "ConstructionAccounting"
        (bundle / "config").mkdir(parents=True)
        (bundle / "_internal" / "assets" / "audio").mkdir(parents=True)
        (bundle / "ConstructionAccounting.exe").write_bytes(b"fake executable")
        (bundle / "config" / "app_config.json").write_text("{}\n", encoding="utf-8")
        (bundle / "_internal" / "assets" / "audio" / "0.wav").write_bytes(b"fake audio")
        self.assertEqual(
            generate_manifest_main(
                [str(bundle), "--version", version, "--platform", platform]
            ),
            0,
        )
        return bundle

    def test_manifest_and_zip_cover_every_release_file(self):
        bundle = self._make_bundle()

        manifest = validate_release_dir(bundle, "1.2.3", "win64")
        zip_path = create_release_zip(bundle, "1.2.3", "win64")

        self.assertEqual(manifest["version"], "1.2.3")
        with zipfile.ZipFile(zip_path) as archive:
            names = set(archive.namelist())
            self.assertEqual(names, set(manifest["files"]) | {"file_manifest.json"})
            zipped_manifest = json.loads(archive.read("file_manifest.json"))
            self.assertEqual(zipped_manifest["files"], manifest["files"])

    def test_release_validation_rejects_stale_manifest(self):
        bundle = self._make_bundle()
        (bundle / "config" / "app_config.json").write_text('{"changed": true}\n', encoding="utf-8")

        with self.assertRaises(ValueError):
            validate_release_dir(bundle, "1.2.3", "win64")

    def test_release_validation_rejects_path_injection_platform(self):
        bundle = self._make_bundle()

        with self.assertRaises(ValueError):
            create_release_zip(bundle, "1.2.3", "..\\outside")

    def test_start_and_build_batches_have_fallbacks_and_error_propagation(self):
        start_text = (ROOT / "start.bat").read_text(encoding="utf-8")
        build_text = (ROOT / "build.bat").read_text(encoding="utf-8")
        zip_batch_text = (ROOT / "scripts" / "ziprelease.bat").read_text(encoding="utf-8")

        self.assertIn(".venv\\Scripts\\pythonw.exe", start_text)
        self.assertIn(".venv\\Scripts\\python.exe", start_text)
        self.assertIn("where python.exe", start_text)
        self.assertIn("where py.exe", start_text)
        self.assertIn("main.py", start_text)
        self.assertIn("pip check", build_text)
        self.assertIn("call \"%ROOT%scripts\\ziprelease.bat\"", build_text)
        self.assertIn('--add-data "%ROOT%config;config"', build_text)
        self.assertIn('--add-data "%ROOT%assets;assets"', build_text)
        self.assertIn('set "PYINSTALLER_EXIT=%ERRORLEVEL%"', build_text)
        self.assertIn("if errorlevel 1", build_text)
        self.assertNotIn('rmdir /s /q "%ROOT%dist"', build_text)
        self.assertNotIn("del /q *.spec", build_text)
        self.assertIn("endlocal & exit /b %EXIT_CODE%", zip_batch_text)


if __name__ == "__main__":
    unittest.main()
