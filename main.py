"""
Glass desktop widget (PySide6)
- ساعت + تاریخ، تقویم، نوار شبکه‌های اجتماعی، داک برنامه‌ها، پلیر موزیک
- تصویر کاراکتر: assets/wallpaper.jpg (پس‌زمینه) و assets/character.png (PNG بدون پس‌زمینه، اختیاری)

اجرا:  pip install PySide6   ->   python main.py
کلیدها: Esc = خروج | F11 = تمام‌صفحه | کلیک راست = منو | درگ با ماوس = جابجایی
"""
import calendar
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRectF, QPoint, QSize, QDate, QDateTime, QLocale, QUrl
from PySide6.QtGui import (QPainter, QPainterPath, QPixmap, QColor, QFont, QImage,
                           QLinearGradient, QIcon, QPen, QBrush)
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, QHBoxLayout,
                               QVBoxLayout, QGridLayout, QSlider, QMenu, QGraphicsScene,
                               QGraphicsPixmapItem, QGraphicsBlurEffect)

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    HAS_MEDIA = True
except Exception:  # pragma: no cover
    HAS_MEDIA = False

# ───────────────────────── تنظیمات (اینجا رو شخصی‌سازی کن) ─────────────────────────
NAME = "Bitaro"                 # اسمی که تو "Hi ...!!" نشون داده میشه
CHARACTER_X = 0.5               # جای افقی کاراکتر (0 تا 1)
STAY_ON_DESKTOP = False         # True = پنجره زیر بقیه پنجره‌ها بمونه
BLUR_RADIUS = 28

BASE = Path(__file__).parent
ASSETS = BASE / "assets"
WALLPAPER = ASSETS / "wallpaper.jpg"      # پس‌زمینه
CHARACTER = ASSETS / "character.png"      # کاراکتر PNG شفاف (اختیاری)
MUSIC_DIR = ASSETS / "music"              # آهنگ‌ها اینجا
CARD_IMAGES = [ASSETS / "cards" / "1.png", ASSETS / "cards" / "2.png", ASSETS / "cards" / "3.png"]

# (اسم، آیکون در assets/icons/<icon>.png، متن جایگزین اگه آیکون نبود، لینک/برنامه)
SOCIALS = [
    ("TikTok",    "tiktok",    "TT", "https://www.tiktok.com"),
    ("YouTube",   "youtube",   "YT", "https://www.youtube.com"),
    ("Facebook",  "facebook",  "f",  "https://www.facebook.com"),
    ("Instagram", "instagram", "IG", "https://www.instagram.com"),
    ("X",         "x",         "X",  "https://x.com"),
]
DOCK = [
    ("Spotify",    "spotify", "Sp", "spotify:"),                 # ویندوز: پروتکل اسپاتیفای
    ("Photoshop",  "ps",      "Ps", r"C:\Program Files\Adobe\Adobe Photoshop 2024\Photoshop.exe"),
    ("Chrome",     "chrome",  "Ch", "https://www.google.com"),
    ("After Effects", "ae",   "Ae", r"C:\Program Files\Adobe\Adobe After Effects 2024\Support Files\AfterFX.exe"),
    ("Discord",    "discord", "Dc", "https://discord.com/app"),
]
SEARCH_URL = "https://www.google.com"
# ───────────────────────────────────────────────────────────────────────────────────


def launch(target: str):
    """لینک یا برنامه رو باز می‌کنه."""
    try:
        if target.startswith("http"):
            webbrowser.open(target)
        elif sys.platform.startswith("win"):
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(target, shell=True)
    except Exception as e:
        print("launch failed:", target, e)


def blur_pixmap(pm: QPixmap, radius: float) -> QPixmap:
    out = QImage(pm.size(), QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.drawPixmap(0, 0, pm)  # زیرلایه، تا لبه‌ها شفاف نشن
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(pm)
    eff = QGraphicsBlurEffect()
    eff.setBlurRadius(radius)
    item.setGraphicsEffect(eff)
    scene.addItem(item)
    scene.render(p, QRectF(out.rect()), QRectF(pm.rect()))
    p.end()
    return QPixmap.fromImage(out)


class Glass(QWidget):
    """پنل شیشه‌ای: بلورِ پس‌زمینه + لایه سفید نیمه‌شفاف + حاشیه."""

    def __init__(self, parent=None, radius=30, alpha=55):
        super().__init__(parent)
        self.radius = radius
        self.alpha = alpha

    def paintEvent(self, _):
        win = self.window()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, self.radius, self.radius)
        p.setClipPath(path)
        blur = getattr(win, "wall_blur", None)
        if blur is not None:
            off = self.mapTo(win, QPoint(0, 0))
            p.drawPixmap(-off, blur)
        p.fillPath(path, QColor(255, 255, 255, self.alpha))
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 120), 1.2))
        p.drawPath(path)


class IconButton(QPushButton):
    def __init__(self, label, icon, fallback, target, size, style, font_px=15):
        super().__init__()
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(label)
        path = ASSETS / "icons" / f"{icon}.png"
        if path.exists():
            self.setIcon(QIcon(str(path)))
            self.setIconSize(QSize(int(size * 0.62), int(size * 0.62)))
        else:
            self.setText(fallback)
        self.setStyleSheet(
            f"QPushButton{{{style} border-radius:{size // 2}px; font-weight:bold; font-size:{font_px}px;}}"
            "QPushButton:hover{background:rgba(255,255,255,150); color:#111;}"
        )
        self.clicked.connect(lambda: launch(target))


class RoundedImage(QWidget):
    def __init__(self, path: Path, w, h, seed=0, radius=20):
        super().__init__()
        self.setFixedSize(w, h)
        self.radius = radius
        self.pm = QPixmap(str(path)) if path.exists() else QPixmap()
        self.colors = [("#ff9a9e", "#fad0c4"), ("#a1c4fd", "#c2e9fb"), ("#fbc2eb", "#a6c1ee")][seed % 3]

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self.radius, self.radius)
        p.setClipPath(path)
        if self.pm.isNull():
            g = QLinearGradient(0, 0, self.width(), self.height())
            g.setColorAt(0, QColor(self.colors[0]))
            g.setColorAt(1, QColor(self.colors[1]))
            p.fillRect(self.rect(), QBrush(g))
        else:
            s = self.pm.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawPixmap((self.width() - s.width()) // 2, (self.height() - s.height()) // 2, s)


class CalendarCard(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("cal")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("#cal{background:rgba(28,28,28,235); border-radius:26px;}"
                           "QLabel{background:transparent; color:white;}")
        self.setFixedSize(236, 296)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        self.title = QLabel(alignment=Qt.AlignCenter)
        self.title.setFont(QFont("Segoe UI", 15, QFont.Bold))
        lay.addWidget(self.title)
        self.grid = QGridLayout()
        self.grid.setSpacing(4)
        lay.addLayout(self.grid)
        lay.addStretch()
        self.shown = None
        self.refresh()

    def refresh(self):
        today = QDate.currentDate()
        self.shown = today
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.title.setText(calendar.month_name[today.month()] if False else calendar.month_name[today.month()])
        for c, d in enumerate("SMTWTFS"):
            lbl = QLabel(d, alignment=Qt.AlignCenter)
            lbl.setStyleSheet("color:#888; font-size:10px;")
            self.grid.addWidget(lbl, 0, c)
        cal = calendar.Calendar(firstweekday=6)
        for r, week in enumerate(cal.monthdayscalendar(today.year(), today.month()), 1):
            for c, day in enumerate(week):
                if not day:
                    continue
                lbl = QLabel(str(day), alignment=Qt.AlignCenter)
                if day == today.day():
                    lbl.setStyleSheet("font-weight:bold; font-size:13px; text-decoration:underline;")
                else:
                    lbl.setStyleSheet("font-size:12px; color:#ddd;")
                self.grid.addWidget(lbl, r, c)


class MusicPlayer(QWidget):
    EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}

    def __init__(self):
        super().__init__()
        self.setObjectName("mp")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(300, 78)
        self.setStyleSheet(
            "#mp{background:rgba(255,255,255,80); border-radius:26px;}"
            "QLabel{background:transparent; color:#1d1d1d;}"
            "QPushButton{background:transparent; border:none; color:#1d1d1d; font-size:15px;}"
            "QPushButton:hover{color:#000; font-weight:bold;}"
            "QSlider::groove:horizontal{height:3px; background:rgba(0,0,0,60); border-radius:1px;}"
            "QSlider::sub-page:horizontal{background:#1d1d1d; border-radius:1px;}"
            "QSlider::handle:horizontal{width:8px; margin:-3px 0; border-radius:4px; background:#1d1d1d;}"
        )
        self.tracks = sorted(p for p in MUSIC_DIR.glob("*") if p.suffix.lower() in self.EXTS) if MUSIC_DIR.exists() else []
        self.idx = 0
        self.player = None
        self.media_failed = False

        disc = QLabel()
        disc.setFixedSize(44, 44)
        disc.setStyleSheet("background:#151515; border-radius:22px;")
        self.title = QLabel("Untitled" if self.tracks else "assets/music خالیه")
        self.title.setStyleSheet("font-size:11px; font-weight:bold;")
        self.prev_b, self.play_b, self.next_b = QPushButton("⏮"), QPushButton("▶"), QPushButton("⏭")
        for b in (self.prev_b, self.play_b, self.next_b):
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedWidth(26)
        self.prev_b.clicked.connect(lambda: self.step(-1))
        self.next_b.clicked.connect(lambda: self.step(1))
        self.play_b.clicked.connect(self.toggle)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.sliderMoved.connect(lambda v: self.player.setPosition(v) if self.player else None)

        row = QHBoxLayout()
        row.setSpacing(0)
        for w in (self.prev_b, self.play_b, self.next_b):
            row.addWidget(w)
        row.addWidget(self.slider, 1)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(self.title)
        col.addLayout(row)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)
        lay.addWidget(disc)
        lay.addLayout(col, 1)

    def ensure_player(self):
        """پلیر رو فقط وقت اولین پخش می‌سازه (جلوگیری از مشکل کارت صدا)."""
        if self.player or self.media_failed or not HAS_MEDIA:
            return self.player
        try:
            self.audio = QAudioOutput()
            self.audio.setVolume(0.6)
            self.player = QMediaPlayer()
            self.player.setAudioOutput(self.audio)
            self.player.positionChanged.connect(self.on_pos)
            self.player.durationChanged.connect(lambda d: self.slider.setRange(0, d))
            self.player.mediaStatusChanged.connect(self.on_status)
        except Exception as e:
            print("media init failed:", e)
            self.media_failed = True
            self.player = None
        return self.player

    def load(self):
        if not (self.ensure_player() and self.tracks):
            return
        t = self.tracks[self.idx]
        self.player.setSource(QUrl.fromLocalFile(str(t)))
        self.title.setText(t.stem[:32])

    def toggle(self):
        if not (self.ensure_player() and self.tracks):
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_b.setText("▶")
        else:
            if self.player.source().isEmpty():
                self.load()
            self.player.play()
            self.play_b.setText("⏸")

    def step(self, d):
        if not self.tracks:
            return
        self.idx = (self.idx + d) % len(self.tracks)
        self.load()
        if self.ensure_player():
            self.player.play()
            self.play_b.setText("⏸")

    def on_pos(self, pos):
        if not self.slider.isSliderDown():
            self.slider.setValue(pos)

    def on_status(self, st):
        if st == QMediaPlayer.EndOfMedia:
            self.step(1)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        flags = Qt.FramelessWindowHint | Qt.Window
        if STAY_ON_DESKTOP:
            flags |= Qt.WindowStaysOnBottomHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("My Desktop")
        self.resize(1280, 720)
        self.wall = None
        self.wall_blur = None
        self.drag = None
        self.char_src = QPixmap(str(CHARACTER)) if CHARACTER.exists() else QPixmap()

        root = QHBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(20)
        root.addWidget(self.build_sidebar())
        col = QVBoxLayout()
        col.setSpacing(20)
        col.addWidget(self.build_main(), 1)
        self.dock = self.build_dock()
        col.addWidget(self.dock, 0, Qt.AlignHCenter)
        root.addLayout(col, 1)

        self.character = QLabel(self)
        self.character.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.character.stackUnder(self.dock)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()

    # ── ساخت بخش‌ها ──
    def build_sidebar(self):
        panel = Glass(radius=42, alpha=50)
        panel.setFixedWidth(84)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 22, 0, 22)
        lay.setSpacing(18)
        lay.setAlignment(Qt.AlignHCenter)
        dark = "background:rgba(20,20,20,235); color:white;"
        lay.addWidget(IconButton("Search", "search", "🔍", SEARCH_URL, 46, "background:transparent; color:#111;", 20), 0, Qt.AlignHCenter)
        lay.addSpacing(8)
        for label, icon, fb, url in SOCIALS:
            lay.addWidget(IconButton(label, icon, fb, url, 50, dark), 0, Qt.AlignHCenter)
        lay.addStretch()
        return panel

    def build_main(self):
        panel = Glass(radius=36, alpha=45)
        h = QHBoxLayout(panel)
        h.setContentsMargins(38, 32, 38, 32)

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
        h.addLayout(left)
        h.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(14)
        top = QHBoxLayout()
        top.addStretch()
        chip = QLabel(f"  {NAME}   ●")
        chip.setFixedHeight(40)
        chip.setStyleSheet("background:rgba(255,255,255,200); color:#222; border-radius:20px;"
                           "padding:0px 18px; font-weight:bold; font-size:13px;")
        top.addWidget(chip)
        right.addLayout(top)
        hi = QLabel(f"Hi {NAME}!!")
        hi.setFont(QFont("Segoe UI", 15, QFont.Bold))
        hi.setStyleSheet("color:white; background:transparent;")
        hi.setAlignment(Qt.AlignRight)
        right.addWidget(hi)
        cards = QHBoxLayout()
        cards.setSpacing(12)
        cards.addWidget(RoundedImage(CARD_IMAGES[0], 140, 282, 0), 0, Qt.AlignTop)
        sq = QVBoxLayout()
        sq.setSpacing(12)
        sq.addWidget(RoundedImage(CARD_IMAGES[1], 140, 135, 1))
        sq.addWidget(RoundedImage(CARD_IMAGES[2], 140, 135, 2))
        cards.addLayout(sq)
        right.addLayout(cards)
        self.music = MusicPlayer()
        right.addWidget(self.music)
        right.addStretch()
        h.addLayout(right)
        return panel

    def build_dock(self):
        panel = Glass(radius=40, alpha=60)
        panel.setFixedHeight(84)
        lay = QHBoxLayout(panel)
        lay.setContentsMargins(26, 10, 26, 10)
        lay.setSpacing(18)
        for label, icon, fb, target in DOCK:
            lay.addWidget(IconButton(label, icon, fb, target, 56,
                                     "background:rgba(255,255,255,70); color:#111;", 16))
        return panel

    # ── منطق ──
    def tick(self):
        now = QDateTime.currentDateTime()
        self.clock.setText(now.toString("HH:mm"))
        self.date.setText(QLocale("en_US").toString(now, "dddd MM/dd"))
        if self.cal.shown != QDate.currentDate():
            self.cal.refresh()

    def build_wallpaper(self):
        dpr = self.devicePixelRatioF()
        w, h = max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr))
        src = QPixmap(str(WALLPAPER)) if WALLPAPER.exists() else QPixmap()
        if src.isNull():
            pm = QPixmap(w, h)
            g = QLinearGradient(0, 0, w, h)
            g.setColorAt(0, QColor("#1b2a49"))
            g.setColorAt(0.5, QColor("#5b6fb5"))
            g.setColorAt(1, QColor("#e8a0bf"))
            p = QPainter(pm)
            p.fillRect(pm.rect(), QBrush(g))
            p.end()
        else:
            pm = src.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            pm = pm.copy((pm.width() - w) // 2, (pm.height() - h) // 2, w, h)
        blurred = blur_pixmap(pm, BLUR_RADIUS * dpr)
        pm.setDevicePixelRatio(dpr)
        blurred.setDevicePixelRatio(dpr)
        self.wall, self.wall_blur = pm, blurred

    def resizeEvent(self, e):
        self.build_wallpaper()
        if not self.char_src.isNull():
            pm = self.char_src.scaledToHeight(int(self.height() * 0.95), Qt.SmoothTransformation)
            self.character.setPixmap(pm)
            self.character.resize(pm.size())
            self.character.move(int(self.width() * CHARACTER_X - pm.width() / 2), self.height() - pm.height())
        super().resizeEvent(e)

    def paintEvent(self, _):
        if self.wall is None:
            return
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        rad = 0 if self.isFullScreen() else 30
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), rad, rad)
        p.setClipPath(path)
        p.drawPixmap(0, 0, self.wall)

    # ── ماوس/کیبورد ──
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self.isFullScreen():
            self.drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self.drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self.drag)

    def mouseReleaseEvent(self, _):
        self.drag = None

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()
        elif e.key() == Qt.Key_F11:
            self.toggle_fullscreen()

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def contextMenuEvent(self, e):
        m = QMenu(self)
        m.addAction("Fullscreen (F11)", self.toggle_fullscreen)
        m.addAction("Quit (Esc)", self.close)
        m.exec(e.globalPos())


def main():
    for d in (ASSETS / "icons", ASSETS / "cards", MUSIC_DIR):
        d.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
