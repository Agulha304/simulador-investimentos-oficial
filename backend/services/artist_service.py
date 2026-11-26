"""Carreira de artista: ator, músico (emprego, freela, banda, músicas, álbum, shows), pintor (encomendas, quadros, divulgação) e
influenciador (canais, equipamentos, investimentos). Estado em `ArtistProfile` e `ArtistItem` (JSON). Nada aqui faz commit.

Dinheiro: pagamentos entram no orçamento do mês SEGUINTE (itens `life:artist:*`); gastos de equipamentos/aulas/divulgação entram no mês da
compra (`one_offs` do perfil). Tempo: ensaios, aulas, vídeos e quadros consomem as horas livres do mês. Sorteios são determinísticos
(semente da partida + mês), então repetir a mesma ação no mesmo mês dá o mesmo resultado."""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import ArtistItem, ArtistProfile, FlowKind, Person, Portfolio, Relationship, SimMonth
from backend.services import artist_rules as AR
from backend.services import budget_service, finance_ledger
from backend.services import life_service as ls
from backend.services.budget_service import require_open, shift_month
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError
from backend.services.goods_rules import hash01

D = Decimal
ZERO = D("0.00")
MAX_APPS = 5
APPLY_HOURS = 3


# ------------------------------------------------------------------ acesso
def _seed(db: Session, user_id: int) -> int:
    from backend.services import world_service
    return world_service._seed(db, user_id)


def profile(db: Session, user_id: int, lock: bool = False) -> ArtistProfile:
    q = select(ArtistProfile).where(ArtistProfile.user_id == user_id)
    p = db.scalar(q.with_for_update() if lock else q)
    if p is None:
        p = ArtistProfile(user_id=user_id, skills={k: 10.0 for k in AR.DISCIPLINES}, fame={k: 0.0 for k in AR.DISCIPLINES}, data={})
        db.add(p)
        db.flush()
    return p


def items(db: Session, user_id: int, kind: str, status: str | None = None) -> list[ArtistItem]:
    q = select(ArtistItem).where(ArtistItem.user_id == user_id, ArtistItem.kind == kind)
    if status:
        q = q.where(ArtistItem.status == status)
    return list(db.scalars(q.order_by(ArtistItem.id)))


def _add(db: Session, user_id: int, kind: str, name: str, ref: date, status: str = "ACTIVE", **data) -> ArtistItem:
    it = ArtistItem(user_id=user_id, kind=kind, status=status, name=name[:120], created_month=ref, data=data)
    db.add(it)
    db.flush()
    return it


def _upd(it: ArtistItem, **kv) -> None:
    it.data = {**(it.data or {}), **kv}


def _get(db: Session, user_id: int, item_id: int, kind: str) -> ArtistItem:
    it = db.get(ArtistItem, item_id)
    if it is None or it.user_id != user_id or it.kind != kind:
        raise NotFoundError("item não encontrado")
    return it


def skill(p: ArtistProfile, d: str) -> float:
    return float((p.skills or {}).get(d, 10.0))


def fame(p: ArtistProfile, d: str) -> float:
    return float((p.fame or {}).get(d, 0.0))


def _bump(p: ArtistProfile, d: str, skill_d: float = 0.0, fame_d: float = 0.0) -> None:
    p.skills = {**(p.skills or {}), d: round(AR.clamp(skill(p, d) + skill_d), 2)}
    p.fame = {**(p.fame or {}), d: round(AR.clamp(fame(p, d) + fame_d), 2)}


def _life(db: Session, user_id: int):
    return ls.get_profile(db, user_id, lock=True)


def _pay_cash(db: Session, user_id: int, month: SimMonth, amount: float | Decimal, name: str, cat: str = "Lazer") -> None:
    """Gasto à vista (entra no orçamento do mês); exige saldo."""
    amount = quantize_money(D(str(amount)))
    if amount <= 0:
        return
    bal = db.scalar(select(Portfolio.cash_balance).where(Portfolio.user_id == user_id)) or ZERO       # dinheiro pessoal
    if bal < amount:
        raise FinanceError(f"saldo insuficiente: {name} custa {amount} e você tem {bal}")
    lp = _life(db, user_id)
    ls.add_one_off(lp, f"life:artist:cost:{month.ref_month:%Y-%m}:{len(lp.one_offs or {})}", name, amount, cat, month.ref_month, "EXPENSE")


def _income(db: Session, user_id: int, ref: date, name: str, amount: float | Decimal, months_ahead: int = 1) -> None:
    amount = quantize_money(D(str(amount)))
    if amount > 0:
        _add(db, user_id, "PAYOUT", name, ref, status="PENDING", month=shift_month(ref, months_ahead).isoformat(), amount=str(amount))


def _resync(db: Session, user_id: int, month: SimMonth) -> None:
    from backend.services import career_hub
    career_hub.recalc_hours(db, user_id)
    ls.sync_month(db, user_id, month)


# ------------------------------------------------------------------ horas comprometidas
def committed_hours(db: Session, user_id: int) -> int:
    h = 0
    for ch in items(db, user_id, "CHANNEL", "ACTIVE"):
        d = ch.data
        per = AR.HOURS_PER_VIDEO * (0.6 if d.get("editor") else 1.0)
        h += int(d.get("cadence", 0) * per)
    if any(b.status == "ACTIVE" for b in items(db, user_id, "BAND")):
        h += 14
    h += sum(int(j.data.get("hours", 0)) for j in items(db, user_id, "JOB", "ACTIVE") if j.data.get("pay_type") == "MONTHLY")
    return h


# ------------------------------------------------------------------ treino e instrumento
def set_instrument(db: Session, user_id: int, month: SimMonth, instrument: str) -> ArtistProfile:
    require_open(month)
    if instrument not in AR.INSTRUMENTS:
        raise FinanceError("instrumento desconhecido")
    p = profile(db, user_id, lock=True)
    if p.instrument and p.instrument != instrument:
        _bump(p, "music", skill_d=-8.0)                                  # trocar de instrumento zera parte da prática
    p.instrument = instrument
    db.flush()
    return p


def train(db: Session, user_id: int, month: SimMonth, discipline: str) -> dict:
    require_open(month)
    if discipline not in AR.TRAIN:
        raise FinanceError("disciplina desconhecida")
    name, cost, hours, gain = AR.TRAIN[discipline]
    p = profile(db, user_id, lock=True)
    ref = month.ref_month
    key = f"train:{discipline}:{ref:%Y-%m}"
    if (p.data or {}).get(key):
        raise ConflictError("você já treinou essa área neste mês")
    ls.spend_hours(_life(db, user_id), hours, name)
    _pay_cash(db, user_id, month, cost, name, "Educação")
    cur = skill(p, discipline)
    real = gain * (1.0 - cur / 140)                                      # quanto mais habilidoso, mais devagar evolui
    _bump(p, discipline, skill_d=real)
    p.data = {**(p.data or {}), key: 1}
    _resync(db, user_id, month)
    return {"discipline": discipline, "skill": round(skill(p, discipline), 1), "gain": round(real, 2)}


# ------------------------------------------------------------------ ofertas (atuação, música, pintura)
def _pay(kind_tuple, seed, key: str, fame_v: float) -> int:
    lo, hi = kind_tuple
    return int((lo + (hi - lo) * hash01("pay", seed, key) ** 1.3) * (1 + fame_v / 200) / 10) * 10


def acting_offers(db: Session, user_id: int, ref: date) -> list[dict]:
    p, seed = profile(db, user_id), _seed(db, user_id)
    out, kinds = [], list(AR.ACTING_KINDS)
    for i in range(3):
        key = f"AC{ref:%Y%m}{i}"
        k = kinds[int(hash01("ak", seed, key) * len(kinds))]
        desc, monthly, lo, hi, months, need_fame, need_skill = AR.ACTING_KINDS[k]
        n = months[0] + int((months[1] - months[0]) * hash01("am", seed, key)) if months[1] > months[0] else months[0]
        out.append({"key": key, "discipline": "acting", "kind": k, "title": desc, "employer": ["Cia. Palco Aberto", "Estúdio Luz", "Produtora Vitória", "Teatro Municipal", "Agência Foco", "Rede Horizonte"][int(hash01("ae", seed, key) * 6)],
                    "monthly": monthly, "pay": _pay((lo, hi), seed, key, fame(p, "acting")), "months": n, "need_fame": need_fame, "need_skill": need_skill,
                    "chance": round(AR.hire_chance(skill(p, "acting"), fame(p, "acting"), need_skill, need_fame) * 100), "hours": 40 if monthly else 0})
    return out + _callbacks(db, user_id, "acting")


def music_offers(db: Session, user_id: int, ref: date) -> list[dict]:
    p, seed = profile(db, user_id), _seed(db, user_id)
    if not p.instrument:
        return []
    demand = AR.INSTRUMENTS[p.instrument][1]
    out, kinds = [], list(AR.MUSIC_JOB_KINDS)
    for i in range(4):
        key = f"MU{ref:%Y%m}{i}"
        k = kinds[int(hash01("mk", seed, key, p.instrument) * len(kinds))]
        desc, monthly, lo, hi, months, need_skill = AR.MUSIC_JOB_KINDS[k]
        n = months[0] + int((months[1] - months[0]) * hash01("mm", seed, key)) if months[1] > months[0] else months[0]
        band = AR.BAND_NAMES[int(hash01("mb", seed, key) * len(AR.BAND_NAMES))]
        out.append({"key": key, "discipline": "music", "kind": k, "title": f"{AR.INSTRUMENTS[p.instrument][0]} — {desc}", "employer": band, "monthly": monthly,
                    "pay": int(_pay((lo, hi), seed, key, fame(p, "music")) * demand ** 0.5 / 10) * 10, "months": n, "need_fame": 0, "need_skill": need_skill,
                    "chance": round(AR.hire_chance(skill(p, "music"), fame(p, "music"), need_skill, 0, demand) * 100), "hours": 20 if monthly else 0})
    return out + _callbacks(db, user_id, "music")


def commission_offers(db: Session, user_id: int, ref: date) -> list[dict]:
    p, seed = profile(db, user_id), _seed(db, user_id)
    out, kinds = [], list(AR.COMMISSION_KINDS)
    for i in range(3):
        key = f"PA{ref:%Y%m}{i}"
        k = kinds[int(hash01("ck", seed, key) * len(kinds))]
        desc, lo, hi, need_skill = AR.COMMISSION_KINDS[k]
        out.append({"key": key, "discipline": "painting", "kind": k, "title": desc, "employer": ["Cliente particular", "Restaurante Sabor", "Editora Folha", "Hotel Bela Vista", "Galeria Arte Viva", "Prefeitura"][int(hash01("ce", seed, key) * 6)],
                    "monthly": False, "pay": _pay((lo, hi), seed, key, fame(p, "painting")), "months": 1 + int(2 * hash01("cm", seed, key)), "need_fame": 0, "need_skill": need_skill,
                    "chance": round(AR.hire_chance(skill(p, "painting"), fame(p, "painting"), need_skill, 0) * 100), "hours": 18})
    return out + _callbacks(db, user_id, "painting")


def _callbacks(db: Session, user_id: int, discipline: str) -> list[dict]:
    return [{**o.data["offer"], "key": f"CB{o.id}", "callback_id": o.id, "chance": 100, "title": o.data["offer"]["title"] + " (convite para voltar)"}
            for o in items(db, user_id, "OFFER", "OPEN") if o.data.get("offer", {}).get("discipline") == discipline]


def _find_offer(db: Session, user_id: int, ref: date, discipline: str, key: str) -> dict:
    fn = {"acting": acting_offers, "music": music_offers, "painting": commission_offers}[discipline]
    o = next((x for x in fn(db, user_id, ref) if x["key"] == key), None)
    if o is None:
        raise NotFoundError("essa vaga não existe mais")
    return o


def apply_offer(db: Session, user_id: int, month: SimMonth, discipline: str, key: str) -> dict:
    require_open(month)
    ref = month.ref_month
    p = profile(db, user_id, lock=True)
    if discipline == "music" and not p.instrument:
        raise FinanceError("escolha o seu instrumento dominante primeiro")
    o = _find_offer(db, user_id, ref, discipline, key)
    if any(a.data.get("offer_key") == key for a in items(db, user_id, "APP")):
        raise ConflictError("você já se candidatou a essa vaga")
    apps = [a for a in items(db, user_id, "APP") if a.created_month == ref]
    if len(apps) >= MAX_APPS and not o.get("callback_id"):
        raise ConflictError(f"no máximo {MAX_APPS} candidaturas por mês")
    if o.get("callback_id"):
        cb = db.get(ArtistItem, o["callback_id"])
        cb.status = "USED"
        won = True
    else:
        ls.spend_hours(_life(db, user_id), APPLY_HOURS, "Testes e candidaturas de artista")
        won = hash01("hire", _seed(db, user_id), user_id, key) * 100 < o["chance"]
        _add(db, user_id, "APP", o["title"], ref, status="WON" if won else "LOST", offer_key=key)
    if not won:
        _life(db, user_id).satisfaction = ls._clamp(_life(db, user_id).satisfaction - 1)
        ls.log(db, user_id, ref, "ARTIST_REJECT", f"{o['employer']} não escolheu você para {o['title']}")
        db.flush()
        return {"hired": False, "message": f"{o['employer']} escolheu outra pessoa para {o['title']}."}
    start, end = shift_month(ref, 1), shift_month(ref, o["months"])
    job = _add(db, user_id, "JOB", o["title"], ref, discipline=discipline, employer=o["employer"], offer_kind=o["kind"], pay=o["pay"],
               pay_type="MONTHLY" if o["monthly"] else "ONEOFF", start=start.isoformat(), end=end.isoformat() if o["monthly"] else start.isoformat(), months=o["months"],
               hours=o.get("hours", 0), pay_month=start.isoformat(), callback=bool(o.get("callback_id")))
    ls.log(db, user_id, ref, "ARTIST_HIRED", f"{o['employer']} contratou você: {o['title']} ({o['pay']}{'/mês' if o['monthly'] else ''})")
    _resync(db, user_id, month)
    return {"hired": True, "message": f"Contratado(a)! {o['employer']}: {o['title']}, a partir de {start:%m/%Y}.", "job_id": job.id}


def quit_job(db: Session, user_id: int, month: SimMonth, job_id: int) -> None:
    require_open(month)
    j = _get(db, user_id, job_id, "JOB")
    if j.status != "ACTIVE":
        raise ConflictError("contrato já encerrado")
    j.status = "QUIT"
    _upd(j, end=month.ref_month.isoformat())
    _resync(db, user_id, month)


# ------------------------------------------------------------------ banda e música
def active_band(db: Session, user_id: int) -> ArtistItem | None:
    return next((b for b in items(db, user_id, "BAND", "ACTIVE")), None)


def _band_quality(band: ArtistItem, p: ArtistProfile) -> float:
    ms = band.data["members"]
    avg = sum(m["skill"] for m in ms) / len(ms)
    return AR.clamp(avg * 0.85 + min(len(ms), 4) * 3 + band.data.get("rehearsal", 0))


def create_band(db: Session, user_id: int, month: SimMonth, name: str, style: str) -> ArtistItem:
    require_open(month)
    p = profile(db, user_id, lock=True)
    if not p.instrument:
        raise FinanceError("escolha o seu instrumento dominante antes de abrir uma banda")
    if style not in AR.STYLES:
        raise FinanceError("estilo desconhecido")
    if active_band(db, user_id):
        raise ConflictError("você já tem uma banda ativa")
    name = name.strip()
    if not name:
        raise FinanceError("dê um nome à banda")
    me = {"name": "Você", "instrument": p.instrument, "skill": round(skill(p, "music"), 1), "source": "YOU"}
    b = _add(db, user_id, "BAND", name, month.ref_month, style=style, reputation=0.0, members=[me], gigs=0, songs=0, rehearsal=0)
    ls.log(db, user_id, month.ref_month, "BAND_CREATED", f"Você abriu a banda {name} ({AR.STYLES[style][0]})")
    _resync(db, user_id, month)
    return b


def market_musicians(db: Session, user_id: int, ref: date) -> list[dict]:
    seed = _seed(db, user_id)
    insts = list(AR.INSTRUMENTS)
    return [AR.draw_musician(seed, ref, i, insts[int(hash01("bmi", seed, ref.isoformat(), i) * len(insts))]) for i in range(8)]


def friend_musicians(db: Session, user_id: int) -> list[dict]:
    seed = _seed(db, user_id)
    out, insts = [], list(AR.INSTRUMENTS)
    for r in db.scalars(select(Relationship).where(Relationship.user_id == user_id, Relationship.stage != "ENDED").order_by(Relationship.id)):
        pe = db.get(Person, r.person_id)
        if pe is None or not pe.alive or hash01("friend-plays", seed, pe.id) > 0.45:        # só parte dos conhecidos toca algum instrumento
            continue
        inst = insts[int(hash01("friend-inst", seed, pe.id) * len(insts))]
        out.append({"key": f"F{pe.id}", "person_id": pe.id, "name": pe.name, "instrument": inst, "skill": int(20 + 55 * hash01("friend-skill", seed, pe.id)),
                    "ask": 0, "affinity": r.affinity})
    return out


def recruit(db: Session, user_id: int, month: SimMonth, key: str) -> dict:
    require_open(month)
    band = active_band(db, user_id)
    if band is None:
        raise ConflictError("abra uma banda primeiro")
    ms = list(band.data["members"])
    if len(ms) >= AR.BAND_MAX:
        raise ConflictError(f"a banda já tem {AR.BAND_MAX} integrantes")
    ref = month.ref_month
    pool = market_musicians(db, user_id, ref) + friend_musicians(db, user_id)
    cand = next((c for c in pool if c["key"] == key), None)
    if cand is None:
        raise NotFoundError("músico não encontrado")
    if any(m.get("key") == key for m in ms):
        raise ConflictError("ele(a) já está na banda")
    rep = float(band.data["reputation"])
    seed = _seed(db, user_id)
    if key.startswith("F"):
        chance = 0.45 + cand["affinity"] / 200
    else:
        chance = AR.clamp(0.30 + 0.5 * (1 - cand["skill"] / 100) + rep / 220, 0.08, 0.92)       # músico bom só topa banda que já tem nome
    if hash01("recruit", seed, user_id, key, band.id) >= chance:
        return {"joined": False, "message": f"{cand['name']} ({AR.INSTRUMENTS[cand['instrument']][0]}) recusou o convite."}
    ms.append({"key": key, "name": cand["name"], "instrument": cand["instrument"], "skill": cand["skill"], "source": "FRIEND" if key.startswith("F") else "MARKET"})
    _upd(band, members=ms)
    ls.log(db, user_id, ref, "BAND_JOIN", f"{cand['name']} entrou na banda {band.name}")
    return {"joined": True, "message": f"{cand['name']} entrou na banda!"}


def disband(db: Session, user_id: int, month: SimMonth) -> None:
    require_open(month)
    b = active_band(db, user_id)
    if b is None:
        raise ConflictError("você não tem banda")
    b.status = "ENDED"
    _resync(db, user_id, month)


def create_song(db: Session, user_id: int, month: SimMonth, scope: str, style: str, theme: str) -> dict:
    require_open(month)
    ref = month.ref_month
    p = profile(db, user_id, lock=True)
    if style not in AR.STYLES or theme not in AR.THEMES:
        raise FinanceError("estilo ou tema desconhecido")
    if scope == "BAND":
        band = active_band(db, user_id)
        if band is None:
            raise ConflictError("você não tem banda: abra uma ou componha em carreira solo")
        q_base = _band_quality(band, p)
        rep = float(band.data["reputation"])
    else:
        if not p.instrument:
            raise FinanceError("escolha o seu instrumento dominante primeiro")
        band, q_base, rep = None, skill(p, "music"), fame(p, "music")
    ls.spend_hours(_life(db, user_id), 12, "Compor uma música")
    n = len([w for w in items(db, user_id, "WORK") if w.data.get("work") == "SONG"])
    seed = _seed(db, user_id)
    idea = 0.30 + 0.5 * q_base / 100 + (0.08 if band and len(band.data["members"]) >= 3 else 0.0)
    if hash01("song-idea", seed, user_id, ref.isoformat(), n, style, theme) >= idea:
        ls.log(db, user_id, ref, "SONG_BLOCK", f"Vocês tentaram compor uma música de {AR.STYLES[style][0]} ({AR.THEMES[theme]}), mas a ideia não saiu")
        db.flush()
        return {"created": False, "message": "A ideia não veio desta vez. Tente de novo (de outro jeito, ou outro mês)."}
    q = AR.clamp(q_base * 0.75 + 25 * hash01("song-q", seed, user_id, ref.isoformat(), n) + (4 if style in ("pop", "sertanejo", "funk") else 0))
    title = f"{AR.THEMES[theme]} {['ao Luar', 'sem Fim', 'de Domingo', 'em Chamas', 'da Rua', 'do Coração'][n % 6]}"
    w = _add(db, user_id, "WORK", title, ref, status="PROMO", work="SONG", scope=scope, style=style, theme=theme, quality=round(q, 1), band_id=band.id if band else None, royalty=0.0, months_left=0)
    dec = _add(db, user_id, "DECISION", f"Como divulgar “{title}”?", ref, status="OPEN", work_id=w.id, work="SONG",
               options=[{"key": k, "label": v[0], "cost": v[1], "desc": v[2]} for k, v in AR.SONG_PROMO.items()])
    if band:
        _upd(band, songs=band.data.get("songs", 0) + 1)
    _bump(p, "music", skill_d=0.6)
    ls.log(db, user_id, ref, "SONG_CREATED", f"Nova música: “{title}” ({AR.STYLES[style][0]}, {AR.THEMES[theme]}), qualidade {q:.0f}")
    db.flush()
    return {"created": True, "message": f"Saiu uma música: “{title}” (qualidade {q:.0f})! Decida como divulgá-la.", "decision_id": dec.id, "work_id": w.id}


def _grow_rep(db: Session, user_id: int, work: ArtistItem, rep_d: float, fame_d: float) -> None:
    p = profile(db, user_id)
    if work.data.get("band_id"):
        b = db.get(ArtistItem, work.data["band_id"])
        if b is not None:
            _upd(b, reputation=round(AR.clamp(float(b.data["reputation"]) + rep_d), 2))
    _bump(p, "music", fame_d=fame_d)


def decide(db: Session, user_id: int, month: SimMonth, decision_id: int, option: str) -> dict:
    require_open(month)
    ref = month.ref_month
    dec = _get(db, user_id, decision_id, "DECISION")
    if dec.status != "OPEN":
        raise ConflictError("essa decisão já foi tomada")
    opt = next((o for o in dec.data["options"] if o["key"] == option), None)
    if opt is None:
        raise FinanceError("opção desconhecida")
    w = db.get(ArtistItem, dec.data["work_id"])
    p = profile(db, user_id, lock=True)
    seed = _seed(db, user_id)
    roll = hash01("promo", seed, user_id, dec.id, option)
    if opt["cost"]:
        _pay_cash(db, user_id, month, opt["cost"], opt["label"], "Lazer")
    q = float(w.data["quality"])
    msg = ""
    if dec.data["work"] == "SONG":
        sm = AR.STYLES[w.data["style"]][1]
        rep = 0.0
        if w.data.get("band_id"):
            b = db.get(ArtistItem, w.data["band_id"])
            rep = float(b.data["reputation"]) if b else 0.0
        else:
            rep = fame(p, "music")
        royalty, rep_d, fame_d, status = 0.0, 0.0, 0.0, "PUBLISHED"
        if option == "gravadora":
            if AR.label_accepts(q, rep, sm, roll):
                adv = int(3500 + q * 200 * sm)
                _income(db, user_id, ref, f"Adiantamento da gravadora — {w.name}", adv)
                royalty, rep_d, fame_d = q * 16 * sm, 7.0, 5.0
                msg = f"A gravadora quis “{w.name}”! Adiantamento de {adv}, divulgação profissional e royalties."
            else:
                status, royalty = "UNPROMOTED", 15.0
                msg = f"A gravadora recusou “{w.name}” (qualidade {q:.0f}, reputação {rep:.0f}). A música ficou guardada."
        elif option == "streaming":
            viral = roll < 0.03 + q / 450
            royalty, rep_d, fame_d = q * 6.5 * sm * (0.7 + 0.6 * roll) * (6 if viral else 1), 2.0 + (6 if viral else 0), 1.5 + (4 if viral else 0)
            msg = "A música viralizou nas plataformas!" if viral else "A música foi lançada nas plataformas."
        elif option == "clipe":
            viral = roll < 0.08 + q / 220
            royalty, rep_d, fame_d = q * 9 * sm * (5 if viral else 1), 4.0 + (8 if viral else 0), 3.0 + (5 if viral else 0)
            msg = "O clipe bombou nas redes!" if viral else "O clipe teve audiência razoável."
        elif option == "radio":
            if rep >= 20:
                royalty, rep_d, fame_d = q * 13 * sm, 4.0, 3.0
                msg = "A música tocou nas rádios da região."
            else:
                royalty, rep_d, fame_d = q * 3.5 * sm, 1.0, 0.5
                msg = "Poucas rádios aceitaram tocar uma banda ainda desconhecida."
        else:
            royalty, rep_d, fame_d = q * 2 * sm, 1.0, 0.5
            msg = "A música circulou entre amigos e nos shows."
        w.status = status
        _upd(w, royalty=round(royalty, 2), months_left=12, promo=option)
        _grow_rep(db, user_id, w, rep_d, fame_d)
    else:                                                               # pintura
        size_base = AR.PAINT_SIZES[w.data["size"]][3]
        price = size_base * (0.35 + 1.6 * q / 100) * (1 + fame(p, "painting") / 150)
        fp = fame(p, "painting")
        status = "SOLD"
        if option == "galeria":
            if q + fp * 0.5 >= 45 and roll < 0.7:
                _income(db, user_id, ref, f"Venda na galeria — {w.name}", price * 0.60, 1 + int(2 * roll))
                _bump(p, "painting", fame_d=3.0)
                msg = f"A galeria aceitou “{w.name}” e vendeu por {int(price)} (você fica com 60%)."
            else:
                status, msg = "UNSOLD", "A galeria recusou o quadro."
        elif option == "feira":
            if roll < 0.5 + q / 200:
                _income(db, user_id, ref, f"Venda na feira — {w.name}", price * 0.85)
                _bump(p, "painting", fame_d=1.5)
                msg = "O quadro foi vendido na feira."
            else:
                status, msg = "UNSOLD", "Ninguém levou o quadro na feira."
        elif option == "leilao":
            mult = 0.6 + 1.7 * roll * min(1.0, 0.4 + fp / 60)
            _income(db, user_id, ref, f"Leilão — {w.name}", price * mult * 0.85, 1 + int(2 * roll))
            _bump(p, "painting", fame_d=2.0 + (3 if mult > 1.5 else 0))
            msg = "O quadro foi a leilão e arrematado" + (" por um valor excelente!" if mult > 1.5 else ".")
        elif option == "redes":
            if roll < 0.25 + fp / 150 + q / 300:
                _income(db, user_id, ref, f"Venda direta — {w.name}", price * 0.9)
                _bump(p, "painting", fame_d=2.0)
                msg = "Um seguidor comprou o quadro."
            else:
                status, msg = "UNSOLD", "A publicação não rendeu venda."
        elif option == "loja":
            if roll < 0.7:
                _income(db, user_id, ref, f"Loja online — {w.name}", price * 0.7, 2)
                _bump(p, "painting", fame_d=1.0)
                msg = "O quadro vendeu pela loja online em alguns meses."
            else:
                status, msg = "UNSOLD", "O quadro não vendeu na loja online."
        else:
            _bump(p, "painting", fame_d=6.0)
            msg = "O quadro foi doado a um leilão beneficente: você ganhou fama e reputação."
        w.status = status
    dec.status = "DONE"
    _upd(dec, chosen=option, result=msg)
    ls.log(db, user_id, ref, "ARTIST_PROMO", msg)
    _resync(db, user_id, month)
    return {"message": msg, "status": w.status}


def play_gig(db: Session, user_id: int, month: SimMonth, tier: str, scope: str) -> dict:
    require_open(month)
    ref = month.ref_month
    p = profile(db, user_id, lock=True)
    if tier not in AR.VENUES:
        raise FinanceError("tipo de casa desconhecido")
    vname, need_rep, lo, hi = AR.VENUES[tier]
    if scope == "BAND":
        band = active_band(db, user_id)
        if band is None:
            raise ConflictError("você não tem banda")
        q, rep, n_members = _band_quality(band, p), float(band.data["reputation"]), len(band.data["members"])
    else:
        if not p.instrument:
            raise FinanceError("escolha o seu instrumento dominante primeiro")
        band, q, rep, n_members = None, skill(p, "music"), fame(p, "music"), 1
    ls.spend_hours(_life(db, user_id), 6, f"Oferecer show em {vname}")
    seed = _seed(db, user_id)
    key = f"gig:{tier}:{ref:%Y-%m}"
    if (p.data or {}).get(key):
        raise ConflictError(f"você já ofereceu show a esse tipo de casa neste mês")
    p.data = {**(p.data or {}), key: 1}
    chance = AR.clamp(0.25 + 0.012 * (rep - need_rep) + 0.004 * (q - 40), 0.04, 0.92) if rep >= need_rep * 0.5 else 0.03
    if hash01("gig", seed, user_id, tier, ref.isoformat()) >= chance:
        db.flush()
        return {"booked": False, "message": f"{vname}: não toparam contratar agora (chance era {chance * 100:.0f}%)."}
    pay = int((lo + (hi - lo) * hash01("gig-pay", seed, user_id, tier, ref.isoformat()) * (0.4 + q / 100)) / 10) * 10
    mine = pay / n_members if scope == "BAND" else pay
    _income(db, user_id, ref, f"Show em {vname}" + (f" — {band.name}" if band else ""), mine)
    gain = 1.5 + (0.6 if tier in ("casa_show", "festival") else 0)
    if band:
        _upd(band, reputation=round(AR.clamp(float(band.data["reputation"]) + gain * 1.6), 2), gigs=band.data.get("gigs", 0) + 1)
    _bump(p, "music", skill_d=0.5, fame_d=gain)
    ls.log(db, user_id, ref, "GIG", f"Show fechado em {vname}: {pay} (sua parte {int(mine)})")
    _resync(db, user_id, month)
    return {"booked": True, "message": f"{vname} contratou o show por {pay} (sua parte: {int(mine)}), pagos no mês que vem."}


def release_album(db: Session, user_id: int, month: SimMonth, scope: str, mode: str) -> dict:
    require_open(month)
    ref = month.ref_month
    p = profile(db, user_id, lock=True)
    songs = [w for w in items(db, user_id, "WORK") if w.data.get("work") == "SONG" and not w.data.get("album") and w.data.get("scope") == scope]
    if len(songs) < 6:
        raise ConflictError(f"um álbum precisa de pelo menos 6 músicas {'da banda' if scope == 'BAND' else 'solo'} (você tem {len(songs)} sem álbum)")
    if mode not in ("INDIE", "LABEL"):
        raise FinanceError("escolha INDIE ou LABEL")
    q = sum(float(s.data["quality"]) for s in songs[:12]) / len(songs[:12]) + 3
    rep = float(active_band(db, user_id).data["reputation"]) if scope == "BAND" and active_band(db, user_id) else fame(p, "music")
    seed = _seed(db, user_id)
    roll = hash01("album", seed, user_id, ref.isoformat(), len(songs))
    cost = 14000 if mode == "INDIE" else 0
    if cost:
        _pay_cash(db, user_id, month, cost, "Gravação e produção do álbum independente", "Lazer")
    sm = sum(AR.STYLES[s.data["style"]][1] for s in songs) / len(songs)
    if mode == "LABEL":
        ok = AR.label_accepts(q + 5, rep, sm, roll)
        if not ok:
            ls.log(db, user_id, ref, "ALBUM_REJECT", "Nenhuma gravadora quis bancar o álbum")
            db.flush()
            return {"released": False, "message": "A gravadora recusou bancar o álbum (qualidade/reputação insuficientes)."}
        adv = int(18000 + q * 450 * sm)
        _income(db, user_id, ref, "Adiantamento do álbum", adv)
    success = roll < 0.35 + q / 150 + (0.1 if mode == "LABEL" else 0)
    sales = int(q * 420 * sm * (1.6 if success else 0.4) * (1.4 if mode == "LABEL" else 1.0))
    for s in songs[:12]:
        _upd(s, album=True)
    _add(db, user_id, "WORK", f"Álbum ({'banda' if scope == 'BAND' else 'solo'}) #{len([1 for w in items(db, user_id, 'WORK') if w.data.get('work') == 'ALBUM']) + 1}", ref, status="PUBLISHED",
         work="ALBUM", scope=scope, quality=round(q, 1), royalty=float(sales), months_left=12, mode=mode, hit=success)
    b_now = active_band(db, user_id) if scope == "BAND" else None
    if b_now is not None:
        _upd(b_now, reputation=round(AR.clamp(float(b_now.data["reputation"]) + (10.0 if success else 2.0)), 2))
    _bump(p, "music", fame_d=8.0 if success else 1.5)
    msg = f"Álbum lançado ({'sucesso!' if success else 'fracasso de vendas'}): royalties de ~{sales}/mês nos primeiros meses."
    ls.log(db, user_id, ref, "ALBUM", msg)
    _resync(db, user_id, month)
    return {"released": True, "message": msg, "hit": success}


# ------------------------------------------------------------------ pintura
def paint(db: Session, user_id: int, month: SimMonth, theme: str, style: str, size: str) -> dict:
    require_open(month)
    ref = month.ref_month
    p = profile(db, user_id, lock=True)
    if theme not in AR.PAINT_THEMES or style not in AR.PAINT_STYLES or size not in AR.PAINT_SIZES:
        raise FinanceError("tema, estilo ou tamanho desconhecido")
    sname, mat, hours, _ = AR.PAINT_SIZES[size]
    ls.spend_hours(_life(db, user_id), hours, f"Pintar um quadro ({sname})")
    _pay_cash(db, user_id, month, mat, f"Material de pintura ({sname})", "Lazer")
    n = len([w for w in items(db, user_id, "WORK") if w.data.get("work") == "PAINTING"])
    seed = _seed(db, user_id)
    q = AR.clamp(skill(p, "painting") * 0.8 + 22 * hash01("paint-q", seed, user_id, ref.isoformat(), n) + (3 if AR.PAINT_STYLES[style][1] > 1.05 else 0))
    title = f"{AR.PAINT_THEMES[theme]} em {AR.PAINT_STYLES[style][0]} #{n + 1}"
    w = _add(db, user_id, "WORK", title, ref, status="PROMO", work="PAINTING", theme=theme, style=style, size=size, quality=round(q, 1))
    dec = _add(db, user_id, "DECISION", f"Como divulgar “{title}”?", ref, status="OPEN", work_id=w.id, work="PAINTING",
               options=[{"key": k, "label": v[0], "cost": v[1], "desc": v[2]} for k, v in AR.PAINT_PROMO.items()])
    _bump(p, "painting", skill_d=0.9)
    ls.log(db, user_id, ref, "PAINTED", f"Você pintou “{title}” (qualidade {q:.0f})")
    db.flush()
    return {"message": f"Quadro pronto: “{title}” (qualidade {q:.0f}). Decida como divulgá-lo.", "decision_id": dec.id, "work_id": w.id}


# ------------------------------------------------------------------ influenciador
def channels(db: Session, user_id: int) -> list[ArtistItem]:
    return items(db, user_id, "CHANNEL", "ACTIVE")


def create_channel(db: Session, user_id: int, month: SimMonth, platform: str, niche: str, name: str) -> ArtistItem:
    require_open(month)
    if platform not in AR.PLATFORMS or niche not in AR.NICHES:
        raise FinanceError("plataforma ou nicho desconhecido")
    name = name.strip()
    if not name:
        raise FinanceError("dê um nome ao canal")
    if len(channels(db, user_id)) >= AR.MAX_CHANNELS:
        raise ConflictError(f"no máximo {AR.MAX_CHANNELS} canais ao mesmo tempo")
    if any(c.data["platform"] == platform for c in channels(db, user_id)):
        raise ConflictError("você já tem um canal nessa plataforma")
    p = profile(db, user_id, lock=True)
    ch = _add(db, user_id, "CHANNEL", name, month.ref_month, platform=platform, niche=niche, subs=0, cadence=4, gear={k: 0 for k in AR.GEAR}, editor=False, thumbs=False,
              ads=False, contador=False, agency=False, merch=False, community=20.0, views=0, income=0, collabs=0, history=[])
    ls.log(db, user_id, month.ref_month, "CHANNEL_CREATED", f"Você criou o canal {name} ({AR.PLATFORMS[platform][0]}, {AR.NICHES[niche][0]})")
    _bump(p, "influencer", skill_d=0.5)
    _resync(db, user_id, month)
    return ch


def _channel(db: Session, user_id: int, cid: int) -> ArtistItem:
    ch = _get(db, user_id, cid, "CHANNEL")
    if ch.status != "ACTIVE":
        raise ConflictError("canal encerrado")
    return ch


def buy_gear(db: Session, user_id: int, month: SimMonth, cid: int, category: str) -> dict:
    require_open(month)
    ch = _channel(db, user_id, cid)
    if category not in AR.GEAR:
        raise FinanceError("equipamento desconhecido")
    gear = dict(ch.data["gear"])
    lvl = int(gear.get(category, 0))
    if lvl >= 5:
        raise ConflictError("esse equipamento já está no nível máximo")
    price = AR.GEAR[category][1][lvl]
    _pay_cash(db, user_id, month, price, f"{AR.GEAR[category][0]}: {AR.GEAR_LEVEL[lvl + 1]}", "Lazer")
    gear[category] = lvl + 1
    _upd(ch, gear=gear)
    ls.log(db, user_id, month.ref_month, "GEAR", f"Você comprou {AR.GEAR[category][0]} ({AR.GEAR_LEVEL[lvl + 1]}) para o canal {ch.name}")
    _resync(db, user_id, month)
    return {"message": f"{AR.GEAR[category][0]}: {AR.GEAR_LEVEL[lvl + 1]} (R$ {price}).", "gear": gear}


def invest(db: Session, user_id: int, month: SimMonth, cid: int, kind: str) -> dict:
    require_open(month)
    ch = _channel(db, user_id, cid)
    if kind not in AR.INVEST:
        raise FinanceError("investimento desconhecido")
    name, typ, cost, desc = AR.INVEST[kind]
    d, p, ref = ch.data, profile(db, user_id, lock=True), month.ref_month
    flag = {"editor": "editor", "thumbs": "thumbs", "ads": "ads", "contador": "contador", "agencia": "agency", "merch": "merch"}.get(kind)
    if flag and d.get(flag):
        raise ConflictError("você já tem isso (para encerrar, desligue-o)")
    if kind == "agencia" and int(d["subs"]) < 10000:
        raise ConflictError("a agência só aceita canais com pelo menos 10 mil inscritos")
    if cost and typ in ("ONCE", "MONTHLY"):
        _pay_cash(db, user_id, month, cost, name, "Lazer")
    msg = f"{name}: contratado."
    if kind == "curso":
        _bump(p, "influencer", skill_d=6.0)
        msg = "Você fez o curso: +6 de habilidade em criação de conteúdo."
    elif kind == "colab":
        got = int(hash01("collab", _seed(db, user_id), cid, ref.isoformat()) * (200 + int(d["subs"]) * 0.25))
        _upd(ch, collabs=int(d.get("collabs", 0)) + got, community=min(100.0, float(d["community"]) + 2))
        msg = f"A colaboração rendeu +{got} inscritos."
        _upd(ch, subs=int(d["subs"]) + got)
    elif kind == "evento":
        _upd(ch, community=min(100.0, float(d["community"]) + 18))
        msg = "O encontro fortaleceu a comunidade (mais fidelidade e venda de produtos)."
    elif flag:
        _upd(ch, **{flag: True})
    ls.log(db, user_id, ref, "CHANNEL_INVEST", f"{ch.name}: {msg}")
    _resync(db, user_id, month)
    return {"message": msg}


def stop_invest(db: Session, user_id: int, month: SimMonth, cid: int, kind: str) -> None:
    require_open(month)
    ch = _channel(db, user_id, cid)
    flag = {"editor": "editor", "thumbs": "thumbs", "ads": "ads", "contador": "contador", "agencia": "agency"}.get(kind)
    if not flag:
        raise FinanceError("esse investimento não pode ser desligado")
    _upd(ch, **{flag: False})
    _resync(db, user_id, month)


def set_cadence(db: Session, user_id: int, month: SimMonth, cid: int, cadence: int) -> None:
    require_open(month)
    ch = _channel(db, user_id, cid)
    if cadence not in AR.CADENCE:
        raise FinanceError(f"escolha entre {AR.CADENCE} vídeos por mês")
    _upd(ch, cadence=cadence)
    _resync(db, user_id, month)


def close_channel(db: Session, user_id: int, month: SimMonth, cid: int) -> None:
    require_open(month)
    ch = _channel(db, user_id, cid)
    ch.status = "CLOSED"
    _resync(db, user_id, month)


def _channel_month(db: Session, user_id: int, ch: ArtistItem, p: ArtistProfile, ref: date, seed: int) -> None:
    d = ch.data
    q = AR.channel_quality(skill(p, "influencer"), d["gear"], d.get("editor", False))
    tr = AR.trend(seed, d["niche"], ref)
    luck = hash01("luck", seed, ch.id, ref.isoformat())
    views = AR.month_views(int(d["subs"]), q, int(d["cadence"]), d["niche"], d["platform"], tr, d.get("ads", False), d.get("thumbs", False), luck)
    event = None
    r = hash01("chev", seed, ch.id, ref.isoformat())
    if r < 0.03 and d["cadence"] > 0:
        views, event = views * 4, "Um vídeo viralizou!"
    elif r > 0.992:
        event = "Polêmica nas redes: perdeu inscritos."
    gain = AR.sub_gain(views, q, d["niche"], d.get("ads", False))
    subs = int(d["subs"]) + gain
    if d["cadence"] == 0:
        subs = int(subs * 0.985)
    if event and event.startswith("Polêmica"):
        subs = int(subs * 0.9)
    ads_rev, shop = AR.channel_revenue(views, subs, d["platform"], d["niche"], d.get("merch", False), float(d.get("community", 20)))
    spons = AR.sponsorship(subs, d["niche"], d.get("agency", False), seed, ch.id, ref)
    gross = ads_rev + shop + spons
    tax = gross * AR.TAX_RATE * (0.5 if d.get("contador") else 1.0)
    agency = gross * 0.15 if d.get("agency") else 0.0
    net = max(0.0, gross - tax - agency)
    _income(db, user_id, ref, f"Canal {ch.name}: receita do mês", net)
    hist = list(d.get("history", []))[-23:] + [{"month": ref.isoformat(), "subs": subs, "views": views, "net": round(net)}]
    _upd(ch, subs=subs, views=views, income=round(net), community=max(5.0, min(100.0, float(d.get("community", 20)) + (0.8 if d["cadence"] >= 4 else -1.0))),
         history=hist, last={"quality": round(q, 1), "trend": tr, "ads": ads_rev, "shop": shop, "sponsor": spons, "tax": round(tax), "agency": round(agency), "gross": gross, "event": event})
    _bump(p, "influencer", skill_d=0.35 if d["cadence"] else 0.0, fame_d=min(0.4, gain / 8000))
    if event:
        ls.log(db, user_id, ref, "CHANNEL_EVENT", f"{ch.name}: {event}")


# ------------------------------------------------------------------ fechamento do mês e orçamento
def process_month(db: Session, lp, ref: date) -> None:
    user_id = lp.user_id
    p = db.scalar(select(ArtistProfile).where(ArtistProfile.user_id == user_id))
    if p is None:
        return
    seed = _seed(db, user_id)
    for ch in channels(db, user_id):
        _channel_month(db, user_id, ch, p, ref, seed)
    for j in items(db, user_id, "JOB", "ACTIVE"):
        d = j.data
        if d["pay_type"] == "MONTHLY":
            if date.fromisoformat(d["start"]) <= ref:
                _bump(p, d["discipline"], skill_d=0.4, fame_d=0.4)
            if date.fromisoformat(d["end"]) <= ref:
                j.status = "DONE"
        elif date.fromisoformat(d["pay_month"]) <= shift_month(ref, 1):
            j.status = "DONE"
            _bump(p, d["discipline"], skill_d=0.8, fame_d=0.8)
            if d["discipline"] in ("music", "acting", "painting") and not d.get("callback") and hash01("again", seed, j.id) < 0.28 + skill(p, d["discipline"]) / 250:
                again = {"key": "", "discipline": d["discipline"], "kind": d["offer_kind"], "title": j.name, "employer": d["employer"], "monthly": False,
                         "pay": int(d["pay"] * 1.12 / 10) * 10, "months": d.get("months", 1), "need_fame": 0, "need_skill": 0, "hours": d.get("hours", 0)}
                _add(db, user_id, "OFFER", f"{d['employer']} quer você de novo", ref, status="OPEN", offer=again)
                ls.log(db, user_id, ref, "ARTIST_CALLBACK", f"{d['employer']} gostou do seu trabalho e quer chamar você de novo")
    band = active_band(db, user_id)
    if band is not None:
        ms = list(band.data["members"])
        rep = float(band.data["reputation"])
        if len(ms) > 1 and hash01("band-quit", seed, band.id, ref.isoformat()) < 0.025 + (0.03 if rep < 10 else 0):
            gone = ms.pop(1 + int(hash01("band-quit-who", seed, band.id, ref.isoformat()) * (len(ms) - 1)))
            ls.log(db, user_id, ref, "BAND_LEAVE", f"{gone['name']} saiu da banda {band.name}")
        for m in ms:
            if m.get("source") != "YOU":
                m["skill"] = round(min(100, m["skill"] + 0.25), 1)
            else:
                m["skill"] = round(skill(p, "music"), 1)
        _upd(band, members=ms, reputation=round(max(0.0, rep - 0.5), 2), rehearsal=min(8, band.data.get("rehearsal", 0) + 0.5))
    for w in items(db, user_id, "WORK"):
        if w.data.get("royalty", 0) > 1 and w.data.get("months_left", 0) > 0 and w.status == "PUBLISHED":
            _income(db, user_id, ref, f"Royalties — {w.name}", w.data["royalty"])
            _upd(w, royalty=round(w.data["royalty"] * 0.9, 2), months_left=w.data["months_left"] - 1)
    for k in list((p.data or {})):                                     # limpa marcas de meses passados
        if k.startswith(("train:", "gig:")) and not k.endswith(f"{ref:%Y-%m}"):
            p.data = {kk: vv for kk, vv in p.data.items() if kk != k}
    db.flush()


def desired_items(db: Session, user_id: int, ref: date, want) -> None:
    p = db.scalar(select(ArtistProfile).where(ArtistProfile.user_id == user_id))
    if p is None:
        return
    for it in items(db, user_id, "PAYOUT"):
        if it.data["month"] == ref.isoformat():
            want(f"life:artist:payout:{it.id}", it.name, FlowKind.INCOME, "Renda extra", D(it.data["amount"]))
    for j in items(db, user_id, "JOB"):
        d = j.data
        if j.status in ("ACTIVE", "DONE") and d["pay_type"] == "MONTHLY" and date.fromisoformat(d["start"]) <= ref <= date.fromisoformat(d["end"]):
            want(f"life:artist:job:{j.id}", f"Artista: {j.name}", FlowKind.INCOME, "Renda extra", d["pay"])
        elif d["pay_type"] == "ONEOFF" and d["pay_month"] == ref.isoformat() and j.status != "QUIT":
            want(f"life:artist:job:{j.id}", f"Artista: {j.name}", FlowKind.INCOME, "Renda extra", d["pay"])
    for ch in channels(db, user_id):
        d = ch.data
        cost = (AR.INVEST["editor"][2] if d.get("editor") else 0) + (AR.INVEST["thumbs"][2] if d.get("thumbs") else 0) + \
               (AR.INVEST["ads"][2] if d.get("ads") else 0) + (AR.INVEST["contador"][2] if d.get("contador") else 0)
        if cost:
            want(f"life:artist:channelcost:{ch.id}", f"Custos do canal {ch.name}", FlowKind.EXPENSE, "Lazer", cost)


# ------------------------------------------------------------------ visão geral
def overview(db: Session, user_id: int, ref: date) -> dict:
    p = profile(db, user_id)
    seed = _seed(db, user_id)
    lp = ls.get_profile(db, user_id)
    band = active_band(db, user_id)
    works = items(db, user_id, "WORK")
    out_ch = []
    for ch in channels(db, user_id):
        d = ch.data
        q = AR.channel_quality(skill(p, "influencer"), d["gear"], d.get("editor", False))
        out_ch.append({"id": ch.id, "name": ch.name, "platform": d["platform"], "platform_name": AR.PLATFORMS[d["platform"]][0], "niche": d["niche"], "niche_name": AR.NICHES[d["niche"]][0],
                       "subs": d["subs"], "views": d["views"], "income": d["income"], "cadence": d["cadence"], "gear": d["gear"], "quality": round(q, 1), "community": round(float(d["community"]), 1),
                       "flags": {k: bool(d.get(k)) for k in ("editor", "thumbs", "ads", "contador", "agency", "merch")}, "monetized": d["subs"] >= AR.PLATFORMS[d["platform"]][1],
                       "monetize_at": AR.PLATFORMS[d["platform"]][1], "trend": AR.trend(seed, d["niche"], ref), "history": d.get("history", []), "last": d.get("last"),
                       "hours": int(d["cadence"] * AR.HOURS_PER_VIDEO * (0.6 if d.get("editor") else 1))})
    return {
        "instrument": p.instrument, "skills": {k: round(skill(p, k), 1) for k in AR.DISCIPLINES}, "fame": {k: round(fame(p, k), 1) for k in AR.DISCIPLINES},
        "free_hours": ls.free_hours(lp) - lp.hours_used, "committed_hours": committed_hours(db, user_id),
        "offers": {"acting": acting_offers(db, user_id, ref), "music": music_offers(db, user_id, ref), "painting": commission_offers(db, user_id, ref)},
        "applied": [a.data["offer_key"] for a in items(db, user_id, "APP") if a.created_month == ref],
        "jobs": [{"id": j.id, "title": j.name, "status": j.status, **j.data} for j in items(db, user_id, "JOB") if j.status in ("ACTIVE",) or j.data.get("pay_month", "") >= ref.isoformat()[:7]],
        "band": ({"id": band.id, "name": band.name, "style": band.data["style"], "style_name": AR.STYLES[band.data["style"]][0], "reputation": band.data["reputation"], "members": band.data["members"],
                  "quality": round(_band_quality(band, p), 1), "gigs": band.data.get("gigs", 0), "songs": band.data.get("songs", 0)} if band else None),
        "market_musicians": market_musicians(db, user_id, ref) if band else [], "friend_musicians": friend_musicians(db, user_id) if band else [],
        "works": [{"id": w.id, "name": w.name, "status": w.status, **{k: v for k, v in w.data.items()}} for w in works if w.name],
        "decisions": [{"id": d.id, "title": d.name, "work": d.data["work"], "options": d.data["options"]} for d in items(db, user_id, "DECISION", "OPEN")],
        "channels": out_ch, "payouts": [{"name": x.name, "month": x.data["month"], "amount": x.data["amount"]} for x in items(db, user_id, "PAYOUT") if x.data["month"] >= ref.isoformat()],
        "catalog": {
            "instruments": [{"key": k, "name": v[0], "demand": v[1]} for k, v in AR.INSTRUMENTS.items()], "styles": [{"key": k, "name": v[0], "market": v[1]} for k, v in AR.STYLES.items()],
            "themes": [{"key": k, "name": v} for k, v in AR.THEMES.items()], "venues": [{"key": k, "name": v[0], "need_rep": v[1], "min": v[2], "max": v[3]} for k, v in AR.VENUES.items()],
            "paint_styles": [{"key": k, "name": v[0]} for k, v in AR.PAINT_STYLES.items()], "paint_sizes": [{"key": k, "name": v[0], "material": v[1], "hours": v[2], "base": v[3]} for k, v in AR.PAINT_SIZES.items()],
            "paint_themes": [{"key": k, "name": v} for k, v in AR.PAINT_THEMES.items()], "platforms": [{"key": k, "name": v[0], "monetize_at": v[1], "cpm": v[2]} for k, v in AR.PLATFORMS.items()],
            "niches": [{"key": k, "name": v[0], "cpm_mult": v[1], "competition": v[2]} for k, v in AR.NICHES.items()],
            "gear": [{"key": k, "name": v[0], "prices": v[1]} for k, v in AR.GEAR.items()], "gear_levels": list(AR.GEAR_LEVEL),
            "invest": [{"key": k, "name": v[0], "type": v[1], "cost": v[2], "desc": v[3]} for k, v in AR.INVEST.items()], "cadence": list(AR.CADENCE),
            "train": {k: {"name": v[0], "cost": v[1], "hours": v[2]} for k, v in AR.TRAIN.items()}},
    }
