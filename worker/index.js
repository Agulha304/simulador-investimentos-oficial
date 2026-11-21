/**
 * Worker do Simulador de Investimentos.
 *
 * Os arquivos do site (frontend/dist) são servidos direto pelo Cloudflare. Este código só roda para /api/*
 * (ver "run_worker_first" no wrangler.jsonc) e repassa a chamada ao backend:
 *   - se BACKEND_URL estiver definida, a um backend externo;
 *   - senão, ao container do Cloudflare (classe Backend), que roda o FastAPI do Dockerfile.
 * O navegador fala sempre com o mesmo domínio: sem CORS.
 */
import { Container, getContainer } from "@cloudflare/containers";

export class Backend extends Container {
  defaultPort = 8000;
  // os workers em segundo plano só rodam com o container acordado; ele dorme depois de muito tempo sem acessos
  sleepAfter = "12h";

  constructor(ctx, env) {
    super(ctx, env);
    this.envVars = {
      ENVIRONMENT: "production",
      PORT: "8000",
      DATABASE_URL: env.DATABASE_URL ?? "",
      JWT_SECRET: env.JWT_SECRET ?? "",
      CORS_ORIGINS: env.CORS_ORIGINS ?? "",
      SCHEDULER_ENABLED: env.SCHEDULER_ENABLED ?? "true",
      INITIAL_BALANCE: env.INITIAL_BALANCE ?? "100000",
    };
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (!url.pathname.startsWith("/api/")) {
      return json({ detail: "Não encontrado" }, 404);
    }

    const base = (env.BACKEND_URL || "").trim();
    if (base) {
      let target;
      try {
        // o destino é sempre o backend configurado; só o caminho e a query vêm da requisição
        target = new URL(url.pathname + url.search, base);
      } catch {
        return json({ detail: "BACKEND_URL inválida" }, 500);
      }
      try {
        return await fetch(new Request(target, request));
      } catch {
        return json({ detail: "Backend indisponível no momento. Tente novamente em instantes." }, 502);
      }
    }

    if (!env.DATABASE_URL || !env.JWT_SECRET) {
      return json({ detail: "Backend sem configuração: defina os segredos DATABASE_URL e JWT_SECRET no Worker." }, 503);
    }
    try {
      return await getContainer(env.BACKEND).fetch(request);
    } catch {
      return json({ detail: "Backend iniciando ou indisponível. Tente novamente em instantes." }, 502);
    }
  },
};

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}
