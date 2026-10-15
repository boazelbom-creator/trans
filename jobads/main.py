"""Application startup."""

import logging
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from . import APP_NAME, APP_VERSION
from .app_state import AppState
from .config import ConfigError, load_api_key, load_config
from .db import Database, DatabaseError
from .paths import Paths
from .ui import dialogs, qt_async
from .ui.main_window import MainWindow

log = logging.getLogger(__name__)


def _setup_logging(paths: Paths) -> None:
    handler = RotatingFileHandler(paths.log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    for noisy in ("httpx", "httpx2", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _install_excepthook() -> None:
    def hook(exc_type, exc, tb):
        log.critical("Unhandled error", exc_info=(exc_type, exc, tb))
        try:
            dialogs.error(None, "שגיאה", dialogs.GENERIC_ERROR)
        except Exception:
            pass

    sys.excepthook = hook


def _check_browser(paths: Paths) -> int:
    """`JobAds.exe --check-browser`: open an invisible Edge and close it. Exit code 0 = OK. For diagnosing a PC."""
    from .browser import BrowserService

    service = BrowserService(paths.data / "browser_check_profile")
    service.headless = True
    try:
        service.submit(service.open_url, "about:blank").result(timeout=120)
        log.info("Browser check: OK")
        return 0
    except Exception:
        log.exception("Browser check failed")
        return 1
    finally:
        service.shutdown()


def main() -> int:
    paths = Paths()
    paths.ensure_dirs()
    _setup_logging(paths)
    log.info("Starting %s %s from %s", APP_NAME, APP_VERSION, paths.root)
    if "--check-browser" in sys.argv:
        return _check_browser(paths)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setLayoutDirection(Qt.RightToLeft)
    app.setFont(QFont("Segoe UI", 10))
    qt_async.init()
    _install_excepthook()

    try:
        config = load_config(paths.config)
        api_key = load_api_key(paths.api_key)
        db = Database(paths.db)
    except (ConfigError, DatabaseError) as e:
        log.error("Startup failed: %s", e)
        dialogs.error(None, "לא ניתן להפעיל את התוכנה", str(e))
        return 1

    state = AppState(paths, config, api_key, db)
    state.load_initial_community()

    window = MainWindow(state)
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
