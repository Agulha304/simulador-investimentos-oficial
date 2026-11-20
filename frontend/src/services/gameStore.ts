// Partida ativa: quando existe, as chamadas de jogo enviam X-Game-Id e o backend passa a operar no mundo dela.
import { useSyncExternalStore } from "react";

export interface ActiveGame { id: number; kind: "LIFE" | "TRAINING"; name: string }
const KEY = "sim.game";
const listeners = new Set<() => void>();
let current: ActiveGame | null = (() => { try { const v = localStorage.getItem(KEY); return v ? (JSON.parse(v) as ActiveGame) : null; } catch { return null; } })();

export const gameStore = {
  get: () => current,
  set(g: ActiveGame | null) {
    current = g;
    try { if (g) localStorage.setItem(KEY, JSON.stringify(g)); else localStorage.removeItem(KEY); } catch { /* ignore */ }
    listeners.forEach((l) => l());
  },
  subscribe(l: () => void) { listeners.add(l); return () => listeners.delete(l); },
};
export const useActiveGame = () => useSyncExternalStore(gameStore.subscribe, gameStore.get);

// rotas da CONTA (fora da partida): não enviam X-Game-Id
export const ACCOUNT_PATHS = ["/games", "/auth", "/learn", "/ranking"];
