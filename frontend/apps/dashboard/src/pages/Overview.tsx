import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { AreaChart, BarList } from "../components/charts";
import { PageHeader } from "../components/Shell";
import { Card, Empty, ErrorBox, Loading, Select, StatCard, Table } from "../components/ui";
import { get, type Overview, type SalesPoint, type TopProduct } from "../lib/api";
import { useBizKey, useBizPath, useSession } from "../lib/session";

export function rangeFor(days: number) {
  const to = new Date();
  const from = new Date(Date.now() - (days - 1) * 86400000);
  const iso = (d: Date) => d.toLocaleDateString("en-CA", { timeZone: "Asia/Baghdad" });
  return { from: iso(from), to: iso(to) };
}

export function SalesChart({ days, currency }: { days: number; currency: string }) {
  const { t, money, lang } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const [table, setTable] = useState(false);
  const r = rangeFor(days);
  const q = useQuery({ queryKey: key("sales", days), queryFn: () =>
    get<SalesPoint[]>(path(`/analytics/sales?from=${r.from}&to=${r.to}`)) });
  const fmtDate = (d: string) => new Date(d + "T00:00:00").toLocaleDateString(
    lang === "ar" ? "ar-IQ" : "en-GB", { day: "numeric", month: "short", numberingSystem: "latn" });
  return (
    <Card title={t("revenue_trend")} actions={
      <button type="button" className="text-[13px] text-info" onClick={() => setTable(!table)}>
        {table ? t("chart_view") : t("table_view")}</button>}>
      {q.isPending ? <Loading /> : q.isError ? <ErrorBox error={q.error} /> : table ? (
        <Table head={[t("date"), t("orders"), t("sales")]}>
          {q.data.map((p) => <tr key={p.date}><td className="px-4 py-2">{fmtDate(p.date)}</td>
            <td className="tabular px-4 py-2">{p.orders}</td><td className="tabular px-4 py-2">{money(p.sales, currency)}</td></tr>)}
        </Table>
      ) : (
        <AreaChart label={t("revenue_trend")} format={(v) => money(v, currency)}
          data={q.data.map((p) => ({ label: fmtDate(p.date), value: p.sales,
            sub: `${p.orders} ${t("orders")}` }))} />
      )}
    </Card>
  );
}

export function TopProducts({ days, currency }: { days: number; currency: string }) {
  const { t, lang, money } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const r = rangeFor(days);
  const q = useQuery({ queryKey: key("top", days), queryFn: () =>
    get<TopProduct[]>(path(`/analytics/top-products?from=${r.from}&to=${r.to}`)) });
  return (
    <Card title={t("best_sellers")}>
      {q.isPending ? <Loading /> : q.isError ? <ErrorBox error={q.error} /> : !q.data.length
        ? <Empty>{t("no_data")}</Empty> : (
          <BarList format={(v) => String(v)} data={q.data.map((p) => ({
            label: (lang === "en" && p.name_en) || p.name_ar, value: p.quantity,
            sub: money(p.revenue, currency) }))} />
        )}
    </Card>
  );
}

export function OverviewPage() {
  const { t, money, can, lang } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const [days, setDays] = useState(30);
  const r = rangeFor(days);
  const q = useQuery({ queryKey: key("overview", days), queryFn: () =>
    get<Overview>(path(`/analytics/overview?from=${r.from}&to=${r.to}`)), refetchInterval: 60_000 });
  const recent = useQuery({ queryKey: key("recent-customers"), enabled: can("customers.view"),
    queryFn: () => get<{ id: string; name: string; orders_count: number; total_spent: number;
      last_order_at: string }[]>(path("/analytics/recent-customers")) });

  return (
    <>
      <PageHeader title={t("overview")} actions={
        <Select aria-label="range" value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-auto">
          <option value={7}>{t("last_7")}</option><option value={30}>{t("last_30")}</option>
          <option value={90}>{t("last_90")}</option>
        </Select>} />
      {q.isPending ? <Loading /> : q.isError ? <ErrorBox error={q.error} onRetry={() => q.refetch()} /> : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label={t("today_orders")} value={q.data.today_orders} hint={money(q.data.today_sales, q.data.currency)} />
            <Link to="/orders?status=pending"><StatCard label={t("pending_orders")} value={
              <span className={q.data.pending_orders ? "text-warn" : ""}>{q.data.pending_orders}</span>} /></Link>
            <StatCard label={t("total_sales")} value={money(q.data.total_sales, q.data.currency)} hint={`${t("completed_orders")}: ${q.data.completed_orders}`} />
            <StatCard label={t("avg_order")} value={money(q.data.average_order_value, q.data.currency)} hint={`${t("total_orders")}: ${q.data.total_orders}`} />
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2"><SalesChart days={days} currency={q.data.currency} /></div>
            <TopProducts days={days} currency={q.data.currency} />
          </div>
          {can("customers.view") && (
            <Card title={t("recent_customers")}>
              {!recent.data?.length ? <Empty>{t("no_data")}</Empty> : (
                <ul className="divide-y divide-line">
                  {recent.data.map((c) => (
                    <li key={c.id} className="flex items-center justify-between py-2.5 text-[14px]">
                      <span className="font-medium">{c.name || "—"}</span>
                      <span className="tabular text-hint">{c.orders_count} · {money(c.total_spent, q.data.currency)} ·{" "}
                        {new Date(c.last_order_at).toLocaleDateString(lang === "ar" ? "ar-IQ" : "en-GB", { numberingSystem: "latn" })}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          )}
        </div>
      )}
    </>
  );
}
