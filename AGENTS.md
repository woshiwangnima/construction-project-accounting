# AGENTS.md

## Quick Start

```bash
python main.py
# or double-click start.bat (Windows)
```

## Project Overview

Tkinter desktop app for construction project accounting. Single-window architecture: left sidebar (project list) + right content area (bills & work types).

## Architecture

```
main.py → src/gui/__init__.py → src/gui/main_window.py
                                    ├── sidebar.py      (project list)
                                    ├── content.py      (bills + work types tabs)
                                    ├── theme.py        (colors/fonts constants)
                                    ├── widgets.py      (reusable buttons, inputs)
                                    └── dialogs/
                                        ├── new_project.py
                                        ├── edit_trade.py
                                        └── edit_bill.py

src/
├── project_manager.py   (CRUD + backup + cache)
├── calculator.py        (math expression parser)
├── config_loader.py     (JSON config read/write)
├── image_output.py      (PIL text → PNG export)
├── logger.py            (file + console logging)
└── utils.py             (atomic_write_json)
```

## Key Commands

```bash
# Install dependencies
pip install -r config/requirements.txt

# Run
python main.py

# Check syntax
python -c "import py_compile; py_compile.compile('src/gui/main_window.py', doraise=True)"
```

## Environment Variables

- `CPA_PROJECTS_DIR` — project data dir (default: `./projects`)
- `CPA_BACKUPS_DIR` — backups dir (default: `./backups`)
- `CPA_CONFIG_DIR` — config dir (default: `./config`)
- `CPA_LOG_LEVEL` — DEBUG/INFO/WARNING/ERROR (default: DEBUG)

## Data Safety

- All writes use `atomic_write_json()` (tmp file → `os.replace`)
- Project refs validated by regex `project_\d{4,8}_\d{3}` — no path traversal
- Projects auto-backup on update/delete, keeps last 10

## GUI Conventions

- Theme constants in `src/gui/theme.py` — use these, not hardcoded values
- All dialogs inherit from `tk.Toplevel`, use `transient()` + `grab_set()`
- Buttons: `primary` (green), `danger` (red), `secondary` (gray), `ghost` (transparent)
- Font: Microsoft YaHei UI, sizes 12–16

## Known Gotchas

- `start.bat` hardcodes Python path `D:\app\Miniforge\python.exe` — adjust for other machines
- Pillow is the only external dependency
- Project list cached by directory mtime — manual file edits won't trigger refresh
- Old project data may have `project_date_type` field — code handles legacy format gracefully