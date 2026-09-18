"""命令行入口（不启动 GUI）。

用法：
    python cli.py project.list --json
    python cli.py schema --json

与 main.py（GUI 入口）完全分离：CLI 不创建 QApplication，因此不会与
桌面程序的单实例锁（src/single_instance.py）互相干扰。
"""

import sys

from src.cli import main

if __name__ == "__main__":
    sys.exit(main())
