"""Compra de empresas (aquisições). Todo mês o mercado traz empresas à venda de todos os portes (pequena, média e grande), em vários
países; cada uma tem avaliação própria (patrimônio, lucro e marca). Você NEGOCIA: faz ofertas e o dono aceita, contrapropõe ou recusa
conforme o quanto você paga em relação ao valor que ele aceita (preço mínimo oculto). Até 4 rodadas; oferta ofensiva duas vezes encerra a
conversa e outro comprador pode fechar antes. Fechado o negócio:
  * MERGE (mesmo segmento e país da sua empresa): vira filiais da sua empresa (ela paga) e a marca ganha relevância;
  * KEEP: vira uma empresa nova sua (você paga o preço do bolso e o capital de giro), com equipe, relevância e reputação da compra.
Regras puras no topo; banco embaixo (sem commit)."""
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import AcquisitionDeal, Company, CompanyEventType, CompanySegment, CompanySize, CompanyUnit, EmployeeRegime, FlowKind, SimMonth
from backend.services import company_rules as rules
from backend.services import company_team as team
from backend.services import country_rules as cr
from backend.services import world_service as ws
from backend.services.budget_service import require_open, shift_month
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError
from backend.services.goods_rules import hash01

D = Decimal
ZERO = D("0.00")
LISTINGS = 7
MAX_ROUNDS = 4
DEAL_TTL_MONTHS = 3
INSULT_RATIO = 0.60              # oferta abaixo de 60% do preço mínimo = ofensiva
COUNTER_RATIO = 0.88             # entre 88% e 100% do mínimo: o dono contrapropõe
RIVAL_P = 0.12                   # chance, a cada rodada sem acordo, de outro comprador fechar antes
SIZE_UNITS = {"SMALL": 1, "MEDIUM": 3, "LARGE": 6}      # filiais que a compra rende no MERGE
PREFIX = ("Boa Mesa", "Nova Era", "Prime", "Horizonte", "União", "Estrela", "Central", "Alfa", "Vértice", "Aurora", "Pioneira", "Sol Nascente", "Atlântica",
          "Real", "Maré", "Delta", "Bandeirante", "Imperial", "Vila Verde", "Orbital", "Cidade Viva", "Meridional", "Terra Forte", "Ponto Certo",
          "Alvorada", "Rota 66", "Pátria", "Cruzeiro", "Lume", "Atlas")


def _h(*parts) -> float:
    return hash01("acq", *parts)


def _seed(db: Session, user_id: int) -> int:
    from backend.services import company_service as cs
    return cs._seed(db, user_id)


def make_target(seed: int, ref: date, i: int, db: Session | None = None, user_id: int | None = None) -> dict:
    """Empresa à venda (determinística pela semente, mês e posição)."""
    key = f"A{ref:%Y%m}{i}"
    segs = list(CompanySegment)
    seg_key = segs[int(_h(seed, key, "seg") * len(segs))]
    seg = rules.SEGMENTS[seg_key]
    u = _h(seed, key, "size")
    size = CompanySize.SMALL if u < 0.5 else CompanySize.MEDIUM if u < 0.85 else CompanySize.LARGE
    codes = [c for c in cr.COUNTRIES if c != "BR"]
    country = "BR" if _h(seed, key, "ctry") < 0.65 else codes[int(_h(seed, key, "ctry2") * len(codes))]
    cc = cr.get(country)
    channel = rules.CompanyChannel.ONLINE if not seg.locations else rules.CompanyChannel.PHYSICAL
    rel = round(8 + 77 * _h(seed, key, "rel") ** 1.2, 1)
    loc = seg.default_location
    try:
        units = rules.expected_units(seg, loc, size) * rules.relevance_factor(rel) * rules.MARKET_DIFFICULTY * cc.market
    except Exception:
        units = seg.base_demand * rules.SIZES[size].demand * 0.5
    ratio = 1.0
    if db is not None and country != "BR":
        ratio = cc.cost_index * float(ws.fx(db, user_id, country, ref)) / cc.fx0
    else:
        ratio = cc.cost_index
    revenue = float(seg.price) * units * ratio
    margin = -0.05 + 0.27 * _h(seed, key, "margin") ** 0.9
    annual_rev = revenue * 12
    annual_profit = annual_rev * margin
    assets = float(rules.setup_cost(seg, size, channel)) * 0.6 * ratio
    multiple = 3.0 + 4.0 * _h(seed, key, "mult")
    fair = max(assets, annual_profit * multiple) + annual_rev * 0.15 * rel / 100
    fair = max(round(fair, -3), 5000.0)
    ask = round(fair * (1.15 + 0.25 * _h(seed, key, "greed")), -3)
    reserve = round(fair * (0.82 + 0.18 * _h(seed, key, "firm")), -2)
    staff = {"SMALL": (3, 8), "MEDIUM": (12, 30), "LARGE": (40, 90)}[size.value]
    employees = staff[0] + int((staff[1] - staff[0]) * _h(seed, key, "emp"))
    return {"key": key, "name": f"{PREFIX[int(_h(seed, key, 'name') * len(PREFIX))]} {seg.label}", "segment": seg_key.value, "segment_label": seg.label,
            "size": size.value, "size_label": rules.SIZES[size].label, "country": country, "country_name": cc.name, "flag": cc.flag, "currency": cc.currency,
            "relevance": rel, "reputation": int(45 + 40 * _h(seed, key, "rep")), "employees": employees, "monthly_revenue": round(revenue, 2),
            "annual_profit": round(annual_profit, 2), "margin_pct": round(margin * 100, 1), "assets": round(assets, 2), "valuation": fair,
            "ask": ask, "months_for_sale": 1 + int(3 * _h(seed, key, "age")), "_reserve": reserve}


def public(target: dict) -> dict:
    return {k: v for k, v in target.items() if not k.startswith("_")}


def listings(db: Session, user_id: int, ref: date) -> list[dict]:
    seed = _seed(db, user_id)
    return [make_target(seed, ref, i, db, user_id) for i in range(LISTINGS)]


# ------------------------------------------------------------------ negociação (pura)
def evaluate(offer: float, ask: float, reserve: float, rounds: int, insults: int, rival_roll: float) -> dict:
    """Resposta do dono: ACCEPT / COUNTER / REFUSE / WALK. `rounds` = rodadas já feitas (antes desta)."""
    if offer >= ask or offer >= reserve:
        return {"status": "ACCEPT", "ask": min(ask, offer)}
    if offer < reserve * INSULT_RATIO:
        return {"status": "WALK" if insults >= 1 else "REFUSE", "ask": ask, "insult": True}
    if rounds + 1 >= MAX_ROUNDS:
        return {"status": "WALK", "ask": ask}
    if rival_roll < RIVAL_P and offer < ask:
        return {"status": "WALK", "ask": ask, "rival": True}
    if offer >= reserve * COUNTER_RATIO:
        return {"status": "COUNTER", "ask": max(reserve * 1.01, round((ask + offer) / 2, -2))}
    return {"status": "REFUSE", "ask": max(reserve * 1.04, round(ask - (ask - reserve) * 0.25, -2))}


# ------------------------------------------------------------------ banco
def _deal(db: Session, user_id: int, key: str) -> AcquisitionDeal | None:
    return db.scalar(select(AcquisitionDeal).where(AcquisitionDeal.user_id == user_id, AcquisitionDeal.target_key == key))


def open_deals(db: Session, user_id: int, ref: date) -> list[AcquisitionDeal]:
    out = []
    for d in db.scalars(select(AcquisitionDeal).where(AcquisitionDeal.user_id == user_id, AcquisitionDeal.status == "OPEN").order_by(AcquisitionDeal.id)):
        if (ref.year - d.first_month.year) * 12 + ref.month - d.first_month.month > DEAL_TTL_MONTHS:
            d.status, d.closed_month = "WALKED", ref
            d.log = list(d.log or []) + [{"month": ref.isoformat(), "event": "A negociação esfriou e o dono desistiu da venda"}]
            continue
        out.append(d)
    return out


def view(db: Session, user_id: int, ref: date) -> dict:
    deals = {d.target_key: d for d in open_deals(db, user_id, ref)}
    done = list(db.scalars(select(AcquisitionDeal).where(AcquisitionDeal.user_id == user_id, AcquisitionDeal.status == "DONE").order_by(AcquisitionDeal.id.desc())))
    rows = []
    for t in listings(db, user_id, ref):
        d = deals.get(t["key"]) or _deal(db, user_id, t["key"])
        rows.append({**public(d.target if d else t), "ask_now": str(d.ask if d else D(str(t["ask"]))), "deal": _deal_out(d) if d else None})
    carry = [{**public(d.target), "ask_now": str(d.ask), "deal": _deal_out(d)} for k, d in deals.items() if k not in {r["key"] for r in rows}]
    return {"month": ref.isoformat(), "listings": rows + carry, "max_rounds": MAX_ROUNDS,
            "done": [{"name": d.target["name"], "price": str(d.price), "month": d.closed_month, "mode": (d.log[-1] or {}).get("mode") if d.log else None} for d in done]}


def _deal_out(d: AcquisitionDeal) -> dict:
    return {"id": d.id, "status": d.status, "rounds": d.rounds, "ask": str(d.ask), "last_offer": str(d.last_offer) if d.last_offer is not None else None,
            "log": d.log or [], "price": str(d.price) if d.price is not None else None}


def negotiate(db: Session, user_id: int, month: SimMonth, target_key: str, offer: Decimal, mode: str, buyer_company_id: int | None,
              name: str | None = None) -> dict:
    from backend.services import company_service as cs
    require_open(month)
    ref = month.ref_month
    mode = mode.upper()
    if mode not in ("MERGE", "KEEP"):
        raise FinanceError("escolha MERGE (incorporar à sua empresa) ou KEEP (empresa separada)")
    offer = quantize_money(offer)
    if offer <= 0:
        raise FinanceError("a oferta deve ser positiva")
    seed = _seed(db, user_id)
    deal = _deal(db, user_id, target_key)
    if deal is None:
        target = next((t for t in listings(db, user_id, ref) if t["key"] == target_key), None)
        if target is None:
            raise NotFoundError("essa empresa não está mais à venda")
        deal = AcquisitionDeal(user_id=user_id, target_key=target_key, target=target, status="OPEN", ask=D(str(target["ask"])), first_month=ref, log=[])
        db.add(deal)
        db.flush()
    if deal.status != "OPEN":
        raise ConflictError("essa negociação já foi encerrada")
    t = deal.target
    buyer = None
    if mode == "MERGE":
        if buyer_company_id is None:
            raise FinanceError("informe qual das suas empresas vai incorporar a compra")
        buyer = cs.get_company(db, user_id, buyer_company_id, lock=True)
        cs._active(buyer)
        if buyer.segment.value != t["segment"] or buyer.country != t["country"]:
            raise FinanceError("só dá para incorporar empresas do mesmo segmento e país; para outro segmento ou país, mantenha como empresa separada (KEEP)")
        if cs._opening(buyer, ref):
            raise ConflictError("sua empresa ainda está em abertura")
        n = SIZE_UNITS[t["size"]]
        if buyer.units - 1 + n > rules.MAX_BRANCHES:
            raise ConflictError(f"a incorporação passaria do limite de {rules.MAX_BRANCHES} filiais próprias")
    insults = sum(1 for e in (deal.log or []) if e.get("insult"))
    res = evaluate(float(offer), float(deal.ask), float(t["_reserve"]), deal.rounds, insults, _h(seed, target_key, "rival", deal.rounds))
    deal.rounds += 1
    deal.last_offer = offer
    entry = {"month": ref.isoformat(), "offer": str(offer), "status": res["status"], "insult": bool(res.get("insult"))}
    if res["status"] == "ACCEPT":
        price = offer
        deal.status, deal.price, deal.closed_month = "DONE", price, ref
        entry["mode"] = mode
        deal.log = list(deal.log or []) + [entry]
        deal.buyer_company_id = buyer.id if buyer else None
        out = _complete(db, user_id, month, t, price, mode, buyer, name)
        return {"status": "ACCEPTED", "message": f"{t['name']} aceitou {price}. {out['message']}", "price": str(price), **out}
    if res["status"] == "WALK":
        deal.status, deal.closed_month = "WALKED", ref
        msg = ("Outro comprador fechou negócio antes de você." if res.get("rival") else "O dono se ofendeu e encerrou a conversa." if res.get("insult")
               else "As rodadas acabaram sem acordo: o dono desistiu da venda.")
        entry["message"] = msg
        deal.log = list(deal.log or []) + [entry]
        return {"status": "WALKED", "message": msg}
    deal.ask = D(str(res["ask"]))
    msg = (f"Contraproposta: o dono aceita por {quantize_money(deal.ask)}." if res["status"] == "COUNTER"
           else f"O dono recusou. Ele ainda pede {quantize_money(deal.ask)}" + (" e achou a oferta ofensiva." if res.get("insult") else "."))
    entry["message"] = msg
    entry["ask"] = str(deal.ask)
    deal.log = list(deal.log or []) + [entry]
    return {"status": res["status"], "message": msg, "counter": str(quantize_money(deal.ask)), "rounds_left": MAX_ROUNDS - deal.rounds}


def _complete(db: Session, user_id: int, month: SimMonth, t: dict, price: Decimal, mode: str, buyer: Company | None, name: str | None) -> dict:
    from backend.services import company_service as cs
    ref = month.ref_month
    seg_key = CompanySegment(t["segment"])
    seg = rules.SEGMENTS[seg_key]
    gain = float(t["relevance"])
    if mode == "MERGE":
        cs._post(db, buyer, ref, kind=FlowKind.EXPENSE, amount=price, desc=f"Aquisição de {t['name']}", line="ACQUISITION", key=f"co:{buyer.id}:acq:{t['key']}")
        n = SIZE_UNITS[t["size"]]
        per = quantize_money(price / n)
        for k in range(n):
            db.add(CompanyUnit(company_id=buyer.id, kind="BRANCH", name=f"{t['name']} #{k + 1} (adquirida)", location=buyer.location, channel=buyer.channel,
                               site_mode=None, monthly_rent=ZERO, relevance=D(str(round(gain * 0.7, 2))), viability=D(str(round(0.8 + 0.4 * _h(t["key"], k, "v"), 3))),
                               status="OPEN", opened_month=ref, opens_month=shift_month(ref, 2), investment=per))
        buyer.units += n
        buyer.relevance = D(str(round(min(100.0, float(buyer.relevance) + gain * 0.15 * (1 - float(buyer.relevance) / 100)), 2)))
        cs._event(db, buyer, ref, CompanyEventType.EXPANSION, f"Incorporou {t['name']} por {price}: +{n} unidade(s) (operam em 2 meses) e marca mais forte", price)
        return {"message": f"Incorporada: +{n} unidade(s) na {buyer.name}, operando em 2 meses.", "company_id": buyer.id}
    # KEEP: empresa nova
    title = (name or t["name"]).strip()[:80]
    if db.scalar(select(Company.id).where(Company.user_id == user_id, Company.name == title)):
        title = f"{title} ({t['key']})"[:80]
    c = cs.create_company(db, user_id, month, name=title, segment=seg_key, size=CompanySize(t["size"]), country=t["country"],
                          channel=rules.CompanyChannel.ONLINE if not seg.locations else rules.CompanyChannel.PHYSICAL)
    cat = cs._category(db, user_id, FlowKind.EXPENSE, "Aquisição de empresas")
    from backend.services import finance_ledger
    finance_ledger.post_entry(db, user_id, kind=FlowKind.EXPENSE, amount=price, description=f"Aquisição de {t['name']}", ref_month=ref, entry_date=ref,
                              category_id=cat.id, origin=cs.EntryOrigin.COMPANY, origin_ref=f"company:{c.id}:acquisition", idempotency_key=f"acq:{c.id}:{t['key']}", capital=True)
    c.relevance = D(str(round(gain * 0.8, 2)))
    c.reputation = int(t["reputation"])
    c.acquired_from = t["name"]
    c.opens_month = shift_month(ref, 1)
    hired = _staff_up(db, c, seg, ref)
    cs._event(db, c, ref, CompanyEventType.CREATED, f"Comprada de {t['name']} por {price}: relevância {c.relevance}, reputação {c.reputation} e {hired} contratado(s) herdado(s)", price)
    return {"message": f"Nova empresa '{c.name}' criada com a equipe da compra ({hired} pessoas).", "company_id": c.id}


def _staff_up(db: Session, c: Company, seg: rules.Segment, ref: date) -> int:
    """Equipe herdada: cargos obrigatórios + equipe produtiva sugerida do porte (sem custo de contratação)."""
    from backend.services import company_service as cs
    seed = cs._seed(db, c.user_id)
    keys = list(rules.mandatory_roles(c.channel)) + rules.initial_staff(seg, c.size)
    n = 0
    for idx, rk in enumerate(keys):
        role = seg.role_for(rk, c.size)
        cand = team.build_candidate(seed, c.id, ref, role, EmployeeRegime.CLT, idx, kind="a")
        cs._create_employee(db, c, cand, role, cand.asking_salary, cand.hours_week, cand.schedule, EmployeeRegime.CLT, ref, via=" (equipe adquirida)")
        n += 1
    return n
