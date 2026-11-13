"""Aulas: progresso por usuário e correção de quizzes (no servidor: as respostas certas só são
reveladas depois que o usuário envia a tentativa)."""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.content.course import LESSONS, LESSONS_ORDERED, MODULE_OF, MODULES, TOTAL_LESSONS
from backend.models import LessonProgress

PASS_SCORE = 67          # % de acertos para concluir a aula (2 de 3)
LEVELS = [(0, "Iniciante"), (15, "Aprendiz"), (40, "Investidor"), (75, "Especialista"), (100, "Mestre")]


class LearnError(Exception):
    pass


def _progress(db: Session, user_id: int) -> dict[str, LessonProgress]:
    return {p.lesson_id: p for p in db.scalars(select(LessonProgress).where(LessonProgress.user_id == user_id))}


def _level(percent: int) -> str:
    return [name for threshold, name in LEVELS if percent >= threshold][-1]


def overview(db: Session, user_id: int) -> dict:
    prog = _progress(db, user_id)
    done = {lid for lid, p in prog.items() if p.completed_at and lid in LESSONS}
    modules = []
    for m in MODULES:
        lessons = [{
            "id": l.id, "title": l.title, "minutes": l.minutes, "summary": l.summary, "completed": l.id in done,
            "best_score": prog[l.id].best_score if l.id in prog and prog[l.id].attempts else None,
        } for l in m.lessons]
        modules.append({"id": m.id, "title": m.title, "description": m.description, "level": m.level, "lessons": lessons,
                        "completed": sum(1 for x in lessons if x["completed"]), "total": len(lessons)})
    percent = round(100 * len(done) / TOTAL_LESSONS)
    points = sum(10 + prog[lid].best_score // 10 for lid in done)
    nxt = next((l.id for l in LESSONS_ORDERED if l.id not in done), None)
    return {"modules": modules, "completed": len(done), "total": TOTAL_LESSONS, "percent": percent,
            "points": points, "level": _level(percent), "next_lesson_id": nxt}


def get_lesson(db: Session, user_id: int, lesson_id: str) -> dict:
    lesson = LESSONS.get(lesson_id)
    if lesson is None:
        raise LearnError("Aula não encontrada")
    p = _progress(db, user_id).get(lesson_id)
    ids = [l.id for l in LESSONS_ORDERED]
    i = ids.index(lesson_id)
    module = MODULE_OF[lesson_id]
    return {
        "id": lesson.id, "module_id": module.id, "module_title": module.title, "title": lesson.title,
        "minutes": lesson.minutes, "blocks": [list(b) for b in lesson.blocks],
        "quiz": [{"text": q.text, "options": list(q.options)} for q in lesson.quiz],     # sem a resposta certa
        "completed": bool(p and p.completed_at), "best_score": p.best_score if p and p.attempts else None,
        "prev_id": ids[i - 1] if i > 0 else None, "next_id": ids[i + 1] if i + 1 < len(ids) else None,
    }


def submit_quiz(db: Session, user_id: int, lesson_id: str, answers: list[int]) -> dict:
    lesson = LESSONS.get(lesson_id)
    if lesson is None:
        raise LearnError("Aula não encontrada")
    if len(answers) != len(lesson.quiz):
        raise LearnError(f"Responda todas as {len(lesson.quiz)} perguntas")
    if any(not 0 <= a < len(q.options) for a, q in zip(answers, lesson.quiz, strict=True)):
        raise LearnError("Resposta inválida")
    results = [{"correct": a == q.correct, "correct_index": q.correct, "explanation": q.explanation}
               for a, q in zip(answers, lesson.quiz, strict=True)]
    score = round(100 * sum(r["correct"] for r in results) / len(results))
    passed = score >= PASS_SCORE

    p = db.scalar(select(LessonProgress).where(LessonProgress.user_id == user_id, LessonProgress.lesson_id == lesson_id)
                  .with_for_update())
    if p is None:
        p = LessonProgress(user_id=user_id, lesson_id=lesson_id, best_score=0, attempts=0)
        db.add(p)
    p.attempts += 1
    p.best_score = max(p.best_score, score)
    if passed and p.completed_at is None:
        p.completed_at = datetime.now(UTC)
    db.commit()

    ids = [l.id for l in LESSONS_ORDERED]
    i = ids.index(lesson_id)
    return {"score": score, "passed": passed, "pass_score": PASS_SCORE, "results": results,
            "completed": p.completed_at is not None, "next_lesson_id": ids[i + 1] if i + 1 < len(ids) else None,
            "overview": overview(db, user_id)}
