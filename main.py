import tkinter as tk
from tkinter import messagebox
import traceback

from src.logger import logger, setup_logger
from src.paths import migrate_legacy_data
from src.single_instance import SingleInstanceLock
from src.versioning import migrate_all_known_files
from src.gui import MainInterface


def main():
    setup_logger()
    instance_lock = SingleInstanceLock()
    if not instance_lock.acquire():
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("程序已运行", "施工项目记账程序已经在运行中。", parent=root)
        root.destroy()
        return
    try:
        copied, failures = migrate_legacy_data()
        if copied:
            logger.info("Legacy data migration copied %d files", copied)
        for failure in failures:
            logger.warning("Legacy data migration failed: %s", failure)
        migrate_all_known_files()
        root = tk.Tk()
        MainInterface(root)
        root.mainloop()
    except Exception:
        logger.critical("程序启动失败:\n%s", traceback.format_exc())
        raise
    finally:
        instance_lock.release()


if __name__ == "__main__":
    main()
