# Repository Guidelines

## Project Structure & Module Organization

- `main.py` is the Windows desktop entry point.
- `src/` contains application logic and data models; `src/gui/` contains Tkinter windows, dialogs, and reusable widgets.
- `config/` stores bundled defaults, while `assets/` stores bundled audio and other resources.
- `scripts/` contains release, migration, manifest, and versioning helpers. Runtime data belongs in `projects/`, `backups/`, and `logs/`; these directories are not source code.
- Runtime user data defaults to `%APPDATA%\\ConstructionAccounting` on Windows and can be redirected with `CPA_DATA_DIR` or the specific `CPA_*_DIR` variables.
- No test suite is currently checked in.

## Build, Test, and Development Commands

Run commands from the repository root so relative config and asset paths resolve correctly:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m compileall -q main.py src
```

The first two commands create an isolated environment and install dependencies. `main.py` launches the GUI; `compileall` catches syntax errors. Run `build.bat` to create the PyInstaller `dist/ConstructionAccounting` release bundle.

## Coding Style & Naming Conventions

Use Python 3.10+ with four-space indentation and standard-library style imports. Use `snake_case` for modules, functions, and variables; `PascalCase` for classes; and `UPPER_SNAKE_CASE` for constants. Keep domain and persistence logic in `src/` modules and UI-specific code under `src/gui/`. Add type hints where they clarify data flow, and preserve the existing JSON schema and atomic-write behavior. No formatter or linter is configured, so keep changes small and run the compile check.

## Testing Guidelines

There is no configured test framework or coverage threshold. For every change, run the compile check and manually exercise the affected Tkinter workflow. GUI changes should be checked for startup, resizing, persistence, and relevant dialogs; data changes should also verify backup and migration behavior.

## Commit & Pull Request Guidelines

Recent commits use concise descriptions, with a mixture of Chinese summaries and Conventional Commit-style prefixes such as `feat:` and `chore:`. Follow that pattern, keep each commit focused, and mention user-visible behavior when applicable. Pull requests should explain the change, list validation commands, call out schema or config changes, and include screenshots for UI modifications.

## Configuration & Data Safety

Do not commit user projects, backups, logs, generated builds, virtual environments, or `config/user_config.json`. Respect `CPA_PROJECTS_DIR`, `CPA_BACKUPS_DIR`, `CPA_CONFIG_DIR`, and `CPA_LOG_LEVEL` when testing alternate locations. Never store secrets in tracked JSON or source files.
