import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { CategoryTotal, MonthRow } from "../../services/api";
import { VIZ, fmtCompactBRL } from "../../lib/viz";
import { fmtBRL, fmtMonthShort } from "../../lib/format";
import { ChartCard, TipBox } from "./ChartCard";

const AXIS = { stroke: VIZ.axis, tick: { fill: VIZ.text, fontSize: 11 }, tickLine: false } as const;
const legend = <Legend iconType="circle" wrapperStyle={{ color: VIZ.text, fontSize: 12 }} />;

/** Previsto x realizado por categoria de despesa (barras horizontais agrupadas). */
export function PlannedVsActualChart({ rows }: { rows: CategoryTotal[] }) {
  const data = rows.filter((r) => r.kind === "EXPENSE")
    .map((r) => ({ name: r.category_name, planned: Number(r.planned), realized: Number(r.realized) }));
  return (
    <ChartCard
      title="Previsto x realizado por categoria"
      subtitle="Despesas do mês aberto"
      empty={data.length ? null : "Adicione despesas ao orçamento para comparar o previsto com o realizado."}
      table={{ headers: ["Categoria", "Previsto", "Realizado"], rows: data.map((d) => [d.name, fmtBRL(String(d.planned)), fmtBRL(String(d.realized))]) }}
    >
      <ResponsiveContainer width="100%" height={Math.max(220, data.length * 46 + 50)}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }} barGap={2}>
          <CartesianGrid stroke={VIZ.grid} horizontal={false} />
          <XAxis type="number" {...AXIS} tickFormatter={fmtCompactBRL} />
          <YAxis type="category" dataKey="name" {...AXIS} width={120} />
          <Tooltip cursor={{ fill: VIZ.grid, opacity: 0.4 }} content={({ active, payload, label }) => active && payload?.length ? (
            <TipBox title={String(label)} rows={[
              { color: VIZ.s1, label: "Previsto", value: fmtBRL(String(payload[0]?.payload.planned)) },
              { color: VIZ.s2, label: "Realizado", value: fmtBRL(String(payload[0]?.payload.realized)) },
            ]} />
          ) : null} />
          {legend}
          <Bar dataKey="planned" name="Previsto" fill={VIZ.s1} radius={[0, 4, 4, 0]} barSize={12} />
          <Bar dataKey="realized" name="Realizado" fill={VIZ.s2} radius={[0, 4, 4, 0]} barSize={12} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

/** Receitas x despesas por mês (barras agrupadas). */
export function IncomeExpenseChart({ months }: { months: MonthRow[] }) {
  const data = [...months].reverse().map((m) => ({ t: fmtMonthShort(m.ref_month), income: Number(m.income), expense: Number(m.expense) }));
  return (
    <ChartCard
      title="Receitas e despesas por mês"
      empty={data.length ? null : "Ainda não há meses para exibir."}
      table={{ headers: ["Mês", "Receitas", "Despesas"], rows: data.map((d) => [d.t, fmtBRL(String(d.income)), fmtBRL(String(d.expense))]) }}
    >
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ left: 4, right: 12 }}>
          <CartesianGrid stroke={VIZ.grid} vertical={false} />
          <XAxis dataKey="t" {...AXIS} />
          <YAxis {...AXIS} tickFormatter={fmtCompactBRL} width={64} />
          <Tooltip cursor={{ fill: VIZ.grid, opacity: 0.4 }} content={({ active, payload, label }) => active && payload?.length ? (
            <TipBox title={String(label)} rows={[
              { color: VIZ.s1, label: "Receitas", value: fmtBRL(String(payload[0]?.payload.income)) },
              { color: VIZ.s2, label: "Despesas", value: fmtBRL(String(payload[0]?.payload.expense)) },
            ]} />
          ) : null} />
          {legend}
          <Bar dataKey="income" name="Receitas" fill={VIZ.s1} radius={[4, 4, 0, 0]} maxBarSize={22} />
          <Bar dataKey="expense" name="Despesas" fill={VIZ.s2} radius={[4, 4, 0, 0]} maxBarSize={22} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

/** Evolução do saldo ao fim de cada mês (um único eixo). */
export function BalanceChart({ months }: { months: MonthRow[] }) {
  const closed = [...months].reverse().filter((m) => m.closing_balance != null);
  const first = [...months].reverse()[0];
  const data = [
    ...(first ? [{ t: `início ${fmtMonthShort(first.ref_month)}`, balance: Number(first.opening_balance) }] : []),
    ...closed.map((m) => ({ t: fmtMonthShort(m.ref_month), balance: Number(m.closing_balance) })),
  ];
  return (
    <ChartCard
      title="Evolução do saldo"
      subtitle="Saldo em caixa ao fim de cada mês fechado"
      empty={closed.length ? null : "O gráfico aparece depois do primeiro fechamento de mês."}
      table={{ headers: ["Momento", "Saldo"], rows: data.map((d) => [d.t, fmtBRL(String(d.balance))]) }}
    >
      <ResponsiveContainer width="100%" height={240}>
        <AreaChart data={data} margin={{ left: 4, right: 12 }}>
          <CartesianGrid stroke={VIZ.grid} vertical={false} />
          <XAxis dataKey="t" {...AXIS} />
          <YAxis {...AXIS} tickFormatter={fmtCompactBRL} width={64} domain={["auto", "auto"]} />
          <Tooltip content={({ active, payload, label }) => active && payload?.length ? (
            <TipBox title={String(label)} rows={[{ color: VIZ.s1, label: "Saldo", value: fmtBRL(String(payload[0]?.payload.balance)) }]} />
          ) : null} />
          <Area type="monotone" dataKey="balance" stroke={VIZ.s1} strokeWidth={2} fill={VIZ.s1} fillOpacity={0.12}
            dot={{ r: 4, stroke: VIZ.surface, strokeWidth: 2, fill: VIZ.s1 }} />
        </AreaChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
