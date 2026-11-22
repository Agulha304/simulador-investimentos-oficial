"""Envio de e-mail (hoje só a redefinição de senha), com dois backends:

- SmtpMailer: smtplib (STARTTLS na porta 587, SSL direto na 465), configurado por SMTP_* no ambiente.
- LogMailer (fallback sem SMTP_HOST): em desenvolvimento LOGA o link; em produção loga só um aviso, SEM o token.

`send_password_reset` NUNCA levanta exceção (roda em background; falha só é logada, sem e-mail/token no log).
Os testes trocam `get_mailer` por um mailer falso.
"""
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Protocol

from backend.config import get_settings

log = logging.getLogger(__name__)

RESET_SUBJECT = "Redefinição de senha - SimulaInvest"


def build_reset_link(token: str) -> str:
    return f"{get_settings().app_base_url.rstrip('/')}/redefinir-senha?token={token}"


def build_reset_body(name: str, link: str) -> str:
    return (
        f"Olá, {name}!\n\n"
        "Recebemos um pedido para redefinir a senha da sua conta no SimulaInvest.\n"
        "Para criar uma nova senha, acesse o link abaixo:\n\n"
        f"{link}\n\n"
        "Este link é válido por 1 hora e só pode ser usado uma vez.\n\n"
        "Se não foi você quem pediu, ignore este e-mail: sua senha continua a mesma.\n"
    )


class Mailer(Protocol):
    def send_password_reset(self, to_email: str, name: str, token: str) -> None: ...


class SmtpMailer:
    def send_password_reset(self, to_email: str, name: str, token: str) -> None:
        s = get_settings()
        msg = EmailMessage()
        msg["Subject"] = RESET_SUBJECT
        sender = s.smtp_from or s.smtp_user
        msg["From"] = sender
        msg["To"] = to_email
        msg.set_content(build_reset_body(name, build_reset_link(token)))
        ctx = ssl.create_default_context()
        try:
            if s.smtp_port == 465:
                server: smtplib.SMTP = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=15, context=ctx)
            else:
                server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15)
            with server:
                if s.smtp_port != 465 and s.smtp_starttls:
                    server.starttls(context=ctx)
                if s.smtp_user:
                    server.login(s.smtp_user, s.smtp_password)
                server.send_message(msg, from_addr=parseaddr(sender)[1] or sender)
        except Exception as exc:   # noqa: BLE001 - nunca vazar token/e-mail no log
            log.error("falha ao enviar e-mail de redefinição de senha (%s)", type(exc).__name__)


class LogMailer:
    def send_password_reset(self, to_email: str, name: str, token: str) -> None:
        if get_settings().environment.lower() == "production":
            log.warning("SMTP não configurado: e-mail de redefinição NÃO enviado")
            return
        log.info("[dev] link de redefinição de senha para %s: %s", to_email, build_reset_link(token))


def get_mailer() -> Mailer:
    return SmtpMailer() if get_settings().smtp_host else LogMailer()


def send_password_reset_safe(to_email: str, name: str, token: str) -> None:
    """Usado como tarefa de background: captura qualquer erro."""
    try:
        get_mailer().send_password_reset(to_email, name, token)
    except Exception as exc:   # noqa: BLE001
        log.error("erro inesperado no envio do e-mail de redefinição (%s)", type(exc).__name__)
