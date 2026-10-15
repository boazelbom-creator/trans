"""Everything the screens share: settings, database, active community, API client, browser."""

import logging

import anthropic

from . import community as community_mod
from .browser import BrowserService
from .community import Community, CommunityError, CommunityInfo
from .config import Config
from .db import Database
from .paths import Paths

log = logging.getLogger(__name__)


class AppState:
    def __init__(self, paths: Paths, config: Config, api_key: str, db: Database):
        self.paths = paths
        self.config = config
        self.db = db
        self.browser = BrowserService(paths.browser_profile)
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=180.0)
        self.communities: list[CommunityInfo] = []
        self.community: Community | None = None
        self.community_error = ""

    def refresh_communities(self) -> None:
        self.communities = community_mod.discover(self.paths.communities, self.config)

    def find_info(self, folder: str) -> CommunityInfo | None:
        return next((c for c in self.communities if c.folder == folder), None)

    def load_community(self, folder: str) -> None:
        """Load a community and make it active. On failure, no community is active and the error is kept."""
        self.community = None
        self.community_error = ""
        info = self.find_info(folder)
        try:
            if info is None:
                raise CommunityError(f"תיקיית הקהילה \"{folder}\" לא נמצאה.")
            self.community = community_mod.load(info)
        except CommunityError as e:
            self.community_error = str(e)
            log.warning("Community %s not loaded: %s", folder, e)
            return
        if self.config.active_community != folder:
            try:
                self.config.set_active_community(folder)
            except OSError:
                log.exception("Could not save the active community to config.json")
        log.info("Community loaded: %s (prompt version %s)", folder, self.community.prompt_version)

    def load_initial_community(self) -> None:
        self.refresh_communities()
        usable = [c for c in self.communities if c.usable]
        folder = self.config.active_community
        if not self.find_info(folder) and usable:
            folder = usable[0].folder
        if folder:
            self.load_community(folder)
        elif not self.communities:
            self.community_error = f"לא נמצאו קהילות בתיקייה:\n{self.paths.communities}"

    def reload(self) -> None:
        """Re-read the community folders and the active community's files (the "Reload files" button)."""
        folder = self.community.folder if self.community else self.config.active_community
        if folder:
            self.refresh_communities()
            self.load_community(folder)
        else:
            self.load_initial_community()

    def set_whatsapp_group(self, group: str) -> None:
        """Save the active community's distribution group (the menu field)."""
        folder = self.community.folder
        self.config.set_whatsapp_group(folder, group)
        self.community.info.whatsapp_group = group
        info = self.find_info(folder)
        if info is not None:
            info.whatsapp_group = group

    def shutdown(self) -> None:
        self.browser.shutdown()
        self.db.close()
