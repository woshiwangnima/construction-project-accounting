"""Reproducible offscreen table benchmark; never reads user project files."""
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main():
    with tempfile.TemporaryDirectory(prefix="cpa_benchmark_") as directory:
        os.environ["CPA_DATA_DIR"] = directory
        os.environ["CPA_CONFIG_DIR"] = directory
        from PySide6.QtWidgets import QApplication
        from src.bill_calculation_cache import BillCalculationCache
        from src.bill_recompute import summarize_bill_calculations
        from src.gui.qt.bill_table import QtBillTable
        from src.gui.font_manager import font_manager

        app = QApplication.instance() or QApplication([])
        font_manager.init_qt()
        results = []
        for count in (1000, 10000):
            bills = [{"id": str(i), "trade_item_id": "changed" if i % 10 == 0 else "stable", "content": "1.25*3+2",
                      "reviewed": False} for i in range(count)]
            trades = [{"id": item_id, "name": "Work", "has_unit": True, "unit_price": 2.5}
                      for item_id in ("changed", "stable")]
            table = QtBillTable({})
            table.set_columns(["#", "工作内容", "金额"], [])
            calculations, _, _ = summarize_bill_calculations(bills, trades, {})
            table.update_data(bills, trades, {}, calculations)
            timings = []
            for _ in range(5):
                start = time.perf_counter()
                bills[0]["reviewed"] = not bills[0]["reviewed"]
                if hasattr(table.model(), "refresh_rows"):
                    table.model().refresh_rows([0])
                else:
                    calculations, _, _ = summarize_bill_calculations(bills, trades, {})
                    table.update_data(bills, trades, {}, calculations)
                timings.append((time.perf_counter() - start) * 1000)
            cache = BillCalculationCache()
            cache.summarize(bills, trades, {})
            full_times, cached_times = [], []
            for _ in range(5):
                trades[0]["unit_price"] += 0.5
                start = time.perf_counter()
                expected = summarize_bill_calculations(bills, trades, {})
                full_times.append((time.perf_counter() - start) * 1000)
                start = time.perf_counter()
                actual = cache.summarize(bills, trades, {})
                cached_times.append((time.perf_counter() - start) * 1000)
                assert actual == expected
            results.append({
                "rows": count,
                "review_refresh_median_ms": round(statistics.median(timings), 3),
                "price_change_affected_rows": count // 10,
                "price_change_full_median_ms": round(statistics.median(full_times), 3),
                "price_change_cached_median_ms": round(statistics.median(cached_times), 3),
            })
            table.deleteLater()
            app.processEvents()
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
