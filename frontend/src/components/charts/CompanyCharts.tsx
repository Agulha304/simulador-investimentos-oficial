import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { CoMonth } from "../../services/api";
import { VIZ, fmtCompactBRL } from "../../lib/viz";
import { fmtBRL, fmtMonthShort } from "../../lib/format";
import { ChartCard, TipBox } from "./ChartCard";

const AXIS = { stroke: VIZ.axis, tick: { fill: VIZ.text, fontSize: 11 }, tickLine: false } as const;

/** Receita x custos totais por mês (barras agrupadas). */
export function RevenueCostChart({ months }: { months: CoMonth[] }) {
  const data = [...months].reverse().map((m) => ({
    t: fmtMonthShort(m.ref_month), revenue: Number(m.revenue),
    costs: Number(m.variable_costs) + Number(m.fixed_costs) + Number(m.payroll) + Number(m.taxes) + Number(m.interest),
  }));
  return (
    <ChartCard title="Receita e custos por mês" empty={data.length ? null : "Os gráficos aparecem depois do primeiro fechamento de mês."}
      table={{ headers: ["Mês", "Receita", "Custos"], rows: data.map((d) => [d.t, fmtBRL(String(d.revenue)), fmtBRL(String(d.costs))]) }}>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data} margin={{ left: 4, right: 12 }}>
          <CartesianGrid stroke={VIZ.grid} vertical={false} />
          <XAxis dataKey="t" {...AXIS} />
          <YAxis {...AXIS} tickFormatter={fmtCompactBRL} width={64} />
          <Tooltip cursor={{ fill: VIZ.grid, opacity: 0.4 }} content={({ active, payload, label }) => active && payload?.length ? (
            <TipBox title={String(label)} rows={[
              { color: VIZ.s1, label: "Receita", value: fmtBRL(String(payload[0]?.payload.revenue)) },
              { color: VIZ.s2, label: "Custos", value: fmtBRL(String(payload[0]?.payload.costs)) },
            ]} />
          ) : null} />
          <Legend iconType="circle" wrapperStyle={{ color: VIZ.text, fontSize: 12 }} />
          <Bar dataKey="revenue" name="Receita" fill={VIZ.s1} radius={[4, 4, 0, 0]} maxBarSize={22} />
          <Bar dataKey="costs" name="Custos" fill={VIZ.s2} radius={[4, 4, 0, 0]} maxBarSize={22} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

/** Resultado líquido por mês: o sinal aparece no eixo e no texto (nunca só na cor). */
export function NetResultChart({ months }: { months: CoMonth[] }) {
  const data = [...months].reverse().map((m) => ({ t: fmtMonthShort(m.ref_month), net: Number(m.net_result) }));
  return (
    <ChartCard title="Resultado líquido por mês" empty={data.length ? null : "Sem meses fechados ainda."}
      table={{ headers: ["Mês", "Resultado"], rows: data.map((d) => [d.t, `${d.net >= 0 ? "▲ " : "▼ "}${fmtBRL(String(d.net))}`]) }}>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ left: 4, right: 12 }}>
          <CartesianGrid stroke={VIZ.grid} vertical={false} />
          <XAxis dataKey="t" {...AXIS} />
          <YAxis {...AXIS} tickFormatter={fmtCompactBRL} width={64} />
          <ReferenceLine y={0} stroke={VIZ.axis} />
          <Tooltip cursor={{ fill: VIZ.grid, opacity: 0.4 }} content={({ active, payload, label }) => active && payload?.length ? (
            <TipBox title={String(label)} rows={[{ color: VIZ.s1, label: Number(payload[0]?.payload.net) >= 0 ? "▲ Lucro" : "▼ Prejuízo", value: fmtBRL(String(payload[0]?.payload.net)) }]} />
          ) : null} />
          <Bar dataKey="net" name="Resultado" fill={VIZ.s1} radius={[4, 4, 0, 0]} maxBarSize={26} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
