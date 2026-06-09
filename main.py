import tkinter as tk
import traceback

from src.logger import logger
from src.versioning import migrate_all_known_files
from src.gui import MainInterface


def main():
    try:
        migrate_all_known_files()
        root = tk.Tk()
        MainInterface(root)
        root.mainloop()
    except Exception:
        logger.critical("程序启动失败:\n%s", traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
