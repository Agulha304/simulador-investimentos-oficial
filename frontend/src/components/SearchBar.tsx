import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Asset } from "../services/api";
import { CLASS_LABEL } from "../lib/format";

export function SearchBar() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Asset[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (q.trim().length < 1) { setResults([]); return; }
    let cancelled = false;
    setBusy(true);
    const t = setTimeout(() => {
      api.searchAssets(q.trim())
        .then((r) => { if (!cancelled) { setResults(r); setOpen(true); } })
        .catch(() => { if (!cancelled) setResults([]); })
        .finally(() => { if (!cancelled) setBusy(false); });
    }, 250);
    return () => { cancelled = true; clearTimeout(t); };
  }, [q]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const pick = (a: Asset) => { setOpen(false); setQ(""); navigate(`/ativo/${a.id}`); };

  return (
    <div className="search" ref={box}>
      <input placeholder="Pesquisar ativo (PETR4, AAPL, Bitcoin, HGLG11…)" value={q}
        onChange={(e) => setQ(e.target.value)} onFocus={() => results.length && setOpen(true)}
        onKeyDown={(e) => { if (e.key === "Enter" && results[0]) pick(results[0]); if (e.key === "Escape") setOpen(false); }} />
      {open && q.trim() && (
        <ul className="search-results">
          {results.length === 0 && <li className="muted">{busy ? "Buscando…" : "Nenhum ativo encontrado"}</li>}
          {results.map((a) => (
            <li key={a.id} onMouseDown={() => pick(a)}>
              <b>{a.symbol}</b>
              <span className="grow">{a.name}</span>
              <span className="tag">{CLASS_LABEL[a.asset_class] ?? a.asset_class}</span>
              <span className="muted small">{a.country ?? "Global"}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
