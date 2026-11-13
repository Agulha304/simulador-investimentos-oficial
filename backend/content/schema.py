"""Estruturas do conteúdo das aulas.

Blocos de texto (tuplas): ("h", título) ("p", texto) ("ul", [itens]) ("tip", texto) ("warn", texto)
("formula", texto) ("table", [cabeçalhos], [[linha], ...]) ("sim", "/rota", "rótulo do botão").
Dentro de textos, **negrito** é suportado.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    text: str
    options: tuple[str, ...]
    correct: int
    explanation: str


@dataclass(frozen=True)
class Lesson:
    id: str
    title: str
    minutes: int
    summary: str
    blocks: tuple
    quiz: tuple[Question, ...]


@dataclass(frozen=True)
class Module:
    id: str
    title: str
    description: str
    level: str
    lessons: tuple[Lesson, ...]


def Q(text: str, options: list[str], correct: int, explanation: str) -> Question:  # noqa: N802
    return Question(text, tuple(options), correct, explanation)
