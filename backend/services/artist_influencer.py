"""Influenciador: CONTAS (uma por nicho/tema) com CANAIS em várias plataformas, equipamentos e investimentos por conta, vídeos postados
em uma, algumas ou todas as plataformas, vídeos temáticos (divulgar quadro, música, peça ou empresa), publi (patrocínios) e monetização
por metas reais de cada plataforma. Nada aqui faz commit."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import ArtistItem, Company, CompanyStatus
from backend.services import artist_rules as AR
from backend.services import life_service as ls
from backend.services.artist_core import D, _add, _bump, _get, _income, _life, _pay_cash, _resync, _seed, _upd, fame, items, profile, skill
from backend.services.budget_service import require_open
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError
from backend.services.goods_rules import hash01

FLAGS = {"editor": "editor", "thumbs": "thumbs", "ads": "ads", "contador": "contador", "agencia": "agency", "merch": "merch"}
VIDEO_HOURS = AR.HOURS_PER_VIDEO
EXTRA_PLATFORM_HOURS = 1.5


# ------------------------------------------------------------------ contas e canais
def accounts(db: Session, user_id: int) -> list[ArtistItem]:
    return items(db, user_id, "ACCOUNT", "ACTIVE")


def channels_of(db: Session, user_id: int, account_id: int) -> list[ArtistItem]:
    return [c for c in items(db, user_id, "CHANNEL", "ACTIVE") if c.data.get("account_id") == account_id]


def _account(db: Session, user_id: int, aid: int) -> ArtistItem:
    a = _get(db, user_id, aid, "ACCOUNT")
    if a.status != "ACTIVE":
        raise ConflictError("conta encerrada")
    return a


def _new_channel(db: Session, user_id: int, ref: date, acct: ArtistItem, platform: str) -> ArtistItem:
    return _add(db, user_id, "CHANNEL", f"{acct.name} ({AR.PLATFORMS[platform][0]})", ref, account_id=acct.id, platform=platform, subs=0, views=0, watch_h=0.0, posted=0,
                total_posted=0, income=0, history=[], last=None)


def create_account(db: Session, user_id: int, month, name: str, niche: str, platforms: list[str]) -> ArtistItem:
    require_open(month)
    if niche not in AR.NICHES:
        raise FinanceError("nicho desconhecido")
    plats = list(dict.fromkeys(platforms))
    if not plats or any(p not in AR.PLATFORMS for p in plats):
        raise FinanceError("escolha pelo menos uma plataforma válida")
    name = name.strip()
    if not name:
        raise FinanceError("dê um nome à conta")
    if len(accounts(db, user_id)) >= AR.MAX_ACCOUNTS:
        raise ConflictError(f"no máximo {AR.MAX_ACCOUNTS} contas (nichos) ao mesmo tempo")
    p = profile(db, user_id, lock=True)
    a = _add(db, user_id, "ACCOUNT", name, month.ref_month, niche=niche, gear={k: 0 for k in AR.GEAR}, editor=False, thumbs=False, ads=False, contador=False, agency=False,
             merch=False, community=20.0, collabs=0)
    for pl in plats:
        _new_channel(db, user_id, month.ref_month, a, pl)
    _bump(p, "influencer", skill_d=0.5)
    ls.log(db, user_id, month.ref_month, "ACCOUNT_CREATED", f"Você criou a conta “{name}” ({AR.NICHES[niche][0]}) em {', '.join(AR.PLATFORMS[x][0] for x in plats)}")
    _resync(db, user_id, month)
    return a


def add_channel(db: Session, user_id: int, month, aid: int, platform: str) -> ArtistItem:
    require_open(month)
    a = _account(db, user_id, aid)
    if platform not in AR.PLATFORMS:
        raise FinanceError("plataforma desconhecida")
    if any(c.data["platform"] == platform for c in channels_of(db, user_id, aid)):
        raise ConflictError("essa conta já tem canal nessa plataforma")
    ch = _new_channel(db, user_id, month.ref_month, a, platform)
    _resync(db, user_id, month)
    return ch


def close_account(db: Session, user_id: int, month, aid: int) -> None:
    require_open(month)
    a = _account(db, user_id, aid)
    a.status = "CLOSED"
    for c in channels_of(db, user_id, aid):
        c.status = "CLOSED"
    _resync(db, user_id, month)


def close_channel(db: Session, user_id: int, month, cid: int) -> None:
    require_open(month)
    c = _get(db, user_id, cid, "CHANNEL")
    c.status = "CLOSED"
    _resync(db, user_id, month)


# ------------------------------------------------------------------ equipamento e investimentos (por conta)
def buy_gear(db: Session, user_id: int, month, aid: int, category: str) -> dict:
    require_open(month)
    a = _account(db, user_id, aid)
    if category not in AR.GEAR:
        raise FinanceError("equipamento desconhecido")
    gear = dict(a.data["gear"])
    lvl = int(gear.get(category, 0))
    if lvl >= 5:
        raise ConflictError("esse equipamento já está no nível máximo")
    price = AR.GEAR[category][1][lvl]
    _pay_cash(db, user_id, month, price, f"{AR.GEAR[category][0]}: {AR.GEAR_LEVEL[lvl + 1]}", "Lazer")
    gear[category] = lvl + 1
    _upd(a, gear=gear)
    ls.log(db, user_id, month.ref_month, "GEAR", f"Você comprou {AR.GEAR[category][0]} ({AR.GEAR_LEVEL[lvl + 1]}) para a conta {a.name}")
    _resync(db, user_id, month)
    return {"message": f"{AR.GEAR[category][0]}: {AR.GEAR_LEVEL[lvl + 1]} (R$ {price}).", "gear": gear}


def invest(db: Session, user_id: int, month, aid: int, kind: str) -> dict:
    require_open(month)
    a = _account(db, user_id, aid)
    if kind not in AR.INVEST:
        raise FinanceError("investimento desconhecido")
    name, typ, cost, _ = AR.INVEST[kind]
    d, p, ref = a.data, profile(db, user_id, lock=True), month.ref_month
    flag = FLAGS.get(kind)
    if flag and d.get(flag):
        raise ConflictError("você já tem isso (para encerrar, desligue-o)")
    subs_total = sum(int(c.data["subs"]) for c in channels_of(db, user_id, aid))
    if kind == "agencia" and subs_total < 10000:
        raise ConflictError("a agência só aceita contas com pelo menos 10 mil inscritos somados")
    if cost and typ in ("ONCE", "MONTHLY"):
        _pay_cash(db, user_id, month, cost, name, "Lazer")
    msg = f"{name}: contratado."
    chs = channels_of(db, user_id, aid)
    if kind == "curso":
        _bump(p, "influencer", skill_d=6.0)
        msg = "Você fez o curso: +6 de habilidade em criação de conteúdo."
    elif kind == "colab" and chs:
        got = int(hash01("collab", _seed(db, user_id), aid, ref.isoformat()) * (200 + subs_total * 0.25))
        for c in chs:
            _upd(c, subs=int(c.data["subs"]) + got // len(chs))
        _upd(a, collabs=int(d.get("collabs", 0)) + got, community=min(100.0, float(d["community"]) + 2))
        msg = f"A colaboração rendeu +{got} inscritos (somando as plataformas)."
    elif kind == "evento":
        _upd(a, community=min(100.0, float(d["community"]) + 18))
        msg = "O encontro fortaleceu a comunidade (mais fidelidade e venda de produtos)."
    elif flag:
        _upd(a, **{flag: True})
    ls.log(db, user_id, ref, "ACCOUNT_INVEST", f"{a.name}: {msg}")
    _resync(db, user_id, month)
    return {"message": msg}


def stop_invest(db: Session, user_id: int, month, aid: int, kind: str) -> None:
    require_open(month)
    a = _account(db, user_id, aid)
    flag = {k: v for k, v in FLAGS.items() if k != "merch"}.get(kind)
    if not flag:
        raise FinanceError("esse investimento não pode ser desligado")
    _upd(a, **{flag: False})
    _resync(db, user_id, month)


def quality(db: Session, user_id: int, a: ArtistItem) -> float:
    p = profile(db, user_id)
    return AR.channel_quality(skill(p, "influencer"), a.data["gear"], a.data.get("editor", False))


# ------------------------------------------------------------------ vídeos
def _audience(db: Session, user_id: int, a: ArtistItem, chs: list[ArtistItem]) -> float:
    q = quality(db, user_id, a)
    return sum(int(c.data["subs"]) * (0.04 + 0.20 * q / 100) * AR.PLATFORMS[c.data["platform"]][3] for c in chs) + 50


def post_video(db: Session, user_id: int, month, aid: int, platforms: list[str], topic: str = "conteudo", ref_id: int | None = None) -> dict:
    """Cria UM vídeo e o publica nas plataformas escolhidas (uma, algumas ou todas). Vídeos temáticos divulgam um quadro, música, peça ou empresa."""
    require_open(month)
    ref = month.ref_month
    a = _account(db, user_id, aid)
    if topic not in AR.TOPICS:
        raise FinanceError("tipo de vídeo desconhecido")
    chs = [c for c in channels_of(db, user_id, aid) if c.data["platform"] in set(platforms)]
    if not chs or len({c.data["platform"] for c in chs}) != len(set(platforms)):
        raise FinanceError("escolha plataformas em que essa conta tem canal")
    hours = int(round(VIDEO_HOURS * (0.6 if a.data.get("editor") else 1.0) + EXTRA_PLATFORM_HOURS * (len(chs) - 1)))
    ls.spend_hours(_life(db, user_id), hours, f"Gravar e editar vídeo ({a.name})")
    p = profile(db, user_id, lock=True)
    seed = _seed(db, user_id)
    for c in chs:
        _upd(c, posted=int(c.data["posted"]) + 1, total_posted=int(c.data.get("total_posted", 0)) + 1)
    _bump(p, "influencer", skill_d=0.25)
    msg = f"Vídeo publicado em {', '.join(AR.PLATFORMS[c.data['platform']][0] for c in chs)} ({hours}h)."
    if topic != "conteudo":
        msg = _topic_effect(db, user_id, month, a, chs, topic, ref_id, seed, p) + f" ({hours}h)"
    ls.log(db, user_id, ref, "VIDEO", f"{a.name}: {msg}")
    _resync(db, user_id, month)
    return {"message": msg}


def _topic_effect(db: Session, user_id: int, month, a: ArtistItem, chs: list[ArtistItem], topic: str, ref_id: int | None, seed: int, p) -> str:
    ref = month.ref_month
    niche = a.data["niche"]
    f = AR.topic_fit(niche, topic)
    aud = _audience(db, user_id, a, chs)
    roll = hash01("topic", seed, a.id, ref.isoformat(), topic, ref_id, sum(int(c.data["total_posted"]) for c in chs))
    reach = min(1.0, 0.12 + aud / 4000)
    pct = (f - 0.45) * 6 * (0.5 + roll)                                           # encaixe baixo irrita a audiência e tira inscritos
    for c in chs:
        _upd(c, subs=max(0, int(int(c.data["subs"]) * (1 + pct / 100))))
    fit_txt = "combina com o seu nicho" if f >= 0.8 else "combina um pouco com o nicho" if f >= 0.45 else "não combina nada com o seu nicho"
    audience_txt = (f"o público gostou (+{pct:.1f}% de inscritos)" if pct > 0.2 else f"parte do público estranhou ({pct:.1f}% de inscritos)" if pct < -0.2 else "o público ficou indiferente")
    head = f"{AR.TOPICS[topic]}: {fit_txt}; {audience_txt}. "
    if ref_id is None:
        raise FinanceError("escolha o que você quer divulgar")
    if topic in ("painting", "song", "play"):
        w = _get(db, user_id, ref_id, "WORK" if topic != "play" else "JOB")
    if topic == "painting":
        if w.data.get("work") != "PAINTING" or w.status == "SOLD":
            raise ConflictError("escolha um quadro que ainda não foi vendido")
        q = float(w.data["quality"])
        price = AR.PAINT_SIZES[w.data["size"]][3] * (0.35 + 1.6 * q / 100) * (1 + fame(p, "painting") / 150)
        if roll < min(0.92, f * reach):
            _income(db, user_id, ref, f"Venda via vídeo — {w.name}", price * 0.9)
            w.status = "SOLD"
            _bump(p, "painting", fame_d=1.5)
            _close_open_decision(db, user_id, w.id)
            return head + f"Alguém comprou “{w.name}” por ~{int(price * 0.9)}."
        return head + "O quadro não vendeu desta vez."
    if topic == "song":
        if w.data.get("work") not in ("SONG", "ALBUM"):
            raise ConflictError("escolha uma música ou álbum")
        add = float(w.data["quality"]) * 0.8 * f * min(3.0, aud / 2500 + 0.3)
        _upd(w, royalty=round(float(w.data.get("royalty", 0)) + add, 2), months_left=max(12, int(w.data.get("months_left", 0))))
        if w.status in ("PROMO", "UNPROMOTED"):
            w.status = "PUBLISHED"
            _close_open_decision(db, user_id, w.id)
        _bump(p, "music", fame_d=0.8 * f)
        return head + f"Os royalties de “{w.name}” sobem ~{int(add)}/mês."
    if topic == "play":
        if w.data.get("offer_kind") != "teatro" or w.status != "ACTIVE":
            raise ConflictError("escolha uma peça de teatro em que você está contratado(a)")
        extra = min(6000.0, aud * f * 0.35)
        _income(db, user_id, ref, f"Bilheteria extra — {w.name}", extra)
        _bump(p, "acting", fame_d=1.0 * f)
        return head + f"A divulgação rendeu bilheteria extra de ~{int(extra)}."
    # empresa
    c = db.get(Company, ref_id)
    if c is None or c.user_id != user_id or c.status != CompanyStatus.ACTIVE:
        raise NotFoundError("empresa não encontrada")
    boost = min(0.30, 0.03 + f * aud / 40000)
    c.marketing_until = ref
    if c.marketing_until is not None:
        c.marketing_boost = D(str(round(boost, 3)))
    c.relevance = D(str(round(min(100.0, float(c.relevance) + min(3.0, f * aud / 8000)), 2)))
    return head + f"A empresa {c.name} ganha +{boost * 100:.0f}% de demanda neste mês e mais relevância."


def _close_open_decision(db: Session, user_id: int, work_id: int) -> None:
    for d in items(db, user_id, "DECISION", "OPEN"):
        if d.data.get("work_id") == work_id:
            d.status = "DONE"
            _upd(d, chosen="video", result="Divulgado em vídeo")


# ------------------------------------------------------------------ publi (patrocínios)
def sponsor_offers(db: Session, user_id: int, a: ArtistItem, ref: date) -> list[dict]:
    chs = channels_of(db, user_id, a.id)
    subs = sum(int(c.data["subs"]) for c in chs)
    if subs < 1000:
        return []
    seed = _seed(db, user_id)
    taken = {s.data.get("offer_key") for s in items(db, user_id, "SPONSOR")}
    n = min(3, 1 + int(hash01("sp-n", seed, a.id, ref.isoformat()) * (1 + subs / 20000)))
    q = quality(db, user_id, a)
    out = []
    for i in range(n):
        key = f"SP{ref:%Y%m}-{a.id}-{i}"
        if key in taken:
            continue
        brand, cat, bniche, base, risk = AR.SPONSORS[int(hash01("sp-b", seed, a.id, ref.isoformat(), i) * len(AR.SPONSORS))]
        fit = 1.0 if bniche == a.data["niche"] else 0.7 if bniche == "*" else 0.35
        pay = int(40 * base * subs ** 0.55 * (0.7 + 0.6 * q / 100) * (0.6 + 0.8 * hash01("sp-v", seed, a.id, ref.isoformat(), i)) * (0.5 + 0.5 * fit) / 10) * 10
        out.append({"key": key, "brand": brand, "category": cat, "fit": round(fit, 2), "risk": risk, "pay": pay,
                    "subs_effect_pct": round(-risk * 10 + (fit - 0.5) * 2, 1), "community_effect": round(-risk * 20, 1),
                    "warning": "Pode irritar o público e derrubar inscritos." if risk >= 0.5 else None})
    return out


def accept_sponsor(db: Session, user_id: int, month, aid: int, key: str) -> dict:
    require_open(month)
    ref = month.ref_month
    a = _account(db, user_id, aid)
    o = next((x for x in sponsor_offers(db, user_id, a, ref) if x["key"] == key), None)
    if o is None:
        raise NotFoundError("essa proposta de publi não existe mais")
    ls.spend_hours(_life(db, user_id), 8, f"Vídeo de publi ({o['brand']})")
    chs = channels_of(db, user_id, aid)
    pct = o["subs_effect_pct"] * (0.6 + 0.8 * hash01("sp-fx", _seed(db, user_id), key))
    for c in chs:
        _upd(c, subs=max(0, int(int(c.data["subs"]) * (1 + pct / 100))))
    _upd(a, community=max(0.0, min(100.0, float(a.data["community"]) + o["community_effect"])))
    agency = 0.85 if a.data.get("agency") else 1.0
    _income(db, user_id, ref, f"Publi: {o['brand']} ({a.name})", o["pay"] * agency)
    _add(db, user_id, "SPONSOR", f"{o['brand']} — {a.name}", ref, status="DONE", offer_key=key, pay=o["pay"])
    _bump(profile(db, user_id), "influencer", fame_d=0.6)
    msg = f"Publi fechada com {o['brand']}: {o['pay']} (no mês que vem). " + (f"O público reagiu mal ({pct:.1f}% de inscritos)." if pct < -0.5 else "O público aceitou bem." if pct > 0.3 else "")
    ls.log(db, user_id, ref, "SPONSOR", msg)
    _resync(db, user_id, month)
    return {"message": msg}


# ------------------------------------------------------------------ fechamento do mês
def month_stats(ch: ArtistItem) -> dict:
    h = ch.data.get("history", [])
    return {"watch_12m": sum(x.get("watch_h", 0) for x in h[-11:]), "uploads_90d": sum(x.get("posted", 0) for x in h[-2:]), "episodes": int(ch.data.get("total_posted", 0))}


def status_of(ch: ArtistItem) -> dict:
    """Situação de monetização do canal AGORA (com os números do último mês fechado)."""
    d, st = ch.data, month_stats(ch)
    last = d.get("history", [])[-1] if d.get("history") else {}
    return AR.tier_status(d["platform"], int(d["subs"]), watch_12m=st["watch_12m"] + float(last.get("watch_h", 0)) * 0, uploads_90d=st["uploads_90d"] + int(d["posted"]),
                          views_30d=int(d.get("views", 0)), streams_30d=int(last.get("posted", 0)) + int(d["posted"]), avg_viewers=float(last.get("avg_viewers", 0)),
                          episodes=st["episodes"], listen_30d=float(last.get("watch_h", 0)))


def process_month(db: Session, user_id: int, p, ref: date, seed: int) -> None:
    for a in accounts(db, user_id):
        d = a.data
        q = quality(db, user_id, a)
        tr = AR.trend(seed, d["niche"], ref)
        gross_total = 0.0
        shop_done = False
        for ch in channels_of(db, user_id, a.id):
            c = ch.data
            platform, posted = c["platform"], int(c["posted"])
            luck = hash01("luck", seed, ch.id, ref.isoformat())
            views = AR.month_views(int(c["subs"]), q, posted, d["niche"], platform, tr, d.get("ads", False), d.get("thumbs", False), luck)
            event = None
            r = hash01("chev", seed, ch.id, ref.isoformat())
            if r < 0.03 and posted > 0:
                views, event = views * 4, "Um vídeo viralizou!"
            gain = AR.sub_gain(views, q, d["niche"], d.get("ads", False))
            subs = int(c["subs"]) + gain
            if posted == 0:
                subs = int(subs * 0.985)
            watch_h = views * AR.AVG_MIN[platform] / 60
            hist = list(c.get("history", []))
            snap = {"month": ref.isoformat(), "subs": subs, "views": views, "watch_h": round(watch_h, 1), "posted": posted, "avg_viewers": round(views / max(1, posted) / 30, 2)}
            tmp = dict(c, subs=subs, views=views, posted=posted, history=hist, total_posted=int(c.get("total_posted", 0)))
            st = AR.tier_status(platform, subs, watch_12m=sum(x.get("watch_h", 0) for x in hist[-11:]) + watch_h, uploads_90d=sum(x.get("posted", 0) for x in hist[-2:]) + posted,
                                views_30d=views, streams_30d=posted, avg_viewers=snap["avg_viewers"], episodes=tmp["total_posted"], listen_30d=watch_h)
            ads_rev, fan, shop = AR.channel_money(platform, st["tier"], views, subs, d["niche"], float(d["community"]), d.get("merch", False) and not shop_done and st["tier"] is not None)
            if shop:
                shop_done = True
            gross = ads_rev + fan + shop
            tax = gross * AR.TAX_RATE * (0.5 if d.get("contador") else 1.0)
            agency = gross * 0.15 if d.get("agency") else 0.0
            net = max(0.0, gross - tax - agency)
            gross_total += net
            snap["net"] = round(net)
            hist = (hist + [snap])[-24:]
            _upd(ch, subs=subs, views=views, watch_h=round(watch_h, 1), posted=0, income=round(net), history=hist,
                 last={"quality": round(q, 1), "trend": tr, "ads": ads_rev, "fan": fan, "shop": shop, "tax": round(tax), "agency": round(agency), "gross": gross,
                       "event": event, "tier": st["tier"]["key"] if st["tier"] else None, "tier_label": st["tier"]["label"] if st["tier"] else None, "next": st["next"]})
            _bump(p, "influencer", skill_d=0.3 if posted else 0.0, fame_d=min(0.4, gain / 8000))
        if gross_total > 0:
            _income(db, user_id, ref, f"Conta {a.name}: receita do mês", gross_total)
        _upd(a, community=max(5.0, min(100.0, float(d.get("community", 20)) + (0.8 if sum(c.data.get("history", [{}])[-1].get("posted", 0) for c in channels_of(db, user_id, a.id)) >= 4 else -1.0))))


def monthly_costs(db: Session, user_id: int):
    for a in accounts(db, user_id):
        d = a.data
        cost = (AR.INVEST["editor"][2] if d.get("editor") else 0) + (AR.INVEST["thumbs"][2] if d.get("thumbs") else 0) + \
               (AR.INVEST["ads"][2] if d.get("ads") else 0) + (AR.INVEST["contador"][2] if d.get("contador") else 0)
        if cost:
            yield a, cost


# ------------------------------------------------------------------ visão geral
def overview(db: Session, user_id: int, ref: date) -> dict:
    seed = _seed(db, user_id)
    out = []
    for a in accounts(db, user_id):
        d = a.data
        chs = []
        for ch in channels_of(db, user_id, a.id):
            c = ch.data
            st = status_of(ch)
            chs.append({"id": ch.id, "platform": c["platform"], "platform_name": AR.PLATFORMS[c["platform"]][0], "subs": c["subs"], "views": c["views"], "income": c["income"],
                        "posted": c["posted"], "watch_h": c.get("watch_h", 0), "history": c.get("history", []), "last": c.get("last"),
                        "tier": ({"key": st["tier"]["key"], "label": st["tier"]["label"]} if st["tier"] else None), "next": st["next"]})
        out.append({"id": a.id, "name": a.name, "niche": d["niche"], "niche_name": AR.NICHES[d["niche"]][0], "gear": d["gear"], "quality": round(quality(db, user_id, a), 1),
                    "community": round(float(d["community"]), 1), "trend": AR.trend(seed, d["niche"], ref), "flags": {k: bool(d.get(v)) for k, v in FLAGS.items()},
                    "channels": chs, "sponsors": sponsor_offers(db, user_id, a, ref),
                    "hours_per_video": int(round(VIDEO_HOURS * (0.6 if d.get("editor") else 1.0)))})
    works = [w for w in items(db, user_id, "WORK") if w.name]
    jobs = [j for j in items(db, user_id, "JOB", "ACTIVE") if j.data.get("offer_kind") == "teatro"]
    comps = list(db.scalars(select(Company).where(Company.user_id == user_id, Company.status == CompanyStatus.ACTIVE).order_by(Company.id)))
    return {"accounts": out,
            "promotable": {"painting": [{"id": w.id, "name": w.name} for w in works if w.data.get("work") == "PAINTING" and w.status != "SOLD"],
                           "song": [{"id": w.id, "name": w.name} for w in works if w.data.get("work") in ("SONG", "ALBUM")],
                           "play": [{"id": j.id, "name": j.name} for j in jobs], "company": [{"id": c.id, "name": c.name} for c in comps]},
            "topics": [{"key": k, "name": v} for k, v in AR.TOPICS.items()]}
