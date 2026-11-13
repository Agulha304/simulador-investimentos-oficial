import type { ReactNode } from "react";

export function StatCard({ label, value, sub, tone = "neutral", emphasis = false }: {
  label: string; value: ReactNode; sub?: ReactNode; tone?: "up" | "down" | "flat" | "neutral"; emphasis?: boolean;
}) {
  return (
    <div className={`card stat${emphasis ? " emphasis" : ""}`}>
      <span className="stat-label">{label}</span>
      <span className={`stat-value num tone-${tone}`}>{value}</span>
      {sub && <span className={`stat-sub num tone-${tone}`}>{sub}</span>}
    </div>
  );
}
