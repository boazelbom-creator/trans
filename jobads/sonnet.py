"""The Sonnet call: building the request, calling the API, checking the response (PRD §9)."""

import base64
import json
import logging
from dataclasses import dataclass, field

import anthropic

from .community import Community
from .images import AdImage

log = logging.getLogger(__name__)

MAX_TOKENS = 8000

# Server-side fallback: if the model declines the request, the API re-runs it on another model.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "is_job_ad": {"type": "boolean"},
        "rewritten_ad": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "score": {"type": "integer"},
        "score_reason": {"type": "string"},
    },
    "required": ["is_job_ad", "rewritten_ad", "tags", "keywords", "score", "score_reason"],
    "additionalProperties": False,
}


IMAGES_NOTE = (
    "The images attached above are part of the source ad. "
    "Read the job details from both the images and the text."
)
NO_TEXT_NOTE = "The ad has no text; all its details are in the images."


def build_user_content(ad_text: str, images: list[AdImage] | None) -> str | list[dict]:
    """The source ad: its text, plus its images when it has any."""
    if not images:
        return ad_text
    blocks = [
        {"type": "image", "source": {"type": "base64", "media_type": img.media_type, "data": base64.b64encode(img.data).decode("ascii")}}
        for img in images
    ]
    text = f"{IMAGES_NOTE}\n\n" + (f"Source ad text:\n{ad_text}" if ad_text.strip() else NO_TEXT_NOTE)
    blocks.append({"type": "text", "text": text})
    return blocks


class SonnetError(Exception):
    """The call failed. `user_message` is shown to the user (Hebrew)."""

    def __init__(self, user_message: str, detail: str = ""):
        super().__init__(detail or user_message)
        self.user_message = user_message


@dataclass
class RewriteResult:
    is_job_ad: bool
    rewritten_ad: str = ""
    tags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    score: int = 0
    score_reason: str = ""
    model: str = ""
    dropped_tags: list[str] = field(default_factory=list)
    dropped_keywords: list[str] = field(default_factory=list)


def _section(title: str, body: str) -> str:
    return f"=== {title} ===\n{body.strip()}\n"


def _rows(header: list[str], rows: list[list[str]]) -> str:
    lines = [" | ".join(header)]
    lines += [" | ".join(cell.replace("\n", " ") for cell in row) for row in rows]
    return "\n".join(lines)


def build_reference(community: Community) -> str:
    """The Excel sheets and examples, as text sections (PRD §9.1). Sent in Hebrew, as is."""
    aids = community.aids
    parts = [
        _section('גיליון "פורמט"', "\n\n".join(aids.format_blocks)),
        _section(
            'גיליון "ניסוחים נפוצים"',
            _rows(["תיאור דרישה [דוגמאות]", "ניסוח", "הערות"], [[p.description, p.phrasing, p.notes] for p in aids.phrases]),
        ),
        _section(
            'גיליון "תיוגים"',
            _rows(["קטגוריה", "האשטג", "סוג התוכן", "הערות"], [[t.category, t.name, t.description, t.notes] for t in aids.tags]),
        ),
        _section(
            'גיליון "מילות מפתח לחיפוש"',
            _rows(["מילת חיפוש", "פירוט"], [[k.name, k.details] for k in aids.keywords]),
        ),
        _section("examples.txt", community.examples),
    ]
    return "\n".join(parts)


def build_system(community: Community) -> list[dict]:
    return [
        {"type": "text", "text": community.system_prompt},
        {"type": "text", "text": "REFERENCE MATERIAL\n\n" + build_reference(community)},
    ]


def _match_terms(values: list, allowed: list[str], is_tag: bool) -> tuple[list[str], list[str]]:
    """Keep only terms from the community's lists, written as in the list (PRD §9.3)."""
    lookup = {a.strip(): a for a in allowed}
    if is_tag:
        lookup.update({a.strip().lstrip("#"): a for a in allowed})
    kept, dropped = [], []
    for v in values:
        if not isinstance(v, str) or not v.strip():
            continue
        key = v.strip()
        match = lookup.get(key) or (lookup.get(key.lstrip("#")) if is_tag else None)
        if match is None:
            dropped.append(key)
        elif match not in kept:
            kept.append(match)
    return kept, dropped


def parse_response(text: str, community: Community, model: str) -> RewriteResult:
    try:
        data = json.loads(text)
    except ValueError as e:
        raise SonnetError("התשובה מהמודל אינה תקינה. נסו שוב.", f"invalid JSON: {e}: {text[:500]!r}") from e
    if not isinstance(data, dict):
        raise SonnetError("התשובה מהמודל אינה תקינה. נסו שוב.", f"not an object: {text[:500]!r}")

    if not data.get("is_job_ad"):
        return RewriteResult(is_job_ad=False, model=model)

    rewritten = str(data.get("rewritten_ad") or "").strip()
    if not rewritten:
        raise SonnetError("המודל החזיר מודעה ריקה. נסו שוב.", "empty rewritten_ad")

    tags, dropped_tags = _match_terms(data.get("tags") or [], community.tag_names, is_tag=True)
    keywords, dropped_keywords = _match_terms(data.get("keywords") or [], community.keyword_names, is_tag=False)
    if dropped_tags or dropped_keywords:
        log.info("Dropped terms not in the lists: tags=%s keywords=%s", dropped_tags, dropped_keywords)

    try:
        score = int(data.get("score") or 0)
    except (TypeError, ValueError):
        score = 0

    return RewriteResult(
        is_job_ad=True,
        rewritten_ad=rewritten,
        tags=tags,
        keywords=keywords,
        score=max(0, min(100, score)),
        score_reason=str(data.get("score_reason") or "").strip(),
        model=model,
        dropped_tags=dropped_tags,
        dropped_keywords=dropped_keywords,
    )


def _is_limit_error(e: anthropic.APIStatusError) -> bool:
    msg = str(getattr(e, "message", "") or e).lower()
    return e.status_code == 402 or any(
        s in msg for s in ("credit balance", "usage limit", "spend limit", "billing", "workspace api usage limits")
    )


def _create(client: anthropic.Anthropic, request: dict, use_fallback: bool):
    if use_fallback:
        return client.beta.messages.create(**request, betas=[FALLBACK_BETA], fallbacks="default")
    return client.messages.create(**request)


def rewrite(
    client: anthropic.Anthropic,
    community: Community,
    ad_text: str,
    model: str,
    effort: str,
    images: list[AdImage] | None = None,
) -> RewriteResult:
    """Rewrite one ad. Runs in a background thread. Raises SonnetError with a Hebrew message on failure."""
    request = dict(
        model=model,
        max_tokens=MAX_TOKENS,
        system=build_system(community),
        messages=[{"role": "user", "content": build_user_content(ad_text, images)}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    )
    try:
        try:
            response = _create(client, request, use_fallback=True)
        except anthropic.BadRequestError as e:
            # If the fallback option is not accepted for this request, send it without the fallback.
            if "fallback" not in str(e).lower():
                raise
            log.warning("Fallback not accepted, retrying without it: %s", e)
            response = _create(client, request, use_fallback=False)
    except anthropic.AuthenticationError as e:
        raise SonnetError("מפתח ה-API אינו תקין. בדקו את הקובץ api_key.json.", str(e)) from e
    except anthropic.PermissionDeniedError as e:
        raise SonnetError("למפתח ה-API אין הרשאה לבצע את הפעולה. בדקו את הקובץ api_key.json.", str(e)) from e
    except anthropic.NotFoundError as e:
        raise SonnetError(f"המודל \"{model}\" לא נמצא. בדקו את השדה model בקובץ config.json.", str(e)) from e
    except anthropic.RateLimitError as e:
        raise SonnetError("שירות ה-API עמוס כרגע. נסו שוב בעוד דקה.", str(e)) from e
    except anthropic.APIConnectionError as e:
        raise SonnetError("אין חיבור לאינטרנט, או ששירות ה-API אינו זמין. בדקו את החיבור ונסו שוב.", str(e)) from e
    except anthropic.APIStatusError as e:
        if _is_limit_error(e):
            raise SonnetError("הגעת למגבלת השימוש ב-API (מגבלת הוצאה או יתרה). ניתן לעדכן אותה במסוף של Anthropic.", str(e)) from e
        if e.status_code >= 500 or e.status_code == 529:
            raise SonnetError("שירות ה-API אינו זמין כרגע. נסו שוב בעוד כמה דקות.", str(e)) from e
        raise SonnetError(f"שגיאה בקריאה ל-API ({e.status_code}). הפרטים נשמרו ביומן.", str(e)) from e

    log.info(
        "Sonnet call: model=%s stop=%s in=%s out=%s request_id=%s",
        response.model, response.stop_reason, response.usage.input_tokens, response.usage.output_tokens,
        getattr(response, "_request_id", ""),
    )
    if response.stop_reason == "refusal":
        raise SonnetError("המודל סירב לעבד את המודעה.", f"refusal: {getattr(response, 'stop_details', None)}")
    if response.stop_reason == "max_tokens":
        raise SonnetError("התשובה מהמודל נקטעה. נסו שוב.", "stop_reason=max_tokens")

    texts = [b.text for b in response.content if getattr(b, "type", "") == "text"]
    if not texts:
        raise SonnetError("התשובה מהמודל ריקה. נסו שוב.", f"no text block, stop={response.stop_reason}")
    # With a fallback, the final answer is the last text block.
    return parse_response(texts[-1], community, response.model)
