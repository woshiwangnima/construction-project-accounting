"""公共工具函数"""

import json
import os
import tempfile
import time


def atomic_write_json(file_path: str, data: dict, max_retries: int = 3):
    """原子写入 JSON 文件（先写临时文件再替换）。

    失败重试：os.replace 在 Windows 上偶发 [WinError 5]（目标/临时文件被
    杀毒/文件监视器/编辑器短暂占用）。先重试 3 次（50/100/200ms 退避），
    仍失败则回退到非原子直接写，保证配置一定能落盘。
    """
    dir_name = os.path.dirname(file_path)
    os.makedirs(dir_name, exist_ok=True)
    delays = [0.05, 0.1, 0.2]
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=dir_name, prefix=".tmp_", suffix=".json.tmp"
            )
        except OSError as e:
            last_err = e
            time.sleep(delays[min(attempt, len(delays) - 1)])
            continue
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            try:
                os.replace(tmp_path, file_path)
                return
            except OSError as e:
                last_err = e
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except OSError:
                    pass
                if attempt < max_retries - 1:
                    time.sleep(delays[min(attempt, len(delays) - 1)])
                    continue
                break
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            raise
    # 重试全部失败 → 兜底非原子写入
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
