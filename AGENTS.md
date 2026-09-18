# Repository Guidelines

## Project Structure & Module Organization

- `main.py` is the Windows desktop entry point; it starts the Qt (PySide6) app in `src/gui/qt/`.
- `src/` contains application logic and data models; `src/gui/qt/` contains the Qt windows, dialogs, and widgets. `QtContentArea` (in `content.py`) is composed of `BillViewMixin` (`bill_view.py`) and `WorkerViewMixin` (`worker_view.py`); shared helpers live in `view_common.py` (metric cards / QSS), `category_utils.py` (pure category + column-weight logic), and `save_bridge.py` (async project save — call `close()` before the host QObject is destroyed).
- Known pitfall: PySide6 6.11 removed instance-level enum access (e.g. `painter.Antialiasing` raises `AttributeError` and can crash a delegate's `paint`); always use class-level enums (`QPainter.RenderHint.Antialiasing`) or `Qt.X` constants.
- Known pitfall: inside a delegate's `paint`, `option.state & QStyle.State_MouseOver` is not a reliable "which row is the mouse on" signal for row-level UI (the `操作` column's ↑/↓/✕ buttons). `QtBaseTable` tracks the hovered row itself (`RowActionDelegate.set_hover_row`) from `mouseMoveEvent` / `leaveEvent` / `wheelEvent` / `scrollContentsBy` and paints the buttons only for that row; row hover fill uses the same source so the two cannot drift apart.
- Known pitfall: qfluentwidgets `MessageBox` / `MaskDialogBase` derives its mask size from the widget you pass as `parent` (`setGeometry(0, 0, parent.width(), parent.height())`). Passing a narrow child such as the project sidebar squeezes the dialog to that width and clips the message and buttons. `confirm_dialog()` therefore promotes the parent to the top-level window and re-anchors the mask to the window's global rect.
- Known pitfall: `Project` is a dataclass that also implements the mapping protocol (`__getitem__` / `__setitem__` / `__contains__` / `__delitem__`). `del project[key]` resets the field to its dataclass default because fields cannot truly be removed; `__contains__` is `hasattr`-based, so a reset field still reports as contained — check the value, not membership.
- Known pitfall: `default_bill_column_widths_data` is a list, and `_deep_merge` replaces lists wholesale instead of merging element-wise, so a config file written by an older build never receives newly added per-column keys. `config_loader.load_app()` repairs rows by name against `_DEFAULT_CONFIGS`; add the same repair whenever you introduce another per-column flag.
- Known pitfall (2026-09-18): qtawesome 1.4.2 only bundles `fa5`/`fa5s`/`fa6`/`fa6s` — there is **no `fa5r` regular variant** (raises `Invalid font prefix "fa5r"` once a QApplication exists). All icons must go through `src/gui/qt/icons.py`, which uses the Phosphor (`ph.*`) linear font; do not hard-write icon-name strings in feature modules. Colorful emoji in UI text are also banned — they render as multicolor system glyphs.
- Font sizes have exactly one source of truth: `theme.FONT_SIZE_MULTIPLIERS` plus `theme.font_px(role)`. Both `build_qss()` and `font_manager` derive from that table (they used to keep separate copies). Never write a `font-size: Npx` literal in a widget - it silently ignores the user's 默认字号 setting; and always interpolate the helper (`f"font-size: {font_px('small')}px"`), a bare `font_px(...)` inside a stylesheet is invalid CSS that Qt drops without any warning. `tests/test_font_consistency.py` fails the build on either mistake. Sizes that exist only to keep a form's label column aligned (`label_col_width()`) must scale with the font too, otherwise a larger base size clips labels like 「已审核行颜色」.
- Palette rule (2026-09-18): one warm-gray neutral ramp + a single terracotta accent (`#b5572f`), defined in `src/theme_tokens.py` / `src/gui/theme.py`. Do not introduce a second hue (especially blues/cyans) or hardcode hex values in feature modules; body-text contrast must stay ≥ 4.5:1. Guarded by `tests/test_theme_qt.py::test_palette_has_no_second_hue`.
- Tooltip readability rule: explanatory hover text on widgets must be installed through `src/gui/qt/tooltips.py::set_readable_tooltip()`, which intercepts the native `QToolTip` event and renders a self-styled qfluentwidgets floating layer using centralized `TOOLTIP_BG` / `TOOLTIP_FG`. Do not call `setToolTip()` directly for new widget help text and never set tooltip colors in feature modules. Windows, Qt, qfluentwidgets, and local QSS can split ownership of native tooltip foreground/background, so palette/QSS alone is not a reliable fix. `TOOLTIP_QSS` remains the fallback for item-view tooltips that cannot install a widget filter; any locally styled container containing those native tooltips must append it. The required appearance is high-contrast dark warm-gray background + light text.
- Framework-agnostic helpers shared by the UI live in `src/gui/common/` (`reorder`, `column_layout`); theme, font, clipboard and editability helpers live directly under `src/gui/`.
- `config/` stores bundled defaults, while `assets/` stores bundled audio and other resources.
- `scripts/` contains release, migration, manifest, and versioning helpers. Runtime data belongs in `projects/`, `backups/`, and `logs/`; these directories are not source code.
- Runtime user data defaults to `%APPDATA%\\ConstructionAccounting` on Windows and can be redirected with `CPA_DATA_DIR` or the specific `CPA_*_DIR` variables.
- `tests/` holds the `unittest` suite (also runnable via `pytest`).

## Build, Test, and Development Commands

Run commands from the repository root so relative config and asset paths resolve correctly:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m compileall -q main.py src
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

The first two commands create an isolated environment and install dependencies. `main.py` launches the GUI; `compileall` catches syntax errors; `unittest discover` runs the test suite. Run `build.bat` to create the PyInstaller `dist/ConstructionAccounting` release bundle.

Packaging is driven by `packaging/ConstructionAccounting.spec` (paths derived from `SPECPATH`, so it works from any checkout). Do not put the spec under `build/` — `build.bat` deletes that directory before each run. When adding a dependency that pulls in a new Qt module, revisit the `QT_EXCLUDES` and `BIN_EXCLUDE_KEYWORDS` lists in the spec: `excludes` only removes Python bindings, the Qt6 native DLLs must be filtered from `a.binaries` as well.

## Coding Style & Naming Conventions

Use Python 3.10+ with four-space indentation and standard-library style imports. Use `snake_case` for modules, functions, and variables; `PascalCase` for classes; and `UPPER_SNAKE_CASE` for constants. Keep domain and persistence logic in `src/` modules and UI-specific code under `src/gui/`. Add type hints where they clarify data flow, and preserve the existing JSON schema and atomic-write behavior. No formatter or linter is configured, so keep changes small and run the compile check.

## Testing Guidelines

There is no coverage threshold. For every change, run the compile check plus `.\.venv\Scripts\python.exe -m unittest discover -s tests`, and manually exercise the affected Qt workflow. GUI changes should be checked for startup, resizing, persistence, and relevant dialogs; data changes should also verify backup and migration behavior.

Historical note (resolved 2026-09-11): `tests/test_qt_smoke.py` used to be flaky — the root cause was `ProjectSaveBridge`'s background thread emitting signals after the host QObject was destroyed (`RuntimeError: Signal source has been deleted`, which broke the drain loop). Fixed by guarding emits and adding `ProjectSaveBridge.close()` called from `MainWindow._on_close`. If flakiness returns, look at background-thread vs. teardown races first.

## Commit & Pull Request Guidelines

Recent commits use concise descriptions, with a mixture of Chinese summaries and Conventional Commit-style prefixes such as `feat:` and `chore:`. Follow that pattern, keep each commit focused, and mention user-visible behavior when applicable. Pull requests should explain the change, list validation commands, call out schema or config changes, and include screenshots for UI modifications.

## Configuration & Data Safety

Do not commit user projects, backups, logs, generated builds, virtual environments, or `config/user_config.json`. Respect `CPA_PROJECTS_DIR`, `CPA_BACKUPS_DIR`, `CPA_CONFIG_DIR`, and `CPA_LOG_LEVEL` when testing alternate locations. Never store secrets in tracked JSON or source files.
