import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, LabelList, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { Performance } from "../../services/api";
import { VIZ, fmtCompactBRL, fmtNum, fmtSigned, fmtTick } from "../../lib/viz";
import { fmtBRL } from "../../lib/format";
import { ChartCard, TipBox } from "./ChartCard";

const AXIS = { stroke: VIZ.axis, tick: { fill: VIZ.text, fontSize: 11 }, tickLine: false } as const;
const GRID = <CartesianGrid stroke={VIZ.grid} vertical={false} />;      // hairline sólida e recessiva
const ring = { r: 4, stroke: VIZ.surface, strokeWidth: 2 };               // marcador com anel da cor do fundo
const monthLabel = (m: string) => new Intl.DateTimeFormat("pt-BR", { month: "short", year: "2-digit" }).format(new Date(`${m}-01T12:00:00`));
const dayLabel = (iso: string) => new Intl.DateTimeFormat("pt-BR").format(new Date(`${iso}T12:00:00`));
const arrow = (v: number) => (v > 0 ? "▲ " : v < 0 ? "▼ " : "");

type Pt = Performance["series"][number];

function useSeries(points: Pt[]) {
  const hourly = points.length > 1 && new Set(points.map((p) => p.t.slice(0, 10))).size < points.length / 1.5;
  return { hourly };
}

export function EquityChart({ points }: { points: Pt[] }) {
  const { hourly } = useSeries(points);
  const data = points.map((p) => ({ t: p.t, wealth: Number(p.wealth), equity: Number(p.equity) }));
  return (
    <ChartCard title="Evolução do patrimônio" subtitle="Saldo + posições + renda fixa, sem contar aportes virtuais extras"
      empty={points.length === 0 ? "Ainda não há registros." : null}
      table={{ headers: ["Momento", "Patrimônio", "Patrimônio total"], rows: points.map((p) => [fmtTick(p.t, true), fmtBRL(p.wealth), fmtBRL(p.equity)]) }}>
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
          <defs><linearGradient id="gEquity" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={VIZ.s1} stopOpacity={0.22} /><stop offset="100%" stopColor={VIZ.s1} stopOpacity={0} />
          </linearGradient></defs>
          {GRID}
          <XAxis dataKey="t" {...AXIS} tickFormatter={(v: string) => fmtTick(v, hourly)} minTickGap={36} />
          <YAxis {...AXIS} width={64} tickFormatter={fmtCompactBRL} domain={[(min: number) => min * 0.995, (max: number) => max * 1.005]} />
          <Tooltip cursor={{ stroke: VIZ.axis }} content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as (typeof data)[number];
            return <TipBox title={fmtTick(d.t, true)} rows={[
              { color: VIZ.s1, label: "Patrimônio", value: fmtBRL(String(d.wealth)) },
              ...(d.equity !== d.wealth ? [{ label: "Total com aportes extras", value: fmtBRL(String(d.equity)) }] : [])]} />;
          }} />
          <Area type="monotone" dataKey="wealth" stroke={VIZ.s1} strokeWidth={2} fill="url(#gEquity)" dot={data.length === 1 ? ring : false} activeDot={ring} />
        </AreaChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

function EndLabel({ x, y, index, last, text }: { x?: number; y?: number; index?: number; last: number; text: string }) {
  if (index !== last || x == null || y == null) return null;
  return <text x={x + 8} y={y + 4} fill="#e3eef2" fontSize={12} fontWeight={600}>{text}</text>;
}

export function ReturnVsCdiChart({ points }: { points: Pt[] }) {
  const { hourly } = useSeries(points);
  const data = points.map((p) => ({ t: p.t, you: Number(p.return_pct), cdi: Number(p.cdi_pct) }));
  const last = data.length - 1;
  return (
    <ChartCard title="Sua rentabilidade vs CDI" subtitle="Variação desde o primeiro registro do período, em %"
      empty={points.length < 2 ? "Precisamos de pelo menos dois registros. Volte daqui a algumas horas." : null}
      table={{ headers: ["Momento", "Você (%)", "CDI (%)"], rows: points.map((p) => [fmtTick(p.t, true), fmtNum(Number(p.return_pct)), fmtNum(Number(p.cdi_pct))]) }}>
      <div className="legend"><span><i style={{ background: VIZ.s1 }} />Você</span><span><i style={{ background: VIZ.s2 }} />CDI</span></div>
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={data} margin={{ top: 8, right: 70, bottom: 0, left: 4 }}>
          {GRID}
          <XAxis dataKey="t" {...AXIS} tickFormatter={(v: string) => fmtTick(v, hourly)} minTickGap={36} />
          <YAxis {...AXIS} width={48} tickFormatter={(v: number) => `${fmtNum(v, 1)}%`} />
          <ReferenceLine y={0} stroke={VIZ.axis} />
          <Tooltip cursor={{ stroke: VIZ.axis }} content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as (typeof data)[number];
            return <TipBox title={fmtTick(d.t, true)} rows={[
              { color: VIZ.s1, label: "Você", value: `${fmtSigned(d.you)}%` }, { color: VIZ.s2, label: "CDI", value: `${fmtSigned(d.cdi)}%` }]} />;
          }} />
          <Line type="monotone" dataKey="you" stroke={VIZ.s1} strokeWidth={2} dot={false} activeDot={ring}
            label={<EndLabel last={last} text={`Você ${fmtSigned(data[last]?.you ?? 0)}%`} />} />
          <Line type="monotone" dataKey="cdi" stroke={VIZ.s2} strokeWidth={2} dot={false} activeDot={ring}
            label={<EndLabel last={last} text={`CDI ${fmtSigned(data[last]?.cdi ?? 0)}%`} />} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function DrawdownChart({ points }: { points: Pt[] }) {
  const { hourly } = useSeries(points);
  const data = points.map((p) => ({ t: p.t, dd: Number(p.drawdown_pct) }));
  const low = Math.min(0, ...data.map((d) => d.dd));
  return (
    <ChartCard title="▼ Queda desde o pico" subtitle="Quanto o patrimônio está abaixo do seu maior valor até então"
      empty={points.length < 2 ? "Disponível a partir do segundo registro." : null}
      table={{ headers: ["Momento", "Queda desde o pico (%)"], rows: points.map((p) => [fmtTick(p.t, true), fmtNum(Number(p.drawdown_pct))]) }}>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
          {GRID}
          <XAxis dataKey="t" {...AXIS} tickFormatter={(v: string) => fmtTick(v, hourly)} minTickGap={36} />
          <YAxis {...AXIS} width={48} domain={[Math.floor(low * 1.2 - 0.5), 0]} tickFormatter={(v: number) => `${fmtNum(v, 0)}%`} />
          <Tooltip cursor={{ stroke: VIZ.axis }} content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as (typeof data)[number];
            return <TipBox title={fmtTick(d.t, true)} rows={[{ color: VIZ.critical, label: "▼ Queda desde o pico", value: `${fmtNum(d.dd)}%` }]} />;
          }} />
          <Area type="monotone" dataKey="dd" stroke={VIZ.critical} strokeWidth={2} fill={VIZ.critical} fillOpacity={0.14} dot={false} activeDot={ring} />
        </AreaChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function AllocationChart({ items }: { items: Performance["allocation"] }) {
  const data = items.map((a) => ({ label: a.label, pct: Number(a.pct), value: Number(a.value) }));
  return (
    <ChartCard title="Composição da carteira" subtitle="Parte de cada classe no patrimônio, da maior para a menor"
      empty={data.length === 0 ? "Sem posições." : null}
      table={{ headers: ["Classe", "% do patrimônio", "Valor"], rows: items.map((a) => [a.label, `${fmtNum(Number(a.pct), 1)}%`, fmtBRL(a.value)]) }}>
      <ResponsiveContainer width="100%" height={Math.max(150, data.length * 38 + 24)}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 56, bottom: 0, left: 4 }} barCategoryGap={10}>
          <XAxis type="number" domain={[0, 100]} hide />
          <YAxis type="category" dataKey="label" {...AXIS} width={112} axisLine={false} />
          <Tooltip cursor={{ fill: "rgba(138,165,177,0.08)" }} content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as (typeof data)[number];
            return <TipBox title={d.label} rows={[{ label: "Participação", value: `${fmtNum(d.pct, 1)}%` }, { label: "Valor", value: fmtBRL(String(d.value)) }]} />;
          }} />
          <Bar dataKey="pct" fill={VIZ.s1} barSize={14} radius={[0, 4, 4, 0]}>
            <LabelList dataKey="pct" position="right" fill="#e3eef2" fontSize={12} formatter={(v: number) => `${fmtNum(v, 1)}%`} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function MonthlyChart({ items }: { items: Performance["monthly"] }) {
  const data = items.map((m) => ({ month: m.month, realized: Number(m.realized), income: Number(m.income) }));
  return (
    <ChartCard title="Resultado por mês" subtitle="Ganhos e perdas realizados em vendas/resgates e proventos recebidos. Barras abaixo do zero são perdas"
      empty={data.length === 0 ? "Nenhuma operação encerrada ainda." : null}
      table={{ headers: ["Mês", "Vendas e resgates", "Proventos e juros", "Operações"], rows: items.map((m) => [monthLabel(m.month), `${arrow(Number(m.realized))}${fmtBRL(m.realized)}`, fmtBRL(m.income), m.trades]) }}>
      <div className="legend"><span><i style={{ background: VIZ.s1 }} />Vendas e resgates</span><span><i style={{ background: VIZ.s2 }} />Proventos e juros</span></div>
      <ResponsiveContainer width="100%" height={230}>
        <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 4 }} barGap={2}>
          {GRID}
          <XAxis dataKey="month" {...AXIS} tickFormatter={monthLabel} />
          <YAxis {...AXIS} width={64} tickFormatter={fmtCompactBRL} />
          <ReferenceLine y={0} stroke={VIZ.axis} />
          <Tooltip cursor={{ fill: "rgba(138,165,177,0.08)" }} content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as (typeof data)[number];
            return <TipBox title={monthLabel(d.month)} rows={[
              { color: VIZ.s1, label: `${arrow(d.realized)}Vendas e resgates`, value: fmtBRL(String(d.realized)) },
              { color: VIZ.s2, label: "Proventos e juros", value: fmtBRL(String(d.income)) }]} />;
          }} />
          <Bar dataKey="realized" fill={VIZ.s1} barSize={14} radius={[4, 4, 0, 0]} />
          <Bar dataKey="income" fill={VIZ.s2} barSize={14} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function CumulativeChart({ items }: { items: Performance["realized_cumulative"] }) {
  const data = items.map((c) => ({ date: c.date, total: Number(c.cumulative) }));
  return (
    <ChartCard title="Ganhos realizados acumulados" subtitle="Soma de vendas, resgates, proventos e juros ao longo do tempo"
      empty={data.length === 0 ? "Quando você encerrar operações ou receber proventos, a curva aparece aqui." : null}
      table={{ headers: ["Data", "Acumulado"], rows: items.map((c) => [dayLabel(c.date), `${arrow(Number(c.cumulative))}${fmtBRL(c.cumulative)}`]) }}>
      <ResponsiveContainer width="100%" height={230}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
          {GRID}
          <XAxis dataKey="date" {...AXIS} tickFormatter={dayLabel} minTickGap={36} />
          <YAxis {...AXIS} width={64} tickFormatter={fmtCompactBRL} />
          <ReferenceLine y={0} stroke={VIZ.axis} />
          <Tooltip cursor={{ stroke: VIZ.axis }} content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as (typeof data)[number];
            return <TipBox title={dayLabel(d.date)} rows={[{ color: VIZ.s1, label: `${arrow(d.total)}Acumulado`, value: fmtBRL(String(d.total)) }]} />;
          }} />
          <Line type="stepAfter" dataKey="total" stroke={VIZ.s1} strokeWidth={2} dot={data.length === 1 ? ring : false} activeDot={ring} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
