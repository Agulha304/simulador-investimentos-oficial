"""Carreira de artista: ator, músico, pintor e influenciador."""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.dependencies import CurrentUser, DbSession
from backend.routers.budget import _run
from backend.services import artist_service as svc
from backend.services import budget_service as bs

router = APIRouter(prefix="/artist", tags=["artist"])


class InstrumentIn(BaseModel):
    instrument: str


class TrainIn(BaseModel):
    discipline: str


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


class ChannelIn(BaseModel):
    platform: str
    niche: str
    name: str = Field(min_length=1, max_length=60)


class GearIn(BaseModel):
    category: str


class InvestIn(BaseModel):
    kind: str


class CadenceIn(BaseModel):
    cadence: int


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
    return _act(db, user, lambda m: svc.train(db, user.id, m, body.discipline))


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


@router.post("/channels")
def channel(body: ChannelIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: ({"channel_id": svc.create_channel(db, user.id, m, body.platform, body.niche, body.name).id}))


@router.post("/channels/{cid}/gear")
def gear(cid: int, body: GearIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: svc.buy_gear(db, user.id, m, cid, body.category))


@router.post("/channels/{cid}/invest")
def invest(cid: int, body: InvestIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: svc.invest(db, user.id, m, cid, body.kind))


@router.delete("/channels/{cid}/invest/{kind}")
def stop_invest(cid: int, kind: str, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: (svc.stop_invest(db, user.id, m, cid, kind), {})[1])


@router.put("/channels/{cid}/cadence")
def cadence(cid: int, body: CadenceIn, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: (svc.set_cadence(db, user.id, m, cid, body.cadence), {})[1])


@router.delete("/channels/{cid}")
def close_channel(cid: int, user: CurrentUser, db: DbSession):
    return _act(db, user, lambda m: (svc.close_channel(db, user.id, m, cid), {})[1])
