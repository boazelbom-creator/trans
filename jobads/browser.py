"""Browser automation with Playwright and Microsoft Edge (PRD §10).

All Playwright calls run on one dedicated thread (Playwright's sync API must stay on the thread
that started it). The UI calls `submit()` and gets a Future back.

The app never scrolls, clicks posts or presses Send. It only opens pages, reads the selected text,
opens a WhatsApp chat and fills in the message box.
"""

import base64
import logging
import os
import shutil
import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

log = logging.getLogger(__name__)

WHATSAPP_URL = "https://web.whatsapp.com/"
MIN_IMAGE_SIDE = 200  # same as images.MIN_SIDE; browser.py does not import Qt
MAX_IMAGES = 4
FACEBOOK_URL = "https://www.facebook.com/"

# WhatsApp Web changes its page structure from time to time. All selectors are kept here so
# they are easy to update. Each list is tried in order.
WA_CHAT_LIST = ["#pane-side", "div[aria-label='Chat list']", "div[aria-label='רשימת צ׳אטים']", "div[role='grid']"]
WA_QR = ["canvas[aria-label*='QR']", "canvas[aria-label*='Scan']", "div[data-ref] canvas"]
WA_SEARCH = [
    "div[contenteditable='true'][data-tab='3']",
    "#side div[contenteditable='true']",
    "#side input[type='text']",
    "input[role='textbox']",
]
WA_MESSAGE_BOX = [
    "footer div[contenteditable='true'][data-tab='10']",
    "footer div[contenteditable='true']",
    "#main div[contenteditable='true'][role='textbox']",
    "#main footer [contenteditable='true']",
    "#main [contenteditable='true']",
    "div[contenteditable='true'][data-tab='10']",
]
# Shown instead of the message box in groups where only admins can send messages.
WA_ADMINS_ONLY = ("only admins", "רק מנהלים", "רק מנהלי", "admins can send")

_CHAT_PANE_JS = """() => {
    const main = document.querySelector('#main');
    const editable = [...document.querySelectorAll('[contenteditable="true"]')].map(el => ({
        inMain: !!el.closest('#main'), inFooter: !!el.closest('footer'), role: el.getAttribute('role'),
        label: el.getAttribute('aria-label'), tab: el.getAttribute('data-tab'), shown: el.offsetParent !== null,
    }));
    const footer = main ? main.querySelector('footer') : null;
    const header = main ? main.querySelector('header [title], header span[dir="auto"]') : null;
    return {main: !!main, chat: header ? (header.getAttribute('title') || header.innerText) : null,
            footer: footer ? footer.innerText.slice(0, 200) : null, editable: editable};
}"""

# Reads the selected text, and finds the ad's images:
# - Facebook: the images of the post (role="article") that contains the selection, not of its comments.
# - Elsewhere: the images inside the selection.
# Small images (profile pictures, icons, emojis) are skipped.
_SELECTION_JS = """() => {
    const sel = window.getSelection ? window.getSelection() : null;
    const text = sel ? sel.toString() : '';
    const result = {text: text, visible: document.visibilityState === 'visible', focused: document.hasFocus(),
                    selectedAt: window.__jobadsSelectedAt || 0, images: [], debug: {post: false, skipped: []}};
    if (!sel || sel.rangeCount === 0 || !text.trim()) return result;
    const range = sel.getRangeAt(0);
    let node = range.commonAncestorContainer;
    if (node.nodeType !== 1) node = node.parentElement;
    if (!node) return result;

    // The images that can show content: <img>, <image> inside SVG, and CSS background images.
    const IMAGE_SELECTOR = 'img, svg image, [style*="background-image"]';
    const big = el => { const b = el.getBoundingClientRect(); return Math.min(b.width, b.height) >= 100; };
    // A comment (or a quoted post) is a nested [role=article] that does not contain the selection.
    const inOtherArticle = (el, container) => {
        const art = el.closest('[role="article"]');
        return art && art !== container && container.contains(art) && !art.contains(node);
    };
    // The post's boundary: Facebook marks posts in different ways, depending on the page layout.
    const isBoundary = el => el.matches('[role="article"], [role="dialog"], [role="main"], [aria-posinset], body')
        || (el.parentElement && el.parentElement.matches('[role="feed"]'));
    const tooTall = el => el.getBoundingClientRect().height > window.innerHeight * 2.5;

    // On Facebook and WhatsApp (pages with posts or messages), walk up from the selected text to the
    // nearest area that has a large image, without crossing the post's boundary. Elsewhere, take only
    // images inside the selection.
    const host = location.hostname;
    const postPage = /(^|\\.)(facebook|whatsapp)\\.com$/.test(host) || !!document.querySelector('[role="feed"], [role="article"], [aria-posinset]');
    let post = null;
    if (postPage) {
        for (let el = node; el; el = el.parentElement) {
            if (tooTall(el)) break;
            const found = [...el.querySelectorAll(IMAGE_SELECTOR)].some(i => big(i) && !inOtherArticle(i, el));
            if (found) { post = el; break; }
            if (isBoundary(el)) break;
        }
    }
    result.debug.post = !!post;
    const scope = post || document;
    const own = el => post ? !inOtherArticle(el, post) : range.intersectsNode(el);
    const candidates = [];
    for (const el of scope.querySelectorAll('img')) {
        candidates.push({el, src: el.currentSrc || el.src, nw: el.naturalWidth, nh: el.naturalHeight, kind: 'img'});
    }
    for (const el of scope.querySelectorAll('svg image')) {
        const href = el.getAttribute('href') || el.getAttribute('xlink:href') || (el.href && el.href.baseVal) || '';
        if (href) candidates.push({el, src: new URL(href, location.href).href, nw: 0, nh: 0, kind: 'svg'});
    }
    for (const el of scope.querySelectorAll('[style*="background-image"]')) {
        const m = (el.style.backgroundImage || '').match(/url\\(["']?(.*?)["']?\\)/);
        if (m) candidates.push({el, src: new URL(m[1], location.href).href, nw: 0, nh: 0, kind: 'bg'});
    }
    const seen = new Set();
    for (const c of candidates) {
        const box = c.el.getBoundingClientRect();
        const size = [c.kind, Math.round(box.width), Math.round(box.height), c.nw, c.nh];
        if (!own(c.el)) { if (post) result.debug.skipped.push(size.concat('comment')); continue; }
        if (!c.src || seen.has(c.src)) continue;
        if (Math.min(box.width, box.height) < 100) { result.debug.skipped.push(size.concat('small on screen')); continue; }
        // Natural size is known only for <img> that finished loading; others are checked after download.
        if (c.nw && Math.max(c.nw, c.nh) < MIN_SIDE) { result.debug.skipped.push(size.concat('small file')); continue; }
        seen.add(c.src);
        result.images.push(c.src);
        if (result.images.length >= MAX_IMAGES) break;
    }
    return result;
}"""

# Finding a chat by its title in the chat list. Matching ignores hidden direction marks, letter case
# and extra spaces. For a phone number, only the digits are compared (+972 52-242-6638 = 052-2426638).
_CHAT_MATCH_JS = """
    const norm = s => (s || '').replace(/[\\u200e\\u200f\\u202a-\\u202e\\u2066-\\u2069]/g, '').replace(/\\s+/g, ' ').trim().toLowerCase();
    const digits = s => { let d = (s || '').replace(/\\D/g, ''); if (d.startsWith('972')) d = d.slice(3); if (d.startsWith('0')) d = d.slice(1); return d; };
    const side = document.querySelector('#side') || document.querySelector('#pane-side') || document;
    const titled = [...side.querySelectorAll('[title]')].filter(el => !el.closest('#main') && !el.closest('[contenteditable]'));
"""

_FIND_CHAT_JS = """(name) => {""" + _CHAT_MATCH_JS + """
    document.querySelectorAll('[data-jobads-chat]').forEach(el => el.removeAttribute('data-jobads-chat'));
    const target = norm(name);
    const nameDigits = digits(name);
    const isPhone = /^[\\d\\s+()\\-]+$/.test(norm(name)) && nameDigits.length >= 7;
    for (const el of titled) {
        const title = el.getAttribute('title');
        if (norm(title) === target || (isPhone && digits(title) === nameDigits)) {
            el.setAttribute('data-jobads-chat', '1');
            return true;
        }
    }
    return false;
}"""

_CHAT_TITLES_JS = """() => {""" + _CHAT_MATCH_JS + """
    return titled.map(el => el.getAttribute('title'));
}"""

# Runs in every page the app's browser opens: remembers when the user last selected text, so that with
# several tabs or windows open, Capture takes the most recent selection.
_TRACK_SELECTION_JS = """
document.addEventListener('selectionchange', () => {
    const sel = window.getSelection();
    if (sel && sel.toString().trim()) window.__jobadsSelectedAt = Date.now();
});
"""

_FETCH_IN_PAGE_JS = """async (src) => {
    const blob = await (await fetch(src)).blob();
    return await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
}"""


class BrowserError(Exception):
    """A browser operation failed. `user_message` is shown to the user (Hebrew)."""

    def __init__(self, user_message: str, detail: str = ""):
        super().__init__(detail or user_message)
        self.user_message = user_message


def find_edge() -> str | None:
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            path = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if path.is_file():
                return str(path)
    return shutil.which("msedge")


def open_login_window(profile_dir: Path) -> subprocess.Popen:
    """Open a normal Edge window (no automation) with the app's profile, on Facebook and WhatsApp Web.

    Facebook's login can hang in an automated browser. Logging in here saves the login in the app's
    profile, so the automated window opens already logged in. Close the automated window first:
    two browsers cannot use the same profile.
    """
    edge = find_edge()
    if edge is None:
        raise BrowserError("הדפדפן Microsoft Edge לא נמצא במחשב. יש להתקין אותו כדי לאסוף ולהפיץ מודעות.", "msedge.exe not found")
    profile_dir.mkdir(parents=True, exist_ok=True)
    _disable_background_mode(profile_dir)
    args = [
        edge, f"--user-data-dir={profile_dir}", "--no-first-run", "--no-default-browser-check",
        "--new-window", FACEBOOK_URL, WHATSAPP_URL,
    ]
    log.info("Opening the login window")
    return subprocess.Popen(args)


def _disable_background_mode(profile_dir: Path) -> None:
    """Turn off "keep running in the background" in the app's profile only, so Edge exits when its window closes."""
    import json

    path = profile_dir / "Local State"
    try:
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if state.get("background_mode", {}).get("enabled") is False:
            return
        state.setdefault("background_mode", {})["enabled"] = False
        path.write_text(json.dumps(state), encoding="utf-8")
    except (OSError, ValueError):
        log.exception("Could not turn off Edge background mode")


def close_login_window(proc: subprocess.Popen, grace_seconds: float = 8.0) -> None:
    """Wait a little for Edge to exit by itself (it saves the logins on exit); otherwise close it."""
    try:
        proc.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    log.info("Login window still running after it was closed; closing it")
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        log.warning("Login window did not exit")


class BrowserService:
    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir
        self.headless = False  # True only in tests
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="browser")
        self._playwright = None
        self._context = None
        self._source_page = None  # the one tab that sources open in

    # ---- public API (called from the UI thread) ----

    def submit(self, fn, *args) -> Future:
        """Run one of the operations below on the browser thread."""
        return self._executor.submit(self._guarded, fn, *args)

    def shutdown(self) -> None:
        try:
            self._executor.submit(self._close).result(timeout=10)
        except Exception:
            log.exception("Error closing the browser")
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ---- operations (run on the browser thread) ----

    def _guarded(self, fn, *args):
        """If the user closed the browser window during the operation, say so instead of a general error."""
        from playwright.sync_api import Error as PlaywrightError

        try:
            return fn(*args)
        except PlaywrightError as e:
            if type(e).__name__ != "TargetClosedError" and "has been closed" not in str(e):
                raise
            self._discard_context()
            raise BrowserError("חלון הדפדפן נסגר. נסו שוב, והדפדפן ייפתח מחדש.", str(e)) from e

    def close_browser(self) -> None:
        """Close the automated window (before opening the login window)."""
        self._close()

    def open_url(self, url: str) -> None:
        """Open a source. Every source opens in the same tab, so old tabs (and old selections) don't pile up."""
        page = self._source_tab()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.bring_to_front()

    def open_whatsapp_chat(self, chat_name: str) -> bool:
        """Open WhatsApp Web and try to open the chat with this name. Returns False if it was not found."""
        page = self._whatsapp_page()
        self._wait_whatsapp_ready(page)
        return self._open_chat(page, chat_name)

    def capture(self) -> tuple[str, str, list[bytes]]:
        """The text selected in the visible tab, the tab's URL, and the ad's images (raw file bytes)."""
        context = self._ensure_context()
        js = _SELECTION_JS.replace("MIN_SIDE", str(MIN_IMAGE_SIDE)).replace("MAX_IMAGES", str(MAX_IMAGES))
        candidates = []
        for page in context.pages:
            for frame in page.frames:
                try:
                    info = frame.evaluate(js)
                except Exception:
                    continue
                if info["text"].strip():
                    # The most recent selection first; then the visible tab, then the focused one.
                    rank = (info["selectedAt"], 2 if info["visible"] else 0, 1 if info["focused"] else 0)
                    candidates.append((rank, info, frame, page.url))
        if not candidates:
            raise BrowserError(
                "לא נבחר טקסט. סמנו בעכבר את טקסט המודעה בחלון הדפדפן של התוכנה "
                "(לא בדפדפן Edge הרגיל שלכם), ולחצו שוב על \"לכידה\"."
            )
        candidates.sort(key=lambda c: c[0], reverse=True)
        _, info, frame, url = candidates[0]
        images = [data for src in info["images"] if (data := self._fetch_image(frame, src))]
        # Clear the selections, so the next capture reads only a new selection and never this ad again.
        for _, _, f, _ in candidates:
            try:
                f.evaluate("() => window.getSelection().removeAllRanges()")
            except Exception:
                pass
        # For diagnosis: which images were on the post and why they were skipped (sizes only, no addresses).
        log.info(
            "Capture: %d chars, %d images found, %d downloaded, in post block: %s, selections in %d tabs/frames, skipped: %s",
            len(info["text"]), len(info["images"]), len(images), info["debug"]["post"], len(candidates),
            info["debug"]["skipped"][:12],
        )
        return info["text"], url, images

    @staticmethod
    def _fetch_image(frame, src: str) -> bytes | None:
        """Download an image with the browser's own session (so images that need a login work too)."""
        if not src.startswith(("blob:", "data:")):
            try:
                response = frame.page.context.request.get(src, timeout=20000)
                if response.ok:
                    return response.body()
                log.info("Image download returned %s, trying from the page: %s", response.status, src[:120])
            except Exception as e:
                log.info("Image download failed (%s), trying from the page: %s", str(e).splitlines()[0], src[:120])
        try:
            # From inside the page. Needed for WhatsApp, whose images have blob: addresses that exist only in the page.
            return base64.b64decode(frame.evaluate(_FETCH_IN_PAGE_JS, src))
        except Exception:
            log.exception("Image download failed: %s", src[:120])
        return None

    def fill_whatsapp(self, group_name: str, text: str) -> None:
        """Open the distribution group and put the text in the message box. Never presses Send."""
        page = self._whatsapp_page()
        self._wait_whatsapp_ready(page)
        if not self._open_chat(page, group_name):
            raise BrowserError(
                f"הקבוצה \"{group_name}\" לא נמצאה בווטסאפ.\n"
                "בדקו את השדה \"קבוצת ווטסאפ להפצה\" במסך התפריט: הוא צריך להיות שם הקבוצה בדיוק כפי שהוא "
                "מופיע ברשימת הצ'אטים בווטסאפ, או מספר טלפון.",
                "group not found",
            )
        box = self._first_visible(page, WA_MESSAGE_BOX, timeout=15000)
        if box is None:
            pane = page.evaluate(_CHAT_PANE_JS)
            # For diagnosis: the structure of the chat pane (no message contents).
            log.warning("WhatsApp message box not found. Chat pane: %s", pane)
            footer = (pane.get("footer") or "").lower()
            if any(s in footer for s in WA_ADMINS_ONLY):
                raise BrowserError(
                    f"בקבוצה \"{group_name}\" רק מנהלי הקבוצה יכולים לשלוח הודעות.\n"
                    "בחרו קבוצה אחרת להפצה, או בקשו ממנהל הקבוצה הרשאה.",
                    "admins only",
                )
            raise BrowserError("לא נמצאה תיבת ההודעה בווטסאפ. הפרטים נשמרו ביומן.", "message box not found")
        box.click()
        self._paste(page, box, text)
        if not box.inner_text().strip():
            self._type_lines(page, text)
        if not box.inner_text().strip():
            raise BrowserError("לא ניתן היה למלא את ההודעה בווטסאפ.", "message box still empty")
        page.bring_to_front()

    # ---- internals ----

    def _ensure_context(self):
        if self._context is not None:
            try:
                # A real round trip to the browser: raises if the user closed the window.
                self._context.cookies("https://example.invalid")
                return self._context
            except Exception:
                self._discard_context()
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        if self._playwright is None:
            self._playwright = sync_playwright().start()
        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                str(self.profile_dir),
                channel="msedge",
                headless=self.headless,
                no_viewport=True,
                args=["--start-maximized"],
            )
        except PlaywrightError as e:
            msg = str(e)
            if "msedge" in msg and ("not found" in msg.lower() or "executable" in msg.lower()):
                raise BrowserError("הדפדפן Microsoft Edge לא נמצא במחשב. יש להתקין אותו כדי לאסוף ולהפיץ מודעות.", msg) from e
            if any(s in msg.lower() for s in ("already in use", "processsingleton", "has been closed")):
                # Another Edge window is using the app's profile, usually the login window.
                raise BrowserError("חלון דפדפן אחר של התוכנה פתוח (למשל חלון ההתחברות). סגרו אותו ונסו שוב.", msg) from e
            raise BrowserError("לא ניתן לפתוח את הדפדפן. הפרטים נשמרו ביומן.", msg) from e
        self._context.add_init_script(_TRACK_SELECTION_JS)
        self._context.on("close", lambda _: self._on_closed())
        return self._context

    def _on_closed(self):
        self._context = None

    def _discard_context(self):
        """Forget a browser that was closed, so the next operation opens a new one."""
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
        self._context = None

    def _close(self):
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def _source_tab(self):
        context = self._ensure_context()
        page = self._source_page
        if page is None or page.is_closed() or page.context is not context:
            page = self._new_page()
            self._source_page = page
        return page

    def _new_page(self):
        context = self._ensure_context()
        for page in context.pages:
            if page.url in ("about:blank", "", "edge://newtab/", "chrome://newtab/"):
                return page
        return context.new_page()

    def _whatsapp_page(self):
        context = self._ensure_context()
        for page in context.pages:
            if page.url.startswith(WHATSAPP_URL):
                page.bring_to_front()
                return page
        page = self._new_page()
        page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=60000)
        page.bring_to_front()
        return page

    @staticmethod
    def _first_visible(page, selectors: list[str], timeout: int = 0):
        """The first selector that matches a visible element, waiting up to `timeout` ms."""
        waited = 0
        step = 500
        while True:
            for sel in selectors:
                loc = page.locator(sel).first
                try:
                    if loc.is_visible():
                        return loc
                except Exception:
                    continue
            if waited >= timeout:
                return None
            page.wait_for_timeout(step)
            waited += step

    def _wait_whatsapp_ready(self, page) -> None:
        if self._first_visible(page, WA_CHAT_LIST, timeout=45000) is not None:
            return
        if self._first_visible(page, WA_QR) is not None:
            raise BrowserError("ווטסאפ אינו מחובר. סרקו את קוד ה-QR בחלון הדפדפן עם הטלפון, ואז נסו שוב.", "QR shown")
        raise BrowserError("ווטסאפ לא נטען. בדקו את חלון הדפדפן ונסו שוב.", "chat list not found")

    def _open_chat(self, page, name: str) -> bool:
        if not name:
            return False
        if self._click_chat(page, name):
            return True
        search = self._first_visible(page, WA_SEARCH, timeout=5000)
        if search is None:
            log.warning("WhatsApp search box not found")
            return False
        search.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        page.keyboard.insert_text(name)
        for _ in range(16):  # search results appear within a few seconds
            page.wait_for_timeout(500)
            if self._click_chat(page, name):
                return True
        titles = page.evaluate(_CHAT_TITLES_JS)
        log.warning("WhatsApp chat %r not found. Chats shown: %s", name, titles[:15])
        page.keyboard.press("Escape")
        return False

    @staticmethod
    def _click_chat(page, name: str) -> bool:
        """Click the chat in the chat list (or search results) whose title matches the name."""
        if not page.evaluate(_FIND_CHAT_JS, name):
            return False
        page.locator("[data-jobads-chat='1']").first.click()
        return True

    @staticmethod
    def _paste(page, box, text: str) -> None:
        """Paste through the clipboard: multi-line text is pasted without sending the message."""
        try:
            page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=WHATSAPP_URL.rstrip("/"))
            page.evaluate("t => navigator.clipboard.writeText(t)", text)
            box.click()
            page.keyboard.press("Control+V")
            page.wait_for_timeout(500)
        except Exception:
            log.exception("Clipboard paste into WhatsApp failed")

    @staticmethod
    def _type_lines(page, text: str) -> None:
        """Fallback: type line by line. Shift+Enter makes a new line; Enter alone would send."""
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if line:
                page.keyboard.insert_text(line)
            if i < len(lines) - 1:
                page.keyboard.press("Shift+Enter")
