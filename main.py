import json
from pathlib import Path
import sys

try:
    import winreg
except ImportError:  # pragma: no cover - Windows only
    winreg = None

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
import qtawesome as qta

from database import DatabaseManager, get_app_data_dir
from ui.sidebar_window import SidebarWindow
from win32_hooks import Win32HookManager

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


def ensure_single_instance() -> QLocalServer | None:
    """If another instance is running, tells it to toggle open and exits."""
    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_KEY)
    if socket.waitForConnected(200):
        socket.write(b"TOGGLE")
        socket.waitForBytesWritten(200)
        socket.disconnectFromServer()
        return None

    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
    server = QLocalServer()
    server.listen(SINGLE_INSTANCE_KEY)
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
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

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
    tray = QSystemTrayIcon(qta.icon("fa5s.columns", color="#89B4FA"), app)
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