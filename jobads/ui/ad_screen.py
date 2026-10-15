"""Detailed ad screen: text, characteristics, approve/reject, distribute (PRD §8.4, §10.3)."""

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from ..db import STATUS_APPROVED, STATUS_DISTRIBUTED, STATUS_LABELS, STATUS_NEW, STATUS_REJECTED, Ad
from . import dialogs, qt_async
from .ads_screen import format_date
from .image_strip import ImageStrip

log = logging.getLogger(__name__)


def _value_label() -> QLabel:
    label = QLabel()
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


class AdScreen(QWidget):
    def __init__(self, window):
        super().__init__()
        self.main = window
        self.state = window.state
        self.ad: Ad | None = None
        self._image_paths = []

        self.title = QLabel()
        self.title.setStyleSheet("font-size: 16pt; font-weight: bold;")

        # ---- ad text (editable) and original (collapsible) ----
        self.text = QPlainTextEdit()
        dialogs.make_rtl(self.text)
        self.text.textChanged.connect(self._update_buttons)

        self.origin_toggle = QToolButton()
        self.origin_toggle.setText("הצגת מודעת המקור")
        self.origin_toggle.setCheckable(True)
        self.origin_toggle.toggled.connect(self._toggle_origin)
        self.origin = QPlainTextEdit()
        self.origin.setReadOnly(True)
        dialogs.make_rtl(self.origin)
        self.origin.setVisible(False)
        self.origin_images = ImageStrip(removable=False)

        text_col = QVBoxLayout()
        text_col.addWidget(QLabel("טקסט המודעה להפצה:"))
        text_col.addWidget(self.text, 3)
        text_col.addWidget(self.origin_toggle, alignment=Qt.AlignLeft)  # mirrored in RTL: the start side
        text_col.addWidget(self.origin, 2)
        text_col.addWidget(self.origin_images)

        # ---- characteristics ----
        self.status = _value_label()
        self.status.setStyleSheet("font-weight: bold;")
        self.score = _value_label()
        self.score.setStyleSheet("font-weight: bold;")
        self.score_reason = _value_label()
        self.tags = _value_label()
        self.keywords = _value_label()
        self.source = _value_label()
        self.source.setOpenExternalLinks(True)
        self.source.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.collect_date = _value_label()
        self.distribute_date = _value_label()
        self.model = _value_label()
        self.images_count = _value_label()

        info_box = QGroupBox("מאפיינים")
        info_box.setFixedWidth(380)
        form = QFormLayout(info_box)
        form.addRow("סטטוס:", self.status)
        form.addRow("ציון:", self.score)
        form.addRow("הסבר לציון:", self.score_reason)
        form.addRow("תגיות:", self.tags)
        form.addRow("מילות מפתח:", self.keywords)
        form.addRow("מקור:", self.source)
        form.addRow("תמונות:", self.images_count)
        form.addRow("תאריך איסוף:", self.collect_date)
        form.addRow("תאריך הפצה:", self.distribute_date)
        form.addRow("מודל:", self.model)

        body = QHBoxLayout()
        body.addLayout(text_col, 1)
        body.addWidget(info_box)

        # ---- actions ----
        self.save_btn = QPushButton("שמירה")
        self.approve_btn = QPushButton("אישור")
        self.reject_btn = QPushButton("דחייה")
        self.reset_btn = QPushButton("החזרה לחדשה")
        self.distribute_btn = QPushButton("הפצה")
        self.copy_btn = QPushButton("העתקה")
        self.back_btn = QPushButton("חזרה לרשימה")
        self.distribute_btn.setStyleSheet("font-weight: bold;")
        self.save_btn.clicked.connect(self._save)
        self.approve_btn.clicked.connect(self._approve)
        self.reject_btn.clicked.connect(lambda: self._set_status(STATUS_REJECTED))
        self.reset_btn.clicked.connect(lambda: self._set_status(STATUS_NEW))
        self.distribute_btn.clicked.connect(self._distribute)
        self.copy_btn.clicked.connect(self._copy)
        self.back_btn.clicked.connect(lambda: self.main.show_screen("ads"))
        actions = QHBoxLayout()
        for b in (self.save_btn, self.approve_btn, self.reject_btn, self.reset_btn, self.distribute_btn, self.copy_btn):
            actions.addWidget(b)
        actions.addStretch()
        actions.addWidget(self.back_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addLayout(body, 1)
        layout.addLayout(actions)

    # ---- screen ----

    def on_show(self, ad_id: int | None = None) -> None:
        if ad_id is not None:
            self._load(ad_id)

    def can_leave(self) -> bool:
        if not self._dirty():
            return True
        choice = dialogs.choose(self, "שינויים שלא נשמרו", "טקסט המודעה השתנה ולא נשמר.", ["שמירה", "ביטול השינויים", "להישאר"])
        if choice == 0:
            self._save()
            return True
        if choice == 1:
            self._show_ad()  # back to the saved text
            return True
        return False

    def _load(self, ad_id: int) -> None:
        self.ad = self.state.db.get_ad(ad_id)
        self._show_ad()

    def _show_ad(self) -> None:
        ad = self.ad
        if ad is None:
            return
        self.title.setText(f"מודעה #{ad.id}")
        self.text.blockSignals(True)
        self.text.setPlainText(ad.user_ad)
        self.text.blockSignals(False)
        self.origin.setPlainText(ad.origin_ad)
        self._image_paths = [self.state.paths.images / name for name in ad.origin_images]
        self.images_count.setText(f"{len(ad.origin_images)} (מוצגות עם מודעת המקור)" if ad.origin_images else "-")
        self._show_origin_images()
        self.status.setText(STATUS_LABELS.get(ad.status, ad.status))
        self.score.setText(f"{ad.score} מתוך 100")
        self.score_reason.setText(ad.score_reason)
        self.tags.setText(" ".join(ad.tags) or "-")
        self.keywords.setText(", ".join(ad.keywords) or "-")
        if ad.source_url:
            url = ad.source_url.replace('"', "%22")
            self.source.setText(f'{ad.source_name}<br><a href="{url}">פתיחת הקישור</a>')
        else:
            self.source.setText(ad.source_name)
        self.collect_date.setText(format_date(ad.collect_date))
        self.distribute_date.setText(format_date(ad.distribute_date) or "-")
        self.model.setText(ad.model)
        self._update_buttons()

    def _dirty(self) -> bool:
        return self.ad is not None and self.text.toPlainText() != self.ad.user_ad

    def _update_buttons(self) -> None:
        status = self.ad.status if self.ad else None
        editable = status in (STATUS_NEW, STATUS_APPROVED)
        self.text.setReadOnly(not editable)
        self.save_btn.setEnabled(editable and self._dirty())
        self.approve_btn.setEnabled(status == STATUS_NEW)
        self.reject_btn.setEnabled(status == STATUS_NEW)
        self.reset_btn.setEnabled(status in (STATUS_APPROVED, STATUS_REJECTED))
        self.distribute_btn.setEnabled(status == STATUS_APPROVED)

    def _show_origin_images(self) -> None:
        if self.origin_toggle.isChecked():
            self.origin_images.set_files([p for p in self._image_paths if p.exists()])
        else:
            self.origin_images.setVisible(False)

    def _toggle_origin(self, shown: bool) -> None:
        self.origin.setVisible(shown)
        self._show_origin_images()
        self.origin_toggle.setText("הסתרת מודעת המקור" if shown else "הצגת מודעת המקור")

    # ---- actions ----

    def _save(self) -> None:
        if not self._dirty():
            return
        text = self.text.toPlainText()
        self.state.db.update_text(self.ad.id, text)
        self.ad.user_ad = text
        self._update_buttons()

    def _set_status(self, status: str) -> None:
        self._save()
        self.state.db.set_status(self.ad.id, status)
        self._load(self.ad.id)

    def _approve(self) -> None:
        if not self.text.toPlainText().strip():
            dialogs.info(self, "אישור", "לא ניתן לאשר מודעה ריקה.")
            return
        self._set_status(STATUS_APPROVED)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.text.toPlainText())
        dialogs.info(self, "העתקה", "טקסט המודעה הועתק.")

    def _distribute(self) -> None:
        community = self.state.community
        group = community.info.whatsapp_group if community else ""
        if not group:
            dialogs.error(
                self, "הפצה",
                "לא הוגדרה קבוצת ווטסאפ להפצה.\nהקלידו את שם הקבוצה בשדה \"קבוצת ווטסאפ להפצה\" במסך התפריט.",
            )
            return
        self._save()
        text = self.ad.user_ad
        browser = self.state.browser
        self.main.start_busy("פותח את ווטסאפ וממלא את ההודעה...")
        qt_async.watch(browser.submit(browser.fill_whatsapp, group, text), lambda _: self._filled(), self._fill_failed)

    def _filled(self) -> None:
        self.main.end_busy()
        dialogs.info(self, "הפצה", "ההודעה מולאה בווטסאפ. בדקו אותה בחלון הדפדפן ולחצו שם על \"שליחה\".")
        if dialogs.ask_yes_no(self, "הפצה", "האם ההודעה נשלחה?"):
            self.state.db.mark_distributed(self.ad.id)
            self._load(self.ad.id)

    def _fill_failed(self, exc: Exception) -> None:
        self.main.end_busy()
        QGuiApplication.clipboard().setText(self.ad.user_ad)
        message = getattr(exc, "user_message", None) or dialogs.GENERIC_ERROR
        if not getattr(exc, "user_message", None):
            log.error("Distribution failed", exc_info=(type(exc), exc, exc.__traceback__))
        else:
            log.warning("Distribution failed: %s", exc)
        dialogs.error(
            self, "הפצה",
            f"{message}\n\nטקסט המודעה הועתק ללוח. אפשר להדביק אותו בווטסאפ בעצמכם (Ctrl+V).",
        )
