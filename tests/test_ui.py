"""UI smoke tests, run without a display (QT_QPA_PLATFORM=offscreen). No browser and no API calls."""

import json
import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from jobads import sonnet  # noqa: E402
from jobads.app_state import AppState  # noqa: E402
from jobads.config import load_config  # noqa: E402
from jobads.db import STATUS_APPROVED, STATUS_DISTRIBUTED, Database  # noqa: E402
from jobads.paths import Paths  # noqa: E402
from jobads.text_clean import fingerprint  # noqa: E402
from jobads.ui import dialogs, qt_async  # noqa: E402
from jobads.ui.main_window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    a.setLayoutDirection(Qt.RightToLeft)
    qt_async.init()
    return a


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    shutil.copytree(ROOT / "communities", tmp_path / "communities")
    shutil.copytree(ROOT / "communities" / "autism", tmp_path / "communities" / "second")
    (tmp_path / "config.json").write_text(json.dumps({
        "active_community": "autism",
        "communities": {"autism": {"display_name": "אוטיזם", "whatsapp_group": "thomas vinters"}},
    }, ensure_ascii=False), encoding="utf-8")
    paths = Paths(tmp_path)
    paths.ensure_dirs()
    state = AppState(paths, load_config(paths.config), "test-key", Database(paths.db))
    state.load_initial_community()

    shown = []
    monkeypatch.setattr(dialogs, "info", lambda p, t, m: shown.append(("info", m)))
    monkeypatch.setattr(dialogs, "error", lambda p, t, m: shown.append(("error", m)))
    w = MainWindow(state)
    w.shown_dialogs = shown
    yield w
    state.browser._executor.shutdown(wait=False)
    state.db.close()


def _add(state, text, tags, keywords, score):
    return state.db.add_ad(
        community="autism", source_name="מקור", source_url="https://example.com", origin_ad=text,
        origin_hash=fingerprint(text), sonnet_ad="משוכתב: " + text, tags=tags, keywords=keywords,
        score=score, score_reason="סיבה", model="claude-sonnet-5-5", prompt_version="v",
    )


def test_menu_lists_communities(window):
    menu = window.screens["menu"]
    assert window.state.community.folder == "autism"
    assert menu.chooser.count() == 2 and not menu.chooser.isHidden()
    assert window.top_bar.isHidden()
    menu._choose(menu.chooser.findData("second"))
    assert window.state.community.folder == "second"
    assert load_config(window.state.paths.config).active_community == "second"


def test_collect_screen_sources(window):
    window.show_screen("collect")
    collect = window.screens["collect"]
    assert collect.table.rowCount() == 16
    assert not window.top_bar.isHidden()


def test_ads_list_filters(window):
    state = window.state
    _add(state, "מודעה 1", ["#חלקית"], ["CNC"], 80)
    _add(state, "מודעה 2", ["#חלקית", "#ללא_ניסיון"], [], 40)
    a3 = _add(state, "מודעה 3", ["#מלאה"], [], 10)
    state.db.set_status(a3, STATUS_APPROVED)

    window.show_screen("ads")
    ads = window.screens["ads"]
    assert ads.table.rowCount() == 3
    assert ads.table.columnCount() == 6  # no ad text column

    def check(list_widget, name):
        for i in range(list_widget.list.count()):
            if list_widget.list.item(i).text() == name:
                list_widget.list.item(i).setCheckState(Qt.Checked)

    check(ads.tags, "#חלקית")
    assert ads.table.rowCount() == 2
    check(ads.tags, "#ללא_ניסיון")
    assert ads.table.rowCount() == 1
    ads._clear_filters()
    ads.status_boxes[STATUS_APPROVED].setChecked(True)
    assert ads.table.rowCount() == 1
    ads._clear_filters()
    ads.score_min.setValue(50)
    assert ads.table.rowCount() == 1
    assert "1 מתוך 3" in ads.counter.text()


def test_ad_screen_edit_approve(window, monkeypatch):
    state = window.state
    ad_id = _add(state, "מודעה", ["#חלקית"], [], 70)
    window.open_ad(ad_id)
    screen = window.screens["ad"]
    assert screen.text.toPlainText() == "משוכתב: מודעה"
    assert screen.approve_btn.isEnabled() and not screen.distribute_btn.isEnabled()

    screen.text.setPlainText("טקסט ערוך")
    assert screen.save_btn.isEnabled()
    # leaving with unsaved text asks; choose "stay"
    monkeypatch.setattr(dialogs, "choose", lambda *a, **k: 2)
    window.show_screen("ads")
    assert window.current == "ad"

    screen._approve()  # saves the text and approves
    ad = state.db.get_ad(ad_id)
    assert ad.status == STATUS_APPROVED and ad.user_ad == "טקסט ערוך" and ad.sonnet_ad == "משוכתב: מודעה"
    assert screen.distribute_btn.isEnabled() and not screen.approve_btn.isEnabled()

    screen.text.setPlainText("")
    screen._show_ad()
    window.show_screen("ads")
    assert window.current == "ads"


def test_rewrite_flow_with_fake_sonnet(window, app, monkeypatch):
    def fake_rewrite(client, community, text, model, effort, images=None):
        return sonnet.RewriteResult(True, "מודעה משוכתבת", ["#חלקית"], ["CNC"], 77, "סיבה", "claude-sonnet-5-5")

    monkeypatch.setattr(sonnet, "rewrite", fake_rewrite)
    monkeypatch.setattr(window, "start_busy", lambda text: None)
    monkeypatch.setattr(window, "end_busy", lambda: None)
    window.show_screen("collect")
    collect = window.screens["collect"]
    collect._paste_manually()
    collect.preview_text.setPlainText("📍 דרוש.ה  מזכיר.ה ✅")
    collect._rewrite()
    for _ in range(50):
        app.processEvents()
        if window.current == "ad":
            break
        import time
        time.sleep(0.05)
    assert window.current == "ad"
    ad = window.screens["ad"].ad
    assert ad.origin_ad == "דרוש.ה מזכיר.ה" and ad.source_name == "ידני" and ad.score == 77
    assert (window.state.paths.prompt_versions / window.state.community.prompt_version).is_dir()

    # same ad again -> duplicate warning; choose "open the existing ad"
    window.show_screen("collect")
    collect._paste_manually()
    collect.preview_text.setPlainText("דרוש.ה מזכיר.ה!!")
    monkeypatch.setattr(dialogs, "choose", lambda *a, **k: 0)
    collect._rewrite()
    assert window.current == "ad" and window.screens["ad"].ad.id == ad.id


def test_distribute_flow(window, monkeypatch):
    state = window.state
    ad_id = _add(state, "מודעה", [], [], 50)
    state.db.set_status(ad_id, STATUS_APPROVED)
    window.open_ad(ad_id)
    screen = window.screens["ad"]
    monkeypatch.setattr(dialogs, "ask_yes_no", lambda *a: True)
    screen._filled()
    assert state.db.get_ad(ad_id).status == STATUS_DISTRIBUTED
    assert screen.text.isReadOnly()


def test_rewrite_with_pasted_image(window, app, monkeypatch):
    from PySide6.QtGui import QColor, QImage
    calls = []

    def fake_rewrite(client, community, text, model, effort, images=None):
        calls.append((text, images))
        return sonnet.RewriteResult(True, "מודעה מתמונה", [], [], 60, "", "claude-sonnet-5-5")

    monkeypatch.setattr(sonnet, "rewrite", fake_rewrite)
    monkeypatch.setattr(window, "start_busy", lambda text: None)
    monkeypatch.setattr(window, "end_busy", lambda: None)
    window.show_screen("collect")
    collect = window.screens["collect"]
    collect._paste_manually()

    tiny = QImage(50, 50, QImage.Format_RGB32)
    collect._add_qimage(tiny)  # too small: refused with a message
    assert collect.preview_images.images == [] and window.shown_dialogs[-1][0] == "info"

    big = QImage(800, 600, QImage.Format_RGB32)
    big.fill(QColor("white"))
    collect._add_qimage(big)
    collect._add_qimage(big)
    assert len(collect.preview_images.images) == 2
    collect.preview_images._remove(1)
    assert len(collect.preview_images.images) == 1

    collect._rewrite()  # image only, no text
    for _ in range(50):
        app.processEvents()
        if window.current == "ad":
            break
        import time
        time.sleep(0.05)
    assert window.current == "ad"
    assert calls[0][0] == "" and len(calls[0][1]) == 1
    ad = window.screens["ad"].ad
    assert ad.origin_images == [f"{ad.id}_1.jpg"]
    assert (window.state.paths.images / ad.origin_images[0]).read_bytes()[:2] == b"\xff\xd8"
    screen = window.screens["ad"]
    screen.origin_toggle.setChecked(True)
    assert not screen.origin_images.isHidden()


def test_menu_whatsapp_group(window):
    menu = window.screens["menu"]
    assert menu.group_edit.text() == "thomas vinters"
    menu.group_edit.setText("  קבוצת משרות צפון  ")
    menu._save_group()
    assert window.state.community.info.whatsapp_group == "קבוצת משרות צפון"
    saved = json.loads(window.state.paths.config.read_text(encoding="utf-8"))
    assert saved["communities"]["autism"]["whatsapp_group"] == "קבוצת משרות צפון"
    assert saved["communities"]["autism"]["display_name"] == "אוטיזם"  # the rest of the file is kept

    menu.group_edit.setText("   ")
    menu._save_group()  # empty: refused with a message
    assert window.state.community.info.whatsapp_group == "קבוצת משרות צפון"


def test_distribute_without_group_points_to_menu(window):
    state = window.state
    state.set_whatsapp_group("")
    ad_id = _add(state, "מודעה", [], [], 50)
    state.db.set_status(ad_id, STATUS_APPROVED)
    window.open_ad(ad_id)
    window.screens["ad"]._distribute()
    assert window.shown_dialogs[-1][0] == "error" and "במסך התפריט" in window.shown_dialogs[-1][1]
