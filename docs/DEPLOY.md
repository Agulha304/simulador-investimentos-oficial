# Publicar o simulador

O projeto tem duas partes, e elas ficam em lugares diferentes:

```text
Navegador ──► Cloudflare (Worker + arquivos do site)
                 │  /api/*  (o Worker repassa)
                 ▼
              Backend FastAPI + workers  ──►  PostgreSQL
              (host sempre ligado)
```

- **Cloudflare** serve o site (React) e encaminha tudo que começa com `/api/` para o backend. O navegador fala só com um
  domínio, então não há CORS.
- **Backend + banco** não rodam no Cloudflare: são Python com PostgreSQL e **workers em segundo plano** (Stop Loss, proventos,
  renda fixa, snapshots), que precisam de um servidor **sempre ligado e com uma única instância**.

Faça nesta ordem: **1) backend**, para ter a URL; **2) Cloudflare**.

## 1. Backend e banco

Qualquer host que rode Docker serve (Render, Fly.io, Railway, uma VPS). O `Dockerfile` está na raiz do repositório e roda as
migrations antes de abrir a porta.

**Banco:** PostgreSQL 14+ com a extensão `unaccent` (Neon, Supabase e Render têm). Copie a *connection string*; o formato
`postgres://...` ou `postgresql://...` já é aceito.

**Variáveis de ambiente do backend:**

| Variável | Valor |
|---|---|
| `ENVIRONMENT` | `production` (o app recusa subir com segredo fraco ou banco em localhost) |
| `DATABASE_URL` | connection string do banco |
| `JWT_SECRET` | segredo aleatório de 32+ caracteres: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `SCHEDULER_ENABLED` | `true` (em **uma** instância apenas) |
| `CORS_ORIGINS` | a URL do site no Cloudflare (opcional: o Worker já deixa tudo na mesma origem) |
| `INITIAL_BALANCE` | opcional, saldo virtual inicial (padrão `100000.00`) |

Health check do host: `GET /api/health`. Teste: `https://SEU-BACKEND/api/health` deve devolver `{"status":"ok","database":"ok"}`.

> Planos gratuitos que "dormem" por inatividade derrubam os workers enquanto o app está parado. Para o Stop Loss, os proventos
> e os snapshots funcionarem, use um plano que fique sempre ligado.

### Banco no Supabase

O banco de produção é o Postgres do Supabase (projeto `kqvpqbdupafpbasrytqw`). Use a URL do **Session pooler** (porta 5432) em `DATABASE_URL`.
As migrações (`alembic upgrade head`) criam as tabelas e ligam o **RLS** em todas elas: o backend conecta com o usuário `postgres` (ignora RLS), e a
chave pública do Supabase fica sem acesso a nada. **Toda tabela nova precisa de `ENABLE ROW LEVEL SECURITY`** na migration.
Os testes (`pytest`) usam `TEST_DATABASE_URL` (Postgres local) e se recusam a rodar se ele apontar para o Supabase.

### Backend no Render (opção grátis)

Render > New > Web Service > conectar o repositório, *Runtime: Docker* (usa o `Dockerfile` da raiz). Em **Environment** defina:
`DATABASE_URL` (Supabase, Session pooler), `JWT_SECRET` (o *legacy JWT secret*) e, se quiser, `CORS_ORIGINS`.
`ENVIRONMENT=production` já vem no Dockerfile. Se faltar `DATABASE_URL`, o container para na hora com uma mensagem explicando. Depois copie a URL pública do
serviço (`https://....onrender.com`) e coloque em `BACKEND_URL` no Worker do Cloudflare.

## 2. Cloudflare (Workers & Pages → Create → conectar o repositório do GitHub)

| Campo | O que colocar |
|---|---|
| Project name | o nome que você der ao Worker (só minúsculas, números e hífens), que precisa ser **igual** ao `name` do `wrangler.jsonc` (hoje: `wealthy-simulator`) |
| Production branch | `main` |
| Root directory (Advanced) | deixe vazio (`/`): é onde está o `wrangler.jsonc` |
| Build command | `npm run build` |
| Deploy command | `npx wrangler deploy` |
| Preview command | `npx wrangler versions upload` (ou desligue *Enable Preview builds*) |
| Protect with Cloudflare Access | desligado (liga só se quiser restringir o site) |

Depois do primeiro deploy, configure o backend:

1. Abra o Worker `wealthy-simulator` → **Settings → Variables and Secrets → Add**.
2. Tipo *Text*, nome `BACKEND_URL`, valor a URL do backend **sem barra no final** (ex.: `https://simulador-api.onrender.com`).
3. Salve. Não é preciso refazer o deploy.

Pronto: abra a URL `https://wealthy-simulator.<sua-conta>.workers.dev`, crie uma conta e use.

Sem `BACKEND_URL`, as chamadas da API respondem `503` ("O backend ainda não foi configurado"). Com o backend fora do ar, `502`.

## 3. Domínio próprio (opcional)

No Worker → **Settings → Domains & Routes → Add → Custom domain**, com um domínio que esteja no Cloudflare.

## 4. Atualizações

Cada `git push` na `main` refaz o build e o deploy do site. O backend atualiza pelo seu host (também ligado ao GitHub).
Migrations de banco rodam sozinhas quando o backend reinicia.

## 5. Vídeos das aulas

As 37 videoaulas somam cerca de 1 GB e **não vão no Git nem na imagem do backend** (só o `media/manifest.json`). Há duas formas:

- **Servir pelo backend (padrão):** o backend entrega `media/videos`, `media/posters` e `media/captions` em `/api/media/...`
  (com suporte a "pular" no vídeo). Funciona local; em produção exige disco persistente no host e passa pelo Worker.
- **Bucket/CDN (recomendado em produção):** envie o conteúdo de `media/` para a raiz de um bucket e defina no backend
  `MEDIA_BASE_URL=https://SEU-BUCKET-PUBLICO`. Exemplo com Cloudflare R2 (precisa de `wrangler login`):

```bash
npx wrangler r2 bucket create simulador-media
for f in media/videos/*.mp4;   do npx wrangler r2 object put "simulador-media/videos/$(basename $f)"   --file "$f" --content-type video/mp4  --remote; done
for f in media/posters/*.jpg;  do npx wrangler r2 object put "simulador-media/posters/$(basename $f)"  --file "$f" --content-type image/jpeg --remote; done
for f in media/captions/*.vtt; do npx wrangler r2 object put "simulador-media/captions/$(basename $f)" --file "$f" --content-type text/vtt  --remote; done
```

  Depois ative o acesso público do bucket (domínio `r2.dev` ou domínio próprio) e configure o **CORS** do bucket para o domínio do site:
  o navegador exige CORS para as legendas (`<track>`), enquanto o vídeo e a capa tocam sem ele.

## Avisos

- **Cotações (Yahoo Finance)** são uma fonte não oficial e podem bloquear IPs de datacenters. Se as cotações ficarem "indisponíveis" só
  em produção, é isso. A fonte está isolada em `backend/services/market_data.py` para ser trocada.
- **Dados de teste:** o usuário `demo@simulador.dev` existe só no seu banco local. Em produção, cada pessoa cria a própria conta.
- **Backup do banco:** use o do provedor. O livro-razão (`transactions`) é o registro histórico e não deve ser perdido.
- Teste local do Worker (aponta para o backend local): `BACKEND_PORT=8010 ... scripts/dev.sh` e, em outro terminal,
  `npm run build && npx wrangler dev --var BACKEND_URL:http://localhost:8010`.


## E-mail de "Esqueci minha senha"

O link de redefinição é enviado por SMTP. No Render (Environment) configure:

| Variável | Exemplo | Observação |
|---|---|---|
| `APP_BASE_URL` | `https://wealthy-simulator.giuliapeluzzos.workers.dev` | endereço PÚBLICO do frontend (sem `/` no fim); o link é `${APP_BASE_URL}/redefinir-senha?token=...` |
| `SMTP_HOST` | `smtp-relay.brevo.com` | vazio = e-mail desligado |
| `SMTP_PORT` | `587` | 587 usa STARTTLS; 465 usa SSL direto |
| `SMTP_USER` / `SMTP_PASSWORD` | (do provedor) | segredos: só no painel do Render, nunca no repositório |
| `SMTP_FROM` | `SimulaInvest <nao-responda@seudominio.com>` | vazio = usa `SMTP_USER`; o domínio deve estar verificado (SPF/DKIM) no provedor |
| `SMTP_STARTTLS` | `true` | |

Provedores recomendados: Brevo (plano grátis ~300 e-mails/dia), Resend ou Mailgun (SMTP) e, para testes, Gmail com **senha de app**
(`smtp.gmail.com:587`, exige verificação em duas etapas). Prefira um domínio próprio verificado: remetentes sem SPF/DKIM caem no spam.

Sem `SMTP_HOST`: em desenvolvimento o link só é LOGADO no servidor; em produção é logado o aviso
`SMTP não configurado: e-mail de redefinição NÃO enviado` (o token nunca vai para log de produção).

Segurança: token aleatório (`secrets.token_urlsafe(32)`), guardado só como SHA-256 (`password_reset_tokens`), válido por 1 h e de uso único;
um novo pedido invalida os anteriores. Rate limit (tabela `password_reset_requests`, vale entre instâncias): 3 pedidos/h por e-mail
(excedente responde igual, sem enviar) e 10/h por IP (429). O IP vem de `X-Forwarded-For` (primeiro valor). Os JWT já emitidos NÃO são
revogados na troca de senha (não há versão de sessão): expiram em `JWT_EXPIRE_MINUTES`.
