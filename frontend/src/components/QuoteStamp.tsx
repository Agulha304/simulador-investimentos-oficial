/** Selo discreto com a hora da cotação; avisa quando está desatualizada (stale do servidor ou > 2 min). Sem os campos, não mostra nada. */
const OLD_MS = 2 * 60_000;

export function quoteIsOld(fetchedAt?: string | null, stale?: boolean | null): boolean {
  if (stale === true) return true;
  const t = fetchedAt ? Date.parse(fetchedAt) : NaN;
  return !Number.isNaN(t) && Date.now() - t > OLD_MS;
}

export function QuoteStamp({ fetchedAt, stale, prefix = "cotação de" }: { fetchedAt?: string | null; stale?: boolean | null; prefix?: string }) {
  const t = fetchedAt ? new Date(fetchedAt) : null;
  const hh = t && !Number.isNaN(t.getTime()) ? t.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : null;
  if (!hh && stale !== true) return null;
  const old = quoteIsOld(fetchedAt, stale);
  return (
    <span className={old ? "tone-warn" : "muted"} style={{ fontSize: "0.8em" }} title={old ? "Cotação desatualizada; atualizando em segundo plano" : undefined}>
      {old ? `desatualizada${hh ? ` · ${prefix} ${hh}` : ""}` : `${prefix} ${hh}`}
    </span>
  );
}
