"""Gera o PDF do curso (uma aula por trecho) a partir do conteúdo das aulas do simulador.

O PDF é a entrada do gerador de videoaulas (projeto livro2video). Cada aula começa em página nova, tem título
destacado e marcador no sumário do PDF, e traz o texto de ligação com a aula anterior e a próxima, para a série
de vídeos ter continuidade. Também grava `course_index.json` com as páginas de cada aula.

Uso (precisa do PyMuPDF, que o ambiente do livro2video já tem):
  PYTHONPATH=<raiz do simulador> <venv do livro2video>/bin/python tools/video_course/build_pdf.py \
      --out <pasta livros do livro2video>/curso-educacao-financeira.pdf
"""
import argparse
import html
import json
import re
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF

from backend.content.course import LESSONS_ORDERED, MODULE_OF, TOTAL_LESSONS

CSS = """
body { font-family: sans-serif; font-size: 11pt; line-height: 1.45; }
h1 { font-size: 22pt; margin: 0 0 4pt 0; }
h2 { font-size: 13pt; margin: 14pt 0 4pt 0; }
h3 { font-size: 12pt; margin: 12pt 0 3pt 0; }
p { margin: 0 0 7pt 0; }
li { margin: 0 0 3pt 0; }
table { border-collapse: collapse; margin: 6pt 0 10pt 0; }
td, th { border: 1px solid #888; padding: 3pt 5pt; }
th { background-color: #e8e8e8; }
.mod { color: #555555; font-size: 10pt; margin: 0 0 14pt 0; }
.formula { font-family: monospace; background-color: #f0f0f0; padding: 4pt; margin: 4pt 0 8pt 0; }
"""

DISCLAIMER_START = "Conteúdo educacional"


def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:48]


def inline(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text))


def blocks_html(lesson, first: bool) -> str:
    out = []
    for b in lesson.blocks:
        kind = b[0]
        if kind == "h":
            out.append(f"<h3>{html.escape(b[1])}</h3>")
        elif kind == "p":
            out.append(f"<p>{inline(b[1])}</p>")
        elif kind == "ul":
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in b[1]) + "</ul>")
        elif kind == "tip":
            out.append(f"<p><b>Dica:</b> {inline(b[1])}</p>")
        elif kind == "warn":
            if b[1].startswith(DISCLAIMER_START) and not first:
                continue                      # o aviso padrão só abre o curso: evita repeti-lo em todos os vídeos
            out.append(f"<p><b>Atenção:</b> {inline(b[1])}</p>")
        elif kind == "formula":
            out.append(f'<p class="formula">{html.escape(b[1])}</p>')
        elif kind == "table":
            head = "".join(f"<th>{html.escape(h)}</th>" for h in b[1])
            rows = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in b[2])
            out.append(f"<table><tr>{head}</tr>{rows}</table>")
        elif kind == "sim":
            out.append(f"<p>Para praticar, use o simulador: {html.escape(b[2])}.</p>")
    return "\n".join(out)


def lesson_html(i: int, lesson) -> str:
    module = MODULE_OF[lesson.id]
    prev = LESSONS_ORDERED[i - 1] if i > 0 else None
    nxt = LESSONS_ORDERED[i + 1] if i + 1 < TOTAL_LESSONS else None
    n = i + 1

    if prev is None:
        intro = (f"Esta é a aula {n} de {TOTAL_LESSONS} do curso de educação financeira e investimentos. "
                 f"Ao longo da série você vai organizar o seu dinheiro e aprender a investir, passo a passo. "
                 f"Nesta primeira aula: {lesson.summary}")
    else:
        same = MODULE_OF[prev.id].id == module.id
        link = (f"Na aula anterior, você viu: {prev.title}." if same
                else f"Na aula anterior, você terminou o módulo {MODULE_OF[prev.id].title} com o tema {prev.title}. "
                     f"Agora começa um novo módulo: {module.title}.")
        intro = f"Aula {n} de {TOTAL_LESSONS}. {link} Nesta aula: {lesson.summary}"

    review = "".join(
        f"<p><b>{html.escape(q.text)}</b><br/>Resposta: {html.escape(q.options[q.correct])}. {html.escape(q.explanation)}</p>"
        for q in lesson.quiz)
    if nxt is None:
        outro = "Esta foi a última aula da série. Pratique no simulador, revise as aulas quando precisar e invista com calma e com método."
    else:
        outro = f"Na próxima aula: {nxt.title}. {nxt.summary}"

    return (f"<h1>Aula {n:02d}: {html.escape(lesson.title)}</h1>"
            f'<p class="mod">Módulo: {html.escape(module.title)} · {lesson.minutes} min de leitura</p>'
            f"<p>{html.escape(intro)}</p>"
            f"{blocks_html(lesson, first=prev is None)}"
            f"<h2>Revisão da aula</h2>{review}"
            f"<h2>Próximos passos</h2><p>{html.escape(outro)}</p>")


def render(html_text: str) -> fitz.Document:
    """Renderiza o HTML em um PDF próprio (A4, margens de 2 cm)."""
    buf = fitz.Story(html=html_text, user_css=CSS)
    mediabox, where = fitz.paper_rect("a4"), fitz.paper_rect("a4") + (56, 56, -56, -56)
    doc = fitz.DocumentWriter(path := _tmp_path())
    more = True
    while more:
        dev = doc.begin_page(mediabox)
        more, _ = buf.place(where)
        buf.draw(dev)
        doc.end_page()
    doc.close()
    out = fitz.open(path)
    Path(path).unlink(missing_ok=True)
    return out


_n = 0


def _tmp_path() -> str:
    global _n
    _n += 1
    return f"/tmp/_curso_part_{_n}.pdf"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--index", type=Path, help="onde gravar o course_index.json (padrão: ao lado do PDF)")
    args = ap.parse_args()

    final = fitz.open()
    toc, index = [], []
    for i, lesson in enumerate(LESSONS_ORDERED):
        part = render(lesson_html(i, lesson))
        start = final.page_count + 1
        final.insert_pdf(part)
        end = final.page_count
        toc.append([1, f"Aula {i + 1:02d}: {lesson.title}", start])
        index.append({"order": i + 1, "lesson_id": lesson.id, "module": MODULE_OF[lesson.id].id,
                      "title": lesson.title, "slug": f"curso-aula-{i + 1:02d}-{slugify(lesson.title)}",
                      "page_start": start, "page_end": end})
    final.set_toc(toc)
    final.set_metadata({"title": "Curso de educação financeira e investimentos", "author": "Simulador de Investimentos"})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    final.save(args.out, garbage=4, deflate=True)
    idx_path = args.index or args.out.with_suffix(".index.json")
    idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{args.out} · {final.page_count} páginas · {len(index)} aulas · índice em {idx_path}")


if __name__ == "__main__":
    main()
