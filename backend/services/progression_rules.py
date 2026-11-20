"""Dados da progressão: cenários do modo carreira, catálogo de objetivos e de conquistas.

Para acrescentar um cenário, objetivo ou conquista basta incluir um item aqui (nada de lógica nova no serviço).
Valores em R$ de referência. `index` em despesas = categoria de preços para reajuste mensal pela inflação
(None = valor contratual fixo, como aluguel).
"""
from dataclasses import dataclass, field

MODES = ("FREE", "CAREER", "RANKED")


@dataclass(frozen=True)
class Expense:
    category: str
    name: str
    amount: int
    index: str | None = None


@dataclass(frozen=True)
class GoalDef:
    key: str
    kind: str
    title: str
    description: str
    metric: str
    target: float
    sustain: int = 1
    comparator: str = "GTE"


@dataclass(frozen=True)
class Scenario:
    key: str
    name: str
    description: str
    cash: int
    salary: int
    expenses: tuple[Expense, ...]
    goals: tuple[GoalDef, ...]
    challenges: tuple[str, ...]
    age: int = 28
    partner: dict | None = None            # {"income": .., "assets": .., "debts": .., "stage": "MARRIED"}
    children_ages: tuple[int, ...] = ()    # idades (anos) dos filhos já existentes
    housing: tuple[str, int] | None = None  # ("SHARED", custo mensal) — gera o item de moradia da família
    economy: dict = field(default_factory=dict)


STD_FOOD = lambda n: Expense("Alimentação", "Mercado", n, "alimentacao")        # noqa: E731
SCENARIOS: dict[str, Scenario] = {s.key: s for s in (
    Scenario(
        "independent", "Início independente",
        "Renda modesta, despesas básicas e pouco patrimônio. Construa estabilidade financeira.",
        cash=4000, salary=2600, age=24,
        expenses=(Expense("Moradia", "Aluguel", 900), STD_FOOD(650), Expense("Transporte", "Transporte", 260, "transporte"),
                  Expense("Contas domésticas", "Energia e água", 300, "energia"), Expense("Lazer", "Lazer", 150, "lazer")),
        goals=(GoalDef("emergency_3", "FINANCIAL", "Reserva de emergência de 3 meses", "Mantenha 3 meses de despesas em caixa.",
                       "emergency_months", 3, 3),
               GoalDef("positive_6", "FINANCIAL", "6 meses seguidos no azul", "Feche meses consecutivos com saldo positivo.",
                       "positive_streak", 6, 1),
               GoalDef("net_30k", "FINANCIAL", "Patrimônio de R$ 30 mil", "Atinja e mantenha o patrimônio.", "net_worth", 30000, 3)),
        challenges=("Orçamento apertado: qualquer imprevisto pesa.", "Inflação corrói o poder de compra de quem ganha pouco.")),
    Scenario(
        "young_pro", "Jovem profissional",
        "Emprego, renda mensal e espaço para crescer. Aumente a renda e construa patrimônio.",
        cash=15000, salary=6500, age=26,
        expenses=(Expense("Moradia", "Aluguel", 1800), STD_FOOD(900), Expense("Transporte", "Transporte", 450, "transporte"),
                  Expense("Contas domésticas", "Energia, água e internet", 420, "energia"), Expense("Lazer", "Lazer", 500, "lazer"),
                  Expense("Saúde", "Plano de saúde", 380, "saude")),
        goals=(GoalDef("emergency_6", "FINANCIAL", "Reserva de emergência de 6 meses", "Seis meses de despesas em caixa.",
                       "emergency_months", 6, 3),
               GoalDef("invested_30k", "FINANCIAL", "R$ 30 mil investidos", "Mantenha valor investido em ativos.", "invested", 30000, 3),
               GoalDef("net_80k", "FINANCIAL", "Patrimônio de R$ 80 mil", "Cresça e sustente seu patrimônio.", "net_worth", 80000, 3),
               GoalDef("quality_70", "PERSONAL", "Qualidade de vida 70+", "Equilibre carreira e bem-estar.", "quality", 70, 4)),
        challenges=("Tentação de gastar a renda crescente.", "Jornada intensa cobra saúde e bem-estar.")),
    Scenario(
        "entrepreneur", "Empreendedor iniciante",
        "Pouco capital e a chance de abrir um negócio. Construa uma empresa sustentável.",
        cash=60000, salary=1500, age=30,
        expenses=(Expense("Moradia", "Aluguel", 1300), STD_FOOD(800), Expense("Transporte", "Transporte", 300, "transporte"),
                  Expense("Contas domésticas", "Energia e água", 320, "energia")),
        goals=(GoalDef("first_company", "BUSINESS", "Abrir a primeira empresa", "Mantenha uma empresa ativa por 3 meses.",
                       "companies", 1, 3),
               GoalDef("profit_streak_6", "BUSINESS", "6 meses lucrativos", "Meses consecutivos de lucro em uma empresa.",
                       "profit_streak", 6, 1),
               GoalDef("revenue_40k", "BUSINESS", "Faturamento de R$ 40 mil/mês", "Receita mensal das empresas.", "company_revenue", 40000, 3),
               GoalDef("staff_5", "BUSINESS", "5 funcionários", "Time contratado de forma sustentável.", "employees", 5, 3)),
        challenges=("Capital curto: errar no estoque ou na folha custa caro.", "Custos de insumos acompanham a inflação.")),
    Scenario(
        "investor", "Investidor",
        "Patrimônio inicial para administrar. Construa carteira, gere renda e preserve o capital.",
        cash=400000, salary=0, age=40,
        expenses=(Expense("Moradia", "Aluguel", 3500), STD_FOOD(1800), Expense("Transporte", "Transporte", 700, "transporte"),
                  Expense("Saúde", "Plano de saúde", 900, "saude"), Expense("Lazer", "Lazer", 1200, "lazer"),
                  Expense("Contas domésticas", "Contas", 700, "energia")),
        goals=(GoalDef("invested_300k", "FINANCIAL", "R$ 300 mil investidos", "Coloque o capital para trabalhar.", "invested", 300000, 3),
               GoalDef("passive_3k", "FINANCIAL", "Renda passiva de R$ 3 mil/mês", "Rendimentos e aluguéis recorrentes.", "passive_income", 3000, 3),
               GoalDef("preserve", "FINANCIAL", "Preservar o patrimônio", "Mantenha o patrimônio acima do inicial por 12 meses.",
                       "net_worth", 400000, 12)),
        challenges=("Sem salário: as despesas saem do capital.", "Juros e inflação mudam o retorno real.")),
    Scenario(
        "family", "Família em formação",
        "Responsabilidades familiares e finanças a organizar. Equilibre qualidade de vida, família e patrimônio.",
        cash=20000, salary=7500, age=32,
        expenses=(STD_FOOD(1400), Expense("Transporte", "Transporte familiar", 700, "transporte"),
                  Expense("Contas domésticas", "Energia, água e internet", 550, "energia"), Expense("Saúde", "Plano de saúde", 900, "saude")),
        partner={"income": 4500, "assets": 15000, "debts": 3000, "stage": "MARRIED", "name": "Marina"},
        children_ages=(3,), housing=("SHARED", 2200),
        goals=(GoalDef("family_quality", "PERSONAL", "Qualidade de vida 70+", "Equilíbrio entre trabalho e família.", "quality", 70, 4),
               GoalDef("kids_education", "PERSONAL", "Educação dos filhos planejada", "Despesas de educação mantidas por 12 meses.",
                       "education_streak", 12, 1),
               GoalDef("emergency_4", "FINANCIAL", "Reserva de emergência de 4 meses", "Proteja a família de imprevistos.",
                       "emergency_months", 4, 3),
               GoalDef("net_70k", "FINANCIAL", "Patrimônio de R$ 70 mil", "Cresça com a família.", "net_worth", 70000, 3)),
        challenges=("Despesas dos filhos crescem a cada fase.", "Um só salário principal: a renda do parceiro ajuda, mas não cobre tudo.")),
)}

# Objetivos que o usuário pode criar (modo livre ou carreira): métrica + alvo
GOAL_TEMPLATES = {
    "emergency_fund": ("FINANCIAL", "Reserva de emergência", "emergency_months", "GTE", 6, 3),
    "net_worth": ("FINANCIAL", "Atingir patrimônio", "net_worth", "GTE", 100000, 3),
    "debt_free": ("FINANCIAL", "Quitar dívidas", "debts", "LTE", 0, 2),
    "passive_income": ("FINANCIAL", "Renda passiva mensal", "passive_income", "GTE", 2000, 3),
    "own_property": ("FINANCIAL", "Ter um imóvel", "real_estate", "GTE", 1, 3),
    "invested": ("FINANCIAL", "Valor investido", "invested", "GTE", 50000, 3),
    "first_company": ("BUSINESS", "Manter uma empresa", "companies", "GTE", 1, 3),
    "company_revenue": ("BUSINESS", "Faturamento mensal", "company_revenue", "GTE", 30000, 3),
    "hire": ("BUSINESS", "Equipe contratada", "employees", "GTE", 3, 3),
    "new_unit": ("BUSINESS", "Abrir nova unidade", "units", "GTE", 2, 2),
    "profit_streak": ("BUSINESS", "Meses seguidos lucrativos", "profit_streak", "GTE", 6, 1),
    "quality": ("PERSONAL", "Qualidade de vida", "quality", "GTE", 75, 4),
    "family": ("PERSONAL", "Construir uma família", "family_members", "GTE", 3, 3),
    "balance": ("PERSONAL", "Equilíbrio trabalho/vida", "work_life", "GTE", 1, 6),
    "education": ("PERSONAL", "Educação dos filhos", "education_streak", "GTE", 12, 1),
}
METRIC_LABEL = {
    "emergency_months": "meses de reserva", "net_worth": "patrimônio (R$)", "debts": "dívidas (R$)",
    "passive_income": "renda passiva (R$/mês)", "real_estate": "imóveis", "invested": "investido (R$)",
    "companies": "empresas ativas", "company_revenue": "faturamento (R$/mês)", "employees": "funcionários",
    "units": "unidades", "profit_streak": "meses lucrativos", "quality": "qualidade de vida",
    "family_members": "pessoas na família", "work_life": "equilíbrio (1=sim)", "education_streak": "meses com educação",
    "positive_streak": "meses no azul",
}

# Conquistas (nome e descrição); a verificação (sobre o HISTÓRICO) está em progression_service.ACHIEVEMENT_CHECKS
ACHIEVEMENTS = {
    "first_investment": ("Primeiro investimento", "Fez a primeira aplicação em ativos ou renda fixa."),
    "first_property": ("Primeiro imóvel", "Comprou o primeiro imóvel."),
    "first_company": ("Primeira empresa", "Abriu a primeira empresa."),
    "first_employee": ("Primeiro funcionário", "Contratou o primeiro funcionário."),
    "first_positive_month": ("Primeiro mês no azul", "Fechou um mês com saldo positivo."),
    "first_debt_paid": ("Primeira dívida quitada", "Quitou um financiamento ou empréstimo."),
    "first_million": ("Primeiro milhão", "Patrimônio total de R$ 1 milhão."),
    "company_expanded": ("Primeira expansão", "Expandiu uma empresa."),
    "first_distribution": ("Primeira distribuição de lucros", "Retirou lucros de uma empresa."),
    "emergency_reserve": ("Reserva de emergência completa", "Chegou a 6 meses de despesas em caixa."),
    "first_partner": ("Primeiro relacionamento", "Começou um namoro."),
    "married": ("Casamento", "Casou-se."),
    "first_child": ("Primeiro filho", "Nasceu seu primeiro filho."),
    "first_goal": ("Primeiro objetivo concluído", "Concluiu um objetivo de longo prazo."),
}
MILLION = 1_000_000
