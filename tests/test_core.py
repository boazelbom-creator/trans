import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest

from jobads import community as community_mod
from jobads import sonnet
from jobads.config import ConfigError, load_api_key, load_config
from jobads.db import STATUS_APPROVED, STATUS_DISTRIBUTED, STATUS_NEW, Database
from jobads.excel_loader import SOURCE_FACEBOOK, SOURCE_WEBSITE, SOURCE_WHATSAPP, source_type
from jobads.text_clean import clean_text, fingerprint

ROOT = Path(__file__).resolve().parent.parent
AUTISM = ROOT / "communities" / "autism"


# ---- text cleaning and fingerprint ----

def test_clean_removes_emojis_and_invisible_chars():
    raw = "📍 חיפה\n\n\n\n✅ דרוש.ה  מזכיר.ה‏ ⭐️\n⁦+972 52-242-6638⁩ office@x.co.il https://a.b/c?d=1"
    assert clean_text(raw) == "חיפה\n\nדרוש.ה מזכיר.ה\n+972 52-242-6638 office@x.co.il https://a.b/c?d=1"


def test_clean_keeps_hebrew_english_punctuation():
    raw = "ל-More Admin דרוש.ה Business Admin (50%) - 45 ש\"ח לשעה, ₪!"
    assert clean_text(raw) == raw


def test_fingerprint_ignores_spacing_emojis_case_punctuation():
    a = "דרוש.ה מזכיר.ה Back Office\nחיפה"
    b = "  📍דרוש.ה   מזכיר.ה back office!!  \n\n חיפה ✅"
    assert fingerprint(a) == fingerprint(b)
    assert fingerprint(a) != fingerprint("דרוש.ה מזכיר.ה Front Office חיפה")


# ---- config ----

def test_config_load_and_save(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"active_community": "autism", "communities": {"autism": {"display_name": "אוטיזם", "whatsapp_group": "g"}}, "extra": 1}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.model == "claude-sonnet-5-5" and cfg.effort == "low"
    assert cfg.community("autism").whatsapp_group == "g"
    cfg.set_active_community("trans")
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["active_community"] == "trans" and saved["extra"] == 1


def test_config_errors(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.json")
    bad = tmp_path / "c.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(bad)
    bad.write_text('{"effort": "turbo"}', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(bad)
    key = tmp_path / "k.json"
    key.write_text('{"api_key": ""}', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_api_key(key)


# ---- Excel and community ----

def test_source_type():
    assert source_type("https://www.facebook.com/groups/1") == SOURCE_FACEBOOK
    assert source_type("https://chat.whatsapp.com/abc") == SOURCE_WHATSAPP
    assert source_type("https://www.drushim.co.il/") == SOURCE_WEBSITE


@pytest.fixture
def autism(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text('{"communities": {"autism": {"display_name": "אוטיזם", "whatsapp_group": "thomas vinters"}}}', encoding="utf-8")
    cfg = load_config(cfg_path)
    infos = community_mod.discover(ROOT / "communities", cfg)
    info = next(i for i in infos if i.folder == "autism")
    return community_mod.load(info)


def test_load_real_community(autism):
    aids = autism.aids
    assert autism.info.display_name == "אוטיזם"
    assert len(aids.sources) == 16
    assert all(s.url.startswith("https://") for s in aids.sources)
    assert "#חלקית" in autism.tag_names and "#ללא_ניסיון" in autism.tag_names
    assert all(t.category for t in aids.tags)
    assert "CNC" in autism.keyword_names
    assert any("דרוש.ה" in b for b in aids.format_blocks)
    assert len(autism.prompt_version) == 12


def test_missing_files_and_snapshot(tmp_path, autism):
    comm_dir = tmp_path / "communities"
    shutil.copytree(AUTISM, comm_dir / "a")
    (comm_dir / "b").mkdir()
    (comm_dir / "b" / "system_prompt.txt").write_text("x", encoding="utf-8")
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}", encoding="utf-8")
    infos = {i.folder: i for i in community_mod.discover(comm_dir, load_config(cfg_path))}
    assert infos["a"].usable and infos["a"].display_name == "a"
    assert infos["b"].missing_files == ["aids.xlsx", "examples.txt"]
    with pytest.raises(community_mod.CommunityError):
        community_mod.load(infos["b"])

    a = community_mod.load(infos["a"])
    assert a.prompt_version == autism.prompt_version  # same files -> same version
    community_mod.save_prompt_snapshot(a, tmp_path / "pv")
    snap = tmp_path / "pv" / a.prompt_version
    assert sorted(p.name for p in snap.iterdir()) == ["aids.xlsx", "community.txt", "examples.txt", "system_prompt.txt"]
    (comm_dir / "a" / "examples.txt").write_text("changed", encoding="utf-8")
    assert community_mod.compute_prompt_version(comm_dir / "a") != a.prompt_version


# ---- database ----

def _add(db, text="ad", community="autism"):
    return db.add_ad(
        community=community, source_name="src", source_url="https://x", origin_ad=text,
        origin_hash=fingerprint(text), sonnet_ad="rewritten " + text, tags=["#חלקית"], keywords=["CNC"],
        score=70, score_reason="r", model="claude-sonnet-5-5", prompt_version="abc",
    )


def test_database_flow(tmp_path):
    db = Database(tmp_path / "ads.db")
    ad_id = _add(db, "מודעה אחת")
    _add(db, "other", community="trans")
    ad = db.get_ad(ad_id)
    assert ad.status == STATUS_NEW and ad.user_ad == ad.sonnet_ad == "rewritten מודעה אחת"
    assert ad.tags == ["#חלקית"]
    assert db.find_by_hash("autism", fingerprint(" מודעה  אחת!")) == ad_id
    assert db.find_by_hash("trans", fingerprint("מודעה אחת")) is None

    listed = db.list_ads("autism")
    assert len(listed) == 1 and listed[0].user_ad == ""  # list has no texts

    db.update_text(ad_id, "edited")
    db.set_status(ad_id, STATUS_APPROVED)
    db.mark_distributed(ad_id)
    ad = db.get_ad(ad_id)
    assert ad.user_ad == "edited" and ad.origin_ad == "מודעה אחת" and ad.sonnet_ad == "rewritten מודעה אחת"
    assert ad.status == STATUS_DISTRIBUTED and ad.distribute_date
    db.close()


def test_corrupted_database(tmp_path):
    from jobads.db import DatabaseError
    p = tmp_path / "ads.db"
    p.write_bytes(b"this is not a database" * 100)
    with pytest.raises(DatabaseError):
        Database(p)


# ---- Sonnet ----

def test_build_system(autism):
    system = sonnet.build_system(autism)
    assert system[0]["text"].startswith("PURPOSE")
    ref = system[1]["text"]
    for title in ("פורמט", "ניסוחים נפוצים", "תיוגים", "מילות מפתח לחיפוש", "examples.txt"):
        assert title in ref
    assert "#ללא_ניסיון" in ref and "Back Office" in ref


def test_parse_response_filters_terms(autism):
    text = json.dumps({
        "is_job_ad": True, "rewritten_ad": " מודעה ", "tags": ["#חלקית", "ללא_ניסיון", "#לא_קיים", "#חלקית"],
        "keywords": ["CNC", "nothing"], "score": 140, "score_reason": "סיבה",
    }, ensure_ascii=False)
    r = sonnet.parse_response(text, autism, "m")
    assert r.rewritten_ad == "מודעה"
    assert r.tags == ["#חלקית", "#ללא_ניסיון"] and r.dropped_tags == ["#לא_קיים"]
    assert r.keywords == ["CNC"] and r.dropped_keywords == ["nothing"]
    assert r.score == 100


def test_parse_response_not_job_and_errors(autism):
    r = sonnet.parse_response('{"is_job_ad": false, "rewritten_ad": "", "tags": [], "keywords": [], "score": 0, "score_reason": ""}', autism, "m")
    assert r.is_job_ad is False
    with pytest.raises(sonnet.SonnetError):
        sonnet.parse_response("not json", autism, "m")
    with pytest.raises(sonnet.SonnetError):
        sonnet.parse_response('{"is_job_ad": true, "rewritten_ad": "  ", "tags": [], "keywords": [], "score": 1, "score_reason": ""}', autism, "m")


class _FakeMessages:
    def __init__(self, outcomes, calls):
        self.outcomes, self.calls = outcomes, calls

    def create(self, **kwargs):
        self.calls.append(kwargs)
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def _fake_client(outcomes):
    calls = []
    msgs = _FakeMessages(outcomes, calls)
    return SimpleNamespace(messages=msgs, beta=SimpleNamespace(messages=msgs)), calls


def _response(text, stop="end_turn"):
    return SimpleNamespace(
        model="claude-sonnet-5-5", stop_reason=stop, stop_details=None,
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
    )


def _status_error(cls, status, message):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(status, request=req, json={"error": {"message": message}})
    return cls(message, response=resp, body=None)


def test_rewrite_request_shape(autism):
    ok = json.dumps({"is_job_ad": True, "rewritten_ad": "x", "tags": [], "keywords": [], "score": 50, "score_reason": ""})
    client, calls = _fake_client([_response(ok)])
    r = sonnet.rewrite(client, autism, "המודעה", "claude-sonnet-5-5", "low")
    assert r.is_job_ad and r.score == 50
    c = calls[0]
    assert c["model"] == "claude-sonnet-5-5"
    assert c["output_config"]["effort"] == "low"
    assert c["output_config"]["format"]["type"] == "json_schema"
    assert c["messages"] == [{"role": "user", "content": "המודעה"}]
    assert c["fallbacks"] == "default" and c["betas"] == [sonnet.FALLBACK_BETA]


def test_rewrite_retries_without_fallback(autism):
    ok = json.dumps({"is_job_ad": False, "rewritten_ad": "", "tags": [], "keywords": [], "score": 0, "score_reason": ""})
    err = _status_error(anthropic.BadRequestError, 400, "fallbacks: not supported")
    client, calls = _fake_client([err, _response(ok)])
    assert sonnet.rewrite(client, autism, "x", "m", "low").is_job_ad is False
    assert "fallbacks" not in calls[1]


@pytest.mark.parametrize("error,expected", [
    (_status_error(anthropic.AuthenticationError, 401, "invalid x-api-key"), "api_key.json"),
    (_status_error(anthropic.BadRequestError, 400, "Your credit balance is too low"), "מגבלת השימוש"),
    (_status_error(anthropic.InternalServerError, 500, "boom"), "אינו זמין"),
    (anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com")), "אין חיבור"),
])
def test_rewrite_error_messages(autism, error, expected):
    client, _ = _fake_client([error])
    with pytest.raises(sonnet.SonnetError) as e:
        sonnet.rewrite(client, autism, "x", "m", "low")
    assert expected in e.value.user_message


def test_rewrite_refusal(autism):
    client, _ = _fake_client([_response("", stop="refusal")])
    with pytest.raises(sonnet.SonnetError) as e:
        sonnet.rewrite(client, autism, "x", "m", "low")
    assert "סירב" in e.value.user_message


# ---- images ----

def _png(w, h, color="red"):
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QColor, QImage
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(QColor(color))
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def test_images_resize_and_filter():
    from jobads import images
    assert images.from_bytes(_png(120, 120)) is None  # icon-sized
    assert images.from_bytes(b"not an image") is None
    big = images.from_bytes(_png(3000, 1500))
    assert (big.width, big.height) == (1568, 784) and big.data[:2] == b"\xff\xd8"  # JPEG
    small_ok = images.from_bytes(_png(600, 400))
    assert (small_ok.width, small_ok.height) == (600, 400)


def test_combined_fingerprint():
    from jobads import images
    a = images.from_bytes(_png(600, 400, "red"))
    b = images.from_bytes(_png(600, 400, "blue"))
    fp = fingerprint("text")
    assert images.combined_fingerprint(fp, []) == fp
    assert images.combined_fingerprint(fp, [a, b]) == images.combined_fingerprint(fp, [b, a])
    assert images.combined_fingerprint(fp, [a]) != images.combined_fingerprint(fp, [b])


def test_rewrite_sends_images(autism):
    from jobads import images
    img = images.from_bytes(_png(600, 400))
    ok = json.dumps({"is_job_ad": True, "rewritten_ad": "x", "tags": [], "keywords": [], "score": 50, "score_reason": ""})
    client, calls = _fake_client([_response(ok), _response(ok)])
    sonnet.rewrite(client, autism, "טקסט", "m", "low", [img])
    content = calls[0]["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/jpeg"
    assert content[-1]["type"] == "text" and "טקסט" in content[-1]["text"] and sonnet.IMAGES_NOTE in content[-1]["text"]
    sonnet.rewrite(client, autism, "", "m", "low", [img])
    assert sonnet.NO_TEXT_NOTE in calls[1]["messages"][0]["content"][-1]["text"]


def test_database_images_and_migration(tmp_path):
    import sqlite3
    p = tmp_path / "old.db"
    old = sqlite3.connect(p)
    old.execute("CREATE TABLE ads (id INTEGER PRIMARY KEY AUTOINCREMENT, community TEXT NOT NULL, collect_date TEXT NOT NULL, "
                "distribute_date TEXT NOT NULL DEFAULT '', source_name TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL DEFAULT '', "
                "origin_ad TEXT NOT NULL, origin_hash TEXT NOT NULL, sonnet_ad TEXT NOT NULL, user_ad TEXT NOT NULL, "
                "status TEXT NOT NULL DEFAULT 'new', tags TEXT NOT NULL DEFAULT '[]', keywords TEXT NOT NULL DEFAULT '[]', "
                "score INTEGER NOT NULL DEFAULT 0, score_reason TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '', "
                "prompt_version TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL)")
    old.execute("INSERT INTO ads (community, collect_date, origin_ad, origin_hash, sonnet_ad, user_ad, updated_at) "
                "VALUES ('autism', '2026-10-15T10:00:00', 'o', 'h', 's', 'u', '2026-10-15T10:00:00')")
    old.commit()
    old.close()
    db = Database(p)  # adds the new column
    assert db.get_ad(1).origin_images == []
    ad_id = _add(db, "with images")
    db.set_images(ad_id, ["2_1.jpg", "2_2.jpg"])
    assert db.get_ad(ad_id).origin_images == ["2_1.jpg", "2_2.jpg"]
    db.close()
