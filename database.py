import json
import os
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def get_app_data_dir() -> Path:
    """Resolve the writable data directory for dev and frozen .exe modes."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parent / "data"


def get_resource_path(relative_path: str) -> Path:
    """Resolve read-only bundled asset paths for dev and frozen .exe modes."""
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_path / relative_path


DEFAULT_NOTE_TABS = [
    ("Scratchpad", "fa5s.sticky-note", ""),
    ("Commands", "fa5s.terminal", ""),
    ("Templates", "fa5s.file-alt", ""),
    ("Tasks", "fa5s.check-square", ""),
    ("Tickets & Logs", "fa5s.clipboard-list", ""),
    ("Network & IPs", "fa5s.network-wired", ""),
    ("Code & Scripts", "fa5s.code", ""),
    ("KB & Links", "fa5s.bookmark", ""),
    ("Ideas", "fa5s.lightbulb", ""),
]


DEFAULT_GLOBAL_SETTINGS: Dict[str, Any] = {
    "active_profile": "work",
    "dock_edge": "right",
    "sidebar_width": 380,
    "sidebar_height": 360,
    "sidebar_opacity": 100,
    "is_pinned": False,
    "pinned_screen_name": "",
    "pinned_screen_center": None,
}


class DatabaseManager:
    def __init__(self, profile: str = "work", base_dir: Optional[Path] = None):
        self.base_dir = base_dir or get_app_data_dir()
        self.backup_dir = self.base_dir / "backups"
        self.icons_dir = self.base_dir / "icons"
        self.settings_path = self.base_dir / "settings.json"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.icons_dir.mkdir(parents=True, exist_ok=True)

        self.profile = ""
        self.db_path: Path = self.base_dir / "work.db"
        self.switch_profile(profile)

    def switch_profile(self, profile: str) -> None:
        """Switches active SQLite database between 'work' and 'personal'."""
        self.profile = profile.lower().strip()
        self.db_path = self.base_dir / f"{self.profile}.db"
        self._init_schema()
        self._perform_daily_backup()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS shortcuts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    target TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'app',
                    icon_path TEXT DEFAULT '',
                    sort_order INTEGER DEFAULT 0,
                    use_count INTEGER NOT NULL DEFAULT 0,
                    last_used_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS note_tabs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tab_name TEXT NOT NULL,
                    icon_name TEXT NOT NULL DEFAULT 'fa5s.sticky-note',
                    content TEXT DEFAULT '',
                    rich_content TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS note_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tab_id INTEGER NOT NULL,
                    content TEXT DEFAULT '',
                    rich_content TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS clip_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'text',
                    is_checked INTEGER NOT NULL DEFAULT 0,
                    is_pinned INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS workspace_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            # Non-destructive column migrations for existing databases
            note_cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(note_tabs)").fetchall()
            }
            if "rich_content" not in note_cols:
                conn.execute(
                    "ALTER TABLE note_tabs ADD COLUMN rich_content TEXT DEFAULT ''"
                )

            shortcut_cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(shortcuts)").fetchall()
            }
            if "use_count" not in shortcut_cols:
                conn.execute(
                    "ALTER TABLE shortcuts ADD COLUMN use_count INTEGER NOT NULL DEFAULT 0"
                )
            if "last_used_at" not in shortcut_cols:
                conn.execute(
                    "ALTER TABLE shortcuts ADD COLUMN last_used_at TIMESTAMP"
                )

            clip_cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(clip_queue)").fetchall()
            }
            if "is_pinned" not in clip_cols:
                conn.execute(
                    "ALTER TABLE clip_queue ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0"
                )

            # Seed or non-destructively upgrade vertical note tabs up to all 9 defaults
            count = conn.execute("SELECT COUNT(*) FROM note_tabs").fetchone()[0]
            if count < len(DEFAULT_NOTE_TABS):
                conn.executemany(
                    "INSERT INTO note_tabs (tab_name, icon_name, content) VALUES (?, ?, ?)",
                    DEFAULT_NOTE_TABS[count:],
                )

    def _perform_daily_backup(self, max_backups: int = 5) -> None:
        if not self.db_path.exists():
            return
        today_stamp = datetime.now().strftime("%Y-%m-%d")
        backup_file = self.backup_dir / f"{self.profile}_{today_stamp}.db"
        if not backup_file.exists():
            shutil.copy2(self.db_path, backup_file)

        # Prune older backups beyond max_backups for this profile
        backups = sorted(
            self.backup_dir.glob(f"{self.profile}_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old_backup in backups[max_backups:]:
            old_backup.unlink(missing_ok=True)

    # --- Global & Per-Profile Settings Helpers ---
    def get_global_settings(self) -> Dict[str, Any]:
        """Reads shared global app settings from data/settings.json."""
        settings = dict(DEFAULT_GLOBAL_SETTINGS)
        if not self.settings_path.is_file():
            return settings
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                settings.update(raw)
        except Exception:
            pass
        return settings

    def get_global_setting(self, key: str, default: Any = None) -> Any:
        settings = self.get_global_settings()
        return settings.get(key, default)

    def update_global_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Atomically merges and writes updates into data/settings.json."""
        settings = self.get_global_settings()
        settings.update(updates)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self.settings_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.settings_path)
        return settings

    def set_global_setting(self, key: str, value: Any) -> None:
        self.update_global_settings({key: value})

    def get_workspace_setting(self, key: str, default: Any = None) -> Any:
        """Reads a per-profile workspace setting from SQLite workspace_state."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM workspace_state WHERE key = ?",
                (str(key),),
            ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return default

    def set_workspace_setting(self, key: str, value: Any) -> None:
        """Persists a per-profile workspace setting inside SQLite workspace_state."""
        payload = json.dumps(value)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO workspace_state (key, value) VALUES (?, ?)",
                (str(key), payload),
            )

    # --- Panel 2: Clip Queue Helpers ---
    def add_clip(self, content: str, source_type: str = "text") -> int:
        content = content.strip()
        if not content:
            return -1
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM clip_queue WHERE content = ? ORDER BY id DESC LIMIT 1",
                (content,),
            ).fetchone()
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) FROM clip_queue"
            ).fetchone()[0]
            if existing is not None:
                clip_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE clip_queue
                    SET source_type = ?, sort_order = ?, created_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (source_type, max_order + 1, clip_id),
                )
            else:
                cur = conn.execute(
                    """
                    INSERT INTO clip_queue (content, source_type, is_checked, is_pinned, sort_order)
                    VALUES (?, ?, 0, 0, ?)
                    """,
                    (content, source_type, max_order + 1),
                )
                clip_id = int(cur.lastrowid)
            conn.execute(
                "INSERT OR REPLACE INTO workspace_state (key, value) VALUES ('last_captured_clip_id', ?)",
                (json.dumps(clip_id),),
            )
            return clip_id

    def get_clips(self, search_query: str = "") -> List[Dict]:
        with self._connect() as conn:
            if search_query.strip():
                rows = conn.execute(
                    """
                    SELECT * FROM clip_queue
                    WHERE content LIKE ?
                    ORDER BY COALESCE(is_pinned, 0) DESC, sort_order ASC, id ASC
                    """,
                    (f"%{search_query.strip()}%",),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM clip_queue
                    ORDER BY COALESCE(is_pinned, 0) DESC, sort_order ASC, id ASC
                    """
                ).fetchall()
            return [dict(r) for r in rows]

    def get_latest_clip(self) -> Optional[Dict]:
        """Returns the most recently captured clip in clip_queue, or None if empty."""
        with self._connect() as conn:
            state_row = conn.execute(
                "SELECT value FROM workspace_state WHERE key = 'last_captured_clip_id'"
            ).fetchone()
            if state_row is not None:
                try:
                    last_id = int(json.loads(state_row["value"]))
                    row = conn.execute(
                        "SELECT * FROM clip_queue WHERE id = ?",
                        (last_id,),
                    ).fetchone()
                    if row is not None:
                        return dict(row)
                except Exception:
                    pass
            row = conn.execute(
                "SELECT * FROM clip_queue ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row is not None else None

    def set_clip_checked(self, clip_id: int, is_checked: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE clip_queue SET is_checked = ? WHERE id = ?",
                (1 if is_checked else 0, clip_id),
            )

    def set_clip_pinned(self, clip_id: int, is_pinned: bool) -> None:
        """Stars or unstars a clip (starred clips float to the top & survive Clear All)."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE clip_queue SET is_pinned = ? WHERE id = ?",
                (1 if is_pinned else 0, int(clip_id)),
            )

    def update_clip(
        self, clip_id: int, content: str, source_type: Optional[str] = None
    ) -> bool:
        """Updates clip text/image content and updates inferred source_type."""
        cleaned = (content or "").strip()
        if not cleaned:
            return False
        if source_type is None:
            if cleaned.startswith("data:image/"):
                source_type = "image"
            elif cleaned.startswith(("http://", "https://")) and "\n" not in cleaned:
                source_type = "url"
            elif Path(cleaned).is_absolute() and Path(cleaned).exists():
                source_type = "path"
            else:
                source_type = "text"
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE clip_queue SET content = ?, source_type = ? WHERE id = ?",
                (cleaned, source_type, int(clip_id)),
            )
            return cur.rowcount > 0

    def delete_clip(self, clip_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM clip_queue WHERE id = ?", (clip_id,))

    def clear_clips(self, only_checked: bool = False) -> None:
        with self._connect() as conn:
            if only_checked:
                conn.execute(
                    "DELETE FROM clip_queue WHERE is_checked = 1 AND COALESCE(is_pinned, 0) = 0"
                )
            else:
                conn.execute(
                    "DELETE FROM clip_queue WHERE COALESCE(is_pinned, 0) = 0"
                )

    # --- Panel 1: Shortcuts & Notes Helpers ---
    def get_shortcuts(
        self, search_query: str = "", sort_by_usage: bool = False
    ) -> List[Dict]:
        order_clause = (
            "use_count DESC, sort_order ASC, id ASC"
            if sort_by_usage
            else "sort_order ASC, id ASC"
        )
        with self._connect() as conn:
            if search_query.strip():
                q = f"%{search_query.strip()}%"
                rows = conn.execute(
                    f"SELECT * FROM shortcuts WHERE title LIKE ? OR target LIKE ? ORDER BY {order_clause}",
                    (q, q),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT * FROM shortcuts ORDER BY {order_clause}"
                ).fetchall()
            return [dict(r) for r in rows]

    def add_shortcut(self, title: str, target: str, category: str = "app", icon_path: str = "") -> int:
        with self._connect() as conn:
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) FROM shortcuts"
            ).fetchone()[0]
            cur = conn.execute(
                """
                INSERT INTO shortcuts (title, target, category, icon_path, sort_order)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title.strip(), target.strip(), category, icon_path, max_order + 1),
            )
            return cur.lastrowid

    def increment_shortcut_usage(self, shortcut_id: int) -> None:
        """Increment usage frequency counter and timestamp for a launched shortcut."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE shortcuts
                SET use_count = COALESCE(use_count, 0) + 1,
                    last_used_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (shortcut_id,),
            )

    def reorder_shortcuts(self, ordered_ids: List[int]) -> None:
        """Persist explicit drag-and-drop shortcut ordering."""
        with self._connect() as conn:
            for order_idx, sid in enumerate(ordered_ids, start=1):
                conn.execute(
                    "UPDATE shortcuts SET sort_order = ? WHERE id = ?",
                    (order_idx, int(sid)),
                )

    def get_note_tabs(self) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM note_tabs ORDER BY id ASC").fetchall()
            return [dict(r) for r in rows]

    def update_note_tab_meta(
        self, tab_id: int, tab_name: str, icon_name: str
    ) -> bool:
        """Updates display title and qtawesome icon name for an existing note tab."""
        clean_name = str(tab_name or "").strip()
        clean_icon = str(icon_name or "").strip()
        if not clean_name or not clean_icon:
            return False
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE note_tabs SET tab_name = ?, icon_name = ? WHERE id = ?",
                (clean_name, clean_icon, int(tab_id)),
            )
            return cur.rowcount > 0

    def reset_note_tabs_meta(self) -> None:
        """Restores default names and icons for canonical note tabs while keeping content."""
        with self._connect() as conn:
            rows = conn.execute("SELECT id FROM note_tabs ORDER BY id ASC").fetchall()
            for idx, row in enumerate(rows[: len(DEFAULT_NOTE_TABS)]):
                def_name, def_icon, _ = DEFAULT_NOTE_TABS[idx]
                conn.execute(
                    "UPDATE note_tabs SET tab_name = ?, icon_name = ? WHERE id = ?",
                    (def_name, def_icon, int(row["id"])),
                )

    def export_workspace_backup(self, zip_path: Path | str) -> Path:
        """Packages work.db, personal.db, settings.json, and cached icons into a .zip."""
        target = Path(zip_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for fname in ("work.db", "personal.db", "settings.json"):
                src = self.base_dir / fname
                if src.is_file():
                    zf.write(src, arcname=fname)
            if self.icons_dir.is_dir():
                for icon_file in sorted(self.icons_dir.iterdir()):
                    if icon_file.is_file():
                        zf.write(icon_file, arcname=f"icons/{icon_file.name}")
        return target

    def import_workspace_backup(self, zip_path: Path | str) -> bool:
        """Safely restores workspace databases, settings.json, and icons from a backup .zip."""
        src = Path(zip_path)
        if not src.is_file():
            return False
        try:
            with zipfile.ZipFile(src, "r") as zf:
                names = set(zf.namelist())
                if not (names & {"work.db", "personal.db", "settings.json"}):
                    return False
                self.base_dir.mkdir(parents=True, exist_ok=True)
                self.icons_dir.mkdir(parents=True, exist_ok=True)
                for member in zf.namelist():
                    norm_member = member.replace("\\", "/")
                    if norm_member.startswith("/") or ".." in norm_member.split("/"):
                        continue
                    if norm_member in ("work.db", "personal.db", "settings.json"):
                        dest = self.base_dir / norm_member
                        dest.write_bytes(zf.read(member))
                    elif norm_member.startswith("icons/") and not norm_member.endswith("/"):
                        rel = norm_member[len("icons/") :]
                        if rel and Path(rel).name == rel:
                            dest_icon = self.icons_dir / rel
                            dest_icon.write_bytes(zf.read(member))
        except Exception:
            return False
        self._init_schema()
        return True

    def update_note_content(
        self, tab_id: int, content: str, rich_content: str = ""
    ) -> None:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT content, rich_content FROM note_tabs WHERE id = ?",
                (tab_id,),
            ).fetchone()
            old_content = (existing["content"] or "") if existing else ""
            old_rich = (existing["rich_content"] or "") if existing else ""

            changed = old_content != content or old_rich != rich_content
            if changed:
                has_history = conn.execute(
                    "SELECT 1 FROM note_history WHERE tab_id = ? LIMIT 1",
                    (tab_id,),
                ).fetchone()
                if not has_history and (old_content or old_rich):
                    conn.execute(
                        "INSERT INTO note_history (tab_id, content, rich_content) VALUES (?, ?, ?)",
                        (tab_id, old_content, old_rich),
                    )
                if content or rich_content or old_content or old_rich:
                    conn.execute(
                        "INSERT INTO note_history (tab_id, content, rich_content) VALUES (?, ?, ?)",
                        (tab_id, content, rich_content),
                    )
                    conn.execute(
                        """
                        DELETE FROM note_history
                        WHERE tab_id = ?
                          AND id NOT IN (
                              SELECT id FROM note_history
                              WHERE tab_id = ?
                              ORDER BY id DESC
                              LIMIT 30
                          )
                        """,
                        (tab_id, tab_id),
                    )

            conn.execute(
                """
                UPDATE note_tabs
                SET content = ?, rich_content = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (content, rich_content, tab_id),
            )

    def get_note_history(self, tab_id: int) -> List[Dict]:
        """Return saved note history snapshots for tab_id ordered newest-first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM note_history WHERE tab_id = ? ORDER BY id DESC",
                (tab_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def restore_note_version(self, history_id: int) -> Optional[Dict]:
        """Restore a note tab to a historical snapshot and return the updated tab."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM note_history WHERE id = ?",
                (history_id,),
            ).fetchone()
            if row is None:
                return None
            tab_id = int(row["tab_id"])
            restored_content = row["content"] or ""
            restored_rich = row["rich_content"] or ""

        self.update_note_content(tab_id, restored_content, restored_rich)
        with self._connect() as conn:
            updated = conn.execute(
                "SELECT * FROM note_tabs WHERE id = ?",
                (tab_id,),
            ).fetchone()
            return dict(updated) if updated is not None else None