"""Gera os vídeos de todas as aulas, em fila, e publica cada um em media/.

Retomável: aulas já publicadas são puladas; se o MP4 já existe na pasta output/ do gerador, só é publicado.
Se uma aula falhar (2 tentativas), registra o erro e segue para a próxima. A GPU é usada por um vídeo por vez.

  python tools/video_course/generate_all.py \
      --generator-dir ~/projetos/videos-de-livros-automacao-oficial \
      --pdf livros/curso-educacao-financeira.pdf --minutes 3
  (opções: --only m0-l1,m0-l2   --force   --limit N)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from publish import load_manifest, publish  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _log_file_run(cmd: list[str], cwd: Path, env: dict, log_file: Path, timeout_s: int) -> bool:
    with log_file.open("a", encoding="utf-8") as f:
        f.write(f"\n===== {time.strftime('%F %T')} {' '.join(cmd)}\n")
        f.flush()
        try:
            return subprocess.run(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=timeout_s).returncode == 0
        except subprocess.TimeoutExpired:
            f.write("\n!!! tempo limite excedido\n")
            return False


def generator_cmd(gen: Path, pdf: Path, entry: dict, minutes: float, depth: str, until: str | None,
                  redo: str | None = None) -> list[str]:
    cmd = [str(gen / ".venv/bin/python"), "-m", "livro2video.cli",
           # opções globais vêm ANTES do subcomando. Sem exemplos inventados pela IA: tudo que o vídeo diz
           # vem do texto da aula, que foi conferido
           "--set", "script.allow_complement=false",
           "gerar", str(pdf), "--paginas", f"{entry['page_start']}-{entry['page_end']}", "--nome", entry["slug"],
           "--profundidade", depth, "--minutos", str(minutes)]
    return cmd + (["--ate", until] if until else []) + (["--refazer", redo] if redo else [])


def work_dir_of(log_file: Path, gen: Path) -> Path | None:
    """Pasta de trabalho da execução mais recente, lida do log do gerador."""
    found = re.findall(r"Pasta de trabalho:\s*(\S+)", log_file.read_text(encoding="utf-8", errors="ignore"))
    return Path(found[-1]) if found else None


def run_generator(gen: Path, pdf: Path, entry: dict, minutes: float, depth: str, log_file: Path, timeout_s: int) -> bool:
    """Duas fases: (1) gera o roteiro; (2) insere abertura/revisão/próxima aula; (3) conclui voz e vídeo."""
    env = {**os.environ, "PYTHONPATH": f"{gen / 'src'}:{ROOT}"}
    if not _log_file_run(generator_cmd(gen, pdf, entry, minutes, depth, "roteiro"), gen, env, log_file, timeout_s):
        return False
    work = work_dir_of(log_file, gen)
    if work is None:
        return False
    inject = [str(gen / ".venv/bin/python"), str(ROOT / "tools/video_course/inject_series.py"),
              "--work", str(work), "--lesson-id", entry["lesson_id"]]
    if not _log_file_run(inject, gen, env, log_file, 300):
        return False
    return _log_file_run(generator_cmd(gen, pdf, entry, minutes, depth, None), gen, env, log_file, timeout_s)


def refresh_series(gen: Path, pdf: Path, entry: dict, minutes: float, depth: str, log_file: Path, timeout_s: int) -> bool:
    """Troca as cenas da série (abertura/revisão/próxima aula) no roteiro já pronto e refaz só visuais, voz e vídeo.
    Roteiro, notas e a voz dos textos que não mudaram vêm do cache."""
    work = work_dir_of(log_file, gen) if log_file.exists() else None
    if work is None or not (work / "roteiro.json").exists():
        return False
    env = {**os.environ, "PYTHONPATH": f"{gen / 'src'}:{ROOT}"}
    inject = [str(gen / ".venv/bin/python"), str(ROOT / "tools/video_course/inject_series.py"),
              "--work", str(work), "--lesson-id", entry["lesson_id"], "--replace"]
    if not _log_file_run(inject, gen, env, log_file, 300):
        return False
    return _log_file_run(generator_cmd(gen, pdf, entry, minutes, depth, None, redo="visuais"), gen, env, log_file, timeout_s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--generator-dir", required=True, type=Path)
    ap.add_argument("--pdf", required=True, type=Path, help="caminho do PDF dentro do projeto do gerador (relativo a ele)")
    ap.add_argument("--index", type=Path, help="course_index.json (padrão: ao lado do PDF)")
    ap.add_argument("--media-dir", type=Path, default=ROOT / "media")
    ap.add_argument("--minutes", type=float, default=1.5)
    ap.add_argument("--depth", default="resumo", choices=["resumo", "padrao", "aprofundado"])
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--refresh-series", action="store_true",
                    help="refaz só as cenas da série (abertura/revisão/próxima aula) das aulas já geradas")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--timeout-min", type=int, default=45, help="tempo máximo por vídeo")
    args = ap.parse_args()

    gen = args.generator_dir.expanduser().resolve()
    pdf = args.pdf if args.pdf.is_absolute() else gen / args.pdf
    index_path = args.index or pdf.with_suffix(".index.json")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    args.media_dir.mkdir(parents=True, exist_ok=True)
    logs = args.media_dir / "logs"
    logs.mkdir(exist_ok=True)
    status_path = args.media_dir / "status.json"
    status: dict = json.loads(status_path.read_text()) if status_path.exists() else {}

    todo = [e for e in index if (not only or e["lesson_id"] in only)]
    started, done_now, failed = time.time(), 0, []
    for n, entry in enumerate(todo, start=1):
        lid, slug = entry["lesson_id"], entry["slug"]
        manifest = load_manifest(args.media_dir)
        if not args.force and not args.refresh_series and lid in manifest["lessons"] and (args.media_dir / manifest["lessons"][lid]["video"]).exists():
            log(f"[{n}/{len(todo)}] {lid} já publicada, pulando")
            continue
        if args.limit and done_now >= args.limit:
            break

        mp4 = gen / "output" / f"{slug}.mp4"
        t0 = time.time()
        if args.refresh_series:
            log(f"[{n}/{len(todo)}] {lid} {entry['title']}: refazendo as cenas da série")
            ok = (refresh_series(gen, pdf, entry, args.minutes, args.depth, logs / f"{slug}.log", args.timeout_min * 60)
                  and mp4.exists() and mp4.stat().st_mtime >= t0)
            if not ok:
                failed.append(lid)
                status[lid] = {"state": "refresh_failed", "at": time.strftime("%F %T")}
                log(f"[{n}/{len(todo)}] {lid} FALHOU ao refazer a série (veja {logs / (slug + '.log')}); o vídeo anterior foi mantido")
            else:
                try:
                    info = publish(mp4, mp4.with_suffix(".srt"), lid, entry["title"], args.media_dir, source=slug)
                    status[lid] = {"state": "done", "seconds": round(time.time() - t0), "video_s": info["duration_s"]}
                    done_now += 1
                    log(f"[{n}/{len(todo)}] {lid} pronta: vídeo de {info['duration_s']}s em {round(time.time() - t0)}s de processamento")
                except Exception as exc:  # noqa: BLE001
                    failed.append(lid)
                    log(f"[{n}/{len(todo)}] {lid} gerada, mas a publicação falhou: {exc}")
            status_path.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
            continue
        ok = mp4.exists() and not args.force
        for attempt in (1, 2):
            if ok:
                break
            log(f"[{n}/{len(todo)}] {lid} {entry['title']}: gerando (tentativa {attempt})")
            ok = run_generator(gen, pdf, entry, args.minutes, args.depth, logs / f"{slug}.log", args.timeout_min * 60) and mp4.exists()
        if not ok:
            failed.append(lid)
            status[lid] = {"state": "failed", "at": time.strftime("%F %T")}
            log(f"[{n}/{len(todo)}] {lid} FALHOU (veja {logs / (slug + '.log')})")
        else:
            try:
                info = publish(mp4, mp4.with_suffix(".srt"), lid, entry["title"], args.media_dir, source=slug)
                status[lid] = {"state": "done", "seconds": round(time.time() - t0), "video_s": info["duration_s"]}
                done_now += 1
                log(f"[{n}/{len(todo)}] {lid} pronta: vídeo de {info['duration_s']}s em {round(time.time() - t0)}s de processamento")
            except Exception as exc:  # noqa: BLE001
                failed.append(lid)
                status[lid] = {"state": "publish_failed", "error": str(exc)[:300]}
                log(f"[{n}/{len(todo)}] {lid} gerada, mas a publicação falhou: {exc}")
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")

    log(f"fim: {done_now} geradas agora, {len(failed)} falhas {failed or ''}, {round((time.time() - started) / 60)} min")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
