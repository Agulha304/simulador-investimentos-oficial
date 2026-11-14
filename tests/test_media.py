import importlib.util
import json
import sys
from pathlib import Path

import pytest

from backend.config import get_settings
from backend.services import video_service

VIDEO = b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 8        # 2.0 KB de "vídeo"


@pytest.fixture
def media(tmp_path, monkeypatch):
    """Pasta de mídia com o vídeo da aula m0-l1 e uma entrada do manifesto sem arquivo (m0-l2)."""
    root = tmp_path / "media"
    for d in ("videos", "posters", "captions", "logs"):
        (root / d).mkdir(parents=True)
    (root / "videos/m0-l1.mp4").write_bytes(VIDEO)
    (root / "posters/m0-l1.jpg").write_bytes(b"\xff\xd8\xff poster")
    (root / "captions/m0-l1.vtt").write_text("WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nOlá\n", encoding="utf-8")
    (root / "logs/segredo.log").write_text("não pode sair", encoding="utf-8")
    (tmp_path / "fora.mp4").write_bytes("fora da pasta de mídia".encode("utf-8"))
    (root / "manifest.json").write_text(json.dumps({"version": 1, "lessons": {
        "m0-l1": {"video": "videos/m0-l1.mp4", "poster": "posters/m0-l1.jpg", "captions": "captions/m0-l1.vtt",
                  "duration_s": 190, "size_bytes": len(VIDEO)},
        "m0-l2": {"video": "videos/m0-l2.mp4", "duration_s": 200, "size_bytes": 1},
    }}), encoding="utf-8")
    monkeypatch.setattr(video_service, "media_dir", lambda: root)
    return root


def lesson(client, h, lid):
    r = client.get(f"/api/learn/lessons/{lid}", headers=h)
    assert r.status_code == 200
    return r.json()


def test_lesson_exposes_its_video(client, auth_headers, media):
    v = lesson(client, auth_headers, "m0-l1")["video"]
    assert v == {"url": "/api/media/videos/m0-l1.mp4", "poster_url": "/api/media/posters/m0-l1.jpg",
                 "captions_url": "/api/media/captions/m0-l1.vtt", "duration_s": 190, "size_bytes": len(VIDEO)}
    assert lesson(client, auth_headers, "m0-l3")["video"] is None                      # sem entrada no manifesto
    assert lesson(client, auth_headers, "m0-l2")["video"] is None                      # no manifesto, mas sem arquivo


def test_overview_counts_videos(client, auth_headers, media):
    o = client.get("/api/learn", headers=auth_headers).json()
    assert (o["videos"], o["video_seconds"]) == (1, 190)
    m0 = next(m for m in o["modules"] if m["id"] == "m0")
    assert m0["video_seconds"] == 190
    by_id = {l["id"]: l for l in m0["lessons"]}
    assert by_id["m0-l1"]["video_seconds"] == 190 and by_id["m0-l2"]["video_seconds"] is None


def test_without_media_everything_still_works(client, auth_headers):                  # fixture autouse: pasta vazia
    o = client.get("/api/learn", headers=auth_headers).json()
    assert o["videos"] == 0 and o["video_seconds"] == 0
    assert lesson(client, auth_headers, "m0-l1")["video"] is None


def test_corrupted_manifest_does_not_break_lessons(client, auth_headers, media):
    (media / "manifest.json").write_text("{isto não é json", encoding="utf-8")
    assert lesson(client, auth_headers, "m0-l1")["video"] is None


def test_external_media_origin_trusts_the_manifest(client, auth_headers, media, monkeypatch):
    monkeypatch.setattr(get_settings(), "media_base_url", "https://cdn.exemplo.com/curso/")
    (media / "videos/m0-l1.mp4").unlink()                                              # arquivos não estão neste servidor
    v = lesson(client, auth_headers, "m0-l1")["video"]
    assert v["url"] == "https://cdn.exemplo.com/curso/videos/m0-l1.mp4" and v["poster_url"].startswith("https://cdn.exemplo.com/curso/posters/")
    assert lesson(client, auth_headers, "m0-l2")["video"]["url"].endswith("videos/m0-l2.mp4")


def test_serves_files_publicly_with_range_support(client, media):
    r = client.get("/api/media/videos/m0-l1.mp4")                                      # sem login: <video> não envia token
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4" and r.content == VIDEO
    assert r.headers.get("accept-ranges") == "bytes" and "max-age" in r.headers["cache-control"]
    part = client.get("/api/media/videos/m0-l1.mp4", headers={"Range": "bytes=10-109"})
    assert part.status_code == 206 and part.content == VIDEO[10:110]
    assert part.headers["content-range"] == f"bytes 10-109/{len(VIDEO)}"
    assert client.get("/api/media/captions/m0-l1.vtt").headers["content-type"].startswith("text/vtt")
    assert client.get("/api/media/posters/m0-l1.jpg").status_code == 200


@pytest.mark.parametrize("path", ["manifest.json", "logs/segredo.log", "videos/nao-existe.mp4", "videos",
                                  "videos/../manifest.json", "..%2Ffora.mp4", "videos/..%2F..%2Ffora.mp4",
                                  "%2e%2e/fora.mp4", "videos/m0-l1.mp4/../../manifest.json"])
def test_media_endpoint_never_leaks_other_files(client, media, path):
    assert client.get(f"/api/media/{path}").status_code == 404


# ------------------------------------------------------------------ ferramentas de publicação

def _load_tool(name):
    path = Path(__file__).resolve().parents[1] / "tools" / "video_course" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"tool_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_srt_is_converted_to_webvtt():
    pub = _load_tool("publish")
    srt = "﻿1\r\n00:00:01,500 --> 00:00:03,250\r\nOlá, mundo\r\n\r\n2\r\n00:00:04,000 --> 00:00:05,000\r\nSegunda\r\n"
    vtt = pub.srt_to_vtt(srt)
    assert vtt.startswith("WEBVTT\n\n1\n00:00:01.500 --> 00:00:03.250\nOlá, mundo")
    assert "00:00:04.000 --> 00:00:05.000" in vtt and "," not in vtt.split("Olá")[0]


def test_manifest_roundtrip_is_atomic_and_keeps_other_lessons(tmp_path):
    pub = _load_tool("publish")
    assert pub.load_manifest(tmp_path) == {"version": 1, "lessons": {}}
    m = pub.load_manifest(tmp_path)
    m["lessons"]["m0-l1"] = {"video": "videos/m0-l1.mp4", "duration_s": 5}
    pub.save_manifest(tmp_path, m)
    m2 = pub.load_manifest(tmp_path)
    m2["lessons"]["m0-l2"] = {"video": "videos/m0-l2.mp4", "duration_s": 6}
    pub.save_manifest(tmp_path, m2)
    assert set(pub.load_manifest(tmp_path)["lessons"]) == {"m0-l1", "m0-l2"}
    assert not list(tmp_path.glob("*.tmp"))
