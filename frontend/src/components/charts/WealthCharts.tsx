import { Area, AreaChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { GoodDetail, WealthOverview } from "../../services/api";
import { VIZ, fmtCompactBRL } from "../../lib/viz";
import { fmtBRL, fmtMonthShort } from "../../lib/format";
import { ChartCard, TipBox } from "./ChartCard";

const AXIS = { stroke: VIZ.axis, tick: { fill: VIZ.text, fontSize: 11 }, tickLine: false } as const;
const dot = { r: 4, stroke: VIZ.surface, strokeWidth: 2 };

/** Evolução do valor dos bens e das dívidas (duas séries, um único eixo). */
export function WealthSeriesChart({ series }: { series: WealthOverview["series"] }) {
  const data = series.map((p) => ({ t: fmtMonthShort(p.ref_month), goods: Number(p.goods_value), debts: Number(p.debts) }));
  return (
    <ChartCard
      title="Evolução do patrimônio em bens"
      subtitle="Valor de mercado dos bens e dívidas associadas, mês a mês"
      empty={data.length >= 1 ? null : "Compre um bem para acompanhar a evolução."}
      table={{ headers: ["Mês", "Bens", "Dívidas"], rows: data.map((d) => [d.t, fmtBRL(String(d.goods)), fmtBRL(String(d.debts))]) }}
    >
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={data} margin={{ left: 4, right: 12 }}>
          <CartesianGrid stroke={VIZ.grid} vertical={false} />
          <XAxis dataKey="t" {...AXIS} />
          <YAxis {...AXIS} tickFormatter={fmtCompactBRL} width={64} />
          <Tooltip content={({ active, payload, label }) => active && payload?.length ? (
            <TipBox title={String(label)} rows={[
              { color: VIZ.s1, label: "Bens", value: fmtBRL(String(payload[0]?.payload.goods)) },
              { color: VIZ.s2, label: "Dívidas", value: fmtBRL(String(payload[0]?.payload.debts)) },
            ]} />
          ) : null} />
          <Legend iconType="circle" wrapperStyle={{ color: VIZ.text, fontSize: 12 }} />
          <Area type="monotone" dataKey="goods" name="Bens" stroke={VIZ.s1} strokeWidth={2} fill={VIZ.s1} fillOpacity={0.12} dot={dot} />
          <Area type="monotone" dataKey="debts" name="Dívidas" stroke={VIZ.s2} strokeWidth={2} fill={VIZ.s2} fillOpacity={0.08} dot={dot} />
        </AreaChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

/** Histórico de valor de um bem (nunca reescrito: cada mês é uma linha). */
export function ValueHistoryChart({ values }: { values: GoodDetail["values"] }) {
  const data = values.map((v) => ({ t: fmtMonthShort(v.ref_month), value: Number(v.value) }));
  return (
    <ChartCard
      title="Evolução do valor"
      empty={data.length >= 2 ? null : "O histórico aparece a partir do primeiro fechamento de mês."}
      table={{ headers: ["Mês", "Valor"], rows: values.map((v) => [fmtMonthShort(v.ref_month), fmtBRL(v.value)]) }}
    >
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ left: 4, right: 12 }}>
          <CartesianGrid stroke={VIZ.grid} vertical={false} />
          <XAxis dataKey="t" {...AXIS} />
          <YAxis {...AXIS} tickFormatter={fmtCompactBRL} width={64} domain={["auto", "auto"]} />
          <Tooltip content={({ active, payload, label }) => active && payload?.length ? (
            <TipBox title={String(label)} rows={[{ color: VIZ.s1, label: "Valor", value: fmtBRL(String(payload[0]?.payload.value)) }]} />
          ) : null} />
          <Line type="monotone" dataKey="value" stroke={VIZ.s1} strokeWidth={2} dot={dot} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
