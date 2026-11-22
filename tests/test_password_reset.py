import logging
from datetime import timedelta

import pytest
from sqlalchemy import select

from backend.models import PasswordResetToken, User
from backend.services import auth_service, mailer

EMAIL = "ana@example.com"


class FakeMailer:
    def __init__(self):
        self.sent = []

    def send_password_reset(self, to_email, name, token):
        self.sent.append((to_email, name, token))


@pytest.fixture
def fake(monkeypatch):
    f = FakeMailer()
    monkeypatch.setattr(mailer, "get_mailer", lambda: f)
    return f


def _forgot(client, email=EMAIL, ip="1.1.1.1"):
    return client.post("/api/auth/forgot-password", json={"email": email}, headers={"X-Forwarded-For": ip})


def _login(client, pw):
    return client.post("/api/auth/login", json={"email": EMAIL, "password": pw})


def test_resposta_identica_existente_e_inexistente(client, auth_headers, fake):
    a, b = _forgot(client), _forgot(client, "ninguem@example.com")
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()
    assert len(fake.sent) == 1 and fake.sent[0][0] == EMAIL


def test_token_guardado_so_como_hash(client, auth_headers, fake, db):
    _forgot(client)
    token = fake.sent[0][2]
    row = db.scalars(select(PasswordResetToken)).one()
    assert row.token_hash != token and token not in row.token_hash and len(row.token_hash) == 64
    assert row.request_ip == "1.1.1.1"


def test_fluxo_completo_login_nova_senha(client, auth_headers, fake):
    _forgot(client)
    token = fake.sent[0][2]
    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "novasenha99"})
    assert r.status_code == 200
    assert _login(client, "novasenha99").status_code == 200
    assert _login(client, "segredo123").status_code == 401


def test_uso_unico(client, auth_headers, fake):
    _forgot(client)
    token = fake.sent[0][2]
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": "novasenha99"}).status_code == 200
    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "outrasenha99"})
    assert r.status_code == 400
    assert _login(client, "novasenha99").status_code == 200


def test_expira_em_1h(client, auth_headers, fake, monkeypatch):
    _forgot(client)
    token = fake.sent[0][2]
    real = auth_service._now
    monkeypatch.setattr(auth_service, "_now", lambda: real() + timedelta(hours=1, seconds=1))
    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "novasenha99"})
    assert r.status_code == 400
    assert _login(client, "segredo123").status_code == 200


def test_ainda_valido_antes_de_1h(client, auth_headers, fake, monkeypatch):
    _forgot(client)
    token = fake.sent[0][2]
    real = auth_service._now
    monkeypatch.setattr(auth_service, "_now", lambda: real() + timedelta(minutes=59))
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": "novasenha99"}).status_code == 200


def test_novo_pedido_invalida_token_antigo(client, auth_headers, fake):
    _forgot(client)
    _forgot(client)
    old, new = fake.sent[0][2], fake.sent[1][2]
    assert client.post("/api/auth/reset-password", json={"token": old, "new_password": "novasenha99"}).status_code == 400
    assert client.post("/api/auth/reset-password", json={"token": new, "new_password": "novasenha99"}).status_code == 200


def test_reset_invalida_outros_tokens(client, auth_headers, fake, db):
    _forgot(client)
    token = fake.sent[0][2]
    client.post("/api/auth/reset-password", json={"token": token, "new_password": "novasenha99"})
    assert all(t.used_at is not None for t in db.scalars(select(PasswordResetToken)))


def test_senha_fraca_e_token_invalido(client, auth_headers, fake):
    _forgot(client)
    token = fake.sent[0][2]
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": "curta"}).status_code == 422
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": "x" * 73}).status_code == 422
    r1 = client.post("/api/auth/reset-password", json={"token": "lixo", "new_password": "novasenha99"})
    assert r1.status_code == 400
    # a senha fraca não consumiu o token
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": "novasenha99"}).status_code == 200


def test_rate_limit_por_email(client, auth_headers, fake):
    for i in range(5):
        r = _forgot(client, ip=f"2.2.2.{i}")
        assert r.status_code == 200
    assert len(fake.sent) == 3            # 4º e 5º pedidos: mesma resposta, sem envio
    assert _forgot(client, "outro@example.com", ip="2.2.2.9").status_code == 200


def test_rate_limit_por_ip(client, fake):
    codes = [_forgot(client, f"u{i}@example.com", ip="9.9.9.9").status_code for i in range(12)]
    assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]
    assert _forgot(client, "u1@example.com", ip="8.8.8.8").status_code == 200


def test_email_invalido_422(client):
    assert client.post("/api/auth/forgot-password", json={"email": "nao-e-email"}).status_code == 422


def test_mailer_real_monta_link_e_texto(monkeypatch):
    from backend.config import get_settings
    monkeypatch.setattr(get_settings(), "app_base_url", "https://app.exemplo.com/")
    assert mailer.build_reset_link("TOK") == "https://app.exemplo.com/redefinir-senha?token=TOK"
    body = mailer.build_reset_body("Ana", mailer.build_reset_link("TOK"))
    assert "redefinir-senha?token=TOK" in body and "1 hora" in body and "ignore" in body


def test_smtp_envia_mensagem_com_link(monkeypatch):
    from backend.config import get_settings
    s = get_settings()
    for k, v in dict(smtp_host="smtp.x", smtp_port=587, smtp_user="u", smtp_password="p", smtp_from="no@x.com", smtp_starttls=True).items():
        monkeypatch.setattr(s, k, v)
    calls = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None): calls["host"] = (host, port)
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, context=None): calls["tls"] = True
        def login(self, u, p): calls["login"] = (u, p)
        def send_message(self, msg, from_addr=None): calls["msg"] = msg; calls["from"] = from_addr

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    assert isinstance(mailer.get_mailer(), mailer.SmtpMailer)
    mailer.send_password_reset_safe("ana@example.com", "Ana", "TOK123")
    assert calls["tls"] and calls["login"] == ("u", "p") and calls["msg"]["To"] == "ana@example.com"
    assert "redefinir-senha?token=TOK123" in calls["msg"].get_content()


def test_falha_smtp_nao_vaza_nem_levanta(monkeypatch, caplog):
    from backend.config import get_settings
    monkeypatch.setattr(mailer.log, "disabled", False)
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.x")

    def boom(*a, **k): raise OSError("conexão recusada ana@example.com TOK999")
    monkeypatch.setattr("smtplib.SMTP", boom)
    with caplog.at_level(logging.DEBUG):
        mailer.send_password_reset_safe("ana@example.com", "Ana", "TOK999")
    assert "TOK999" not in caplog.text and "ana@example.com" not in caplog.text


def test_log_fallback_dev_loga_link_prod_nao(monkeypatch, caplog):
    from backend.config import get_settings
    s = get_settings()
    monkeypatch.setattr(mailer.log, "disabled", False)   # o fileConfig do alembic (conftest) desativa loggers já criados
    monkeypatch.setattr(s, "smtp_host", "")
    monkeypatch.setattr(s, "environment", "development")
    with caplog.at_level(logging.INFO):
        mailer.send_password_reset_safe("ana@example.com", "Ana", "TOKDEV")
    assert "redefinir-senha?token=TOKDEV" in caplog.text
    caplog.clear()
    monkeypatch.setattr(s, "environment", "production")
    with caplog.at_level(logging.DEBUG):
        mailer.send_password_reset_safe("ana@example.com", "Ana", "TOKPROD")
    assert "TOKPROD" not in caplog.text and "NÃO enviado" in caplog.text


def test_token_nunca_na_resposta(client, auth_headers, fake):
    r = _forgot(client)
    assert fake.sent[0][2] not in r.text
