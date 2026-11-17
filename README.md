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

| Shortcut | Scope | Action |
|---|---|---|
| `F9` | Global | Toggle sidebar on the monitor holding the cursor |
| `Ctrl+F9` | Global | Silently capture selection / URL / path / screenshot to Clip Queue |
| `Ctrl+Alt+F9` | Global | Paste the latest `Ctrl+F9` captured item into the active window |
| `Shift+F9` | Global | Switch between Panel 1 (Hub) and Panel 2 (Clip Queue) |
| `Ctrl+Shift+F9` | Global | Pin / unpin sidebar and toggle AppBar dock push-aside |
| `Ctrl+1` – `Ctrl+9` | Sidebar | Switch Panel 1 note tab |
| `Ctrl+B` / `I` / `U` | Note Editor | Toggle bold / italic / underline |
| `Ctrl+Enter` | Note Editor | Run selected text or current line and append output |
| `Ctrl+C` | Panel 2 | Copy all checked clips using selected join format |
| `Esc` | Sidebar | Clear Omni-Search filter or hide sidebar (cancels inline edit when editing) |

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
