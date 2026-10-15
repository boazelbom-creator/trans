"""Presenting screen: list of ads with filters, without the ad text (PRD §8.3)."""

from datetime import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..db import STATUS_LABELS, STATUSES, Ad
from .table_style import highlight_rows

ALL = "הכול"


def format_date(iso: str) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso


class _Item(QTableWidgetItem):
    """A table cell that sorts by a key instead of by its text."""

    def __init__(self, text: str, key):
        super().__init__(text)
        self.key = key

    def __lt__(self, other):
        if isinstance(other, _Item):
            return self.key < other.key
        return super().__lt__(other)


class _CheckList(QWidget):
    """A list of checkboxes with a search box (for tags and keywords)."""

    def __init__(self, on_change):
        super().__init__()
        self.search = QLineEdit()
        self.search.setPlaceholderText("חיפוש...")
        self.search.textChanged.connect(self._filter)
        self.list = QListWidget()
        self.list.setMinimumHeight(140)
        self.list.itemChanged.connect(lambda _: on_change())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.search)
        layout.addWidget(self.list)

    def set_items(self, names: list[str]) -> None:
        checked = self.checked()
        self.list.blockSignals(True)
        self.list.clear()
        for name in names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if name in checked else Qt.Unchecked)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._filter(self.search.text())

    def checked(self) -> set[str]:
        return {
            self.list.item(i).text() for i in range(self.list.count()) if self.list.item(i).checkState() == Qt.Checked
        }

    def clear_checks(self) -> None:
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.Unchecked)
        self.list.blockSignals(False)
        self.search.clear()

    def _filter(self, text: str) -> None:
        text = text.strip().lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(bool(text) and text not in item.text().lower())


class AdsScreen(QWidget):
    COLUMNS = ["תאריך איסוף", "מקור", "סטטוס", "ציון", "תגיות", "מילות מפתח"]

    def __init__(self, window):
        super().__init__()
        self.main = window
        self.state = window.state
        self.ads: list[Ad] = []
        self._community_folder = None

        # ---- filters ----
        self.status_boxes = {}
        status_box = QGroupBox("סטטוס")
        s_layout = QVBoxLayout(status_box)
        for status in STATUSES:
            cb = QCheckBox(STATUS_LABELS[status])
            cb.toggled.connect(self._apply)
            s_layout.addWidget(cb)
            self.status_boxes[status] = cb

        self.tags = _CheckList(self._apply)
        tags_box = QGroupBox("תגיות (כל התגיות שנבחרו)")
        QVBoxLayout(tags_box).addWidget(self.tags)

        self.keywords = _CheckList(self._apply)
        kw_box = QGroupBox("מילות מפתח (כל המילים שנבחרו)")
        QVBoxLayout(kw_box).addWidget(self.keywords)

        self.score_min = QSpinBox()
        self.score_max = QSpinBox()
        for sb, value in ((self.score_min, 0), (self.score_max, 100)):
            sb.setRange(0, 100)
            sb.setValue(value)
            sb.valueChanged.connect(self._apply)

        self.source = QComboBox()
        self.source.currentIndexChanged.connect(self._apply)

        self.date_filter = QCheckBox("סינון לפי תאריך")
        self.date_from = QDateEdit()
        self.date_to = QDateEdit()
        today = QDate.currentDate()
        for de, date in ((self.date_from, today.addMonths(-1)), (self.date_to, today)):
            de.setLayoutDirection(Qt.LeftToRight)  # must come before the format, or Qt reverses it to year/month/day
            de.setCalendarPopup(True)
            de.setDisplayFormat("dd/MM/yyyy")
            de.setDate(date)
            de.dateChanged.connect(self._apply)
        self.date_filter.toggled.connect(self._apply)

        other_box = QGroupBox("סינון נוסף")
        form = QFormLayout(other_box)
        form.addRow("ציון מ-", self.score_min)
        form.addRow("עד", self.score_max)
        form.addRow("מקור", self.source)
        form.addRow(self.date_filter)
        form.addRow("מתאריך", self.date_from)
        form.addRow("עד תאריך", self.date_to)

        clear_btn = QPushButton("ניקוי סינון")
        clear_btn.clicked.connect(self._clear_filters)

        filters = QWidget()
        f_layout = QVBoxLayout(filters)
        for w in (status_box, other_box, tags_box, kw_box, clear_btn):
            f_layout.addWidget(w)
        f_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidget(filters)
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(300)

        # ---- table ----
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        header.setSortIndicator(0, Qt.DescendingOrder)  # default: newest first
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(lambda _: self._open())
        highlight_rows(self.table)

        self.counter = QLabel()
        open_btn = QPushButton("פתיחה")
        open_btn.clicked.connect(self._open)
        bottom = QHBoxLayout()
        bottom.addWidget(self.counter)
        bottom.addStretch()
        bottom.addWidget(open_btn)

        right = QVBoxLayout()
        right.addWidget(self.table)
        right.addLayout(bottom)

        layout = QHBoxLayout(self)
        layout.addWidget(scroll)
        layout.addLayout(right, 1)

    # ---- screen ----

    def on_show(self) -> None:
        community = self.state.community
        if community is None:
            return
        if community.folder != self._community_folder:
            self._community_folder = community.folder
            self.tags.clear_checks()
            self.keywords.clear_checks()
        self.ads = self.state.db.list_ads(community.folder)
        # Lists include terms from the Excel and from saved ads (in case the Excel changed since).
        self.tags.set_items(_merge(community.tag_names, (t for a in self.ads for t in a.tags)))
        self.keywords.set_items(_merge(community.keyword_names, (k for a in self.ads for k in a.keywords)))
        current_source = self.source.currentText()
        self.source.blockSignals(True)
        self.source.clear()
        self.source.addItem(ALL)
        self.source.addItems(sorted({a.source_name for a in self.ads if a.source_name}))
        idx = self.source.findText(current_source)
        self.source.setCurrentIndex(idx if idx >= 0 else 0)
        self.source.blockSignals(False)
        self._apply()

    # ---- filtering ----

    def _matches(self, ad: Ad) -> bool:
        statuses = {s for s, cb in self.status_boxes.items() if cb.isChecked()}
        if statuses and ad.status not in statuses:
            return False
        if not self.tags.checked() <= set(ad.tags):
            return False
        if not self.keywords.checked() <= set(ad.keywords):
            return False
        if not (self.score_min.value() <= ad.score <= self.score_max.value()):
            return False
        if self.source.currentIndex() > 0 and ad.source_name != self.source.currentText():
            return False
        if self.date_filter.isChecked():
            day = ad.collect_date[:10]
            if not (self.date_from.date().toString("yyyy-MM-dd") <= day <= self.date_to.date().toString("yyyy-MM-dd")):
                return False
        return True

    def _apply(self) -> None:
        shown = [a for a in self.ads if self._matches(a)]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(shown))
        for row, ad in enumerate(shown):
            cells = [
                _Item(format_date(ad.collect_date), ad.collect_date),
                _Item(ad.source_name, ad.source_name),
                _Item(STATUS_LABELS.get(ad.status, ad.status), STATUSES.index(ad.status) if ad.status in STATUSES else 9),
                _Item(str(ad.score), ad.score),
                _Item(" ".join(ad.tags), " ".join(ad.tags)),
                _Item(", ".join(ad.keywords), ", ".join(ad.keywords)),
            ]
            cells[0].setData(Qt.UserRole, ad.id)
            for col, item in enumerate(cells):
                self.table.setItem(row, col, item)
        self.table.setSortingEnabled(True)  # re-sorts by the column the user chose
        self.counter.setText(f"מוצגות {len(shown)} מתוך {len(self.ads)} מודעות")

    def _clear_filters(self) -> None:
        for cb in self.status_boxes.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self.tags.clear_checks()
        self.keywords.clear_checks()
        self.score_min.setValue(0)
        self.score_max.setValue(100)
        self.source.setCurrentIndex(0)
        self.date_filter.setChecked(False)
        self._apply()

    def _open(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        ad_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        self.main.open_ad(ad_id)


def _merge(primary: list[str], extra) -> list[str]:
    result = list(dict.fromkeys(primary))
    seen = set(result)
    for item in extra:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
