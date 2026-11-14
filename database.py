import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


def get_app_data_dir() -> Path:
    """Resolve the writable data directory for dev and frozen .exe modes."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parent / "data"


def get_resource_path(relative_path: str) -> Path:
    """Resolve read-only bundled asset paths for dev and frozen .exe modes."""
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_path / relative_path


class DatabaseManager:
    def __init__(self, profile: str = "work", base_dir: Optional[Path] = None):
        self.base_dir = base_dir or get_app_data_dir()
        self.backup_dir = self.base_dir / "backups"
        self.icons_dir = self.base_dir / "icons"
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
                    sort_order INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS note_tabs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tab_name TEXT NOT NULL,
                    icon_name TEXT NOT NULL DEFAULT 'fa5s.sticky-note',
                    content TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS clip_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'text',
                    is_checked INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            # Seed default vertical note tabs if empty
            count = conn.execute("SELECT COUNT(*) FROM note_tabs").fetchone()[0]
            if count == 0:
                default_tabs = [
                    ("Scratchpad", "fa5s.sticky-note", ""),
                    ("Commands", "fa5s.terminal", ""),
                    ("Templates", "fa5s.file-alt", ""),
                    ("Tasks", "fa5s.check-square", ""),
                ]
                conn.executemany(
                    "INSERT INTO note_tabs (tab_name, icon_name, content) VALUES (?, ?, ?)",
                    default_tabs,
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

    # --- Panel 2: Clip Queue Helpers ---
    def add_clip(self, content: str, source_type: str = "text") -> int:
        content = content.strip()
        if not content:
            return -1
        with self._connect() as conn:
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) FROM clip_queue"
            ).fetchone()[0]
            cur = conn.execute(
                """
                INSERT INTO clip_queue (content, source_type, is_checked, sort_order)
                VALUES (?, ?, 0, ?)
                """,
                (content, source_type, max_order + 1),
            )
            return cur.lastrowid

    def get_clips(self, search_query: str = "") -> List[Dict]:
        with self._connect() as conn:
            if search_query.strip():
                rows = conn.execute(
                    "SELECT * FROM clip_queue WHERE content LIKE ? ORDER BY sort_order ASC, id ASC",
                    (f"%{search_query.strip()}%",),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM clip_queue ORDER BY sort_order ASC, id ASC"
                ).fetchall()
            return [dict(r) for r in rows]

    def set_clip_checked(self, clip_id: int, is_checked: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE clip_queue SET is_checked = ? WHERE id = ?",
                (1 if is_checked else 0, clip_id),
            )

    def delete_clip(self, clip_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM clip_queue WHERE id = ?", (clip_id,))

    def clear_clips(self, only_checked: bool = False) -> None:
        with self._connect() as conn:
            if only_checked:
                conn.execute("DELETE FROM clip_queue WHERE is_checked = 1")
            else:
                conn.execute("DELETE FROM clip_queue")

    # --- Panel 1: Shortcuts & Notes Helpers ---
    def get_shortcuts(self, search_query: str = "") -> List[Dict]:
        with self._connect() as conn:
            if search_query.strip():
                q = f"%{search_query.strip()}%"
                rows = conn.execute(
                    "SELECT * FROM shortcuts WHERE title LIKE ? OR target LIKE ? ORDER BY sort_order ASC, id ASC",
                    (q, q),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM shortcuts ORDER BY sort_order ASC, id ASC"
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

    def get_note_tabs(self) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM note_tabs ORDER BY id ASC").fetchall()
            return [dict(r) for r in rows]

    def update_note_content(self, tab_id: int, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE note_tabs SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (content, tab_id),
            )