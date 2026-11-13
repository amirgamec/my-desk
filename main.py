"""
Glass Desktop Widget - customizable + animated version
Requirements:
    pip install PySide6 qtawesome jdatetime

Folder structure:
    main.py
    config.json            (created automatically - your pinned apps)
    assets/
        wallpaper.jpg
        wallpapers/        (optional: more images; change with the sidebar button or the W key)
        character.png
        cards/1.png, 2.png, 3.png
        music/
        fonts/VAZIR-MEDIUM.TTF

Run:
    python main.py                      opens fullscreen (F11 or the profile panel to change)
    python main.py --windowed           opens in a window
    python main.py --create-shortcut    creates a Desktop shortcut (also in the profile panel)

Keys:  F11 fullscreen | W wallpaper | S system | T focus timer | P profile | R running apps
       Ctrl+S search | Ctrl+1..7 dock apps | Ctrl+X back | Ctrl+Q quit

How to customize:
    * "+" button at the end of the dock / sidebar  -> pick an installed app or type a website
    * Right-click a pinned button                  -> Move / Remove
    * Running Apps drawer -> pin icon on a card    -> pin that app to the dock
    * Right-click empty space                      -> Reset dock & sidebar
"""

import os
import sys
import re
import json
import copy
import glob
import math
import shutil
import socket
import time
import ast
import hashlib
import secrets
import urllib.request
import atexit
import ctypes
import subprocess
import webbrowser
from pathlib import Path
from ctypes import wintypes
from urllib.parse import urlparse, quote

import qtawesome as qta
import jdatetime

from PySide6.QtCore import (
    Qt, QSize, QRect, QRectF, QPoint, QPointF, QTimer, QUrl, QDateTime,
    QLocale, QPropertyAnimation, QEasingCurve, QFileInfo, Property,
    QVariantAnimation, QAbstractAnimation, QParallelAnimationGroup,
    QObject, QEvent, Signal, QRunnable, QThreadPool
)
from PySide6.QtGui import (
    QPainter, QPainterPath, QPixmap, QColor, QFont, QImage,
    QLinearGradient, QIcon, QPen, QBrush, QFontDatabase, QCursor,
    QFontMetrics, QPolygonF
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QHBoxLayout,
    QVBoxLayout, QGridLayout, QSlider, QMenu, QGraphicsScene,
    QDialog, QLineEdit, QListWidget, QListWidgetItem,
    QGraphicsPixmapItem, QGraphicsBlurEffect, QGraphicsOpacityEffect,
    QToolButton, QScrollArea, QFrame, QFileIconProvider, QStyle, QFileDialog,
    QAbstractButton
)

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
    HAS_MEDIA = True
except Exception:
    HAS_MEDIA = False


# ----------------------------- Settings -----------------------------

NAME = "User"
CHARACTER_X = 0.5
STAY_ON_DESKTOP = True
BLUR_RADIUS = 28

APP_VERSION = "1.0.2"
# Raw link to version.json in your GitHub repo, e.g.
# https://raw.githubusercontent.com/YOUR_NAME/glass-desktop/main/version.json
UPDATE_URL = "https://raw.githubusercontent.com/amirgamec/my-desk/main/version.json"
# Default friends database (Firebase Realtime Database link). Leave empty to type it in the app.
FIREBASE_URL = ""

FROZEN = bool(getattr(sys, "frozen", False))      # True when built into an .exe (PyInstaller)
BASE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
ASSETS = BASE / "assets"
CONFIG_PATH = BASE / "config.json"
APP_ICON = ASSETS / "icon.ico"
SHORTCUT_NAME = "Glass Desktop.lnk"
WALLPAPER_DIR = ASSETS / "wallpapers"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
FOCUS_MINUTES = 25
WALLPAPER = ASSETS / "wallpaper.jpg"
CHARACTER = ASSETS / "character.png"
MUSIC_DIR = ASSETS / "music"
CARD_IMAGES = [
    ASSETS / "cards" / "1.png",
    ASSETS / "cards" / "2.png",
    ASSETS / "cards" / "3.png",
]

# Default pinned items (used the first time, or after "Reset").
# "qta": qtawesome icon name   "exe": optional exe path (glob allowed) launched first
SIDEBAR_DEFAULT = [

]

DOCK_DEFAULT = [

]

MENU_QSS = """
QMenu { background:rgba(18,18,18,245); color:white; border:1px solid rgba(255,255,255,40);
        border-radius:14px; padding:6px; }
QMenu::item { padding:8px 26px 8px 16px; border-radius:8px; }
QMenu::item:selected { background:rgba(255,255,255,32); }
QMenu::item:disabled { color:rgba(255,255,255,70); }
QMenu::separator { height:1px; background:rgba(255,255,255,30); margin:5px 8px; }
"""


# ----------------------------- Config -----------------------------

def load_config():
    cfg = {"sidebar": copy.deepcopy(SIDEBAR_DEFAULT), "dock": copy.deepcopy(DOCK_DEFAULT),
           "wallpaper": None, "name": NAME, "status": "Feeling productive", "avatar": None,
           "fullscreen": True, "tools_visible": False, "volume": 60, "muted": False,
           "hide_taskbar": True, "taskbar_hidden": False,
           "friend_db_url": "", "friend_code": "", "update_url": "", "app_usage": {},
           "focus_done": {"date": "", "count": 0}}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        for key in ("sidebar", "dock"):
            items = data.get(key)
            if isinstance(items, list):
                cfg[key] = [i for i in items
                            if isinstance(i, dict) and i.get("label") and i.get("target")]
        for key in ("wallpaper", "name", "status", "avatar", "friend_db_url", "friend_code", "update_url"):
            if isinstance(data.get(key), str):
                cfg[key] = data[key]
        for key in ("fullscreen", "tools_visible", "muted", "hide_taskbar", "taskbar_hidden"):
            if isinstance(data.get(key), bool):
                cfg[key] = data[key]
        if isinstance(data.get("volume"), int):
            cfg["volume"] = max(0, min(100, data["volume"]))
        usage = data.get("app_usage")
        if isinstance(usage, dict):
            cfg["app_usage"] = {str(k): v for k, v in usage.items() if isinstance(v, int)}
        done = data.get("focus_done")
        if isinstance(done, dict) and isinstance(done.get("count"), int):
            cfg["focus_done"] = {"date": str(done.get("date", "")), "count": done["count"]}
    except FileNotFoundError:
        pass
    except Exception as exc:
        print("Config load failed:", exc)
    return cfg


def save_config(cfg):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print("Config save failed:", exc)


# ----------------------------- Helpers -----------------------------

def find_exe(pattern):
    if not pattern:
        return None
    for path in glob.glob(os.path.expandvars(pattern)):
        if os.path.isfile(path):
            return path
    return None


def launch(target: str, exe: str = None):
    try:
        path = find_exe(exe)
        if path:
            if sys.platform.startswith("win"):
                os.startfile(path)
            else:
                subprocess.Popen([path])
            return

        if not target:
            return
        if target.startswith(("http://", "https://")):
            webbrowser.open(target)
        elif target.lower().startswith("shell:"):
            subprocess.Popen(["explorer.exe", target])
        elif sys.platform.startswith("win"):
            expanded = os.path.expandvars(target)
            if os.path.exists(expanded):
                os.startfile(expanded)
            else:
                subprocess.Popen(target, shell=True)
        else:
            subprocess.Popen(target, shell=True)
    except Exception as exc:
        print("Launch failed:", target, exc)


_ICON_PROVIDER = None


def file_icon(path):
    global _ICON_PROVIDER
    if _ICON_PROVIDER is None:
        _ICON_PROVIDER = QFileIconProvider()
    return _ICON_PROVIDER.icon(QFileInfo(path))


def make_icon(item, dark):
    color = "#FFFFFF" if dark else "#111111"
    exe = find_exe(item.get("exe"))
    if exe:
        return file_icon(exe)
    name = item.get("qta")
    if name:
        try:
            return qta.icon(name, color=color)
        except Exception:
            pass
    path = os.path.expandvars(item.get("target", ""))
    if path and os.path.exists(path):
        return file_icon(path)
    return qta.icon("fa5s.globe", color=color)


def looks_like_url(text):
    t = text.strip()
    if not t or " " in t:
        return False
    if "://" in t:
        return True
    return "." in t.strip(".") and len(t) > 3


def styled_menu(parent):
    menu = QMenu(parent)
    menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WA_TranslucentBackground, True)
    menu.setStyleSheet(MENU_QSS)
    return menu


def wallpaper_list():
    paths = []
    if WALLPAPER.exists():
        paths.append(WALLPAPER)
    if WALLPAPER_DIR.is_dir():
        paths += sorted(p for p in WALLPAPER_DIR.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    return paths


def item_hint(item):
    target = item.get("target", "")
    if target.startswith(("http://", "https://")):
        return urlparse(target).netloc.replace("www.", "")
    return "App"


class GlassTip(QWidget):
    """Animated tooltip: dark glass bubble with an arrow, a title and an optional hint line."""
    ARROW = 7

    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.title = ""
        self.hint = ""
        self.side = "top"
        self._pending = None
        self._f_title = QFont()
        self._f_hint = QFont()
        self._th = 0
        self._hh = 0

        self.fade = QPropertyAnimation(self, b"windowOpacity", self)
        self.fade.finished.connect(self._after_fade)      # connected once, guarded by _hiding
        self._hiding = False
        self.slide = QPropertyAnimation(self, b"pos", self)

        self.delay = QTimer(self)
        self.delay.setSingleShot(True)
        self.delay.timeout.connect(self._show_pending)
        self.life = QTimer(self)
        self.life.setSingleShot(True)
        self.life.timeout.connect(self.cancel)

    def request(self, title, widget, side="top", hint=""):
        """Show after a short hover delay (instantly when moving between buttons)."""
        self._pending = (title, widget, side, hint)
        self.delay.stop()
        if self.isVisible():
            self._show_pending()
        else:
            self.delay.start(320)

    def flash(self, title, widget, side="top", hint="", ms=2200):
        self._pending = (title, widget, side, hint)
        self.delay.stop()
        self._show_pending()
        self.life.start(ms)

    def _show_pending(self):
        if not self._pending:
            return
        try:
            self._present(*self._pending)
        except RuntimeError:
            pass  # the widget was deleted

    def _disconnect_fade(self):
        try:
            self.fade.finished.disconnect()
        except Exception:
            pass

    def _present(self, title, widget, side, hint):
        self.title, self.hint, self.side = title, hint, side

        self._f_title = QFont(QApplication.font())
        self._f_title.setPixelSize(13)
        self._f_title.setBold(True)
        self._f_hint = QFont(QApplication.font())
        self._f_hint.setPixelSize(11)
        fm_t, fm_h = QFontMetrics(self._f_title), QFontMetrics(self._f_hint)
        self._th, self._hh = fm_t.height(), fm_h.height()

        text_w = max(fm_t.horizontalAdvance(title), fm_h.horizontalAdvance(hint) if hint else 0)
        body_w = text_w + 30
        body_h = self._th + 16 + (self._hh + 2 if hint else 0)
        a = self.ARROW
        if side in ("top", "bottom"):
            self.resize(body_w, body_h + a)
        else:
            self.resize(body_w + a, body_h)
        w, h = self.width(), self.height()

        top_left = widget.mapToGlobal(QPoint(0, 0))
        center = QPoint(top_left.x() + widget.width() // 2, top_left.y() + widget.height() // 2)
        base = getattr(widget, "base", None)           # IconButton: size of the visible circle
        half_h = (base * 0.56 + 4) if base else widget.height() / 2
        half_w = (base * 0.56) if base else widget.width() / 2

        if side == "top":
            tx, ty = center.x() - w // 2, int(center.y() - half_h - h - 2)
        elif side == "bottom":
            tx, ty = center.x() - w // 2, int(center.y() + half_h + 2)
        else:  # right
            tx, ty = int(center.x() + half_w + 4), center.y() - h // 2

        geo = widget.screen().availableGeometry()
        tx = max(geo.left() + 6, min(tx, geo.right() - w - 6))
        ty = max(geo.top() + 6, min(ty, geo.bottom() - h - 6))
        target = QPoint(tx, ty)

        was_visible = self.isVisible() and self.windowOpacity() > 0.4
        self.fade.stop()
        self._hiding = False
        self.slide.stop()

        if was_visible:
            self.slide.setStartValue(self.pos())
            self.slide.setDuration(170)
            self.slide.setEasingCurve(QEasingCurve.OutCubic)
        else:
            offset = {"top": QPoint(0, 8), "bottom": QPoint(0, -8), "right": QPoint(-8, 0)}[side]
            self.move(target + offset)
            self.setWindowOpacity(0.0)
            self.show()
            self.slide.setStartValue(target + offset)
            self.slide.setDuration(260)
            self.slide.setEasingCurve(QEasingCurve.OutBack)
        self.slide.setEndValue(target)
        self.slide.start()

        self.fade.setDuration(150)
        self.fade.setStartValue(self.windowOpacity())
        self.fade.setEndValue(1.0)
        self.fade.start()
        self.update()

    def cancel(self):
        self._pending = None
        self.delay.stop()
        self.life.stop()
        if not self.isVisible():
            return
        self.fade.stop()
        self._hiding = True
        self.fade.setDuration(110)
        self.fade.setStartValue(self.windowOpacity())
        self.fade.setEndValue(0.0)
        self.fade.start()

    def _after_fade(self):
        if self._hiding and self.windowOpacity() <= 0.01:
            self.hide()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        a = self.ARROW
        w, h = self.width(), self.height()

        if self.side == "top":
            body = QRectF(0.5, 0.5, w - 1, h - a - 1)
            tri = [QPointF(w / 2 - a, body.bottom() - 0.5), QPointF(w / 2 + a, body.bottom() - 0.5),
                   QPointF(w / 2, h - 0.5)]
        elif self.side == "bottom":
            body = QRectF(0.5, a + 0.5, w - 1, h - a - 1)
            tri = [QPointF(w / 2 - a, body.top() + 0.5), QPointF(w / 2 + a, body.top() + 0.5),
                   QPointF(w / 2, 0.5)]
        else:
            body = QRectF(a + 0.5, 0.5, w - a - 1, h - 1)
            tri = [QPointF(body.left() + 0.5, h / 2 - a), QPointF(body.left() + 0.5, h / 2 + a),
                   QPointF(0.5, h / 2)]

        path = QPainterPath()
        path.addRoundedRect(body, 11, 11)
        arrow = QPainterPath()
        arrow.addPolygon(QPolygonF(tri))
        arrow.closeSubpath()
        path = path.united(arrow)

        p.setBrush(QColor(18, 18, 18, 240))
        p.setPen(QPen(QColor(255, 255, 255, 50), 1))
        p.drawPath(path)

        inner = body.adjusted(14, 8, -14, -8)
        p.setFont(self._f_title)
        p.setPen(QColor("white"))
        p.drawText(QRectF(inner.x(), inner.y(), inner.width(), self._th),
                   Qt.AlignHCenter | Qt.AlignVCenter, self.title)
        if self.hint:
            p.setFont(self._f_hint)
            p.setPen(QColor(255, 255, 255, 150))
            p.drawText(QRectF(inner.x(), inner.y() + self._th + 2, inner.width(), self._hh),
                       Qt.AlignHCenter | Qt.AlignVCenter, self.hint)


_TIP = None


def tip():
    global _TIP
    if _TIP is None:
        _TIP = GlassTip()
    return _TIP


def avatar_pixmap(path, size, name):
    """Round avatar: the user's image, or a gradient circle with the first letter of the name."""
    dpr = 2
    side = size * dpr
    px = QPixmap(side, side)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addEllipse(QRectF(0, 0, side, side))
    p.setClipPath(clip)

    src = QPixmap(path) if path and os.path.isfile(path) else QPixmap()
    if src.isNull():
        grad = QLinearGradient(0, 0, side, side)
        grad.setColorAt(0, QColor("#ff9a9e"))
        grad.setColorAt(1, QColor("#a1c4fd"))
        p.fillRect(px.rect(), QBrush(grad))
        font = QFont(QApplication.font())
        font.setPixelSize(int(side * 0.46))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("white"))
        letter = ((name or "?").strip()[:1] or "?").upper()
        p.drawText(QRectF(0, 0, side, side), Qt.AlignCenter, letter)
    else:
        scaled = src.scaled(side, side, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        p.drawPixmap((side - scaled.width()) // 2, (side - scaled.height()) // 2, scaled)
    p.end()
    px.setDevicePixelRatio(dpr)
    return px


# ---- desktop shortcut / startup (Windows) ----

def ensure_app_icon():
    """assets/icon.ico - generated once if you did not provide your own."""
    if APP_ICON.exists():
        return APP_ICON
    try:
        APP_ICON.parent.mkdir(parents=True, exist_ok=True)
        s = 256
        img = QImage(s, s, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, s, s)
        grad.setColorAt(0, QColor("#a1c4fd"))
        grad.setColorAt(1, QColor("#fbc2eb"))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(QRectF(8, 8, s - 16, s - 16), 58, 58)
        p.setBrush(QColor(255, 255, 255, 80))
        p.drawRoundedRect(QRectF(46, 46, s - 92, s - 92), 34, 34)
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawEllipse(QPointF(s / 2, s / 2), 28, 28)
        p.end()
        if img.save(str(APP_ICON)):
            return APP_ICON
    except Exception as exc:
        print("Icon generation failed:", exc)
    return None


def _ps_quote(text):
    return "'" + str(text).replace("'", "''") + "'"


def create_shortcut(where="Desktop"):
    """Create a .lnk that starts this widget. where = 'Desktop' or 'Startup'.
    Returns the shortcut path, or None (not Windows / failed)."""
    if os.name != "nt":
        return None
    exe = Path(sys.executable)
    if FROZEN:                                       # built .exe: the exe itself is the target
        target, script, args = exe, exe, ""
    else:
        pythonw = exe.with_name("pythonw.exe")       # no console window
        target = pythonw if pythonw.exists() else exe
        script = Path(__file__).resolve()
        args = '"%s"' % script
    icon = ensure_app_icon()
    folder = "[Environment]::GetFolderPath('%s')" % ("Desktop" if where == "Desktop" else "Startup")

    ps = (
        f"$dir={folder};"
        f"$lnk=Join-Path $dir {_ps_quote(SHORTCUT_NAME)};"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($lnk);"
        f"$s.TargetPath={_ps_quote(target)};"
        f"$s.Arguments={_ps_quote(args)};"
        f"$s.WorkingDirectory={_ps_quote(script.parent)};"
        "$s.Description='Glass Desktop Widget';"
        + (f"$s.IconLocation={_ps_quote(icon)};" if icon else "")
        + "$s.Save();Write-Output $lnk"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True, text=True, timeout=25, creationflags=0x08000000
        )
        out = result.stdout.strip()
        return out if result.returncode == 0 and out else None
    except Exception as exc:
        print("Shortcut failed:", exc)
        return None


def startup_shortcut_path():
    folder = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")
    return Path(folder) / SHORTCUT_NAME


def startup_enabled():
    return os.name == "nt" and startup_shortcut_path().exists()


def set_startup(enabled):
    """Returns True when the requested state was reached."""
    if os.name != "nt":
        return False
    try:
        if enabled:
            return create_shortcut("Startup") is not None
        path = startup_shortcut_path()
        if path.exists():
            path.unlink()
        return True
    except Exception as exc:
        print("Startup toggle failed:", exc)
        return False


# ---- system statistics (no extra packages needed on Windows) ----

class _FILETIME(ctypes.Structure):
    _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32),
                ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64)]


class _POWERSTATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_uint8), ("BatteryFlag", ctypes.c_uint8),
                ("BatteryLifePercent", ctypes.c_uint8), ("SystemStatusFlag", ctypes.c_uint8),
                ("BatteryLifeTime", ctypes.c_uint32), ("BatteryFullLifeTime", ctypes.c_uint32)]


class SysStats:
    """sample() -> dict(cpu, ram, ram_used, ram_total, disk, disk_free, battery, uptime)."""

    def __init__(self):
        self._last = None
        self.psutil = None
        if os.name != "nt":
            try:
                import psutil
                self.psutil = psutil
                psutil.cpu_percent(None)
            except Exception:
                pass
        drive = os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"
        self.disk_path = drive

    @staticmethod
    def _ft(value):
        return (value.hi << 32) | value.lo

    def _cpu_windows(self):
        idle, kernel, user = _FILETIME(), _FILETIME(), _FILETIME()
        ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
        now = (self._ft(idle), self._ft(kernel), self._ft(user))
        last, self._last = self._last, now
        if last is None:
            return 0.0
        d_idle, d_kernel, d_user = (now[i] - last[i] for i in range(3))
        total = d_kernel + d_user                     # kernel time already includes idle
        return max(0.0, min(100.0, (total - d_idle) * 100.0 / total)) if total > 0 else 0.0

    def sample(self):
        data = {"cpu": 0.0, "ram": 0.0, "ram_used": 0.0, "ram_total": 0.0,
                "disk": 0.0, "disk_free": 0.0, "battery": None, "uptime": 0}
        gb = 1024 ** 3
        try:
            if os.name == "nt":
                data["cpu"] = self._cpu_windows()
                mem = _MEMORYSTATUSEX()
                mem.dwLength = ctypes.sizeof(mem)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
                data["ram"] = float(mem.dwMemoryLoad)
                data["ram_total"] = mem.ullTotalPhys / gb
                data["ram_used"] = (mem.ullTotalPhys - mem.ullAvailPhys) / gb

                power = _POWERSTATUS()
                if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power)):
                    if power.BatteryFlag != 128 and power.BatteryLifePercent <= 100:
                        data["battery"] = (int(power.BatteryLifePercent), power.ACLineStatus == 1)

                kernel32 = ctypes.windll.kernel32
                kernel32.GetTickCount64.restype = ctypes.c_uint64
                data["uptime"] = int(kernel32.GetTickCount64() // 1000)
            elif self.psutil:
                ps = self.psutil
                data["cpu"] = ps.cpu_percent(None)
                vm = ps.virtual_memory()
                data.update(ram=vm.percent, ram_total=vm.total / gb, ram_used=(vm.total - vm.available) / gb)
                battery = ps.sensors_battery()
                if battery:
                    data["battery"] = (int(battery.percent), bool(battery.power_plugged))
                data["uptime"] = int(time.time() - ps.boot_time())

            usage = shutil.disk_usage(self.disk_path)
            data["disk"] = usage.used * 100.0 / usage.total
            data["disk_free"] = usage.free / gb
        except Exception as exc:
            print("Stats error:", exc)
        return data


# ---- network (Wi-Fi name / signal, internet reachability, battery) ----

def read_network():
    """Runs in a worker thread (it calls netsh and opens sockets, so it must not block the UI)."""
    info = {"kind": "none", "ssid": "", "signal": 0, "online": False, "ping": None, "battery": None}

    if os.name == "nt":
        try:
            raw = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True,
                                 timeout=5, creationflags=0x08000000).stdout
            try:
                text = raw.decode("cp%d" % ctypes.windll.kernel32.GetOEMCP(), "replace")
            except Exception:
                text = raw.decode("utf-8", "replace")
            ssid = re.search(r"^\s*SSID\s*:\s*(.+?)\s*$", text, re.M)   # BSSID lines do not match
            if ssid and ssid.group(1):
                info["kind"] = "wifi"
                info["ssid"] = ssid.group(1)
                signal = re.search(r"(\d{1,3})\s*%", text)              # the only % line is the signal
                info["signal"] = min(100, int(signal.group(1))) if signal else 0
        except Exception:
            pass

    # Is the internet really reachable? (Wi-Fi can be connected with no internet.)
    for host, port in (("1.1.1.1", 443), ("8.8.8.8", 53), ("9.9.9.9", 53)):
        try:
            start = time.perf_counter()
            with socket.create_connection((host, port), timeout=1.3):
                info["ping"] = int((time.perf_counter() - start) * 1000)
            info["online"] = True
            break
        except OSError:
            continue

    if info["kind"] == "none" and info["online"]:
        info["kind"] = "wired"

    try:
        info["battery"] = SysStats().sample()["battery"]
    except Exception:
        pass
    return info


class _NetSignals(QObject):
    done = Signal(dict)


class NetWorker(QRunnable):
    def __init__(self):
        super().__init__()
        self.setAutoDelete(False)          # MainWindow keeps the reference until the result arrives
        self.signals = _NetSignals()

    def run(self):
        try:
            info = read_network()
        except Exception as exc:
            print("Network check failed:", exc)
            info = {"kind": "none", "ssid": "", "signal": 0, "online": False,
                    "ping": None, "battery": None}
        self.signals.done.emit(info)


# ---- generic background job (network / PowerShell work must never block the UI) ----

_JOBS = set()
_RECEIVER = None


class _JobSignals(QObject):
    done = Signal(object, object, object)


class Job(QRunnable):
    def __init__(self, fn, callback, args):
        super().__init__()
        self.setAutoDelete(False)
        self.fn, self.callback, self.args = fn, callback, args
        self.signals = _JobSignals()

    def run(self):
        try:
            result, error = self.fn(*self.args), None
        except Exception as exc:
            result, error = None, exc
        self.signals.done.emit(self, result, error)


class _JobReceiver(QObject):
    """Lives in the main thread, so callbacks always run there."""
    def on_done(self, job, result, error):
        _JOBS.discard(job)
        if job.callback:
            try:
                job.callback(result, error)
            except Exception as exc:
                print("Job callback failed:", exc)


def run_job(fn, callback=None, *args):
    """Run fn(*args) in a thread, then callback(result, error) in the main thread."""
    global _RECEIVER
    if _RECEIVER is None:
        _RECEIVER = _JobReceiver()
    job = Job(fn, callback, args)
    job.signals.done.connect(_RECEIVER.on_done)
    _JOBS.add(job)
    QThreadPool.globalInstance().start(job)
    return job


def blur_pixmap(pm: QPixmap, radius: float) -> QPixmap:
    """Fast blur: a big blur looks the same on a small copy, so blur at 1/4 size and scale back."""
    if pm.isNull() or radius <= 0:
        return QPixmap(pm)
    scale = 4 if radius >= 16 else (2 if radius >= 8 else 1)
    if scale == 1:
        return _blur_core(pm, radius)
    small = pm.scaled(max(1, pm.width() // scale), max(1, pm.height() // scale),
                      Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    blurred = _blur_core(small, radius / scale)
    return blurred.scaled(pm.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def _blur_core(pm: QPixmap, radius: float) -> QPixmap:
    """Blur a pixmap without the transparent/sharp fringe at the edges."""
    if pm.isNull() or radius <= 0:
        return QPixmap(pm)

    pad = int(radius * 2) + 2
    w, h = pm.width(), pm.height()

    padded = QPixmap(w + 2 * pad, h + 2 * pad)
    padded.fill(Qt.transparent)
    p = QPainter(padded)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.drawPixmap(QRect(0, 0, padded.width(), padded.height()), pm)
    p.drawPixmap(pad, pad, pm)
    p.end()

    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(padded)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius)
    item.setGraphicsEffect(effect)
    scene.addItem(item)

    result = QImage(padded.size(), QImage.Format_ARGB32_Premultiplied)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    scene.render(painter, QRectF(result.rect()), QRectF(padded.rect()))
    painter.end()
    return QPixmap.fromImage(result.copy(pad, pad, w, h))


def fade_slide(widget, dx=0, dy=0, delay=0, duration=600, curve=QEasingCurve.OutCubic,
               fade=True):
    """Fade a widget in while sliding it from (dx, dy) to where its layout put it.

    The widget is made invisible immediately; the real position is read when the
    animation starts, so it works for widgets that live inside layouts.
    fade=False only slides (used for panels that contain other animated widgets:
    nested opacity effects are not allowed to overlap in Qt).
    """
    if widget is None:
        return

    effect = None
    if fade:
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)

    def start():
        try:
            end = QPoint(widget.pos())
            begin = end + QPoint(dx, dy)
            widget.move(begin)

            group = QParallelAnimationGroup(widget)
            move = QPropertyAnimation(widget, b"pos")
            move.setDuration(duration)
            move.setEasingCurve(curve)
            move.setStartValue(begin)
            move.setEndValue(end)
            group.addAnimation(move)
            if effect is not None:
                fader = QPropertyAnimation(effect, b"opacity")
                fader.setDuration(int(duration * 0.8))
                fader.setStartValue(0.0)
                fader.setEndValue(1.0)
                group.addAnimation(fader)

            def finish():
                try:
                    if effect is not None:
                        widget.setGraphicsEffect(None)
                    parent = widget.parentWidget()
                    if parent is not None and parent.layout() is not None:
                        parent.layout().invalidate()
                        parent.layout().activate()
                except RuntimeError:
                    pass

            group.finished.connect(finish)
            group.finished.connect(group.deleteLater)
            group.start()
        except RuntimeError:
            pass  # widget was deleted before the animation started

    QTimer.singleShot(max(30, delay), start)


# ---- Win32 helpers (typed once, so 64-bit handles are safe) ----

_USER32 = None


def user32_api():
    global _USER32
    if _USER32 is None:
        u = ctypes.WinDLL("user32", use_last_error=True)
        H = wintypes.HWND
        u.IsWindowVisible.argtypes = [H]
        u.IsWindowVisible.restype = wintypes.BOOL
        u.GetWindowTextLengthW.argtypes = [H]
        u.GetWindowTextLengthW.restype = ctypes.c_int
        u.GetWindowTextW.argtypes = [H, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowTextW.restype = ctypes.c_int
        u.GetWindowThreadProcessId.argtypes = [H, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.GetWindow.argtypes = [H, wintypes.UINT]
        u.GetWindow.restype = H
        u.GetWindowLongW.argtypes = [H, ctypes.c_int]
        u.GetWindowLongW.restype = ctypes.c_long
        u.IsIconic.argtypes = [H]
        u.IsIconic.restype = wintypes.BOOL
        u.ShowWindow.argtypes = [H, ctypes.c_int]
        u.ShowWindow.restype = wintypes.BOOL
        u.SetForegroundWindow.argtypes = [H]
        u.SetForegroundWindow.restype = wintypes.BOOL
        u.PostMessageW.argtypes = [H, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.PostMessageW.restype = wintypes.BOOL
        u.FindWindowExW.argtypes = [H, H, wintypes.LPCWSTR, wintypes.LPCWSTR]
        u.FindWindowExW.restype = H
        _USER32 = u
    return _USER32


def set_taskbar_visible(visible):
    """Show / hide the Windows taskbar (all monitors). No-op on other systems."""
    if os.name != "nt":
        return
    try:
        u = user32_api()
        for cls in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            handle = u.FindWindowExW(None, None, cls, None)
            while handle:
                u.ShowWindow(handle, 5 if visible else 0)      # SW_SHOW / SW_HIDE
                handle = u.FindWindowExW(None, handle, cls, None)
    except Exception as exc:
        print("Taskbar toggle failed:", exc)


# ----------------------------- Glass panels -----------------------------

class Glass(QWidget):
    def __init__(self, parent=None, radius=30, alpha=55):
        super().__init__(parent)
        self.radius = radius
        self.alpha = alpha
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._intro = 1.0
        self._intro_anim = QPropertyAnimation(self, b"introT", self)

    def _get_intro(self): return self._intro
    def _set_intro(self, v): self._intro = v; self.update()
    introT = Property(float, _get_intro, _set_intro)

    def intro(self, delay=0, duration=700):
        """Fade only the glass background in (the children keep their own animations)."""
        def go():
            try:
                self._intro_anim.stop()
                self._intro_anim.setDuration(duration)
                self._intro_anim.setEasingCurve(QEasingCurve.OutCubic)
                self._intro_anim.setStartValue(self._intro)
                self._intro_anim.setEndValue(1.0)
                self._intro_anim.start()
            except RuntimeError:
                pass
        QTimer.singleShot(delay, go)

    def paintEvent(self, event):
        win = self.window()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(self._intro)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)
        painter.setClipPath(path)

        blurred = getattr(win, "wall_blur", None)
        if blurred is not None and not blurred.isNull():
            offset = self.mapTo(win, QPoint(0, 0))
            old = getattr(win, "wall_blur_old", None)
            fade = getattr(win, "fade_t", 1.0)
            if old is not None and fade < 1.0:       # wallpaper cross-fade
                painter.drawPixmap(-offset, old)
                painter.setOpacity(fade)
                painter.drawPixmap(-offset, blurred)
                painter.setOpacity(1.0)
            else:
                painter.drawPixmap(-offset, blurred)

        painter.fillPath(path, QColor(255, 255, 255, self.alpha))
        painter.setClipping(False)
        painter.setPen(QPen(QColor(255, 255, 255, 120), 1.2))
        painter.drawPath(path)


class IconButton(QPushButton):
    """Round animated button: hover lift + glow, press squash, click pulse, pop-in."""
    PROPS = {"hoverT": "_hover", "pressT": "_press", "appearT": "_appear", "pulseT": "_pulse"}

    def __init__(self, label, icon, size, dark, pad=8, on_click=None, ghost=False,
                 hint="", tip_side="top"):
        super().__init__()
        self.base = size
        self.pad = pad
        self.icon_obj = icon
        self.dark = dark
        self.ghost = ghost
        self.context_cb = None
        self.overlay_cb = None      # optional extra painting: cb(painter, center, radius, scale)
        self.hide_icon = False
        self._hover = 0.0
        self._press = 0.0
        self._pulse = 0.0
        self._appear = 0.0
        self._anims = {}

        self.setFixedSize(size + 2 * pad, size + 2 * pad)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.label = label
        self.hint = hint
        self.tip_side = tip_side
        if on_click:
            self.clicked.connect(on_click)

    # ---- animated properties ----
    def _get_hover(self): return self._hover
    def _set_hover(self, v): self._hover = v; self.update()
    hoverT = Property(float, _get_hover, _set_hover)

    def _get_press(self): return self._press
    def _set_press(self, v): self._press = v; self.update()
    pressT = Property(float, _get_press, _set_press)

    def _get_appear(self): return self._appear
    def _set_appear(self, v): self._appear = v; self.update()
    appearT = Property(float, _get_appear, _set_appear)

    def _get_pulse(self): return self._pulse
    def _set_pulse(self, v): self._pulse = v; self.update()
    pulseT = Property(float, _get_pulse, _set_pulse)

    def _go(self, prop, end, duration=220, curve=QEasingCurve.OutCubic, start=None):
        anim = self._anims.get(prop)
        if anim is None:
            anim = QPropertyAnimation(self, prop.encode(), self)
            self._anims[prop] = anim
        anim.stop()
        anim.setDuration(duration)
        anim.setEasingCurve(curve)
        anim.setStartValue(getattr(self, self.PROPS[prop]) if start is None else start)
        anim.setEndValue(end)
        anim.start()
        return anim

    def _guard(self, fn):
        try:
            fn()
        except RuntimeError:
            pass

    def set_appear(self, value):
        self._appear = value
        self.update()

    def pulse(self):
        self._go("pulseT", 1.0, 700, QEasingCurve.OutCubic, start=0.0)

    def appear(self, delay=0):
        QTimer.singleShot(delay, lambda: self._guard(
            lambda: self._go("appearT", 1.0, 560, QEasingCurve.OutBack)))

    def disappear(self, done=None):
        anim = self._go("appearT", 0.0, 230, QEasingCurve.InBack)
        if done:
            def once():
                try:
                    anim.finished.disconnect(once)
                except Exception:
                    pass
                done()
            anim.finished.connect(once)

    # ---- events ----
    def enterEvent(self, event):
        self._go("hoverT", 1.0, 260, QEasingCurve.OutBack)
        tip().request(self.label, self, self.tip_side, self.hint)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._go("hoverT", 0.0, 260)
        self._go("pressT", 0.0, 200)
        tip().cancel()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        tip().cancel()
        if event.button() == Qt.LeftButton:
            self._go("pressT", 1.0, 110)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        inside = self.rect().contains(event.position().toPoint())
        self._go("pressT", 0.0, 420, QEasingCurve.OutBack)
        if inside and event.button() == Qt.LeftButton:
            self._go("pulseT", 1.0, 560, QEasingCurve.OutCubic, start=0.0)
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        if self.context_cb:
            self.context_cb(event.globalPos())
            event.accept()
        else:
            event.ignore()

    def paintEvent(self, event):
        a = self._appear
        if a <= 0.002:
            return

        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        p.setOpacity(max(0.0, min(1.0, a * 1.5)))

        h, pr = self._hover, self._press
        s = (1.0 + 0.12 * h - 0.10 * pr) * (0.35 + 0.65 * a)
        cx = self.width() / 2.0
        cy = self.height() / 2.0 - 4.0 * h
        r = self.base / 2.0 * s
        center = QPointF(cx, cy)

        # soft shadow under the button
        if h > 0.01:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, int(55 * h)))
            p.drawEllipse(QPointF(cx, self.height() / 2.0 + self.base * 0.42), r * 0.7, 4.5)

        if self.ghost:
            fill = QColor(255, 255, 255, int((18 + 50 * h) if self.dark else (30 + 80 * h)))
            edge = QColor(255, 255, 255, int(150 + 90 * h)) if self.dark \
                else QColor(20, 20, 20, int(120 + 100 * h))
            p.setBrush(fill)
            p.setPen(QPen(edge, 1.4, Qt.DashLine))
            p.drawEllipse(center, r - 1, r - 1)
        else:
            base_c, hover_c = ((20, 20, 20, 235), (70, 70, 70, 245)) if self.dark \
                else ((255, 255, 255, 70), (255, 255, 255, 165))
            color = QColor(*[int(base_c[i] + (hover_c[i] - base_c[i]) * h) for i in range(4)])
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(center, r, r)
            if h > 0.01:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(255, 255, 255, int(110 * h)), 1.4))
                p.drawEllipse(center, r, r)

        # click pulse ring
        if 0.0 < self._pulse < 1.0:
            t = self._pulse
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, int(170 * (1 - t))), 2.0))
            ring = r + 3 + 6 * t
            p.drawEllipse(center, ring, ring)

        if self.overlay_cb:
            self.overlay_cb(p, center, r, s)

        if not self.hide_icon:
            isz = max(1, int(self.base * 0.52 * s * (1 + 0.05 * h)))
            self.icon_obj.paint(p, QRect(int(cx - isz / 2), int(cy - isz / 2), isz, isz))


class RoundedImage(QWidget):
    """Card image that zooms smoothly on hover."""
    def __init__(self, path: Path, width, height, seed=0, radius=20):
        super().__init__()
        self.setFixedSize(width, height)
        self.radius = radius
        self._zoom = 0.0
        self.anim = QPropertyAnimation(self, b"zoomT", self)
        self.setAttribute(Qt.WA_Hover, True)
        self.pixmap = QPixmap(str(path)) if path.exists() else QPixmap()
        self.colors = [
            ("#ff9a9e", "#fad0c4"),
            ("#a1c4fd", "#c2e9fb"),
            ("#fbc2eb", "#a6c1ee"),
        ][seed % 3]
        self._big = QPixmap()
        if not self.pixmap.isNull():
            self._big = self.pixmap.scaled(
                int(width * 1.12), int(height * 1.12),
                Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )

    def _get_zoom(self): return self._zoom
    def _set_zoom(self, v): self._zoom = v; self.update()
    zoomT = Property(float, _get_zoom, _set_zoom)

    def _go(self, end):
        self.anim.stop()
        self.anim.setDuration(380)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.setStartValue(self._zoom)
        self.anim.setEndValue(end)
        self.anim.start()

    def enterEvent(self, event):
        self._go(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._go(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self.radius, self.radius)
        painter.setClipPath(path)

        if self._big.isNull():
            gradient = QLinearGradient(0, 0, self.width(), self.height())
            gradient.setColorAt(0, QColor(self.colors[0]))
            gradient.setColorAt(1, QColor(self.colors[1]))
            painter.fillRect(self.rect(), QBrush(gradient))
        else:
            scale = (1.0 + 0.10 * self._zoom) / 1.12
            w = self._big.width() * scale
            h = self._big.height() * scale
            target = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
            painter.drawPixmap(target, self._big, QRectF(self._big.rect()))

        if self._zoom > 0.01:  # soft light on hover
            painter.fillRect(self.rect(), QColor(255, 255, 255, int(28 * self._zoom)))


class TypeLabel(QLabel):
    """Label whose text is 'typed' in (progressT 0 -> 1). Size stays constant."""
    def __init__(self, text):
        super().__init__(text)
        self._progress = 0.0
        self.anim = QPropertyAnimation(self, b"progressT", self)

    def _get_progress(self): return self._progress
    def _set_progress(self, v): self._progress = v; self.update()
    progressT = Property(float, _get_progress, _set_progress)

    def type_in(self, delay=0, duration=900):
        def start():
            try:
                self.anim.stop()
                self.anim.setDuration(duration)
                self.anim.setEasingCurve(QEasingCurve.Linear)
                self.anim.setStartValue(0.0)
                self.anim.setEndValue(1.0)
                self.anim.start()
            except RuntimeError:
                pass
        QTimer.singleShot(delay, start)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setFont(self.font())
        painter.setPen(QColor("white"))
        fm = self.fontMetrics()
        full = self.text()
        count = int(len(full) * self._progress + 0.5)
        x = self.width() - fm.horizontalAdvance(full)   # right aligned as a whole
        y = (self.height() + fm.ascent() - fm.descent()) // 2
        painter.drawText(x, y, full[:count])


# ----------------------------- Calendar -----------------------------

def jalali_days_in_month(date: "jdatetime.date") -> int:
    if date.month <= 6:
        return 31
    if date.month <= 11:
        return 30
    return 30 if date.isleap() else 29


class CalendarCard(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("cal")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "#cal{background:rgba(28,28,28,235); border-radius:26px;}"
            "QLabel{background:transparent; color:white;}"
        )
        self.setFixedSize(236, 296)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        self.title = QLabel(alignment=Qt.AlignCenter)
        title_font = QFont(QApplication.font())
        title_font.setPointSize(15)
        title_font.setBold(True)
        self.title.setFont(title_font)
        layout.addWidget(self.title)

        self.grid = QGridLayout()
        self.grid.setSpacing(4)
        layout.addLayout(self.grid)
        layout.addStretch()

        self.shown = None
        self.refresh()

    def refresh(self):
        today = jdatetime.date.today()
        self.shown = today

        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        months = [
            "فروردین", "اردیبهشت", "خرداد", "تیر",
            "مرداد", "شهریور", "مهر", "آبان",
            "آذر", "دی", "بهمن", "اسفند"
        ]
        weekdays = ["ش", "ی", "د", "س", "چ", "پ", "ج"]
        self.title.setText(f"{months[today.month - 1]} {today.year}")

        for col, day_name in enumerate(weekdays):
            label = QLabel(day_name, alignment=Qt.AlignCenter)
            label.setStyleSheet("color:#888; font-size:10px;")
            self.grid.addWidget(label, 0, col)

        first_day = jdatetime.date(today.year, today.month, 1)
        offset = first_day.weekday()  # jdatetime: Saturday = 0 ... Friday = 6
        days_in_month = jalali_days_in_month(today)

        for day in range(1, days_in_month + 1):
            index = offset + day - 1
            row = index // 7 + 1
            col = index % 7
            label = QLabel(str(day), alignment=Qt.AlignCenter)

            if day == today.day:
                label.setStyleSheet("color:white; background:#444; border-radius:10px;"
                                    "font-weight:bold; font-size:14px;")
            elif col == 6:  # Friday
                label.setStyleSheet("color:#ff7b7b; font-size:12px;")
            else:
                label.setStyleSheet("color:#ddd; font-size:12px;")

            self.grid.addWidget(label, row, col)


# ----------------------------- Music player -----------------------------

class VinylDisc(QWidget):
    """Little vinyl record that spins while music plays."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(44, 44)
        self._angle = 0.0
        self.anim = QVariantAnimation(self)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(360.0)
        self.anim.setDuration(3200)
        self.anim.setLoopCount(-1)
        self.anim.valueChanged.connect(self._on_value)

    def _on_value(self, value):
        self._angle = float(value)
        self.update()

    def set_playing(self, playing):
        if playing:
            if self.anim.state() == QAbstractAnimation.Paused:
                self.anim.resume()
            elif self.anim.state() != QAbstractAnimation.Running:
                self.anim.start()
        elif self.anim.state() == QAbstractAnimation.Running:
            self.anim.pause()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(22, 22)
        p.rotate(self._angle)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#151515"))
        p.drawEllipse(QPointF(0, 0), 22, 22)

        p.setBrush(Qt.NoBrush)
        for radius in (18, 14.5, 11.5):
            p.setPen(QPen(QColor(255, 255, 255, 22), 0.8))
            p.drawEllipse(QPointF(0, 0), radius, radius)

        p.setPen(QPen(QColor(255, 255, 255, 80), 1.6))
        p.drawArc(QRectF(-18, -18, 36, 36), 20 * 16, 40 * 16)
        p.drawArc(QRectF(-18, -18, 36, 36), 200 * 16, 40 * 16)

        gradient = QLinearGradient(-8, -8, 8, 8)
        gradient.setColorAt(0, QColor("#ff9a9e"))
        gradient.setColorAt(1, QColor("#a1c4fd"))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(gradient))
        p.drawEllipse(QPointF(0, 0), 8, 8)
        p.setBrush(QColor("#151515"))
        p.drawEllipse(QPointF(0, 0), 2, 2)


class ClickSlider(QSlider):
    """Slider that jumps to where you click and can still be dragged."""
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.maximum() > self.minimum():
            value = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(), int(event.position().x()), max(1, self.width() - 1))
            self.setValue(value)
            self.sliderMoved.emit(value)
        super().mousePressEvent(event)


def fmt_time(ms):
    seconds = max(0, int(ms // 1000))
    return f"{seconds // 60}:{seconds % 60:02d}"


class MusicPlayer(QWidget):
    EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}

    def __init__(self, volume=60, muted=False, on_change=None):
        super().__init__()
        self.volume = max(0, min(100, int(volume)))
        self.muted = bool(muted)
        self.on_change = on_change
        self._gain = 1.0                 # fade in / out multiplier
        self._fade_anim = None
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._emit_change)

        self.setObjectName("mp")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(300, 96)
        self.setStyleSheet("""
            #mp { background: rgba(255,255,255,80); border-radius: 26px; }
            QLabel { background: transparent; color: #1d1d1d; }
            QPushButton { background: transparent; border: none; padding: 3px; }
            QPushButton:hover { background: rgba(255,255,255,90); border-radius: 10px; }
            QSlider::groove:horizontal { height:3px; background:rgba(0,0,0,60); border-radius:1px; }
            QSlider::sub-page:horizontal { background:#111; border-radius:1px; }
            QSlider::handle:horizontal { width:9px; margin:-3px 0; background:#111; border-radius:4px; }
            QSlider::handle:horizontal:hover { width:11px; margin:-4px 0; border-radius:5px; }
        """)

        self.tracks = sorted(
            p for p in MUSIC_DIR.glob("*") if p.suffix.lower() in self.EXTS
        ) if MUSIC_DIR.exists() else []

        self.idx = 0
        self.player = None
        self.audio = None
        self.media_failed = False

        self.disc = VinylDisc()

        title_font = QFont(QApplication.font())
        title_font.setPixelSize(11)
        title_font.setBold(True)
        self.title_font = title_font
        self.title = QLabel()
        self.title.setFont(title_font)
        self.set_title(self.tracks[0].stem if self.tracks else "No music in assets/music")

        time_font = QFont(QApplication.font())
        time_font.setPixelSize(10)
        self.time = QLabel("0:00 / 0:00")
        self.time.setFont(time_font)
        self.time.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.time.setMinimumWidth(68)
        self.time.setStyleSheet("color:rgba(0,0,0,150);")

        self.prev_b = self._button("fa5s.step-backward", 26, 15, "Previous  (B)", lambda: self.step(-1))
        self.play_b = self._button("fa5s.play", 30, 18, "Play / pause  (Space)", self.toggle)
        self.next_b = self._button("fa5s.step-forward", 26, 15, "Next  (N)", lambda: self.step(1))
        self.stop_b = self._button("fa5s.stop", 26, 12, "Stop", self.stop)
        self.mute_b = self._button("fa5s.volume-up", 26, 15, "Mute  (M)", self.toggle_mute)

        self.slider = ClickSlider(Qt.Horizontal)
        self.slider.setFixedHeight(14)
        self.slider.sliderMoved.connect(self._seek)

        self.vol = ClickSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(self.volume)
        self.vol.setFixedSize(60, 14)
        self.vol.setToolTip("Volume  (Up / Down, or scroll over the player)")
        self.vol.valueChanged.connect(lambda v: self.set_volume(v, show=True))
        self._update_vol_icon()

        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(self.title, 1)
        top.addWidget(self.time)

        controls = QHBoxLayout()
        controls.setSpacing(2)
        for button in (self.prev_b, self.play_b, self.next_b, self.stop_b):
            controls.addWidget(button)
        controls.addStretch()
        controls.addWidget(self.mute_b)
        controls.addWidget(self.vol)

        column = QVBoxLayout()
        column.setSpacing(3)
        column.addLayout(top)
        column.addWidget(self.slider)
        column.addLayout(controls)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)
        layout.addWidget(self.disc, 0, Qt.AlignVCenter)
        layout.addLayout(column, 1)

    # ---- small helpers ----
    def _button(self, icon, size, icon_px, tooltip, slot):
        button = QPushButton()
        button.setFixedSize(size, 28)
        button.setCursor(Qt.PointingHandCursor)
        button.setFocusPolicy(Qt.NoFocus)
        button.setToolTip(tooltip)
        button.setIcon(qta.icon(icon, color="#111111"))
        button.setIconSize(QSize(icon_px, icon_px))
        button.clicked.connect(lambda checked=False: slot())
        return button

    def set_title(self, text):
        self.title.setToolTip(text)
        self.title.setText(QFontMetrics(self.title_font).elidedText(text, Qt.ElideRight, 124))

    def set_play_icon(self, playing):
        self.play_b.setIcon(qta.icon("fa5s.pause" if playing else "fa5s.play", color="#111111"))
        self.play_b.setIconSize(QSize(18, 18))

    def _update_vol_icon(self):
        if self.muted or self.volume == 0:
            name = "fa5s.volume-mute"
        elif self.volume < 50:
            name = "fa5s.volume-down"
        else:
            name = "fa5s.volume-up"
        self.mute_b.setIcon(qta.icon(name, color="#111111" if not self.muted else "#777777"))
        self.mute_b.setIconSize(QSize(15, 15))

    # ---- volume ----
    def _apply_volume(self):
        if self.audio is not None:
            level = 0.0 if self.muted else (self.volume / 100.0) ** 1.8
            self.audio.setVolume(level * self._gain)

    def _emit_change(self):
        if self.on_change:
            self.on_change(self.volume, self.muted)

    def set_volume(self, value, show=False):
        value = max(0, min(100, int(value)))
        self.volume = value
        if value > 0 and self.muted:
            self.muted = False
        if self.vol.value() != value:
            self.vol.blockSignals(True)
            self.vol.setValue(value)
            self.vol.blockSignals(False)
        self._update_vol_icon()
        self._apply_volume()
        self._save_timer.start(500)
        if show:
            tip().flash(f"Volume {value}%", self.vol, "top", "", 900)

    def change_volume(self, delta):
        self.set_volume(self.volume + delta, show=True)

    def toggle_mute(self):
        self.muted = not self.muted
        if not self.muted and self.volume == 0:
            self.volume = 30
            self.vol.blockSignals(True)
            self.vol.setValue(30)
            self.vol.blockSignals(False)
        self._update_vol_icon()
        self._apply_volume()
        self._save_timer.start(500)
        tip().flash("Muted" if self.muted else f"Volume {self.volume}%", self.vol, "top", "", 900)

    def wheelEvent(self, event):
        self.change_volume(5 if event.angleDelta().y() > 0 else -5)
        event.accept()

    def _on_gain(self, value):
        self._gain = float(value)
        self._apply_volume()

    def _fade(self, target, ms, then=None):
        if self._fade_anim is not None:
            self._fade_anim.stop()
            self._fade_anim.deleteLater()
        anim = QVariantAnimation(self)
        anim.setStartValue(float(self._gain))
        anim.setEndValue(float(target))
        anim.setDuration(ms)
        anim.valueChanged.connect(self._on_gain)
        if then:
            anim.finished.connect(then)
        self._fade_anim = anim
        anim.start()

    # ---- playback ----
    def on_state(self, state):
        playing = state == QMediaPlayer.PlayingState
        self.set_play_icon(playing)
        self.disc.set_playing(playing)

    def ensure_player(self):
        if self.player or self.media_failed or not HAS_MEDIA:
            return self.player
        try:
            if not QMediaDevices.audioOutputs():          # no speakers / sound device found
                self.media_failed = True
                self.set_title("No audio output device")
                return None
            self.audio = QAudioOutput()
            self.player = QMediaPlayer()
            self.player.setAudioOutput(self.audio)
            self._apply_volume()
            self.player.positionChanged.connect(self.on_pos)
            self.player.durationChanged.connect(self.on_duration)
            self.player.mediaStatusChanged.connect(self.on_status)
            self.player.playbackStateChanged.connect(self.on_state)
        except Exception as exc:
            print("Media init failed:", exc)
            self.media_failed = True
            self.player = None
        return self.player

    def load(self):
        if not (self.ensure_player() and self.tracks):
            return
        track = self.tracks[self.idx]
        self.player.setSource(QUrl.fromLocalFile(str(track)))
        self.set_title(track.stem)
        self.slider.setValue(0)
        self.time.setText("0:00 / 0:00")

    def _play(self):
        self._gain = 0.0
        self._apply_volume()
        self.player.play()
        self._fade(1.0, 300)                     # fade in

    def toggle(self):
        if not (self.ensure_player() and self.tracks):
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self._fade(0.0, 200, self.player.pause)          # fade out, then pause
        else:
            if self.player.source().isEmpty():
                self.load()
            self._play()

    def stop(self):
        if not self.player:
            return
        def finish():
            self.player.stop()
            self.slider.setValue(0)
            self.time.setText(f"0:00 / {fmt_time(self.player.duration())}")
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self._fade(0.0, 180, finish)
        else:
            finish()

    def step(self, direction):
        if not self.tracks:
            return
        self.idx = (self.idx + direction) % len(self.tracks)
        self.load()
        if self.ensure_player():
            self._play()

    def _seek(self, value):
        if self.player:
            self.player.setPosition(value)
            self.time.setText(f"{fmt_time(value)} / {fmt_time(self.player.duration())}")

    def on_duration(self, duration):
        self.slider.setRange(0, max(0, duration))
        self.time.setText(f"{fmt_time(self.slider.value())} / {fmt_time(duration)}")

    def on_pos(self, position):
        if not self.slider.isSliderDown():
            self.slider.setValue(position)
            self.time.setText(f"{fmt_time(position)} / {fmt_time(self.player.duration())}")

    def on_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.step(1)


# ----------------------------- App search / picker -----------------------------

_APP_INDEX = {"files": None, "store": None, "store_ts": 0.0}


def scan_start_menu():
    """Classic apps: shortcuts from both Start Menu folders (fast)."""
    folders = [
        os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
    ]
    apps, seen_paths, seen_names = [], set(), set()
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for root, dirs, files in os.walk(folder):
            for filename in files:
                if not filename.lower().endswith((".lnk", ".url", ".exe")):
                    continue
                name = os.path.splitext(filename)[0]
                path = os.path.join(root, filename)
                if path.lower() in seen_paths or name.lower() in seen_names \
                        or name.lower().startswith("uninstall"):
                    continue
                seen_paths.add(path.lower())
                seen_names.add(name.lower())
                apps.append({"name": name, "target": path, "qta": None, "kind": "file"})
    return sorted(apps, key=lambda a: a["name"].lower())


def scan_store_apps():
    """Microsoft Store (UWP) apps such as Calculator / Settings. Slow (~1 s), so run in a thread."""
    if os.name != "nt":
        return []
    cmd = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"
    raw = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
        capture_output=True, timeout=25, creationflags=0x08000000
    ).stdout.decode("utf-8", "ignore").strip()
    data = json.loads(raw) if raw else []
    if isinstance(data, dict):
        data = [data]
    apps = []
    for entry in data:
        name, app_id = entry.get("Name"), entry.get("AppID")
        if name and app_id and "!" in app_id:                 # package apps only (no duplicates)
            apps.append({"name": name, "target": "shell:AppsFolder\\" + app_id,
                         "qta": "fa5s.cube", "kind": "store"})
    return apps


def _fuzzy(token, name):
    """Letters of token appear in order inside name (e.g. 'chr' -> 'Chrome'). 0 = no match."""
    if len(token) < 3:
        return 0
    pos, gaps = -1, 0
    for ch in token:
        nxt = name.find(ch, pos + 1)
        if nxt < 0:
            return 0
        gaps += nxt - pos - 1 if pos >= 0 else 0
        pos = nxt
    return max(60, 220 - gaps * 12)


def match_score(tokens, name):
    """Higher = better. None = not a match. Every typed word must match."""
    low = name.lower()
    words = [w for w in re.split(r"[\s\-_.()\[\]]+", low) if w]
    initials = "".join(w[0] for w in words)
    total = 0
    for t in tokens:
        if low == t:
            score = 1000
        elif low.startswith(t):
            score = 800
        elif any(w.startswith(t) for w in words):
            score = 600
        elif len(t) >= 2 and initials.startswith(t):          # 'vsc' -> Visual Studio Code
            score = 550
        elif t in low:
            score = 400
        else:
            score = _fuzzy(t, low)
            if not score:
                return None
        total += score
    return total / len(tokens)


_CALC_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Add, ast.Sub,
               ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv, ast.USub, ast.UAdd)


def safe_calc(text):
    """'12*(3+4)' -> '84'. Only numbers and + - * / % ** ( ) are allowed. None if not math."""
    text = text.strip()
    if not text or not re.fullmatch(r"[0-9+\-*/().%^ \t]+", text):
        return None
    if not re.search(r"[+*/%^]|(?<=[0-9)\s])-", text):                  # needs an operator
        return None
    try:
        tree = ast.parse(text.replace("^", "**"), mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, _CALC_NODES):
                return None
            if isinstance(node, ast.Pow) and isinstance(getattr(node, "parent", None), ast.AST):
                pass
        # block huge powers
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
                right = node.right
                if not (isinstance(right, ast.Constant) and abs(right.value) <= 64):
                    return None
        value = eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}}, {})
    except Exception:
        return None
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return str(int(value)) if value.is_integer() else f"{value:.10g}"
    return str(value)


class AppSearchDialog(QDialog):
    """Launch mode: opens the chosen app.  Pick mode: returns it in self.picked.
    Ranks by relevance (prefix, word start, initials, typos) and by how often you use an app;
    also finds Store apps, does quick maths and can search the web."""

    def __init__(self, parent=None, pick=False, title="Search Apps"):
        super().__init__(parent)
        self.pick = pick
        self.picked = None
        self._animated = False
        self.setWindowTitle(title)
        self.setFixedSize(460, 560)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        if _APP_INDEX["files"] is None:
            _APP_INDEX["files"] = scan_start_menu()
        self.icon_cache = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.container = QWidget()
        self.container.setObjectName("container")
        self.container.setStyleSheet("""
            #container { background:#101010; border:1px solid #383838; border-radius:24px; }
            QLabel { color:white; background:transparent; border:none; }
            QLineEdit { background:#202020; color:white; border:1px solid #444;
                        border-radius:14px; padding:13px; font-size:14px; }
            QLineEdit:focus { border:1px solid #888; }
            QListWidget { background:transparent; color:white; border:none; outline:none; padding:4px; }
            QListWidget::item { padding:9px 10px; border-radius:12px; }
            QListWidget::item:selected { background:#353535; }
            QListWidget::item:hover { background:#292929; }
        """)

        inner = QVBoxLayout(self.container)
        inner.setContentsMargins(22, 20, 22, 14)
        inner.setSpacing(12)

        heading = QLabel(title)
        heading.setStyleSheet("font-size:21px; font-weight:bold;")
        inner.addWidget(heading)

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Search an app or a website (github.com)..." if pick
            else "Search apps, type a website, or do maths (12*7)...")
        inner.addWidget(self.search)

        self.list = QListWidget()
        self.list.setIconSize(QSize(24, 24))
        inner.addWidget(self.list)

        self.footer = QLabel("")
        self.footer.setStyleSheet("color:rgba(255,255,255,110); font-size:11px;")
        inner.addWidget(self.footer)
        layout.addWidget(self.container)

        self.search.textChanged.connect(self.filter_apps)
        self.search.returnPressed.connect(self.open_selected)
        self.list.itemActivated.connect(self.open_item)

        self.load_store_apps()
        self.filter_apps("")
        self.search.setFocus()

    # ---- data ----
    def entries(self):
        return (_APP_INDEX["files"] or []) + (_APP_INDEX["store"] or [])

    def usage(self):
        parent = self.parent()
        return parent.config.setdefault("app_usage", {}) if parent is not None \
            and hasattr(parent, "config") else {}

    def load_store_apps(self):
        fresh = _APP_INDEX["store"] is not None and time.time() - _APP_INDEX["store_ts"] < 600
        if fresh or os.name != "nt":
            self.set_footer()
            return
        self.set_footer(loading=True)

        def done(result, error):
            if error is None and result is not None:
                _APP_INDEX["store"] = result
                _APP_INDEX["store_ts"] = time.time()
            elif _APP_INDEX["store"] is None:
                _APP_INDEX["store"] = []
            try:
                self.set_footer()
                self.filter_apps(self.search.text())
            except RuntimeError:
                pass                                   # dialog already closed

        run_job(scan_store_apps, done)

    def set_footer(self, loading=False):
        hint = "Enter = open   Up/Down = select   Esc = close"
        self.footer.setText(("Loading Store apps...   " if loading else "") + hint)

    # ---- showing results ----
    def icon_for(self, item):
        if item.get("qta"):
            return qta.icon(item["qta"], color="white")
        path = item["target"]
        icon = self.icon_cache.get(path)
        if icon is None:
            icon = self.icon_cache[path] = file_icon(path)
        return icon

    def add_row(self, text, data, icon):
        row = QListWidgetItem(text)
        row.setData(Qt.UserRole, data)
        row.setIcon(icon)
        self.list.addItem(row)

    def filter_apps(self, text):
        self.list.clear()
        query = text.strip()
        usage = self.usage()
        entries = self.entries()

        if query:
            result = safe_calc(query)
            if result is not None:
                self.add_row(f"{query} = {result}", {"kind": "calc", "target": result},
                             qta.icon("fa5s.calculator", color="white"))
            if looks_like_url(query):
                url = query if "://" in query else "https://" + query
                host = urlparse(url).netloc.replace("www.", "") or query
                self.add_row(f"{'Add' if self.pick else 'Open'} website:  {host}",
                             {"kind": "site", "label": host, "target": url, "qta": "fa5s.globe"},
                             qta.icon("fa5s.globe", color="white"))

            tokens = query.lower().split()
            scored = []
            for app in entries:
                score = match_score(tokens, app["name"])
                if score is not None:
                    scored.append((score + min(usage.get(app["name"], 0), 30) * 6, app))
            scored.sort(key=lambda pair: (-pair[0], pair[1]["name"].lower()))
            shown = [app for _, app in scored[:60]]
        else:
            used = sorted((a for a in entries if usage.get(a["name"], 0) > 0),
                          key=lambda a: -usage[a["name"]])[:8]
            rest = [a for a in entries if a not in used]
            shown = (used + rest)[:80]

        for app in shown:
            self.add_row(app["name"], dict(app), self.icon_for(app))

        if query and not self.pick:
            self.add_row(f"Search the web for \"{query}\"",
                         {"kind": "web", "target": "https://www.google.com/search?q=" + quote(query)},
                         qta.icon("fa5s.search", color="white"))

        if self.list.count():
            self.list.setCurrentRow(0)

    # ---- opening ----
    def showEvent(self, event):
        super().showEvent(event)
        if self._animated:
            return
        self._animated = True

        end = self.pos()
        self.setWindowOpacity(0.0)
        self.move(end + QPoint(0, 28))

        group = QParallelAnimationGroup(self)
        move = QPropertyAnimation(self, b"pos")
        move.setDuration(380)
        move.setEasingCurve(QEasingCurve.OutBack)
        move.setStartValue(end + QPoint(0, 28))
        move.setEndValue(end)
        fade = QPropertyAnimation(self, b"windowOpacity")
        fade.setDuration(260)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        group.addAnimation(move)
        group.addAnimation(fade)
        group.start()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Down, Qt.Key_Up) and self.list.count():
            step = 1 if event.key() == Qt.Key_Down else -1
            row = max(0, min(self.list.count() - 1, self.list.currentRow() + step))
            self.list.setCurrentRow(row)
            return
        super().keyPressEvent(event)

    def open_selected(self):
        item = self.list.currentItem()
        if item:
            self.open_item(item)

    def open_item(self, item):
        data = item.data(Qt.UserRole)
        kind = data.get("kind")

        if kind == "calc":                                   # copy the result
            QApplication.clipboard().setText(data["target"])
            tip().flash("Copied " + data["target"], self.search, "top", "", 1400)
            return

        if self.pick:
            self.picked = {"label": data.get("label") or data["name"], "target": data["target"],
                           "exe": None, "qta": data.get("qta")}
        else:
            launch(data["target"])
            if kind in ("file", "store"):                    # remember what you open most
                usage = self.usage()
                usage[data["name"]] = usage.get(data["name"], 0) + 1
                parent = self.parent()
                if parent is not None and hasattr(parent, "save_config"):
                    parent.save_config()
        self.accept()


# ----------------------------- Pinned apps (sidebar / dock) -----------------------------

class PinPanel(Glass):
    """Glass bar with user-chosen pinned buttons, a '+' button and a right-click menu."""

    def __init__(self, win, key, title, vertical, max_items, radius, alpha,
                 size, pad, lead=None, trail=None):
        super().__init__(radius=radius, alpha=alpha)
        self.win = win
        self.key = key
        self.title = title
        self.vertical = vertical
        self.max_items = max_items
        self.size_ = size
        self.pad = pad
        self.dark = vertical          # sidebar = dark buttons, dock = light buttons
        self.lead = lead or []        # fixed buttons before the pinned ones
        self.trail = trail or []      # fixed tool buttons after the "+" button
        self.divider = Divider() if self.trail else None
        self.buttons = []
        self.add_btn = None
        self.intro_done = False

        self.box = QVBoxLayout(self) if vertical else QHBoxLayout(self)
        if vertical:
            self.box.setContentsMargins(0, 18, 0, 18)
            self.box.setSpacing(4)
            self.box.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        else:
            self.box.setContentsMargins(22, 6, 22, 6)
            self.box.setSpacing(6)

        self.rebuild()

    @property
    def items(self):
        return self.win.config[self.key]

    def _place(self, widget):
        if self.vertical:
            self.box.addWidget(widget, 0, Qt.AlignHCenter)
        else:
            self.box.addWidget(widget, 0, Qt.AlignVCenter)

    def rebuild(self, new_index=None):
        keep = set(self.lead) | set(self.trail)
        if self.divider is not None:
            keep.add(self.divider)
        while self.box.count():
            entry = self.box.takeAt(0)
            widget = entry.widget()
            if widget is not None and widget not in keep:
                widget.deleteLater()
        self.buttons = []
        self.add_btn = None

        for widget in self.lead:
            self._place(widget)

        side = "right" if self.vertical else "top"
        for index, item in enumerate(self.items):
            button = IconButton(
                item["label"], make_icon(item, self.dark), self.size_, self.dark, self.pad,
                on_click=lambda checked=False, it=item: launch(it["target"], it.get("exe")),
                hint=item_hint(item), tip_side=side
            )
            button.context_cb = lambda pos, i=index: self.show_menu(i, pos)
            visible_now = self.intro_done and index != new_index
            button.set_appear(1.0 if visible_now else 0.0)
            if self.intro_done and index == new_index:
                button.appear(40)
            self.buttons.append(button)
            self._place(button)

        if len(self.items) < self.max_items:
            icon = qta.icon("fa5s.plus", color="#FFFFFF" if self.dark else "#111111")
            self.add_btn = IconButton(
                f"Add to {self.title}", icon, self.size_ - 8, self.dark, self.pad + 4,
                on_click=self.add_dialog, ghost=True,
                hint="Pin an app or a website", tip_side=side
            )
            self.add_btn.set_appear(1.0 if self.intro_done else 0.0)
            self._place(self.add_btn)

        if self.divider is not None:
            self.divider.set_appear(1.0 if self.intro_done else 0.0)
            self._place(self.divider)
        for widget in self.trail:
            self._place(widget)

        if self.vertical:
            self.box.addStretch()

    def set_tools_visible(self, visible, animate=True):
        """Show / hide the tool buttons (system, focus, wallpaper) and their divider."""
        self._tools_on = bool(visible)
        widgets = list(self.trail)
        if visible:
            if self.divider is not None:
                self.divider.setVisible(True)
                self.divider.set_appear(1.0)
            for i, widget in enumerate(widgets):
                widget.setVisible(True)
                if animate and self.isVisible():
                    widget.set_appear(0.0)
                    widget.appear(40 + i * 70)
                else:
                    widget.set_appear(1.0)
            return

        def hide_all():
            if getattr(self, "_tools_on", True):      # shown again in the meantime
                return
            for widget in widgets:
                widget.setVisible(False)
            if self.divider is not None:
                self.divider.setVisible(False)

        if animate and self.isVisible():
            for widget in widgets:
                widget.disappear()
            if self.divider is not None:
                self.divider.set_appear(0.0)
            QTimer.singleShot(280, hide_all)
        else:
            hide_all()

    def appear_all(self, base_delay=0, stagger=70):
        self.intro_done = True
        widgets = list(self.lead) + list(self.buttons) + ([self.add_btn] if self.add_btn else [])
        if self.divider is not None:
            widgets.append(self.divider)
        widgets += list(self.trail)
        for i, widget in enumerate(widgets):
            widget.appear(base_delay + i * stagger)

    # ---- editing ----
    def add_dialog(self):
        dialog = AppSearchDialog(self.win, pick=True, title=f"Add to {self.title}")
        if dialog.exec() == QDialog.Accepted and dialog.picked:
            self.pin_item(dialog.picked)

    def pin_item(self, item):
        """Returns True when added (or already pinned), False when the panel is full."""
        target = item["target"].lower()
        if any(i["target"].lower() == target for i in self.items):
            return True
        if len(self.items) >= self.max_items:
            return False
        self.items.append(item)
        self.win.save_config()
        self.rebuild(new_index=len(self.items) - 1)
        return True

    def move_item(self, index, step):
        other = index + step
        if 0 <= other < len(self.items):
            self.items[index], self.items[other] = self.items[other], self.items[index]
            self.win.save_config()
            self.rebuild()

    def remove_item(self, index):
        def done():
            if 0 <= index < len(self.items):
                self.items.pop(index)
                self.win.save_config()
            self.rebuild()
        if 0 <= index < len(self.buttons):
            self.buttons[index].disappear(done)
        else:
            done()

    def show_menu(self, index, pos):
        item = self.items[index]
        menu = styled_menu(self.win)
        menu.addAction("Open", lambda: launch(item["target"], item.get("exe")))
        menu.addSeparator()
        before = menu.addAction("Move up" if self.vertical else "Move left")
        after = menu.addAction("Move down" if self.vertical else "Move right")
        before.setEnabled(index > 0)
        after.setEnabled(index < len(self.items) - 1)
        before.triggered.connect(lambda: self.move_item(index, -1))
        after.triggered.connect(lambda: self.move_item(index, 1))
        menu.addSeparator()
        menu.addAction(f"Remove from {self.title}", lambda: self.remove_item(index))
        menu.exec(pos)


# ----------------------------- Small widgets -----------------------------

class Divider(QWidget):
    """Thin vertical line between the pinned apps and the tool buttons."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(16, 44)
        self._a = 0.0
        self.anim = QVariantAnimation(self)
        self.anim.valueChanged.connect(self._on_value)

    def _on_value(self, value):
        self._a = float(value)
        self.update()

    def set_appear(self, value):
        self._a = value
        self.update()

    def appear(self, delay=0):
        def go():
            try:
                self.anim.stop()
                self.anim.setDuration(500)
                self.anim.setStartValue(0.0)
                self.anim.setEndValue(1.0)
                self.anim.start()
            except RuntimeError:
                pass
        QTimer.singleShot(delay, go)

    def paintEvent(self, event):
        if self._a <= 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(self._a)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 110))
        p.drawRoundedRect(QRectF(self.width() / 2 - 1, 8, 2, self.height() - 16), 1, 1)


class RingGauge(QWidget):
    """Animated circular gauge: big percentage inside, title and a small line below."""
    def __init__(self, title, color):
        super().__init__()
        self.setFixedSize(92, 118)
        self.title = title
        self.color = QColor(color)
        self.sub = ""
        self._v = 0.0
        self.anim = QPropertyAnimation(self, b"valueT", self)

    def _get_v(self): return self._v
    def _set_v(self, v): self._v = v; self.update()
    valueT = Property(float, _get_v, _set_v)

    def set_value(self, value, sub=""):
        self.sub = sub
        self.anim.stop()
        self.anim.setDuration(500)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.setStartValue(self._v)
        self.anim.setEndValue(float(max(0, min(100, value))))
        self.anim.start()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        d = 76
        w = self.width()
        rect = QRectF((w - d) / 2, 4, d, d).adjusted(5, 5, -5, -5)

        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 30), 7))
        p.drawEllipse(rect)
        p.setPen(QPen(self.color, 7, Qt.SolidLine, Qt.RoundCap))
        span = int(-360 * 16 * self._v / 100.0)
        if span:
            p.drawArc(rect, 90 * 16, span)

        big = QFont(QApplication.font())
        big.setPixelSize(17)
        big.setBold(True)
        p.setFont(big)
        p.setPen(QColor("white"))
        p.drawText(QRectF(0, 4, w, d), Qt.AlignCenter, f"{int(round(self._v))}%")

        mid = QFont(QApplication.font())
        mid.setPixelSize(12)
        mid.setBold(True)
        p.setFont(mid)
        p.setPen(QColor(255, 255, 255, 220))
        p.drawText(QRectF(0, d + 6, w, 16), Qt.AlignHCenter | Qt.AlignVCenter, self.title)

        small = QFont(QApplication.font())
        small.setPixelSize(10)
        p.setFont(small)
        p.setPen(QColor(255, 255, 255, 120))
        p.drawText(QRectF(0, d + 22, w, 14), Qt.AlignHCenter | Qt.AlignVCenter, self.sub)


class ToggleSwitch(QAbstractButton):
    def __init__(self, checked=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(46, 26)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self._t = 1.0 if checked else 0.0
        self.anim = QPropertyAnimation(self, b"slideT", self)
        self.toggled.connect(self._animate)

    def _get_t(self): return self._t
    def _set_t(self, v): self._t = v; self.update()
    slideT = Property(float, _get_t, _set_t)

    def set_silent(self, value):
        self.blockSignals(True)
        self.setChecked(value)
        self.blockSignals(False)
        self._t = 1.0 if value else 0.0
        self.update()

    def _animate(self, on):
        self.anim.stop()
        self.anim.setDuration(240)
        self.anim.setEasingCurve(QEasingCurve.OutBack)
        self.anim.setStartValue(self._t)
        self.anim.setEndValue(1.0 if on else 0.0)
        self.anim.start()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = max(0.0, min(1.0, self._t))
        off, on = (255, 255, 255, 45), (84, 196, 140, 255)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(*[int(off[i] + (on[i] - off[i]) * t) for i in range(4)]))
        p.drawRoundedRect(self.rect(), 13, 13)
        x = 3 + (self.width() - 26) * self._t
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, 3, 20, 20))


class AvatarButton(QPushButton):
    """Round avatar; hover shows a camera to change it."""
    def __init__(self, size):
        super().__init__()
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.pix = QPixmap()
        self._h = 0.0
        self.anim = QPropertyAnimation(self, b"hoverT", self)
        self.cam = qta.icon("fa5s.camera", color="white")

    def _get_h(self): return self._h
    def _set_h(self, v): self._h = v; self.update()
    hoverT = Property(float, _get_h, _set_h)

    def set_pix(self, pix):
        self.pix = pix
        self.update()

    def _go(self, end):
        self.anim.stop()
        self.anim.setDuration(200)
        self.anim.setStartValue(self._h)
        self.anim.setEndValue(end)
        self.anim.start()

    def enterEvent(self, event):
        self._go(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._go(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        if not self.pix.isNull():
            p.drawPixmap(0, 0, self.pix)
        if self._h > 0.01:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, int(130 * self._h)))
            p.drawEllipse(self.rect())
            p.setOpacity(self._h)
            s = int(self.width() * 0.34)
            self.cam.paint(p, QRect((self.width() - s) // 2, (self.height() - s) // 2, s, s))
            p.setOpacity(1.0)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 90), 1.5))
        p.drawEllipse(QRectF(self.rect()).adjusted(1, 1, -1, -1))


class ProfileChip(QPushButton):
    """Top-right pill: avatar + name + status dot. Click opens the profile panel."""
    def __init__(self):
        super().__init__()
        self.setFixedHeight(40)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.name = ""
        self.hint = ""
        self.avatar = QPixmap()
        self.hover = False
        self.font_ = QFont(QApplication.font())
        self.font_.setPixelSize(13)
        self.font_.setBold(True)

    def set_profile(self, name, avatar_path, status=""):
        self.name = name
        self.hint = status
        self.avatar = avatar_pixmap(avatar_path, 28, name)
        width = QFontMetrics(self.font_).horizontalAdvance(name)
        self.setFixedWidth(6 + 28 + 10 + width + 12 + 10 + 16)
        self.update()

    def enterEvent(self, event):
        self.hover = True
        self.update()
        tip().request(self.name or "Profile", self, "bottom", self.hint)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover = False
        self.update()
        tip().cancel()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        tip().cancel()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        h = self.height()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 235 if self.hover else 200))
        p.drawRoundedRect(QRectF(self.rect()), h / 2, h / 2)
        if not self.avatar.isNull():
            p.drawPixmap(6, 6, self.avatar)
        p.setFont(self.font_)
        p.setPen(QColor("#222"))
        p.drawText(QRectF(44, 0, self.width() - 44 - 30, h), Qt.AlignVCenter | Qt.AlignLeft, self.name)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(84, 196, 140))
        p.drawEllipse(QPointF(self.width() - 18, h / 2), 5, 5)


class StatusPill(QPushButton):
    """Wi-Fi / internet / battery indicator (next to the profile chip).
    Green dot = internet works, red dot = connected but no internet. Click opens Wi-Fi settings."""
    def __init__(self):
        super().__init__()
        self.setFixedHeight(40)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.hover = False
        self._icons = {}
        self.font_ = QFont(QApplication.font())
        self.font_.setPixelSize(12)
        self.font_.setBold(True)
        self.info = {}
        self.set_info({"kind": "unknown", "ssid": "", "signal": 0, "online": False,
                       "ping": None, "battery": None})

    def _icon(self, name, color):
        key = (name, color)
        if key not in self._icons:
            self._icons[key] = qta.icon(name, color=color)
        return self._icons[key]

    def set_info(self, info):
        self.info = info
        width = 14 + 18 + 14
        battery = info.get("battery")
        if battery:
            text_w = QFontMetrics(self.font_).horizontalAdvance(f"{battery[0]}%")
            width += 12 + 22 + (14 if battery[1] else 0) + text_w
        self.setFixedWidth(width)
        self.update()

    def tip_text(self):
        info = self.info
        parts = []
        if info["kind"] == "wifi":
            title = info["ssid"] or "Wi-Fi"
            parts.append(f"Signal {info['signal']}%")
        elif info["kind"] == "wired":
            title = "Wired network"
        elif info["kind"] == "unknown":
            title = "Checking network..."
        else:
            title = "No network"
        if info["kind"] != "unknown":
            parts.append(f"online {info['ping']} ms" if info["online"] else "no internet")
        if info.get("battery"):
            percent, plugged = info["battery"]
            parts.append(f"battery {percent}%" + (" (charging)" if plugged else ""))
        return title, "  -  ".join(parts)

    def enterEvent(self, event):
        self.hover = True
        self.update()
        title, hint = self.tip_text()
        tip().request(title, self, "bottom", hint)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover = False
        self.update()
        tip().cancel()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        tip().cancel()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        info = self.info
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing
                         | QPainter.SmoothPixmapTransform)
        h = self.height()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 235 if self.hover else 200))
        p.drawRoundedRect(QRectF(self.rect()), h / 2, h / 2)

        kind, online = info["kind"], info["online"]
        x = 14
        if kind == "wifi":
            name = "fa5s.wifi"
            signal = info["signal"]
            alpha = 1.0 if signal >= 60 else (0.75 if signal >= 30 else 0.5)
        elif kind == "wired":
            name, alpha = "fa5s.ethernet", 1.0
        else:
            name, alpha = "fa5s.wifi", 0.3
        p.setOpacity(alpha)
        self._icon(name, "#222222").paint(p, QRect(x, (h - 16) // 2, 18, 16))
        p.setOpacity(1.0)

        if kind != "unknown":                       # status dot on the icon
            p.setBrush(QColor(84, 196, 140) if online else QColor(230, 80, 80))
            p.setPen(QPen(QColor(255, 255, 255, 235), 1.5))
            p.drawEllipse(QPointF(x + 18, h / 2 + 7), 4, 4)
        x += 18 + 14

        battery = info.get("battery")
        if battery:
            percent, plugged = battery
            if percent >= 90:
                icon = "fa5s.battery-full"
            elif percent >= 65:
                icon = "fa5s.battery-three-quarters"
            elif percent >= 35:
                icon = "fa5s.battery-half"
            elif percent >= 12:
                icon = "fa5s.battery-quarter"
            else:
                icon = "fa5s.battery-empty"
            low = percent <= 15 and not plugged
            color = "#d33a3a" if low else "#222222"
            self._icon(icon, color).paint(p, QRect(x, (h - 14) // 2, 18, 14))
            x += 22
            if plugged:
                self._icon("fa5s.bolt", "#d9a400").paint(p, QRect(x - 2, (h - 12) // 2, 10, 12))
                x += 14
            p.setFont(self.font_)
            p.setPen(QColor(color))
            p.drawText(QRectF(x, 0, 60, h), Qt.AlignVCenter | Qt.AlignLeft, f"{percent}%")


# ----------------------------- Focus timer -----------------------------

class FocusTimer(QObject):
    changed = Signal()
    finished = Signal()

    def __init__(self, minutes=FOCUS_MINUTES):
        super().__init__()
        self.total = minutes * 60
        self.remaining = self.total
        self.running = False
        self.end_at = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    @property
    def state(self):
        if self.running:
            return "running"
        return "idle" if self.remaining == self.total else "paused"

    def mmss(self):
        return f"{self.remaining // 60:02d}:{self.remaining % 60:02d}"

    def start(self):
        if self.running:
            return
        self.running = True
        self.end_at = time.monotonic() + self.remaining
        self.timer.start(250)
        self.changed.emit()

    def pause(self):
        if not self.running:
            return
        self._update_remaining()
        self.running = False
        self.timer.stop()
        self.changed.emit()

    def toggle(self):
        self.pause() if self.running else self.start()

    def reset(self):
        self.running = False
        self.timer.stop()
        self.remaining = self.total
        self.changed.emit()

    def set_minutes(self, minutes):
        self.total = int(minutes) * 60
        self.reset()

    def _update_remaining(self):
        self.remaining = max(0, int(math.ceil(self.end_at - time.monotonic())))

    def _tick(self):
        before = self.remaining
        self._update_remaining()
        if self.remaining <= 0:
            self.running = False
            self.timer.stop()
            self.remaining = self.total
            self.changed.emit()
            self.finished.emit()
        elif self.remaining != before:
            self.changed.emit()


# ----------------------------- Popovers (system stats, profile) -----------------------------

class Popover(QWidget):
    """Dark glass panel that floats over the window and animates in / out."""
    def __init__(self, win, owner, width, height):
        super().__init__(win)
        self.win = win
        self.owner = owner
        self.is_open = False
        self.group = None
        self.setFixedSize(width, height)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.effect = QGraphicsOpacityEffect(self)
        self.effect.setOpacity(0.0)
        self.setGraphicsEffect(self.effect)
        self.hide()

    def anchor(self):
        """The widget the panel hangs from (the dock when its tool button is hidden)."""
        return self.owner if self.owner.isVisible() else self.win.dock

    # subclasses
    def target_pos(self):
        return QPoint(0, 0)

    def on_open(self):
        pass

    def on_close(self):
        pass

    def clamp(self, x, y):
        margin = 14
        x = max(margin, min(x, self.win.width() - self.width() - margin))
        y = max(margin, min(y, self.win.height() - self.height() - margin))
        return QPoint(x, y)

    def reposition(self):
        if self.is_open:
            self.move(self.target_pos())

    def _animate(self, begin, end, o_from, o_to, duration, curve, hide_after=False):
        if self.group:
            self.group.stop()
        group = QParallelAnimationGroup(self)
        move = QPropertyAnimation(self, b"pos")
        move.setDuration(duration)
        move.setEasingCurve(curve)
        move.setStartValue(begin)
        move.setEndValue(end)
        fade = QPropertyAnimation(self.effect, b"opacity")
        fade.setDuration(int(duration * 0.8))
        fade.setStartValue(o_from)
        fade.setEndValue(o_to)
        group.addAnimation(move)
        group.addAnimation(fade)
        if hide_after:
            group.finished.connect(lambda: None if self.is_open else self.hide())
        self.group = group
        group.start()

    def open_pop(self):
        self.is_open = True
        end = self.target_pos()
        begin = end + QPoint(0, 18)
        self.on_open()
        self.move(begin)
        self.show()
        self.raise_()
        self._animate(begin, end, self.effect.opacity(), 1.0, 340, QEasingCurve.OutBack)

    def close_pop(self):
        if not self.is_open:
            return
        self.is_open = False
        self.on_close()
        current = self.pos()
        self._animate(current, current + QPoint(0, 14), self.effect.opacity(), 0.0, 190,
                      QEasingCurve.InCubic, hide_after=True)
        self.win.setFocus()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 28, 28)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0, QColor(30, 30, 32, 250))
        grad.setColorAt(1, QColor(14, 14, 16, 252))
        p.fillPath(path, QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 48), 1))
        p.drawPath(path)


class StatsPopover(Popover):
    def __init__(self, win, owner):
        super().__init__(win, owner, 340, 276)
        self.stats = SysStats()
        self.stats.sample()          # primes the CPU counter
        self.setStyleSheet("QLabel{color:white; background:transparent;}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("System")
        title.setStyleSheet("font-size:16px; font-weight:bold;")
        self.up = QLabel("")
        self.up.setStyleSheet("color:rgba(255,255,255,130); font-size:11px;")
        head.addWidget(title)
        head.addStretch()
        head.addWidget(self.up)
        lay.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(4)
        self.g_cpu = RingGauge("CPU", "#6aa7ff")
        self.g_ram = RingGauge("RAM", "#b18cff")
        self.g_disk = RingGauge("Disk", "#5fe0b0")
        for gauge in (self.g_cpu, self.g_ram, self.g_disk):
            row.addWidget(gauge)
        lay.addLayout(row)

        self.net = QLabel("")
        self.net.setAlignment(Qt.AlignCenter)
        self.net.setStyleSheet("color:rgba(255,255,255,200); font-size:12px;")
        lay.addWidget(self.net)

        self.bat = QLabel("")
        self.bat.setAlignment(Qt.AlignCenter)
        self.bat.setStyleSheet("color:rgba(255,255,255,170); font-size:12px;")
        lay.addWidget(self.bat)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)

    def target_pos(self):
        owner = self.anchor()
        o = owner.mapTo(self.win, QPoint(0, 0))
        return self.clamp(o.x() + owner.width() // 2 - self.width() // 2,
                          o.y() - self.height() - 8)

    def on_open(self):
        self.refresh()
        self.timer.start(1000)

    def on_close(self):
        self.timer.stop()

    def refresh(self):
        s = self.stats.sample()
        self.g_cpu.set_value(s["cpu"], "")
        self.g_ram.set_value(s["ram"], f"{s['ram_used']:.1f} / {s['ram_total']:.0f} GB")
        self.g_disk.set_value(s["disk"], f"{s['disk_free']:.0f} GB free")

        hours, rest = divmod(s["uptime"], 3600)
        self.up.setText(f"Up {hours}h {rest // 60}m" if s["uptime"] else "")

        net = getattr(self.win, "net_info", None)
        if net and net["kind"] == "wifi":
            state = f"online {net['ping']} ms" if net["online"] else "no internet"
            self.net.setText(f"Wi-Fi  {net['ssid']}  -  {net['signal']}%  -  {state}")
        elif net and net["kind"] == "wired":
            self.net.setText(f"Wired network  -  online {net['ping']} ms")
        elif net:
            self.net.setText("Offline" if not net["online"] else "Online")
        else:
            self.net.setText("Checking network...")

        if s["battery"] is None:
            self.bat.setText("Plugged in  -  no battery")
        else:
            percent, plugged = s["battery"]
            self.bat.setText(f"Battery {percent}%  -  {'charging' if plugged else 'on battery'}")


class ProfilePanel(Popover):
    def __init__(self, win, owner):
        super().__init__(win, owner, 356, 420)
        self.setStyleSheet("""
            QLabel { color:white; background:transparent; }
            QLineEdit { background:transparent; color:white; border:none;
                        border-bottom:1px solid transparent; padding:2px 0;
                        selection-background-color:rgba(255,255,255,70); }
            QLineEdit:hover { border-bottom:1px solid rgba(255,255,255,70); }
            QLineEdit:focus { border-bottom:1px solid rgba(255,255,255,180); }
            QPushButton#act { background:rgba(255,255,255,22); color:white; border:none;
                              border-radius:12px; padding:9px 12px; font-size:12px; }
            QPushButton#act:hover { background:rgba(255,255,255,46); }
            QPushButton#danger { background:rgba(255,255,255,22); border:none; border-radius:12px; }
            QPushButton#danger:hover { background:rgba(210,70,70,220); }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(14)

        # --- header: avatar + name + status ---
        head = QHBoxLayout()
        head.setSpacing(14)
        self.avatar = AvatarButton(68)
        self.avatar.clicked.connect(self.choose_avatar)
        head.addWidget(self.avatar)

        col = QVBoxLayout()
        col.setSpacing(2)
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(18)
        self.name_edit.setPlaceholderText("Your name")
        self.name_edit.setStyleSheet("font-size:19px; font-weight:bold;")
        self.status_edit = QLineEdit()
        self.status_edit.setMaxLength(36)
        self.status_edit.setPlaceholderText("Set a status...")
        self.status_edit.setStyleSheet("font-size:12px; color:rgba(255,255,255,160);")
        self.name_edit.editingFinished.connect(self.save_text)
        self.status_edit.editingFinished.connect(self.save_text)
        col.addStretch()
        col.addWidget(self.name_edit)
        col.addWidget(self.status_edit)
        col.addStretch()
        head.addLayout(col, 1)
        lay.addLayout(head)

        # --- stats ---
        stats = QHBoxLayout()
        stats.setSpacing(10)
        self.v_focus = self._stat(stats, "Focus today")
        self.v_pins = self._stat(stats, "Pinned apps")
        self.v_open = self._stat(stats, "Open windows")
        lay.addLayout(stats)

        # --- switches ---
        self.sw_full = ToggleSwitch()
        self.sw_task = ToggleSwitch()
        self.sw_tools = ToggleSwitch()
        self.sw_start = ToggleSwitch()
        lay.addLayout(self._row("Fullscreen", "F11", self.sw_full))
        lay.addLayout(self._row("Hide Windows taskbar", "", self.sw_task))
        lay.addLayout(self._row("Dock tools", "H", self.sw_tools))
        lay.addLayout(self._row("Start with Windows", "", self.sw_start))
        self.sw_full.toggled.connect(win.set_fullscreen)
        self.sw_task.toggled.connect(win.set_hide_taskbar)
        self.sw_tools.toggled.connect(win.set_tools_visible)
        self.sw_start.toggled.connect(self.on_startup)

        # --- buttons ---
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.b_short = self._button("  Desktop shortcut", "fa5s.external-link-alt", self.make_shortcut)
        self.b_reset = self._button("  Reset dock", "fa5s.undo", self.reset)
        self.b_quit = QPushButton()
        self.b_quit.setObjectName("danger")
        self.b_quit.setFixedSize(38, 36)
        self.b_quit.setCursor(Qt.PointingHandCursor)
        self.b_quit.setFocusPolicy(Qt.NoFocus)
        self.b_quit.setToolTip("Quit")
        self.b_quit.setIcon(qta.icon("fa5s.power-off", color="white"))
        self.b_quit.clicked.connect(win.close)
        buttons.addWidget(self.b_short, 1)
        buttons.addWidget(self.b_reset, 1)
        buttons.addWidget(self.b_quit)
        lay.addLayout(buttons)

        # --- version / updates ---
        upd = QHBoxLayout()
        self.ver_label = QLabel(f"Version {APP_VERSION}")
        self.ver_label.setStyleSheet("font-size:11px; color:rgba(255,255,255,130);")
        self.b_update = self._button("  Check for updates", "fa5s.sync-alt", win.updater.on_button)
        upd.addWidget(self.ver_label, 1)
        upd.addWidget(self.b_update)
        lay.addLayout(upd)
        win.updater.changed.connect(self.update_ui)

        # --- keyboard shortcuts cheat sheet ---
        line = QLabel()
        line.setFixedHeight(1)
        line.setStyleSheet("background:rgba(255,255,255,26);")
        lay.addWidget(line)

        heading = QLabel("KEYBOARD SHORTCUTS")
        heading.setStyleSheet("color:rgba(255,255,255,110); font-size:10px; letter-spacing:2px;")
        lay.addWidget(heading)

        keys = [("F11", "Fullscreen"), ("W", "Wallpaper"), ("S", "System"), ("T", "Focus timer"),
                ("P", "Profile"), ("R", "Running apps"), ("Ctrl+S", "Search"), ("Ctrl+1..7", "Dock apps"),
                ("H", "Dock tools"), ("F", "Friends"), ("Space", "Play / pause"), ("Up / Down", "Volume"),
                ("M", "Mute"), ("N / B", "Next / prev song"), ("Ctrl+X", "Back / close"),
                ("Ctrl+Q", "Quit")]
        cells = [f"<td><b>{k}</b>&nbsp;&nbsp;</td><td><font color='#9aa0a6'>{d}</font>&nbsp;&nbsp;&nbsp;</td>"
                 for k, d in keys]
        if len(cells) % 2:
            cells.append("<td></td><td></td>")
        rows = "".join("<tr>" + cells[i] + cells[i + 1] + "</tr>" for i in range(0, len(cells), 2))
        sheet = QLabel(f"<table cellspacing='3'>{rows}</table>")
        sheet.setStyleSheet("font-size:11px;")
        lay.addWidget(sheet)

        lay.activate()
        self.setFixedHeight(lay.sizeHint().height())

    # ---- builders ----
    def _stat(self, parent_layout, caption):
        box = QWidget()
        box.setObjectName("stat")
        box.setAttribute(Qt.WA_StyledBackground, True)
        box.setStyleSheet("#stat{background:rgba(255,255,255,16); border-radius:14px;}")
        inner = QVBoxLayout(box)
        inner.setContentsMargins(10, 9, 10, 9)
        inner.setSpacing(0)
        value = QLabel("0")
        value.setAlignment(Qt.AlignCenter)
        value.setStyleSheet("font-size:21px; font-weight:bold;")
        label = QLabel(caption)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size:10px; color:rgba(255,255,255,130);")
        inner.addWidget(value)
        inner.addWidget(label)
        parent_layout.addWidget(box, 1)
        return value

    def _row(self, text, key, switch):
        row = QHBoxLayout()
        label = QLabel(text)
        label.setStyleSheet("font-size:13px;")
        row.addWidget(label)
        if key:
            hint = QLabel(key)
            hint.setStyleSheet("color:rgba(255,255,255,110); font-size:11px;")
            row.addWidget(hint)
        row.addStretch()
        row.addWidget(switch)
        return row

    def _button(self, text, icon, slot):
        button = QPushButton(text)
        button.setObjectName("act")
        button.setIcon(qta.icon(icon, color="white"))
        button.setIconSize(QSize(13, 13))
        button.setCursor(Qt.PointingHandCursor)
        button.setFocusPolicy(Qt.NoFocus)
        button.clicked.connect(lambda checked=False: slot())
        return button

    # ---- popover hooks ----
    def target_pos(self):
        o = self.owner.mapTo(self.win, QPoint(0, 0))
        return self.clamp(o.x() + self.owner.width() - self.width(), o.y() + self.owner.height() + 10)

    def on_open(self):
        win = self.win
        self.name_edit.setText(win.profile_name())
        self.status_edit.setText(win.config.get("status", ""))
        self.avatar.set_pix(avatar_pixmap(win.config.get("avatar"), 68, win.profile_name()))
        self.v_focus.setText(str(win.focus_today()))
        self.v_pins.setText(str(len(win.config["dock"]) + len(win.config["sidebar"])))
        self.v_open.setText(str(len(win.running_panel.get_running_windows())) if os.name == "nt" else "-")
        self.sw_full.set_silent(win.isFullScreen())
        self.sw_task.set_silent(win.config.get("hide_taskbar", True))
        self.sw_tools.set_silent(win.config.get("tools_visible", False))
        self.sw_start.set_silent(startup_enabled())
        self.update_ui()

    def update_ui(self):
        u = self.win.updater
        busy = u.state in ("checking", "installing")
        text = {"checking": "  Checking...", "installing": "  Installing...",
                "available": f"  Install v{(u.info or {}).get('version', '')}"
                }.get(u.state, "  Check for updates")
        self.b_update.setText(text)
        self.b_update.setEnabled(not busy)
        self.ver_label.setText(u.message if u.state in ("uptodate", "error", "available", "installing")
                               else f"Version {APP_VERSION}")

    # ---- actions ----
    def toast(self, text, anchor, hint=""):
        tip().flash(text, anchor, "top", hint, 2800)

    def save_text(self):
        name = self.name_edit.text().strip() or NAME
        self.win.set_profile(name=name, status=self.status_edit.text().strip())
        self.avatar.set_pix(avatar_pixmap(self.win.config.get("avatar"), 68, name))
        self.win.setFocus()

    def choose_avatar(self):
        path, _ = QFileDialog.getOpenFileName(
            self.win, "Choose a profile picture", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        try:
            ASSETS.mkdir(parents=True, exist_ok=True)
            dest = ASSETS / ("avatar" + Path(path).suffix.lower())
            if Path(path).resolve() != dest.resolve():
                shutil.copyfile(path, dest)
            path = str(dest)
        except Exception as exc:
            print("Avatar copy failed:", exc)
        self.win.set_profile(avatar=path)
        self.avatar.set_pix(avatar_pixmap(path, 68, self.win.profile_name()))

    def on_startup(self, on):
        ok = set_startup(on)
        if not ok:
            self.sw_start.set_silent(not on)
            self.toast("Only works on Windows" if os.name != "nt" else "Could not change startup",
                       self.sw_start)
        else:
            self.toast("Will start with Windows" if on else "Removed from startup", self.sw_start)

    def make_shortcut(self):
        path = create_shortcut("Desktop")
        if path:
            self.toast("Shortcut added to your Desktop", self.b_short, SHORTCUT_NAME)
        else:
            self.toast("Only works on Windows" if os.name != "nt" else "Could not create the shortcut",
                       self.b_short)

    def reset(self):
        self.win.reset_pins()
        self.toast("Dock and sidebar reset", self.b_reset)


# ----------------------------- Running apps drawer -----------------------------

# ----------------------------- Friends (Firebase Realtime Database) -----------------------------

def normalize_db_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    url = url.split("?")[0].rstrip("/")
    if url.endswith(".json"):
        url = url[:-5].rstrip("/")
    return url


def rtdb(base, path, method="GET", data=None, timeout=8):
    """Tiny Firebase Realtime Database REST client (no extra packages needed)."""
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(f"{base}/{path}.json", data=body, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else None


CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_friend_code():
    return "".join(secrets.choice(CODE_CHARS) for _ in range(6))


def clean_code(text):
    return "".join(c for c in (text or "").upper() if c in CODE_CHARS)[:6]


def friends_sync(base, me, name, status):
    """Heartbeat + download friends and requests. Runs in a worker thread."""
    put = rtdb(base, f"users/{me}", "PUT",
               {"name": name, "status": status, "seen": {".sv": "timestamp"}})
    now = put.get("seen") if isinstance(put, dict) else None
    if not isinstance(now, (int, float)):
        now = int(time.time() * 1000)
    friends, requests = [], []
    for code in (rtdb(base, f"friends/{me}") or {}):
        info = rtdb(base, f"users/{code}") or {}
        friends.append({"code": code, "name": info.get("name") or code,
                        "status": info.get("status") or "", "seen": info.get("seen") or 0})
    for code, info in (rtdb(base, f"requests/{me}") or {}).items():
        requests.append({"code": code, "name": (info or {}).get("name") or code})
    friends.sort(key=lambda f: (-(now - f["seen"] < 90000), f["name"].lower()))
    return {"now": now, "friends": friends, "requests": requests}


def friends_add(base, me, my_name, code):
    if code == me:
        return "That is your own code"
    if len(code) != 6:
        return "A code has 6 letters/numbers"
    if not rtdb(base, f"users/{code}"):
        return "No one has this code"
    if rtdb(base, f"friends/{me}/{code}"):
        return "Already your friend"
    if rtdb(base, f"requests/{me}/{code}"):          # they asked first -> just accept
        friends_accept(base, me, code)
        return "Friend added!"
    rtdb(base, f"requests/{code}/{me}", "PUT", {"name": my_name})
    return "Request sent"


def friends_accept(base, me, code):
    rtdb(base, f"friends/{me}/{code}", "PUT", True)
    rtdb(base, f"friends/{code}/{me}", "PUT", True)
    rtdb(base, f"requests/{me}/{code}", "DELETE")
    return "Friend added!"


def friends_decline(base, me, code):
    rtdb(base, f"requests/{me}/{code}", "DELETE")
    return "Request removed"


def friends_remove(base, me, code):
    rtdb(base, f"friends/{me}/{code}", "DELETE")
    rtdb(base, f"friends/{code}/{me}", "DELETE")
    return "Friend removed"


class FriendsService(QObject):
    changed = Signal()

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.friends, self.requests = [], []
        self.now = 0
        self.error = ""
        self.busy = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)

    @property
    def base(self):
        return normalize_db_url(self.win.config.get("friend_db_url") or FIREBASE_URL)

    @property
    def configured(self):
        return bool(self.base)

    def my_code(self):
        cfg = self.win.config
        if not cfg.get("friend_code"):
            cfg["friend_code"] = new_friend_code()
            self.win.save_config()
        return cfg["friend_code"]

    def start(self):
        if self.configured:
            self.timer.start(30000)
            self.refresh()
        else:
            self.timer.stop()

    def online(self, friend):
        return self.now - friend["seen"] < 90000

    def refresh(self):
        if not self.configured or self.busy:
            return
        self.busy = True
        cfg = self.win.config
        run_job(friends_sync, self._synced, self.base, self.my_code(),
                self.win.profile_name(), cfg.get("status", ""))

    def _synced(self, result, error):
        self.busy = False
        if error is not None:
            self.error = "No connection to the friends server"
        else:
            self.error = ""
            old = {r["code"] for r in self.requests}
            self.friends, self.requests, self.now = result["friends"], result["requests"], result["now"]
            if any(r["code"] not in old for r in self.requests):
                tip().flash("New friend request!", self.win.friends_btn, "bottom", "Press F", 4000)
        self.changed.emit()

    def act(self, fn, *args, done=None):
        if not self.configured:
            return
        me = self.my_code()

        def finished(result, error):
            msg = result if error is None else "Could not reach the server"
            if done:
                done(msg)
            self.refresh()
        run_job(fn, finished, self.base, me, *args)


class FriendsButton(QPushButton):
    """Round button next to the profile chip, with a red badge for pending requests."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(40, 40)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.badge = 0
        self.hover = False
        self.icon_ = qta.icon("fa5s.user-friends", color="#222")

    def set_badge(self, n):
        self.badge = n
        self.update()

    def enterEvent(self, event):
        self.hover = True
        self.update()
        tip().request("Friends", self, "bottom", "F")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover = False
        self.update()
        tip().cancel()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        tip().cancel()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 235 if self.hover else 200))
        p.drawEllipse(QRectF(self.rect()).adjusted(1, 1, -1, -1))
        self.icon_.paint(p, QRect(11, 11, 18, 18))
        if self.badge:
            p.setBrush(QColor(235, 70, 70))
            p.drawEllipse(QRectF(self.width() - 15, 0, 15, 15))
            p.setPen(QColor("white"))
            font = QFont(QApplication.font())
            font.setPixelSize(10)
            font.setBold(True)
            p.setFont(font)
            p.drawText(QRectF(self.width() - 15, 0, 15, 15), Qt.AlignCenter, str(min(self.badge, 9)))


class FriendsPanel(Popover):
    def __init__(self, win, owner):
        super().__init__(win, owner, 360, 480)
        self.service = win.friends
        self.setStyleSheet("""
            QLabel { color:white; background:transparent; }
            QLineEdit { background:rgba(255,255,255,18); color:white; border:1px solid rgba(255,255,255,40);
                        border-radius:12px; padding:9px 12px; font-size:13px; }
            QLineEdit:focus { border:1px solid rgba(255,255,255,150); }
            QPushButton#act { background:rgba(255,255,255,26); color:white; border:none;
                              border-radius:12px; padding:9px 14px; font-size:12px; }
            QPushButton#act:hover { background:rgba(255,255,255,52); }
            QPushButton#ok { background:rgba(84,196,140,200); border:none; border-radius:13px; }
            QPushButton#ok:hover { background:rgba(84,196,140,255); }
            QPushButton#no { background:rgba(255,255,255,26); border:none; border-radius:13px; }
            QPushButton#no:hover { background:rgba(210,70,70,220); }
            QScrollArea { background:transparent; border:none; }
            QScrollBar:vertical { width:0px; }
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("Friends")
        title.setStyleSheet("font-size:19px; font-weight:bold;")
        self.state = QLabel("")
        self.state.setStyleSheet("color:rgba(255,255,255,120); font-size:11px;")
        head.addWidget(title)
        head.addStretch()
        head.addWidget(self.state)
        lay.addLayout(head)

        # ---- setup view (no server yet) ----
        self.setup = QWidget()
        sl = QVBoxLayout(self.setup)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(10)
        info = QLabel("Friends need a small server (free).\n"
                      "Easiest: run friends_server.py on any PC/host your friends can reach,\n"
                      "then paste its address below, e.g. http://1.2.3.4:8080\n"
                      "Or use a Firebase Realtime Database link.\n"
                      "See FRIENDS_SETUP.txt. Everyone uses the same address.")
        info.setWordWrap(True)
        info.setStyleSheet("font-size:12px; color:rgba(255,255,255,170);")
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://your-project-default-rtdb.firebaseio.com")
        self.url_save = QPushButton("Connect")
        self.url_save.setObjectName("act")
        self.url_save.setCursor(Qt.PointingHandCursor)
        self.url_save.setFocusPolicy(Qt.NoFocus)
        self.url_save.clicked.connect(self.save_url)
        sl.addWidget(info)
        sl.addWidget(self.url_edit)
        sl.addWidget(self.url_save)
        sl.addStretch()
        lay.addWidget(self.setup, 1)

        # ---- main view ----
        self.main = QWidget()
        ml = QVBoxLayout(self.main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(10)

        mine = QHBoxLayout()
        cap = QLabel("Your code")
        cap.setStyleSheet("font-size:12px; color:rgba(255,255,255,140);")
        self.code_label = QLabel("")
        self.code_label.setStyleSheet("font-size:20px; font-weight:bold; letter-spacing:3px;")
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("act")
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setFocusPolicy(Qt.NoFocus)
        self.copy_btn.clicked.connect(self.copy_code)
        mine.addWidget(cap)
        mine.addSpacing(6)
        mine.addWidget(self.code_label)
        mine.addStretch()
        mine.addWidget(self.copy_btn)
        ml.addLayout(mine)

        add = QHBoxLayout()
        self.code_edit = QLineEdit()
        self.code_edit.setMaxLength(6)
        self.code_edit.setPlaceholderText("Friend's code")
        self.code_edit.returnPressed.connect(self.add_friend)
        self.add_btn = QPushButton("Add")
        self.add_btn.setObjectName("act")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.setFocusPolicy(Qt.NoFocus)
        self.add_btn.clicked.connect(self.add_friend)
        add.addWidget(self.code_edit, 1)
        add.addWidget(self.add_btn)
        ml.addLayout(add)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.list_host = QWidget()
        self.list_host.setStyleSheet("background:transparent;")
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(6)
        self.scroll.setWidget(self.list_host)
        ml.addWidget(self.scroll, 1)

        self.reset_link = QPushButton("Change server")
        self.reset_link.setFlat(True)
        self.reset_link.setCursor(Qt.PointingHandCursor)
        self.reset_link.setFocusPolicy(Qt.NoFocus)
        self.reset_link.setStyleSheet("color:rgba(255,255,255,90); font-size:10px; border:none;")
        self.reset_link.clicked.connect(self.change_server)
        ml.addWidget(self.reset_link, 0, Qt.AlignRight)
        lay.addWidget(self.main, 1)

        self.service.changed.connect(self.rebuild)

    # ---- popover hooks ----
    def target_pos(self):
        o = self.owner.mapTo(self.win, QPoint(0, 0))
        return self.clamp(o.x() + self.owner.width() - self.width(), o.y() + self.owner.height() + 10)

    def on_open(self):
        self.rebuild()
        self.service.refresh()

    # ---- helpers ----
    def toast(self, text, anchor=None):
        tip().flash(text, anchor or self.add_btn, "top", "", 2400)

    def clear_rows(self):
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def make_row(self, name, sub, online, buttons=(), code=None):
        row = QWidget()
        row.setObjectName("row")
        row.setAttribute(Qt.WA_StyledBackground, True)
        row.setStyleSheet("#row{background:rgba(255,255,255,14); border-radius:14px;}")
        hl = QHBoxLayout(row)
        hl.setContentsMargins(10, 8, 10, 8)
        hl.setSpacing(10)
        pic = QLabel()
        pic.setPixmap(avatar_pixmap(None, 34, name))
        pic.setFixedSize(34, 34)
        hl.addWidget(pic)
        col = QVBoxLayout()
        col.setSpacing(0)
        top = QLabel(name)
        top.setStyleSheet("font-size:13px; font-weight:bold;")
        bottom = QLabel(sub)
        bottom.setStyleSheet("font-size:11px; color:rgba(255,255,255,130);")
        col.addWidget(top)
        col.addWidget(bottom)
        hl.addLayout(col, 1)
        if online is not None:
            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet("border-radius:5px; background:%s;" %
                              ("rgb(84,196,140)" if online else "rgba(255,255,255,60)"))
            hl.addWidget(dot)
        for obj, icon, slot in buttons:
            b = QPushButton()
            b.setObjectName(obj)
            b.setFixedSize(26, 26)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setIcon(qta.icon(icon, color="white"))
            b.clicked.connect(lambda checked=False, s=slot: s())
            hl.addWidget(b)
        if code:
            row.setContextMenuPolicy(Qt.CustomContextMenu)
            row.customContextMenuRequested.connect(
                lambda pos, r=row, c=code, n=name: self.friend_menu(r.mapToGlobal(pos), c, n))
        return row

    def friend_menu(self, pos, code, name):
        menu = styled_menu(self)
        menu.addAction(f"Remove {name}", lambda: self.service.act(
            friends_remove, code, done=self.toast))
        menu.exec(pos)

    def rebuild(self):
        svc = self.service
        configured = svc.configured
        self.setup.setVisible(not configured)
        self.main.setVisible(configured)
        if not configured:
            self.state.setText("")
            return
        self.code_label.setText(svc.my_code())
        self.state.setText(svc.error or ("syncing..." if svc.busy else ""))
        self.clear_rows()
        for r in svc.requests:
            self.list_lay.addWidget(self.make_row(
                r["name"], "wants to be your friend", None,
                [("ok", "fa5s.check", lambda c=r["code"]: svc.act(friends_accept, c, done=self.toast)),
                 ("no", "fa5s.times", lambda c=r["code"]: svc.act(friends_decline, c, done=self.toast))]))
        for f in svc.friends:
            on = svc.online(f)
            self.list_lay.addWidget(self.make_row(
                f["name"], (f["status"] or ("online" if on else "offline")), on, code=f["code"]))
        if not svc.requests and not svc.friends:
            empty = QLabel("No friends yet.\nShare your code or add theirs.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color:rgba(255,255,255,110); font-size:12px; padding:30px;")
            self.list_lay.addWidget(empty)
        self.list_lay.addStretch()

    # ---- actions ----
    def save_url(self):
        url = normalize_db_url(self.url_edit.text())
        if not url:
            return
        self.win.config["friend_db_url"] = url
        self.win.save_config()
        self.service.start()
        self.rebuild()

    def change_server(self):
        self.win.config["friend_db_url"] = ""
        self.win.save_config()
        self.service.friends, self.service.requests = [], []
        self.service.start()
        self.win.friends_btn.set_badge(0)
        self.url_edit.setText("")
        self.rebuild()

    def copy_code(self):
        QApplication.clipboard().setText(self.service.my_code())
        self.toast("Code copied", self.copy_btn)

    def add_friend(self):
        code = clean_code(self.code_edit.text())
        if not code:
            return
        self.code_edit.clear()
        self.service.act(friends_add, self.win.profile_name(), code, done=self.toast)


# ----------------------------- Updates (GitHub) -----------------------------

def parse_version(text):
    return tuple(int(x) for x in re.findall(r"\d+", str(text))[:4])


def fetch_update_info(url):
    req = urllib.request.Request(url, headers={"User-Agent": "GlassDesktop-updater",
                                               "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        info = json.loads(resp.read().decode("utf-8"))
    if not isinstance(info, dict) or "version" not in info:
        raise ValueError("bad version.json")
    return info


def download_update(info):
    """Download the new main.py, verify it, and return its bytes."""
    url = info.get("url")
    if not url:
        raise ValueError("version.json has no url")
    req = urllib.request.Request(url, headers={"User-Agent": "GlassDesktop-updater"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    want = (info.get("sha256") or "").lower().strip()
    if want and hashlib.sha256(data).hexdigest() != want:
        raise ValueError("Checksum mismatch - update refused")
    compile(data, "main.py", "exec")               # must at least be valid Python
    return data


class UpdateService(QObject):
    changed = Signal()

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.state = "idle"        # idle | checking | uptodate | available | installing | error
        self.info = None
        self.message = ""
        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.check(silent=True))

    @property
    def url(self):
        return (self.win.config.get("update_url") or UPDATE_URL or "").strip()

    def on_button(self):
        if self.state == "available":
            self.install()
        else:
            self.check()

    def start(self):
        if self.url:
            QTimer.singleShot(6000, lambda: self.check(silent=True))
            self.timer.start(6 * 3600 * 1000)

    def check(self, silent=False):
        if not self.url:
            self.state, self.message = "error", "No update link set (UPDATE_URL)"
            self.changed.emit()
            return
        if self.state in ("checking", "installing"):
            return
        self.state = "checking"
        self.changed.emit()

        def done(info, error):
            if error is not None:
                self.state = "error"
                self.message = "Could not check for updates"
            elif parse_version(info["version"]) > parse_version(APP_VERSION):
                self.state, self.info = "available", info
                self.message = "Update available: v" + str(info["version"])
                if silent:
                    tip().flash(f"Update v{info['version']} is ready", self.win.chip, "bottom",
                                "Open your profile to install it", 6000)
            else:
                self.state, self.message = "uptodate", "You have the latest version"
            self.changed.emit()
        run_job(fetch_update_info, done, self.url)

    def install(self):
        if self.state != "available" or not self.info:
            return
        if FROZEN:                                    # an .exe can't replace itself
            webbrowser.open(self.info.get("page") or self.info.get("url") or self.url)
            return
        self.state, self.message = "installing", "Downloading..."
        self.changed.emit()

        def done(data, error):
            if error is not None:
                self.state, self.message = "error", "Update failed: " + str(error)[:60]
                self.changed.emit()
                return
            try:
                script = Path(__file__).resolve()
                shutil.copyfile(script, script.with_suffix(".py.bak"))
                tmp = script.with_suffix(".py.new")
                tmp.write_bytes(data)
                os.replace(tmp, script)
            except Exception as exc:
                self.state, self.message = "error", "Could not write update: " + str(exc)[:50]
                self.changed.emit()
                return
            subprocess.Popen([sys.executable, str(script)] + sys.argv[1:])
            self.win.close()
        run_job(download_update, done, self.info)


class SnapshotBlurOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap = QPixmap()
        self._amount = 1.0
        self.anim = QPropertyAnimation(self, b"amountT", self)
        self._on_done = None
        self.anim.finished.connect(self._finished)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.hide()

    def _get_amount(self): return self._amount
    def _set_amount(self, v): self._amount = v; self.update()
    amountT = Property(float, _get_amount, _set_amount)

    def set_pixmap(self, pixmap):
        self.pixmap = pixmap
        self.update()

    def fade(self, end, duration=300, on_done=None):
        self.anim.stop()
        self._on_done = on_done
        self.anim.setDuration(duration)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.setStartValue(self._amount)
        self.anim.setEndValue(end)
        self.anim.start()

    def _finished(self):
        callback, self._on_done = self._on_done, None
        if callback:
            callback()

    def paintEvent(self, event):
        if self.pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setOpacity(max(0.0, min(1.0, self._amount)))
        painter.drawPixmap(self.rect(), self.pixmap)


class HandleLine(QPushButton):
    """The Running Apps button: just a thin straight line at the top."""
    W, H = 150, 20
    LINE_W, LINE_H = 64, 4

    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self._t = 0.0
        self.anim = QPropertyAnimation(self, b"hoverT", self)

    def _get_t(self): return self._t
    def _set_t(self, v): self._t = v; self.update()
    hoverT = Property(float, _get_t, _set_t)

    def _go(self, end):
        self.anim.stop()
        self.anim.setDuration(240)
        self.anim.setEasingCurve(QEasingCurve.OutBack)
        self.anim.setStartValue(self._t)
        self.anim.setEndValue(end)
        self.anim.start()

    def enterEvent(self, event):
        self._go(1.0)
        opened = getattr(self.parent(), "opened", False)
        tip().request("Close" if opened else "Running apps", self,
                      "top" if opened else "bottom",
                      "" if opened else "See and switch open windows")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._go(0.0)
        tip().cancel()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        tip().cancel()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        t = self._t
        w = self.LINE_W + 26 * t
        h = self.LINE_H + 1.2 * t
        x = (self.width() - w) / 2
        y = (self.height() - h) / 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 70))
        painter.drawRoundedRect(QRectF(x, y + 1.2, w, h), h / 2, h / 2)
        painter.setBrush(QColor(255, 255, 255, int(200 + 55 * min(1.0, t))))
        painter.drawRoundedRect(QRectF(x, y, w, h), h / 2, h / 2)


class HScrollArea(QScrollArea):
    """Mouse wheel scrolls horizontally."""
    def wheelEvent(self, event):
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - event.angleDelta().y())
        event.accept()


class AppCard(QWidget):
    def __init__(self, app, icon, on_click, on_close, on_pin=None):
        super().__init__()
        self.on_click = on_click
        self.setObjectName("appCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(155, 175)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QWidget#appCard {
                background:rgba(30,30,30,175);
                border:1px solid rgba(255,255,255,65);
                border-radius:18px;
            }
            QWidget#appCard:hover { background:rgba(60,60,60,200); }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(5)
        icon_label = QLabel()
        icon_label.setFixedSize(55, 55)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setPixmap(icon.pixmap(48, 48))
        top.addWidget(icon_label)
        top.addStretch()

        small = """
            QToolButton { color:white; background:rgba(255,255,255,25);
                          border:none; border-radius:13px; font-size:18px; padding:0; }
            QToolButton:hover { background:%s; }
        """

        if on_pin:
            self.pin_btn = QToolButton()
            self.pin_btn.setFixedSize(27, 27)
            self.pin_btn.setCursor(Qt.PointingHandCursor)
            self.pin_btn.setToolTip("Pin to dock")
            self.pin_btn.setIcon(qta.icon("fa5s.thumbtack", color="white"))
            self.pin_btn.setIconSize(QSize(13, 13))
            self.pin_btn.setStyleSheet(small % "rgba(70,140,255,230)")
            self.pin_btn.clicked.connect(lambda: self._pin(on_pin))
            top.addWidget(self.pin_btn)

        close_app = QToolButton()
        close_app.setText("×")
        close_app.setFixedSize(27, 27)
        close_app.setCursor(Qt.PointingHandCursor)
        close_app.setStyleSheet(small % "rgba(190,55,55,220)")
        close_app.clicked.connect(on_close)
        top.addWidget(close_app)
        layout.addLayout(top)

        title = app["title"]
        name = QLabel(title if len(title) <= 60 else title[:57] + "...")
        name.setAlignment(Qt.AlignCenter)
        name.setWordWrap(True)
        name.setToolTip(title)
        name.setStyleSheet("color:white; font-size:11px; background:transparent; border:none;")
        layout.addWidget(name)
        layout.addStretch()

    def _pin(self, on_pin):
        ok = on_pin()
        self.pin_btn.setIcon(qta.icon("fa5s.check" if ok else "fa5s.times", color="white"))
        self.pin_btn.setToolTip("Pinned!" if ok else "Dock is full")
        if ok:
            self.pin_btn.setEnabled(False)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.on_click()
        event.accept()


class RunningAppsDrawer(QWidget):
    COLLAPSED_W = HandleLine.W
    COLLAPSED_H = HandleLine.H
    TOP_MARGIN = 6

    def __init__(self, parent):
        super().__init__(parent)
        self.win = parent
        self.opened = False
        self.anim = None
        self.apps = []
        self._sig = None

        self.setObjectName("runningDrawer")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(0, 0)
        self.setStyleSheet("""
            QLabel { color:white; background:transparent; }
            QToolButton {
                color:white; background:rgba(35,35,35,210);
                border:1px solid rgba(255,255,255,75); border-radius:12px; padding:7px;
            }
            QToolButton:hover { background:rgba(85,85,85,235); }
            QScrollArea { background:transparent; border:none; }
            QScrollBar:horizontal { height:6px; background:transparent; }
            QScrollBar::handle:horizontal {
                background:rgba(255,255,255,110); border-radius:3px; min-width:35px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0px; }
        """)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(35, 28, 35, 40)
        self.main_layout.setSpacing(22)

        header = QHBoxLayout()
        self.title_label = QLabel("RUNNING APPLICATIONS")
        self.title_label.setStyleSheet("font-size:17px; font-weight:bold; letter-spacing:2px;")
        self.count_label = QLabel("0 APPS")
        self.count_label.setStyleSheet("color:rgba(255,255,255,170); font-size:11px;")

        self.close_button = QToolButton()
        self.close_button.setText("×")
        self.close_button.setFixedSize(38, 38)
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.setStyleSheet("QToolButton{font-size:25px; border-radius:19px; padding:0;}")
        self.close_button.clicked.connect(self.toggle)

        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(self.count_label)
        header.addSpacing(15)
        header.addWidget(self.close_button)
        self.main_layout.addLayout(header)

        self.scroll = HScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.apps_container = QWidget()
        self.apps_container.setStyleSheet("background:transparent;")
        self.apps_layout = QHBoxLayout(self.apps_container)
        self.apps_layout.setContentsMargins(5, 10, 5, 10)
        self.apps_layout.setSpacing(16)
        self.apps_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.scroll.setWidget(self.apps_container)
        self.main_layout.addWidget(self.scroll, 1)

        self.handle = HandleLine(self)
        self.handle.clicked.connect(self.toggle)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_if_open)
        self.timer.start(3000)

        self.set_content_visible(False)
        self.update_position()
        self.show()
        self.raise_()

    # ---- geometry ----

    def collapsed_rect(self):
        x = (self.win.width() - self.COLLAPSED_W) // 2
        return QRect(x, self.TOP_MARGIN, self.COLLAPSED_W, self.COLLAPSED_H)

    def set_content_visible(self, visible):
        for widget in (self.title_label, self.count_label, self.close_button, self.scroll):
            widget.setVisible(visible)

    def update_position(self):
        if not self.win:
            return
        self.setGeometry(self.win.rect() if self.opened else self.collapsed_rect())
        self.set_content_visible(self.opened)
        self.raise_()
        self.handle.raise_()

    def resizeEvent(self, event):
        self.handle.move((self.width() - HandleLine.W) // 2, self.height() - HandleLine.H)
        super().resizeEvent(event)

    def paintEvent(self, event):
        if self.height() <= 40:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        radius = 0 if self.win.isFullScreen() else 30
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        painter.fillPath(path, QColor(12, 12, 12, 150))

    def mousePressEvent(self, event):
        if self.opened and event.button() == Qt.LeftButton:
            self.toggle()
        event.accept()

    # ---- open / close ----

    def toggle(self):
        self.opened = not self.opened
        if self.opened:
            self.win.close_popover()
            self.refresh(force=True)
            self.win.set_background_blur(True)
        else:
            self.set_content_visible(False)
            self.win.set_background_blur(False)
        self.animate()

    def animate(self):
        if self.anim:
            self.anim.stop()
            self.anim.deleteLater()

        target = self.win.rect() if self.opened else self.collapsed_rect()
        self.anim = QPropertyAnimation(self, b"geometry", self)
        self.anim.setDuration(380)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.setStartValue(self.geometry())
        self.anim.setEndValue(target)
        self.anim.finished.connect(self._anim_done)
        self.anim.start()

    def _anim_done(self):
        self.update_position()
        if self.opened:
            self.play_cards_intro()

    def play_cards_intro(self):
        # Cards pop in one after another.
        for i in range(self.apps_layout.count()):
            widget = self.apps_layout.itemAt(i).widget()
            if widget is not None:
                fade_slide(widget, 0, 34, delay=40 + i * 55, duration=480,
                           curve=QEasingCurve.OutBack)

    # ---- running windows (Windows only) ----

    def get_running_windows(self):
        if os.name != "nt":
            return []

        user32 = user32_api()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD)
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        try:
            dwmapi = ctypes.WinDLL("dwmapi")
            dwmapi.DwmGetWindowAttribute.argtypes = [
                wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
            ]
            dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
        except OSError:
            dwmapi = None

        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        GW_OWNER = 4
        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_APPWINDOW = 0x00040000
        DWMWA_CLOAKED = 14
        ignored_titles = {"Program Manager"}
        own_pid = os.getpid()
        found = []

        def callback(hwnd, lparam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                if user32.GetWindow(hwnd, GW_OWNER):
                    return True

                ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                if ex_style & WS_EX_TOOLWINDOW and not ex_style & WS_EX_APPWINDOW:
                    return True

                if dwmapi:
                    cloaked = wintypes.DWORD(0)
                    if dwmapi.DwmGetWindowAttribute(
                        hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
                    ) == 0 and cloaked.value:
                        return True

                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                title = buffer.value.strip()
                if not title or title in ignored_titles:
                    return True

                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == own_pid:
                    return True

                exe_path = ""
                process = kernel32.OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
                )
                if process:
                    try:
                        path_buffer = ctypes.create_unicode_buffer(1024)
                        path_size = wintypes.DWORD(len(path_buffer))
                        if kernel32.QueryFullProcessImageNameW(
                            process, 0, path_buffer, ctypes.byref(path_size)
                        ):
                            exe_path = path_buffer.value
                    finally:
                        kernel32.CloseHandle(process)

                found.append({"hwnd": int(hwnd), "title": title, "exe": exe_path})
            except Exception as exc:
                print("Window enum error:", exc)
            return True

        cb = callback_type(callback)
        user32.EnumWindows(cb, 0)
        return found

    def icon_for(self, exe):
        cache = self.__dict__.setdefault("_icons", {})     # icons are slow to fetch, keep them
        icon = cache.get(exe)
        if icon is None:
            icon = cache[exe] = file_icon(exe)
        return icon

    def clear_items(self):
        while self.apps_layout.count():
            item = self.apps_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def refresh_if_open(self):
        if self.opened:
            self.refresh()

    def refresh(self, force=False):
        if not self.opened:
            return

        windows = list({app["hwnd"]: app for app in self.get_running_windows()}.values())

        signature = tuple((app["hwnd"], app["title"]) for app in windows)
        if signature == self._sig and not force:
            return
        self._sig = signature
        self.apps = windows

        self.clear_items()
        self.count_label.setText(f"{len(windows)} APPS")

        if not windows:
            empty = QLabel("No running applications found")
            empty.setStyleSheet("color:rgba(255,255,255,160); font-size:14px;")
            self.apps_layout.addWidget(empty)
            return

        for app in windows:
            has_exe = bool(app["exe"]) and os.path.exists(app["exe"])
            if has_exe:
                icon = self.icon_for(app["exe"])
            else:
                icon = self.style().standardIcon(QStyle.SP_ComputerIcon)

            hwnd = app["hwnd"]
            pin = None
            if has_exe:
                exe = app["exe"]
                pin = lambda e=exe: self.win.dock.pin_item(
                    {"label": Path(e).stem, "target": e, "exe": None, "qta": None})

            card = AppCard(
                app, icon,
                on_click=lambda h=hwnd: self.activate_window(h),
                on_close=lambda checked=False, h=hwnd: self.close_window(h),
                on_pin=pin,
            )
            self.apps_layout.addWidget(card)

    def activate_window(self, hwnd):
        if os.name != "nt":
            return
        user32 = user32_api()
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        QTimer.singleShot(0, lambda: self.opened and self.toggle())

    def close_window(self, hwnd):
        if os.name != "nt":
            return
        user32_api().PostMessageW(hwnd, 0x0010, 0, 0)
        QTimer.singleShot(700, lambda: self.refresh(force=True))


# ----------------------------- Main window -----------------------------

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        flags = Qt.FramelessWindowHint | Qt.Window
        if STAY_ON_DESKTOP:
            flags |= Qt.WindowStaysOnBottomHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("My Desktop")
        self.resize(1280, 720)

        self.first_run = not CONFIG_PATH.exists()
        self.config = load_config()
        self._taskbar_hidden = False
        if self.config.get("taskbar_hidden"):          # last run ended without restoring it
            set_taskbar_visible(True)
            self.config["taskbar_hidden"] = False
        self.net_info = None
        self._net_worker = None
        self.net_timer = QTimer(self)
        self.net_timer.timeout.connect(self.poll_network)
        self.wall = None
        self.wall_blur = None
        self.wall_old = None          # previous wallpaper during the cross-fade
        self.wall_blur_old = None
        self.fade_t = 1.0
        self._wall_anim = None
        self.popover = None
        self.drag = None
        self._intro_played = False
        self.live = False
        self.par_x = 0.0
        self.char_base = QPoint(0, 0)
        self.char_src = QPixmap(str(CHARACTER)) if CHARACTER.exists() else QPixmap()
        self.setFocusPolicy(Qt.StrongFocus)
        self.focus = FocusTimer()

        root = QGridLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setHorizontalSpacing(20)
        root.setVerticalSpacing(20)

        self.sidebar = self.build_sidebar()
        self.main_panel = self.build_main()
        self.dock = self.build_dock()
        for panel in (self.sidebar, self.main_panel, self.dock):
            panel._set_intro(0.0)        # glass fades in during the intro animation
        self.dock.set_tools_visible(self.config.get("tools_visible", False), animate=False)

        root.addWidget(self.sidebar, 0, 0)
        root.addWidget(self.main_panel, 0, 1)
        root.addWidget(self.dock, 1, 0, 1, 2, Qt.AlignHCenter)     # centred on the whole window
        root.setRowStretch(0, 1)
        root.setRowStretch(1, 0)
        root.setColumnStretch(0, 0)
        root.setColumnStretch(1, 1)

        self.character = QLabel(self)
        self.character.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.character.stackUnder(self.dock)

        self.blur_overlay = SnapshotBlurOverlay(self)
        self.blur_overlay.setGeometry(self.rect())

        # Clock ticks and ambient motion start after the intro animation.
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.ambient = QTimer(self)
        self.ambient.timeout.connect(self.ambient_tick)

        # floating panels (opened from the dock tools / the profile chip)
        self.stats_pop = StatsPopover(self, self.btn_stats)
        self.friends = FriendsService(self)
        self.updater = UpdateService(self)
        self.friends_pop = FriendsPanel(self, self.friends_btn)
        self.friends_btn.clicked.connect(lambda: self.toggle_popover(self.friends_pop))
        self.friends.changed.connect(lambda: self.friends_btn.set_badge(len(self.friends.requests)))
        self.profile = ProfilePanel(self, self.chip)
        self.chip.clicked.connect(lambda: self.toggle_popover(self.profile))
        self.focus.changed.connect(self.focus_changed)
        self.focus.finished.connect(self.focus_finished)
        self.focus_changed()
        self.apply_profile()

        self.running_panel = RunningAppsDrawer(self)
        self.tick()
        QApplication.instance().installEventFilter(self)

    # ---- config / profile ----

    def save_config(self):
        save_config(self.config)

    def reset_pins(self):
        self.config["sidebar"] = copy.deepcopy(SIDEBAR_DEFAULT)
        self.config["dock"] = copy.deepcopy(DOCK_DEFAULT)
        self.save_config()
        self.sidebar.rebuild()
        self.dock.rebuild()

    def profile_name(self):
        return self.config.get("name") or NAME

    def apply_profile(self):
        name = self.profile_name()
        self.chip.set_profile(name, self.config.get("avatar"), self.config.get("status", ""))
        self.hello.setText(f"Hi {name}!!")
        self.hello.update()

    def set_profile(self, name=None, status=None, avatar=None):
        if name is not None:
            self.config["name"] = name
        if status is not None:
            self.config["status"] = status
        if avatar is not None:
            self.config["avatar"] = avatar
        self.save_config()
        self.apply_profile()

    def open_app_search(self):
        dialog = AppSearchDialog(self)
        dialog.exec()

    # ---- popovers ----

    def toggle_popover(self, pop):
        current = self.popover
        if current is not None and current.is_open:
            current.close_pop()
        if current is pop:
            self.popover = None
            return
        if self.running_panel.opened:
            self.running_panel.toggle()
        self.popover = pop
        pop.open_pop()

    def close_popover(self):
        if self.popover is not None and self.popover.is_open:
            self.popover.close_pop()
        self.popover = None

    def eventFilter(self, obj, event):
        # first click after coming back from another app: take focus right away
        if event.type() == QEvent.MouseButtonPress and not self.isActiveWindow():
            try:
                if isinstance(obj, QWidget) and obj.window() is self:
                    self.activateWindow()
                    self.setFocus(Qt.MouseFocusReason)
            except Exception:
                pass

        # click outside an open popover closes it
        if event.type() == QEvent.MouseButtonPress and self.popover is not None \
                and self.popover.is_open:
            try:
                if isinstance(obj, QWidget) and obj.window() is self:
                    point = event.globalPosition().toPoint()
                    pop, owner = self.popover, self.popover.anchor()
                    inside = pop.rect().contains(pop.mapFromGlobal(point))
                    on_owner = owner.rect().contains(owner.mapFromGlobal(point))
                    if not inside and not on_owner:
                        self.close_popover()
            except Exception:
                pass
        return False

    # ---- dock tools (system / focus / wallpaper) ----

    def set_tools_visible(self, on, save=True):
        on = bool(on)
        self.config["tools_visible"] = on
        if save:
            self.save_config()
        self.dock.set_tools_visible(on)
        if not on and self.popover is self.stats_pop and self.stats_pop.is_open:
            QTimer.singleShot(0, self.stats_pop.reposition)    # re-hang it from the dock
        if self.popover is self.profile and self.profile.is_open:
            self.profile.sw_tools.set_silent(on)

    def toggle_tools(self):
        self.set_tools_visible(not self.config.get("tools_visible", False))

    def visible_anchor(self, button):
        return button if button.isVisible() else self.dock

    # ---- focus timer ----

    def focus_today(self):
        done = self.config["focus_done"]
        return done["count"] if done["date"] == time.strftime("%Y-%m-%d") else 0

    def focus_changed(self):
        state = self.focus.state
        previous = getattr(self, "_focus_state", "idle")
        self._focus_state = state
        if state == "running" and previous != "running" \
                and not self.config.get("tools_visible", False) and self.live:
            self.set_tools_visible(True, save=False)      # show the countdown while it runs
        btn = self.btn_focus
        btn.hide_icon = state != "idle"
        if state == "idle":
            btn.label = "Focus timer"
            btn.hint = f"{self.focus.total // 60} min  -  click to start  (T)"
        elif state == "running":
            btn.label = f"Focus  {self.focus.mmss()}"
            btn.hint = "Click to pause"
        else:
            btn.label = f"Paused  {self.focus.mmss()}"
            btn.hint = "Click to resume"
        btn.update()

    def focus_finished(self):
        QApplication.beep()
        today = time.strftime("%Y-%m-%d")
        done = self.config["focus_done"]
        if done["date"] != today:
            done["date"], done["count"] = today, 0
        done["count"] += 1
        self.save_config()
        self.btn_focus.pulse()
        tip().flash("Focus session done!", self.visible_anchor(self.btn_focus), "top",
                    "Take a short break", 5000)

    def paint_focus(self, p, center, r, s):
        focus = self.focus
        if focus.state == "idle":
            return
        frac = 1.0 - focus.remaining / max(1, focus.total)
        ring = r + 4.5
        rect = QRectF(center.x() - ring, center.y() - ring, ring * 2, ring * 2)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 40), 3))
        p.drawEllipse(rect)
        color = QColor("#ff6b6b") if focus.state == "running" else QColor("#f5b942")
        p.setPen(QPen(color, 3, Qt.SolidLine, Qt.RoundCap))
        if frac > 0:
            p.drawArc(rect, 90 * 16, int(-360 * 16 * frac))
        font = QFont(QApplication.font())
        font.setPixelSize(max(9, int(12 * s)))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#111111"))
        p.drawText(QRectF(center.x() - r, center.y() - r, 2 * r, 2 * r), Qt.AlignCenter, focus.mmss())

    def focus_menu(self, pos):
        menu = styled_menu(self)
        for minutes in (15, 25, 50):
            mark = "   (current)" if self.focus.total == minutes * 60 else ""
            menu.addAction(f"{minutes} minutes{mark}",
                           lambda checked=False, m=minutes: self.focus.set_minutes(m))
        menu.addSeparator()
        menu.addAction("Reset", self.focus.reset)
        menu.exec(pos)

    # ---- wallpapers ----

    def wallpaper_path(self):
        config = getattr(self, "config", None) or {}
        current = config.get("wallpaper")
        if current and os.path.isfile(current):
            return current
        return str(WALLPAPER) if WALLPAPER.exists() else None

    def set_wallpaper(self, path):
        self.config["wallpaper"] = str(path) if path else None
        self.save_config()

        old = (self.wall, self.wall_blur)
        self.build_wallpaper()
        self.wall_old, self.wall_blur_old = old
        self.fade_t = 0.0

        if self._wall_anim is not None:
            self._wall_anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(800)
        anim.setEasingCurve(QEasingCurve.InOutCubic)
        anim.valueChanged.connect(self._wall_step)
        anim.finished.connect(self._wall_done)
        self._wall_anim = anim
        anim.start()

    def _wall_step(self, value):
        self.fade_t = float(value)
        self.repaint_all()

    def _wall_done(self):
        self.fade_t = 1.0
        self.wall_old = self.wall_blur_old = None
        self.repaint_all()

    def repaint_all(self):
        self.update()
        for widget in (self.sidebar, self.main_panel, self.dock):
            widget.update()

    def next_wallpaper(self):
        paths = [str(p) for p in wallpaper_list()]
        if len(paths) < 2:
            tip().flash("Add more wallpapers", self.visible_anchor(self.btn_wall), "top",
                        "Put images in assets/wallpapers", 3200)
            return
        current = self.config.get("wallpaper")
        index = paths.index(current) if current in paths else 0
        self.set_wallpaper(paths[(index + 1) % len(paths)])

    def choose_wallpaper(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a wallpaper", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self.set_wallpaper(path)

    def wallpaper_menu(self, pos):
        menu = styled_menu(self)
        menu.addAction("Next wallpaper  (W)", self.next_wallpaper)
        menu.addAction("Choose image...", self.choose_wallpaper)
        menu.addAction("Open wallpapers folder", self.open_wallpaper_folder)
        menu.addSeparator()
        menu.addAction("Back to default", lambda: self.set_wallpaper(None))
        menu.exec(pos)

    def open_wallpaper_folder(self):
        WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)
        launch(str(WALLPAPER_DIR))

    # ---- building ----

    def build_sidebar(self):
        search = IconButton(
            "Search apps", qta.icon("fa5s.search", color="white"),
            46, True, pad=10, on_click=self.open_app_search,
            hint="Ctrl+S", tip_side="right"
        )
        panel = PinPanel(self, "sidebar", "sidebar", vertical=True, max_items=5,
                         radius=42, alpha=50, size=50, pad=8, lead=[search])
        panel.setFixedWidth(84)
        return panel

    def build_dock(self):
        def tool(label, icon, slot, hint):
            return IconButton(label, qta.icon(icon, color="#111111"), 46, False, pad=10,
                              on_click=lambda checked=False: slot(), hint=hint)

        self.btn_stats = tool("System", "fa5s.microchip",
                              lambda: self.toggle_popover(self.stats_pop), "CPU, RAM, disk  (S)")
        self.btn_focus = tool("Focus timer", "fa5s.stopwatch", self.focus.toggle, "")
        self.btn_focus.overlay_cb = self.paint_focus
        self.btn_focus.context_cb = self.focus_menu
        self.btn_wall = tool("Wallpaper", "fa5s.image", self.next_wallpaper,
                             "Next background  (W)  -  right-click for more")
        self.btn_wall.context_cb = self.wallpaper_menu

        panel = PinPanel(self, "dock", "dock", vertical=False, max_items=7,
                         radius=40, alpha=60, size=56, pad=10,
                         trail=[self.btn_stats, self.btn_focus, self.btn_wall])
        panel.setFixedHeight(92)
        return panel

    def build_main(self):
        panel = Glass(radius=36, alpha=45)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(38, 32, 38, 32)

        left = QVBoxLayout()
        self.clock = QLabel("00:00")
        self.clock.setFont(QFont("Consolas", 46, QFont.Bold))
        self.clock.setStyleSheet("color:#141414; background:transparent;")

        self.date = QLabel("")
        self.date.setFont(QFont("Consolas", 12))
        self.date.setStyleSheet("color:#222; background:transparent;")

        self.cal = CalendarCard()
        left.addWidget(self.clock)
        left.addWidget(self.date)
        left.addSpacing(28)
        left.addWidget(self.cal)
        left.addStretch()
        layout.addLayout(left)
        layout.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(10)

        top = QHBoxLayout()
        top.addStretch()
        self.net_pill = StatusPill()
        self.net_pill.clicked.connect(self.open_wifi_settings)
        top.addWidget(self.net_pill)
        top.addSpacing(8)
        self.friends_btn = FriendsButton()
        top.addWidget(self.friends_btn)
        top.addSpacing(8)
        self.chip = ProfileChip()
        self.chip.set_profile(self.profile_name(), self.config.get("avatar"),
                              self.config.get("status", ""))
        top.addWidget(self.chip)
        right.addLayout(top)

        self.hello = TypeLabel(f"Hi {self.profile_name()}!!")
        self.hello.setFont(QFont("Segoe UI", 15, QFont.Bold))
        self.hello.setStyleSheet("background:transparent;")
        self.hello.setAlignment(Qt.AlignRight)
        right.addWidget(self.hello)

        self.card_imgs = [
            RoundedImage(CARD_IMAGES[0], 140, 282, 0),
            RoundedImage(CARD_IMAGES[1], 140, 135, 1),
            RoundedImage(CARD_IMAGES[2], 140, 135, 2),
        ]
        cards = QHBoxLayout()
        cards.setSpacing(12)
        cards.addWidget(self.card_imgs[0], 0, Qt.AlignTop)

        stack = QVBoxLayout()
        stack.setSpacing(12)
        stack.addWidget(self.card_imgs[1])
        stack.addWidget(self.card_imgs[2])
        cards.addLayout(stack)
        right.addLayout(cards)

        self.music = MusicPlayer(self.config.get("volume", 60), self.config.get("muted", False),
                                 self.on_music_settings)
        right.addWidget(self.music)
        right.addStretch()
        layout.addLayout(right)
        return panel

    # ---- animations ----

    def showEvent(self, event):
        super().showEvent(event)
        if not self._intro_played:
            self._intro_played = True
            self.play_intro()

    def play_intro(self):
        back = QEasingCurve.OutBack
        # panels: slide + glass fade only (no opacity effect, their children animate too)
        fade_slide(self.sidebar, -90, 0, 0, 750, fade=False)
        fade_slide(self.main_panel, 0, 60, 120, 800, fade=False)
        fade_slide(self.dock, 0, 110, 280, 850, back, fade=False)
        self.sidebar.intro(0, 650)
        self.main_panel.intro(120, 700)
        self.dock.intro(280, 700)
        fade_slide(self.character, 0, 110, 260, 1000)
        fade_slide(self.running_panel, 0, -30, 1400, 600)

        fade_slide(self.clock, -40, 0, 600, 650)
        fade_slide(self.date, -40, 0, 680, 650)
        fade_slide(self.cal, 0, 44, 760, 700, back)
        fade_slide(self.chip, 40, 0, 700, 650)
        fade_slide(self.net_pill, 40, 0, 760, 650)
        for i, card in enumerate(self.card_imgs):
            fade_slide(card, 0, 50, 850 + i * 90, 700, back)
        fade_slide(self.music, 0, 40, 1100, 700, back)
        self.hello.type_in(1000)

        self.sidebar.appear_all(520)
        self.dock.appear_all(700)
        QTimer.singleShot(1900, self.start_live)

    def start_live(self):
        self.live = True
        self.timer.start(1000)
        self.ambient.start(40)
        self.net_timer.start(10000)
        self.poll_network()
        self.shell_timer = QTimer(self)
        self.shell_timer.timeout.connect(self.apply_taskbar)
        self.shell_timer.start(1500)
        QApplication.instance().applicationStateChanged.connect(lambda state: self.apply_taskbar())
        self.apply_taskbar()
        self.friends.start()
        self.updater.start()

        if self.first_run:                      # first start (e.g. on a friend's PC): ask for the name
            self.save_config()
            self.toggle_popover(self.profile)
            self.profile.name_edit.setFocus()
            self.profile.name_edit.selectAll()
            tip().flash("Welcome! Type your name", self.chip, "bottom", "Click the picture to add a photo", 6000)

    # ---- network indicator ----

    def poll_network(self):
        if self._net_worker is not None:
            return                               # previous check still running
        worker = NetWorker()
        worker.signals.done.connect(self.on_network)
        self._net_worker = worker
        QThreadPool.globalInstance().start(worker)

    def on_network(self, info):
        self._net_worker = None
        previous = self.net_info
        self.net_info = info
        self.net_pill.set_info(info)
        if previous is not None and previous["online"] != info["online"] and self.live:
            tip().flash("Back online" if info["online"] else "Internet lost", self.net_pill,
                        "bottom", info["ssid"] if info["kind"] == "wifi" else "", 3500)
        if self.popover is self.stats_pop and self.stats_pop.is_open:
            self.stats_pop.refresh()

    def open_wifi_settings(self):
        if os.name == "nt":
            try:
                os.startfile("ms-settings:network-wifi")
            except Exception as exc:
                print("Could not open Wi-Fi settings:", exc)
        else:
            tip().flash("Wi-Fi settings open on Windows only", self.net_pill, "bottom", "", 2500)

    # ---- music ----

    def on_music_settings(self, volume, muted):
        self.config["volume"] = int(volume)
        self.config["muted"] = bool(muted)
        self.save_config()

    def ambient_tick(self):
        """Character floats gently and follows the mouse a little (parallax)."""
        if (not self.live or self.char_src.isNull() or not self.isVisible()
                or not self.isActiveWindow() or self.running_panel.opened):
            return
        bob = -(math.sin(time.monotonic() * 1.3) + 1.0) * 3.0
        cursor = self.mapFromGlobal(QCursor.pos())
        ratio = max(-0.5, min(0.5, cursor.x() / max(1, self.width()) - 0.5))
        self.par_x += (ratio * 24 - self.par_x) * 0.1
        pos = QPoint(self.char_base.x() + int(round(self.par_x)),
                     self.char_base.y() + int(round(bob)))
        if pos != self.character.pos():
            self.character.move(pos)

    def tick(self):
        now = QDateTime.currentDateTime()
        self.clock.setText(now.toString("HH:mm"))
        self.date.setText(QLocale("en_US").toString(now, "dddd MM/dd"))
        if self.cal.shown != jdatetime.date.today():
            self.cal.refresh()

    # ---- wallpaper / blur ----

    def build_wallpaper(self):
        dpr = self.devicePixelRatioF()
        width = max(1, int(self.width() * dpr))
        height = max(1, int(self.height() * dpr))

        path = self.wallpaper_path()
        source = QPixmap(path) if path else QPixmap()
        if source.isNull():
            pixmap = QPixmap(width, height)
            gradient = QLinearGradient(0, 0, width, height)
            gradient.setColorAt(0, QColor("#202020"))
            gradient.setColorAt(0.5, QColor("#454545"))
            gradient.setColorAt(1, QColor("#151515"))
            painter = QPainter(pixmap)
            painter.fillRect(pixmap.rect(), QBrush(gradient))
            painter.end()
        else:
            pixmap = source.scaled(
                width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            pixmap = pixmap.copy(
                (pixmap.width() - width) // 2,
                (pixmap.height() - height) // 2,
                width, height
            )

        blurred = blur_pixmap(pixmap, BLUR_RADIUS * dpr)
        pixmap.setDevicePixelRatio(dpr)
        blurred.setDevicePixelRatio(dpr)
        self.wall = pixmap
        self.wall_blur = blurred

    def set_background_blur(self, enabled, animate=True):
        if enabled:
            self.running_panel.hide()
            self.blur_overlay.hide()

            snapshot = self.grab()
            dpr = snapshot.devicePixelRatio()
            snapshot.setDevicePixelRatio(1.0)
            blurred = blur_pixmap(snapshot, BLUR_RADIUS * dpr)

            self.blur_overlay.set_pixmap(blurred)
            self.blur_overlay.setGeometry(self.rect())
            self.blur_overlay.show()
            self.blur_overlay.raise_()
            if animate:
                self.blur_overlay._set_amount(0.0)
                self.blur_overlay.fade(1.0, 340)
            else:
                self.blur_overlay._set_amount(1.0)

            self.running_panel.show()
            self.running_panel.raise_()
            self.running_panel.handle.raise_()
        else:
            self.blur_overlay.fade(0.0, 280, on_done=self.blur_overlay.hide)

    # ---- events ----

    def resizeEvent(self, event):
        self.build_wallpaper()

        if hasattr(self, "char_src") and not self.char_src.isNull():
            scaled = self.char_src.scaledToHeight(
                max(1, int(self.height() * 0.95)),
                Qt.SmoothTransformation
            )
            self.character.setPixmap(scaled)
            self.character.resize(scaled.size())
            self.char_base = QPoint(
                int(self.width() * CHARACTER_X - scaled.width() / 2),
                self.height() - scaled.height() + 10
            )
            self.character.move(self.char_base)

        if hasattr(self, "blur_overlay"):
            self.blur_overlay.setGeometry(self.rect())

        if hasattr(self, "running_panel"):
            self.running_panel.update_position()
            if self.running_panel.opened:
                self.set_background_blur(True, animate=False)

        if getattr(self, "popover", None) is not None:   # keep an open popover attached to its button
            QTimer.singleShot(0, self.popover.reposition)

        super().resizeEvent(event)

    def paintEvent(self, event):
        if self.wall is None:
            self.build_wallpaper()

        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

        radius = 0 if self.isFullScreen() else 30
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        painter.setClipPath(path)
        if self.wall_old is not None and self.fade_t < 1.0:      # wallpaper cross-fade
            painter.drawPixmap(0, 0, self.wall_old)
            painter.setOpacity(self.fade_t)
            painter.drawPixmap(0, 0, self.wall)
            painter.setOpacity(1.0)
        else:
            painter.drawPixmap(0, 0, self.wall)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.isFullScreen():
            self.drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.drag is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag)

    def mouseReleaseEvent(self, event):
        self.drag = None

    def go_back(self):
        """Ctrl+X: close popover -> close running apps -> leave fullscreen -> quit."""
        if self.popover is not None and self.popover.is_open:
            self.close_popover()
        elif self.running_panel.opened:
            self.running_panel.toggle()
        elif self.isFullScreen():
            self.set_fullscreen(False)
        else:
            self.close()

    def launch_dock_item(self, index):
        items = self.config["dock"]
        if 0 <= index < len(items):
            item = items[index]
            launch(item["target"], item.get("exe"))
            button = self.dock.buttons[index] if index < len(self.dock.buttons) else None
            if button is not None:
                button.pulse()

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.ControlModifier)
        alt = bool(mods & Qt.AltModifier)

        if ctrl and key == Qt.Key_X:
            self.go_back()
        elif key == Qt.Key_F11 or (alt and key in (Qt.Key_Return, Qt.Key_Enter)):
            self.toggle_fullscreen()
        elif ctrl and key == Qt.Key_Q:
            self.close()
        elif ctrl and key == Qt.Key_S:
            self.open_app_search()
        elif ctrl and Qt.Key_1 <= key <= Qt.Key_9:
            self.launch_dock_item(int(key) - int(Qt.Key_1))
        elif not (ctrl or alt or (mods & Qt.MetaModifier)):
            letter = {Qt.Key_W: self.next_wallpaper,
                      Qt.Key_S: lambda: self.toggle_popover(self.stats_pop),
                      Qt.Key_T: self.focus.toggle,
                      Qt.Key_P: lambda: self.toggle_popover(self.profile),
                      Qt.Key_F: lambda: self.toggle_popover(self.friends_pop),
                      Qt.Key_H: self.toggle_tools,
                      Qt.Key_Space: self.music.toggle,
                      Qt.Key_M: self.music.toggle_mute,
                      Qt.Key_Up: lambda: self.music.change_volume(5),
                      Qt.Key_Down: lambda: self.music.change_volume(-5),
                      Qt.Key_N: lambda: self.music.step(1),
                      Qt.Key_B: lambda: self.music.step(-1),
                      Qt.Key_R: self.running_panel.toggle}.get(key)
            if letter:
                letter()
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def set_fullscreen(self, on):
        if bool(on) == self.isFullScreen():
            return
        if on:
            self.showFullScreen()
        else:
            self.showNormal()
        self.config["fullscreen"] = bool(on)      # remembered for the next start
        self.save_config()
        QTimer.singleShot(50, self.apply_taskbar)
        if self.popover is not None and self.popover is self.profile:
            self.profile.sw_full.set_silent(bool(on))

    def toggle_fullscreen(self):
        self.set_fullscreen(not self.isFullScreen())

    # ---- Windows taskbar: hidden while the widget is the active fullscreen app ----

    def apply_taskbar(self):
        if os.name != "nt":
            return
        app_active = QApplication.applicationState() == Qt.ApplicationActive
        want = bool(self.config.get("hide_taskbar", True) and self.isFullScreen() and app_active)
        if want != self._taskbar_hidden:
            self._taskbar_hidden = want
            set_taskbar_visible(not want)
            self.config["taskbar_hidden"] = want       # crash safety: restored on the next start
            self.save_config()
        elif want:
            set_taskbar_visible(False)                  # Explorer sometimes brings it back

    def set_hide_taskbar(self, on):
        self.config["hide_taskbar"] = bool(on)
        self.save_config()
        self.apply_taskbar()

    def restore_taskbar(self):
        if self._taskbar_hidden or self.config.get("taskbar_hidden"):
            set_taskbar_visible(True)
            self._taskbar_hidden = False
            self.config["taskbar_hidden"] = False
            self.save_config()

    def changeEvent(self, event):
        # back from another window (e.g. Chrome): grab keyboard focus so the keys work at once
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            QTimer.singleShot(0, lambda: self.setFocus(Qt.ActiveWindowFocusReason))
        super().changeEvent(event)

    def closeEvent(self, event):
        self.restore_taskbar()
        tip().cancel()
        self.close_popover()
        try:
            QApplication.instance().removeEventFilter(self)
        except Exception:
            pass
        super().closeEvent(event)

    def contextMenuEvent(self, event):
        menu = styled_menu(self)
        menu.addAction("Profile  (P)", lambda: self.toggle_popover(self.profile))
        menu.addAction("Friends  (F)", lambda: self.toggle_popover(self.friends_pop))
        menu.addAction("System stats  (S)", lambda: self.toggle_popover(self.stats_pop))
        menu.addAction("Running apps  (R)", self.running_panel.toggle)
        menu.addSeparator()
        menu.addAction("Next wallpaper  (W)", self.next_wallpaper)
        menu.addAction("Hide dock tools  (H)" if self.config.get("tools_visible") else "Show dock tools  (H)",
                       self.toggle_tools)
        menu.addAction("Fullscreen  (F11)", self.toggle_fullscreen)
        menu.addSeparator()
        menu.addAction("Reset dock && sidebar", self.reset_pins)
        menu.addAction("Quit  (Ctrl+Q)", self.close)
        menu.exec(event.globalPos())


# ----------------------------- Start -----------------------------

def main():
    for folder in (ASSETS / "cards", MUSIC_DIR):
        folder.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)

    font_path = ASSETS / "fonts" / "VAZIR-MEDIUM.TTF"
    if font_path.exists():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id != -1:
            family = QFontDatabase.applicationFontFamilies(font_id)[0]
            app.setFont(QFont(family, 10))
        else:
            print("Font loading failed!")
    else:
        print("Persian font not found; using system font.")

    icon_path = ensure_app_icon()
    if icon_path:
        app.setWindowIcon(QIcon(str(icon_path)))

    # python main.py --create-shortcut   -> puts a shortcut on the Desktop and exits
    if "--create-shortcut" in sys.argv:
        path = create_shortcut("Desktop")
        print("Shortcut created:" if path else "Shortcut failed (Windows only):", path or "")
        return

    atexit.register(set_taskbar_visible, True)       # never leave the taskbar hidden
    window = MainWindow()

    # Fullscreen by default (F11 / profile panel to change). Command line can override it.
    fullscreen = window.config.get("fullscreen", True)
    if "--windowed" in sys.argv:
        fullscreen = False
    elif "--fullscreen" in sys.argv:
        fullscreen = True

    if fullscreen:
        window.showFullScreen()
    else:
        screen = app.primaryScreen().availableGeometry()
        window.move(screen.center() - window.rect().center())
        window.show()
    window.activateWindow()
    window.setFocus()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
