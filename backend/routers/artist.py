"""Carreira de artista: ator, músico, pintor e influenciador."""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.dependencies import CurrentUser, DbSession
from backend.routers.budget import _run
from backend.services import artist_film as film
from backend.services import artist_influencer as inf
from backend.services import politics_service as pol
from backend.services import artist_service as svc
from backend.services import budget_service as bs

router = APIRouter(prefix="/artist", tags=["artist"])


class InstrumentIn(BaseModel):
    instrument: str


class TrainIn(BaseModel):
    discipline: str
    instrument: str | None = None      # música: "geral" (ou vazio) ou a chave de um instrumento


class ApplyIn(BaseModel):
    discipline: str
    offer_key: str


class BandIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    style: str


class RecruitIn(BaseModel):
    key: str


class SongIn(BaseModel):
    scope: str = "BAND"          # BAND | SOLO
    style: str
    theme: str


class AlbumIn(BaseModel):
    scope: str = "BAND"
    mode: str = "INDIE"          # INDIE | LABEL


class GigIn(BaseModel):
    tier: str
    scope: str = "BAND"


class PaintIn(BaseModel):
    theme: str
    style: str
    size: str


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    niche: str
    platforms: list[str] = Field(min_length=1)


class PlatformIn(BaseModel):
    platform: str


class GearIn(BaseModel):
    category: str


class InvestIn(BaseModel):
    kind: str


class VideoIn(BaseModel):
    platforms: list[str] = Field(min_length=1)
    topic: str = "conteudo"
    ref_id: int | None = None


class SponsorIn(BaseModel):
    offer_key: str


class ScriptWriteIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    genre: str
    theme: str


class KeyIn(BaseModel):
    key: str


class FilmStartIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    theme: str
    genre: str
    script_id: int
    funding: str = "SELF"        # SELF | PRODUCER
    scale: str = "indie"


class ProductionIn(BaseModel):
    kind: str                    # costume | studio | set
    tier: int


class PolProfileIn(BaseModel):
    party: str | None = None
    ideology: str | None = None
    proposals: list[str] | None = None
    media: str | None = None


class PartyIn(BaseModel):
    party: str


class OfficeIn(BaseModel):
    office: str


class LevelIn(BaseModel):
    level: str


class SpendIn(BaseModel):
    amount: float = Field(gt=0)


class KindIn(BaseModel):
    kind: str


class DecideIn(BaseModel):
    option: str


def _view(db, user_id):
    return svc.overview(db, user_id, bs.ensure_setup(db, user_id).ref_month)


def _act(db, user, fn):
    """Executa a ação no mês aberto e devolve o resultado + a visão geral atualizada."""
    def go():
        month = bs.ensure_setup(db, user.id)
        res = fn(month)
        return {"result": res if isinstance(res, dict) else {}, **svc.overview(db, user.id, month.ref_month)}
    return _run(db, go)


@router.get("")
def overview(user: CurrentUser, db: DbSession):
    return _run(db, lambda: _view(db, user.id))


@router.post("/instrument")
def instrument(body: InstrumentIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: (svc.set_instrument(db, user.id, m, body.instrument), {})[1])


@router.post("/train")
def train(body: TrainIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: svc.train(db, user.id, m, body.discipline, body.instrument))


@router.post("/apply")
def apply(body: ApplyIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: svc.apply_offer(db, user.id, m, body.discipline, body.offer_key))


@router.delete("/jobs/{job_id}")
def quit_job(job_id: int, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: (svc.quit_job(db, user.id, m, job_id), {})[1])


@router.post("/band")
def band(body: BandIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: (svc.create_band(db, user.id, m, body.name, body.style), {})[1])


@router.delete("/band")
def disband(user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: (svc.disband(db, user.id, m), {})[1])


@router.post("/band/recruit")
def recruit(body: RecruitIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: svc.recruit(db, user.id, m, body.key))


@router.post("/song")
def song(body: SongIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: svc.create_song(db, user.id, m, body.scope, body.style, body.theme))


@router.post("/album")
def album(body: AlbumIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: svc.release_album(db, user.id, m, body.scope, body.mode))


@router.post("/gig")
def gig(body: GigIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: svc.play_gig(db, user.id, m, body.tier, body.scope))


@router.post("/painting")
def painting(body: PaintIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: svc.paint(db, user.id, m, body.theme, body.style, body.size))


@router.post("/decisions/{decision_id}")
def decide(decision_id: int, body: DecideIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: svc.decide(db, user.id, m, decision_id, body.option))


@router.post("/accounts")
def account(body: AccountIn, user: CurrentUser, db: DbSession):
    """Cria uma conta de criador (um nicho/tema) com canais nas plataformas escolhidas."""
    return _act(db, user, lambda m: {"account_id": inf.create_account(db, user.id, m, body.name, body.niche, body.platforms).id})


@router.post("/accounts/{aid}/channels")
def add_channel(aid: int, body: PlatformIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: {"channel_id": inf.add_channel(db, user.id, m, aid, body.platform).id})


@router.delete("/accounts/{aid}")
def close_account(aid: int, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: (inf.close_account(db, user.id, m, aid), {})[1])


@router.delete("/channels/{cid}")
def close_channel(cid: int, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: (inf.close_channel(db, user.id, m, cid), {})[1])


@router.post("/accounts/{aid}/gear")
def gear(aid: int, body: GearIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: inf.buy_gear(db, user.id, m, aid, body.category))


@router.post("/accounts/{aid}/invest")
def invest(aid: int, body: InvestIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: inf.invest(db, user.id, m, aid, body.kind))


@router.delete("/accounts/{aid}/invest/{kind}")
def stop_invest(aid: int, kind: str, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: (inf.stop_invest(db, user.id, m, aid, kind), {})[1])


@router.post("/accounts/{aid}/video")
def video(aid: int, body: VideoIn, user: CurrentUser, db: DbSession):
    """Cria um vídeo e publica em uma, algumas ou todas as plataformas da conta (temático ou normal)."""
    return _act(db, user, lambda m: inf.post_video(db, user.id, m, aid, body.platforms, body.topic, body.ref_id))


@router.post("/accounts/{aid}/sponsor")
def sponsor(aid: int, body: SponsorIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: inf.accept_sponsor(db, user.id, m, aid, body.offer_key))


# ------------------------------------------------------------------ cinema (diretor, roteirista, produtor)
@router.post("/film/script/buy")
def script_buy(body: KeyIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: film.buy_script(db, user.id, m, body.key))


@router.post("/film/script/write")
def script_write(body: ScriptWriteIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: film.write_script(db, user.id, m, body.title, body.genre, body.theme))


@router.post("/film/script/{sid}/sell")
def script_sell(sid: int, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: film.sell_script(db, user.id, m, sid))


@router.post("/film/projects")
def film_start(body: FilmStartIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: film.start_film(db, user.id, m, body.title, body.theme, body.genre, body.script_id, body.funding, body.scale))


@router.post("/film/projects/{fid}/cast")
def film_cast(fid: int, body: KeyIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: film.hire_cast(db, user.id, m, fid, body.key))


@router.post("/film/projects/{fid}/production")
def film_production(fid: int, body: ProductionIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: film.buy_production(db, user.id, m, fid, body.kind, body.tier))


@router.post("/film/projects/{fid}/shoot")
def film_shoot(fid: int, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: film.start_shoot(db, user.id, m, fid))


@router.delete("/film/projects/{fid}")
def film_cancel(fid: int, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: (film.cancel_film(db, user.id, m, fid), {})[1])


# ------------------------------------------------------------------ política e concursos públicos
politics = APIRouter(prefix="/politics", tags=["politics"])


def _pact(db, user, fn):
    def go():
        month = bs.ensure_setup(db, user.id)
        res = fn(month)
        return {"result": res if isinstance(res, dict) else {}, **pol.overview(db, user.id, month.ref_month)}
    return _run(db, go)


@politics.get("")
def pol_overview(user: CurrentUser, db: DbSession):
    return _run(db, lambda: pol.overview(db, user.id, bs.ensure_setup(db, user.id).ref_month))


@politics.put("/profile")
def pol_profile(body: PolProfileIn, user: CurrentUser, db: DbSession):
    return _pact(db, user, lambda m: (pol.set_profile(db, user.id, m, body.party, body.ideology, body.proposals, body.media), {})[1])


@politics.post("/party")
def pol_party(body: PartyIn, user: CurrentUser, db: DbSession):
    """Pede filiação a um partido: ele pode recusar (e só reconsidera depois de alguns meses)."""
    return _pact(db, user, lambda m: pol.join_party(db, user.id, m, body.party))


@politics.delete("/party")
def pol_leave_party(user: CurrentUser, db: DbSession):
    return _pact(db, user, lambda m: pol.leave_party(db, user.id, m))


@politics.post("/candidacy")
def pol_candidacy(body: OfficeIn, user: CurrentUser, db: DbSession):
    """Pede a candidatura: o partido precisa querer você para o cargo."""
    return _pact(db, user, lambda m: pol.candidacy(db, user.id, m, body.office))


@politics.delete("/campaigns/{cid}")
def pol_withdraw(cid: int, user: CurrentUser, db: DbSession):
    return _pact(db, user, lambda m: (pol.withdraw(db, user.id, m, cid), {})[1])


@politics.post("/campaigns/{cid}/marketer")
def pol_marketer(cid: int, body: LevelIn, user: CurrentUser, db: DbSession):
    return _pact(db, user, lambda m: pol.hire_marketer(db, user.id, m, cid, body.level))


@politics.delete("/campaigns/{cid}/marketer")
def pol_fire_marketer(cid: int, user: CurrentUser, db: DbSession):
    return _pact(db, user, lambda m: (pol.fire_marketer(db, user.id, m, cid), {})[1])


@politics.post("/campaigns/{cid}/spend")
def pol_spend(cid: int, body: SpendIn, user: CurrentUser, db: DbSession):
    from decimal import Decimal
    return _pact(db, user, lambda m: pol.spend(db, user.id, m, cid, Decimal(str(body.amount))))


@politics.post("/campaigns/{cid}/rally")
def pol_rally(cid: int, body: KindIn, user: CurrentUser, db: DbSession):
    return _pact(db, user, lambda m: pol.rally(db, user.id, m, cid, body.kind))


@politics.post("/terms/{tid}/action")
def pol_action(tid: int, body: KindIn, user: CurrentUser, db: DbSession):
    return _pact(db, user, lambda m: pol.mandate_action(db, user.id, m, tid, body.kind))


@politics.delete("/terms/{tid}")
def pol_resign(tid: int, user: CurrentUser, db: DbSession):
    return _pact(db, user, lambda m: (pol.resign(db, user.id, m, tid), {})[1])


@politics.post("/exams/register")
def exam_register(body: KeyIn, user: CurrentUser, db: DbSession):
    return _pact(db, user, lambda m: pol.exam_register(db, user.id, m, body.key))
