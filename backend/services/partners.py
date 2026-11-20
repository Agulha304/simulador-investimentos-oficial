"""Sociedades: convites a amigos e parceiros, aporte de capital de cada sócio e saída/calote.

Quem aceita é decidido pela relação (afinidade, confiança, compatibilidade), pelo perfil da pessoa, pela justiça da proposta e
pela capacidade financeira dela — nunca pelo dinheiro do jogador. A decisão sai de um sorteio determinístico, gravado uma vez.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import Company, CompanyPartner, PartnerInvite, Person, Relationship, SimMonth
from backend.services import budget_service, life_rules as R
from backend.services import life_service
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError

D = Decimal
MAX_PARTNERS_SHARE = D("80")          # o dono fica com pelo menos 20%
CLOSE_STAGES = ("FRIEND", "DATING", "COHABITING", "MARRIED")
PERSONALITY_TRUST = {"ambicioso": 0.10, "aventureiro": 0.08, "criativo": 0.05, "extrovertido": 0.04, "tranquilo": 0.0,
                     "caseiro": -0.05, "reservado": -0.06, "metódico": -0.03}


def finance_label(person: Person) -> str:
    """Retrato simples da situação financeira de uma pessoa (mostrado nos relacionamentos)."""
    income = person.income or D(1)
    debt_ratio = float(person.debts / income)
    wealth_ratio = float(person.assets / income)
    if debt_ratio > 4:
        return "endividado(a)"
    if wealth_ratio >= 24:
        return "muito confortável"
    if wealth_ratio >= 10:
        return "confortável"
    if wealth_ratio >= 4 and debt_ratio < 3:
        return "estável"
    return "apertada"


def _decide(p, person: Person, r: Relationship, share: Decimal, contribution: Decimal, seed_parts: tuple) -> tuple[bool, str]:
    if r.stage == "FAMILY":
        return False, f"{person.name.split()[0]} prefere não misturar família e negócios"
    if r.stage not in CLOSE_STAGES:
        return False, f"{person.name.split()[0]} ainda não tem intimidade para virar sócio(a)"
    if person.assets < contribution:
        return False, f"{person.name.split()[0]} não tem como investir {quantize_money(contribution)} agora"
    comp = life_service.compatibility(p, person, r.compat_bonus)
    prob = 0.30 + 0.004 * r.affinity + 0.003 * r.trust + 0.002 * comp + PERSONALITY_TRUST.get(person.personality, 0.0)
    prob += (float(share) - 15.0) / 300.0                                  # participação mais justa convence mais
    if person.assets and contribution / person.assets > D("0.6"):
        prob -= 0.15                                                       # arriscar quase tudo assusta
    prob = max(0.05, min(0.95, prob))
    if R.hash01("partner", *seed_parts) < prob:
        return True, f"{person.name.split()[0]} topou entrar na sociedade!"
    return False, f"{person.name.split()[0]} agradeceu, mas preferiu não entrar nessa sociedade agora"


def invite(db: Session, user_id: int, month: SimMonth, person_id: int, share_pct: Decimal, capital: Decimal) -> PartnerInvite:
    budget_service.require_open(month)
    share_pct, capital = D(share_pct), quantize_money(capital)
    if not D("5") <= share_pct <= MAX_PARTNERS_SHARE:
        raise FinanceError("a participação do sócio deve ficar entre 5% e 80%")
    if capital <= 0:
        raise FinanceError("informe o capital total previsto da empresa")
    r = life_service.get_relationship(db, user_id, person_id, lock=True)
    person = db.get(Person, person_id)
    existing = db.scalar(select(PartnerInvite).where(PartnerInvite.user_id == user_id, PartnerInvite.person_id == person_id,
                                                     PartnerInvite.ref_month == month.ref_month))
    if existing is not None:
        return existing                                                    # nada de repetir o convite no mesmo mês até conseguir sim
    p = life_service.get_profile(db, user_id)
    contribution = quantize_money(capital * share_pct / 100)
    ok, msg = _decide(p, person, r, share_pct, contribution, (user_id, person_id, month.ref_month.isoformat()))
    if not ok:                                                             # ser recusado esfria a relação (e fica gravado)
        r.affinity = life_service._clamp(r.affinity - 6)
        r.trust = life_service._clamp(r.trust - 3)
        life_service._hit_mood(p, -2, -2)                                  # a recusa também pesa no humor
    inv = PartnerInvite(user_id=user_id, person_id=person_id, ref_month=month.ref_month, share_pct=share_pct, capital=capital,
                        accepted=ok, message=msg)
    db.add(inv)
    db.flush()
    return inv


def usable_invites(db: Session, user_id: int, month: SimMonth, invite_ids: list[int]) -> list[PartnerInvite]:
    out = []
    for iid in invite_ids:
        inv = db.get(PartnerInvite, iid)
        if inv is None or inv.user_id != user_id:
            raise NotFoundError("convite não encontrado")
        if not inv.accepted:
            raise ConflictError("este convite foi recusado")
        if inv.used or inv.ref_month != month.ref_month:
            raise ConflictError("convite já usado ou de outro mês: faça um novo convite")
        out.append(inv)
    if len({i.person_id for i in out}) != len(out):
        raise FinanceError("a mesma pessoa não pode entrar duas vezes")
    if sum((i.share_pct for i in out), D(0)) > MAX_PARTNERS_SHARE:
        raise FinanceError("os sócios somam mais de 80%: o dono precisa ficar com pelo menos 20%")
    return out


def owner_share(invites: list[PartnerInvite]) -> Decimal:
    return D(100) - sum((i.share_pct for i in invites), D(0))


def contributions(invites: list[PartnerInvite], capital: Decimal) -> list[tuple[PartnerInvite, Decimal]]:
    out = []
    for inv in invites:
        c = quantize_money(capital * inv.share_pct / 100)
        if capital > inv.capital:
            raise FinanceError("o capital passou do que você combinou com os sócios: faça um novo convite")
        out.append((inv, c))
    return out


def partners_of(db: Session, company_id: int) -> list[CompanyPartner]:
    return list(db.scalars(select(CompanyPartner).where(CompanyPartner.company_id == company_id).order_by(CompanyPartner.id)))
