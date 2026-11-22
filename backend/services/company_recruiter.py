"""Contratador (headhunter) das empresas: níveis, taxas, briefing e seleção de candidatos/fornecedores. PURO e determinístico.

Nada aqui toca o banco: os sorteios usam `hash01` com a semente da partida, a empresa, o mês e o nível. A orquestração (cobrança, contratos,
funcionários) está em `company_recruiter_service`.

Decisões (ver docs/EMPRESAS_V2.md, "Contratador"):
  * Níveis BASIC/PRO/ELITE definem: quantas pessoas ele avalia por vaga (6/12/24) e quantas ofertas por categoria de fornecedor (6/12/24),
    a chance de CADA uma ser encontrada (0,60/0,80/0,95), o desconto de negociação (0/3/6%) e a taxa de sucesso da negociação
    (0,80/0,90/0,97). Quanto melhor o nível, mais opções visíveis => o melhor custo-benefício encontrado é melhor e mais vagas são preenchidas.
  * Custo-benefício do funcionário = produtividade (nível x jornada/40, no máx. 1) / custo mensal REAL (CLT 2x, PJ 1x).
  * O contratador propõe SEMPRE o menor salário que o candidato aceita (`company_team.min_acceptable`), nunca acima do teto do briefing.
  * O desconto entra na avaliação como `extra_flex` (candidato) ou `extra_discount` (fornecedor): só baixa o MÍNIMO aceito; recusa,
    contraproposta e demais regras continuam as do fluxo manual, e a proposta é sempre validada pela mesma função de avaliação.
"""
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal

from backend.core.money import quantize_money
from backend.models import CompanySize, EmployeeRegime, WorkSchedule
from backend.services import company_rules as rules
from backend.services import company_supply as supply
from backend.services import company_team as team
from backend.services.goods_rules import hash01

D = Decimal
CLT, PJ = EmployeeRegime.CLT, EmployeeRegime.PJ


@dataclass(frozen=True)
class Tier:
    key: str
    label: str
    fee: Decimal              # taxa mensal (porte pequeno)
    commission: Decimal       # x o salário contratado, por contratação (substitui o custo de recrutamento de meio salário)
    pool: int                 # pessoas avaliadas por vaga
    offers: int               # ofertas avaliadas por categoria de fornecedor
    find_chance: float        # chance de cada pessoa/oferta do universo ser encontrada
    discount: float           # desconto de negociação (folga extra do candidato / do fornecedor)
    success: float            # chance de a negociação com o escolhido dar certo


TIERS = {
    "BASIC": Tier("BASIC", "Básico", D(900), D("0.25"), 6, 6, 0.60, 0.00, 0.80),
    "PRO": Tier("PRO", "Profissional", D(2200), D("0.20"), 12, 12, 0.80, 0.03, 0.90),
    "ELITE": Tier("ELITE", "Elite", D(4800), D("0.15"), 24, 24, 0.95, 0.06, 0.97),
}
FEE_SIZE_MULT = {CompanySize.SMALL: D(1), CompanySize.MEDIUM: D("1.6"), CompanySize.LARGE: D("2.6")}
POLICIES = ("CLT_ONLY", "PJ_ONLY", "BOTH")
POLICY_LABEL = {"CLT_ONLY": "Só CLT", "PJ_ONLY": "Só PJ", "BOTH": "CLT e PJ"}
BRIEFING_MAX_HOURS = 44
MAX_SALARY_LIMIT = D(1_000_000)
MAX_LEAD_LIMIT = 60
NEG_SUPPLY_LOSS = 2.0       # penalização da falha de entrega no custo-benefício do fornecedor: preço x (1 + 2 x (1 - confiabilidade))


def tier_of(key: str) -> Tier:
    try:
        return TIERS[key]
    except KeyError:
        raise ValueError("nível de contratador inexistente (BASIC, PRO ou ELITE)") from None


def monthly_fee(tier: str, size: CompanySize) -> Decimal:
    return quantize_money(tier_of(tier).fee * FEE_SIZE_MULT[size])


def commission(tier: str, salary: Decimal) -> Decimal:
    return quantize_money(salary * tier_of(tier).commission)


# ------------------------------------------------------------------ briefing

@dataclass(frozen=True)
class Limits:
    """Critérios de um fornecedor/categoria (None = sem critério)."""
    max_spend: Decimal | None = None
    min_reliability: float | None = None
    max_lead_days: int | None = None
    volume_cap: Decimal | None = None


@dataclass(frozen=True)
class Settings:
    max_salary: Decimal | None = None
    schedule: WorkSchedule = WorkSchedule.ESC_5X2
    hours_week: int = 40
    regime_policy: str = "BOTH"
    max_monthly_payroll: Decimal | None = None
    supplier_max_total_spend: Decimal | None = None
    general: Limits = field(default_factory=Limits)                   # confiabilidade/prazo/volume gerais (max_spend geral = total)
    overrides: dict[str, Limits] = field(default_factory=dict)

    def limits_for(self, category: str) -> Limits:
        """Critérios da categoria: o override (campo a campo) prevalece sobre o geral."""
        o = self.overrides.get(category)
        g = self.general
        if o is None:
            return g
        return Limits(max_spend=o.max_spend, min_reliability=o.min_reliability if o.min_reliability is not None else g.min_reliability,
                      max_lead_days=o.max_lead_days if o.max_lead_days is not None else g.max_lead_days,
                      volume_cap=o.volume_cap if o.volume_cap is not None else g.volume_cap)


def _dec(v) -> Decimal | None:
    return None if v is None else D(str(v))


def _pos(v, name: str, top: Decimal | None = None) -> Decimal | None:
    if v is None:
        return None
    d = D(str(v))
    if d <= 0 or (top is not None and d > top):
        raise ValueError(f"{name} deve ser maior que zero" + (f" e no máximo {top}" if top is not None else ""))
    return d


def _rel(v, name: str) -> float | None:
    if v is None:
        return None
    f = float(v)
    if not 0 < f <= 1:
        raise ValueError(f"{name} deve ficar entre 0 e 1 (ex.: 0,9 = 90%)")
    return round(f, 3)


def _lead(v, name: str) -> int | None:
    if v is None:
        return None
    if not 1 <= int(v) <= MAX_LEAD_LIMIT:
        raise ValueError(f"{name} deve ficar entre 1 e {MAX_LEAD_LIMIT} dias")
    return int(v)


def build_settings(raw: dict, categories: set[str]) -> Settings:
    """Valida o briefing (ValueError com mensagem em português se algo estiver fora do intervalo)."""
    try:
        schedule = WorkSchedule(raw.get("schedule") or "5x2")
    except ValueError:
        raise ValueError("escala inválida: use 6x1, 5x2, 12x36 ou 4x3") from None
    hours = int(raw.get("hours_week") or team.SCHEDULE_HOURS[schedule])
    if not team.MIN_WEEK <= hours <= BRIEFING_MAX_HOURS:
        raise ValueError(f"a jornada padrão deve ficar entre {team.MIN_WEEK} e {BRIEFING_MAX_HOURS} horas por semana (nunca acima de 48)")
    policy = raw.get("regime_policy") or "BOTH"
    if policy not in POLICIES:
        raise ValueError("regime inválido: use CLT_ONLY, PJ_ONLY ou BOTH")
    overrides = {}
    for cat, o in (raw.get("supplier_overrides") or {}).items():
        if cat not in categories:
            raise ValueError(f"categoria de fornecimento inexistente neste segmento: {cat}")
        o = o or {}
        overrides[cat] = Limits(_pos(o.get("max_spend"), "o gasto máximo da categoria"), _rel(o.get("min_reliability"), "a confiabilidade mínima"),
                                _lead(o.get("max_lead_days"), "o prazo máximo"), _pos(o.get("volume_cap"), "o volume máximo"))
    return Settings(
        max_salary=_pos(raw.get("max_salary"), "o salário máximo", MAX_SALARY_LIMIT), schedule=schedule, hours_week=hours, regime_policy=policy,
        max_monthly_payroll=_pos(raw.get("max_monthly_payroll"), "o teto de folha extra"),
        supplier_max_total_spend=_pos(raw.get("supplier_max_total_spend"), "o gasto máximo com fornecedores"),
        general=Limits(None, _rel(raw.get("supplier_min_reliability"), "a confiabilidade mínima"),
                       _lead(raw.get("supplier_max_lead_days"), "o prazo máximo"), _pos(raw.get("supplier_volume_cap"), "o volume máximo")),
        overrides=overrides)


def settings_to_json(st: Settings) -> dict:
    def s(v):
        return None if v is None else str(v)
    return {"max_salary": s(st.max_salary), "schedule": st.schedule.value, "hours_week": st.hours_week, "regime_policy": st.regime_policy,
            "max_monthly_payroll": s(st.max_monthly_payroll), "supplier_max_total_spend": s(st.supplier_max_total_spend),
            "supplier_min_reliability": st.general.min_reliability, "supplier_max_lead_days": st.general.max_lead_days,
            "supplier_volume_cap": s(st.general.volume_cap),
            "supplier_overrides": {k: {"max_spend": s(v.max_spend), "min_reliability": v.min_reliability, "max_lead_days": v.max_lead_days,
                                       "volume_cap": s(v.volume_cap)} for k, v in st.overrides.items()}}


def settings_from_json(raw: dict | None, categories: set[str]) -> Settings:
    try:
        return build_settings(raw or {}, categories)
    except ValueError:                       # briefing salvo antes de uma mudança de regra: volta ao padrão em vez de quebrar a empresa
        return Settings()


# ------------------------------------------------------------------ pessoas

def person_pool(seed: int, company_id: int, ref: date, role: rules.Role, tier: str) -> list[team.Candidate]:
    """Pessoas do universo do contratador para a vaga que ELE encontrou (cada uma com chance `find_chance`), em ordem de índice.
    A pessoa ainda não tem regime: nasce com a pretensão CLT e `as_regime` converte para PJ (+10%)."""
    t = tier_of(tier)
    out = []
    for i in range(t.pool):
        p = team.build_candidate(seed, company_id, ref, role, CLT, i, "r")
        if hash01(seed, "rec-vis", company_id, f"{ref:%Y-%m}", tier, p.id) < t.find_chance:
            out.append(p)
    return out


def as_regime(p: team.Candidate, regime: EmployeeRegime) -> team.Candidate:
    if regime == CLT:
        return p
    asking = D(int(round(float(p.asking_salary * team.PJ_ASKING_FACTOR) / 10.0)) * 10).quantize(D("0.01"))
    return replace(p, regime=PJ, asking_salary=asking, id=p.id.replace("-CLT-", "-PJ-"))


@dataclass(frozen=True)
class Plan:
    person: team.Candidate            # já no regime escolhido
    salary: Decimal                   # a MENOR proposta aceita
    hours_week: int
    schedule: WorkSchedule
    monthly_cost: Decimal
    score: float                      # produtividade esperada / custo mensal
    why: str                          # por que este regime
    key: str                          # chave da PESSOA (para bloquear): independe do regime


def plan_for(person: team.Candidate, regime: EmployeeRegime, hours: int, schedule: WorkSchedule, tier: str,
             max_salary: Decimal) -> Plan | str:
    c = as_regime(person, regime)
    extra = tier_of(tier).discount
    salary = team.min_acceptable(c, hours, schedule, extra)
    if not team.evaluate_offer(c, salary, hours, schedule, extra).accepted:      # defesa: nunca propor algo que a avaliação não aceite
        return f"{person.name} não aceita nenhuma proposta nestas condições"
    if salary > max_salary:
        return f"{person.name} ({regime.value}) aceita no mínimo R$ {salary}, acima do teto de R$ {max_salary}"
    cost = rules.payroll_cost(salary, regime)
    score = float(c.productivity) * min(1.0, hours / 40) / float(cost)
    return Plan(c, salary, hours, schedule, cost, score, "", person.id)


def choose_plan(person: team.Candidate, policy: str, hours_options: list[int], schedule: WorkSchedule, tier: str, max_salary: Decimal,
                cost_limit: Decimal | None = None) -> Plan | str:
    """Regime e jornada de UMA pessoa. CLT_ONLY/PJ_ONLY: o pedido. BOTH: com histórico de processos => CLT (menor risco de vínculo/ação);
    sem histórico => PJ (mais barato) e, se o PJ não couber no teto de salário ou no orçamento de folha, cai para CLT. Entre as jornadas
    possíveis escolhe a de menor custo."""
    if policy == "CLT_ONLY":
        order = [(CLT, "somente CLT")]
    elif policy == "PJ_ONLY":
        order = [(PJ, "somente PJ")]
    elif person.lawsuit_history > 0:
        n = person.lawsuit_history
        order = [(CLT, f"CLT: {n} processo(s) trabalhista(s) anterior(es)")]
    else:
        order = [(PJ, "PJ: sem histórico de processos (mais barato)"), (CLT, "CLT: o PJ não coube no teto/orçamento")]
    last = "sem opção"
    for regime, why in order:
        options = []
        for h in hours_options:
            p = plan_for(person, regime, h, schedule, tier, max_salary)
            if isinstance(p, str):
                last = p
            elif cost_limit is not None and p.monthly_cost > cost_limit:
                last = f"{person.name} ({regime.value}) custaria R$ {p.monthly_cost}/mês, acima do orçamento de folha restante (R$ {cost_limit})"
            else:
                options.append(replace(p, why=why))
        if options:
            return min(options, key=lambda x: (x.monthly_cost, x.hours_week))
    return last


def ranked_plans(seed: int, company_id: int, ref: date, role: rules.Role, tier: str, cfg: Settings, *, exclude: set[str] = frozenset(),
                 hours_options: list[int] | None = None, cost_limit: Decimal | None = None,
                 by_cost: bool = False) -> tuple[list[Plan], str]:
    """Planos viáveis para a vaga, do melhor para o pior (custo-benefício; `by_cost`: menor custo mensal, p/ cargos obrigatórios) e um
    diagnóstico (por que não há plano) quando a lista é vazia."""
    hours_options = hours_options or [cfg.hours_week]
    persons = [p for p in person_pool(seed, company_id, ref, role, tier) if p.id not in exclude]
    if not persons:
        return [], "nenhum candidato disponível neste mês"
    plans, reasons = [], []
    for p in persons:
        r = choose_plan(p, cfg.regime_policy, hours_options, cfg.schedule, tier, cfg.max_salary, cost_limit)
        if isinstance(r, str):
            reasons.append(r)
            continue
        if hash01(seed, "rec-neg", company_id, f"{ref:%Y-%m}", tier, p.id) >= tier_of(tier).success:
            reasons.append(f"a negociação com {p.name} não avançou")
            continue
        plans.append(r)
    if by_cost:
        plans.sort(key=lambda x: (x.monthly_cost, -float(x.person.productivity), x.key))
    else:
        plans.sort(key=lambda x: (-x.score, x.key))
    return plans, "; ".join(dict.fromkeys(reasons[:3])) if not plans else ""


# ------------------------------------------------------------------ fornecedores

@dataclass(frozen=True)
class SupplierPlan:
    offer: supply.SupplierOffer
    volume: Decimal                   # volume mensal do contrato (<= volume máximo do briefing)
    price: Decimal                    # preço negociado (o menor que o fornecedor aceita, com o desconto do nível)
    expected_spend: Decimal           # min(volume esperado, volume do contrato) x preço
    score: float                      # preço efetivo por unidade entregue (menor = melhor)
    limits: Limits


def plan_supplier(offer: supply.SupplierOffer, *, seed: int, company_id: int, ref: date, tier: str, relevance: float, expected_volume: Decimal,
                  limits: Limits) -> SupplierPlan | str:
    t = tier_of(tier)
    if limits.min_reliability is not None and offer.reliability < limits.min_reliability:
        return f"{offer.name}: confiabilidade {round(offer.reliability * 100)}% abaixo do mínimo de {round(limits.min_reliability * 100)}%"
    if limits.max_lead_days is not None and offer.lead_days > limits.max_lead_days:
        return f"{offer.name}: prazo de {offer.lead_days} dias acima do máximo de {limits.max_lead_days}"
    volume = min(offer.max_units_month, limits.volume_cap) if limits.volume_cap is not None else offer.max_units_month
    if volume < offer.min_monthly_order:
        return f"{offer.name}: o volume máximo ({volume}) fica abaixo do pedido mínimo ({offer.min_monthly_order})"
    price = min(supply.minimum_price(offer, relevance, volume, t.discount), offer.unit_price)
    deal = supply.evaluate(offer, price, relevance, volume, t.discount)
    if not deal.accepted:
        return f"{offer.name}: não aceitou o preço proposto"
    spend = quantize_money(min(expected_volume, volume) * deal.price)
    if limits.max_spend is not None and spend > limits.max_spend:
        return f"{offer.name}: gasto previsto de R$ {spend}/mês acima do máximo de R$ {limits.max_spend}"
    if hash01(seed, "rec-sup", company_id, f"{ref:%Y-%m}", tier, offer.id) >= t.success:
        return f"a negociação com {offer.name} não avançou"
    score = float(deal.price) * (1 + NEG_SUPPLY_LOSS * (1 - offer.reliability))
    return SupplierPlan(offer, volume, deal.price, spend, score, limits)


def visible_offers(seed: int, company_id: int, ref: date, tier: str, offers: list[supply.SupplierOffer]) -> list[supply.SupplierOffer]:
    t = tier_of(tier)
    return [o for o in offers if hash01(seed, "rec-vis", company_id, f"{ref:%Y-%m}", tier, o.id) < t.find_chance]
