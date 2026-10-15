"""Running slow work (Sonnet call, browser) off the UI thread, and getting the result back on it."""

import logging
from concurrent.futures import Future, ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)


class _Bridge(QObject):
    call = Signal(object)


_bridge: _Bridge | None = None
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="worker")


def init() -> None:
    """Call once on the UI thread, after the QApplication is created."""
    global _bridge
    _bridge = _Bridge()
    _bridge.call.connect(lambda fn: fn())


def _on_ui(fn) -> None:
    _bridge.call.emit(fn)


def watch(future: Future, on_ok, on_error) -> None:
    """Call on_ok(result) or on_error(exception) on the UI thread when the future finishes."""

    def done(f: Future):
        exc = f.exception()
        if exc is not None:
            _on_ui(lambda: on_error(exc))
        else:
            result = f.result()
            _on_ui(lambda: on_ok(result))

    future.add_done_callback(done)


def run(fn, *args, on_ok, on_error) -> None:
    """Run fn(*args) on a worker thread."""
    watch(_pool.submit(fn, *args), on_ok, on_error)
