/**
 * Worker do Simulador de Investimentos.
 *
 * Os arquivos do site (frontend/dist) são servidos direto pelo Cloudflare. Este código só roda para
 * /api/* (ver "run_worker_first" no wrangler.jsonc) e repassa a chamada ao backend em BACKEND_URL.
 * Assim o navegador fala sempre com o mesmo domínio: sem CORS e sem expor a URL do backend ao front.
 */
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (!url.pathname.startsWith("/api/")) {
      return json({ detail: "Não encontrado" }, 404);
    }

    const base = (env.BACKEND_URL || "").trim();
    if (!base) {
      return json(
        { detail: "O backend ainda não foi configurado: defina a variável BACKEND_URL no Worker." },
        503,
      );
    }

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
  },
};

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}
