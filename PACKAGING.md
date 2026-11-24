# Packaging F9Sidebar for Windows

F9Sidebar ships as a standalone, windowed (`console=False`) **PyInstaller `--onedir`** Windows 11 portable release (`F9Sidebar.exe` + `_internal/`) archived as `dist/F9Sidebar-v<Version>-win64.zip`.

Using `--onedir` instead of a self-extracting `--onefile` archive provides instant startup (no temporary extraction on every launch) and significantly lower Windows Defender false-positive risk.

---

## 1. Prerequisites

Ensure the local virtual environment (`.venv`) has both runtime and build-only dependencies installed:

```powershell
# Runtime dependencies
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Build-only dependencies (PyInstaller)
.\.venv\Scripts\python.exe -m pip install -r packaging\requirements-build.txt
```

Build-only tools are kept in `packaging/requirements-build.txt` so `requirements.txt` remains strictly runtime dependencies.

---

## 2. Building a Release

Run the single-command PowerShell build script from anywhere in the repository:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

### Optional Parameters

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `-Version <semver>` | `database.APP_VERSION` | Overrides the version string used in the output `.zip` filename. |
| `-SkipZip` | `$false` | Builds only `dist\F9Sidebar\` without generating the `.zip` archive. |

### What `scripts/build.ps1` Does

1. Fails fast on any error (`Set-StrictMode -Version Latest`, `$ErrorActionPreference = 'Stop'`).
2. Verifies `.venv\Scripts\python.exe`, `PySide6`, `qtawesome`, `PyInstaller`, and `database.APP_VERSION`.
3. Ensures `assets/f9sidebar.ico` exists (runs `scripts/generate_icon.py` automatically if missing).
4. Cleans previous `build/` and `dist/` outputs.
5. Runs PyInstaller against `packaging/F9Sidebar.spec` (windowed bootloader, UPX disabled, unused heavy Qt modules and plugins pruned).
6. Runs post-build sanity checks:
   - Confirms `F9Sidebar.exe`, bundled `assets/f9sidebar.ico`, QtAwesome `.ttf`/`.json` font assets, and required Qt image plugins (`qico`, `qjpeg`, `qgif`, `qwebp`, `qsvg`) exist.
   - Fails if live dev `data/` leaked into `dist/` or if excluded Qt modules (`Qt6WebEngineCore.dll`, `Qt6Pdf.dll`, `Qt6Quick.dll`, `Qt6Qml.dll`) are present.
7. Compresses `dist/F9Sidebar/` into `dist/F9Sidebar-v<Version>-win64.zip` and prints final artifact paths and sizes.

---

## 3. Release Layout & Runtime Data Storage

Extracting `F9Sidebar-v<Version>-win64.zip` produces:

```text
F9Sidebar/
├── F9Sidebar.exe            # Windowed Windows 11 executable (no console window)
├── _internal/               # Bundled Python runtime, PySide6 DLLs, QtAwesome fonts, assets/
└── data/                    # Created automatically on first run (never bundled in the zip)
    ├── work.db              # Work profile SQLite database
    ├── personal.db          # Personal profile SQLite database (created on profile switch)
    ├── settings.json        # Edge, hotkey, startup, and window geometry settings
    ├── icons/               # Cached favicons and app icons
    ├── backups/             # 5-day rolling SQLite backups
    └── logs/
        └── f9sidebar.log    # Fatal unhandled traceback log in frozen windowed mode (capped at 512 KB)
```

### Data Directory Resolution (`database.get_app_data_dir()`)

1. **Explicit override:** If `F9SIDEBAR_DATA_DIR` is set in the environment, that directory is used.
2. **Portable default (packaged):** `data/` next to `F9Sidebar.exe` (`Path(sys.executable).resolve().parent / "data"`).
3. **Read-only install fallback:** If `F9Sidebar.exe` is placed in a non-writable directory (such as `C:\Program Files\F9Sidebar`), F9Sidebar automatically falls back to `%LOCALAPPDATA%\F9Sidebar\data`.
4. **Development mode:** `data/` in the repository root (`Path(__file__).resolve().parent / "data"`).

Read-only bundled assets (`assets/f9sidebar.ico`, optional `bin/` helpers) are always resolved through `database.get_resource_path()` via `sys._MEIPASS`, never written to at runtime.

---

## 4. Customizing the App Icon

- The default Sunset Glass multi-resolution icon (`16, 24, 32, 48, 64, 128, 256` px) is stored at `assets/f9sidebar.ico`.
- To regenerate it from source:
  ```powershell
  .\.venv\Scripts\python.exe .\scripts\generate_icon.py
  ```
- To use a custom icon, replace `assets/f9sidebar.ico` with your `.ico` file and re-run `scripts/build.ps1`.

---

## 5. Cutting Future Releases

1. **Bump the version** in both places:
   - `APP_VERSION` in `database.py`
   - `filevers`, `prodvers`, `FileVersion`, and `ProductVersion` in `packaging/version_info.txt`
2. **Build the release:**
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
   ```
3. **Verify outside the repository:**
   - Extract `dist\F9Sidebar-v<Version>-win64.zip` to an unrelated folder (e.g., `C:\Temp\F9SidebarTest\`).
   - Launch `F9Sidebar.exe` via Windows Explorer (or a shortcut with working directory `C:\Windows\System32`) with no console window appearing.
   - Verify the Sunset Glass tray icon appears, `F9` toggles the sidebar on the active monitor, `Shift+F9` switches panels, and `Ctrl+F9` captures clips into Panel 2.
   - Confirm `data\work.db`, `data\backups\`, and `data\icons\` are created beside `F9Sidebar.exe` (not inside `_internal\` or the source repo) and persist across restarts.
4. **Publish:**
   - `build/`, `dist/`, `*.exe`, and `*.zip` are ignored by `.gitignore` and must never be committed.
   - Tag the release in Git and upload `dist/F9Sidebar-v<Version>-win64.zip` to GitHub Releases.
