"""Carreira de artista: ator, músico, pintor e influenciador."""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.dependencies import CurrentUser, DbSession
from backend.routers.budget import _run
from backend.services import artist_influencer as inf
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
