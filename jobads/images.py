"""Ad images: checking, resizing, saving (images captured with an ad or pasted by the user)."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QColor, QImage, QPainter

# Sonnet reads images up to about this size; bigger images are scaled down by the API anyway,
# so scaling them here keeps the request and the saved file small without losing anything.
MAX_SIDE = 1568
# Smaller images are profile pictures, icons and emojis, not ad content.
MIN_SIDE = 200
MAX_IMAGES = 4
JPEG_QUALITY = 88


@dataclass
class AdImage:
    data: bytes  # JPEG
    width: int
    height: int

    @property
    def media_type(self) -> str:
        return "image/jpeg"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


def from_qimage(image: QImage) -> AdImage | None:
    """Scale down if needed and encode as JPEG. Returns None for images too small to be ad content."""
    if image.isNull() or max(image.width(), image.height()) < MIN_SIDE:
        return None
    if max(image.width(), image.height()) > MAX_SIDE:
        image = image.scaled(MAX_SIDE, MAX_SIDE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    if image.hasAlphaChannel():
        # JPEG has no transparency: put the image on a white background.
        flat = QImage(image.size(), QImage.Format_RGB32)
        flat.fill(QColor("white"))
        painter = QPainter(flat)
        painter.drawImage(0, 0, image)
        painter.end()
        image = flat
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    image.save(buf, "JPEG", JPEG_QUALITY)
    return AdImage(bytes(buf.data()), image.width(), image.height())


def from_bytes(data: bytes) -> AdImage | None:
    """Image file bytes (JPEG, PNG, WebP, GIF...) -> AdImage, or None if unreadable or too small."""
    image = QImage.fromData(QByteArray(data))
    return from_qimage(image)


def combined_fingerprint(text_fingerprint: str, images: list[AdImage]) -> str:
    """The duplicate-check hash of an ad: the text alone, or the text plus its images."""
    if not images:
        return text_fingerprint
    parts = [text_fingerprint] + sorted(img.sha256 for img in images)
    return hashlib.sha256("|".join(parts).encode("ascii")).hexdigest()


def save(images: list[AdImage], images_dir: Path, ad_id: int) -> list[str]:
    """Save the images of an ad. Returns file names relative to images_dir."""
    images_dir.mkdir(parents=True, exist_ok=True)
    names = []
    for i, img in enumerate(images, start=1):
        name = f"{ad_id}_{i}.jpg"
        (images_dir / name).write_bytes(img.data)
        names.append(name)
    return names
