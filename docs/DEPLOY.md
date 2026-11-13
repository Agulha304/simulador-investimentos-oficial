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

## Avisos

- **Cotações (Yahoo Finance)** são uma fonte não oficial e podem bloquear IPs de datacenters. Se as cotações ficarem "indisponíveis" só
  em produção, é isso. A fonte está isolada em `backend/services/market_data.py` para ser trocada.
- **Dados de teste:** o usuário `demo@simulador.dev` existe só no seu banco local. Em produção, cada pessoa cria a própria conta.
- **Backup do banco:** use o do provedor. O livro-razão (`transactions`) é o registro histórico e não deve ser perdido.
- Teste local do Worker (aponta para o backend local): `BACKEND_PORT=8010 ... scripts/dev.sh` e, em outro terminal,
  `npm run build && npx wrangler dev --var BACKEND_URL:http://localhost:8010`.
