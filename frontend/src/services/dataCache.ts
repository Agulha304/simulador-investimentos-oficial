// Cache de GETs em memória: dedupe de requests em voo, TTL, stale-while-revalidate.
// Segurança financeira: TODA mutação (POST/PUT/PATCH/DELETE via request) limpa o cache inteiro e os hooks montados
// refazem a busca; troca de usuário/partida limpa tudo. A chave inclui token (hash) + partida + path.
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { ACCOUNT_PATHS, gameStore, useActiveGame } from "./gameStore";
import { request, tokenStore } from "./api";

const TTL_DEFAULT = 15_000, TTL_FIN = 10_000, TTL_CATALOG = 300_000;

/** TTL padrão por tipo de dado: financeiro 10s, catálogos 5min, resto 15s. */
export function defaultTtl(path: string): number {
  const p = path.split("?")[0];
  if (/^\/assets\/(quotes|\d+\/(quote|chart))$/.test(p)) return TTL_FIN;
  if (/^\/(learn|assets|companies\/catalog)(\/|$)/.test(p)) return TTL_CATALOG;
  if (/^\/(portfolio|fixed-income|budget|goods|performance|progress|debt|companies|invest-plan|life)(\/|$)/.test(p)) return TTL_FIN;
  return TTL_DEFAULT;
}
// além disso o dado em cache não é mais servido nem como "stale": espera-se a rede
const maxStale = (ttl: number) => Math.max(ttl * 6, 60_000);

interface Entry { data: unknown; at: number }
type Ev = { type: "write"; key: string } | { type: "invalidate" };
const store = new Map<string, Entry>();
const inflight = new Map<string, Promise<unknown>>();
const subs = new Set<(e: Ev) => void>();
let epoch = 0;
let lastScope: string | null = null;

const hash = (s: string) => { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0; return (h >>> 0).toString(36); };
const isAccount = (path: string) => ACCOUNT_PATHS.some((p) => path.startsWith(p));
const scope = () => `${hash(tokenStore.get() ?? "")}|${gameStore.get()?.id ?? ""}`;

function clearAll() { store.clear(); inflight.clear(); epoch++; }
/** Troca de usuário/partida (detectada pelo escopo): descarta tudo, sem notificar. */
function ensureScope() { const s = scope(); if (lastScope !== null && s !== lastScope) clearAll(); lastScope = s; }
const keyFor = (path: string) => { ensureScope(); return `${hash(tokenStore.get() ?? "")}|${isAccount(path) ? "" : gameStore.get()?.id ?? ""}|${path}`; };

/** Limpa o cache inteiro (sem refetch). Use em logout/login. */
export function clearCache() { clearAll(); lastScope = scope(); }
/** Invalida tudo e manda os hooks montados rebuscarem (chamado após qualquer mutação). */
export function invalidateAll() { clearAll(); subs.forEach((s) => s({ type: "invalidate" })); }
gameStore.subscribe(ensureScope); // troca de partida (mudança real de escopo) limpa tudo

function load<T>(path: string): Promise<T> {
  const key = keyFor(path);
  const running = inflight.get(key);
  if (running) return running as Promise<T>;
  const myEpoch = epoch;
  const p: Promise<T> = request<T>(path)
    .then((data) => {
      if (epoch === myEpoch) { store.set(key, { data, at: Date.now() }); subs.forEach((s) => s({ type: "write", key })); } // mutação no meio: não guarda dado velho
      return data;
    })
    .finally(() => { if (inflight.get(key) === p) inflight.delete(key); });
  inflight.set(key, p);
  return p;
}

/** GET com cache: fresco -> cache; vencido (SWR) -> devolve o cache e revalida em segundo plano; senão rede. `force` ignora o cache. */
export function cachedGet<T>(path: string, opts: { ttl?: number; force?: boolean } = {}): Promise<T> {
  const ttl = opts.ttl ?? defaultTtl(path);
  const e = store.get(keyFor(path));
  if (!opts.force && e) {
    const age = Date.now() - e.at;
    if (age < ttl) return Promise.resolve(e.data as T);
    if (age < maxStale(ttl)) { load<T>(path).catch(() => {}); return Promise.resolve(e.data as T); }
  }
  return load<T>(path);
}

const msgOf = (x: unknown) => (x instanceof Error ? x.message : String(x));

export interface ApiState<T> { data: T | undefined; error: string | null; loading: boolean; refreshing: boolean; reload: () => Promise<T | undefined> }

/** Hook: mostra o cache na hora, revalida se vencido, refaz ao mudar o path e após mutações. `reload()` força a rede. */
export function useApi<T>(path: string | null, opts: { ttl?: number } = {}): ApiState<T> {
  useActiveGame(); // re-renderiza (e recalcula a chave) ao trocar de partida
  const key = path ? keyFor(path) : null;
  const ttl = opts.ttl ?? (path ? defaultTtl(path) : 0);
  const [, bump] = useReducer((n: number) => n + 1, 0);
  const [fetching, setFetching] = useState(false);
  const [err, setErr] = useState<{ key: string; msg: string } | null>(null);
  const last = useRef<{ key: string | null; data: T | undefined }>({ key: null, data: undefined });

  const entry = key ? store.get(key) : undefined;
  if (key && entry) last.current = { key, data: entry.data as T };
  // após invalidação mantém o último dado DA MESMA chave enquanto refaz (refreshing=true); nunca de outra chave/usuário/partida
  const data = key ? (entry ? (entry.data as T) : last.current.key === key ? last.current.data : undefined) : undefined;

  const run = useCallback((p: string, k: string, alive: () => boolean) => {
    setFetching(true);
    return load<T>(p)
      .then((d) => { if (alive()) setErr(null); return d; })
      .catch((x) => { if (alive()) setErr({ key: k, msg: msgOf(x) }); return undefined; })
      .finally(() => { if (alive()) setFetching(false); });
  }, []);

  useEffect(() => {
    if (!path || !key) { setFetching(false); return; }
    let alive = true;
    const e = store.get(key);
    const age = e ? Date.now() - e.at : Infinity;
    if (age < ttl) { setFetching(false); return; }
    void run(path, key, () => alive); // vencido ou ausente: busca (o dado vencido segue visível)
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    if (!path || !key) return;
    let on = true;
    const fn = (ev: Ev) => {
      if (ev.type === "write" && ev.key === key) bump();
      else if (ev.type === "invalidate") void run(path, key, () => on).then(() => { if (on) bump(); });
    };
    subs.add(fn);
    return () => { on = false; subs.delete(fn); };
  }, [key, path, run]);

  const reload = useCallback(() => (path && key ? run(path, key, () => true) : Promise.resolve(undefined)), [path, key, run]);
  const error = err && err.key === key ? err.msg : null;
  return { data, error, loading: !!key && data === undefined && !error, refreshing: data !== undefined && fetching, reload };
}
