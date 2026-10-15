"""Browser tests against the real Microsoft Edge, invisible (headless), with fake pages.

Runs only on Windows with Edge installed. WhatsApp Web is replaced by a fake page that has the same
structure, so no real account is used. The fake page "sends" a message on Enter, to check that the
app never sends.
"""

import sys
from pathlib import Path

import pytest

from jobads.browser import WHATSAPP_URL, BrowserError, BrowserService

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
pytestmark = pytest.mark.skipif(sys.platform != "win32" or not EDGE.exists(), reason="needs Windows with Edge")

FAKE_WHATSAPP = """<!doctype html><html><body>
<div id="side">
  <div contenteditable="true" data-tab="3" id="search" style="min-height:20px;border:1px solid"></div>
  <div id="pane-side">
    <span title="קבוצה אחרת">קבוצה אחרת</span>
    <span title="מנהלים בלבד" onclick="openAdminsOnly()">מנהלים בלבד</span>
    <span title="⁦+972 52-242-6638⁩">⁦+972 52-242-6638⁩</span>
  </div>
</div>
<div id="main"></div>
<script>
  window.sent = false;
  const pane = document.getElementById('pane-side');
  document.getElementById('search').addEventListener('input', e => {
    if (e.target.innerText.toLowerCase().includes('thomas')) {
      const s = document.createElement('span'); s.title = 'thomas vinters'; s.innerText = 'thomas vinters';
      s.onclick = openChat; pane.appendChild(s);
    }
  });
  function openAdminsOnly() {
    document.getElementById('main').innerHTML = '<footer><div>Only admins can send messages</div></footer>';
  }
  function openChat() {
    document.getElementById('main').innerHTML =
      '<footer><div contenteditable="true" data-tab="10" id="box" style="min-height:40px;border:1px solid"></div></footer>';
    document.getElementById('box').addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { window.sent = true; e.preventDefault(); }
    });
  }
</script></body></html>"""

FB_POST = """<!doctype html><html><body>
<div role="feed">
  <div role="article" id="post">
    <img src="https://img.example/avatar.png" width="40" height="40">
    <div id="text">דרושה מזכירה למשרד בחיפה. פרטים בתמונה.</div>
    <img src="https://img.example/details.png" width="500" height="300">
    <div role="article"><span>תגובה</span><img src="https://img.example/comment.png" width="300" height="300"></div>
  </div>
  <div role="article"><img src="https://img.example/other_post.png" width="500" height="300"></div>
  <div role="article" id="post2">
    <div id="text2">דרוש טכנאי. פרטים בתמונות.</div>
    <svg width="400" height="300"><image href="https://img.example/svg_photo.png" width="400" height="300"></image></svg>
    <div style="width:400px;height:300px;background-image:url('/bg_photo.png')"></div>
  </div>
</div></body></html>"""

# Facebook's other page layout: posts are not marked role="article", only children of the feed.
FB_UNMARKED = """<!doctype html><html><body>
<div role="feed">
  <div><div><div id="a_text">דרושה מזכירה. פרטים בתמונה <img src="https://img.example/emoji.png" width="16" height="16"></div></div>
       <div><div><img src="https://img.example/a_photo.png" width="500" height="400"></div></div></div>
  <div><div id="b_text">דרוש מחסנאי, משרה מלאה, בלי תמונה.</div></div>
  <div><div><div><img src="https://img.example/c_photo.png" width="500" height="400"></div></div>
       <div><div id="c_text">התמונה למעלה: דרוש טכנאי מעבדה.</div></div></div>
</div></body></html>"""

POST_PAGE = """<!doctype html><html><body>
<div>Header text</div>
<div id="post">ל-More Admin דרוש.ה Business Admin.<br>90-100 שעות בחודש.<br>📍 חיפה</div>
</body></html>"""


def _png(w, h, color):
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QColor, QImage
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor(color))
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


_PNGS = {
    "avatar.png": _png(40, 40, "gray"),
    "details.png": _png(1000, 600, "red"),
    "comment.png": _png(600, 600, "blue"),
    "other_post.png": _png(1000, 600, "green"),
    "svg_photo.png": _png(800, 600, "yellow"),
    "bg_photo.png": _png(800, 600, "purple"),
    "emoji.png": _png(16, 16, "orange"),
    "a_photo.png": _png(900, 700, "teal"),
    "c_photo.png": _png(900, 700, "navy"),
}


@pytest.fixture
def browser(tmp_path):
    service = BrowserService(tmp_path / "profile")
    service.headless = True

    def setup():
        context = service._ensure_context()
        context.route(WHATSAPP_URL + "**", lambda route: route.fulfill(body=FAKE_WHATSAPP, content_type="text/html; charset=utf-8"))
        context.route("https://jobs.example/**", lambda route: route.fulfill(body=POST_PAGE, content_type="text/html; charset=utf-8"))
        context.route("https://fb.example/bg_photo.png", lambda route: route.fulfill(body=_PNGS["bg_photo.png"], content_type="image/png"))
        context.route("https://fb.example/unmarked", lambda route: route.fulfill(body=FB_UNMARKED, content_type="text/html; charset=utf-8"))
        context.route("https://fb.example/group", lambda route: route.fulfill(body=FB_POST, content_type="text/html; charset=utf-8"))
        context.route("https://img.example/**", lambda route: route.fulfill(
            body=_PNGS[route.request.url.rsplit("/", 1)[1]], content_type="image/png", headers={"Access-Control-Allow-Origin": "*"}))

    service.submit(setup).result(timeout=60)
    yield service
    service.shutdown()


def _run(service, fn, *args):
    return service.submit(fn, *args).result(timeout=120)


def test_capture_selected_text(browser):
    _run(browser, browser.open_url, "https://jobs.example/post")

    with pytest.raises(BrowserError):
        _run(browser, browser.capture)  # nothing selected yet

    def select_post():
        page = next(p for p in browser._context.pages if p.url.startswith("https://jobs.example"))
        page.evaluate("() => getSelection().selectAllChildren(document.getElementById('post'))")

    _run(browser, select_post)
    text, url, images = _run(browser, browser.capture)
    assert "ל-More Admin דרוש.ה Business Admin." in text
    assert "90-100 שעות בחודש." in text
    assert "Header text" not in text
    assert url == "https://jobs.example/post"
    assert images == []

    with pytest.raises(BrowserError):
        _run(browser, browser.capture)  # the selection was cleared: the same ad is not captured twice


def test_whatsapp_open_chat(browser):
    assert _run(browser, browser.open_whatsapp_chat, "קבוצה אחרת") is True
    assert _run(browser, browser.open_whatsapp_chat, "לא קיימת") is False


def test_whatsapp_fill_never_sends(browser):
    text = "חיפה\n#חלקית #אדמיניסטרציה\n\nל-More Admin דרוש.ה Business Admin.\nניתן לשלוח קו\"ח למייל: office@x.com"
    _run(browser, browser.fill_whatsapp, "thomas vinters", text)

    def read():
        page = next(p for p in browser._context.pages if p.url.startswith(WHATSAPP_URL))
        return page.evaluate("() => ({text: document.getElementById('box').innerText, sent: window.sent})")

    result = _run(browser, read)
    assert result["sent"] is False
    filled = result["text"].replace("\r", "")
    for line in ("חיפה", "#חלקית #אדמיניסטרציה", "ל-More Admin דרוש.ה Business Admin.", "office@x.com"):
        assert line in filled
    assert filled.index("חיפה") < filled.index("#חלקית") < filled.index("office@x.com")


def test_whatsapp_group_not_found(browser):
    with pytest.raises(BrowserError) as e:
        _run(browser, browser.fill_whatsapp, "nobody", "x")
    assert "לא נמצאה" in e.value.user_message


def test_reopens_after_user_closed_the_window(browser):
    _run(browser, browser.open_url, "https://jobs.example/post")

    def close_like_user():
        stale = browser._context
        stale.close()
        browser._context = stale  # the app has not noticed yet, as when the user closes the window

    _run(browser, close_like_user)
    _run(browser, browser.open_url, "data:text/html,<p>reopened</p>")
    pages = _run(browser, lambda: [p.url for p in browser._context.pages])
    assert any(u.startswith("data:text/html") for u in pages)


def test_capture_facebook_post_images(browser):
    _run(browser, browser.open_url, "https://fb.example/group")

    def select_text_only():
        page = next(p for p in browser._context.pages if p.url.startswith("https://fb.example"))
        page.wait_for_function("() => [...document.images].every(i => i.complete)")
        page.evaluate("() => getSelection().selectAllChildren(document.getElementById('text'))")

    _run(browser, select_text_only)
    text, url, images = _run(browser, browser.capture)
    assert "פרטים בתמונה" in text
    # only the post's own large image: not the avatar, not the comment's image, not another post's image
    assert images == [_PNGS["details.png"]]


def test_whatsapp_tolerant_chat_names(browser):
    assert _run(browser, browser.open_whatsapp_chat, "052-2426638") is True  # phone, other format
    assert _run(browser, browser.open_whatsapp_chat, "+972522426638") is True
    assert _run(browser, browser.open_whatsapp_chat, "  קבוצה   אחרת ") is True  # extra spaces
    assert _run(browser, browser.open_whatsapp_chat, "052-9999999") is False  # other number
    _run(browser, browser.fill_whatsapp, "Thomas Vinters", "שלום")  # letter case, found through search


def test_capture_svg_and_background_images(browser):
    _run(browser, browser.open_url, "https://fb.example/group")

    def select():
        page = next(p for p in browser._context.pages if p.url.startswith("https://fb.example"))
        page.wait_for_timeout(500)
        page.evaluate("() => getSelection().selectAllChildren(document.getElementById('text2'))")

    _run(browser, select)
    text, url, images = _run(browser, browser.capture)
    assert "טכנאי" in text
    assert sorted(images) == sorted([_PNGS["svg_photo.png"], _PNGS["bg_photo.png"]])


def test_whatsapp_admins_only_group(browser):
    with pytest.raises(BrowserError) as e:
        _run(browser, browser.fill_whatsapp, "מנהלים בלבד", "x")
    assert "רק מנהלי הקבוצה" in e.value.user_message


def test_capture_unmarked_facebook_layout(browser):
    _run(browser, browser.open_url, "https://fb.example/unmarked")

    def select(element_id):
        def run():
            page = next(p for p in browser._context.pages if p.url.startswith("https://fb.example"))
            page.wait_for_function("() => [...document.images].every(i => i.complete)")
            page.evaluate(f"() => getSelection().selectAllChildren(document.getElementById('{element_id}'))")
        return run

    _run(browser, select("a_text"))
    text, url, images = _run(browser, browser.capture)
    assert "מזכירה" in text
    assert images == [_PNGS["a_photo.png"]]  # the post's photo; not the emoji, not another post's photo

    _run(browser, select("b_text"))
    text, url, images = _run(browser, browser.capture)
    assert "מחסנאי" in text
    assert images == []  # a post without an image does not take its neighbour's image

    _run(browser, select("c_text"))  # image before the text
    text, url, images = _run(browser, browser.capture)
    assert "טכנאי מעבדה" in text
    assert images == [_PNGS["c_photo.png"]]


def test_capture_takes_latest_selection_across_tabs(browser):
    """Two tabs, each with a selection: the one selected last is captured, and the old one never comes back."""
    def open_two_tabs():
        context = browser._context
        first = context.pages[0] if context.pages[0].url == "about:blank" else context.new_page()
        first.goto("https://jobs.example/first")
        second = context.new_page()
        second.goto("https://fb.example/unmarked")
        second.wait_for_function("() => [...document.images].every(i => i.complete)")
        first.evaluate("() => getSelection().selectAllChildren(document.getElementById('post'))")
        second.wait_for_timeout(50)
        second.evaluate("() => getSelection().selectAllChildren(document.getElementById('b_text'))")

    _run(browser, open_two_tabs)
    text, url, images = _run(browser, browser.capture)
    assert "מחסנאי" in text and url == "https://fb.example/unmarked"
    with pytest.raises(BrowserError):
        _run(browser, browser.capture)  # both selections were cleared


def test_sources_open_in_one_tab(browser):
    _run(browser, browser.open_url, "https://jobs.example/one")
    _run(browser, browser.open_url, "https://fb.example/unmarked")
    _run(browser, browser.open_url, "https://jobs.example/two")
    urls = _run(browser, lambda: [p.url for p in browser._context.pages])
    assert urls.count("https://jobs.example/two") == 1
    assert "https://jobs.example/one" not in urls and "https://fb.example/unmarked" not in urls

    _run(browser, browser.open_whatsapp_chat, "קבוצה אחרת")  # WhatsApp keeps its own tab
    _run(browser, browser.open_url, "https://jobs.example/three")
    urls = _run(browser, lambda: [p.url for p in browser._context.pages])
    assert any(u.startswith("https://web.whatsapp.com") for u in urls)
    assert "https://jobs.example/three" in urls and len(urls) == 2
