from datetime import datetime
import json
import os
from pathlib import Path
import sys
import traceback


def _reexec_into_venv_if_needed() -> None:
    """Re-launches main.py under .venv when invoked with global `python main.py`."""
    if getattr(sys, "frozen", False) or __name__ != "__main__":
        return
    venv_dir = Path(__file__).resolve().parent / ".venv"
    exe_name = (
        "pythonw.exe"
        if Path(sys.executable).name.lower() == "pythonw.exe"
        else "python.exe"
    )
    venv_python = venv_dir / "Scripts" / exe_name
    if venv_python.is_file() and Path(sys.prefix).resolve() != venv_dir.resolve():
        import subprocess

        raise SystemExit(
            subprocess.call(
                [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]]
            )
        )


_reexec_into_venv_if_needed()

try:
    import winreg
except ImportError:  # pragma: no cover - Windows only
    winreg = None

from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
import qtawesome as qta

from database import (
    APP_NAME,
    APP_VERSION,
    DatabaseManager,
    get_app_data_dir,
    get_resource_path,
)
from ui.sidebar_window import SidebarWindow
from win32_hooks import Win32HookManager, set_process_app_user_model_id

SINGLE_INSTANCE_KEY = "F9Sidebar_SingleInstance_Lock"
PROJECT_ROOT = Path(__file__).resolve().parent
RUN_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_REG_VALUE_NAME = "F9Sidebar"


def get_startup_command() -> str:
    """Returns the command line targeting the frozen .exe or .venv\\Scripts\\pythonw.exe and main.py."""
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    pythonw_exe = PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe"
    main_py = PROJECT_ROOT / "main.py"
    return f'"{pythonw_exe}" "{main_py}"'


def is_startup_enabled() -> bool:
    """Checks HKCU Run registry key for the F9Sidebar startup entry."""
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_READ
        ) as key:
            val, _ = winreg.QueryValueEx(key, RUN_REG_VALUE_NAME)
            return isinstance(val, str) and bool(val.strip())
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_startup_enabled(enabled: bool) -> bool:
    """Creates or removes the F9Sidebar startup value under HKCU Run."""
    if winreg is None:
        return False
    try:
        if enabled:
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(
                    key, RUN_REG_VALUE_NAME, 0, winreg.REG_SZ, get_startup_command()
                )
        else:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_SET_VALUE
                ) as key:
                    try:
                        winreg.DeleteValue(key, RUN_REG_VALUE_NAME)
                    except FileNotFoundError:
                        pass
            except FileNotFoundError:
                pass
        return True
    except OSError as exc:
        print(f"[Startup] Failed to update Windows startup entry: {exc}")
        return False


def _configure_frozen_stdio_and_logging() -> None:
    """Prevents None-stream print crashes under console=False and logs fatal exceptions."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    if not getattr(sys, "frozen", False):
        return

    orig_hook = sys.excepthook

    def _log_unhandled(exc_type, exc_value, exc_tb) -> None:
        try:
            log_dir = get_app_data_dir() / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "f9sidebar.log"
            if log_file.is_file() and log_file.stat().st_size > 512 * 1024:
                log_file.write_text("", encoding="utf-8")
            stamp = datetime.now().isoformat(timespec="seconds")
            body = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            with log_file.open("a", encoding="utf-8") as fh:
                fh.write(f"[{stamp}] Unhandled exception:\n{body}\n")
        except Exception:
            pass
        try:
            orig_hook(exc_type, exc_value, exc_tb)
        except Exception:
            pass

    sys.excepthook = _log_unhandled


def load_app_icon() -> QIcon:
    """Loads bundled Sunset Glass .ico asset if present, falling back to QtAwesome."""
    ico_path = get_resource_path("assets/f9sidebar.ico")
    if ico_path.is_file():
        icon = QIcon(str(ico_path))
        if not icon.isNull():
            return icon
    return qta.icon("fa5s.columns", color="#89B4FA")


def ensure_single_instance(instance_key: str | None = None) -> QLocalServer | None:
    """If another instance is running, tells it to toggle open and exits."""
    key = (
        instance_key
        or os.environ.get("F9SIDEBAR_INSTANCE_KEY", "").strip()
        or SINGLE_INSTANCE_KEY
    )
    socket = QLocalSocket()
    socket.connectToServer(key)
    if socket.waitForConnected(200):
        socket.write(b"TOGGLE")
        socket.waitForBytesWritten(200)
        socket.disconnectFromServer()
        return None

    QLocalServer.removeServer(key)
    server = QLocalServer()
    server.listen(key)
    return server


def load_startup_profile_db(base_dir: Path | None = None) -> DatabaseManager:
    """Opens DatabaseManager on the last saved global active_profile ('work' or 'personal')."""
    data_dir = base_dir or get_app_data_dir()
    settings_path = data_dir / "settings.json"
    profile = "work"
    if settings_path.is_file():
        try:
            raw = json.loads(settings_path.read_text(encoding="utf-8"))
            saved = str(raw.get("active_profile", "work")).lower().strip()
            if saved in ("work", "personal"):
                profile = saved
        except Exception:
            pass
    return DatabaseManager(profile=profile, base_dir=base_dir)


def launch_initial_sidebar_state(sidebar: SidebarWindow) -> None:
    """Auto-shows and docks the sidebar on its remembered monitor if it was pinned before exit."""
    if getattr(sidebar, "is_pinned", False):
        target_screen = (
            sidebar.get_pinned_screen() if hasattr(sidebar, "get_pinned_screen") else None
        )
        sidebar.show_sidebar(target_screen=target_screen)


def main() -> int:
    _configure_frozen_stdio_and_logging()
    set_process_app_user_model_id("F9Sidebar.App")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)

    app_icon = load_app_icon()
    app.setWindowIcon(app_icon)

    server = ensure_single_instance()
    if server is None:
        print("F9Sidebar is already running. Toggling existing window.")
        return 0

    db = load_startup_profile_db()
    hooks = Win32HookManager()
    sidebar = SidebarWindow(db, hooks)

    # Force native HWND allocation while hidden so RegisterHotKey binds immediately
    hwnd = int(sidebar.winId())
    hooks.install(app, hwnd)

    # Wire global hotkey signals
    hooks.sig_toggle_sidebar.connect(sidebar.toggle_sidebar)
    hooks.sig_switch_panel.connect(sidebar.toggle_panel)
    hooks.sig_toggle_pin.connect(sidebar.toggle_pin)
    hooks.sig_paste_last_clip.connect(sidebar.paste_last_captured_clip)
    hooks.sig_clip_captured.connect(sidebar.on_new_clip_captured)

    # Handle secondary launch requests from single-instance socket
    def on_new_connection():
        client = server.nextPendingConnection()
        if client and client.waitForReadyRead(200):
            sidebar.show_sidebar()
            client.disconnectFromServer()

    server.newConnection.connect(on_new_connection)

    # System Tray Icon & Menu
    tray = QSystemTrayIcon(app_icon, app)
    tray.setToolTip(
        "F9Sidebar (F9: Toggle | Ctrl+F9: Clip | Ctrl+Alt+F9: Paste Last | Shift+F9: Panel | Ctrl+Shift+F9: Pin)"
    )

    menu = QMenu()
    act_toggle = QAction("Toggle Sidebar (F9)", menu)
    act_toggle.triggered.connect(sidebar.toggle_sidebar)
    menu.addAction(act_toggle)

    act_switch = QAction("Switch Panel (Shift+F9)", menu)
    act_switch.triggered.connect(sidebar.toggle_panel)
    menu.addAction(act_switch)

    act_paste_last = QAction("Paste Last Clip (Ctrl+Alt+F9)", menu)
    act_paste_last.triggered.connect(sidebar.paste_last_captured_clip)
    menu.addAction(act_paste_last)

    dock_menu = menu.addMenu("Dock Edge")
    dock_group = QActionGroup(dock_menu)
    dock_group.setExclusive(True)
    dock_edge_actions = {}
    for edge in ("right", "left", "top", "bottom"):
        act_edge = QAction(edge.capitalize(), dock_menu)
        act_edge.setCheckable(True)
        act_edge.setChecked(sidebar.dock_edge == edge)
        act_edge.triggered.connect(lambda _chk=False, e=edge: sidebar.set_dock_edge(e))
        dock_group.addAction(act_edge)
        dock_menu.addAction(act_edge)
        dock_edge_actions[edge] = act_edge

    def on_dock_edge_changed(edge: str):
        act = dock_edge_actions.get(edge)
        if act is not None:
            act.blockSignals(True)
            act.setChecked(True)
            act.blockSignals(False)

    sidebar.sig_dock_edge_changed.connect(on_dock_edge_changed)

    act_appbar = QAction("Pin & AppBar Dock Mode (Ctrl+Shift+F9)", menu)
    act_appbar.setCheckable(True)
    act_appbar.setChecked(sidebar.appbar_enabled)
    act_appbar.toggled.connect(sidebar.set_appbar_mode)

    def on_appbar_toggled(enabled: bool):
        act_appbar.blockSignals(True)
        act_appbar.setChecked(enabled)
        act_appbar.blockSignals(False)

    sidebar.sig_appbar_toggled.connect(on_appbar_toggled)
    menu.addAction(act_appbar)

    act_pause = QAction("Pause Global Hotkeys", menu)
    act_pause.setCheckable(True)

    def on_pause_toggled(paused: bool):
        hooks.hotkeys_paused = paused

    act_pause.toggled.connect(on_pause_toggled)
    menu.addAction(act_pause)

    act_startup = QAction("Launch at Windows Startup", menu)
    act_startup.setCheckable(True)
    act_startup.setChecked(is_startup_enabled())

    def on_startup_toggled(enabled: bool):
        if not set_startup_enabled(enabled):
            act_startup.blockSignals(True)
            act_startup.setChecked(is_startup_enabled())
            act_startup.blockSignals(False)

    act_startup.toggled.connect(on_startup_toggled)
    menu.addAction(act_startup)

    act_settings = QAction("Settings && Backup... (Ctrl+Shift+I)", menu)
    act_settings.triggered.connect(sidebar.open_settings_dialog)
    menu.addAction(act_settings)

    menu.addSeparator()
    act_quit = QAction("Quit F9Sidebar", menu)

    def quit_app():
        sidebar.flush_pending_state()
        hooks.unregister_appbar()
        hooks.unregister_all_hotkeys()
        tray.hide()
        app.quit()

    act_quit.triggered.connect(quit_app)
    menu.addAction(act_quit)

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: sidebar.toggle_sidebar()
        if reason == QSystemTrayIcon.ActivationReason.Trigger
        else None
    )
    tray.show()
    launch_initial_sidebar_state(sidebar)

    print("F9Sidebar running in system tray. Press F9 to toggle, Ctrl+F9 to capture.")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())