"""Insere no roteiro de uma aula as cenas que ligam a série: abertura, revisão (com as perguntas do quiz) e próxima aula.

O roteirista do livro2video resume o texto como um livro; ele não conhece a série. Estas cenas são texto NOSSO,
determinístico e sem invenção (vêm do conteúdo da aula). Roda com o Python do livro2video (usa o esquema dele):

  PYTHONPATH=<gerador>/src:<raiz do simulador> <gerador>/.venv/bin/python tools/video_course/inject_series.py \
      --work <gerador>/work/<trabalho> --lesson-id m0-l1
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from speech import num_to_words, speak_pt  # noqa: E402

from backend.content.course import LESSONS_ORDERED, MODULE_OF, TOTAL_LESSONS  # noqa: E402

WPM = 140.0
MARK = "serie_"                      # prefixo do id das cenas inseridas (evita inserir duas vezes)


def element(eid: str, kind: str, text: str = "", query: str = "", items: list[str] | None = None) -> dict:
    return {"id": eid, "kind": kind, "text": text, "query": query, "latex": "", "items": items or [], "values": [],
            "labels": [], "chart": "", "ref": "", "complement": False, "figure": ""}


def beat(narration: str, *actions: tuple[str, str]) -> dict:
    return {"narration": narration, "actions": [{"do": d, "target": t, "to": "", "text": ""} for d, t in actions],
            "complement": False}


def scene(sid: str, title: str, concept: str, elements: list[dict], beats: list[dict]) -> dict:
    words = sum(len(b["narration"].split()) for b in beats)
    return {"id": sid, "index": 0, "topic": title, "title": title, "concept": concept, "keywords": [],
            "composition": "", "elements": elements, "beats": beats, "complement": False, "source_pages": [],
            "difficulty": 1.5, "est_duration": round(words / WPM * 60 + 2 * len(beats), 1), "words": words,
            "timings": [], "duration": 0.0, "visuals": {}}


def opening(i: int, lesson, prev, module) -> dict:
    """Os desenhos acompanham falas longas: o gerador estende a cena até o desenho acabar, e uma fala curta
    sobre um desenho demorado vira silêncio (a mão desenhando sem ninguém falar)."""
    n, total = i + 1, TOTAL_LESSONS
    head = f"Curso de educação financeira e investimentos. Aula {num_to_words(n)} de {num_to_words(total)}."
    if prev is None:
        link = "Ao longo da série, você vai organizar o seu dinheiro e aprender a investir, passo a passo."
    else:
        prev_mod = MODULE_OF[prev.id]
        link = (speak_pt(f"Na aula anterior, você viu: {prev.title}.") if prev_mod.id == module.id
                else speak_pt(f"Você concluiu o módulo {prev_mod.title}. Agora começa um novo módulo: {module.title}."))
    beats = [beat(f"{head} {link}", ("draw", "e1"), ("write", "e2"))]
    if prev is None:
        beats.append(beat("Este conteúdo é educacional e não é recomendação de investimento."))
    beats.append(beat(speak_pt(f"Hoje, o tema é: {lesson.title}. {lesson.summary}"), ("write", "e3")))
    return scene(f"cena000_{MARK}abertura", f"Aula {n} de {total}", f"Abertura da aula {n}: {lesson.title}",
                 [element("e1", "illustration", query="book"), element("e2", "keyword", text=module.title),
                  element("e3", "text", text=lesson.title)], beats)


def _question_line(q) -> str:
    answer = q.options[q.correct]
    if q.text.endswith(":"):                                          # pergunta de completar: vira uma frase natural
        first = answer.split()[0]
        if not (first.isupper() and len(first) > 1):                  # mantém siglas (CDB); "Que..." vira "que..."
            answer = answer[0].lower() + answer[1:]
        return speak_pt(f"{q.text[:-1]} {answer}.")
    return speak_pt(f"{q.text} Resposta: {answer}.")


def review(lesson) -> dict:
    items = [q.explanation for q in lesson.quiz]                     # frases completas: fazem sentido sozinhas na tela
    lines = [_question_line(q) for q in lesson.quiz]
    beats = [beat(f"Para fixar o que você aprendeu, vamos revisar três perguntas. {lines[0]}", ("draw", "e1"), ("write", "e2")),
             beat(lines[1], ("write", "e3")), beat(lines[2]),
             beat("Agora, responda ao quiz desta aula no site para registrar o seu progresso.")]
    return scene(f"cena900_{MARK}revisao", "Revisão", f"Revisão da aula: {lesson.title}",
                 [element("e1", "illustration", query="checklist"), element("e2", "keyword", text="Para fixar"),
                  element("e3", "bullets", items=items)], beats)


def closing(nxt) -> dict:
    if nxt is None:
        beats = [beat("Esta foi a última aula da série. Pratique no simulador, revise as aulas quando precisar e invista "
                      "com calma e com método. Obrigado por assistir!", ("draw", "e1"), ("write", "e2"))]
        elements = [element("e1", "illustration", query="trophy"), element("e2", "keyword", text="Fim da série")]
    else:
        beats = [beat(speak_pt(f"Na próxima aula: {nxt.title}. {nxt.summary} Até lá!"),
                      ("draw", "e1"), ("write", "e2"), ("write", "e3"))]
        elements = [element("e1", "illustration", query="rocket"), element("e2", "keyword", text="Próxima aula"),
                    element("e3", "text", text=nxt.title)]
    return scene(f"cena901_{MARK}proxima", "Próxima aula", "Ligação com a próxima aula da série", elements, beats)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zà-ú0-9]+", text.lower()))


def _sentences(text: str) -> list[str]:
    return [x for x in re.split(r"(?<=[.!?])\s+", text.strip()) if x]


def dedupe_scenes(scenes: list[dict], threshold: float = 0.7, min_tokens: int = 5) -> dict:
    """Tira do roteiro do LLM o que ele repete: frases (quase) idênticas a uma já dita em cena anterior e
    elementos duplicados na mesma cena. As ações de uma fala removida passam para a fala vizinha, para nada
    deixar de ser desenhado. Conservador: só remove sentenças com Jaccard >= `threshold`."""
    seen: list[set[str]] = []
    stats = {"sentences": 0, "elements": 0, "scenes": 0}
    for sc in scenes:
        # elementos duplicados (mesmo tipo, texto e itens) -> mantém o primeiro, redireciona as ações
        kept: dict[tuple, str] = {}
        remap: dict[str, str] = {}
        elements = []
        for el in sc["elements"]:
            key = (el["kind"], el["text"].strip().lower(), tuple(x.strip().lower() for x in el["items"]), el["query"])
            if key in kept and (el["text"] or el["items"]):
                remap[el["id"]] = kept[key]
                stats["elements"] += 1
                continue
            kept[key] = el["id"]
            elements.append(el)
        sc["elements"] = elements

        beats, carry = [], []
        for b in sc["beats"]:
            for a in b["actions"]:
                a["target"] = remap.get(a["target"], a["target"])
                a["to"] = remap.get(a["to"], a["to"])
            keep = []
            for sent in _sentences(b["narration"]):
                toks = _tokens(sent)
                if len(toks) >= min_tokens and any(len(toks & t) / len(toks | t) >= threshold for t in seen):
                    stats["sentences"] += 1
                    continue
                keep.append(sent)
                if len(toks) >= min_tokens:
                    seen.append(toks)
            if keep:
                b["narration"] = " ".join(keep)
                b["actions"] = carry + b["actions"]
                carry = []
                beats.append(b)
            else:
                carry += b["actions"]
        if beats:
            beats[-1]["actions"] += carry
        seen_actions, deduped = set(), []
        for b in beats:                                              # a mesma ação não se repete na cena
            b["actions"] = [a for a in b["actions"] if (a["do"], a["target"], a["to"]) not in seen_actions
                            and not seen_actions.add((a["do"], a["target"], a["to"]))]
            deduped.append(b)
        sc["beats"] = deduped
        words = sum(len(b["narration"].split()) for b in deduped)
        sc["words"], sc["est_duration"] = words, round(words / WPM * 60 + 2 * len(deduped), 1)
    before = len(scenes)
    scenes[:] = [sc for sc in scenes if sc["beats"]]
    stats["scenes"] = before - len(scenes)
    return stats


def inject(work: Path, lesson_id: str, replace: bool = False) -> dict:
    from livro2video.script.schema import Script
    from livro2video.utils import atomic_write_text, read_json, write_json
    from livro2video.pipeline import script_markdown

    i = next(k for k, l in enumerate(LESSONS_ORDERED) if l.id == lesson_id)
    lesson = LESSONS_ORDERED[i]
    prev = LESSONS_ORDERED[i - 1] if i > 0 else None
    nxt = LESSONS_ORDERED[i + 1] if i + 1 < TOTAL_LESSONS else None

    path = work / "roteiro.json"
    data = read_json(path)
    had_series = any(MARK in s["id"] for s in data["scenes"])
    if had_series and not replace:
        return {"inserted": False, "scenes": len(data["scenes"])}                    # idempotente
    data["scenes"] = [s for s in data["scenes"] if MARK not in s["id"]]              # (replace) tira as da série antiga
    removed = dedupe_scenes(data["scenes"])
    scenes = [opening(i, lesson, prev, MODULE_OF[lesson.id])] + data["scenes"] + [review(lesson), closing(nxt)]
    for k, s in enumerate(scenes):
        s["index"] = k
    data["scenes"] = scenes
    data["title"] = f"Aula {i + 1:02d}: {lesson.title}"
    script = Script.model_validate(data)                                             # valida com o esquema do gerador
    write_json(path, script.model_dump())
    atomic_write_text(work / "roteiro.md", script_markdown(script))
    return {"inserted": True, "scenes": len(scenes), "removed": removed,
            "minutes": round(sum(s.est_duration for s in script.scenes) / 60, 1)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True, type=Path)
    ap.add_argument("--lesson-id", required=True)
    ap.add_argument("--replace", action="store_true", help="troca as cenas da série já inseridas")
    a = ap.parse_args()
    print(inject(a.work, a.lesson_id, replace=a.replace))
