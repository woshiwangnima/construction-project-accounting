# Repository Guidelines

## Documentation Map

Read the relevant document before changing that area:

- Architecture and module boundaries: `docs/architecture.md`
- UI design and Qt implementation: `docs/ui-guidelines.md`
- Data, configuration, migration, backup, and saving: `docs/data-and-persistence.md`
- Development, testing, commits, and pull requests: `docs/development.md`
- Packaging and releases: `docs/release-and-packaging.md`
- CLI contract and commands: `docs/cli.md`

The rules in this file are mandatory summaries. Detailed documents provide context and checklists. If they conflict, this file takes precedence.

## Project Structure

- `main.py` starts the PySide6 desktop application; Qt code belongs in `src/gui/qt/`.
- `cli.py` and `src/cli/` provide the non-GUI command line interface and must not import Qt.
- Domain models, calculations, configuration, persistence, and backups belong in `src/` and must not depend on the GUI.
- Framework-independent UI helpers belong in `src/gui/common/`; shared theme, font, clipboard, and editability helpers belong in `src/gui/`.
- `config/` contains bundled defaults, `assets/` contains resources, `scripts/` contains release/migration helpers, and `tests/` contains the test suite.
- Runtime data belongs in `projects/`, `backups/`, `logs/`, or the configured external data directories; it is not source code.

GUI and CLI must reuse the same domain and persistence logic. Do not duplicate calculations or write project JSON directly from an adapter.

## Non-Negotiable UI Rules

Follow `docs/ui-guidelines.md` for every UI change.

- Colors come from `src/theme_tokens.py` / `src/gui/theme.py`: one warm-gray neutral ramp and one terracotta accent (`#b5572f`). Do not hardcode feature-level hex colors or introduce another hue. Body-text contrast must remain at least 4.5:1.
- Font sizes come only from `theme.FONT_SIZE_MULTIPLIERS` and `theme.font_px(role)`. Never write a `font-size: Npx` literal; interpolate the helper into QSS. Layout widths used to avoid clipping must scale with the font (for example, `label_col_width()`).
- All icons go through `src/gui/qt/icons.py`. Do not hardcode icon names, use the unavailable `fa5r` prefix, or use colorful emoji in UI text.
- Install explanatory tooltips with `src/gui/qt/tooltips.py::set_readable_tooltip()`, not direct `setToolTip()` calls. Use `TOOLTIP_QSS` only for item-view fallback cases.
- Use class-level PySide6 enums, such as `QPainter.RenderHint.Antialiasing`; instance-level enum access can fail on PySide6 6.11.
- Use the shared `confirm_dialog()` for confirmations. qfluentwidgets mask dialogs must be anchored to the top-level window, not a narrow child widget.
- Row-level table hover and action buttons must use `QtBaseTable`'s tracked hover row and `RowActionDelegate.set_hover_row()`, not only `QStyle.State_MouseOver`.
- A host `QObject` must call `ProjectSaveBridge.close()` before it is destroyed.

## Non-Negotiable Data Rules

Follow `docs/data-and-persistence.md` for data-related changes.

- Preserve JSON compatibility, atomic writes, backups, and existing lock behavior. Schema changes require defaults, migration/repair logic, and tests with old data.
- `Project` is both a dataclass and a mapping. `del project[key]` resets a dataclass field to its default; it does not remove it. Membership is `hasattr`-based, so check the value rather than membership after reset.
- `_deep_merge` replaces lists wholesale. When adding per-column configuration, update `config_loader.load_app()` repair logic so old configurations receive the new key without losing user values.
- CLI write commands must reuse `project_manager` and its GUI-running guard; they must not write JSON independently.
- Never commit user projects, backups, logs, generated builds, virtual environments, `config/user_config.json`, or secrets.
- Respect `CPA_DATA_DIR`, `CPA_PROJECTS_DIR`, `CPA_BACKUPS_DIR`, `CPA_CONFIG_DIR`, and `CPA_LOG_LEVEL` when testing alternate paths.

## Build and Validation

Run commands from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m compileall -q main.py cli.py src
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Every Python change requires the compile check and complete test suite. GUI changes also require manual checks for startup, shutdown, resizing, larger font settings, persistence, tooltips, and affected dialogs. Data changes must additionally verify old-data loading, backup, migration, save/reload, and failure behavior.

If Qt smoke tests become flaky during teardown, first inspect background-thread signals and whether every `ProjectSaveBridge` is closed before its host QObject is destroyed.

## Packaging

Run `build.bat` to create `dist/ConstructionAccounting`. Packaging is driven by `packaging/ConstructionAccounting.spec`; do not move the spec under `build/`, which is deleted before builds. Paths in the spec must derive from `SPECPATH`.

When a dependency adds a Qt module, review both `QT_EXCLUDES` and `BIN_EXCLUDE_KEYWORDS`: excluding Python bindings does not remove the corresponding Qt6 native DLLs. See `docs/release-and-packaging.md` before changing packaging.

## Coding and Change Discipline

- Use Python 3.10+, four-space indentation, standard-library import style, `snake_case` functions/variables, `PascalCase` classes, and `UPPER_SNAKE_CASE` constants.
- Add type hints where they clarify data flow. Keep changes focused and avoid unrelated refactors.
- Add regression tests for fixed bugs and compatibility tests for schema/configuration changes.
- Use concise Chinese summaries or Conventional Commit-style messages such as `feat:` and `chore:`.
- Pull requests must explain user-visible behavior, list validation commands, identify schema/config changes, and include screenshots for UI modifications.
