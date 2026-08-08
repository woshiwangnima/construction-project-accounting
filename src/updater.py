"""GitHub Releases 自动更新。

流程：
  1. 检查 GitHub API latest release
  2. 语义化版本对比
  3. 下载 zip + manifest SHA256 校验
  4. 写 apply_update.bat → 拉起 → 退出（绕过 Windows 不能覆写自身 exe 的限制）

使用前在下方填写 GITHUB_OWNER / GITHUB_REPO。
"""
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import threading
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen, Request

from .logger import logger
from .versioning import APP_VERSION

# ── 创建 GitHub 仓库后填写 ──────────────────────────────
GITHUB_OWNER = "woshiwangnima"
GITHUB_REPO = "construction-project-accounting"
# ──────────────────────────────────────────────────────

# 当前运行平台标识，与 release zip 文件名后缀对应
# 扩展时在此添加新平台，如 "mac-arm64"、"linux64" 等
if sys.platform == "win32":
    import struct
    _bits = struct.calcsize("P") * 8
    CURRENT_PLATFORM = f"win{_bits}"       # "win64" 或 "win32"
else:
    CURRENT_PLATFORM = sys.platform         # 未来扩展

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


_PRE_RELEASE_RANK = {"alpha": 0, "a": 0, "beta": 1, "b": 1, "pre": 1, "preview": 1, "rc": 2}


def _parse_version(v: str) -> tuple:
    """解析版本号 → ((1,2,3), 'beta.1')；预发布后缀保留用于比较。"""
    v = v.lstrip("vV")
    match = re.match(r"(\d+(?:\.\d+)*)(?:[-.]*(.*))?$", v)
    if not match:
        return ((), "")
    numbers = tuple(int(p) for p in match.group(1).split("."))
    suffix = (match.group(2) or "").strip()
    return (numbers, suffix)


def _version_key(v: str) -> tuple:
    """版本排序键：预发布 < 正式版；alpha < beta < rc。"""
    numbers, suffix = _parse_version(v)
    padded = tuple(numbers) + (0,) * (6 - len(numbers))
    if not suffix:
        return (padded, (3, ""))
    token_match = re.match(r"[a-z]+", suffix.lower())
    token = token_match.group(0) if token_match else ""
    rank = _PRE_RELEASE_RANK.get(token, 2)
    return (padded, (rank, suffix.lower()))


def _compare_versions(local: str, remote: str) -> bool:
    """remote > local 时返回 True。"""
    return _version_key(remote) > _version_key(local)


def check_for_update() -> UpdateInfo | None:
    """查询 GitHub API latest release，返回 UpdateInfo 或 None。"""
    if not getattr(sys, "frozen", False):
        logger.debug("updater: 源码运行模式跳过自动更新")
        return None
    if not GITHUB_OWNER or not GITHUB_REPO:
        logger.debug("updater: GITHUB_OWNER / GITHUB_REPO 未配置，跳过检查")
        return None
    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    try:
        req = Request(url, headers={"Accept": "application/json", "User-Agent": "ConstructionAccounting"})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (URLError, OSError, TimeoutError, UnicodeError) as e:
        logger.warning("updater: 检查更新失败（网络）: %s", e)
        return None
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("updater: 检查更新失败（解析）: %s", e)
        return None

    if not isinstance(data, dict):
        logger.warning("updater: GitHub response root is not an object")
        return None

    tag = data.get("tag_name", "")
    if not isinstance(tag, str):
        logger.warning("updater: release tag is invalid")
        return None
    remote_version = tag.lstrip("vV")
    if not remote_version or not _parse_version(remote_version):
        logger.warning("updater: release version is invalid: %r", tag)
        return None
    if not _compare_versions(APP_VERSION, remote_version):
        logger.info("updater: 已是最新版 %s", APP_VERSION)
        return None

    body_value = data.get("body") or ""
    body = body_value.strip() if isinstance(body_value, str) else ""
    notes = [line.strip("- ").strip() for line in body.split("\n") if line.strip()]

    # 优先匹配当前平台的 zip（如 -win64.zip），兜底匹配无平台后缀的旧版 zip
    platform_suffix = f"-{CURRENT_PLATFORM}.zip"
    zip_url = ""
    fallback_url = ""
    assets = data.get("assets", []) or []
    if not isinstance(assets, list):
        logger.warning("updater: release assets is invalid")
        return None
    legacy_names = {
        "ConstructionAccounting.zip",
        f"ConstructionAccounting-{remote_version}.zip",
        f"ConstructionAccounting-v{remote_version}.zip",
    }
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name", "")
        if not isinstance(name, str):
            continue
        if not name.endswith(".zip") or not name.startswith("ConstructionAccounting"):
            continue
        url = asset.get("browser_download_url", "")
        if not isinstance(url, str) or not _is_https_url(url):
            continue
        if name.endswith(platform_suffix):
            zip_url = url
            break
        # Do not fall back to another platform's package. Only an explicitly
        # unqualified legacy asset is safe to use across platforms.
        if not fallback_url and name in legacy_names:
            fallback_url = url
    zip_url = zip_url or fallback_url

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

    if not isinstance(manifest, dict):
        logger.error("updater: invalid manifest root")
        return False

    expected = manifest.get("files", {})
    if not isinstance(expected, dict):
        logger.error("updater: manifest files 字段无效")
        return False

    try:
        root = download_dir.resolve()
    except OSError as e:
        logger.error("updater: update directory cannot be resolved: %s", e)
        return False
    normalized_expected: dict[str, str] = {}
    for rel_path, expected_hash in expected.items():
        if not isinstance(rel_path, str) or not isinstance(expected_hash, str):
            logger.error("updater: manifest 条目无效: %r", rel_path)
            return False
        if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
            logger.error("updater: manifest hash 无效: %s", rel_path)
            return False
        try:
            full_path = _safe_archive_target(root, rel_path)
        except (OSError, ValueError):
            logger.error("updater: manifest 路径越界: %s", rel_path)
            return False
        normalized_path = full_path.relative_to(root).as_posix()
        if normalized_path == "file_manifest.json" or normalized_path in normalized_expected:
            logger.error("updater: manifest 路径重复或指向 manifest: %s", rel_path)
            return False
        if not full_path.is_file():
            logger.error("updater: 文件缺失: %s", rel_path)
            return False
        try:
            with open(full_path, "rb") as f:
                actual = _sha256_stream(f)
        except OSError as e:
            logger.error("updater: 文件读取失败 %s: %s", rel_path, e)
            return False
        if actual != expected_hash.lower():
            logger.error("updater: 文件校验失败 %s", rel_path)
            return False
        normalized_expected[normalized_path] = expected_hash.lower()

    try:
        actual_files = {
            p.relative_to(root).as_posix()
            for p in root.rglob("*")
            if p.is_file() and p.relative_to(root).as_posix() != "file_manifest.json"
        }
    except OSError as e:
        logger.error("updater: 无法枚举更新文件: %s", e)
        return False
    if actual_files != set(normalized_expected):
        logger.error("updater: manifest 与实际文件集合不一致")
        return False
    logger.info("updater: manifest 校验通过 (%d 个文件)", len(expected))
    return True


_DOWNLOAD_TOTAL_TIMEOUT = 600  # 整个下载流程的总时限（秒）
_DOWNLOAD_RETRIES = 2          # 下载失败后的自动重试次数


def _download_to_file(info: UpdateInfo, zip_path: Path, progress_callback, deadline: float) -> None:
    """单次下载尝试；超过 deadline 抛 TimeoutError。"""
    req = Request(info.download_url, headers={"User-Agent": "ConstructionAccounting"})
    with urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length", "0") or 0)
        downloaded = 0
        with open(zip_path, "wb") as f:
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError("download exceeded total time budget")
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total:
                    progress_callback(downloaded, total)
        if total and downloaded != total:
            raise OSError(f"download truncated: {downloaded}/{total} bytes")


def download_update(info: UpdateInfo, progress_callback: Callable[[int, int], None] | None = None) -> Path | None:
    """下载 update zip 并解压到临时目录，返回目录路径。

    有总时限（_DOWNLOAD_TOTAL_TIMEOUT）与自动重试（_DOWNLOAD_RETRIES），
    慢速但不断的连接不会无限挂起。
    """
    import tempfile
    import time
    tmp = Path(tempfile.mkdtemp(prefix="cpa_update_"))
    zip_path = tmp / "update.zip"
    deadline = time.monotonic() + _DOWNLOAD_TOTAL_TIMEOUT

    last_error: Exception | None = None
    for attempt in range(_DOWNLOAD_RETRIES + 1):
        try:
            _download_to_file(info, zip_path, progress_callback, deadline)
            last_error = None
            break
        except (URLError, OSError, TimeoutError, ValueError, UnicodeError) as e:
            last_error = e
            logger.error("updater: 下载失败(第%d次): %s", attempt + 1, e)
            try:
                zip_path.unlink(missing_ok=True)
            except OSError:
                pass
            if attempt < _DOWNLOAD_RETRIES:
                time.sleep(2 * (2 ** attempt))
    if last_error is not None:
        shutil.rmtree(tmp, ignore_errors=True)
        return None

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            _extract_zip_safely(zf, tmp)
    except (zipfile.BadZipFile, OSError, RuntimeError, ValueError) as e:
        logger.error("updater: zip 损坏: %s", e)
        shutil.rmtree(tmp, ignore_errors=True)
        return None

    try:
        os.remove(zip_path)
    except OSError as e:
        logger.error("updater: 无法清理下载压缩包: %s", e)
        shutil.rmtree(tmp, ignore_errors=True)
        return None

    if not _verify_manifest(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
        return None

    return tmp


def _extract_zip_safely(zf: zipfile.ZipFile, destination: Path) -> None:
    """拒绝 Zip Slip 和符号链接，只解压到 destination 内。"""
    root = destination.resolve()
    for member in zf.infolist():
        if _zip_member_is_symlink(member):
            raise zipfile.BadZipFile(f"压缩包包含符号链接: {member.filename}")
        try:
            target = _safe_archive_target(root, member.filename)
            target.relative_to(root)
        except (OSError, ValueError) as exc:
            raise zipfile.BadZipFile(f"压缩包路径越界: {member.filename}") from exc
        if target.is_symlink():
            raise zipfile.BadZipFile(f"压缩包目标是符号链接: {member.filename}")
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member, "r") as source, open(target, "wb") as output:
            while True:
                chunk = source.read(65536)
                if not chunk:
                    break
                output.write(chunk)


def _is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme.lower() == "https" and bool(parsed.netloc)


def _safe_archive_target(root: Path, member_name: str) -> Path:
    """Resolve an archive-relative path without platform-specific escapes."""
    if not isinstance(member_name, str) or not member_name or "\x00" in member_name:
        raise ValueError("invalid archive path")
    normalized = member_name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise ValueError("absolute archive path")
    relative = PurePosixPath(normalized)
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("traversal archive path")
    if any(":" in part for part in relative.parts):
        raise ValueError("invalid archive path component")
    target = (root.joinpath(*relative.parts)).resolve()
    target.relative_to(root)
    return target


def _zip_member_is_symlink(member: zipfile.ZipInfo) -> bool:
    mode = (member.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def _write_apply_script(update_dir: Path) -> Path:
    """在 update_dir 中创建 apply_update.bat + exclude.txt，返回 bat 路径。

    脚本逻辑：等父进程退出 → xcopy 新文件（排除用户数据目录）→ 删除 update_dir → 重启。
    """
    app_dir = _app_dir()
    bat_path = update_dir / "apply_update.bat"
    exclude_path = update_dir / "exclude.txt"

    is_frozen = getattr(sys, "frozen", False)
    if not is_frozen:
        raise RuntimeError("源码运行模式不支持自动更新")
    exe_name = "ConstructionAccounting.exe"

    # xcopy /EXCLUDE 格式：每行一个子串，文件路径包含该子串则被跳过。
    # 保护用户数据目录不被发布包覆盖。
    exclude_patterns = [
        "\\projects\\",
        "\\backups\\",
        "\\migration_backups\\",
        "\\logs\\",
    ]
    exclude_path.write_text("\r\n".join(exclude_patterns), encoding="utf-8")

    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "setlocal",
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
        "REM 复制新文件，排除用户数据目录（config/projects/backups/logs）",
        "REM 复制失败不重启新 exe，保留原安装，并把错误写入 error.log",
        f'xcopy /s /y /EXCLUDE:"{exclude_path}" "{update_dir}\\*" "{app_dir}\\" >nul 2>nul',
        "if errorlevel 1 (",
        "    echo xcopy failed with errorlevel %ERRORLEVEL% > \"%TEMP%\\cpa_update_error.log\"",
        "    echo update_dir=%update_dir% >> \"%TEMP%\\cpa_update_error.log\"",
        "    echo app_dir=%app_dir% >> \"%TEMP%\\cpa_update_error.log\"",
        "    echo %date% %time% >> \"%TEMP%\\cpa_update_error.log\"",
        "    goto :failed",
        ")",
        "",
        "REM 确认关键文件已就位，未就位视为更新失败",
        f'if not exist "{app_dir}\\{exe_name}" (',
        "    echo exe missing after copy > \"%TEMP%\\cpa_update_error.log\"",
        "    goto :failed",
        ")",
        "",
        "REM 清理更新临时目录",
        f'rmdir /s /q "{update_dir}" 2>nul',
        "",
        "REM 重启",
        f'start "" "{app_dir}\\ConstructionAccounting.exe"',
        "",
        "REM 自删除",
        "del \"%~f0\"",
        "exit /b 0",
        "",
        ":failed",
        "REM 更新失败：保留临时目录供人工排查，不回滚（原文件未被覆盖前的场景），不启动新 exe",
        f'echo update failed, staging kept at "{update_dir}"',
        "exit /b 1",
    ]
    bat_path.write_text("\r\n".join(lines), encoding="utf-8")
    return bat_path


def apply_update(update_dir: Path) -> None:
    """准备更新：将新文件复制到 _app_dir 中的 update/ 子目录，然后拉起 apply_update.bat。

    调用方应在拉起脚本后立即退出当前进程。

    staging 目录必须与安装目录同卷：%TEMP% 可能在另一个盘上，直接
    rename 会抛 EXDEV，此时改用 shutil.copytree 复制；staging 清理失败
    时抛异常让 UI 提示用户，不再静默吞掉。
    """
    import subprocess
    app_dir = _app_dir()
    stage_dir = app_dir / ".update_staging"
    if stage_dir.exists():
        try:
            shutil.rmtree(stage_dir)
        except OSError as exc:
            logger.error("updater: 清理旧 staging 失败: %s", exc)
            raise OSError(f"无法清理旧的更新暂存目录 {stage_dir}: {exc}") from exc
    try:
        update_dir.rename(stage_dir)
    except OSError as exc:
        # 跨卷（%TEMP% 与安装盘不同）时 rename 失败（POSIX EXDEV / WinError 17）：
        # 改用复制把 staging 放到安装目录同卷下。
        is_cross_volume = (
            getattr(exc, "errno", None) == errno.EXDEV
            or getattr(exc, "winerror", None) == 17
        )
        if not is_cross_volume:
            raise
        logger.info("updater: staging 跨卷，改用复制: %s", exc)
        try:
            shutil.copytree(update_dir, stage_dir, dirs_exist_ok=True)
        except OSError as exc2:
            logger.error("updater: staging 复制失败: %s", exc2)
            raise OSError(f"无法将更新文件就位到 {stage_dir}: {exc2}") from exc2

    bat_path = _write_apply_script(stage_dir)
    subprocess.Popen(
        ["cmd.exe", "/d", "/c", str(bat_path)],
        shell=False,
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
        # 单例：只在首次创建时初始化状态；后续实例化不得重置进行中的检查。
        if not getattr(self, "_initialized", False):
            self._result: UpdateInfo | None = None
            self._done = threading.Event()
            self._initialized = True

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
