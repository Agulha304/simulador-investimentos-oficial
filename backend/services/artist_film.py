"""Cinema: diretor contratado, roteirista (escreve e vende roteiros) e produtor (compra/usa um roteiro e monta o filme: elenco, figurino,
estúdio e cenário, com financiamento próprio ou de uma produtora). Tudo simulado. Nada aqui faz commit."""
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import ArtistItem
from backend.services import artist_rules as AR
from backend.services import life_service as ls
from backend.services.artist_core import _add, _bump, _get, _income, _life, _pay_cash, _resync, _seed, _upd, fame, items, profile, skill
from backend.services.budget_service import require_open
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError
from backend.services.goods_rules import hash01

D = Decimal
GENRES = {"acao": ("Ação", 1.25), "comedia": ("Comédia", 1.30), "drama": ("Drama", 0.90), "terror": ("Terror", 1.15), "romance": ("Romance", 1.00), "documentario": ("Documentário", 0.55),
          "animacao": ("Animação", 1.20), "ficcao": ("Ficção científica", 1.10), "infantil": ("Infantil", 1.15), "suspense": ("Suspense", 1.10)}
THEMES = {"superacao": "Superação", "familia": "Família", "amor": "Amor", "crime": "Crime", "historia": "História real", "futuro": "Futuro distópico", "amizade": "Amizade",
          "politica": "Política", "fe": "Fé", "natureza": "Natureza", "vinganca": "Vingança", "misterio": "Mistério"}
SCALES = {"indie": ("Independente (baixo orçamento)", 0.15, 2, 1.0), "medio": ("Orçamento médio", 0.5, 3, 1.0), "grande": ("Superprodução", 1.6, 5, 1.0)}   # (nome, multiplicador de custos, meses de filmagem)
COSTUME = {1: ("Figurino básico", 8000), 2: ("Figurino profissional", 40000), 3: ("Figurino de grife/época", 150000)}
STUDIO = {1: ("Estúdio alugado por diária", 15000), 2: ("Estúdio profissional", 90000), 3: ("Estúdio de cinema", 400000)}
SETS = {1: ("Cenário simples", 10000), 2: ("Cenário construído", 60000), 3: ("Cenário de grande produção", 300000)}
KIND_TABLE = {"costume": COSTUME, "studio": STUDIO, "set": SETS}
KIND_LABEL = {"costume": "figurinista", "studio": "estúdio", "set": "cenário"}
MAX_CAST = 8
MIN_CAST = 3
DIRECTOR_JOBS = {  # tipo -> (descrição, mensal?, min, max, meses, habilidade mínima, fama mínima)
    "curta": ("Dirigir um curta-metragem", False, 1500, 6000, 1, 12, 0), "clipe": ("Dirigir um videoclipe", False, 3000, 14000, 1, 22, 2), "comercial": ("Dirigir um comercial de TV", False, 6000, 35000, 1, 30, 5),
    "doc": ("Dirigir um documentário", True, 3500, 9000, 4, 28, 3), "serie": ("Dirigir episódios de uma série", True, 9000, 28000, 5, 42, 12), "longa": ("Dirigir um longa-metragem (diretor contratado)", True, 14000, 60000, 6, 55, 22)}
RELEASE = {  # opção -> (nome, custo de marketing (% do orçamento), descrição)
    "cinemas": ("Lançamento amplo nos cinemas", 0.15, "Maior bilheteria possível, mas metade vai para distribuidores e cinemas e há risco de flop."),
    "festivais": ("Circuito de festivais", 0.03, "Pouco dinheiro, muito prestígio: sobe fama e habilidade."),
    "streaming": ("Vender os direitos para streaming", 0.0, "Pagamento quase garantido, sem risco de bilheteria."),
    "video": ("Lançar direto em vídeo/TV", 0.0, "Sem custo de marketing; receita modesta."),
}


def market(seed: int, ref: date) -> dict:
    scripts = []
    for i in range(5):
        key = f"SC{ref:%Y%m}{i}"
        q = int(30 + 62 * hash01("sc-q", seed, key) ** 1.2)
        g = list(GENRES)[int(hash01("sc-g", seed, key) * len(GENRES))]
        t = list(THEMES)[int(hash01("sc-t", seed, key) * len(THEMES))]
        scripts.append({"key": key, "title": f"{THEMES[t]}: {['A Última Estação', 'Entre Dois Mundos', 'O Peso do Silêncio', 'Noite sem Fim', 'Caminho de Volta', 'O Segredo do Rio'][int(hash01('sc-n', seed, key) * 6)]}",
                        "writer": f"{AR.FIRST[int(hash01('sc-w', seed, key) * len(AR.FIRST))]} {AR.LAST[int(hash01('sc-w2', seed, key) * len(AR.LAST))]}", "genre": g, "theme": t, "quality": q,
                        "price": int((2000 + q * q * 9) * (0.7 + 0.6 * hash01("sc-p", seed, key)) / 100) * 100})
    actors = []
    for i in range(8):
        key = f"AT{ref:%Y%m}{i}"
        sk = int(20 + 75 * hash01("at-s", seed, key) ** 1.3)
        actors.append({"key": key, "name": f"{AR.FIRST[int(hash01('at-n', seed, key) * len(AR.FIRST))]} {AR.LAST[int(hash01('at-n2', seed, key) * len(AR.LAST))]}", "skill": sk,
                       "fee": int(1500 + sk * sk * 9 * (0.7 + 0.6 * hash01("at-f", seed, key)) / 100) * 100})
    return {"scripts": scripts, "actors": actors}


def film_offers(db: Session, user_id: int, ref: date) -> list[dict]:
    p, seed = profile(db, user_id), _seed(db, user_id)
    out, kinds = [], list(DIRECTOR_JOBS)
    for i in range(3):
        key = f"FD{ref:%Y%m}{i}"
        k = kinds[int(hash01("fk", seed, key) * len(kinds))]
        desc, monthly, lo, hi, months, need_skill, need_fame = DIRECTOR_JOBS[k]
        pay = int((lo + (hi - lo) * hash01("fp", seed, key) ** 1.3) * (1 + fame(p, "film") / 200) / 10) * 10
        out.append({"key": key, "discipline": "film", "kind": k, "title": desc, "employer": ["Produtora Lente Viva", "Estúdio Horizonte", "Cia. de Cinema Aurora", "Agência Foco", "Canal Brasil Livre"][int(hash01("fe", seed, key) * 5)],
                    "monthly": monthly, "pay": pay, "months": months, "need_fame": need_fame, "need_skill": need_skill, "hours": 30 if monthly else 0,
                    "chance": round(AR.hire_chance(skill(p, "film"), fame(p, "film"), need_skill, need_fame) * 100)})
    return out


# ------------------------------------------------------------------ roteiros
def scripts(db: Session, user_id: int) -> list[ArtistItem]:
    return items(db, user_id, "SCRIPT")


def buy_script(db: Session, user_id: int, month, key: str) -> dict:
    require_open(month)
    ref = month.ref_month
    sc = next((s for s in market(_seed(db, user_id), ref)["scripts"] if s["key"] == key), None)
    if sc is None:
        raise NotFoundError("esse roteiro não está mais à venda")
    if any(x.data.get("market_key") == key for x in scripts(db, user_id)):
        raise ConflictError("você já comprou esse roteiro")
    _pay_cash(db, user_id, month, sc["price"], f"Roteiro: {sc['title']}", "Outros")
    _add(db, user_id, "SCRIPT", sc["title"], ref, status="OWNED", source="BOUGHT", market_key=key, writer=sc["writer"], genre=sc["genre"], theme=sc["theme"], quality=sc["quality"])
    ls.log(db, user_id, ref, "SCRIPT_BOUGHT", f"Você comprou o roteiro “{sc['title']}” de {sc['writer']} (qualidade {sc['quality']})")
    _resync(db, user_id, month)
    return {"message": f"Roteiro comprado: {sc['title']} (qualidade {sc['quality']})."}


def write_script(db: Session, user_id: int, month, title: str, genre: str, theme: str) -> dict:
    require_open(month)
    ref = month.ref_month
    title = title.strip()
    if not title or genre not in GENRES or theme not in THEMES:
        raise FinanceError("informe título, gênero e tema válidos")
    p = profile(db, user_id, lock=True)
    ls.spend_hours(_life(db, user_id), 20, "Escrever um roteiro")
    n = len(scripts(db, user_id))
    seed = _seed(db, user_id)
    if hash01("script-idea", seed, user_id, ref.isoformat(), n, title) >= 0.30 + 0.5 * skill(p, "film") / 100:
        db.flush()
        return {"created": False, "message": "A história não fechou desta vez. Tente outro título ou tema (ou estude mais roteiro)."}
    q = int(AR.clamp(0.65 * skill(p, "film") + 22 * hash01("script-q", seed, user_id, ref.isoformat(), n, title) + 6))
    s = _add(db, user_id, "SCRIPT", title, ref, status="OWNED", source="OWN", genre=genre, theme=theme, quality=q)
    _bump(p, "film", skill_d=0.8)
    ls.log(db, user_id, ref, "SCRIPT_WRITTEN", f"Você escreveu o roteiro “{title}” (qualidade {q})")
    _resync(db, user_id, month)
    return {"created": True, "message": f"Roteiro pronto: “{title}” (qualidade {q}).", "script_id": s.id}


def sell_script(db: Session, user_id: int, month, sid: int) -> dict:
    require_open(month)
    ref = month.ref_month
    s = _get(db, user_id, sid, "SCRIPT")
    if s.status != "OWNED":
        raise ConflictError("esse roteiro já foi vendido ou está em produção")
    if s.data["source"] != "OWN":
        raise ConflictError("só dá para vender roteiros que você mesmo escreveu")
    p, seed = profile(db, user_id), _seed(db, user_id)
    q = float(s.data["quality"])
    chance = AR.clamp((0.10 + 0.008 * (q - 30) + 0.004 * fame(p, "film")) * 100, 4, 90) / 100
    if hash01("script-sale", seed, user_id, sid, ref.isoformat()) >= chance:
        return {"sold": False, "message": f"Nenhuma produtora quis comprar “{s.name}” agora (chance era {chance * 100:.0f}%)."}
    price = q * q * 12 * GENRES[s.data["genre"]][1] * (0.6 + 0.8 * hash01("script-price", seed, user_id, sid))
    _income(db, user_id, ref, f"Venda do roteiro — {s.name}", price)
    s.status = "SOLD"
    _bump(p, "film", fame_d=1.5)
    _resync(db, user_id, month)
    return {"sold": True, "message": f"Uma produtora comprou “{s.name}” por {int(price)} (entra no mês que vem)."}


# ------------------------------------------------------------------ projetos de filme
def films(db: Session, user_id: int) -> list[ArtistItem]:
    return items(db, user_id, "FILM")


def _film(db: Session, user_id: int, fid: int) -> ArtistItem:
    f = _get(db, user_id, fid, "FILM")
    return f


def start_film(db: Session, user_id: int, month, title: str, theme: str, genre: str, script_id: int, funding: str, scale: str) -> dict:
    require_open(month)
    ref = month.ref_month
    if genre not in GENRES or theme not in THEMES or scale not in SCALES or funding not in ("SELF", "PRODUCER"):
        raise FinanceError("título, tema, gênero, porte ou financiamento inválidos")
    title = title.strip()
    if not title:
        raise FinanceError("dê um título ao filme")
    s = _get(db, user_id, script_id, "SCRIPT")
    if s.status != "OWNED":
        raise ConflictError("esse roteiro não está disponível")
    p, seed = profile(db, user_id, lock=True), _seed(db, user_id)
    mult = SCALES[scale][1]
    budget = int(1_200_000 * mult)
    producer_ok = True
    if funding == "PRODUCER":
        chance = AR.clamp((0.08 + 0.007 * (float(s.data["quality"]) - 30) + 0.006 * fame(p, "film") + 0.12 * (GENRES[genre][1] - 1)) * 100 / (1 + 0.25 * mult), 3, 88) / 100
        producer_ok = hash01("producer", seed, user_id, ref.isoformat(), script_id) < chance
        if not producer_ok:
            ls.log(db, user_id, ref, "FILM_PRODUCER_NO", f"Nenhuma produtora quis financiar “{title}” (chance era {chance * 100:.0f}%)")
            db.flush()
            return {"started": False, "message": f"Nenhuma produtora topou financiar o filme (chance era {chance * 100:.0f}%). Tente financiar por conta própria ou melhorar o roteiro."}
    s.status = "IN_FILM"
    f = _add(db, user_id, "FILM", title, ref, status="PREP", theme=theme, genre=genre, script_id=script_id, script_q=float(s.data["quality"]), funding=funding, scale=scale,
             budget=budget, spent=0, cast=[], costume=0, studio=0, set=0, months=0)
    ls.log(db, user_id, ref, "FILM_STARTED", f"Projeto de filme: “{title}” ({GENRES[genre][0]}, {THEMES[theme]}), {'financiado por uma produtora' if funding == 'PRODUCER' else 'financiado por você'}")
    _resync(db, user_id, month)
    return {"started": True, "message": f"Projeto “{title}” criado" + (" com financiamento da produtora." if funding == "PRODUCER" else ". Agora monte elenco, figurino, estúdio e cenário."), "film_id": f.id}


def _cost(f: ArtistItem, base: int) -> int:
    return int(round(base * SCALES[f.data["scale"]][1] / 100)) * 100


def _spend(db: Session, user_id: int, month, f: ArtistItem, amount: int, name: str) -> None:
    if f.data["funding"] == "SELF":
        _pay_cash(db, user_id, month, amount, f"{name} ({f.name})", "Outros")
    _upd(f, spent=int(f.data["spent"]) + amount)


def hire_cast(db: Session, user_id: int, month, fid: int, key: str) -> dict:
    require_open(month)
    f = _film(db, user_id, fid)
    if f.status != "PREP":
        raise ConflictError("o elenco só pode ser montado antes das filmagens")
    cast = list(f.data["cast"])
    if len(cast) >= MAX_CAST:
        raise ConflictError(f"o elenco já tem {MAX_CAST} atores")
    a = next((x for x in market(_seed(db, user_id), month.ref_month)["actors"] if x["key"] == key), None)
    if a is None:
        raise NotFoundError("ator não encontrado")
    if any(c["key"] == key for c in cast):
        raise ConflictError("esse ator já está no elenco")
    p = profile(db, user_id)
    chance = AR.clamp(0.35 + 0.5 * (1 - a["skill"] / 100) + 0.01 * (fame(p, "film") + float(f.data["script_q"]) / 3), 0.1, 0.95)
    if hash01("cast", _seed(db, user_id), user_id, fid, key) >= chance:
        return {"hired": False, "message": f"{a['name']} recusou o papel (não acreditou no projeto)."}
    fee = _cost(f, a["fee"])
    _spend(db, user_id, month, f, fee, f"Cachê de {a['name']}")
    cast.append({"key": key, "name": a["name"], "skill": a["skill"], "fee": fee})
    _upd(f, cast=cast)
    _resync(db, user_id, month)
    return {"hired": True, "message": f"{a['name']} entrou no elenco (cachê {fee})."}


def buy_production(db: Session, user_id: int, month, fid: int, kind: str, tier: int) -> dict:
    require_open(month)
    f = _film(db, user_id, fid)
    if f.status != "PREP":
        raise ConflictError("a estrutura só pode ser contratada antes das filmagens")
    table = KIND_TABLE.get(kind)
    if table is None or tier not in table:
        raise FinanceError("item de produção inválido")
    if int(f.data[kind]) >= tier:
        raise ConflictError("você já tem esse nível ou um melhor")
    name, base = table[tier]
    cost = _cost(f, base)
    _spend(db, user_id, month, f, cost, f"{name}")
    _upd(f, **{kind: tier})
    _resync(db, user_id, month)
    return {"message": f"{name} contratado ({cost})."}


def requirements(f: ArtistItem) -> list[str]:
    d, miss = f.data, []
    if len(d["cast"]) < MIN_CAST:
        miss.append(f"elenco com pelo menos {MIN_CAST} atores")
    for k in ("costume", "studio", "set"):
        if int(d[k]) < 1:
            miss.append(KIND_LABEL[k])
    return miss


def start_shoot(db: Session, user_id: int, month, fid: int) -> dict:
    require_open(month)
    f = _film(db, user_id, fid)
    if f.status != "PREP":
        raise ConflictError("o filme já saiu da pré-produção")
    miss = requirements(f)
    if miss:
        raise ConflictError("faltam para começar a gravar: " + ", ".join(miss))
    _upd(f, months=SCALES[f.data["scale"]][2])
    f.status = "SHOOTING"
    ls.log(db, user_id, month.ref_month, "FILM_SHOOT", f"Começaram as filmagens de “{f.name}”")
    _resync(db, user_id, month)
    return {"message": f"Filmagens de “{f.name}” começaram: {f.data['months']} meses."}


def cancel_film(db: Session, user_id: int, month, fid: int) -> None:
    require_open(month)
    f = _film(db, user_id, fid)
    if f.status not in ("PREP", "SHOOTING"):
        raise ConflictError("esse filme já foi concluído")
    f.status = "CANCELED"
    sc = db.get(ArtistItem, f.data["script_id"])
    if sc is not None and sc.status == "IN_FILM":
        sc.status = "OWNED"
    _resync(db, user_id, month)


# ------------------------------------------------------------------ lançamento
def quality_of(db: Session, user_id: int, f: ArtistItem, seed: int) -> float:
    p, d = profile(db, user_id), f.data
    cast = d["cast"]
    cavg = sum(c["skill"] for c in cast) / max(1, len(cast))
    prod = (int(d["costume"]) + int(d["studio"]) + int(d["set"])) / 9 * 100
    return round(AR.clamp(0.34 * float(d["script_q"]) + 0.24 * cavg + 0.17 * skill(p, "film") + 0.15 * prod + 18 * hash01("fq", seed, f.id) - 3), 1)


def release(db: Session, user_id: int, month, dec: ArtistItem, option: str) -> dict:
    ref = month.ref_month
    f = db.get(ArtistItem, dec.data["work_id"])
    if option not in RELEASE:
        raise FinanceError("opção desconhecida")
    seed, p = _seed(db, user_id), profile(db, user_id, lock=True)
    d = f.data
    q, budget = float(d["quality"]), int(d["budget"])
    name, mkt, _ = RELEASE[option]
    mk = int(budget * mkt / 100) * 100
    roll = hash01("release", seed, f.id, option)
    share = 1.0 if d["funding"] == "SELF" else 0.45                      # com produtora você fica com 45% do que o filme rende
    g = GENRES[d["genre"]][1]
    if option == "cinemas":
        if mk and d["funding"] == "SELF":
            _pay_cash(db, user_id, month, mk, f"Marketing do lançamento ({f.name})", "Outros")
        box = budget * (0.15 + q / 100 * 2.4) * g * (0.5 + 1.0 * roll)
        total = box * 0.5 * share
        for i in range(1, 4):
            _income(db, user_id, ref, f"Bilheteria — {f.name} ({i}/3)", total / 3, i)
        fame_d, skill_d = (q / 14 if q > 55 else -1.5), 1.0
        msg = f"“{f.name}” estreou nos cinemas: qualidade {q:.0f}, bilheteria total ~{int(box)}; sua parte ~{int(total)} em 3 meses."
    elif option == "festivais":
        prize = q > 62 and roll < 0.45
        total = budget * 0.08 * share * (2.5 if prize else 1)
        _income(db, user_id, ref, f"Festivais — {f.name}", total, 2)
        fame_d, skill_d = (q / 8 if prize else q / 22), 2.0
        msg = f"“{f.name}” circulou por festivais" + (" e GANHOU PRÊMIOS!" if prize else ".") + f" Qualidade {q:.0f}."
    elif option == "streaming":
        total = budget * (0.55 + 0.9 * q / 100) * share
        _income(db, user_id, ref, f"Direitos de streaming — {f.name}", total, 1)
        fame_d, skill_d = q / 20, 1.0
        msg = f"A plataforma de streaming comprou os direitos de “{f.name}” por {int(total)} (qualidade {q:.0f})."
    else:
        total = budget * (0.12 + q / 100 * 0.5) * g * (0.6 + 0.8 * roll) * share
        _income(db, user_id, ref, f"Lançamento em vídeo — {f.name}", total, 2)
        fame_d, skill_d = q / 30, 0.6
        msg = f"“{f.name}” saiu direto em vídeo/TV: receita de ~{int(total)}."
    f.status = "RELEASED"
    _upd(f, release=option, result=msg, revenue=int(total))
    _bump(p, "film", skill_d=skill_d, fame_d=fame_d)
    sc = db.get(ArtistItem, d["script_id"])
    if sc is not None:
        sc.status = "PRODUCED"
    return {"message": msg, "status": "FILM"}


def process_month(db: Session, user_id: int, p, ref: date, seed: int) -> None:
    for f in items(db, user_id, "FILM", "SHOOTING"):
        left = int(f.data["months"]) - 1
        _upd(f, months=left)
        if left <= 0:
            q = quality_of(db, user_id, f, seed)
            _upd(f, quality=q)
            f.status = "WRAPPED"
            opts = [{"key": k, "label": v[0], "cost": int(int(f.data["budget"]) * v[1] / 100) * 100 if f.data["funding"] == "SELF" else 0, "desc": v[2]} for k, v in RELEASE.items()]
            _add(db, user_id, "DECISION", f"Como lançar “{f.name}”?", ref, status="OPEN", work="FILM", work_id=f.id, desc=f"As filmagens terminaram. Qualidade final: {q:.0f}/100.", options=opts)
            ls.log(db, user_id, ref, "FILM_WRAPPED", f"As filmagens de “{f.name}” terminaram (qualidade {q:.0f}). Decida como lançar.")


def desired_items(db: Session, user_id: int, ref: date, want) -> None:
    return None


def committed_hours(db: Session, user_id: int) -> int:
    return 25 * len(items(db, user_id, "FILM", "SHOOTING"))


def overview(db: Session, user_id: int, ref: date) -> dict:
    mk = market(_seed(db, user_id), ref)
    return {"market": mk, "offers": film_offers(db, user_id, ref),
            "scripts": [{"id": s.id, "title": s.name, "status": s.status, **s.data} for s in scripts(db, user_id)],
            "projects": [{"id": f.id, "title": f.name, "status": f.status, "missing": requirements(f) if f.status == "PREP" else [], **f.data} for f in films(db, user_id)],
            "catalog": {"genres": [{"key": k, "name": v[0], "market": v[1]} for k, v in GENRES.items()], "themes": [{"key": k, "name": v} for k, v in THEMES.items()],
                        "scales": [{"key": k, "name": v[0], "cost_mult": v[1], "months": v[2]} for k, v in SCALES.items()],
                        "costume": {k: {"name": v[0], "cost": v[1]} for k, v in COSTUME.items()}, "studio": {k: {"name": v[0], "cost": v[1]} for k, v in STUDIO.items()},
                        "set": {k: {"name": v[0], "cost": v[1]} for k, v in SETS.items()}, "min_cast": MIN_CAST, "max_cast": MAX_CAST}}
