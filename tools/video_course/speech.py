"""Texto -> fala por extenso (pt-BR) para as cenas que NÓS escrevemos (abertura, revisão, próxima aula).

O roteirista do livro2video já escreve números por extenso ("mil e duzentos reais"); a voz não converte valores como
"R$ 1.200" ou "8,75%". Aqui fazemos essa conversão, só com a biblioteca padrão.
"""
import re

_UN = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze", "treze",
       "catorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
_DEZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_CEN = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos", "oitocentos", "novecentos"]


def _upto_999(n: int) -> str:
    if n == 100:
        return "cem"
    c, r = divmod(n, 100)
    parts = [_CEN[c]] if c else []
    if r:
        if r < 20:
            parts.append(_UN[r])
        else:
            d, u = divmod(r, 10)
            parts.append(_DEZ[d] + (f" e {_UN[u]}" if u else ""))
    return " e ".join(parts)


def num_to_words(n: int) -> str:
    if n < 0:
        return "menos " + num_to_words(-n)
    if n == 0:
        return "zero"
    if n >= 10**12:
        return " ".join(_UN[int(d)] for d in str(n))           # número enorme: soletra
    parts: list[tuple[int, str]] = []
    for size, one, many in ((10**9, "um bilhão", "bilhões"), (10**6, "um milhão", "milhões"), (1000, "mil", "mil")):
        q, n = divmod(n, size)
        if q:
            parts.append((q * size, one if q == 1 else f"{_upto_999(q)} {many}"))
    if n:
        parts.append((n, _upto_999(n)))
    out = parts[0][1]
    for i, (value, words) in enumerate(parts[1:], start=1):
        last = i == len(parts) - 1
        glue = " e " if last and (value < 100 or value % 100 == 0) else " "
        out += glue + words
    return out


def _decimal_words(frac: str) -> str:
    zeros = len(frac) - len(frac.lstrip("0"))
    rest = frac.lstrip("0")
    return " ".join(["zero"] * zeros + ([num_to_words(int(rest))] if rest else []))


def _int(s: str) -> int:
    return int(s.replace(".", ""))


def _money(m: re.Match, unit_one: str, unit_many: str, cents_word: bool = True) -> str:
    whole = _int(m.group(1))
    out = f"{num_to_words(whole)} {unit_one if whole == 1 else unit_many}"
    if m.group(2) and cents_word and int(m.group(2)):
        cents = int(m.group(2).ljust(2, "0"))
        out += f" e {num_to_words(cents)} {'centavo' if cents == 1 else 'centavos'}"
    return out


_LETTERS = {"A": "á", "B": "bê", "C": "cê", "D": "dê", "E": "é", "F": "éfe", "G": "gê", "H": "agá", "I": "i", "J": "jota",
            "K": "cá", "L": "éle", "M": "ême", "N": "êne", "O": "ó", "P": "pê", "Q": "quê", "R": "érre", "S": "ésse",
            "T": "tê", "U": "u", "V": "vê", "W": "dáblio", "X": "xis", "Y": "ípsilon", "Z": "zê"}
# siglas lidas letra a letra (as demais, como IPCA, Selic e IPVA, são lidas como palavra)
_SPELLED = {"CDB", "CDI", "LCI", "LCA", "CRI", "CRA", "FGC", "CET", "ETF", "ETFs", "FII", "FIIs", "IOF", "IR", "SPY", "VOO",
            "QQQ", "PGBL", "VGBL", "REIT", "REITs", "CLT", "CPF", "USD", "BRL"}
_ORDINALS = {1: "primeiro", 2: "segundo", 3: "terceiro", 4: "quarto", 5: "quinto", 6: "sexto", 7: "sétimo", 8: "oitavo",
             9: "nono", 10: "décimo", 11: "décimo primeiro", 12: "décimo segundo"}


def _spell(letters: str) -> str:
    return " ".join(_LETTERS.get(c, c) for c in letters.upper() if c.isalpha())


_NUM = r"(\d{1,3}(?:\.\d{3})+|\d+)"


def speak_pt(text: str) -> str:
    t = re.sub(r"[\"“”‘’«»]", "", text).replace("−", " menos ").replace("≈", " aproximadamente ")
    t = t.replace("²", " ao quadrado").replace("³", " ao cubo")
    t = t.replace("×", " vezes ").replace("÷", " dividido por ").replace("=", " igual a ")
    # tickers (IVVB11, PETR4, B3): letras soletradas + número por extenso
    t = re.sub(r"\b([A-Z]{1,5})(\d{1,2})\b", lambda m: f"{_spell(m.group(1))} {num_to_words(int(m.group(2)))}", t)
    t = re.sub(r"\b(" + "|".join(sorted(_SPELLED, key=len, reverse=True)) + r")\b", lambda m: _spell(m.group(1).rstrip("s")), t)
    t = re.sub(r"(?<=[A-Za-z])&(?=[A-Za-z])", " e ", t)                      # S&P -> S e P
    t = re.sub(r"(?<=[A-Za-z])-(?=\d)", " ", t)                              # Nasdaq-100 -> Nasdaq 100
    t = re.sub(r"(\d+)[ºª°]", lambda m: _ORDINALS.get(int(m.group(1)), num_to_words(int(m.group(1)))), t)
    t = re.sub(rf"US\$\s*{_NUM}(?:,(\d{{1,2}}))?", lambda m: _money(m, "dólar", "dólares"), t)
    t = re.sub(rf"R\$\s*{_NUM}(?:,(\d{{1,2}}))?", lambda m: _money(m, "real", "reais"), t)
    t = re.sub(rf"{_NUM},(\d+)\s?%", lambda m: f"{num_to_words(_int(m.group(1)))} vírgula {_decimal_words(m.group(2))} por cento", t)
    t = re.sub(rf"{_NUM}\s?%", lambda m: f"{num_to_words(_int(m.group(1)))} por cento", t)
    t = re.sub(r"(?<=\d)-(?=\d)", ", ", t)                                   # 50-30-20
    t = re.sub(rf"{_NUM},(\d+)", lambda m: f"{num_to_words(_int(m.group(1)))} vírgula {_decimal_words(m.group(2))}", t)
    t = re.sub(r"\b\d{1,3}(?:\.\d{3})+\b|\b\d+\b", lambda m: num_to_words(_int(m.group(0))), t)
    t = re.sub(r"(?<=[A-Za-zÀ-ú])\+", " mais", t)                            # IPCA+ -> IPCA mais
    t = t.replace("p.p.", "pontos percentuais")
    t = re.sub(r"\s+", " ", t).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", t)
