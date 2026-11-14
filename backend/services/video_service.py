"""Vídeos das aulas (whiteboard, gerados pelo livro2video).

O manifesto `media/manifest.json` liga cada aula ao seu vídeo, capa, legendas e duração. A origem dos arquivos é
`MEDIA_BASE_URL`: por padrão o próprio backend (`/api/media`); em produção pode ser um bucket/CDN, caso em que
confiamos no manifesto (os arquivos não estão no servidor).
"""
import json
import mimetypes
from pathlib import Path

from backend.config import get_settings

ALLOWED_SUFFIXES = {".mp4", ".jpg", ".jpeg", ".png", ".vtt"}      # nunca manifest.json, logs ou status
_cache: dict = {"key": None, "lessons": {}}


def media_dir() -> Path:
    return get_settings().media_dir


def _manifest() -> dict:
    path = media_dir() / "manifest.json"
    try:
        key = (str(path), path.stat().st_mtime_ns)
    except FileNotFoundError:
        return {}
    if _cache["key"] != key:
        try:
            _cache["lessons"] = json.loads(path.read_text(encoding="utf-8")).get("lessons", {})
        except (OSError, ValueError):
            return {}                                   # manifesto ilegível: sem vídeos, nunca erro 500
        _cache["key"] = key
    return _cache["lessons"]


def _external() -> bool:
    return get_settings().media_base_url.startswith(("http://", "https://"))


def _url(rel: str) -> str:
    return f"{get_settings().media_base_url.rstrip('/')}/{rel}"


def video_for(lesson_id: str) -> dict | None:
    entry = _manifest().get(lesson_id)
    if not entry or "video" not in entry:
        return None
    if not _external() and resolve(entry["video"]) is None:
        return None                                     # no manifesto, mas o arquivo não está aqui
    return {
        "url": _url(entry["video"]),
        "poster_url": _url(entry["poster"]) if entry.get("poster") else None,
        "captions_url": _url(entry["captions"]) if entry.get("captions") else None,
        "duration_s": int(entry.get("duration_s", 0)),
        "size_bytes": int(entry.get("size_bytes", 0)),
    }


def seconds_for(lesson_id: str) -> int | None:
    v = video_for(lesson_id)
    return v["duration_s"] if v else None


def resolve(rel: str) -> Path | None:
    """Caminho seguro dentro de media/: recusa saída da pasta (../), extensões não listadas e não-arquivos."""
    try:
        base = media_dir().resolve()
        path = (base / rel).resolve()
        path.relative_to(base)
    except (ValueError, OSError):
        return None
    if path.suffix.lower() not in ALLOWED_SUFFIXES or not path.is_file():
        return None
    return path


def media_type(path: Path) -> str:
    if path.suffix.lower() == ".vtt":
        return "text/vtt"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"
