"""Equipe das empresas (Empresas v2, fase 2): candidatos, propostas, headhunter, rescisão e risco de processo.

Tudo aqui é PURO e determinístico (sem banco, sem `random`): os sorteios usam `hash01` com a semente da partida, o id da
empresa, o mês, o cargo e o regime. O `id` do candidato é um token que descreve QUEM ele é (mês-cargo-regime-índice), então
o servidor sempre recalcula o candidato a partir do token: o cliente nunca informa pretensão, nível ou escolaridade.
"""
import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.core.money import quantize_money
from backend.models import EmployeeEducation, EmployeeLevel, EmployeeRegime, WorkSchedule
from backend.services import company_rules as rules
from backend.services.goods_rules import hash01

D = Decimal

# ------------------------------------------------------------------ parâmetros
CANDIDATES_MIN, CANDIDATES_SPAN = 4, 3          # 4 a 6 candidatos por consulta
HEADHUNTER_POOL = 12                            # o headhunter varre um universo maior, filtra e devolve até 3
HEADHUNTER_MAX = 3
HEADHUNTER_FEE_MONTHS = D("1.0")                # honorário = 1x o orçamento (salário-teto) informado no briefing
HEADHUNTER_EMPTY_FEE_FACTOR = D("0.5")          # sem candidato que sirva ao briefing: cobra metade
COMPETING_PROB = 0.30                           # chance (por candidato/mês) de ter proposta concorrente
COMPETING_PREMIUM = D("1.10")                   # concorrência exige +10% sobre a pretensão
PJ_ASKING_FACTOR = D("1.10")                    # PJ não tem encargos nem benefícios: pede ~10% a mais de salário
STANDARD_WEEK = 44                              # CLT: acima disso é hora extra
OVERTIME_PREMIUM = D("1.5")                     # prêmio proporcional às horas extras (50% a mais por hora)
HARD_WEEK = 52                                  # acima disso só aceita com pelo menos +40%
HARD_WEEK_MIN_PREMIUM = D("0.40")
MIN_WEEK, MAX_WEEK = 20, 70
COUNTER_FLOOR = D("0.80")                       # proposta de 80% a 100% da pretensão ajustada recebe contraproposta

SCHEDULE_FACTOR = {                             # 6x1 pede prêmio; 12x36 e 4x3 (mais folgas) aceitam desconto
    WorkSchedule.ESC_6X1: D("1.04"), WorkSchedule.ESC_5X2: D("1.00"),
    WorkSchedule.ESC_12X36: D("0.97"), WorkSchedule.ESC_4X3: D("0.95"),
}
SCHEDULE_HOURS = {WorkSchedule.ESC_6X1: 44, WorkSchedule.ESC_5X2: 40, WorkSchedule.ESC_12X36: 36, WorkSchedule.ESC_4X3: 40}
OFF_PREFERENCE = D("1.02")                      # escala diferente da preferida: +2%

LAWSUIT_BASE = {EmployeeRegime.CLT: 0.06, EmployeeRegime.PJ: 0.35}
LAWSUIT_LONG_HOURS = 1.5                        # jornada acima de 44 h/semana
LAWSUIT_6X1 = 1.2
LAWSUIT_TENURE_MAX = 0.5                        # até +50% com 5 anos de casa
LAWSUIT_CAP = 0.90

EDUCATION_ORDER = [EmployeeEducation.FUNDAMENTAL, EmployeeEducation.MEDIO, EmployeeEducation.TECNICO,
                   EmployeeEducation.SUPERIOR, EmployeeEducation.POS]
EDUCATION_LABEL = {EmployeeEducation.FUNDAMENTAL: "Fundamental", EmployeeEducation.MEDIO: "Médio",
                   EmployeeEducation.TECNICO: "Técnico", EmployeeEducation.SUPERIOR: "Superior", EmployeeEducation.POS: "Pós-graduação"}
LEVEL_ORDER = [EmployeeLevel.JUNIOR, EmployeeLevel.MID, EmployeeLevel.SENIOR]
LEVEL_LABEL = {EmployeeLevel.JUNIOR: "Júnior", EmployeeLevel.MID: "Pleno", EmployeeLevel.SENIOR: "Sênior"}

FIRST_NAMES = ("Ana", "Bruno", "Camila", "Diego", "Eduarda", "Felipe", "Gabriela", "Henrique", "Isabela", "João", "Karina", "Lucas",
               "Mariana", "Nicolas", "Olívia", "Pedro", "Quésia", "Rafael", "Sabrina", "Thiago", "Ursula", "Vinícius", "Wesley",
               "Yasmin", "Zeca", "Aline", "Bernardo", "Carla", "Daniel", "Elisa", "Fábio", "Giovana", "Hugo", "Letícia", "Marcos",
               "Natália", "Otávio", "Priscila", "Renato", "Tatiane")
LAST_NAMES = ("Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", "Pereira", "Lima", "Gomes", "Costa", "Ribeiro",
              "Martins", "Carvalho", "Almeida", "Lopes", "Soares", "Fernandes", "Vieira", "Barbosa", "Rocha", "Dias", "Nascimento",
              "Andrade", "Moreira", "Nunes", "Marques", "Machado", "Mendes", "Freitas", "Cardoso", "Ramos", "Teixeira", "Araújo",
              "Pinto", "Correia", "Monteiro", "Cavalcanti", "Barros", "Duarte")


# ------------------------------------------------------------------ candidatos

@dataclass(frozen=True)
class Candidate:
    id: str
    role: str
    regime: EmployeeRegime
    name: str
    education: EmployeeEducation
    experience_years: int
    level: EmployeeLevel
    asking_salary: Decimal
    hours_week: int
    schedule: WorkSchedule
    flex: float                 # quanto abaixo da pretensão (ajustada) ele aceita
    competing: bool             # tem proposta concorrente neste mês

    @property
    def productivity(self) -> Decimal:
        return rules.level_productivity(self.level)


def make_token(ref: date, role: str, regime: EmployeeRegime, idx: int, headhunter: bool = False) -> str:
    return f"{ref:%Y%m}-{role}-{regime.value}-{'h' if headhunter else 'c'}{idx}"


def parse_token(token: str) -> tuple[str, str, EmployeeRegime, bool, int]:
    """(AAAAMM, cargo, regime, via headhunter?, índice). Levanta ValueError se o token for inválido."""
    try:
        ym, role, regime, tail = token.split("-")
        if len(ym) != 6 or not ym.isdigit() or tail[0] not in "ch" or not tail[1:].isdigit():
            raise ValueError
        return ym, role, EmployeeRegime(regime), tail[0] == "h", int(tail[1:])
    except (ValueError, IndexError):
        raise ValueError("candidato inválido") from None


def visible_count(seed: int, company_id: int, ref: date, role: str, regime: EmployeeRegime) -> int:
    return CANDIDATES_MIN + int(hash01(seed, "cand-n", company_id, f"{ref:%Y-%m}", role, regime.value) * CANDIDATES_SPAN)


def _min_education(role: rules.Role) -> int:
    return 3 if role.salary >= D(6500) or role.key in ("accountant", "lawyer") else 0


def build_candidate(seed: int, company_id: int, ref: date, role: rules.Role, regime: EmployeeRegime, idx: int,
                    headhunter: bool = False) -> Candidate:
    def h(tag: str) -> float:
        return hash01(seed, "cand", tag, company_id, f"{ref:%Y-%m}", role.key, regime.value, "h" if headhunter else "c", idx)

    name = f"{FIRST_NAMES[int(h('fn') * len(FIRST_NAMES))]} {LAST_NAMES[int(h('ln') * len(LAST_NAMES))]}"
    exp = int(h("exp") ** 1.4 * 16)                                                  # 0..15 anos, mais gente com pouca experiência
    shift = 1.4 if role.salary >= D(4000) else 0.0 if role.salary >= D(2500) else -0.4     # cargos mais bem pagos pedem mais estudo
    edu_idx = max(_min_education(role), min(4, max(0, int(h("edu") * 4.2 + shift))))
    score = exp + 2 * edu_idx
    level = EmployeeLevel.JUNIOR if score < 6 else EmployeeLevel.MID if score < 12 else EmployeeLevel.SENIOR
    asking = role.salary * rules.LEVELS[level][0] * D(str(round(0.92 + 0.20 * h("var"), 4)))
    prefs = [WorkSchedule.ESC_5X2] * 9 + [WorkSchedule.ESC_6X1] * 5 + [WorkSchedule.ESC_12X36] * 3 + [WorkSchedule.ESC_4X3] * 3
    schedule = prefs[int(h("sch") * len(prefs))]
    hours = role.hours or SCHEDULE_HOURS[schedule]                          # cargos gerais do porte pequeno/médio: meio período
    asking *= rules.wage_hours_factor(hours)                               # salário proporcional à jornada
    if regime == EmployeeRegime.PJ:
        asking *= PJ_ASKING_FACTOR
    asking = D(int(round(float(asking) / 10.0)) * 10).quantize(D("0.01"))
    cid = make_token(ref, role.key, regime, idx, headhunter)
    return Candidate(
        id=cid, role=role.key, regime=regime, name=name, education=EDUCATION_ORDER[edu_idx], experience_years=exp, level=level,
        asking_salary=asking, hours_week=hours, schedule=schedule, flex=0.03 + 0.07 * h("flex"),
        competing=hash01(seed, "compete", company_id, f"{ref:%Y-%m}", cid) < COMPETING_PROB)


def candidates_for(seed: int, company_id: int, ref: date, role: rules.Role, regime: EmployeeRegime) -> list[Candidate]:
    n = visible_count(seed, company_id, ref, role.key, regime)
    return [build_candidate(seed, company_id, ref, role, regime, i) for i in range(n)]


def headhunter_search(seed: int, company_id: int, ref: date, role: rules.Role, regime: EmployeeRegime, max_salary: Decimal,
                      min_level: EmployeeLevel) -> list[Candidate]:
    """Até 3 candidatos do universo do headhunter que cumprem o briefing: pretensão <= teto, nível >= mínimo, regime pedido.
    Ordem: maior nível primeiro e, no empate, menor pretensão."""
    floor = LEVEL_ORDER.index(min_level)
    pool = [build_candidate(seed, company_id, ref, role, regime, i, headhunter=True) for i in range(HEADHUNTER_POOL)]
    ok = [c for c in pool if c.asking_salary <= max_salary and LEVEL_ORDER.index(c.level) >= floor]
    ok.sort(key=lambda c: (-LEVEL_ORDER.index(c.level), c.asking_salary, c.id))
    return ok[:HEADHUNTER_MAX]


def resolve_token(seed: int, company_id: int, ref: date, token: str, seg: rules.Segment,
                  size: rules.CompanySize = rules.CompanySize.SMALL) -> Candidate:
    """Recalcula o candidato a partir do token. ValueError se o token não for da empresa/mês atual ou não existir."""
    ym, role_key, regime, hh, idx = parse_token(token)
    if ym != f"{ref:%Y%m}":
        raise ValueError("a lista de candidatos é de outro mês: consulte novamente")
    try:
        role = seg.role_for(role_key, size)
    except KeyError:
        raise ValueError("cargo inexistente neste segmento") from None
    limit = HEADHUNTER_POOL if hh else visible_count(seed, company_id, ref, role_key, regime)
    if idx >= limit:
        raise ValueError("candidato inexistente")
    return build_candidate(seed, company_id, ref, role, regime, idx, headhunter=hh)


# ------------------------------------------------------------------ proposta

@dataclass(frozen=True)
class Offer:
    status: str                       # ACCEPTED | COUNTER | REFUSED
    message: str
    required: Decimal                 # salário mínimo que aceitaria (nas condições propostas)
    counter_offer: Decimal | None = None

    @property
    def accepted(self) -> bool:
        return self.status == "ACCEPTED"


def hours_factor(hours_week: int, base_hours: int = rules.FULL_TIME_HOURS) -> Decimal:
    """Fator da pretensão pela jornada, em relação à jornada em que a pretensão foi calculada (`base_hours`): meio período tem
    salário PROPORCIONAL (20 h = 55,6% do integral); de 36 a 44 h não muda; acima de 44 h há prêmio de hora extra."""
    ratio = rules.wage_hours_factor(hours_week) / rules.wage_hours_factor(base_hours)
    if hours_week <= STANDARD_WEEK:
        return ratio
    premium = D(hours_week - STANDARD_WEEK) / STANDARD_WEEK * OVERTIME_PREMIUM
    if hours_week > HARD_WEEK:
        premium = max(premium, HARD_WEEK_MIN_PREMIUM)
    return ratio * (1 + premium)


def schedule_factor(c: Candidate, schedule: WorkSchedule) -> Decimal:
    return SCHEDULE_FACTOR[schedule] * (OFF_PREFERENCE if schedule != c.schedule else D(1))


def adjusted_asking(c: Candidate, hours_week: int, schedule: WorkSchedule) -> Decimal:
    """Pretensão ajustada às condições (jornada, escala e concorrência), ANTES da folga de negociação do candidato."""
    comp = COMPETING_PREMIUM if c.competing else D(1)
    return c.asking_salary * hours_factor(hours_week, c.hours_week) * schedule_factor(c, schedule) * comp


def evaluate_offer(c: Candidate, salary: Decimal, hours_week: int, schedule: WorkSchedule) -> Offer:
    adjusted = adjusted_asking(c, hours_week, schedule)
    required = D(math.ceil(adjusted * D(str(1 - c.flex))))                              # reais inteiros, arredondando para cima
    if hours_week > HARD_WEEK:                                                           # regra dura: nunca abaixo de +40% da pretensão
        required = max(required, D(math.ceil(c.asking_salary * (1 + HARD_WEEK_MIN_PREMIUM))))
    if salary >= required:
        return Offer("ACCEPTED", f"{c.name} aceitou a proposta.", required)
    if c.regime == EmployeeRegime.PJ and salary >= c.asking_salary * hours_factor(hours_week, c.hours_week):
        return Offer("ACCEPTED", f"{c.name} aceitou: como PJ, o valor cobriu a pretensão.", required)
    if hours_week > HARD_WEEK and salary < c.asking_salary * (1 + HARD_WEEK_MIN_PREMIUM) * D("0.99"):
        why = f"jornada de {hours_week} h/semana só com pelo menos 40% a mais de salário"
    elif hours_week > STANDARD_WEEK and salary < c.asking_salary:
        why = f"a jornada de {hours_week} h/semana exige um prêmio proporcional"
    elif c.competing and salary < c.asking_salary * COMPETING_PREMIUM:
        why = "recebeu outra proposta e quer um valor maior"
    elif schedule == WorkSchedule.ESC_6X1 and salary < c.asking_salary * SCHEDULE_FACTOR[schedule]:
        why = "a escala 6x1 exige um prêmio"
    else:
        why = f"a pretensão era de {quantize_money(c.asking_salary)}"
    if salary / adjusted >= COUNTER_FLOOR:
        return Offer("COUNTER", f"{c.name} não aceitou ({why}), mas topa por {required}.", required, required)
    return Offer("REFUSED", f"{c.name} recusou: a proposta ficou muito abaixo ({why}). Não está mais disponível neste mês.", required)


# ------------------------------------------------------------------ cobertura, rescisão e processo

def monthly_cost(salary: Decimal, regime: EmployeeRegime) -> Decimal:
    return rules.payroll_cost(salary, regime)


def tenure_months(hired_on: date, ref: date) -> int:
    return max((ref.year - hired_on.year) * 12 + ref.month - hired_on.month, 0)


def severance(regime: EmployeeRegime, salary: Decimal, tenure: int) -> Decimal:
    """CLT: 1 salário de rescisão + aviso prévio (30 dias + 3 dias por ano de casa, máx. 90 dias = 1 a 3 salários).
    PJ: sem rescisão."""
    if regime == EmployeeRegime.PJ:
        return D("0.00")
    notice_months = min(D(3), 1 + D(tenure // 12) * D("0.1"))
    return quantize_money(salary * (rules.SEVERANCE_MONTHS + notice_months))


def lawsuit_probability(regime: EmployeeRegime, hours_week: int, schedule: WorkSchedule, tenure: int) -> float:
    """Chance de processo trabalhista depois de demitir. CLT ~6%, PJ ~35% (alegam vínculo); jornada > 44 h (x1.5),
    escala 6x1 (x1.2) e tempo de casa (até +50% com 5 anos) aumentam; teto de 90%."""
    p = LAWSUIT_BASE[regime]
    if hours_week > STANDARD_WEEK:
        p *= LAWSUIT_LONG_HOURS
    if schedule == WorkSchedule.ESC_6X1:
        p *= LAWSUIT_6X1
    p *= 1 + LAWSUIT_TENURE_MAX * min(tenure, 60) / 60
    return round(min(p, LAWSUIT_CAP), 4)
