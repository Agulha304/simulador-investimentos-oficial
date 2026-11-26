"""Situações exclusivas de artistas e influenciadores (decisões que aparecem na tela): polêmicas, propostas, imprevistos e oportunidades."""
from datetime import date

from sqlalchemy.orm import Session

from backend.services import artist_influencer as inf
from backend.services import artist_rules as AR
from backend.services import life_service as ls
from backend.services import politics_rules as PR
from backend.services import politics_service as pols
from backend.services.artist_core import D, _add, _bump, _get, _income, _life, _pay_cash, _seed, _upd, fame, items, profile, skill
from backend.services.finance_ledger import ConflictError, FinanceError
from backend.services.goods_rules import hash01


def _eligible(db: Session, user_id: int, p, ref: date) -> list[str]:
    accs = inf.accounts(db, user_id)
    subs = max([sum(int(c.data["subs"]) for c in inf.channels_of(db, user_id, a.id)) for a in accs], default=0)
    band = next((b for b in items(db, user_id, "BAND", "ACTIVE")), None)
    works = len([w for w in items(db, user_id, "WORK") if w.name and w.data.get("work") == "PAINTING"])
    out = []
    rel = pols.public_relevance(db, user_id, p)
    has_term = bool(pols.terms(db, user_id))
    has_office = has_term or bool(items(db, user_id, "CAMPAIGN", "RUNNING"))
    for k, e in AR.EVENTS.items():
        n, d = e["need"], e["disc"]
        if d == "public" and rel < n.get("rel", 0):
            continue
        if d == "politics" and ((n.get("term") and not has_term) or (n.get("office") and not has_office)):
            continue
        if d == "influencer" and subs < n.get("subs", 0):
            continue
        if d == "music" and (not p.instrument or (n.get("band") and band is None) or fame(p, "music") < n.get("fame", 0)):
            continue
        if d == "acting" and (fame(p, "acting") < n.get("fame", 0) or skill(p, "acting") <= 10 and fame(p, "acting") <= 0):
            continue
        if d == "painting" and (works < n.get("works", 0) or fame(p, "painting") < n.get("fame", 0)):
            continue
        out.append(k)
    return out


def roll(db: Session, user_id: int, p, ref: date, seed: int) -> None:
    """Fim do mês: com alguma chance, surge UMA situação (se não houver outra esperando)."""
    if items(db, user_id, "DECISION", "OPEN"):
        return
    if hash01("ev-roll", seed, user_id, ref.isoformat()) >= AR.EVENT_P:
        return
    elig = _eligible(db, user_id, p, ref)
    if not elig:
        return
    recent = {x.data.get("event_key") for x in items(db, user_id, "DECISION") if x.created_month >= date(ref.year - 1, ref.month, 1)}
    pool = [k for k in elig if k not in recent] or elig
    key = pool[int(hash01("ev-pick", seed, user_id, ref.isoformat()) * len(pool))]
    e = AR.EVENTS[key]
    opts = [{"key": o["key"], "label": o["label"], "cost": o["cost"], "desc": ""} for o in e["options"]]
    _add(db, user_id, "DECISION", e["title"], ref, status="OPEN", work="EVENT", event_key=key, desc=e["desc"], options=opts, work_id=0)
    ls.log(db, user_id, ref, "ARTIST_EVENT", f"Situação: {e['title']}")


def resolve(db: Session, user_id: int, month, dec, option: str) -> dict:
    ref = month.ref_month
    e = AR.EVENTS[dec.data["event_key"]]
    o = next((x for x in e["options"] if x["key"] == option), None)
    if o is None:
        raise FinanceError("opção desconhecida")
    p = profile(db, user_id, lock=True)
    if o["cost"]:
        _pay_cash(db, user_id, month, o["cost"], o["label"], "Lazer")
    roll_v = hash01("ev-out", _seed(db, user_id), user_id, dec.id, option)
    acc, chosen = 0.0, o["outcomes"][-1]
    for prob, text, fx in o["outcomes"]:
        acc += prob
        if roll_v < acc:
            chosen = (prob, text, fx)
            break
    _, text, fx = chosen
    subs_all = [c for a in inf.accounts(db, user_id) for c in inf.channels_of(db, user_id, a.id)]
    total_subs = sum(int(c.data["subs"]) for c in subs_all)
    extra = []
    if fx.get("subs_pct") and subs_all:
        for c in subs_all:
            _upd(c, subs=max(0, int(int(c.data["subs"]) * (1 + fx["subs_pct"] / 100))))
        extra.append(f"{fx['subs_pct']:+.0f}% de inscritos")
    if fx.get("community"):
        for a in inf.accounts(db, user_id):
            _upd(a, community=max(0.0, min(100.0, float(a.data["community"]) + fx["community"])))
    disc = e["disc"]
    if fx.get("fame"):
        _bump(p, disc if disc in AR.DISCIPLINES else "politics", fame_d=fx["fame"])
    media = PR.MEDIA.get(pols.pol(p).get("media", "evasivo"), PR.MEDIA["evasivo"])
    var = media[2] if disc in ("politics", "public") else 1.0
    if fx.get("relevance"):                                              # polêmica: a postura com a mídia amplia (ou reduz) ganhos e perdas
        r = fx["relevance"]
        delta = r * var if r < 0 else r * (0.6 + 0.4 * var)
        known = [k for k, v in (p.fame or {}).items() if float(v) > 0 and k != "politics"]
        for k in known:
            _bump(p, k, fame_d=delta)
        if pols.terms(db, user_id) or disc == "politics" or float((p.fame or {}).get("politics", 0)) > 0:
            _bump(p, "politics", fame_d=delta)
        from backend.models import Company, CompanyStatus
        from sqlalchemy import select as _select
        for c in db.scalars(_select(Company).where(Company.user_id == user_id, Company.status == CompanyStatus.ACTIVE)):
            c.relevance = D(str(round(max(0.0, min(100.0, float(c.relevance) + delta * 0.3)), 2)))
        extra.append(f"relevância {delta:+.1f}")
    if fx.get("approval"):
        for t in pols.terms(db, user_id):
            a = fx["approval"] * (var if fx["approval"] < 0 else 1.0)
            _upd(t, approval=round(max(0.0, min(100.0, float(t.data["approval"]) + a)), 1))
        extra.append(f"aprovação {fx['approval']:+d}")
    if fx.get("skill"):
        _bump(p, disc, skill_d=fx["skill"])
    if fx.get("rep"):
        band = next((b for b in items(db, user_id, "BAND", "ACTIVE")), None)
        if band is not None:
            _upd(band, reputation=round(AR.clamp(float(band.data["reputation"]) + fx["rep"]), 2))
    money = float(fx.get("money", 0)) + float(fx.get("money_k", 0)) * total_subs / 1000
    if money > 0:
        _income(db, user_id, ref, e["title"], money)
        extra.append(f"+R$ {int(money)}")
    elif money < 0:
        lp = _life(db, user_id)
        ls.add_one_off(lp, f"life:artist:ev:{ref:%Y-%m}:{len(lp.one_offs or {})}", e["title"], -money, "Lazer", ref, "EXPENSE")
        extra.append(f"−R$ {int(-money)}")
    if fx.get("life"):
        lp = _life(db, user_id)
        for attr, delta in fx["life"].items():
            setattr(lp, attr, ls._clamp(getattr(lp, attr) + delta))
    return {"message": text + (f" ({'; '.join(extra)})" if extra else ""), "status": "EVENT"}
