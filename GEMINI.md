# F9Sidebar — Project Workspace Rules (GEMINI.md)

## 1. Project Overview
F9Sidebar is a frameless, multi-monitor Windows 11 system-tray overlay built with Python and PySide6.
- **Global Hotkeys:**
  - `F9`: Toggle sidebar visibility on the monitor currently holding the mouse cursor.
  - `Ctrl+F9`: Silently capture highlighted text, URLs, or file paths from any active window into Panel 2's checkable queue without interrupting focus.
  - `Shift+F9`: Switch between Panel 1 (Launcher & Notes Hub) and Panel 2 (Ctrl+F9 Clip Queue).
- **Panel 1 Note Tab Shortcuts & Bottom Horizontal Tab Bar (`Ctrl+1`–`Ctrl+9`):**
  - 9 canonical horizontal note tabs along the bottom bar: `Scratchpad` (`Ctrl+1`), `Commands` (`Ctrl+2`), `Templates` (`Ctrl+3`), `Tasks` (`Ctrl+4`), `Tickets & Logs` (`Ctrl+5`), `Network & IPs` (`Ctrl+6`), `Code & Scripts` (`Ctrl+7`), `KB & Links` (`Ctrl+8`), and `Ideas` (`Ctrl+9`).

## 2. Strict Coding & Framework Rules
- **GUI Framework:** Strictly use `PySide6` (`QtCore`, `QtGui`, `QtWidgets`). NEVER import `PyQt5` or `PyQt6`.
- **Win32 Isolation:** All `ctypes` / `user32` calls MUST remain isolated inside `win32_hooks.py`. Do not scatter Win32 API calls across UI files.
- **PySide6 C++ Inheritance Rule:** Never inherit from both `QObject` and `QAbstractNativeEventFilter` in the same class (avoids Shiboken metaclass conflicts). Use composition instead.
- **Database:** Use built-in `sqlite3` via `database.py`. Support instant profile switching between `data/work.db` and `data/personal.db`.
- **UI Theme (Dark Mode QSS):**
  - Main Background: `#1E1E2E`
  - Surface / Cards / Tiles: `#2A2D3E`
  - Border / Divider: `#363A4F`
  - Primary Accent: `#89B4FA`
  - Text Primary: `#CDD6F4`, Text Muted: `#A6ADC8`

## 3. Directory Structure
C:\Dev\F9Sidebar\
├── GEMINI.md
├── main.py                 # Entry point, single-instance lock, QSystemTrayIcon
├── database.py             # SQLite manager (work.db / personal.db) + 5-day rolling backup
├── win32_hooks.py          # RegisterHotKey, focus memory, silent Ctrl+F9 clipboard round-trip
├── icon_provider.py        # QFileIconProvider (.exe/folders) + async favicon caching
└── ui/
    ├── sidebar_window.py   # Frameless overlay, active-monitor slide animation, Omni-Bar header
    ├── toast_popup.py      # Non-activating Ctrl+F9 corner capture notification toast
    ├── button_fx.py        # App-wide hover gradient + blue/purple glow halo + press pulse for all buttons
    ├── panel_hub.py        # Panel 1: 6-col Icon Grid (top) + Bottom Horizontal-Tab Notes (bottom)
    └── panel_queue.py      # Panel 2: Draggable Checkable Clip Queue + Batch Copy Bar

## 4. SQLite Schema (`work.db` & `personal.db`)
- `shortcuts`: `id`, `title`, `target`, `category` ('app'|'folder'|'url'), `icon_path`, `sort_order`
- `note_tabs`: `id`, `tab_name`, `icon_name`, `content`, `updated_at` (seeded/non-destructively migrated to the 9 canonical tabs)
- `clip_queue`: `id`, `content`, `source_type` ('text'|'url'|'path'), `is_checked`, `sort_order`, `created_at`

## 5. Packaging & Path Resolution Rules
- **Writable Data (`data/work.db`, `data/personal.db`, `data/icons/`, `data/backups/`):** Must resolve next to the executable (`Path(sys.executable).resolve().parent / "data"`) when `getattr(sys, "frozen", False)` is `True`, and `Path(__file__).resolve().parent / "data"` during IDE development. Never store SQLite databases inside `sys._MEIPASS`.
- **Bundled Read-Only Assets (e.g., `bin/ahk/`):** Must resolve via `Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))`.

## 6. Agent Execution & Verification Environment
- Always run Python commands and tests using `.\.venv\Scripts\python.exe`.
- Run automated PySide6 UI verification scripts with `$env:QT_QPA_PLATFORM="offscreen"`.

## 7. Documentation Rules
- Document every keyboard shortcut and its exact function inside `README.md` under the `## Keyboard Shortcuts` section.
- Keep `README.md` synchronized whenever any global, sidebar, panel, note editor, or image editor keyboard shortcut is added, changed, or removed.