"""CLI 层不得依赖 Qt / GUI。

这是"其他程序能调用 CLI"的核心保障：只要 CLI 进程里出现 PySide6，
无显示器环境（CI、服务器、子进程调用）就可能失败，且启动会明显变慢。

两条独立防线：
1. 静态：扫描 src/cli/** 源码，禁止出现 GUI 相关 import。
2. 运行时：在子进程中真正跑一条命令，断言 PySide6 未进入 sys.modules。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_DIR = REPO_ROOT / "src" / "cli"

FORBIDDEN_IMPORTS = (
    "PySide6",
    "qfluentwidgets",
    "qtawesome",
    "src.gui",
    "..gui",
    "...gui",
)


class TestCliDoesNotImportQt(unittest.TestCase):
    def test_source_has_no_gui_imports(self):
        offenders = []
        for path in sorted(CLI_DIR.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped.startswith(("import ", "from ")):
                    continue
                if any(token in stripped for token in FORBIDDEN_IMPORTS):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {stripped}")
        self.assertEqual(offenders, [], "CLI 层出现 GUI 依赖:\n" + "\n".join(offenders))

    def test_running_command_loads_no_qt_module(self):
        """在干净子进程里跑 calc，断言 Qt 完全没被加载。

        用子进程而非 import 当前进程，避免测试套件自身（Qt 冒烟测试）
        已经把 PySide6 装进 sys.modules 导致假阳性。
        """
        script = (
            "import sys, json;"
            f"sys.path.insert(0, {str(REPO_ROOT)!r});"
            "from src.cli import main;"
            "code = main(['calc', '1+1', '--json']);"
            "mods = sorted({m.split('.')[0] for m in sys.modules"
            " if m.split('.')[0] in ('PySide6', 'qfluentwidgets', 'qtawesome')});"
            "print(json.dumps({'code': code, 'qt': mods}));"
        )
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        # 隔离数据目录，避免读到用户真实项目
        with tempfile.TemporaryDirectory() as tmp:
            env["CPA_PROJECTS_DIR"] = tmp
            env["CPA_BACKUPS_DIR"] = tmp
            proc = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
                cwd=str(REPO_ROOT),
                timeout=120,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["qt"], [], f"CLI 进程加载了 Qt: {payload['qt']}")
        self.assertEqual(payload["code"], 0)


if __name__ == "__main__":
    unittest.main()
