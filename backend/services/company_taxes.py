"""Tributos reais das empresas (Empresas v2, fase 3b). Módulo PURO (sem banco), determinístico e testável.

Fonte: docs/IMPOSTOS_EMPRESAS.md (referência 21/11/2026). Convenção de confiança do documento:
[OFICIAL] lido no texto da lei; [SECUNDÁRIA] imprensa/consultorias; [CONHECIMENTO] regra estável não rebuscada;
[NÃO CONFIRMADO]. O que NÃO está confirmado ou foi reduzido para caber no jogo está listado em `SIMPLIFICACOES`
(e mostrado na interface).

REGIME (escolhido AUTOMATICAMENTE todo mês pelo RBT12 = receita bruta dos últimos 12 meses):
    RBT12 > R$ 4,8 mi            -> LUCRO_PRESUMIDO
    senão, se elegível ao MEI     -> MEI   (segmento permitido, <= 1 empregado CLT, RBT12 <= R$ 81 mil; e a empresa nunca
                                            "volta" ao MEI depois de ter sido Simples/Lucro Presumido)
    senão                         -> SIMPLES (DAS, Anexos I a V)
Empresa com menos de 12 meses: RBT12 proporcionalizado (1º mês: receita do mês x 12; depois: média mensal x 12) —
é a regra real da LC 123 (art. 18 §§ 2º e 3º) [OFICIAL].

ENCARGOS DA FOLHA: o custo CLT do jogo (2x o salário) JÁ embute INSS patronal, FGTS, 13º, férias e demais encargos
(decisão de design). Por isso este módulo NÃO calcula CPP/INSS patronal/FGTS/RAT/terceiros: a parcela "CPP" do DAS
(Anexos I, II, III, V) é só uma repartição interna do DAS e o Anexo IV (INSS patronal por fora) também não cobra GPS aqui.
Pró-labore, INSS/IRPF do dono e retenção sobre dividendos NÃO são tratados nesta fase.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import NamedTuple

from backend.core.money import quantize_money

D = Decimal
ZERO = D("0")

# ---------------------------------------------------------------- regimes
MEI = "MEI"
SIMPLES = "SIMPLES"
LUCRO_PRESUMIDO = "LUCRO_PRESUMIDO"
REGIME_LABELS = {MEI: "MEI (DAS-MEI)", SIMPLES: "Simples Nacional (DAS)", LUCRO_PRESUMIDO: "Lucro Presumido", "EXT": "Tributos do exterior (IVA + imposto sobre o lucro)"}

# ---------------------------------------------------------------- parâmetros gerais (2026)
SALARIO_MINIMO = D("1621.00")                 # [SECUNDÁRIA]
LIMITE_SIMPLES = D("4800000")                 # [OFICIAL] RBT12 máximo do Simples; acima disso: Lucro Presumido
MEI_LIMITE_ANUAL = D("81000")                 # [OFICIAL] LC 123 vigente em 2026 (LC 238/2026 sobe para 110 mil em 2027 e 140 mil em 2028)
MEI_LIMITE_CAMINHONEIRO = D("251600")         # [SECUNDÁRIA]
MEI_MAX_EMPREGADOS = 1                        # [OFICIAL]
FATOR_R_MIN = D("0.28")                       # [OFICIAL] r >= 28% -> Anexo III; senão Anexo V

# DAS-MEI 2026 = 5% do salário mínimo (INSS) + R$ 1 (ICMS) e/ou R$ 5 (ISS) [OFICIAL a fórmula; valores conferidos em fontes secundárias]
MEI_INSS = quantize_money(SALARIO_MINIMO * D("0.05"))        # 81,05
MEI_DAS = {
    "COMERCIO": MEI_INSS + D("1.00"),         # comércio / indústria: 82,05
    "SERVICOS": MEI_INSS + D("5.00"),         # serviços: 86,05
    "CAMINHONEIRO": D("195.52"),              # 12% do SM + R$ 1 de ICMS: cálculo próprio, fontes divergem [NÃO CONFIRMADO]
}
MEI_ATIVIDADE = {                              # segmento -> tipo de DAS-MEI; ausente = o MEI NÃO pode ter o segmento
    "RESTAURANT": "COMERCIO", "CAFE": "COMERCIO", "CLOTHING": "COMERCIO", "ECOMMERCE": "COMERCIO",
    "WORKSHOP": "SERVICOS", "TECH": "SERVICOS", "AGENCY": "SERVICOS", "TRANSPORT": "CAMINHONEIRO",
}                                              # fora: SUPERMARKET, INDUSTRY, CONSTRUCTION, REAL_ESTATE_AGENCY (doc: inviáveis/vedados)
MEI_LABEL = {"COMERCIO": "comércio", "SERVICOS": "serviços", "CAMINHONEIRO": "MEI Caminhoneiro"}

# ---------------------------------------------------------------- Simples Nacional: (limite superior do RBT12, alíquota nominal, parcela a deduzir)
SIMPLES_FAIXAS: dict[str, list[tuple[Decimal, Decimal, Decimal]]] = {
    anexo: [(D(a), D(b), D(c)) for a, b, c in rows] for anexo, rows in {
        "I":   [("180000", "0.0400", "0"), ("360000", "0.0730", "5940"), ("720000", "0.0950", "13860"),
                ("1800000", "0.1070", "22500"), ("3600000", "0.1430", "87300"), ("4800000", "0.1900", "378000")],
        "II":  [("180000", "0.0450", "0"), ("360000", "0.0780", "5940"), ("720000", "0.1000", "13860"),
                ("1800000", "0.1120", "22500"), ("3600000", "0.1470", "85500"), ("4800000", "0.3000", "720000")],
        "III": [("180000", "0.0600", "0"), ("360000", "0.1120", "9360"), ("720000", "0.1350", "17640"),
                ("1800000", "0.1600", "35640"), ("3600000", "0.2100", "125640"), ("4800000", "0.3300", "648000")],
        "IV":  [("180000", "0.0450", "0"), ("360000", "0.0900", "8100"), ("720000", "0.1020", "12420"),
                ("1800000", "0.1400", "39780"), ("3600000", "0.2200", "183780"), ("4800000", "0.3300", "828000")],
        "V":   [("180000", "0.1550", "0"), ("360000", "0.1800", "4500"), ("720000", "0.1950", "9900"),
                ("1800000", "0.2050", "17100"), ("3600000", "0.2300", "62100"), ("4800000", "0.3050", "540000")],
    }.items()}
ANEXO_LABEL = {"I": "Comércio", "II": "Indústria", "III": "Serviços", "IV": "Serviços (construção)", "V": "Serviços intelectuais"}

# Anexo por segmento (None = depende do Fator R: III se folha >= 28% do RBT12, senão V) [CONHECIMENTO; ver doc, incerteza 6]
ANEXO_SEGMENTO: dict[str, str | None] = {
    "RESTAURANT": "I", "CAFE": "I", "CLOTHING": "I", "SUPERMARKET": "I", "ECOMMERCE": "I",
    "WORKSHOP": "III", "TECH": None, "AGENCY": None, "INDUSTRY": "II", "CONSTRUCTION": "IV",
    "TRANSPORT": "III", "REAL_ESTATE_AGENCY": "III", "AGRIBUSINESS": "I",       # agro: comercialização da produção (Anexo I; SIMPLIFICAÇÃO, ver lista)
}

# ---------------------------------------------------------------- Lucro Presumido
LP_IRPJ = D("0.15")
LP_IRPJ_ADICIONAL = D("0.10")                 # sobre a base presumida que exceder R$ 20 mil/mês [CONHECIMENTO, estável]
LP_IRPJ_ADICIONAL_LIMITE_MES = D("20000")
LP_CSLL = D("0.09")
LP_PIS = D("0.0065")                          # cumulativo [CONHECIMENTO]
LP_COFINS = D("0.03")                         # cumulativo [CONHECIMENTO]
LC224_LIMITE_ANO = D("5000000")               # [OFICIAL o texto; datas de vigência: leitura própria, NÃO CONFIRMADO]
LC224_ACRESCIMO = D("0.10")                   # +10% (relativo) na presunção, só sobre a parcela da receita acima do limite
PRESUNCAO = {                                 # (IRPJ, CSLL) sobre a receita bruta [OFICIAL Lei 9.249 art. 15; CSLL: CONHECIMENTO]
    "comercio": (D("0.08"), D("0.12")), "industria": (D("0.08"), D("0.12")), "transporte_carga": (D("0.08"), D("0.12")),
    "construcao_com_material": (D("0.08"), D("0.12")), "servicos": (D("0.32"), D("0.32")), "intermediacao": (D("0.32"), D("0.32")),
}
PRESUNCAO_SEGMENTO = {
    "RESTAURANT": "comercio", "CAFE": "comercio", "CLOTHING": "comercio", "SUPERMARKET": "comercio", "ECOMMERCE": "comercio",
    "WORKSHOP": "servicos", "TECH": "servicos", "AGENCY": "servicos", "INDUSTRY": "industria",
    "CONSTRUCTION": "construcao_com_material", "TRANSPORT": "transporte_carga", "REAL_ESTATE_AGENCY": "intermediacao",
    "AGRIBUSINESS": "comercio",
}
ISS_MIN, ISS_MAX = D("0.02"), D("0.05")       # [OFICIAL] LC 116 art. 8º e 8º-A
ISS_TIPICO = {                                # sugestão para o jogo (doc, incerteza 5: NÃO CONFIRMADO por cidade)
    "WORKSHOP": D("0.03"), "TECH": D("0.03"), "AGENCY": D("0.03"), "CONSTRUCTION": D("0.03"),
    "REAL_ESTATE_AGENCY": D("0.04"), "TRANSPORT": D("0.03"),
}
ICMS_TIPICO = D("0.18")                       # SP 18% [SECUNDÁRIA]; varia por estado (17%-23%): SIMPLIFICAÇÃO
IPI_TIPICO = D("0.10")                        # depende da TIPI: valor lúdico, SIMPLIFICAÇÃO
ICMS_SEGMENTOS = {"RESTAURANT", "CAFE", "CLOTHING", "SUPERMARKET", "ECOMMERCE", "INDUSTRY", "TRANSPORT",
                 "AGRIBUSINESS"}   # vendem mercadoria/transportam
IPI_SEGMENTOS = {"INDUSTRY"}
TRANSPORT_ICMS_SHARE = D("0.5")               # fatia da receita do transporte que é intermunicipal (ICMS); o resto paga ISS: SIMPLIFICAÇÃO

SIMPLIFICACOES = [
    "Alíquota de ICMS única de 18% (no real varia de 17% a 23% por estado) e IPI fixo de 10% (no real depende da TIPI).",
    "ICMS e IPI do Lucro Presumido calculados sobre (receita - compras do mês), como se todo insumo gerasse crédito.",
    "ISS por tipo de atividade (2% a 5%, típico do jogo); no real depende do município.",
    "Sublimite do Simples (R$ 3,6 mi, ICMS/ISS por fora) e ICMS-ST/monofásico não são modelados.",
    "MEI: sem tolerância de 20% sobre o limite de R$ 81 mil; o desenquadramento é imediato.",
    "Lucro Presumido apurado por mês (no real, IRPJ/CSLL são trimestrais); majoração da LC 224 (presunção +10% acima de R$ 5 mi) proporcional ao RBT12.",
    "Agronegócio: tratado como comercialização da produção (Simples Anexo I, presunção de comércio e ICMS de 18% com crédito dos insumos); "
    "no real há diferimento/isenção de ICMS em muitas operações rurais, tributação do produtor rural pessoa física e Funrural, não modelados. ISS não se aplica.",
    "Encargos da folha (INSS patronal, FGTS, 13º, férias) já estão incluídos no custo CLT de 2x o salário e não são cobrados de novo.",
    "Pró-labore, INSS e IRPF do dono e retenção sobre dividendos não são calculados.",
]


# ---------------------------------------------------------------- resultado
class TaxLine(NamedTuple):
    name: str
    amount: Decimal
    base: Decimal
    rate_pct: Decimal


@dataclass(frozen=True)
class TaxResult:
    regime: str
    lines: list[TaxLine]
    total: Decimal
    annex: str | None = None                     # Simples: anexo efetivamente aplicado
    effective_pct: Decimal | None = None         # Simples: alíquota efetiva (%)
    fator_r: Decimal | None = None               # Simples com Fator R: folha / RBT12
    rbt12: Decimal = ZERO
    notes: list[str] = field(default_factory=list)

    def breakdown(self) -> list[dict]:
        """Lista serializável (JSON) para `CompanyMonth.tax_breakdown`."""
        return [{"name": ln.name, "base": str(ln.base), "rate_pct": str(ln.rate_pct), "amount": str(ln.amount)} for ln in self.lines]


# ---------------------------------------------------------------- funções puras
def annualize(prior: list[Decimal], current: Decimal) -> Decimal:
    """RBT12 (ou folha de 12 meses) proporcionalizado. `prior` = valores dos meses anteriores (do mais antigo ao mais recente).
    Sem histórico: valor do mês x 12; menos de 12 meses: média x 12; 12 ou mais: soma dos últimos 12."""
    if not prior:
        return current * 12
    if len(prior) < 12:
        return sum(prior, ZERO) / len(prior) * 12
    return sum(prior[-12:], ZERO)


def simples_faixa(anexo: str, rbt12: Decimal) -> tuple[int, Decimal, Decimal]:
    """(número da faixa 1..6, alíquota nominal, parcela a deduzir). Acima de R$ 4,8 mi: ValueError."""
    for i, (lim, aliq, ded) in enumerate(SIMPLES_FAIXAS[anexo], start=1):
        if rbt12 <= lim:
            return i, aliq, ded
    raise ValueError("RBT12 acima do limite do Simples Nacional")


def effective_rate(anexo: str, rbt12: Decimal) -> Decimal:
    """Alíquota efetiva (fração) = (RBT12 x alíquota - parcela a deduzir) / RBT12. Com RBT12 = 0, a nominal da 1ª faixa."""
    if rbt12 <= 0:
        return SIMPLES_FAIXAS[anexo][0][1]
    _, aliq, ded = simples_faixa(anexo, rbt12)
    return (rbt12 * aliq - ded) / rbt12


def simples_annex(segment: str, rbt12: Decimal, payroll12: Decimal) -> tuple[str, Decimal | None]:
    """Anexo do segmento; para os de Fator R, III se folha/RBT12 >= 28%, senão V. Devolve (anexo, fator r ou None)."""
    anexo = ANEXO_SEGMENTO[segment]
    if anexo is not None:
        return anexo, None
    r = payroll12 / rbt12 if rbt12 > 0 else ZERO
    return ("III" if r >= FATOR_R_MIN else "V"), r


def mei_allowed(segment: str) -> bool:
    return segment in MEI_ATIVIDADE


def mei_limit(segment: str) -> Decimal:
    return MEI_LIMITE_CAMINHONEIRO if MEI_ATIVIDADE.get(segment) == "CAMINHONEIRO" else MEI_LIMITE_ANUAL


def choose_regime(segment: str, regime_hint: str | None, rbt12: Decimal, employees: int) -> str:
    """MEI -> Simples -> Lucro Presumido pelo RBT12 e restrições. Nunca volta ao MEI depois de ter saído dele."""
    if rbt12 > LIMITE_SIMPLES:
        return LUCRO_PRESUMIDO
    if regime_hint in (None, MEI) and mei_allowed(segment) and employees <= MEI_MAX_EMPREGADOS and rbt12 <= mei_limit(segment):
        return MEI
    return SIMPLES


def _pct(rate: Decimal) -> Decimal:
    return (rate * 100).quantize(D("0.0001"))


def _line(name: str, base: Decimal, rate: Decimal) -> TaxLine:
    return TaxLine(name, quantize_money(base * rate), quantize_money(base), _pct(rate))


def _lucro_presumido(segment: str, rbt12: Decimal, revenue: Decimal, purchases: Decimal) -> TaxResult:
    irpj_pres, csll_pres = PRESUNCAO[PRESUNCAO_SEGMENTO[segment]]
    excess = max(rbt12 - LC224_LIMITE_ANO, ZERO) / rbt12 if rbt12 > 0 else ZERO       # fração da receita acima de R$ 5 mi/ano
    mult = 1 + LC224_ACRESCIMO * excess
    irpj_base = revenue * irpj_pres * mult
    csll_base = revenue * csll_pres * mult
    lines = [
        TaxLine("IRPJ", quantize_money(irpj_base * LP_IRPJ), quantize_money(irpj_base), _pct(LP_IRPJ)),
    ]
    adicional_base = max(irpj_base - LP_IRPJ_ADICIONAL_LIMITE_MES, ZERO)
    if adicional_base > 0:
        lines.append(TaxLine("Adicional de IRPJ", quantize_money(adicional_base * LP_IRPJ_ADICIONAL), quantize_money(adicional_base),
                             _pct(LP_IRPJ_ADICIONAL)))
    lines.append(TaxLine("CSLL", quantize_money(csll_base * LP_CSLL), quantize_money(csll_base), _pct(LP_CSLL)))
    lines.append(_line("PIS", revenue, LP_PIS))
    lines.append(_line("COFINS", revenue, LP_COFINS))
    credit_base = max(revenue - purchases, ZERO)
    iss = ISS_TIPICO.get(segment)
    if segment == "TRANSPORT":
        lines.append(_line("ICMS", credit_base * TRANSPORT_ICMS_SHARE, ICMS_TIPICO))
        lines.append(_line("ISS", revenue * (1 - TRANSPORT_ICMS_SHARE), min(max(iss, ISS_MIN), ISS_MAX)))
    else:
        if segment in ICMS_SEGMENTOS:
            lines.append(_line("ICMS", credit_base, ICMS_TIPICO))
        if segment in IPI_SEGMENTOS:
            lines.append(_line("IPI", credit_base, IPI_TIPICO))
        if iss is not None:
            lines.append(_line("ISS", revenue, min(max(iss, ISS_MIN), ISS_MAX)))
    total = quantize_money(sum((ln.amount for ln in lines), ZERO))
    notes = ["Presunção LC 224: +10% sobre a parcela da receita acima de R$ 5 mi/ano."] if excess > 0 else []
    return TaxResult(LUCRO_PRESUMIDO, lines, total, rbt12=rbt12, notes=notes)


def compute_taxes(segment: str, regime_hint: str | None, rbt12: Decimal, monthly_revenue: Decimal, payroll: Decimal,
                  employees: int, *, purchases: Decimal = ZERO) -> TaxResult:
    """Tributos do mês de uma empresa.

    segment: chave do segmento (ex.: "RESTAURANT"); regime_hint: regime do mês anterior (None = primeiro mês);
    rbt12: receita bruta de 12 meses (já proporcionalizada, ver `annualize`); monthly_revenue: receita do mês;
    payroll: folha dos 12 meses (mesma proporcionalização do RBT12, serve ao Fator R);
    employees: empregados CLT (limite do MEI); purchases: compras de insumos/mercadorias do mês (crédito de ICMS/IPI no Lucro Presumido).
    """
    revenue = max(D(monthly_revenue), ZERO)
    rbt12 = max(D(rbt12), ZERO)
    regime = choose_regime(segment, regime_hint, rbt12, employees)
    if regime == MEI:
        das = MEI_DAS[MEI_ATIVIDADE[segment]]          # valor FIXO por atividade, mesmo sem faturamento
        rate = das / revenue * 100 if revenue > 0 else ZERO
        line = TaxLine("DAS-MEI", das, quantize_money(revenue), rate.quantize(D("0.0001")))
        return TaxResult(MEI, [line], das, rbt12=rbt12,
                         notes=[f"DAS-MEI fixo ({MEI_LABEL[MEI_ATIVIDADE[segment]]}), independe do faturamento."])
    if regime == LUCRO_PRESUMIDO:
        return _lucro_presumido(segment, rbt12, revenue, D(purchases))
    anexo, r = simples_annex(segment, rbt12, max(D(payroll), ZERO))
    eff = effective_rate(anexo, rbt12)
    lines = [TaxLine("DAS", quantize_money(revenue * eff), quantize_money(revenue), _pct(eff))]
    notes = [f"Anexo {anexo} ({ANEXO_LABEL[anexo]}), alíquota efetiva {_pct(eff)}% sobre o RBT12."]
    if r is not None:
        notes.append(f"Fator R = folha/RBT12 = {(r * 100).quantize(D('0.1'))}% ({'>= 28%: Anexo III' if anexo == 'III' else '< 28%: Anexo V'}).")
    return TaxResult(SIMPLES, lines, lines[0].amount, annex=anexo, effective_pct=_pct(eff),
                     fator_r=r.quantize(D("0.0001")) if r is not None else None, rbt12=rbt12, notes=notes)


# ---------------------------------------------------------------- informação para catálogo / cotação
def segment_tax_info(segment: str) -> dict:
    """Regime/anexo provável do segmento (para catálogo e /quote): empresa pequena começa no MEI só se o segmento permitir,
    tiver até 1 empregado CLT e faturar até R$ 81 mil/ano; na prática, no Simples."""
    anexo = ANEXO_SEGMENTO[segment]
    anexos = [anexo] if anexo else ["III", "V"]
    lo = min(effective_rate(a, D("100000")) for a in anexos)
    hi = max(effective_rate(a, LIMITE_SIMPLES) for a in anexos)
    label = (f"Simples Nacional - Anexo {anexo} ({ANEXO_LABEL[anexo]})" if anexo
             else "Simples Nacional - Anexo III (se folha >= 28% do faturamento, Fator R) ou V")
    return {
        "regime": SIMPLES, "annex": anexo or "III/V", "regime_label": label,
        "effective_min_pct": _pct(lo), "effective_max_pct": _pct(hi),
        "mei_allowed": mei_allowed(segment), "mei_das": MEI_DAS[MEI_ATIVIDADE[segment]] if mei_allowed(segment) else None,
        "lp_taxes": lucro_presumido_names(segment),
    }


def lucro_presumido_names(segment: str) -> list[str]:
    names = ["IRPJ", "CSLL", "PIS", "COFINS"]
    if segment in ICMS_SEGMENTOS:
        names.append("ICMS")
    if segment in IPI_SEGMENTOS:
        names.append("IPI")
    if segment in ISS_TIPICO:
        names.append("ISS")
    return names
