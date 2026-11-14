from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.services import video_service

router = APIRouter(tags=["media"])


@router.get("/media/{path:path}")
def serve_media(path: str):
    """Entrega vídeos, capas e legendas das aulas (com suporte a Range, para pular no vídeo).
    Público de propósito: a tag <video> não envia o token de login, e o conteúdo do curso não é sigiloso."""
    file = video_service.resolve(path)
    if file is None:
        raise HTTPException(404, "Arquivo não encontrado")
    return FileResponse(file, media_type=video_service.media_type(file), headers={"Cache-Control": "public, max-age=86400"})
