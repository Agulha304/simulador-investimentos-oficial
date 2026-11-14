import importlib.util
import sys
from pathlib import Path

import pytest

from backend.content.course import LESSONS_ORDERED


def _load(name):
    path = Path(__file__).resolve().parents[1] / "tools" / "video_course" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"vc_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


speech = _load("speech")


@pytest.mark.parametrize("n,words", [
    (0, "zero"), (1, "um"), (16, "dezesseis"), (20, "vinte"), (21, "vinte e um"), (99, "noventa e nove"),
    (100, "cem"), (101, "cento e um"), (116, "cento e dezesseis"), (200, "duzentos"), (999, "novecentos e noventa e nove"),
    (1000, "mil"), (1001, "mil e um"), (1200, "mil e duzentos"), (1310, "mil trezentos e dez"), (2000, "dois mil"),
    (2593, "dois mil quinhentos e noventa e três"), (3650, "três mil seiscentos e cinquenta"), (12000, "doze mil"),
    (18000, "dezoito mil"), (100000, "cem mil"), (250000, "duzentos e cinquenta mil"),
    (1000000, "um milhão"), (2500000, "dois milhões e quinhentos mil"), (1000001, "um milhão e um"),
    (1234567, "um milhão duzentos e trinta e quatro mil quinhentos e sessenta e sete"), (2026, "dois mil e vinte e seis"),
])
def test_number_words(n, words):
    assert speech.num_to_words(n) == words


@pytest.mark.parametrize("text,spoken", [
    ("R$ 1.200", "mil e duzentos reais"),
    ("R$ 1", "um real"),
    ("R$ 1.250,50", "mil duzentos e cinquenta reais e cinquenta centavos"),
    ("Sobra de R$ 350, ou 8,75% da renda.", "Sobra de trezentos e cinquenta reais, ou oito vírgula setenta e cinco por cento da renda."),
    ("20% do futuro", "vinte por cento do futuro"),
    ("a 0,8% ao mês", "a zero vírgula oito por cento ao mês"),
    ("0,05%", "zero vírgula zero cinco por cento"),
    ("regra 50-30-20", "regra cinquenta, trinta, vinte"),
    ("US$ 300 com o dólar a R$ 5,20", "trezentos dólares com o dólar a cinco reais e vinte centavos"),
    ("IPCA+ e CDI", "IPCA mais e cê dê i"),
    ("de 3 a 6 meses", "de três a seis meses"),
    ("um \"caixinha\" de “teste”", "um caixinha de teste"),
    ("1,5 vezes", "um vírgula cinco vezes"),
    ("−4,8%", "menos quatro vírgula oito por cento"),
    ("2.000 × 10% = R$ 200", "dois mil vezes dez por cento igual a duzentos reais"),
    ("12 ÷ 3", "doze dividido por três"),
    ("(1 − 4 × 0,25²) × 100", "(um menos quatro vezes zero vírgula vinte e cinco ao quadrado) vezes cem"),
    ("no 2º ano e o 1º lugar", "no segundo ano e o primeiro lugar"),
    ("O ETF IVVB11 replica o S&P 500", "O é tê éfe i vê vê bê onze replica o S e P quinhentos"),
    ("PETR4 e B3", "pê é tê érre quatro e bê três"),
    ("Nasdaq-100", "Nasdaq cem"),
    ("CDB, LCI e LCA", "cê dê bê, éle cê i e éle cê á"),
    ("IPCA e Selic", "IPCA e Selic"),
])
def test_speak_pt(text, spoken):
    assert speech.speak_pt(text) == spoken


def test_no_digits_or_symbols_survive_in_any_review_narration():
    """Tudo que a voz vai ler nas cenas de revisão deve estar por extenso."""
    for lesson in LESSONS_ORDERED:
        for q in lesson.quiz:
            said = speech.speak_pt(f"{q.text} Resposta: {q.options[q.correct]}. {q.explanation}")
            assert not any(ch.isdigit() for ch in said), (lesson.id, said)
            assert not any(sym in said for sym in ("R$", "US$", "%", "−", "≈", "×", "÷", "=")), (lesson.id, said)


# ------------------------------------------------------------------ cenas da série e remoção de repetições
series = _load("inject_series")


def _el(eid, kind="text", text="", items=None, query=""):
    return series.element(eid, kind, text=text, items=items, query=query)


def _sc(sid, elements, narrations_actions):
    beats = [series.beat(n, *a) for n, a in narrations_actions]
    return series.scene(sid, sid, "c", elements, beats)


def test_dedupe_removes_repeated_sentences_and_keeps_their_actions():
    a = _sc("a", [_el("e1"), _el("e2")], [
        ("Os gastos se dividem em três grupos. Para não ser pego de surpresa, divida os custos anuais por doze meses.", [("write", "e1")])])
    b = _sc("b", [_el("e1"), _el("e2")], [
        ("Para não ser pego de surpresa, divida os custos anuais por doze meses.", [("write", "e2")]),
        ("Isso evita sustos no meio do mês e deixa o planejamento mais realista.", [])])
    stats = series.dedupe_scenes([a, b])
    assert stats == {"sentences": 1, "elements": 0, "scenes": 0}
    assert [x["narration"] for x in b["beats"]] == ["Isso evita sustos no meio do mês e deixa o planejamento mais realista."]
    assert [(x["do"], x["target"]) for x in b["beats"][0]["actions"]] == [("write", "e2")]      # a ação não se perdeu


def test_dedupe_drops_scenes_left_empty_and_duplicate_elements():
    a = _sc("a", [_el("e1", text="Sobra = Rendas - Despesas"), _el("e2", text="Sobra = Rendas - Despesas"), _el("e3", "bullets", items=["x"])],
            [("A sobra do mês é a renda menos as despesas totais do período.", [("write", "e1"), ("write", "e2")])])
    b = _sc("b", [_el("e1")], [("A sobra do mês é a renda menos as despesas totais do período.", [("write", "e1")])])
    stats = series.dedupe_scenes(scenes := [a, b])
    assert stats == {"sentences": 1, "elements": 1, "scenes": 1} and [s["id"] for s in scenes] == ["a"]
    assert [e["id"] for e in a["elements"]] == ["e1", "e3"]
    assert [(x["do"], x["target"]) for x in a["beats"][0]["actions"]] == [("write", "e1")]        # e2 virou e1, sem repetir


def test_dedupe_is_conservative_with_short_or_different_sentences():
    a = _sc("a", [_el("e1")], [("Muito bem. Vamos adiante com calma e atenção ao orçamento.", [])])
    b = _sc("b", [_el("e1")], [("Muito bem. O orçamento mensal precisa de metas realistas para funcionar.", [])])
    assert series.dedupe_scenes([a, b])["sentences"] == 0


def test_series_scenes_are_consistent_for_every_lesson():
    from backend.content.course import MODULE_OF, TOTAL_LESSONS
    for i, lesson in enumerate(LESSONS_ORDERED):
        prev = LESSONS_ORDERED[i - 1] if i else None
        nxt = LESSONS_ORDERED[i + 1] if i + 1 < TOTAL_LESSONS else None
        scenes = [series.opening(i, lesson, prev, MODULE_OF[lesson.id]), series.review(lesson), series.closing(nxt)]
        for sc in scenes:
            ids = [e["id"] for e in sc["elements"]]
            assert len(ids) == len(set(ids)) and 2 <= len(ids) <= 4 and 2 <= len(sc["beats"]) <= 7, (lesson.id, sc["id"])
            for b in sc["beats"]:
                assert all(a["target"] in ids for a in b["actions"]), (lesson.id, sc["id"])
                assert not any(ch.isdigit() for ch in b["narration"]) and "%" not in b["narration"], (lesson.id, b["narration"])
            # todo elemento de tela é desenhado por alguma ação
            drawn = {a["target"] for b in sc["beats"] for a in b["actions"]}
            assert set(ids) <= drawn, (lesson.id, sc["id"], set(ids) - drawn)
        opening_text = " ".join(b["narration"] for b in scenes[0]["beats"])
        assert f"Aula {speech.num_to_words(i + 1)} de {speech.num_to_words(TOTAL_LESSONS)}" in opening_text
        assert [e["items"] for e in scenes[1]["elements"] if e["kind"] == "bullets"] == [[q.explanation for q in lesson.quiz]]
        assert ("Na próxima aula" in " ".join(b["narration"] for b in scenes[2]["beats"])) == (nxt is not None)


def test_fill_in_the_blank_questions_become_natural_sentences():
    from backend.content.course import LESSONS
    lines = [b["narration"] for b in series.review(LESSONS["m4-l1"])["beats"]]
    assert "O é tê éfe i vê vê bê onze replica o S e P quinhentos, negociado em reais." in lines
    assert not any("Resposta: o " in x or ": Resposta" in x for x in lines)
    lines = [b["narration"] for b in series.review(LESSONS["m3-l4"])["beats"]]
    assert any(x.startswith("Um P L de dez significa, aproximadamente que o preço") or "aproximadamente que o preço" in x for x in lines)
