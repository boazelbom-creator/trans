"""Message boxes with Hebrew buttons, and RTL helpers."""

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QMessageBox, QPlainTextEdit, QWidget

log = logging.getLogger(__name__)

GENERIC_ERROR = "אירעה שגיאה. הפרטים נשמרו ביומן (logs\\app.log)."


def _box(parent: QWidget | None, icon, title: str, text: str) -> QMessageBox:
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    box.setLayoutDirection(Qt.RightToLeft)
    return box


def info(parent, title: str, text: str) -> None:
    box = _box(parent, QMessageBox.Information, title, text)
    box.addButton("אישור", QMessageBox.AcceptRole)
    box.exec()


def error(parent, title: str, text: str) -> None:
    box = _box(parent, QMessageBox.Critical, title, text)
    box.addButton("אישור", QMessageBox.AcceptRole)
    box.exec()


def error_from(parent, title: str, exc: BaseException) -> None:
    """Show an exception: its Hebrew user_message if it has one, otherwise a generic message (and log it)."""
    message = getattr(exc, "user_message", None)
    if message:
        log.warning("%s: %s", title, exc)
    else:
        log.error("%s", title, exc_info=(type(exc), exc, exc.__traceback__))
        message = GENERIC_ERROR
    error(parent, title, message)


def choose(parent, title: str, text: str, buttons: list[str], icon=QMessageBox.Question) -> int:
    """Ask a question with Hebrew buttons. Returns the index of the button clicked (-1 if closed)."""
    box = _box(parent, icon, title, text)
    added = [box.addButton(label, QMessageBox.AcceptRole) for label in buttons]
    box.setDefaultButton(added[0])
    box.exec()
    clicked = box.clickedButton()
    return added.index(clicked) if clicked in added else -1


def ask_yes_no(parent, title: str, text: str) -> bool:
    return choose(parent, title, text, ["כן", "לא"]) == 0


def make_rtl(edit: QPlainTextEdit) -> None:
    """Show every line right-to-left, also lines that start with an English word."""
    edit.setLayoutDirection(Qt.RightToLeft)
    option = edit.document().defaultTextOption()
    option.setTextDirection(Qt.RightToLeft)
    option.setAlignment(Qt.AlignRight)
    option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    edit.document().setDefaultTextOption(option)
