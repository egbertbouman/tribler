
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import qasync
import tribler

from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon, QMoveEvent, QMovie, QAction
from PySide6.QtWidgets import QMainWindow, QWidget, QLabel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtCore import QByteArray, QUrl, Slot, Qt

if TYPE_CHECKING:
    from tribler.core.session import Session
    from tribler.tribler_config import TriblerConfigManager


class UiBridge(QObject):
    position_changed = Signal(float, float)  # (current, total)
    playback_status = Signal(bool)  # (is_paused)
    volume_changed = Signal(float)

    def __init__(self, window):
        super().__init__()
        self._logger = logging.getLogger(self.__class__.__name__)
        self.window = window

    @Slot()
    def ui_is_ready(self):
        self.window.loading_screen.hide()

    def register_mpv_observers(self):
        if self.window.player:
            self.window.player.observe_property('time-pos', self._on_pos_change)
            self.window.player.observe_property('pause', self._on_pause_change)
            self.window.player.observe_property('volume', self._on_volume_change)

    def _on_pos_change(self, name, value):
        if value is not None:
            duration = getattr(self.window.player, 'duration', 0) or 0
            self.position_changed.emit(float(value), float(duration))

    @Slot()
    def toggle_fullscreen(self):
        if self.window.isFullScreen():
            self.window.showNormal()
        else:
            self.window.showFullScreen()

    def _on_pause_change(self, name, value):
        self.playback_status.emit(bool(value))

    @Slot()
    def toggle_pause(self):
        if self.window.player:
            self.window.player.pause = not self.window.player.pause

    @Slot(float)
    def seek_to(self, percent):
        if self.window.player and self.window.player.duration:
            target = (percent / 100) * self.window.player.duration
            self.window.player.time_pos = target

    def _on_volume_change(self, name, value):
        if value is not None:
            self.volume_changed.emit(float(value))

    @Slot(float)
    def set_volume(self, value):
        if self.window.player:
            self.window.player.volume = value

    @Slot(str, int)
    def start_playback(self, infohash, fileindex):
        api_key = self.window.config.get('api/key')
        stream_url = f"{self.window.base_url}/api/downloads/{infohash}/stream/{fileindex}?key={api_key}"
        if self.window.player:
            self.window.player.play(stream_url)

    @Slot()
    def stop_playback(self):
        if self.window.player:
            self.window.player.stop()

    @Slot(float, float, float, float)
    def updateVideoRect(self, x, y, w, h):
        is_fs = self.window.windowState() & Qt.WindowFullScreen
        self.window.video_container.setGeometry(int(x), int(y), int(w), int(h) if is_fs else (int(h) - 85))
        if w > 0 and not self.window.video_container.isVisible():
            self.window.video_container.show()


class TriblerWindow(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self._logger = logging.getLogger(self.__class__.__name__)

        self.config = config
        self.player = None
        self.base_url = ""
        self.shutdown_event = None

        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, True)

        icon_path = tribler.get_webui_root() / "public" / "tribler.png"
        self.setWindowIcon(QIcon(str(icon_path)))
        self.setWindowTitle("Tribler")
        if geometry := self.config.get("ui/geometry"):
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode()))
        else:
            self.resize(1280, 800)

        self.browser = QWebEngineView(self)
        self.browser.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.Tool)
        self.browser.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.browser.page().setBackgroundColor(Qt.GlobalColor.transparent)
        self.browser.show()

        self.video_container = QWidget(self)
        self.video_container.setStyleSheet("background-color: black;")

        self.channel = QWebChannel()
        self.bridge = UiBridge(self)
        self.channel.registerObject("pybridge", self.bridge)
        self.browser.page().setWebChannel(self.channel)

        self.loading_screen = QLabel(self)
        self.loading_screen.setAlignment(Qt.AlignCenter)
        bg_color = "#1c1917" if self.config.get("ui/theme") == "dark" else "#f9f9f9"
        self.loading_screen.setStyleSheet(f"background-color: {bg_color}")
        self.setCentralWidget(self.loading_screen)

        self.movie = QMovie("tribler/ui/public/spinner.gif")
        self.loading_screen.setMovie(self.movie)
        self.movie.start()

        self.quit_event = asyncio.Event()
        QApplication.instance().aboutToQuit.connect(self.quit_event.set)

    @qasync.asyncClose
    async def closeEvent(self, event):
        self.config.set("ui/geometry", self.saveGeometry().toBase64().data().decode())
        self.config.write()
        if self.shutdown_event:
            self._logger.info("Shutting down main window...")
            self.shutdown_event.set()
        await self.quit_event.wait()
        event.accept()

    def set_api_server(self, host, port, key, shutdown_event: asyncio.Event):
        if not port or port == 0:
            return

        self.base_url = f"http://{host}:{port}"
        cookie = QNetworkCookie(QByteArray(b"api_key"), QByteArray(key.encode()))
        cookie.setDomain(host)
        cookie.setPath("/")
        self.browser.page().profile().cookieStore().setCookie(cookie, QUrl(self.base_url))
        self.browser.setUrl(QUrl(f"{self.base_url}/ui/#/downloads/all"))

        self.shutdown_event = shutdown_event

    def showEvent(self, event):
        if self.player is None:
            try:
                import mpv
                self.player = mpv.MPV(
                    wid=str(int(self.video_container.winId())),
                    log_handler=lambda level, prefix, text: self._logger.error(f'MPV errpr: {text}'),
                    loglevel='error',
                )

                # It's important to register the observers after creating the MPV player.
                self.bridge.register_mpv_observers()
                self._logger.info(f"MPV loaded on WID: {self.player.wid}")
            except Exception as exc:
                self._logger.info(f"MPV error: {exc}")
        super().showEvent(event)

    def resizeEvent(self, event):
        self.browser.setGeometry(self.geometry())
        super().resizeEvent(event)

    def moveEvent(self, event: QMoveEvent):
        self.browser.setGeometry(self.geometry())
        super().moveEvent(event)


def spawn_qt_window(session: Session, config: TriblerConfigManager) -> QMainWindow:
    """
    Create the tray icon.
    """
    api_port = session.rest_manager.get_api_port()
    api_host = config.get('api/http_host') or "127.0.0.1"
    api_key = config.get('api/key')

    window = TriblerWindow(config)
    window.set_api_server(api_host, api_port, api_key, session.shutdown_event)
    window.show()

    icon_path = tribler.get_webui_root() / "public" / "tribler.png"
    tray = QSystemTrayIcon(QIcon(str(icon_path)), QApplication.instance())
    tray_menu = QMenu()
    open_action = QAction("Open Tribler", tray)
    open_action.triggered.connect(window.show)
    tray_menu.addAction(open_action)
    tray_menu.addSeparator()
    exit_action = QAction("Exit", tray)
    exit_action.triggered.connect(lambda: session.shutdown_event.set())
    tray_menu.addAction(exit_action)
    tray.setContextMenu(tray_menu)
    tray.show()

    return window
