"""Locations of the app's files (PRD §4).

When running as the installed EXE, everything lives next to JobAds.exe.
When running from source, everything lives in the project folder.
"""

import sys
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


class Paths:
    def __init__(self, root: Path | None = None):
        self.root = root or app_dir()
        self.config = self.root / "config.json"
        self.api_key = self.root / "api_key.json"
        self.communities = self.root / "communities"
        self.data = self.root / "data"
        self.db = self.data / "ads.db"
        self.prompt_versions = self.data / "prompt_versions"
        self.images = self.data / "images"
        self.browser_profile = self.root / "browser_profile"
        self.logs = self.root / "logs"
        self.log_file = self.logs / "app.log"

    def ensure_dirs(self) -> None:
        for d in (self.data, self.prompt_versions, self.images, self.browser_profile, self.logs):
            d.mkdir(parents=True, exist_ok=True)
