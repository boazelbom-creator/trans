"""Row highlighting for tables: the row under the mouse, and the selected row."""

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTableWidget

HOVER_COLOR = QColor("#e8f0fe")
SELECTED_COLOR = QColor("#c2dbff")


class _HoverDelegate(QStyledItemDelegate):
    def __init__(self, table: QTableWidget):
        super().__init__(table)
        self.hover_row = -1

    def paint(self, painter, option, index):
        # The row colors are painted here, not by the Windows style: the Windows 11 style draws
        # selection its own way and ignores the colors set on the table.
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, SELECTED_COLOR)
        elif index.row() == self.hover_row:
            painter.fillRect(option.rect, HOVER_COLOR)
        plain = QStyleOptionViewItem(option)
        plain.state &= ~(QStyle.State_Selected | QStyle.State_MouseOver | QStyle.State_HasFocus)
        super().paint(painter, plain, index)


class _HoverTracker(QObject):
    def __init__(self, table: QTableWidget, delegate: _HoverDelegate):
        super().__init__(table)
        self.table = table
        self.delegate = delegate

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseMove:
            row = self.table.rowAt(event.position().toPoint().y())
            self._set(row)
        elif event.type() == QEvent.Leave:
            self._set(-1)
        return False

    def _set(self, row: int) -> None:
        if row != self.delegate.hover_row:
            self.delegate.hover_row = row
            self.table.viewport().update()


def highlight_rows(table: QTableWidget) -> None:
    """Highlight the whole row under the mouse, and keep the selected row clearly visible."""
    delegate = _HoverDelegate(table)
    table.setItemDelegate(delegate)
    table.setMouseTracking(True)
    table.viewport().installEventFilter(_HoverTracker(table, delegate))

