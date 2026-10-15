"""Collecting screen: sources, capture, preview, rephrase (PRD §8.2)."""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import (
    QAbstractItemView, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import community as community_mod
from .. import images as images_mod
from .. import sonnet
from ..db import MANUAL_SOURCE
from ..excel_loader import SOURCE_TYPE_LABELS, SOURCE_WHATSAPP, Source
from ..text_clean import clean_text, fingerprint
from . import dialogs, qt_async
from .table_style import highlight_rows
from .image_strip import ImageStrip

log = logging.getLogger(__name__)

HINT = (
    "בחרו מקור ולחצו \"פתיחת מקור\". בדפדפן, סמנו בעכבר את טקסט המודעה ולחצו כאן על \"לכידה\".\n"
    "בפייסבוק: אם המודעה ארוכה, לחצו קודם על \"עוד\" (See more) כדי לפתוח את כל הטקסט, ורק אז סמנו אותו. "
    "תמונות של הפוסט נלכדות יחד עם הטקסט.\n"
    "תמונה שלא נלכדה: בדפדפן, לחצו עליה בכפתור הימני ← \"העתק תמונה\", ואז כאן \"הדבקת תמונה\" (או Ctrl+V בתיבת הטקסט)."
)

NO_IMAGE_IN_CLIPBOARD = "אין תמונה בלוח. בדפדפן, לחצו על התמונה בכפתור הימני ובחרו \"העתק תמונה\"."
IMAGE_TOO_SMALL = "התמונה קטנה מדי כדי להכיל פרטי משרה."
TOO_MANY_IMAGES = f"אפשר לצרף עד {images_mod.MAX_IMAGES} תמונות למודעה."


class _PasteTextEdit(QPlainTextEdit):
    """A text box where Ctrl+V of an image adds the image instead of pasting text."""

    image_pasted = Signal(QImage)

    def canInsertFromMimeData(self, source):
        return source.hasImage() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if source.hasImage():
            self.image_pasted.emit(QImage(source.imageData()))
        else:
            super().insertFromMimeData(source)


class CollectScreen(QWidget):
    def __init__(self, window):
        super().__init__()
        self.main = window
        self.state = window.state
        self.sources: list[Source] = []
        self.current_source: Source | None = None
        self.preview_source_name = ""
        self.preview_source_url = ""

        hint = QLabel(HINT)
        hint.setWordWrap(True)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["שם", "סוג", "טווח", "הערות", "תדירות"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.doubleClicked.connect(lambda _: self._open_source())
        highlight_rows(self.table)

        self.open_btn = QPushButton("פתיחת מקור")
        self.capture_btn = QPushButton("לכידה")
        self.paste_btn = QPushButton("הדבקה ידנית")
        self.capture_btn.setStyleSheet("font-weight: bold;")
        self.open_btn.clicked.connect(self._open_source)
        self.capture_btn.clicked.connect(self._capture)
        self.paste_btn.clicked.connect(self._paste_manually)
        actions = QHBoxLayout()
        for b in (self.open_btn, self.capture_btn, self.paste_btn):
            actions.addWidget(b)
        actions.addStretch()

        # Preview panel, shown after capture / paste
        self.preview = QGroupBox("תצוגה מקדימה")
        self.preview_source = QLabel()
        self.preview_source.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.preview_text = _PasteTextEdit()
        dialogs.make_rtl(self.preview_text)
        self.preview_text.image_pasted.connect(self._add_qimage)
        self.preview_images = ImageStrip(removable=True)
        self.paste_image_btn = QPushButton("הדבקת תמונה")
        self.paste_image_btn.clicked.connect(lambda: self._add_qimage(QGuiApplication.clipboard().image()))
        self.rewrite_btn = QPushButton("שכתוב")
        self.cancel_btn = QPushButton("ביטול")
        self.rewrite_btn.setStyleSheet("font-weight: bold;")
        self.rewrite_btn.clicked.connect(self._rewrite)
        self.cancel_btn.clicked.connect(self._close_preview)
        preview_buttons = QHBoxLayout()
        preview_buttons.addWidget(self.rewrite_btn)
        preview_buttons.addWidget(self.cancel_btn)
        preview_buttons.addStretch()
        preview_buttons.addWidget(self.paste_image_btn)
        p_layout = QVBoxLayout(self.preview)
        p_layout.addWidget(self.preview_source)
        p_layout.addWidget(self.preview_text)
        p_layout.addWidget(self.preview_images)
        p_layout.addLayout(preview_buttons)
        self.preview.setVisible(False)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.table, 1)
        layout.addLayout(actions)
        layout.addWidget(self.preview, 1)

    # ---- screen ----

    def on_show(self) -> None:
        community = self.state.community
        sources = community.aids.sources if community else []
        if sources is not self.sources:
            self.sources = sources
            self.current_source = None
            self._fill_table()

    def can_leave(self) -> bool:
        if not self.preview.isHidden() and (self.preview_text.toPlainText().strip() or self.preview_images.images):
            choice = dialogs.choose(
                self, "מודעה שלא נשלחה לשכתוב",
                "יש מודעה בתצוגה המקדימה שעוד לא נשלחה לשכתוב. לעזוב את המסך?",
                ["להישאר", "לעזוב (המודעה תימחק)"],
            )
            if choice != 1:
                return False
            self._close_preview()
        return True

    def _fill_table(self) -> None:
        self.table.setRowCount(len(self.sources))
        for row, s in enumerate(self.sources):
            values = [s.name, SOURCE_TYPE_LABELS.get(s.type, s.type), s.range, s.notes, s.frequency]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(s.url if col == 0 else value)
                self.table.setItem(row, col, item)

    def _selected_source(self) -> Source | None:
        rows = self.table.selectionModel().selectedRows()
        return self.sources[rows[0].row()] if rows else None

    # ---- actions ----

    def _open_source(self) -> None:
        source = self._selected_source()
        if source is None:
            dialogs.info(self, "פתיחת מקור", "בחרו מקור מהרשימה.")
            return
        if not source.url:
            dialogs.error(self, "פתיחת מקור", f"למקור \"{source.name}\" אין קישור בקובץ האקסל.")
            return
        self.current_source = source
        browser = self.state.browser
        self.main.start_busy("פותח את הדפדפן...")
        if source.type == SOURCE_WHATSAPP:
            future = browser.submit(browser.open_whatsapp_chat, source.name)
            qt_async.watch(future, self._whatsapp_opened, self._browser_failed)
        else:
            future = browser.submit(browser.open_url, source.url)
            qt_async.watch(future, lambda _: self.main.end_busy(), self._browser_failed)

    def _whatsapp_opened(self, found: bool) -> None:
        self.main.end_busy()
        if not found:
            dialogs.info(
                self, "פתיחת מקור",
                f"הצ'אט \"{self.current_source.name}\" לא נמצא בווטסאפ. פתחו אותו בעצמכם בחלון הדפדפן.",
            )

    def _browser_failed(self, exc: Exception) -> None:
        self.main.end_busy()
        dialogs.error_from(self, "דפדפן", exc)

    def _capture(self) -> None:
        browser = self.state.browser
        self.main.start_busy("קורא את הטקסט שסומן...")
        qt_async.watch(browser.submit(browser.capture), self._captured, self._browser_failed)

    def _captured(self, result: tuple[str, str, list[bytes]]) -> None:
        self.main.end_busy()
        text, url, raw_images = result
        name = self.current_source.name if self.current_source else ""
        imgs = [img for data in raw_images if (img := images_mod.from_bytes(data))]
        self._show_preview(clean_text(text), name, url, imgs[: images_mod.MAX_IMAGES])

    def _paste_manually(self) -> None:
        self._show_preview("", MANUAL_SOURCE, "")
        self.preview_text.setPlaceholderText("הדביקו כאן את טקסט המודעה (ותמונות, עם Ctrl+V)")
        self.preview_text.setFocus()

    def _show_preview(self, text: str, source_name: str, source_url: str, imgs: list | None = None) -> None:
        self.preview_source_name = source_name or MANUAL_SOURCE
        self.preview_source_url = source_url
        label = f"מקור: {self.preview_source_name}"
        if source_url:
            label += f"   |   {source_url}"
        self.preview_source.setText(label)
        self.preview_text.setPlainText(text)
        self.preview_images.set_ad_images(imgs or [])
        self.preview.setVisible(True)

    def _add_qimage(self, qimage: QImage) -> None:
        if qimage.isNull():
            dialogs.info(self, "הדבקת תמונה", NO_IMAGE_IN_CLIPBOARD)
            return
        if len(self.preview_images.images) >= images_mod.MAX_IMAGES:
            dialogs.info(self, "הדבקת תמונה", TOO_MANY_IMAGES)
            return
        img = images_mod.from_qimage(qimage)
        if img is None:
            dialogs.info(self, "הדבקת תמונה", IMAGE_TOO_SMALL)
            return
        if self.preview.isHidden():
            self._show_preview("", self.current_source.name if self.current_source else MANUAL_SOURCE, "")
        self.preview_images.add_ad_image(img)

    def _close_preview(self) -> None:
        self.preview_text.clear()
        self.preview_images.set_ad_images([])
        self.preview.setVisible(False)

    def _rewrite(self) -> None:
        state = self.state
        community = state.community
        # Pasted text is cleaned here; captured text was cleaned already (cleaning twice changes nothing).
        text = clean_text(self.preview_text.toPlainText())
        imgs = list(self.preview_images.images)
        if not text and not imgs:
            dialogs.info(self, "שכתוב", "אין טקסט או תמונה לשכתוב.")
            return
        self.preview_text.setPlainText(text)

        origin_hash = images_mod.combined_fingerprint(fingerprint(text), imgs)
        existing = state.db.find_by_hash(community.folder, origin_hash)
        if existing is not None:
            choice = dialogs.choose(
                self, "המודעה כבר קיימת",
                "מודעה זהה כבר שמורה במערכת.",
                ["פתיחת המודעה הקיימת", "המשך בכל זאת", "ביטול"], icon=dialogs.QMessageBox.Warning,
            )
            if choice == 0:
                self._close_preview()
                self.main.open_ad(existing)
                return
            if choice != 1:
                return

        self.main.start_busy("המודעה נשלחת לשכתוב. זה עשוי לקחת עד דקה...")
        qt_async.run(
            sonnet.rewrite, state.client, community, text, state.config.model, state.config.effort, imgs,
            on_ok=lambda result: self._rewritten(result, community, text, origin_hash, imgs),
            on_error=self._rewrite_failed,
        )

    def _rewrite_failed(self, exc: Exception) -> None:
        self.main.end_busy()
        dialogs.error_from(self, "שכתוב", exc)  # the text stays in the preview

    def _rewritten(self, result: sonnet.RewriteResult, community, text: str, origin_hash: str, imgs: list) -> None:
        self.main.end_busy()
        if not result.is_job_ad:
            dialogs.info(self, "שכתוב", "הטקסט אינו מודעת דרושים. המודעה לא נשמרה.")
            return
        state = self.state
        try:
            community_mod.save_prompt_snapshot(community, state.paths.prompt_versions)
        except OSError:
            log.exception("Could not save the prompt version snapshot")
        ad_id = state.db.add_ad(
            community=community.folder,
            source_name=self.preview_source_name,
            source_url=self.preview_source_url,
            origin_ad=text,
            origin_hash=origin_hash,
            sonnet_ad=result.rewritten_ad,
            tags=result.tags,
            keywords=result.keywords,
            score=result.score,
            score_reason=result.score_reason,
            model=result.model,
            prompt_version=community.prompt_version,
        )
        if imgs:
            try:
                state.db.set_images(ad_id, images_mod.save(imgs, state.paths.images, ad_id))
            except OSError:
                log.exception("Could not save the images of ad %s", ad_id)
        log.info("Ad %s saved (score %s, %d images)", ad_id, result.score, len(imgs))
        self._close_preview()
        self.main.open_ad(ad_id)
