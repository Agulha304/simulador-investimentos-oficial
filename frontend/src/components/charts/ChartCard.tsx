import { useState, type ReactNode } from "react";

export interface TableView { headers: string[]; rows: (string | number)[][] }

/** Cartão de gráfico: título, subtítulo, gráfico e uma visão em TABELA equivalente (acessível). */
export function ChartCard({ title, subtitle, table, children, empty }: {
  title: string; subtitle?: string; table: TableView; children: ReactNode; empty?: string | null;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <section className="card viz-card">
      <header className="viz-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p className="muted small">{subtitle}</p>}
        </div>
        {!empty && <button type="button" className="link-btn" aria-pressed={asTable} onClick={() => setAsTable(!asTable)}>
          {asTable ? "Ver gráfico" : "Ver tabela"}
        </button>}
      </header>
      {empty ? <div className="empty">{empty}</div> : asTable ? (
        <div className="table-wrap viz-table"><table>
          <thead><tr>{table.headers.map((h, i) => <th key={h} className={i ? "r" : ""}>{h}</th>)}</tr></thead>
          <tbody>{table.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={j ? "r num" : ""}>{c}</td>)}</tr>)}</tbody>
        </table></div>
      ) : <div className="viz-body">{children}</div>}
    </section>
  );
}

/** Tooltip no estilo do app (texto em tokens de texto, nunca na cor da série). */
export function TipBox({ title, rows }: { title: string; rows: { color?: string; label: string; value: string }[] }) {
  return (
    <div className="viz-tip">
      <div className="viz-tip-title">{title}</div>
      {rows.map((r) => (
        <div key={r.label} className="viz-tip-row">
          <span>{r.color && <i className="swatch" style={{ background: r.color }} />}{r.label}</span><b className="num">{r.value}</b>
        </div>
      ))}
    </div>
  );
}
