"""Publica um vídeo gerado pelo livro2video na pasta media/ do simulador.

Para cada aula: remuxa o MP4 com `faststart` (permite assistir enquanto baixa e pular no vídeo), cria a capa (JPG),
converte as legendas SRT para WebVTT e registra tudo em media/manifest.json (lesson_id -> arquivos e duração).
Só usa a biblioteca padrão e o ffmpeg/ffprobe do sistema.
"""
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def probe_duration(path: Path) -> float:
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip())


def srt_to_vtt(srt_text: str) -> str:
    body = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", srt_text.replace("\r\n", "\n").lstrip("﻿"))
    return "WEBVTT\n\n" + body.strip() + "\n"


def load_manifest(media_dir: Path) -> dict:
    path = media_dir / "manifest.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"version": 1, "lessons": {}}


def save_manifest(media_dir: Path, manifest: dict) -> None:
    path = media_dir / "manifest.json"
    fd, tmp = tempfile.mkstemp(dir=media_dir, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)            # gravação atômica: o backend nunca lê um manifesto pela metade


def publish(mp4: Path, srt: Path | None, lesson_id: str, title: str, media_dir: Path, source: str) -> dict:
    (media_dir / "videos").mkdir(parents=True, exist_ok=True)
    (media_dir / "posters").mkdir(exist_ok=True)
    (media_dir / "captions").mkdir(exist_ok=True)

    video = media_dir / "videos" / f"{lesson_id}.mp4"
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(mp4), "-c", "copy", "-movflags", "+faststart", str(video)])
    duration = probe_duration(video)

    poster = media_dir / "posters" / f"{lesson_id}.jpg"
    _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{duration * 0.18:.2f}", "-i", str(video), "-frames:v", "1",
          "-vf", "scale=960:-2", "-q:v", "4", str(poster)])

    entry = {"title": title, "video": f"videos/{lesson_id}.mp4", "poster": f"posters/{lesson_id}.jpg",
             "duration_s": round(duration), "size_bytes": video.stat().st_size, "source": source,
             "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if srt and srt.exists():
        vtt = media_dir / "captions" / f"{lesson_id}.vtt"
        vtt.write_text(srt_to_vtt(srt.read_text(encoding="utf-8")), encoding="utf-8")
        entry["captions"] = f"captions/{lesson_id}.vtt"

    manifest = load_manifest(media_dir)
    manifest["lessons"][lesson_id] = entry
    save_manifest(media_dir, manifest)
    return entry
