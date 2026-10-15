"""Community folders: discovery, loading, prompt version (PRD §6, §13)."""

import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .excel_loader import AidsData, ExcelError, load_aids

SYSTEM_PROMPT_FILE = "system_prompt.txt"
AIDS_FILE = "aids.xlsx"
EXAMPLES_FILE = "examples.txt"
REQUIRED_FILES = (SYSTEM_PROMPT_FILE, AIDS_FILE, EXAMPLES_FILE)


class CommunityError(Exception):
    """A community cannot be loaded. The message is shown to the user."""


@dataclass
class CommunityInfo:
    folder: str
    path: Path
    display_name: str
    whatsapp_group: str
    missing_files: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return not self.missing_files


@dataclass
class Community:
    info: CommunityInfo
    system_prompt: str
    examples: str
    aids: AidsData
    prompt_version: str

    @property
    def folder(self) -> str:
        return self.info.folder

    @property
    def tag_names(self) -> list[str]:
        return [t.name for t in self.aids.tags]

    @property
    def keyword_names(self) -> list[str]:
        return [k.name for k in self.aids.keywords]


def discover(communities_dir: Path, config: Config) -> list[CommunityInfo]:
    if not communities_dir.is_dir():
        return []
    result = []
    for path in sorted(p for p in communities_dir.iterdir() if p.is_dir()):
        settings = config.community(path.name)
        result.append(
            CommunityInfo(
                folder=path.name,
                path=path,
                display_name=settings.display_name or path.name,
                whatsapp_group=settings.whatsapp_group,
                missing_files=[f for f in REQUIRED_FILES if not (path / f).is_file()],
            )
        )
    return result


def compute_prompt_version(folder: Path) -> str:
    """First 12 characters of a SHA-256 of the three community files."""
    h = hashlib.sha256()
    for name in REQUIRED_FILES:
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update((folder / name).read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:12]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig").strip()
    except UnicodeDecodeError as e:
        raise CommunityError(f"הקובץ {path.name} אינו שמור בקידוד UTF-8.\n{path}") from e
    except OSError as e:
        raise CommunityError(f"לא ניתן לקרוא את הקובץ {path.name}:\n{e}") from e


def load(info: CommunityInfo) -> Community:
    if info.missing_files:
        raise CommunityError(f"בתיקיית הקהילה \"{info.display_name}\" חסרים הקבצים: {', '.join(info.missing_files)}")
    system_prompt = _read_text(info.path / SYSTEM_PROMPT_FILE)
    examples = _read_text(info.path / EXAMPLES_FILE)
    if not system_prompt:
        raise CommunityError(f"הקובץ {SYSTEM_PROMPT_FILE} ריק.")
    try:
        aids = load_aids(info.path / AIDS_FILE)
    except ExcelError as e:
        raise CommunityError(str(e)) from e
    return Community(
        info=info,
        system_prompt=system_prompt,
        examples=examples,
        aids=aids,
        prompt_version=compute_prompt_version(info.path),
    )


def save_prompt_snapshot(community: Community, prompt_versions_dir: Path) -> None:
    """Keep a copy of the files behind a prompt version, the first time it is used (PRD §13)."""
    target = prompt_versions_dir / community.prompt_version
    if target.exists():
        return
    tmp = prompt_versions_dir / (community.prompt_version + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for name in REQUIRED_FILES:
        shutil.copy2(community.info.path / name, tmp / name)
    (tmp / "community.txt").write_text(community.folder + "\n", encoding="utf-8")
    tmp.rename(target)
