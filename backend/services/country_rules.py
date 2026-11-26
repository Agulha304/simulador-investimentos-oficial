"""Países do jogo: moeda, câmbio inicial, custo de vida, impostos e mercado. NENHUM dado é consultado da vida real durante o jogo: estes
são apenas PONTOS DE PARTIDA aproximados (ordens de grandeza), e a economia de cada país é SIMULADA em `world_economy` (inflação, juros,
crescimento, nível de preços, câmbio e crises sorteados a cada partida).

Campos:
  fx0         reais por 1 unidade da moeda no início do jogo;     infl   inflação anual (%) usada na deriva cambial (PPC);
  vol         volatilidade mensal do câmbio;                       cost_index   nível de preços vs. Brasil (1,0) em reais ao câmbio inicial;
  wage_index  salários vs. Brasil (1,0);                           market   tamanho de mercado para uma empresa (demanda relativa);
  living      custo mensal (moeda local) de um estudante/morador: aluguel (1 quarto), comida, contas (energia, água e internet), transporte e saúde;
  flight/visa passagem de ida e volta e visto/seguro iniciais (reais);
  income_tax  alíquota efetiva sobre salário (%);              burden   encargo patronal (multiplicador do salário);
  corp_tax    imposto sobre o lucro (%);                         vat      IVA/imposto sobre vendas (%).
"""
from dataclasses import dataclass
from decimal import Decimal

D = Decimal


@dataclass(frozen=True)
class Country:
    code: str
    name: str
    flag: str
    currency: str
    symbol: str
    fx0: float
    infl: float
    vol: float
    cost_index: float
    wage_index: float
    market: float
    living: dict
    flight: int
    visa: int
    income_tax: float
    burden: float
    corp_tax: float
    vat: float
    language: str


def _c(code, name, flag, cur, sym, fx0, infl, vol, cost, wage, market, rent, food, util, transp, health, flight, visa, itax, burden, corp, vat, lang):
    return Country(code, name, flag, cur, sym, fx0, infl, vol, cost, wage, market,
                   {"rent": rent, "food": food, "utilities": util, "transport": transp, "health": health}, flight, visa, itax, burden, corp, vat, lang)


COUNTRIES: dict[str, Country] = {c.code: c for c in [
    _c("BR", "Brasil", "🇧🇷", "BRL", "R$", 1.0, 4.5, 0.0, 1.00, 1.00, 1.00, 1800, 900, 450, 300, 400, 0, 0, 12.0, 2.0, 15.0, 17.0, "português"),
    _c("US", "Estados Unidos", "🇺🇸", "USD", "US$", 5.2, 3.0, 0.022, 2.60, 3.20, 1.40, 1900, 450, 220, 130, 450, 4500, 3000, 22.0, 1.12, 25.0, 7.0, "inglês"),
    _c("CA", "Canadá", "🇨🇦", "CAD", "C$", 3.8, 2.5, 0.018, 2.20, 2.60, 0.90, 1700, 400, 200, 110, 120, 5000, 1800, 20.0, 1.10, 26.0, 12.0, "inglês/francês"),
    _c("GB", "Reino Unido", "🇬🇧", "GBP", "£", 6.6, 3.0, 0.020, 2.50, 2.80, 0.90, 1300, 300, 250, 160, 60, 4800, 6000, 23.0, 1.15, 25.0, 20.0, "inglês"),
    _c("IE", "Irlanda", "🇮🇪", "EUR", "€", 6.0, 2.3, 0.017, 2.30, 2.60, 0.50, 1700, 350, 230, 110, 80, 4600, 1500, 24.0, 1.11, 12.5, 23.0, "inglês"),
    _c("DE", "Alemanha", "🇩🇪", "EUR", "€", 6.0, 2.2, 0.017, 2.10, 2.50, 1.00, 950, 330, 280, 60, 120, 4500, 600, 30.0, 1.21, 30.0, 19.0, "alemão"),
    _c("FR", "França", "🇫🇷", "EUR", "€", 6.0, 2.1, 0.017, 2.00, 2.30, 0.90, 900, 330, 180, 85, 25, 4400, 700, 25.0, 1.42, 25.0, 20.0, "francês"),
    _c("ES", "Espanha", "🇪🇸", "EUR", "€", 6.0, 2.5, 0.017, 1.60, 1.60, 0.60, 800, 280, 160, 40, 60, 4000, 700, 22.0, 1.31, 25.0, 21.0, "espanhol"),
    _c("IT", "Itália", "🇮🇹", "EUR", "€", 6.0, 2.2, 0.017, 1.70, 1.70, 0.70, 750, 300, 200, 35, 50, 4200, 700, 26.0, 1.33, 24.0, 22.0, "italiano"),
    _c("PT", "Portugal", "🇵🇹", "EUR", "€", 6.0, 2.4, 0.017, 1.40, 1.20, 0.35, 800, 250, 140, 40, 40, 3800, 600, 22.0, 1.24, 21.0, 23.0, "português"),
    _c("NL", "Países Baixos", "🇳🇱", "EUR", "€", 6.0, 2.8, 0.017, 2.20, 2.60, 0.60, 1500, 350, 260, 90, 150, 4500, 1500, 28.0, 1.18, 25.8, 21.0, "neerlandês/inglês"),
    _c("CH", "Suíça", "🇨🇭", "CHF", "CHF", 6.4, 0.8, 0.016, 3.60, 4.20, 0.50, 1700, 600, 250, 90, 350, 5200, 900, 15.0, 1.14, 14.6, 8.1, "alemão/francês"),
    _c("AU", "Austrália", "🇦🇺", "AUD", "A$", 3.4, 3.0, 0.019, 2.30, 2.70, 0.90, 1800, 450, 250, 150, 150, 6000, 3300, 22.0, 1.12, 30.0, 10.0, "inglês"),
    _c("NZ", "Nova Zelândia", "🇳🇿", "NZD", "NZ$", 3.1, 2.5, 0.020, 2.00, 2.30, 0.30, 1600, 420, 230, 140, 60, 7000, 1800, 21.0, 1.04, 28.0, 15.0, "inglês"),
    _c("JP", "Japão", "🇯🇵", "JPY", "¥", 0.035, 1.8, 0.021, 1.80, 1.90, 1.00, 85000, 45000, 18000, 12000, 6000, 6500, 400, 18.0, 1.15, 30.0, 10.0, "japonês"),
    _c("KR", "Coreia do Sul", "🇰🇷", "KRW", "₩", 0.0038, 2.2, 0.020, 1.70, 1.80, 0.60, 700000, 400000, 150000, 70000, 60000, 6800, 250, 17.0, 1.12, 24.0, 10.0, "coreano"),
    _c("AR", "Argentina", "🇦🇷", "ARS", "AR$", 0.0052, 55.0, 0.045, 0.90, 0.50, 0.40, 450000, 250000, 90000, 40000, 80000, 2500, 400, 12.0, 1.25, 35.0, 21.0, "espanhol"),
    _c("CL", "Chile", "🇨🇱", "CLP", "CL$", 0.0056, 4.5, 0.025, 1.10, 0.90, 0.30, 450000, 250000, 90000, 40000, 50000, 3000, 400, 14.0, 1.03, 27.0, 19.0, "espanhol"),
    _c("MX", "México", "🇲🇽", "MXN", "MX$", 0.27, 4.2, 0.024, 0.90, 0.70, 0.60, 14000, 6000, 2200, 1000, 1500, 3500, 500, 15.0, 1.30, 30.0, 16.0, "espanhol"),
]}
HOME = "BR"
FX_FRICTION = D("0.045")        # IOF (3,5%) + spread de câmbio sobre dinheiro enviado/convertido para viver fora
LIFESTYLE_MULT = {"LOW": 0.85, "NORMAL": 1.0, "HIGH": 1.35}


def get(code: str) -> Country:
    try:
        return COUNTRIES[code.upper()]
    except KeyError:
        raise ValueError("país desconhecido") from None


def living_local(code: str, lifestyle: str = "NORMAL") -> dict:
    """Custo mensal (moeda local) por item, ajustado ao padrão de vida."""
    c, m = get(code), LIFESTYLE_MULT.get(lifestyle, 1.0)
    out = {k: round(v * (m if k in ("food", "rent") else 1.0), 2) for k, v in c.living.items()}
    out["total"] = round(sum(out.values()), 2)
    return out
