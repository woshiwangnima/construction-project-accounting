"""GitHub Releases 自动更新。

流程：
  1. 检查 GitHub API latest release
  2. 语义化版本对比
  3. 下载 zip + manifest SHA256 校验
  4. 写 apply_update.bat → 拉起 → 退出（绕过 Windows 不能覆写自身 exe 的限制）

使用前在下方填写 GITHUB_OWNER / GITHUB_REPO。
"""
import hashlib
import json
import os
import sys
import threading
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import urlopen, Request

from .logger import logger
from .versioning import APP_VERSION

# ── 创建 GitHub 仓库后填写 ──────────────────────────────
GITHUB_OWNER = "woshiwangnima"
GITHUB_REPO = "construction-project-accounting"
# ──────────────────────────────────────────────────────

GITHUB_API = "https://api.github.com"


@dataclass
class UpdateInfo:
    version: str
    download_url: str
    release_notes: list[str] = field(default_factory=list)


@dataclass
class UpdateResult:
    success: bool
    message: str = ""


def _app_dir() -> Path:
    """返回 exe（打包后）或项目根目录（源码）的父目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _parse_version(v: str) -> tuple[int, ...]:
    """'1.2.3' → (1, 2, 3)。忽略非数字后缀如 '1.0.0-beta'。"""
    v = v.lstrip("vV")
    parts = []
    for p in v.split("."):
        digits = ""
        for ch in p:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits:
            parts.append(int(digits))
        else:
            break
    return tuple(parts)


def _compare_versions(local: str, remote: str) -> bool:
    """remote > local 时返回 True。"""
    return _parse_version(remote) > _parse_version(local)


def check_for_update() -> UpdateInfo | None:
    """查询 GitHub API latest release，返回 UpdateInfo 或 None。"""
    if not GITHUB_OWNER or not GITHUB_REPO:
        logger.debug("updater: GITHUB_OWNER / GITHUB_REPO 未配置，跳过检查")
        return None
    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    try:
        req = Request(url, headers={"Accept": "application/json", "User-Agent": "ConstructionAccounting"})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except URLError as e:
        logger.warning("updater: 检查更新失败（网络）: %s", e)
        return None
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("updater: 检查更新失败（解析）: %s", e)
        return None

    tag = data.get("tag_name", "")
    remote_version = tag.lstrip("vV")
    if not _compare_versions(APP_VERSION, remote_version):
        logger.info("updater: 已是最新版 %s", APP_VERSION)
        return None

    body = (data.get("body") or "").strip()
    notes = [line.strip("- ").strip() for line in body.split("\n") if line.strip()]

    zip_url = ""
    for asset in data.get("assets", []):
        name: str = asset.get("name", "")
        if name.endswith(".zip") and name.startswith("ConstructionAccounting"):
            zip_url = asset.get("browser_download_url", "")
            break

    if not zip_url:
        logger.warning("updater: 未在 release assets 中找到 zip 文件")
        return None

    logger.info("updater: 发现新版本 %s", remote_version)
    return UpdateInfo(version=remote_version, download_url=zip_url, release_notes=notes)


def _sha256_stream(stream, chunk_size=65536) -> str:
    h = hashlib.sha256()
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        h.update(chunk)
    return h.hexdigest()


def _verify_manifest(download_dir: Path) -> bool:
    """校验下载目录中的 file_manifest.json 与实际文件是否匹配。"""
    manifest_path = download_dir / "file_manifest.json"
    if not manifest_path.is_file():
        logger.error("updater: manifest 不存在: %s", manifest_path)
        return False
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("updater: manifest 解析失败: %s", e)
        return False

    expected = manifest.get("files", {})
    for rel_path, expected_hash in expected.items():
        full_path = download_dir / rel_path
        if not full_path.is_file():
            logger.error("updater: 文件缺失: %s", rel_path)
            return False
        try:
            with open(full_path, "rb") as f:
                actual = _sha256_stream(f)
        except OSError as e:
            logger.error("updater: 文件读取失败 %s: %s", rel_path, e)
            return False
        if actual != expected_hash:
            logger.error("updater: 文件校验失败 %s", rel_path)
            return False
    logger.info("updater: manifest 校验通过 (%d 个文件)", len(expected))
    return True


def download_update(info: UpdateInfo, progress_callback: Callable[[int, int], None] | None = None) -> Path | None:
    """下载 update zip 并解压到临时目录，返回目录路径。"""
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="cpa_update_"))
    zip_path = tmp / "update.zip"

    try:
        req = Request(info.download_url, headers={"User-Agent": "ConstructionAccounting"})
        with urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", "0") or 0)
            downloaded = 0
            with open(zip_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total:
                        progress_callback(downloaded, total)
    except URLError as e:
        logger.error("updater: 下载失败: %s", e)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
        return None

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)
    except zipfile.BadZipFile as e:
        logger.error("updater: zip 损坏: %s", e)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
        return None

    os.remove(zip_path)

    if not _verify_manifest(tmp):
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
        return None

    return tmp


def _write_apply_script(update_dir: Path) -> Path:
    """在 update_dir 中创建 apply_update.bat，返回其路径。

    脚本逻辑：等父进程退出 → xcopy 新文件覆盖安装目录 → 删除 update_dir → 重启。
    """
    app_dir = _app_dir()
    bat_path = update_dir / "apply_update.bat"

    is_frozen = getattr(sys, "frozen", False)
    exe_name = "ConstructionAccounting.exe" if is_frozen else "python.exe"

    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "",
        "REM 等待主进程退出",
        ":wait",
        f'tasklist /FI "IMAGENAME eq {exe_name}" 2>NUL | find /I /N "{exe_name}" >NUL',
        "if \"%ERRORLEVEL%\"==\"0\" (",
        "    timeout /t 1 /nobreak >NUL",
        "    goto wait",
        ")",
        "",
        "echo 正在更新文件…",
        "",
        "REM 复制新文件（release zip 只含 exe + _internal，不会覆盖用户数据）",
        f'xcopy /s /y "{update_dir}\\*" "{app_dir}\\" >nul',
        "",
        "REM 清理更新临时目录",
        f'rmdir /s /q "{update_dir}" 2>nul',
        "",
        "REM 重启",
        f'start "" "{app_dir}\\ConstructionAccounting.exe"',
        "",
        "REM 自删除",
        "del \"%~f0\"",
    ]
    bat_path.write_text("\r\n".join(lines), encoding="utf-8")
    return bat_path


def apply_update(update_dir: Path) -> None:
    """准备更新：将新文件复制到 _app_dir 中的 update/ 子目录，然后拉起 apply_update.bat。

    调用方应在拉起脚本后立即退出当前进程。
    """
    app_dir = _app_dir()
    stage_dir = app_dir / ".update_staging"
    if stage_dir.exists():
        import shutil
        shutil.rmtree(stage_dir, ignore_errors=True)
    update_dir.rename(stage_dir)

    bat_path = _write_apply_script(stage_dir)
    import subprocess
    subprocess.Popen(
        [str(bat_path)],
        shell=True,
        creationflags=subprocess.DETACHED_PROCESS if hasattr(subprocess, "DETACHED_PROCESS") else 0,
    )
    logger.info("updater: apply_update.bat 已拉起，当前进程即将退出")


class UpdateChecker:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._result: UpdateInfo | None = None
        self._done = threading.Event()

    @property
    def result(self) -> UpdateInfo | None:
        return self._result

    @property
    def is_done(self) -> bool:
        return self._done.is_set()

    def run_async(self):
        """在后台线程中检查更新。"""
        def _run():
            try:
                self._result = check_for_update()
            except Exception as e:
                logger.warning("updater: 异步检查异常: %s", e)
            finally:
                self._done.set()
        threading.Thread(target=_run, daemon=True).start()
