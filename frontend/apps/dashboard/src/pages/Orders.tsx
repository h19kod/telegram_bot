import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { PageHeader } from "../components/Shell";
import { STATUSES, StatusBadge } from "../components/status";
import { Badge, Button, cx, ErrorBox, errorMessage, Input, Loading, Modal, Pager, Select, Table,
  useUi } from "../components/ui";
import { download, get, post, qs, type Branch, type Member, type OrderDetail, type OrderRow, type OrderStatus,
  type Paginated } from "../lib/api";
import type { TKey } from "../lib/i18n";
import { useLiveOrders } from "../lib/live";
import { printReceipt } from "../lib/receipt";
import { useBizKey, useBizPath, useSession } from "../lib/session";

function fmt(iso: string, lang: string) {
  return new Date(iso).toLocaleString(lang === "ar" ? "ar-IQ" : "en-GB", { dateStyle: "short",
    timeStyle: "short", numberingSystem: "latn", timeZone: "Asia/Baghdad" });
}

export function OrdersPage() {
  const { t, money, lang, can } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const live = useLiveOrders();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("search") ?? "");
  const [openId, setOpenId] = useState<string | null>(null);
  const filters = { status: params.get("status") ?? "", search: params.get("search") ?? "",
    placed_after: params.get("from") ? `${params.get("from")}T00:00:00+03:00` : "",
    placed_before: params.get("to") ? `${params.get("to")}T23:59:59+03:00` : "",
    branch: params.get("branch") ?? "",
    page: params.get("page") ?? "1" };
  const branches = useQuery({ queryKey: key("branches"), queryFn: () => get<Branch[]>(path("/branches")) });
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v); else next.delete(k);
    if (k !== "page") next.delete("page");
    setParams(next, { replace: true });
  };
  const q = useQuery({ queryKey: key("orders", filters), placeholderData: (p) => p,
    queryFn: () => get<Paginated<OrderRow>>(path(`/orders${qs(filters)}`)),
    refetchInterval: live.connected ? false : 20_000 });
  const exportQs = qs({ ...filters, page: undefined });

  return (
    <>
      <PageHeader title={t("orders")} actions={<>
        <Badge tone={live.connected ? "success" : "neutral"}>● {live.connected ? t("live") : t("offline")}</Badge>
        {can("reports.export") && <>
          <Button variant="secondary" size="sm" onClick={() => download(path(`/orders/export${exportQs}${exportQs ? "&" : "?"}format_type=csv`), "orders.csv")}>{t("export_csv")}</Button>
          <Button variant="secondary" size="sm" onClick={() => download(path(`/orders/export${exportQs}${exportQs ? "&" : "?"}format_type=xlsx`), "orders.xlsx")}>{t("export_xlsx")}</Button>
        </>}
      </>}>
        <div className="mt-4 flex flex-wrap gap-2">
          <form onSubmit={(e) => { e.preventDefault(); set("search", search.trim()); }} className="min-w-52 flex-1">
            <Input type="search" placeholder={`${t("search")} #1042 / 0770…`} value={search} onChange={(e) => setSearch(e.target.value)} />
          </form>
          {(branches.data?.length ?? 0) > 1 && (
            <Select aria-label={t("all_branches")} className="w-auto" value={filters.branch} onChange={(e) => set("branch", e.target.value)}>
              <option value="">{t("all_branches")}</option>
              {branches.data?.map((b) => <option key={b.id} value={b.id}>{(lang === "en" && b.name_en) || b.name_ar}</option>)}
            </Select>
          )}
          <Select aria-label={t("status")} className="w-auto" value={filters.status} onChange={(e) => set("status", e.target.value)}>
            <option value="">{t("all_statuses")}</option>
            {STATUSES.map((s) => <option key={s} value={s}>{t(`status_${s}` as TKey)}</option>)}
          </Select>
          <Input aria-label={t("from")} type="date" className="w-auto" value={params.get("from") ?? ""} onChange={(e) => set("from", e.target.value)} />
          <Input aria-label={t("to")} type="date" className="w-auto" value={params.get("to") ?? ""} onChange={(e) => set("to", e.target.value)} />
        </div>
      </PageHeader>
      {q.isPending ? <Loading /> : q.isError ? <ErrorBox error={q.error} onRetry={() => q.refetch()} /> : (
        <>
          <Table empty={!q.data.results.length} head={[t("order"), t("customer"), t("status"),
            t("fulfilment"), t("total"), t("time")]}>
            {q.data.results.map((o) => (
              <tr key={o.id} onClick={() => setOpenId(o.id)} tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && setOpenId(o.id)}
                className={cx("cursor-pointer hover:bg-bg2/60", o.status === "pending" && "bg-warn/5")}>
                <td className="px-4 py-3 font-bold">#{o.number}</td>
                <td className="px-4 py-3"><div className="font-medium">{o.customer_name}</div>
                  <div dir="ltr" className="text-[12px] text-hint">{o.customer_phone}</div></td>
                <td className="px-4 py-3"><StatusBadge status={o.status} /></td>
                <td className="px-4 py-3 text-[13px]">{o.fulfilment === "delivery" ? `🛵 ${o.zone_name_snapshot}` : o.fulfilment === "dine_in" ? `🍽 ${t("table_f", { n: o.table_label })}` : `🏪 ${t("pickup_f")}`}</td>
                <td className="tabular px-4 py-3 font-semibold">{money(o.total, o.currency)}</td>
                <td className="tabular px-4 py-3 text-[13px] text-hint">{fmt(o.placed_at, lang)}</td>
              </tr>
            ))}
          </Table>
          <Pager page={Number(filters.page)} count={q.data.count} onPage={(p) => set("page", String(p))} />
        </>
      )}
      <OrderModal id={openId} onClose={() => setOpenId(null)} />
    </>
  );
}

function OrderModal({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { t, money, lang, can, membership } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { confirm, toast } = useUi();
  const q = useQuery({ queryKey: key("order", id), enabled: Boolean(id),
    queryFn: () => get<OrderDetail>(path(`/orders/${id}`)) });
  const drivers = useQuery({ queryKey: key("drivers"), enabled: Boolean(id) && can("orders.assign_driver"),
    queryFn: () => get<Member[]>(path("/members/drivers")) });
  const move = useMutation({
    mutationFn: (v: { to: OrderStatus; reason?: string }) => post<OrderDetail>(path(`/orders/${id}/transition`),
      { to: v.to, expected_version: q.data?.version, reason: v.reason }),
    onSuccess: (o) => { qc.setQueryData(key("order", id), o); qc.invalidateQueries({ queryKey: key("orders") }); },
    onError: (e) => { toast(errorMessage(e, t("error")), "error"); q.refetch(); },
  });
  const assign = useMutation({
    mutationFn: (driver_id: string) => post<OrderDetail>(path(`/orders/${id}/assign-driver`), { driver_id: driver_id || null }),
    onSuccess: (o) => qc.setQueryData(key("order", id), o),
    onError: (e) => toast(errorMessage(e, t("error")), "error"),
  });
  const o = q.data;
  async function act(to: OrderStatus) {
    if (to === "rejected" || to === "cancelled") {
      const reason = await confirm({ title: t(`act_${to}` as TKey), danger: true, input: t("reason_required") });
      if (reason) move.mutate({ to, reason });
    } else move.mutate({ to });
  }
  const fulfilmentLabel = (x: OrderDetail) => x.fulfilment === "delivery" ? `🛵 ${t("delivery_f")}`
    : x.fulfilment === "dine_in" ? `🍽 ${t("table_f", { n: x.table_label })}` : `🏪 ${t("pickup_f")}`;
  const optName = (x: { option_name_ar: string; option_name_en: string }) => (lang === "en" && x.option_name_en) || x.option_name_ar;
  return (
    <Modal wide open={Boolean(id)} onClose={onClose} title={o ? `${t("order")} #${o.number}` : "…"}
      footer={o && o.allowed_actions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {o.allowed_actions.map((a) => (
            <Button key={a} disabled={move.isPending} variant={a === "rejected" || a === "cancelled" ? "danger" : "primary"}
              onClick={() => act(a)}>{t(`act_${a}` as TKey)}</Button>
          ))}
        </div>
      )}>
      {q.isPending ? <Loading /> : q.isError ? <ErrorBox error={q.error} /> : o && (
        <div className="grid gap-5 md:grid-cols-[1fr_260px]">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2"><StatusBadge status={o.status} />
              <Badge>{fulfilmentLabel(o)}</Badge>
              <Badge>{o.channel}</Badge>
              <Button size="sm" variant="secondary" className="ms-auto" onClick={() => printReceipt(o, {
                shop: (lang === "en" && membership?.business_name_en) || membership?.business_name_ar || "",
                order: t("order"), fulfilment: fulfilmentLabel(o), subtotal: t("subtotal"),
                delivery: t("delivery_fee"), discount: t("discount"), total: t("total"),
                customer: t("customer"), notes: t("notes"), thanks: t("receipt_thanks"),
              }, (n) => money(n, o.currency), lang, fmt(o.placed_at, lang))}>🖨️ {t("print_receipt")}</Button></div>
            <ul className="divide-y divide-line rounded-lg border border-line">
              {o.items.map((i) => (
                <li key={i.id} className="flex justify-between gap-3 p-3 text-[14px]">
                  <div><p className="font-medium">{(lang === "en" && i.product_name_en) || i.product_name_ar} × {i.quantity}</p>
                    {i.options.length > 0 && <p className="text-[12px] text-hint">{i.options.map(optName).join("، ")}</p>}
                    {i.note && <p className="text-[12px] text-warn">📝 {i.note}</p>}</div>
                  <span className="tabular shrink-0">{money(i.line_total, o.currency)}</span>
                </li>
              ))}
              <li className="space-y-1 p-3 text-[14px]">
                <div className="flex justify-between text-hint"><span>{t("subtotal")}</span><span className="tabular">{money(o.subtotal, o.currency)}</span></div>
                {o.delivery_fee > 0 && <div className="flex justify-between text-hint"><span>{t("delivery_fee")}</span><span className="tabular">{money(o.delivery_fee, o.currency)}</span></div>}
                {o.discount_total > 0 && <div className="flex justify-between text-success"><span>{t("discount")}</span><span className="tabular">-{money(o.discount_total, o.currency)}</span></div>}
                <div className="flex justify-between font-bold"><span>{t("total")}</span><span className="tabular">{money(o.total, o.currency)}</span></div>
              </li>
            </ul>
            {o.notes && <p className="rounded-lg bg-warn/8 p-3 text-[14px]">🗒 {o.notes}</p>}
          </div>
          <div className="space-y-4 text-[14px]">
            <div><p className="text-[12px] text-hint">{t("customer")}</p><p className="font-semibold">{o.customer_name}</p>
              <a dir="ltr" href={`tel:${o.customer_phone}`} className="text-info">{o.customer_phone}</a></div>
            {o.address && <div><p className="text-[12px] text-hint">{t("address")}</p>
              {Object.values(o.address).filter(Boolean).map((v, i) => <p key={i}>{v}</p>)}</div>}
            {can("orders.assign_driver") && o.fulfilment === "delivery" && !["delivered", "cancelled", "rejected"].includes(o.status) && (
              <label className="block"><span className="text-[12px] text-hint">{t("assign_driver")}</span>
                <Select value={o.assigned_driver ?? ""} disabled={assign.isPending} onChange={(e) => assign.mutate(e.target.value)}>
                  <option value="">{t("none")}</option>
                  {drivers.data?.map((d) => <option key={d.id} value={d.id}>{d.full_name || d.email}</option>)}
                </Select></label>
            )}
            <div><p className="mb-1 text-[12px] text-hint">{t("history")}</p>
              <ol className="space-y-1.5 border-s-2 border-line ps-3">
                {o.events.map((e, i) => (
                  <li key={i}><span className="font-medium">{t(`status_${e.to_status}` as TKey)}</span>
                    <span className="block text-[12px] text-hint">{fmt(e.created_at, lang)}{e.actor && ` · ${e.actor}`} · {e.source}</span>
                    {e.reason && <span className="block text-[12px]">{e.reason}</span>}</li>
                ))}
              </ol></div>
          </div>
        </div>
      )}
    </Modal>
  );
}
