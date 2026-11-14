"""Índice do curso: módulos e aulas, na ordem em que são exibidos (organização financeira vem antes de investir)."""
from backend.content import (
    m0_organizacao, m1_fundamentos, m2_renda_fixa, m3_acoes, m4_fundos, m5_cripto, m6_tecnica, m7_risco,
)

MODULES = [m.MODULE for m in (m0_organizacao, m1_fundamentos, m2_renda_fixa, m3_acoes, m4_fundos, m5_cripto, m6_tecnica, m7_risco)]
LESSONS_ORDERED = [lesson for module in MODULES for lesson in module.lessons]
LESSONS = {lesson.id: lesson for lesson in LESSONS_ORDERED}
MODULE_OF = {lesson.id: module for module in MODULES for lesson in module.lessons}
TOTAL_LESSONS = len(LESSONS_ORDERED)
