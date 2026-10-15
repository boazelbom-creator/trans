"""Menu screen (PRD §8.1)."""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ..browser import close_login_window, open_login_window
from . import dialogs, qt_async

log = logging.getLogger(__name__)

LOGIN_TEXT = (
    "נפתח חלון דפדפן עם פייסבוק וווטסאפ.\n\n"
    "1. התחברו לפייסבוק (שם משתמש וסיסמה, ואימות אם מתבקש).\n"
    "2. בלשונית של ווטסאפ, סרקו את קוד ה-QR עם הטלפון.\n"
    "3. בסיום, סגרו את חלון הדפדפן ולחצו כאן על \"סיימתי\".\n\n"
    "ההתחברות תישמר, ואין צורך לחזור על זה בכל פעם."
)


class MenuScreen(QWidget):
    def __init__(self, window):
        super().__init__()
        self.main = window
        self.state = window.state

        title = QLabel("מודעות דרושים")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 26pt; font-weight: bold;")

        self.community_label = QLabel()
        self.community_label.setAlignment(Qt.AlignCenter)
        self.community_label.setStyleSheet("font-size: 14pt;")

        self.chooser_label = QLabel("בחירת קהילה:")
        self.chooser = QComboBox()
        self.chooser.setMinimumWidth(300)
        self.chooser.activated.connect(self._choose)
        chooser_row = QHBoxLayout()
        chooser_row.addStretch()
        chooser_row.addWidget(self.chooser_label)
        chooser_row.addWidget(self.chooser)
        chooser_row.addStretch()

        self.group_edit = QLineEdit()
        self.group_edit.setMinimumWidth(300)
        self.group_edit.setPlaceholderText("שם הקבוצה בדיוק כפי שהוא מופיע בווטסאפ")
        self.group_edit.returnPressed.connect(self._save_group)
        self.group_save_btn = QPushButton("שמירה")
        self.group_save_btn.clicked.connect(self._save_group)
        self.group_row = QWidget()
        group_row = QHBoxLayout(self.group_row)
        group_row.addStretch()
        group_row.addWidget(QLabel("קבוצת ווטסאפ להפצה:"))
        group_row.addWidget(self.group_edit)
        group_row.addWidget(self.group_save_btn)
        group_row.addStretch()

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setStyleSheet("color: #b00020;")

        self.collect_btn = QPushButton("איסוף מודעות")
        self.ads_btn = QPushButton("הצגת מודעות")
        self.reload_btn = QPushButton("טעינה מחדש של קבצים")
        self.login_btn = QPushButton("התחברות לפייסבוק ולווטסאפ")
        for btn in (self.collect_btn, self.ads_btn):
            btn.setMinimumSize(260, 60)
            btn.setStyleSheet("font-size: 14pt;")
        self.collect_btn.clicked.connect(lambda: self.main.show_screen("collect"))
        self.ads_btn.clicked.connect(lambda: self.main.show_screen("ads"))
        self.reload_btn.clicked.connect(self._reload)
        self.login_btn.clicked.connect(self._login)

        buttons = QVBoxLayout()
        buttons.setAlignment(Qt.AlignCenter)
        for btn in (self.collect_btn, self.ads_btn):
            buttons.addWidget(btn, alignment=Qt.AlignCenter)
        buttons.addSpacing(20)
        buttons.addWidget(self.login_btn, alignment=Qt.AlignCenter)
        buttons.addWidget(self.reload_btn, alignment=Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(self.community_label)
        layout.addLayout(chooser_row)
        layout.addWidget(self.group_row)
        layout.addWidget(self.error_label)
        layout.addSpacing(30)
        layout.addLayout(buttons)
        layout.addStretch()

    def on_show(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        state = self.state
        community = state.community
        self.community_label.setText(f"קהילה פעילה: {community.info.display_name}" if community else "אין קהילה פעילה")

        self.chooser.clear()
        for info in state.communities:
            label = info.display_name if info.usable else f"{info.display_name} (חסרים קבצים: {', '.join(info.missing_files)})"
            self.chooser.addItem(label, info.folder)
            if not info.usable:
                item = self.chooser.model().item(self.chooser.count() - 1)
                item.setEnabled(False)
        if community:
            self.chooser.setCurrentIndex(self.chooser.findData(community.folder))
        many = len(state.communities) > 1
        self.chooser.setVisible(many)
        self.chooser_label.setVisible(many)

        self.group_row.setVisible(community is not None)
        self.group_edit.setText(community.info.whatsapp_group if community else "")

        self.error_label.setText(state.community_error)
        self.error_label.setVisible(bool(state.community_error))
        self.collect_btn.setEnabled(community is not None)
        self.ads_btn.setEnabled(community is not None)
        self.main.community_changed()

    def _save_group(self) -> None:
        group = self.group_edit.text().strip()
        if not group:
            dialogs.info(self, "קבוצת ווטסאפ", "הקלידו את שם הקבוצה כפי שהוא מופיע ברשימת הצ'אטים בווטסאפ.")
            return
        try:
            self.state.set_whatsapp_group(group)
        except OSError as e:
            dialogs.error_from(self, "קבוצת ווטסאפ", e)
            return
        self.group_edit.setText(group)
        dialogs.info(self, "קבוצת ווטסאפ", f"מודעות יופצו לקבוצה \"{group}\".")

    def _choose(self, index: int) -> None:
        folder = self.chooser.itemData(index)
        if self.state.community and folder == self.state.community.folder:
            return
        self.state.load_community(folder)
        self._refresh()
        if self.state.community_error:
            dialogs.error(self, "טעינת קהילה", self.state.community_error)

    def _reload(self) -> None:
        self.state.reload()
        self._refresh()
        if self.state.community_error:
            dialogs.error(self, "טעינה מחדש", self.state.community_error)
        else:
            dialogs.info(self, "טעינה מחדש", "הקבצים נטענו מחדש.")

    # ---- login window ----

    def _login(self) -> None:
        browser = self.state.browser
        self.main.start_busy("סוגר את חלון הדפדפן של התוכנה...")
        qt_async.watch(browser.submit(browser.close_browser), lambda _: self._open_login(), self._login_failed)

    def _open_login(self) -> None:
        self.main.end_busy()
        try:
            proc = open_login_window(self.state.paths.browser_profile)
        except Exception as e:
            self._login_failed(e)
            return
        dialogs.choose(self, "התחברות לפייסבוק ולווטסאפ", LOGIN_TEXT, ["סיימתי"], icon=dialogs.QMessageBox.Information)
        self.main.start_busy("מסיים את ההתחברות...")
        qt_async.run(close_login_window, proc, on_ok=lambda _: self._login_closed(), on_error=self._login_failed)

    def _login_closed(self) -> None:
        self.main.end_busy()
        log.info("Login window closed")
        dialogs.info(self, "התחברות", "ההתחברות הסתיימה. אפשר לאסוף ולהפיץ מודעות.")

    def _login_failed(self, exc: Exception) -> None:
        self.main.end_busy()
        dialogs.error_from(self, "התחברות", exc)
