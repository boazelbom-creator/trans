"""A row of image thumbnails: in the capture preview (with remove buttons) and on the detailed ad screen."""

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ..images import AdImage

THUMB_HEIGHT = 140


class _ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class ImageStrip(QScrollArea):
    changed = Signal()

    def __init__(self, removable: bool):
        super().__init__()
        self.removable = removable
        self.images: list[AdImage] = []
        self.setWidgetResizable(True)
        self.setFixedHeight(THUMB_HEIGHT + (60 if removable else 30))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._inner = QWidget()
        self._row = QHBoxLayout(self._inner)
        self._row.setAlignment(Qt.AlignLeft)  # mirrored in RTL: images start at the right
        self.setWidget(self._inner)
        self.setVisible(False)

    # ---- capture preview (removable) ----

    def set_ad_images(self, images: list[AdImage]) -> None:
        self.images = list(images)
        self._rebuild()

    def add_ad_image(self, image: AdImage) -> None:
        self.images.append(image)
        self._rebuild()
        self.changed.emit()

    def _remove(self, index: int) -> None:
        del self.images[index]
        self._rebuild()
        self.changed.emit()

    # ---- detailed ad screen (read-only; click opens the image) ----

    def set_files(self, paths: list[Path]) -> None:
        self.images = []
        self._clear()
        for path in paths:
            pixmap = QPixmap(str(path))
            label = self._thumb(pixmap, tooltip="לחצו לפתיחת התמונה")
            label.clicked.connect(lambda p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))))
            self._row.addWidget(label)
        self.setVisible(bool(paths))

    # ---- internals ----

    def _clear(self) -> None:
        while self._row.count():
            item = self._row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _thumb(self, pixmap: QPixmap, tooltip: str = "") -> _ClickableLabel:
        label = _ClickableLabel()
        if not pixmap.isNull():
            label.setPixmap(pixmap.scaledToHeight(THUMB_HEIGHT, Qt.SmoothTransformation))
        label.setFrameShape(QFrame.Box)
        label.setToolTip(tooltip)
        label.setCursor(Qt.PointingHandCursor if tooltip else Qt.ArrowCursor)
        return label

    def _rebuild(self) -> None:
        self._clear()
        for i, img in enumerate(self.images):
            pixmap = QPixmap()
            pixmap.loadFromData(QByteArray(img.data))
            box = QWidget()
            col = QVBoxLayout(box)
            col.setContentsMargins(0, 0, 0, 0)
            col.addWidget(self._thumb(pixmap))
            if self.removable:
                remove = QPushButton("הסרה")
                remove.clicked.connect(lambda _=False, idx=i: self._remove(idx))
                col.addWidget(remove)
            self._row.addWidget(box)
        self.setVisible(bool(self.images))
