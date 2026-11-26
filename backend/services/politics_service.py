"""Carreira política (partido, propostas, mídia, candidatura, campanha, mandato) e concursos públicos. Estado em `ArtistProfile.data["pol"]`
e em itens `CAMPAIGN` (disputas), `TERM` (mandatos) e `CONCURSO` (inscrições). Nada aqui faz commit."""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import ArtistItem, FlowKind, LifeProfile
from backend.services import artist_rules as AR
from backend.services import budget_service, finance_ledger, item_sync
from backend.services import life_service as ls
from backend.services import politics_rules as P
from backend.services.artist_core import _add, _bump, _get, _income, _life, _pay_cash, _resync, _seed, _upd, fame, items, profile, skill
from backend.services.budget_service import months_between, require_open, shift_month
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError
from backend.services.goods_rules import hash01

D = Decimal


# ------------------------------------------------------------------ perfil político
def pol(p) -> dict:
    return dict((p.data or {}).get("pol", {}))


def _set_pol(p, **kv) -> None:
    p.data = {**(p.data or {}), "pol": {**pol(p), **kv}}


def set_profile(db: Session, user_id: int, month, party: str | None, ideology: str | None, proposals: list[str] | None, media: str | None) -> dict:
    require_open(month)
    p = profile(db, user_id, lock=True)
    st, ref = pol(p), month.ref_month
    kv = {}
    if party is not None and party != st.get("party"):
        raise FinanceError("para entrar em um partido peça a filiação (o partido pode recusar); a troca é feita em /party")
    if ideology is not None:
        if ideology not in P.IDEOLOGIES:
            raise FinanceError("lado político desconhecido")
        kv["ideology"] = ideology
    if proposals is not None:
        if len(set(proposals)) != len(proposals) or len(proposals) > P.MAX_PROPOSALS or any(x not in P.PROPOSALS for x in proposals):
            raise FinanceError(f"escolha até {P.MAX_PROPOSALS} propostas diferentes da lista")
        kv["proposals"] = list(proposals)
    if media is not None:
        if media not in P.MEDIA:
            raise FinanceError("postura com a mídia desconhecida")
        kv["media"] = media
    _set_pol(p, **kv)
    ls.log(db, user_id, ref, "POLITICS_PROFILE", "Você atualizou o seu perfil político")
    db.flush()
    return pol(p)


# ------------------------------------------------------------------ calendário eleitoral
def election_date(office: str, ref: date) -> date:
    """Próxima eleição do cargo (outubro; municipais em anos múltiplos de 4 a partir de 2028; gerais em 2030, 2034...)."""
    cycle = P.OFFICES[office][2]
    offset = 0 if cycle == "municipal" else 2
    y = ref.year
    while True:
        if y % 4 == offset and (y > ref.year or ref.month <= P.ELECTION_MONTH):
            return date(y, P.ELECTION_MONTH, 1)
        y += 1


def _mood(seed: int, year: int) -> dict:
    """O humor do eleitorado naquele ano: lado político em alta (-2..2) e a importância de cada tema."""
    lean = (hash01("mood", seed, year) - 0.5) * 3.0
    sal = {k: 0.3 + hash01("sal", seed, year, k) for k in P.PROPOSALS}
    tot = sum(sal.values())
    return {"lean": round(lean, 2), "salience": {k: v / tot for k, v in sal.items()}}


def _fit(proposals: list[str], mood: dict, ideology: int) -> float:
    if not proposals:
        return 0.0
    s = 0.0
    for k in proposals:
        lean = P.PROPOSALS[k][1]
        s += mood["salience"][k] * len(P.PROPOSALS) * (1 - abs(lean - mood["lean"]) / 4)
    return max(0.0, min(1.0, s / len(proposals) * 0.9))


def _ideo_fit(ideology: int, mood: dict) -> float:
    return max(0.0, 1 - abs(ideology - mood["lean"]) / 4)


def public_relevance(db: Session, user_id: int, p) -> float:
    """Relevância pública 0..100: fama política pesa mais; as demais áreas e as empresas conhecidas somam."""
    f = p.fame or {}
    others = sorted((float(v) for k, v in f.items() if k != "politics"), reverse=True)
    return min(100.0, float(f.get("politics", 0)) + 0.5 * (others[0] if others else 0) + 0.2 * (others[1] if len(others) > 1 else 0))


def popularity(db: Session, user_id: int, p) -> float:
    """Popularidade da pessoa (0..100): quanto ela é conhecida por música, atuação, cinema, pintura, internet, política ou por uma empresa. Sem fama, é zero."""
    from sqlalchemy import select as _select
    from backend.models import Company, CompanyStatus
    fames = [float(v) for v in (p.fame or {}).values()]
    top = max(fames, default=0.0)
    second = sorted(fames, reverse=True)[1] if len(fames) > 1 else 0.0
    comp = max((float(c.relevance) for c in db.scalars(_select(Company).where(Company.user_id == user_id, Company.status == CompanyStatus.ACTIVE))), default=0.0)
    return round(min(100.0, 0.62 * top + 0.10 * second + 0.30 * comp * 0.8), 1)


def _compat(p, party_key: str) -> float:
    party = P.PARTIES.get(party_key)
    if party is None:
        return 0.0
    return 1 - abs(P.IDEOLOGIES.get(pol(p).get("ideology", "centro"), 0) - party[1]) / 4


def party_chance(db: Session, user_id: int, p, party_key: str) -> float:
    """Chance de o partido ADMITIR você: partidos fortes são mais exigentes; fama e afinidade ideológica ajudam."""
    pop = popularity(db, user_id, p) / 100
    strength = P.PARTIES[party_key][2]
    return round(max(0.05, min(0.92, 0.80 - 0.35 * strength + 0.35 * pop + 0.35 * (_compat(p, party_key) - 0.5))), 3)


def join_party(db: Session, user_id: int, month, party_key: str) -> dict:
    require_open(month)
    if party_key not in P.PARTIES:
        raise FinanceError("partido desconhecido")
    p = profile(db, user_id, lock=True)
    st, ref = pol(p), month.ref_month
    if st.get("party") == party_key:
        raise ConflictError("você já é filiado(a) a esse partido")
    if items(db, user_id, "CAMPAIGN", "RUNNING"):
        raise ConflictError("encerre ou conclua a campanha antes de trocar de partido")
    refused = dict(st.get("party_refused", {}))
    last = refused.get(party_key)
    if last and months_between(date.fromisoformat(last), ref) < P.PARTY_RETRY_MONTHS:
        wait = P.PARTY_RETRY_MONTHS - months_between(date.fromisoformat(last), ref)
        raise ConflictError(f"esse partido recusou você recentemente: tente de novo em {wait} {'mês' if wait == 1 else 'meses'}")
    chance = party_chance(db, user_id, p, party_key)
    name = P.PARTIES[party_key][0]
    if hash01("party-admit", _seed(db, user_id), user_id, party_key, ref.isoformat(), st.get("party_tries", 0)) >= chance:
        refused[party_key] = ref.isoformat()
        _set_pol(p, party_refused=refused, party_tries=int(st.get("party_tries", 0)) + 1)
        ls.log(db, user_id, ref, "PARTY_REFUSED", f"O {name} recusou a sua filiação (a chance era {chance * 100:.0f}%)")
        db.flush()
        return {"joined": False, "message": f"O {name} não quis admitir você agora (chance era {chance * 100:.0f}%). Tente outro partido ou volte em {P.PARTY_RETRY_MONTHS} meses."}
    _set_pol(p, party=party_key, joined=ref.isoformat(), nom_refused={})
    ls.log(db, user_id, ref, "PARTY_JOINED", f"Você foi admitido(a) no {name}")
    db.flush()
    return {"joined": True, "message": f"O {name} admitiu você como filiado(a)! Para ser candidato(a), o partido ainda precisa querer você para o cargo."}


def leave_party(db: Session, user_id: int, month) -> dict:
    require_open(month)
    p = profile(db, user_id, lock=True)
    if not pol(p).get("party"):
        raise ConflictError("você não é filiado(a) a nenhum partido")
    if items(db, user_id, "CAMPAIGN", "RUNNING"):
        raise ConflictError("encerre ou conclua a campanha antes de sair do partido")
    _set_pol(p, party=None, joined=None)
    ls.log(db, user_id, month.ref_month, "PARTY_LEFT", "Você se desfiliou do partido")
    db.flush()
    return {"message": "Você se desfiliou."}


def nomination_chance(db: Session, user_id: int, p, office: str, ref: date) -> float:
    """Chance de o partido QUERER você para o cargo: depende da popularidade, do tempo de casa e da afinidade; cargos maiores exigem muito mais."""
    st = pol(p)
    if not st.get("party"):
        return 0.0
    tenure = months_between(date.fromisoformat(st["joined"]), ref) if st.get("joined") else 0
    pop = popularity(db, user_id, p) / 100
    diff = P.OFFICE_DIFFICULTY[office]
    return round(max(0.03, min(0.95, 0.12 + 0.55 * pop + 0.012 * min(tenure, 36) + 0.15 * (_compat(p, st["party"]) - 0.5) - 0.45 * (1 - diff))), 3)


def office_rows(db: Session, user_id: int, ref: date, lp) -> list[dict]:
    p = profile(db, user_id)
    st, seed = pol(p), _seed(db, user_id)
    camps = {c.data["office"]: c for c in items(db, user_id, "CAMPAIGN", "RUNNING")}
    out = []
    for k, (name, sphere, cycle, min_age, salary, cost, rival, seats) in P.OFFICES.items():
        ed = election_date(k, ref)
        joined = date.fromisoformat(st["joined"]) if st.get("joined") else None
        reasons = []
        if lp.age_years < min_age:
            reasons.append(f"idade mínima {min_age} anos")
        if not st.get("party"):
            reasons.append("filie-se a um partido")
        elif joined and months_between(joined, ed) < P.AFFILIATION_MONTHS:
            reasons.append(f"filiação com pelo menos {P.AFFILIATION_MONTHS} meses de antecedência (você entrou em {joined:%m/%Y})")
        if not st.get("proposals"):
            reasons.append("escolha ao menos uma proposta")
        if ref.year == ed.year and ref.month > 8:
            reasons.append("prazo de registro de candidaturas encerrado (agosto)")
        nr = st.get("nom_refused", {}).get(k)
        if nr and months_between(date.fromisoformat(nr), ref) < P.NOMINATION_RETRY_MONTHS:
            reasons.append(f"o partido não quis você para esse cargo (tente de novo em {P.NOMINATION_RETRY_MONTHS - months_between(date.fromisoformat(nr), ref)} mês(es))")
        if k in camps:
            reasons.append("candidatura já registrada")
        out.append({"key": k, "name": name, "sphere": sphere, "cycle": cycle, "min_age": min_age, "salary": salary, "campaign_cost": cost, "rivals": rival, "seats": seats,
                    "election": ed.isoformat(), "can_run": not reasons, "blocked_by": reasons, "nomination": nomination_chance(db, user_id, p, k, ref) if st.get("party") else None, "estimate": estimate(db, user_id, p, k, ed, 0.0, 0.0, 0.0) if st.get("party") else None})
    return out


def estimate(db: Session, user_id: int, p, office: str, ed: date, spent: float, momentum: float, marketer: float) -> dict:
    """Chance de vitória. Sem campanha ela é só a popularidade da pessoa (no máximo 20%, e zero para quem é desconhecido); a campanha (embalo, dinheiro e
    marqueteiro) soma o resto, filtrada pela credibilidade (popularidade), pelas propostas, pelo lado político e pela força do partido."""
    st, seed = pol(p), _seed(db, user_id)
    _, _, _, _, _, cost, rival, seats = P.OFFICES[office]
    mood = _mood(seed, ed.year)
    ideology = P.IDEOLOGIES.get(st.get("ideology", "centro"), 0)
    party = P.PARTIES.get(st.get("party", ""), (None, 0, 0.3))
    pop = popularity(db, user_id, p) / 100
    base = min(P.INITIAL_CAP, P.INITIAL_CAP * (pop ** 0.8) * P.OFFICE_DIFFICULTY[office])
    quality = 0.45 + 0.30 * _fit(st.get("proposals", []), mood, ideology) + 0.15 * _ideo_fit(ideology, mood) * (1 - 0.12 * abs(ideology - party[1]) / 2) + 0.10 * party[2]
    credibility = 0.30 + 0.70 * (pop ** 0.5)
    power = 0.42 * min(1.0, momentum / 100) + 0.30 * min(1.0, spent / cost) + 0.12 * marketer
    boost = power * quality * credibility * (1 - 0.55 * rival) + (0.05 * min(1.0, power) if seats > 1 else 0.0)
    prob = max(0.0, min(0.95, base + boost))
    return {"score": round(power, 3), "win_chance": round(prob, 3), "base_chance": round(base, 3), "mood_lean": mood["lean"], "popularity": round(pop * 100, 1)}


# ------------------------------------------------------------------ candidatura e campanha
def candidacy(db: Session, user_id: int, month, office: str) -> dict:
    """Pede a candidatura: além de cumprir os requisitos, o PARTIDO precisa querer você para o cargo (pode recusar e só reconsidera depois de alguns meses)."""
    require_open(month)
    if office not in P.OFFICES:
        raise FinanceError("cargo desconhecido")
    ref = month.ref_month
    lp = _life(db, user_id)
    row = next(r for r in office_rows(db, user_id, ref, lp) if r["key"] == office)
    if not row["can_run"]:
        raise ConflictError("você ainda não pode se candidatar: " + "; ".join(row["blocked_by"]))
    p = profile(db, user_id, lock=True)
    st = pol(p)
    name = P.OFFICES[office][0]
    chance = row["nomination"] or 0.0
    if hash01("nomination", _seed(db, user_id), user_id, office, ref.isoformat(), st["party"], st.get("nom_tries", 0)) >= chance:
        refused = dict(st.get("nom_refused", {}))
        refused[office] = ref.isoformat()
        _set_pol(p, nom_refused=refused, nom_tries=int(st.get("nom_tries", 0)) + 1)
        ls.log(db, user_id, ref, "NOMINATION_REFUSED", f"O partido não quis lançar você a {name} (chance era {chance * 100:.0f}%)")
        db.flush()
        return {"registered": False, "message": f"O partido não quis lançar você a {name} (chance era {chance * 100:.0f}%). Ganhe popularidade e tempo de casa e tente de novo em {P.NOMINATION_RETRY_MONTHS} meses."}
    ed = date.fromisoformat(row["election"])
    c = _add(db, user_id, "CAMPAIGN", f"Campanha para {name} ({ed.year})", ref, status="RUNNING", office=office, year=ed.year, election=ed.isoformat(),
             spent=0.0, momentum=0.0, marketer=None, marketer_skill=0.0)
    ls.log(db, user_id, ref, "CANDIDACY", f"O partido lançou você a {name} para outubro de {ed.year}")
    _resync(db, user_id, month)
    return {"registered": True, "campaign_id": c.id, "message": f"O partido aprovou a sua candidatura a {name}! A campanha começa do zero: ganhe embalo, invista e contrate um marqueteiro."}


def withdraw(db: Session, user_id: int, month, cid: int) -> None:
    require_open(month)
    c = _get(db, user_id, cid, "CAMPAIGN")
    if c.status != "RUNNING":
        raise ConflictError("campanha já encerrada")
    c.status = "WITHDRAWN"
    _bump(profile(db, user_id), "politics", fame_d=-1.0)
    _resync(db, user_id, month)


def _running(db: Session, user_id: int, cid: int) -> ArtistItem:
    c = _get(db, user_id, cid, "CAMPAIGN")
    if c.status != "RUNNING":
        raise ConflictError("essa campanha já terminou")
    return c


def hire_marketer(db: Session, user_id: int, month, cid: int, level: str) -> dict:
    require_open(month)
    c = _running(db, user_id, cid)
    if level not in P.MARKETERS:
        raise FinanceError("nível de marqueteiro desconhecido (LOW, MID ou HIGH)")
    name, fee, sk = P.MARKETERS[level]
    _upd(c, marketer=level, marketer_skill=sk)
    ls.log(db, user_id, month.ref_month, "CAMPAIGN_MARKETER", f"Marqueteiro contratado: {name} ({fee}/mês)")
    _resync(db, user_id, month)
    return {"message": f"{name} contratado: {fee} por mês até a eleição."}


def fire_marketer(db: Session, user_id: int, month, cid: int) -> None:
    require_open(month)
    c = _running(db, user_id, cid)
    _upd(c, marketer=None, marketer_skill=0.0)
    _resync(db, user_id, month)


def spend(db: Session, user_id: int, month, cid: int, amount: Decimal) -> dict:
    require_open(month)
    c = _running(db, user_id, cid)
    amount = quantize_money(D(str(amount)))
    if amount <= 0:
        raise FinanceError("informe um valor positivo")
    _pay_cash(db, user_id, month, amount, f"Gastos de campanha ({c.name})", "Outros")
    _upd(c, spent=float(c.data["spent"]) + float(amount))
    _resync(db, user_id, month)
    return {"message": f"{amount} investidos na campanha (total {c.data['spent']:.0f})."}


def rally(db: Session, user_id: int, month, cid: int, kind: str) -> dict:
    require_open(month)
    c = _running(db, user_id, cid)
    if kind not in P.RALLIES:
        raise FinanceError("ação de campanha desconhecida")
    name, cost, gain = P.RALLIES[kind]
    key = f"rally:{kind}:{month.ref_month:%Y-%m}"
    p = profile(db, user_id, lock=True)
    if (c.data or {}).get(key):
        raise ConflictError("você já fez essa ação neste mês")
    ls.spend_hours(_life(db, user_id), 8, name)
    _pay_cash(db, user_id, month, cost, f"{name} ({c.name})", "Outros")
    seed = _seed(db, user_id)
    mk = float(c.data.get("marketer_skill", 0.0))
    real = gain * (0.6 + 0.8 * hash01("rally", seed, c.id, key)) * (1 + 0.8 * mk) * (1 + skill(p, "politics") / 200)
    _upd(c, momentum=min(100.0, float(c.data["momentum"]) + real), spent=float(c.data["spent"]) + cost, **{key: True})
    _bump(p, "politics", skill_d=0.4, fame_d=0.8)
    _resync(db, user_id, month)
    return {"message": f"{name}: +{real:.1f} de embalo (agora {c.data['momentum']:.0f}/100)."}


# ------------------------------------------------------------------ mandato
def terms(db: Session, user_id: int, status: str | None = "ACTIVE") -> list[ArtistItem]:
    return items(db, user_id, "TERM", status)


def mandate_action(db: Session, user_id: int, month, tid: int, kind: str) -> dict:
    require_open(month)
    t = _get(db, user_id, tid, "TERM")
    if t.status != "ACTIVE":
        raise ConflictError("mandato encerrado")
    p = profile(db, user_id, lock=True)
    st = pol(p)
    key = f"act:{kind}:{month.ref_month:%Y-%m}"
    if t.data.get(key):
        raise ConflictError("você já fez isso neste mês")
    seed = _seed(db, user_id)
    roll = hash01("mandate", seed, t.id, key)
    media = P.MEDIA.get(st.get("media", "evasivo"), P.MEDIA["evasivo"])
    if kind == "bill":
        area = (st.get("proposals") or ["social"])[int(hash01("bill-area", seed, t.id, key) * max(1, len(st.get("proposals") or [1])))]
        ls.spend_hours(_life(db, user_id), 10, "Elaborar projeto de lei")
        ok = roll < 0.35 + 0.004 * float(t.data["approval"]) + skill(p, "politics") / 400
        delta, fm = (4.0, 3.0) if ok else (-1.0, 0.0)
        msg = f"Projeto sobre {P.PROPOSALS[area][0].lower()}: " + ("aprovado na casa legislativa!" if ok else "barrado pela oposição.")
    elif kind == "town_hall":
        ls.spend_hours(_life(db, user_id), 8, "Reunião com a população")
        delta, fm = 2.5 + 3 * roll + media[3] * 6, 1.0
        msg = "Você ouviu a população e a aprovação subiu."
    else:
        raise FinanceError("ação desconhecida (bill ou town_hall)")
    _upd(t, approval=round(max(0.0, min(100.0, float(t.data["approval"]) + delta)), 1), **{key: True})
    _bump(p, "politics", skill_d=0.5, fame_d=fm)
    _resync(db, user_id, month)
    return {"message": msg + f" Aprovação: {t.data['approval']:.0f}%."}


def resign(db: Session, user_id: int, month, tid: int) -> None:
    require_open(month)
    t = _get(db, user_id, tid, "TERM")
    t.status = "RESIGNED"
    _bump(profile(db, user_id), "politics", fame_d=-3.0)
    _resync(db, user_id, month)


# ------------------------------------------------------------------ concursos públicos
def exam_offers(db: Session, user_id: int, ref: date) -> list[dict]:
    seed = _seed(db, user_id)
    kinds = list(P.EXAMS)
    p = profile(db, user_id)
    lp = _life(db, user_id)
    from backend.services import career_hub
    out, done = [], {c.data["offer_key"] for c in items(db, user_id, "CONCURSO")}
    degrees = set(lp.degrees or [])
    for i in range(6):
        key = f"CP{ref:%Y%m}{i}"
        k = kinds[int(hash01("exam-kind", seed, key) * len(kinds))] if i < 4 else [x for x in kinds if len(P.EXAMS[x]) > 8][int(hash01("exam-pol", seed, key) * 6)]
        org, role, net, comp, req, fee, field, level, *_rest = P.EXAMS[k]
        area = _rest[0] if _rest else "geral"
        comp = int(comp * (0.8 + 0.5 * hash01("exam-comp", seed, key)))
        match = req is None or req in degrees
        syn = career_hub.degree_synergy(db, user_id, "concurso") + (career_hub.degree_synergy(db, user_id, req) if req else 0)
        out.append({"key": key, "kind": k, "area": area, "organ": org, "role": role, "net": net, "competition": comp, "requires": req, "fee": fee, "field": field, "level": level,
                    "exam_month": shift_month(ref, P.EXAM_DELAY_MONTHS).isoformat(), "registered": key in done,
                    "chance": P.exam_chance(float(lp.study or 0), syn, match, comp, level, float(lp.study_hours_day or 0)), "eligible": match or req is None})
    return out


def exam_register(db: Session, user_id: int, month, key: str) -> dict:
    require_open(month)
    ref = month.ref_month
    offer = next((o for o in exam_offers(db, user_id, ref) if o["key"] == key), None)
    if offer is None:
        raise NotFoundError("esse concurso não está mais aberto")
    if offer["registered"]:
        raise ConflictError("você já se inscreveu nesse concurso")
    if any(c.status == "REGISTERED" and c.data["exam_kind"] == offer["kind"] for c in items(db, user_id, "CONCURSO")):
        raise ConflictError("você já tem uma inscrição ativa para esse tipo de concurso")
    _pay_cash(db, user_id, month, offer["fee"], f"Inscrição no concurso: {offer['role']}", "Educação")
    c = _add(db, user_id, "CONCURSO", f"{offer['role']} — {offer['organ']}", ref, status="REGISTERED", offer_key=key, exam_kind=offer["kind"], area=offer["area"], exam_month=offer["exam_month"],
             organ=offer["organ"], role=offer["role"], net=offer["net"], competition=offer["competition"], requires=offer["requires"], field=offer["field"], level=offer["level"])
    ls.log(db, user_id, ref, "EXAM_REGISTERED", f"Inscrição no concurso {offer['role']} ({offer['organ']}); prova em {offer['exam_month'][:7]}")
    _resync(db, user_id, month)
    return {"message": f"Inscrito(a)! A prova é em {offer['exam_month'][:7]}: estude até lá."}


def _exam_chance_now(db: Session, user_id: int, c: ArtistItem, lp) -> float:
    from backend.services import career_hub
    d = c.data
    match = d["requires"] is None or d["requires"] in set(lp.degrees or [])
    syn = career_hub.degree_synergy(db, user_id, "concurso") + (career_hub.degree_synergy(db, user_id, d["requires"]) if d["requires"] else 0)
    return P.exam_chance(float(lp.study or 0), syn, match, d["competition"], d["level"], float(lp.study_hours_day or 0))


# ------------------------------------------------------------------ fechamento do mês e orçamento
def process_month(db: Session, user_id: int, p, ref: date, seed: int) -> None:
    lp = db.scalar(select(LifeProfile).where(LifeProfile.user_id == user_id))
    # concursos: resultado no mês da prova
    for c in items(db, user_id, "CONCURSO", "REGISTERED"):
        if date.fromisoformat(c.data["exam_month"]) <= ref and lp is not None:
            chance = _exam_chance_now(db, user_id, c, lp)
            if hash01("exam", seed, c.id) < chance:
                c.status = "PASSED"
                from backend.services import career_hub
                career_hub.create_public_job(db, user_id, ref, c.data["role"], c.data["organ"], c.data["field"], D(str(c.data["net"])), c.data["level"])
                if c.data.get("area") == "politica":
                    _bump(p, "politics", skill_d=3.0, fame_d=1.5)
                ls.log(db, user_id, ref, "EXAM_PASSED", f"APROVADO(A) no concurso {c.data['role']} ({c.data['organ']})! Posse no mês que vem. (chance era {chance * 100:.0f}%)")
            else:
                c.status = "FAILED"
                lp.satisfaction = ls._clamp(lp.satisfaction - 3)
                ls.log(db, user_id, ref, "EXAM_FAILED", f"Não passou no concurso {c.data['role']} ({c.data['organ']}); a chance era {chance * 100:.0f}%.")
    # campanhas: o embalo esfria, e a eleição é decidida em outubro
    for c in items(db, user_id, "CAMPAIGN", "RUNNING"):
        d = c.data
        _upd(c, momentum=round(float(d["momentum"]) * 0.93, 2))
        if ref >= date.fromisoformat(d["election"]):
            _decide_election(db, user_id, p, c, ref, seed)
    # mandatos: aprovação deriva com a postura na mídia; termina no prazo
    for t in terms(db, user_id):
        d = t.data
        media = P.MEDIA.get(pol(p).get("media", "evasivo"), P.MEDIA["evasivo"])
        appr = float(d["approval"]) + media[3] * 2 + (hash01("appr", seed, t.id, ref.isoformat()) - 0.52) * 3 - 0.3
        _upd(t, approval=round(max(0.0, min(100.0, appr)), 1))
        if appr < 20:
            _bump(p, "politics", fame_d=-0.5)
        if date.fromisoformat(d["end"]) <= ref:
            t.status = "DONE"
            ls.log(db, user_id, ref, "TERM_END", f"O seu mandato de {d['office_name']} terminou")


def _decide_election(db: Session, user_id: int, p, c: ArtistItem, ref: date, seed: int) -> None:
    d = c.data
    marketer = float(d.get("marketer_skill", 0.0))
    est = estimate(db, user_id, p, d["office"], date.fromisoformat(d["election"]), float(d["spent"]), float(d["momentum"]), marketer)
    won = hash01("election", seed, c.id) < est["win_chance"]
    name, sphere, cycle, _, salary, cost, rival, seats = P.OFFICES[d["office"]]
    if won:
        c.status = "WON"
        start = date(date.fromisoformat(d["election"]).year + 1, 1, 1)
        _add(db, user_id, "TERM", f"{name}", ref, status="ACTIVE", office=d["office"], office_name=name, start=start.isoformat(), end=shift_month(start, 12 * P.TERM_YEARS - 1).isoformat(),
             salary=salary, approval=55.0)
        _bump(p, "politics", fame_d=8.0, skill_d=1.0)
        ls.log(db, user_id, ref, "ELECTED", f"VOCÊ FOI ELEITO(A) {name}! (chance era {est['win_chance'] * 100:.0f}%). Posse em {start:%m/%Y}.")
    else:
        c.status = "LOST"
        _bump(p, "politics", fame_d=1.0)
        ls.log(db, user_id, ref, "ELECTION_LOST", f"Você não foi eleito(a) {name} (chance era {est['win_chance'] * 100:.0f}%). A campanha ajudou a divulgar o seu nome.")


def desired_items(db: Session, user_id: int, ref: date, want) -> None:
    for t in terms(db, user_id, None):
        d = t.data
        if t.status in ("ACTIVE", "DONE") and date.fromisoformat(d["start"]) <= ref <= date.fromisoformat(d["end"]):
            want(f"life:pol:term:{t.id}", f"Subsídio: {d['office_name']}", FlowKind.INCOME, "Salário", D(str(d["salary"])) * D("0.80"))     # líquido (~80% do bruto)
    for c in items(db, user_id, "CAMPAIGN", "RUNNING"):
        if c.data.get("marketer"):
            want(f"life:pol:marketer:{c.id}", f"Marqueteiro de campanha ({c.name})", FlowKind.EXPENSE, "Outros", P.MARKETERS[c.data["marketer"]][1])


# ------------------------------------------------------------------ visão geral
def overview(db: Session, user_id: int, ref: date) -> dict:
    p = profile(db, user_id)
    lp = _life(db, user_id)
    st = pol(p)
    camps = [{"id": c.id, "name": c.name, "office": c.data["office"], "status": c.status, "election": c.data["election"], "spent": round(float(c.data["spent"])),
              "momentum": round(float(c.data["momentum"]), 1), "marketer": c.data.get("marketer"), "year": c.data["year"],
              "estimate": estimate(db, user_id, p, c.data["office"], date.fromisoformat(c.data["election"]), float(c.data["spent"]), float(c.data["momentum"]), float(c.data.get("marketer_skill", 0)))
              if c.status == "RUNNING" else None, "done": [k for k in c.data if k.startswith("rally:") and k.endswith(f"{ref:%Y-%m}")]} for c in items(db, user_id, "CAMPAIGN")]
    return {
        "profile": {"party": st.get("party"), "joined": st.get("joined"), "ideology": st.get("ideology", "centro"), "proposals": st.get("proposals", []), "media": st.get("media", "evasivo")},
        "popularity": popularity(db, user_id, p), "party_chances": {k: party_chance(db, user_id, p, k) for k in P.PARTIES}, "party_refused": st.get("party_refused", {}),
        "fame": round(fame(p, "politics"), 1), "skill": round(skill(p, "politics"), 1), "relevance": round(public_relevance(db, user_id, p), 1), "age": lp.age_years,
        "study": round(float(lp.study or 0), 1), "study_hours_day": float(lp.study_hours_day or 0),
        "offices": office_rows(db, user_id, ref, lp), "campaigns": camps,
        "terms": [{"id": t.id, "name": t.name, "status": t.status, "start": t.data["start"], "end": t.data["end"], "salary": t.data["salary"], "approval": t.data["approval"],
                   "done": [k for k in t.data if k.startswith("act:") and k.endswith(f"{ref:%Y-%m}")]} for t in items(db, user_id, "TERM")],
        "exams": {"offers": exam_offers(db, user_id, ref), "mine": [{"id": c.id, "name": c.name, "status": c.status, "exam_month": c.data["exam_month"], "net": c.data["net"],
                                                                      "chance": round(_exam_chance_now(db, user_id, c, lp), 3) if c.status == "REGISTERED" else None}
                                                                     for c in items(db, user_id, "CONCURSO")]},
        "catalog": {"parties": [{"key": k, "name": v[0], "ideology": v[1], "strength": v[2]} for k, v in P.PARTIES.items()],
                    "ideologies": [{"key": k, "name": P.IDEOLOGY_LABEL[k]} for k in P.IDEOLOGIES],
                    "proposals": [{"key": k, "name": v[0], "lean": v[1]} for k, v in P.PROPOSALS.items()], "max_proposals": P.MAX_PROPOSALS,
                    "media": [{"key": k, "name": v[0], "desc": v[1]} for k, v in P.MEDIA.items()],
                    "marketers": [{"key": k, "name": v[0], "fee": v[1], "skill": v[2]} for k, v in P.MARKETERS.items()],
                    "rallies": [{"key": k, "name": v[0], "cost": v[1], "gain": v[2]} for k, v in P.RALLIES.items()]},
    }
