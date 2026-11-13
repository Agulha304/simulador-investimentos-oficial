"""Catálogo inicial de ativos + busca (local primeiro, fonte externa como complemento)."""
import logging

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.models import Asset, AssetClass, Currency
from backend.services import market_data

log = logging.getLogger(__name__)
S, E, F, R, C = AssetClass.STOCK, AssetClass.ETF, AssetClass.FII, AssetClass.REIT, AssetClass.CRYPTO


def _br(sym, name, cls):  # B3
    return (sym, name, cls, "B3", "BR", Currency.BRL, f"{sym}.SA")


def _us(sym, name, cls, ex="NASDAQ"):
    return (sym, name, cls, ex, "US", Currency.USD, sym)


def _cr(sym, name, ps):
    return (sym, name, C, "CRYPTO", None, Currency.USD, ps)


SEED: list[tuple] = [
    # Ações brasileiras
    *[_br(s, n, S) for s, n in [
        ("PETR4", "Petrobras PN"), ("PETR3", "Petrobras ON"), ("VALE3", "Vale"), ("ITUB4", "Itaú Unibanco PN"),
        ("BBDC4", "Bradesco PN"), ("BBAS3", "Banco do Brasil"), ("ABEV3", "Ambev"), ("WEGE3", "WEG"),
        ("B3SA3", "B3"), ("RENT3", "Localiza"), ("SUZB3", "Suzano"), ("GGBR4", "Gerdau PN"),
        ("JBSS3", "JBS"), ("LREN3", "Lojas Renner"), ("RADL3", "Raia Drogasil"), ("EQTL3", "Equatorial"),
        ("ELET3", "Eletrobras ON"), ("SBSP3", "Sabesp"), ("PRIO3", "PRIO"), ("RAIL3", "Rumo"),
        ("CSNA3", "CSN"), ("MGLU3", "Magazine Luiza"), ("HAPV3", "Hapvida"), ("TIMS3", "TIM"),
        ("VIVT3", "Vivo"), ("CMIG4", "Cemig PN"), ("BBSE3", "BB Seguridade"), ("KLBN11", "Klabin"),
    ]],
    # Ações internacionais
    *[_us(s, n, S, ex) for s, n, ex in [
        ("AAPL", "Apple", "NASDAQ"), ("MSFT", "Microsoft", "NASDAQ"), ("NVDA", "NVIDIA", "NASDAQ"),
        ("GOOGL", "Alphabet (Google) A", "NASDAQ"), ("AMZN", "Amazon", "NASDAQ"), ("META", "Meta Platforms", "NASDAQ"),
        ("TSLA", "Tesla", "NASDAQ"), ("NFLX", "Netflix", "NASDAQ"), ("AMD", "Advanced Micro Devices", "NASDAQ"),
        ("JPM", "JPMorgan Chase", "NYSE"), ("V", "Visa", "NYSE"), ("KO", "Coca-Cola", "NYSE"),
        ("DIS", "Walt Disney", "NYSE"), ("NKE", "Nike", "NYSE"), ("WMT", "Walmart", "NYSE"),
        ("XOM", "Exxon Mobil", "NYSE"), ("JNJ", "Johnson & Johnson", "NYSE"), ("MCD", "McDonald's", "NYSE"),
        ("BRK-B", "Berkshire Hathaway B", "NYSE"), ("INTC", "Intel", "NASDAQ"),
    ]],
    # ETFs brasileiros e internacionais
    *[_br(s, n, E) for s, n in [
        ("BOVA11", "iShares Ibovespa"), ("IVVB11", "iShares S&P 500"), ("SMAL11", "iShares Small Cap"),
        ("HASH11", "Hashdex Crypto Index"), ("GOLD11", "Trend Ouro"), ("DIVO11", "It Now IDIV"),
    ]],
    *[_us(s, n, E, "NYSE") for s, n in [
        ("SPY", "SPDR S&P 500 ETF"), ("QQQ", "Invesco QQQ (Nasdaq 100)"), ("VOO", "Vanguard S&P 500 ETF"),
        ("VTI", "Vanguard Total Stock Market"), ("IWM", "iShares Russell 2000"), ("SCHD", "Schwab US Dividend Equity"),
    ]],
    # FIIs
    *[_br(s, n, F) for s, n in [
        ("HGLG11", "CSHG Logística"), ("MXRF11", "Maxi Renda"), ("KNRI11", "Kinea Renda Imobiliária"),
        ("XPLG11", "XP Log"), ("XPML11", "XP Malls"), ("VISC11", "Vinci Shopping Centers"),
        ("BTLG11", "BTG Pactual Logística"), ("HGRU11", "CSHG Renda Urbana"), ("KNCR11", "Kinea Rendimentos"),
        ("VGHF11", "Valora Hedge Fund"), ("RECR11", "REC Recebíveis"), ("TRXF11", "TRX Real Estate"),
    ]],
    # REITs
    *[_us(s, n, R, "NYSE") for s, n in [
        ("O", "Realty Income"), ("AMT", "American Tower"), ("PLD", "Prologis"), ("SPG", "Simon Property Group"),
        ("PSA", "Public Storage"), ("EQIX", "Equinix"), ("CCI", "Crown Castle"), ("VICI", "VICI Properties"),
    ]],
    # Criptomoedas (cotadas em USD)
    _cr("BTC", "Bitcoin", "BTC-USD"), _cr("ETH", "Ethereum", "ETH-USD"), _cr("SOL", "Solana", "SOL-USD"),
    _cr("BNB", "BNB", "BNB-USD"), _cr("XRP", "XRP", "XRP-USD"), _cr("ADA", "Cardano", "ADA-USD"),
    _cr("DOGE", "Dogecoin", "DOGE-USD"), _cr("AVAX", "Avalanche", "AVAX-USD"), _cr("DOT", "Polkadot", "DOT-USD"),
    _cr("LINK", "Chainlink", "LINK-USD"), _cr("LTC", "Litecoin", "LTC-USD"), _cr("MATIC", "Polygon", "MATIC-USD"),
]


def seed_assets(db: Session) -> int:
    """Upsert idempotente do catálogo. Retorna quantos foram criados."""
    existing = {(a.symbol, a.exchange) for a in db.scalars(select(Asset))}
    created = 0
    for sym, name, cls, exch, country, cur, psym in SEED:
        if (sym, exch) in existing:
            continue
        db.add(Asset(symbol=sym, name=name, asset_class=cls, exchange=exch, country=country,
                     currency=cur, provider_symbol=psym, allows_fractional=(cls == C), extra={}))
        created += 1
    db.commit()
    if created:
        log.info("catálogo: %s ativos criados", created)
    return created


def _classify(hit: market_data.SearchHit) -> tuple[AssetClass, str, str | None, Currency]:
    ps = hit.provider_symbol
    if hit.quote_type == "CRYPTOCURRENCY":
        return C, "CRYPTO", None, Currency.USD
    if ps.endswith(".SA"):
        if hit.quote_type == "ETF":
            cls = E
        elif ps.removesuffix(".SA").endswith("11") and any(k in hit.name.lower() for k in ("fii", "fundo", "imobili")):
            cls = F
        else:
            cls = S
        return cls, "B3", "BR", Currency.BRL
    cls = E if hit.quote_type == "ETF" else (R if any(k in hit.name.lower() for k in ("realty", "reit", "properties", "trust")) else S)
    return cls, hit.exchange or "US", "US", Currency.USD


def _match(like: str):
    """Busca sem diferenciar maiúsculas nem acentos (itau -> Itaú)."""
    return or_(Asset.symbol.ilike(like), func.unaccent(Asset.name).ilike(func.unaccent(like)))


def search(db: Session, query: str, limit: int = 10) -> list[Asset]:
    q = query.strip()
    if not q:
        return []
    like = f"%{q}%"
    local = list(db.scalars(
        select(Asset).where(Asset.is_active, _match(like))
        .order_by((Asset.symbol.ilike(f"{q}%")).desc(), Asset.symbol).limit(limit)
    ))
    if len(local) >= 3 or len(q) < 2:
        return local
    # Complemento externo: cadastra o que for novo (somente moedas suportadas).
    for hit in market_data.search_remote(q):
        ps = hit.provider_symbol
        if not (ps.endswith(".SA") or "." not in ps) or "=" in ps or "^" in ps:
            continue  # só B3, EUA (sem sufixo) e cripto: outras bolsas têm moedas que não suportamos
        cls, exch, country, cur = _classify(hit)
        if db.scalar(select(Asset.id).where(Asset.provider_symbol == hit.provider_symbol)):
            continue
        db.add(Asset(symbol=hit.symbol, name=hit.name, asset_class=cls, exchange=exch, country=country,
                     currency=cur, provider_symbol=hit.provider_symbol, allows_fractional=(cls == C), extra={"auto": True}))
    try:
        db.commit()
    except Exception:  # corrida de cadastro duplicado: ignora
        db.rollback()
    return list(db.scalars(
        select(Asset).where(Asset.is_active, _match(like))
        .order_by((Asset.symbol.ilike(f"{q}%")).desc(), Asset.symbol).limit(limit)
    ))
