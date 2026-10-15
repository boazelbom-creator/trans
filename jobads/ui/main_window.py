"""Main window: top bar with navigation, and the four screens (PRD §8)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QProgressDialog, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import APP_VERSION
from ..app_state import AppState
from .ad_screen import AdScreen
from .ads_screen import AdsScreen
from .collect_screen import CollectScreen
from .menu_screen import MenuScreen

MENU, COLLECT, ADS, AD = "menu", "collect", "ads", "ad"


class MainWindow(QMainWindow):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setWindowTitle(f"מודעות דרושים {APP_VERSION}")
        self.resize(1200, 800)
        self._busy: QProgressDialog | None = None

        # Top bar: community name + navigation (hidden on the menu screen)
        self.community_label = QLabel()
        self.community_label.setStyleSheet("font-weight: bold;")
        self.nav_buttons = {
            MENU: QPushButton("תפריט"),
            COLLECT: QPushButton("איסוף"),
            ADS: QPushButton("מודעות"),
        }
        bar = QHBoxLayout()
        bar.addWidget(self.community_label)
        bar.addStretch()
        for name, btn in self.nav_buttons.items():
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, n=name: self.show_screen(n))
            bar.addWidget(btn)
        self.top_bar = QWidget()
        self.top_bar.setLayout(bar)

        self.screens = {
            MENU: MenuScreen(self),
            COLLECT: CollectScreen(self),
            ADS: AdsScreen(self),
            AD: AdScreen(self),
        }
        self.stack = QStackedWidget()
        for screen in self.screens.values():
            self.stack.addWidget(screen)
        self.current = MENU

        layout = QVBoxLayout()
        layout.addWidget(self.top_bar)
        layout.addWidget(self.stack)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)
        self.show_screen(MENU)

    # ---- navigation ----

    def show_screen(self, name: str, **kwargs) -> None:
        current = self.screens[self.current]
        if name != self.current or kwargs:
            if hasattr(current, "can_leave") and not current.can_leave():
                self._update_nav()
                return
        self.current = name
        screen = self.screens[name]
        self.stack.setCurrentWidget(screen)
        screen.on_show(**kwargs)
        self._update_nav()

    def open_ad(self, ad_id: int) -> None:
        self.show_screen(AD, ad_id=ad_id)

    def _update_nav(self) -> None:
        community = self.state.community
        self.community_label.setText(f"קהילה: {community.info.display_name}" if community else "")
        self.top_bar.setVisible(self.current != MENU)
        for name, btn in self.nav_buttons.items():
            btn.setChecked(name == self.current or (name == ADS and self.current == AD))
            btn.setEnabled(name == MENU or community is not None)

    def community_changed(self) -> None:
        self._update_nav()

    # ---- busy indicator for slow operations ----

    def start_busy(self, text: str) -> None:
        self.end_busy()
        dlg = QProgressDialog(text, None, 0, 0, self)
        dlg.setWindowTitle("רגע...")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setCancelButton(None)
        dlg.setLayoutDirection(Qt.RightToLeft)
        dlg.setWindowFlag(Qt.WindowCloseButtonHint, False)
        dlg.show()
        self._busy = dlg

    def end_busy(self) -> None:
        if self._busy is not None:
            self._busy.close()
            self._busy.deleteLater()
            self._busy = None

    # ---- closing ----

    def closeEvent(self, event):
        current = self.screens[self.current]
        if hasattr(current, "can_leave") and not current.can_leave():
            event.ignore()
            return
        self.state.shutdown()
        event.accept()
