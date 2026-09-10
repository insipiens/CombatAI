"""Minimal native Windows notification-area controller."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import threading
from typing import Callable

from .stt import PROJECT_ROOT

WM_APP = 0x8000
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_TRAY = WM_APP + 1
NIM_ADD = 0
NIM_DELETE = 2
NIF_MESSAGE = 1
NIF_ICON = 2
NIF_TIP = 4
MF_STRING = 0
TPM_RIGHTBUTTON = 2
IDI_APPLICATION = 32512
STATUS_ID = 1001
CONFIGURATION_ID = 1002
EXIT_ID = 1003

class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT), ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256), ("uTimeoutOrVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD), ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wintypes.HICON)]

if os.name == "nt":
    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

class WindowsTray:
    """Own a tiny notification-area icon without third-party dependencies."""
    def __init__(self, stop_event: threading.Event, status_provider: Callable[[], tuple[str, str]]) -> None:
        self.stop_event = stop_event
        self.status_provider = status_provider
        self._thread: threading.Thread | None = None
        self._hwnd: int | None = None
        self._callback = None

    def start(self) -> None:
        if os.name != "nt" or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="DCSRadioVoiceControlTray", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self.stop_event.set()
        if os.name == "nt" and self._hwnd:
            ctypes.windll.user32.PostMessageW(self._hwnd, WM_DESTROY, 0, 0)

    def _open_configuration(self) -> None:
        pythonw = PROJECT_ROOT / "runtime" / "pythonw.exe"
        executable = pythonw if pythonw.exists() else sys.executable
        subprocess.Popen([str(executable), "-m", "dcs_radio_voice_control.configuration_ui"], cwd=PROJECT_ROOT)

    def _show_status(self, hwnd: int) -> None:
        state, message = self.status_provider()
        text = state + (f"\n\n{message}" if message else "")
        ctypes.windll.user32.MessageBoxW(hwnd, text, "DCS Radio Voice Control", 0x40)

    def _show_menu(self, hwnd: int) -> None:
        user32 = ctypes.windll.user32
        menu = user32.CreatePopupMenu()
        try:
            user32.AppendMenuW(menu, MF_STRING, STATUS_ID, "Status")
            user32.AppendMenuW(menu, MF_STRING, CONFIGURATION_ID, "Configuration")
            user32.AppendMenuW(menu, MF_STRING, EXIT_ID, "Exit")
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            user32.SetForegroundWindow(hwnd)
            user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON, point.x, point.y, 0, hwnd, None)
        finally:
            user32.DestroyMenu(menu)

    def _run(self) -> None:
        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        kernel32 = ctypes.windll.kernel32
        class_name = "DCSRadioVoiceControlTrayWindow"
        @WNDPROC
        def window_proc(hwnd, message, wparam, lparam):
            if message == WM_TRAY:
                if lparam == WM_RBUTTONUP:
                    self._show_menu(hwnd); return 0
                if lparam == WM_LBUTTONDBLCLK:
                    self._open_configuration(); return 0
            if message == WM_COMMAND:
                command = int(wparam) & 0xFFFF
                if command == STATUS_ID:
                    self._show_status(hwnd)
                elif command == CONFIGURATION_ID:
                    self._open_configuration()
                elif command == EXIT_ID:
                    self.stop_event.set(); user32.DestroyWindow(hwnd)
                return 0
            if message == WM_DESTROY:
                user32.PostQuitMessage(0); return 0
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)
        self._callback = window_proc
        instance = kernel32.GetModuleHandleW(None)
        window_class = WNDCLASSW()
        window_class.lpfnWndProc = window_proc
        window_class.hInstance = instance
        window_class.lpszClassName = class_name
        atom = user32.RegisterClassW(ctypes.byref(window_class))
        if not atom and ctypes.get_last_error() != 1410:
            return
        hwnd = user32.CreateWindowExW(0, class_name, class_name, 0, 0, 0, 0, 0, 0, 0, instance, None)
        if not hwnd:
            return
        self._hwnd = hwnd
        icon = user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
        notify = NOTIFYICONDATAW()
        notify.cbSize = ctypes.sizeof(notify)
        notify.hWnd = hwnd
        notify.uID = 1
        notify.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        notify.uCallbackMessage = WM_TRAY
        notify.hIcon = icon
        notify.szTip = "DCS Radio Voice Control"
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(notify)):
            user32.DestroyWindow(hwnd); return
        try:
            message = wintypes.MSG()
            while not self.stop_event.is_set() and user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(notify))
            if self._hwnd:
                user32.DestroyWindow(self._hwnd)
            self._hwnd = None
