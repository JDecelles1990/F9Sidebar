# F9Sidebar

A frameless, multi-monitor Windows 11 system-tray productivity overlay built with **Python**, **PySide6**, **SQLite**, and isolated **Win32 hooks**.

Summon it on any monitor with `F9` for instant access to app/folder/URL shortcuts, a 9-tab rich notes hub, and a silent `Ctrl+F9` clipboard capture queue.

---

## Features

### Multi-Monitor Overlay & Windows AppBar Docking
- **Active-Monitor Positioning:** Unpinned `F9` slides open on whichever monitor currently holds the mouse cursor.
- **Multi-Edge Docking:** Dock along the **Right (`↦`)**, **Bottom (`↧`)**, **Left (`↤`)**, or **Top (`↥`)** edge via the Omni-Bar dock button (click to cycle, right-click for menu) or the tray menu. Dock orientation automatically switches the Hub splitter between vertical and horizontal layouts.
- **Pin & AppBar Push-Aside (`Ctrl+Shift+F9`):** Pinning keeps the sidebar open and resizes overlapping full-screen/maximized background windows cleanly into the remaining monitor area (restoring them when unpinned or hidden).
- **Opacity Slider (`40%`–`100%`):** Live window translucency slider located directly to the left of **Copy All** in Panel 1.
- **Persistent State:** Remembers global settings (`data/settings.json`: active profile, dock edge, opacity, pin state, pinned monitor) and per-profile workspace state (`workspace_state`: active panel, active note tab, usage sort, splitter ratios, batch-copy join format), and auto-opens docked if pinned when closed.

### Panel 1 — Launcher & Notes Hub
- **6-Column Shortcut Grid:** Draggable launcher tiles for apps, folders, and URLs with native Windows shell icons (`QFileIconProvider`), async cached favicons (`data/icons/`), live search filtering, and **Usage** frequency sorting.
- **9 Canonical Note Tabs (`Ctrl+1`–`Ctrl+9`):** `Scratchpad`, `Commands`, `Templates`, `Tasks`, `Tickets & Logs`, `Network & IPs`, `Code & Scripts`, `KB & Links`, and `Ideas`.
- **Rich-Text Editor:**
  - Bold (`Ctrl+B`), Italic (`Ctrl+I`), Underline (`Ctrl+U`), Text Color, Highlight Color (`🖍️`, right-click to clear), and interactive checklists (`☐` / `☑`).
  - **Images:** Insert from file or paste directly from the clipboard; click-and-drag images within a note or onto another bottom note tab to move/copy; double-click an inline image to open **Edit & Resize Image** (resize, crop, rotate, flip, grayscale, invert, freehand draw, replace, delete, and double-click top bar for fullscreen).
  - **Inline Command Runner (`Ctrl+Enter` / `▶ Run`):** Execute selected text or the current line and insert command output directly below.
  - **Note History:** Up to 30 saved snapshots per tab in SQLite (`note_history`) for preview and one-click restore.

### Panel 2 — Clip Queue
- **Silent Capture (`Ctrl+F9`):** Captures highlighted text, URLs, file/folder paths, newly copied images, or clipboard screenshots (`Win+Shift+S`) without stealing focus, restoring your prior clipboard and showing a non-activating corner pill (`ToastPopup`) when the sidebar is hidden.
- **Paste Last Captured Item (`Ctrl+Alt+F9`):** Pastes the most recent `Ctrl+F9` text or image clip into the active window and restores the clipboard afterward.
- **Quick Copy, Inline Edit & Drag Reordering:**
  - Image clips render scaled thumbnails and dimensions (`W×H px`).
  - Click **`📋`** to quick-copy a single text or image clip to the clipboard.
  - Double-click a row or click **`✎`** for inline text editing (`Enter` saves & re-infers `url`/`path`/`text`, `Escape` cancels) or `ImageEditDialog` editing on image clips.
  - Drag rows to reorder and batch-copy checked clips (`Ctrl+C`) as Lines (`\n`), Paragraphs (`\n\n`), or Bullets (`- `).
  - Click **`→`** (left-click or right-click) to send clips into any note tab or promote URLs/paths directly into Panel 1 shortcuts.

### Profiles, Tray & Startup
- **Work / Personal Profiles:** Instant toggle between `data/work.db` and `data/personal.db` with 5-day rolling backups in `data/backups/`.
- **Keyboard Navigation:** Full `Tab` / `Enter` activation across controls alongside global `F9` hotkeys and animated hover/press button styling (`ui/button_fx.py`).
- **Single-Instance & System Tray:** Single-instance lock via `QLocalServer`, tray menu controls, pause-hotkeys toggle, and **Launch at Windows Startup** (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).

---

## Keyboard Shortcuts

### Global Hotkeys (Work Anywhere in Windows)
| Shortcut | Function |
|---|---|
| `F9` | Show or hide the sidebar on the monitor currently holding the mouse cursor |
| `Ctrl+F9` | Silently copy highlighted text, URLs, file/folder paths, or clipboard screenshots into **2. Clip Queue** without interrupting focus |
| `Ctrl+Alt+F9` | Paste the most recently special-copied item from **2. Clip Queue** into the active window |
| `Shift+F9` | Switch between **1. Notes** and **2. Clip Queue** |
| `Ctrl+Shift+F9` | Toggle pin mode & Windows AppBar docking (keeps sidebar open and pushes aside overlapping maximized windows) |

### Sidebar Navigation, Layout, Profile & Settings
| Shortcut | Function |
|---|---|
| `Ctrl+F` | Move caret into the top-left **Search** bar and select existing query text |
| `Enter` *(in Search bar)* | Copy inline `=math` result, launch top matching shortcut (`1. Notes`), cycle matching note tabs if only notes match, or copy top matching clip (`2. Clip Queue`) |
| `Ctrl+Alt+Up` | Dock/move the sidebar to the **top** edge of the screen |
| `Ctrl+Alt+Down` | Dock/move the sidebar to the **bottom** edge of the screen |
| `Ctrl+Alt+Left` | Dock/move the sidebar to the **left** edge of the screen |
| `Ctrl+Alt+Right` | Dock/move the sidebar to the **right** edge of the screen |
| `Ctrl+Shift+1` | Switch to **1. Notes** (Shortcuts & Rich Notes panel) |
| `Ctrl+Shift+2` | Switch to **2. Clip Queue** |
| `Ctrl+Shift+W` | Switch the app to **WORK** profile (`data/work.db`) |
| `Ctrl+Shift+P` | Switch the app to **PERSONAL** profile (`data/personal.db`) |
| `Ctrl+Shift+I` / `Ctrl+,` | Open the **Settings & Workspace Backup** dialog |
| `Tab` / `Enter` | Move focus across sidebar controls and activate the focused button/toggle |
| `Esc` | Clear active search text, or hide the sidebar and restore focus to the previous window |

### Panel 1 — 1. Notes & Rich Note Editor
| Shortcut | Function |
|---|---|
| `Ctrl+1` – `Ctrl+9` | Switch across the 9 canonical Note Tabs (`Scratchpad`, `Commands`, `Templates`, `Tasks`, `Tickets & Logs`, `Network & IPs`, `Code & Scripts`, `KB & Links`, `Ideas`) |
| `Ctrl+B` | Toggle **Bold** formatting on selected text or at cursor |
| `Ctrl+I` | Toggle *Italic* formatting on selected text or at cursor |
| `Ctrl+U` | Toggle <u>Underline</u> formatting on selected text or at cursor |
| `Ctrl+Shift+H` | Open highlight color picker to highlight the selected text |
| `Ctrl+Shift+C` | Open text color picker to change the text color of selected text |
| `Ctrl+Shift+T` | Insert current timestamp (`YYYY-MM-DD HH:MM`) at the cursor |
| `Ctrl+Shift+K` | Toggle monospace dark code-block styling on the current or selected paragraph(s) |
| `Enter` *(in checklist)* | Continue `☐` checklist items on the next line (or exit checklist mode on an empty item) |
| `F5` | Run all code in the current Note and append output inline (`>>> Output:`) |
| `Ctrl+F5` | Run only the highlighted/selected code and append output right after the selection |
| `Ctrl+Shift+F5` | Run highlighted/selected code and special-copy the output **only** into **2. Clip Queue** without modifying the Note |
| `Ctrl+Enter` | Run highlighted/selected code or current line and append output inline |

### Panel 2 — 2. Clip Queue
| Shortcut | Function |
|---|---|
| `Ctrl+C` | Copy all checked clips joined by the selected separator (`Lines`, `Paragraphs`, `Bullets`) |
| `Enter` *(inline edit)* | Save inline clip edits and re-classify type (`text`, `url`, `path`) |
| `Esc` *(inline edit)* | Discard inline clip edits without saving |

### Full-Screen Studio Image Editor
| Shortcut | Function |
|---|---|
| `Ctrl+Z` | Undo last stroke, shape, text edit, resize, move, transform, or filter |
| `Ctrl+Y` / `Ctrl+Shift+Z` | Redo previously undone edit |
| `Alt + Left-Click Drag` | Pan/move across the canvas (or Middle/Right-Click drag) |
| `Mouse Wheel` | Zoom canvas in or out smoothly |
| `Delete` / `Backspace` | Delete the currently selected drawn item (pen/crayon, highlighter, shape, text, or pixelate box) |
| `Ctrl+C` | Copy full-resolution edited image to the clipboard |
| `Ctrl+S` | Apply edits and save image back into the Note |
| `F11` | Toggle between Full Screen and normal windowed size (`960×640`) |
| `Esc` | Cancel changes and close the Image Editor |

---

## Getting Started

### Requirements
- Windows 11 (uses Win32 APIs in `win32_hooks.py` for global hotkeys and AppBar docking)
- Python 3.14+ (verified on Python `3.14.6`)
- Core dependencies installed in `.venv`:
  - `PySide6` (`6.12.0`)
  - `qtawesome` (`1.4.2`)

### Running the App
Once `.venv` is set up, you can launch `F9Sidebar` directly with global Python (which automatically delegates into `.venv`) or via the virtual environment interpreter:

```powershell
python main.py
```

Or explicitly via `.venv`:

```powershell
.\.venv\Scripts\python.exe main.py
```

If creating a fresh `.venv` on a new machine:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
python main.py
```

---

## Project Structure

```text
F9Sidebar/
├── main.py                 # Entry point, auto-.venv bootstrap, single-instance lock, system tray
├── database.py             # SQLite manager (work.db / personal.db), settings.json, 5-day backups
├── win32_hooks.py          # Isolated ctypes Win32 hotkeys, clipboard round-trip, AppBar window docking
├── icon_provider.py        # Native file/folder icons + async URL favicon caching
├── GEMINI.md               # Workspace architecture & coding rules
├── data/                   # Runtime SQLite DBs, settings.json, cached icons, rolling backups (gitignored)
└── ui/
    ├── sidebar_window.py   # Frameless multi-monitor/multi-edge overlay, Omni-Bar, slide animation
    ├── button_fx.py        # App-wide hover gradient, rotating glow halo, and click pulse FX
    ├── toast_popup.py      # Non-activating Ctrl+F9 corner notification pill
    ├── panel_hub.py        # Panel 1: 6-col shortcut grid, rich notes, ImageEditDialog, note history
    └── panel_queue.py      # Panel 2: draggable checkable clip queue, quick copy, inline edit, batch copy
```
