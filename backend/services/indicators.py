"""Indicadores técnicos. Camada de cálculo, independente do frontend e da fonte de dados.

Tudo em Decimal. Cada função recebe as listas alinhadas por candle e devolve
listas do mesmo tamanho, com None onde o indicador ainda não tem dados
(período de aquecimento). A fórmula de cada um está documentada na função.
"""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from backend.services.market_data import Candle

D = Decimal
Series = list[Decimal | None]
ZERO, HUNDRED = D(0), D(100)


class IndicatorError(ValueError):
    pass


def _q(x: Decimal) -> Decimal:
    return x.quantize(D("0.00000001"))


# ------------------------------------------------------------ médias móveis

def sma(values: list[Decimal | None], n: int) -> Series:
    """Média simples das últimas n entradas (None se a janela tiver None)."""
    out: Series = [None] * len(values)
    for i in range(n - 1, len(values)):
        w = values[i - n + 1:i + 1]
        if None not in w:
            out[i] = _q(sum(w, ZERO) / n)  # type: ignore[arg-type]
    return out


def ema(values: list[Decimal | None], n: int) -> Series:
    """Média exponencial: semente = SMA das n primeiras entradas válidas; alpha = 2/(n+1)."""
    out: Series = [None] * len(values)
    alpha = D(2) / (n + 1)
    start = next((i for i, v in enumerate(values) if v is not None), None)
    if start is None or len(values) - start < n:
        return out
    prev = sum(values[start:start + n], ZERO) / n  # type: ignore[arg-type]
    out[start + n - 1] = _q(prev)
    for i in range(start + n, len(values)):
        prev = (values[i] - prev) * alpha + prev  # type: ignore[operator]
        out[i] = _q(prev)
    return out


def _wilder(values: list[Decimal], n: int) -> Series:
    """Suavização de Wilder: semente = média das n primeiras; depois (prev*(n-1)+x)/n."""
    out: Series = [None] * len(values)
    if len(values) < n:
        return out
    prev = sum(values[:n], ZERO) / n
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = (prev * (n - 1) + values[i]) / n
        out[i] = prev
    return out


# ----------------------------------------------------------------- osciladores

def rsi(closes: list[Decimal], n: int = 14) -> Series:
    """RSI de Wilder: 100 - 100/(1+RS), RS = ganho médio / perda média."""
    out: Series = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = [max(closes[i] - closes[i - 1], ZERO) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], ZERO) for i in range(1, len(closes))]
    avg_g, avg_l = sum(gains[:n], ZERO) / n, sum(losses[:n], ZERO) / n
    for i in range(n, len(closes)):
        if i > n:
            avg_g = (avg_g * (n - 1) + gains[i - 1]) / n
            avg_l = (avg_l * (n - 1) + losses[i - 1]) / n
        out[i] = HUNDRED if avg_l == 0 else _q(HUNDRED - HUNDRED / (1 + avg_g / avg_l))
    return out


def macd(closes: list[Decimal], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, Series]:
    """MACD = EMA(fast) - EMA(slow); sinal = EMA(signal) do MACD; histograma = MACD - sinal."""
    ef, es = ema(closes, fast), ema(closes, slow)
    line: Series = [None if a is None or b is None else a - b for a, b in zip(ef, es, strict=True)]
    sig = ema(line, signal)
    hist: Series = [None if m is None or s is None else _q(m - s) for m, s in zip(line, sig, strict=True)]
    return {"macd": [None if m is None else _q(m) for m in line], "signal": sig, "histogram": hist}


def bollinger(closes: list[Decimal], n: int = 20, k: Decimal = D(2)) -> dict[str, Series]:
    """Bandas de Bollinger: SMA(n) ± k * desvio-padrão populacional das n últimas."""
    mid = sma(closes, n)
    upper: Series = [None] * len(closes)
    lower: Series = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        w = closes[i - n + 1:i + 1]
        mean = sum(w, ZERO) / n
        sd = (sum(((x - mean) ** 2 for x in w), ZERO) / n).sqrt()
        upper[i], lower[i] = _q(mean + k * sd), _q(mean - k * sd)
    return {"upper": upper, "middle": mid, "lower": lower}


def stochastic(candles: list[Candle], k_period: int = 14, k_smooth: int = 3, d_period: int = 3) -> dict[str, Series]:
    """Estocástico lento: %K bruto = (C - mín)/(máx - mín)*100; %K = SMA(k_smooth); %D = SMA(d_period) de %K."""
    raw: Series = [None] * len(candles)
    for i in range(k_period - 1, len(candles)):
        w = candles[i - k_period + 1:i + 1]
        hh, ll = max(c.high for c in w), min(c.low for c in w)
        raw[i] = HUNDRED / 2 if hh == ll else (candles[i].close - ll) / (hh - ll) * HUNDRED
    k = sma(raw, k_smooth)
    return {"k": k, "d": sma(k, d_period)}


# ----------------------------------------------------------- volatilidade / tendência

def _true_ranges(candles: list[Candle]) -> list[Decimal]:
    trs = [candles[0].high - candles[0].low]
    for i in range(1, len(candles)):
        c, pc = candles[i], candles[i - 1].close
        trs.append(max(c.high - c.low, abs(c.high - pc), abs(c.low - pc)))
    return trs


def atr(candles: list[Candle], n: int = 14) -> Series:
    """ATR: média de Wilder do True Range (máx de H-L, |H-Cant|, |L-Cant|)."""
    return [None if v is None else _q(v) for v in _wilder(_true_ranges(candles), n)]


def adx(candles: list[Candle], n: int = 14) -> dict[str, Series]:
    """ADX de Wilder: +DI/-DI a partir de +DM/-DM e TR suavizados; DX = |+DI - -DI|/(+DI + -DI)*100; ADX = Wilder(DX)."""
    size = len(candles)
    out = {"adx": [None] * size, "plus_di": [None] * size, "minus_di": [None] * size}
    if size < 2 * n:
        return out  # type: ignore[return-value]
    plus_dm, minus_dm, trs = [ZERO], [ZERO], _true_ranges(candles)
    for i in range(1, size):
        up, down = candles[i].high - candles[i - 1].high, candles[i - 1].low - candles[i].low
        plus_dm.append(up if up > down and up > 0 else ZERO)
        minus_dm.append(down if down > up and down > 0 else ZERO)
    # suavização de Wilder sobre as séries a partir do índice 1 (o 0 não tem variação)
    s_tr = _wilder(trs[1:], n)
    s_p, s_m = _wilder(plus_dm[1:], n), _wilder(minus_dm[1:], n)
    dx: list[Decimal] = []
    first = n - 1  # índice (na série deslocada) do primeiro valor suavizado
    for j in range(first, size - 1):
        i = j + 1
        if not s_tr[j]:
            pdi = mdi = ZERO
        else:
            pdi, mdi = HUNDRED * s_p[j] / s_tr[j], HUNDRED * s_m[j] / s_tr[j]  # type: ignore[operator]
        out["plus_di"][i], out["minus_di"][i] = _q(pdi), _q(mdi)
        dx.append(ZERO if pdi + mdi == 0 else HUNDRED * abs(pdi - mdi) / (pdi + mdi))
    adx_s = _wilder(dx, n)
    for k, v in enumerate(adx_s):
        if v is not None:
            out["adx"][first + 1 + k] = _q(v)
    return out  # type: ignore[return-value]


def vwap(candles: list[Candle], reset_daily: bool) -> Series:
    """VWAP = Σ(preço típico × volume) / Σ volume. Em gráficos intraday reinicia a cada dia (UTC)."""
    out: Series = []
    cum_pv = cum_v = ZERO
    day = None
    for c in candles:
        d = datetime.fromtimestamp(c.time, UTC).date()
        if reset_daily and d != day:
            cum_pv = cum_v = ZERO
            day = d
        typical = (c.high + c.low + c.close) / 3
        cum_pv += typical * c.volume
        cum_v += c.volume
        out.append(_q(cum_pv / cum_v) if cum_v > 0 else None)
    return out


# ------------------------------------------------------------------- registro

@dataclass(frozen=True)
class Spec:
    kind: str                       # "overlay" (sobre o preço) | "pane" (painel separado)
    defaults: tuple[int, ...]
    compute: Callable[..., dict[str, Series]]
    max_params: int = 3


def _one(name: str, s: Series) -> dict[str, Series]:
    return {name: s}


REGISTRY: dict[str, Spec] = {
    "sma": Spec("overlay", (20,), lambda c, n, **_: _one("sma", sma([x.close for x in c], n)), 1),
    "ema": Spec("overlay", (20,), lambda c, n, **_: _one("ema", ema([x.close for x in c], n)), 1),
    "bbands": Spec("overlay", (20, 2), lambda c, n, k, **_: bollinger([x.close for x in c], n, D(k)), 2),
    "vwap": Spec("overlay", (), lambda c, reset_daily, **_: _one("vwap", vwap(c, reset_daily)), 0),
    "rsi": Spec("pane", (14,), lambda c, n, **_: _one("rsi", rsi([x.close for x in c], n)), 1),
    "macd": Spec("pane", (12, 26, 9), lambda c, f, s, g, **_: macd([x.close for x in c], f, s, g), 3),
    "stoch": Spec("pane", (14, 3, 3), lambda c, k, s, d, **_: stochastic(c, k, s, d), 3),
    "adx": Spec("pane", (14,), lambda c, n, **_: adx(c, n), 1),
    "atr": Spec("pane", (14,), lambda c, n, **_: _one("atr", atr(c, n)), 1),
    "volume": Spec("pane", (), lambda c, **_: _one("volume", [x.volume for x in c]), 0),
}
MAX_INDICATORS = 12


def parse_spec(text: str) -> tuple[str, tuple[int, ...]]:
    """'sma:50' -> ('sma', (50,)); parâmetros omitidos usam o padrão."""
    name, *raw = text.strip().lower().split(":")
    spec = REGISTRY.get(name)
    if spec is None:
        raise IndicatorError(f"indicador desconhecido: {name}")
    if len(raw) > spec.max_params:
        raise IndicatorError(f"parâmetros demais para {name}")
    try:
        given = tuple(int(x) for x in raw)
    except ValueError as exc:
        raise IndicatorError(f"parâmetro inválido em '{text}'") from exc
    if any(not 1 <= p <= 500 for p in given):
        raise IndicatorError("parâmetros devem estar entre 1 e 500")
    return name, given + spec.defaults[len(given):]


def compute(candles: list[Candle], specs: list[str], *, intraday: bool = False) -> dict[str, dict]:
    """Calcula os indicadores pedidos. Retorna {spec: {"kind", "series": {linha: [valores]}}}."""
    if len(specs) > MAX_INDICATORS:
        raise IndicatorError(f"no máximo {MAX_INDICATORS} indicadores")
    result: dict[str, dict] = {}
    for text in dict.fromkeys(specs):  # sem duplicatas, mantém ordem
        name, params = parse_spec(text)
        spec = REGISTRY[name]
        kwargs = {"reset_daily": intraday} if name == "vwap" else {}
        series = spec.compute(candles, *params, **kwargs)
        result[text.strip().lower()] = {"kind": spec.kind, "series": series}
    return result
