export function Meter({ label, value, max = 100, invert = false }: { label: string; value: number; max?: number; invert?: boolean }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const good = invert ? 100 - pct : pct;
  return (
    <div className={`meter ${good < 35 ? "low" : good < 60 ? "mid" : "high"}`}>
      <div className="meter-top"><span>{label}</span><span className="num">{Math.round(value)}</span></div>
      <div className="meter-bar"><i style={{ width: `${pct}%` }} /></div>
    </div>
  );
}
