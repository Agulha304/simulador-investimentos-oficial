import re

import pytest

from backend.content.course import LESSONS, LESSONS_ORDERED, MODULES, TOTAL_LESSONS
from backend.services import learn_service

BLOCK_TYPES = {"h", "p", "ul", "tip", "warn", "formula", "table", "sim"}
APP_ROUTES = {"/mercado", "/renda-fixa", "/historico", "/desempenho", "/carteira", "/ranking", "/aulas"}


def right(lesson_id):
    return [q.correct for q in LESSONS[lesson_id].quiz]


def wrong(lesson_id):
    return [(q.correct + 1) % len(q.options) for q in LESSONS[lesson_id].quiz]


def submit(client, h, lesson_id, answers):
    return client.post(f"/api/learn/lessons/{lesson_id}/quiz", headers=h, json={"answers": answers})


# ------------------------------------------------------------------ integridade do conteúdo

def test_course_structure():
    assert TOTAL_LESSONS == 37 and len(MODULES) == 8
    ids = [l.id for l in LESSONS_ORDERED]
    assert len(ids) == len(set(ids)) and len({m.id for m in MODULES}) == len(MODULES)
    for m in MODULES:
        assert m.title and m.description and m.level in {"Iniciante", "Intermediário", "Avançado"} and m.lessons
        assert all(l.id.startswith(m.id + "-") for l in m.lessons)
    # as aulas citadas pelos insights do desempenho precisam existir
    assert {"m0-l1", "m1-l1", "m2-l2", "m7-l1", "m7-l2", "m7-l3"} <= set(ids) and ids[0] == "m0-l1"   # organização financeira abre o curso


def test_every_lesson_is_well_formed():
    for l in LESSONS_ORDERED:
        assert l.title and l.summary and 3 <= l.minutes <= 15, l.id
        assert len(l.blocks) >= 4 and any(b[0] == "p" for b in l.blocks), l.id
        assert any(b[0] == "warn" for b in l.blocks), f"{l.id}: falta o aviso educacional"
        for b in l.blocks:
            kind = b[0]
            assert kind in BLOCK_TYPES, (l.id, kind)
            if kind in {"h", "p", "tip", "warn", "formula"}:
                assert isinstance(b[1], str) and len(b[1]) >= (2 if kind == "h" else 6), (l.id, b)   # títulos podem ser curtos ("FGC")
            if kind == "ul":
                assert b[1] and all(isinstance(i, str) and i for i in b[1]), (l.id, b)
            if kind == "table":
                headers, rows = b[1], b[2]
                assert rows and all(len(r) == len(headers) for r in rows), (l.id, b)
            if kind == "sim":
                assert b[1] in APP_ROUTES and b[2], (l.id, b)
            for text in ([b[1]] if isinstance(b[1], str) else []):
                assert text.count("**") % 2 == 0, f"{l.id}: negrito não fechado"


def test_every_quiz_is_valid():
    positions, seen = [], set()
    for l in LESSONS_ORDERED:
        assert len(l.quiz) == 3, l.id
        for q in l.quiz:
            assert len(q.options) == 4 and len(set(q.options)) == 4, (l.id, q.text)
            assert 0 <= q.correct < 4 and q.text.strip().endswith((":", "?")) and len(q.explanation) > 10, (l.id, q.text)
            assert q.text not in seen, f"pergunta repetida: {q.text}"
            seen.add(q.text)
            positions.append(q.correct)
    assert set(positions) == {0, 1, 2, 3}                                  # a resposta certa não é sempre a mesma posição
    assert max(positions.count(i) for i in range(4)) / len(positions) < 0.4


def test_no_leftover_placeholders():
    text = " ".join(str(b) for l in LESSONS_ORDERED for b in l.blocks)
    assert not re.search(r"\bTODO\b|XXX|(?i:lorem ipsum)|\?\?", text)      # só marcadores; "Todo" em português é normal


# ------------------------------------------------------------------ API

def test_requires_auth(client):
    assert client.get("/api/learn").status_code == 401
    assert client.get("/api/learn/lessons/m1-l1").status_code == 401
    assert client.post("/api/learn/lessons/m1-l1/quiz", json={"answers": [0, 0, 0]}).status_code == 401


def test_overview_starts_empty(client, auth_headers):
    o = client.get("/api/learn", headers=auth_headers).json()
    assert (o["completed"], o["percent"], o["points"], o["level"], o["next_lesson_id"]) == (0, 0, 0, "Iniciante", "m0-l1")
    assert o["total"] == TOTAL_LESSONS and len(o["modules"]) == len(MODULES)
    assert all(not l["completed"] and l["best_score"] is None for m in o["modules"] for l in m["lessons"])


def test_lesson_payload_never_leaks_answers(client, auth_headers):
    r = client.get("/api/learn/lessons/m2-l3", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["prev_id"] == "m2-l2" and body["next_id"] == "m2-l4" and body["module_title"] == "Renda fixa"
    assert len(body["quiz"]) == 3 and all(set(q) == {"text", "options"} for q in body["quiz"])
    assert "correct" not in r.text and "explanation" not in r.text
    assert client.get("/api/learn/lessons/m0-l1", headers=auth_headers).json()["prev_id"] is None
    assert client.get(f"/api/learn/lessons/{LESSONS_ORDERED[-1].id}", headers=auth_headers).json()["next_id"] is None
    assert client.get("/api/learn/lessons/nao-existe", headers=auth_headers).status_code == 404


def test_quiz_validation(client, auth_headers):
    assert submit(client, auth_headers, "nao-existe", [0, 0, 0]).status_code == 404
    assert submit(client, auth_headers, "m1-l1", [0, 0]).status_code == 422          # faltou responder
    assert submit(client, auth_headers, "m1-l1", [0, 0, 9]).status_code == 422       # opção inexistente
    assert submit(client, auth_headers, "m1-l1", [0, 0, -1]).status_code == 422
    assert client.get("/api/learn", headers=auth_headers).json()["completed"] == 0   # nada foi registrado


def test_failing_then_passing_a_lesson(client, auth_headers):
    r = submit(client, auth_headers, "m1-l1", wrong("m1-l1"))
    assert r.status_code == 200
    res = r.json()
    assert res["score"] == 0 and res["passed"] is False and res["completed"] is False
    assert [x["correct_index"] for x in res["results"]] == right("m1-l1") and all(x["explanation"] for x in res["results"])
    assert not any(x["correct"] for x in res["results"])
    lesson = client.get("/api/learn/lessons/m1-l1", headers=auth_headers).json()
    assert lesson["completed"] is False and lesson["best_score"] == 0

    res = submit(client, auth_headers, "m1-l1", right("m1-l1")).json()
    assert res["score"] == 100 and res["passed"] and res["completed"] and res["next_lesson_id"] == "m1-l2"
    assert res["overview"]["completed"] == 1 and res["overview"]["points"] == 20 and res["overview"]["next_lesson_id"] == "m0-l1"   # 1ª ainda pendente

    res = submit(client, auth_headers, "m1-l1", wrong("m1-l1")).json()               # pior tentativa depois: não desfaz
    assert res["score"] == 0 and res["completed"] is True
    lesson = client.get("/api/learn/lessons/m1-l1", headers=auth_headers).json()
    assert lesson["completed"] and lesson["best_score"] == 100
    o = client.get("/api/learn", headers=auth_headers).json()
    m1 = next(m for m in o["modules"] if m["id"] == "m1")
    assert o["completed"] == 1 and m1["completed"] == 1 and m1["lessons"][0]["best_score"] == 100


def test_two_of_three_is_enough(client, auth_headers):
    answers = right("m1-l2")
    answers[0] = (answers[0] + 1) % 4
    res = submit(client, auth_headers, "m1-l2", answers).json()
    assert res["score"] == 67 and res["passed"] and res["completed"]
    answers[1] = (answers[1] + 1) % 4                                                 # 1 de 3
    assert submit(client, auth_headers, "m1-l3", [(a + 1) % 4 for a in right("m1-l3")]).json()["passed"] is False


def test_progress_is_per_user_and_levels_up(client, auth_headers, db):
    other = client.post("/api/auth/register", json={"email": "o@example.com", "name": "O", "password": "segredo123"}).json()
    h2 = {"Authorization": f"Bearer {other['access_token']}"}
    submit(client, auth_headers, "m1-l1", right("m1-l1"))
    assert client.get("/api/learn", headers=h2).json()["completed"] == 0

    for l in LESSONS_ORDERED:
        submit(client, auth_headers, l.id, right(l.id))
    o = client.get("/api/learn", headers=auth_headers).json()
    assert (o["completed"], o["percent"], o["level"], o["next_lesson_id"]) == (TOTAL_LESSONS, 100, "Mestre", None)
    assert o["points"] == 20 * TOTAL_LESSONS
    assert [m["completed"] for m in o["modules"]] == [m["total"] for m in o["modules"]]
    assert learn_service._level(14) == "Iniciante" and learn_service._level(15) == "Aprendiz" and learn_service._level(75) == "Especialista"
