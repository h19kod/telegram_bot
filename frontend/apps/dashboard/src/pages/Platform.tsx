import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader } from "../components/Shell";
import { Badge, Button, Card, cx, ErrorBox, errorMessage, Field, Input, Loading, Modal, Select,
  StatCard, Table, useUi } from "../components/ui";
import { del, get, post, put, qs, type Feature, type Paginated, type Plan,
  type PlatformBusiness } from "../lib/api";
import { useSession } from "../lib/session";

type PBiz = PlatformBusiness;

const TABS = ["businesses", "plans", "stats", "health", "support"] as const;

export function PlatformPage() {
  const { t } = useSession();
  const [tab, setTab] = useState<(typeof TABS)[number]>("businesses");
  const labels = { businesses: t("businesses"), plans: t("plans"), stats: t("stats"), health: t("health"), support: t("support") };
  return (
    <>
      <PageHeader title={t("platform")}>
        <div role="tablist" className="mt-4 flex flex-wrap gap-1 border-b border-line">
          {TABS.map((x) => <button key={x} role="tab" aria-selected={tab === x} type="button" onClick={() => setTab(x)}
            className={cx("-mb-px border-b-2 px-3 py-2 text-[14px] font-medium", tab === x ? "border-accent text-accent" : "border-transparent text-hint")}>{labels[x]}</button>)}
        </div>
      </PageHeader>
      {tab === "businesses" && <Businesses />}
      {tab === "plans" && <Plans />}
      {tab === "stats" && <Stats />}
      {tab === "health" && <Health />}
      {tab === "support" && <Tickets />}
    </>
  );
}

function Businesses() {
  const { t } = useSession();
  const qc = useQueryClient();
  const { toast } = useUi();
  const [f, setF] = useState({ search: "", status: "" });
  const [open, setOpen] = useState<PBiz | null>(null);
  const [creating, setCreating] = useState(false);
  const [nb, setNb] = useState({ owner_email: "", slug: "", name_ar: "", plan: "free" });
  const q = useQuery({ queryKey: ["platform", "businesses", f], queryFn: () => get<Paginated<PBiz>>(`/platform/businesses${qs(f)}`) });
  const create = useMutation({ mutationFn: () => post("/platform/businesses", nb), onSuccess: () => { setCreating(false); qc.invalidateQueries({ queryKey: ["platform"] }); },
    onError: (e) => toast(errorMessage(e, t("error")), "error") });
  return (
    <>
      <div className="mb-4 flex flex-wrap gap-2">
        <Input type="search" placeholder={t("search")} className="min-w-52 flex-1" value={f.search} onChange={(e) => setF({ ...f, search: e.target.value })} />
        <Select aria-label={t("status")} className="w-auto" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
          <option value="">{t("all_statuses")}</option><option value="active">active</option><option value="suspended">suspended</option><option value="inactive">inactive</option></Select>
        <Button onClick={() => setCreating(true)}>+ {t("create")}</Button>
      </div>
      {q.isPending ? <Loading /> : q.isError ? <ErrorBox error={q.error} /> : (
        <Table empty={!q.data.results.length} head={[t("businesses"), t("owner_email"), t("plan"), t("status"), t("orders"), ""]}>
          {q.data.results.map((b) => (
            <tr key={b.id}>
              <td className="px-4 py-2.5"><p className="font-medium">{b.name_ar}</p><p className="text-[12px] text-hint" dir="ltr">{b.slug}</p></td>
              <td className="px-4 py-2.5" dir="ltr">{b.owner_email}</td>
              <td className="px-4 py-2.5">{b.plan ?? "—"} {b.subscription_status && <Badge>{b.subscription_status}</Badge>}</td>
              <td className="px-4 py-2.5"><Badge tone={b.status === "active" ? "success" : "danger"}>{b.status}</Badge></td>
              <td className="tabular px-4 py-2.5">{b.orders_count}</td>
              <td className="px-4 py-2.5 text-end"><Button size="sm" variant="secondary" onClick={() => setOpen(b)}>{t("edit")}</Button></td>
            </tr>))}
        </Table>
      )}
      <Modal open={creating} onClose={() => setCreating(false)} title={t("create_business")} footer={<Button disabled={create.isPending} onClick={() => create.mutate()}>{t("create")}</Button>}>
        <div className="space-y-3">
          <Field label={t("owner_email")}><Input dir="ltr" type="email" value={nb.owner_email} onChange={(e) => setNb({ ...nb, owner_email: e.target.value })} /></Field>
          <Field label={t("business_name")}><Input value={nb.name_ar} onChange={(e) => setNb({ ...nb, name_ar: e.target.value })} /></Field>
          <Field label={t("slug")}><Input dir="ltr" value={nb.slug} onChange={(e) => setNb({ ...nb, slug: e.target.value.toLowerCase() })} /></Field>
          <Field label={t("plan")}><Select value={nb.plan} onChange={(e) => setNb({ ...nb, plan: e.target.value })}>{["free", "basic", "pro", "enterprise"].map((p) => <option key={p}>{p}</option>)}</Select></Field>
        </div>
      </Modal>
      {open && <BusinessAdmin biz={open} onClose={() => setOpen(null)} />}
    </>
  );
}

function BusinessAdmin({ biz, onClose }: { biz: PBiz; onClose: () => void }) {
  const { t } = useSession();
  const qc = useQueryClient();
  const { toast, confirm } = useUi();
  const usage = useQuery({ queryKey: ["platform", "usage", biz.id], queryFn: () => get<{ entitlements: Record<string, unknown>; usage: Record<string, number> }>(`/platform/businesses/${biz.id}/usage`) });
  const subs = useQuery({ queryKey: ["platform", "subs", biz.id], queryFn: () => get<{ id: string; plan: string; status: string; current_period_end: string | null }[]>(`/platform/businesses/${biz.id}/subscriptions`) });
  const features = useQuery({ queryKey: ["platform", "features"], queryFn: () => get<Feature[]>("/platform/features") });
  const [plan, setPlan] = useState("basic");
  const [months, setMonths] = useState("1");
  const [pay, setPay] = useState({ amount: "", method: "cash", months: "1", reference: "" });
  const [ov, setOv] = useState({ feature: "max_products", value: "" });
  const refresh = () => qc.invalidateQueries({ queryKey: ["platform"] });
  const onErr = (e: unknown) => toast(errorMessage(e, t("error")), "error");
  const status = useMutation({ mutationFn: async () => {
    if (biz.status === "active") {
      const reason = await confirm({ title: t("suspend"), danger: true, input: t("reason") });
      if (!reason) return;
      return post(`/platform/businesses/${biz.id}/suspend`, { reason });
    }
    return post(`/platform/businesses/${biz.id}/activate`);
  }, onSuccess: () => { refresh(); onClose(); }, onError: onErr });
  const assign = useMutation({ mutationFn: () => post(`/platform/businesses/${biz.id}/subscriptions`, { plan, months: Number(months) }), onSuccess: () => { toast(t("saved")); refresh(); }, onError: onErr });
  const live = subs.data?.find((s) => ["active", "trialing", "past_due"].includes(s.status));
  const record = useMutation({ mutationFn: () => post(`/platform/subscriptions/${live!.id}/payments`, { amount: Number(pay.amount), currency: "IQD", method: pay.method, months: Number(pay.months), reference: pay.reference, paid_at: new Date().toISOString() }),
    onSuccess: () => { toast(t("saved")); refresh(); }, onError: onErr });
  const feature = features.data?.find((x) => x.key === ov.feature);
  const override = useMutation({ mutationFn: () => put(`/platform/businesses/${biz.id}/overrides`, { feature: ov.feature,
    value: ov.value === "" ? null : feature?.value_type === "bool" ? ov.value === "true" : Number(ov.value), reason: "platform console" }),
  onSuccess: () => { toast(t("saved")); refresh(); }, onError: onErr });
  const clearOv = useMutation({ mutationFn: (k: string) => del(`/platform/businesses/${biz.id}/overrides/${k}`), onSuccess: refresh });
  return (
    <Modal wide open onClose={onClose} title={biz.name_ar} footer={
      <Button variant={biz.status === "active" ? "danger" : "primary"} onClick={() => status.mutate()}>{biz.status === "active" ? t("suspend") : t("activate")}</Button>}>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title={t("subscription")}>
          <ul className="mb-3 space-y-1 text-[13px]">{subs.data?.slice(0, 4).map((s) => <li key={s.id}>{s.plan} · <Badge>{s.status}</Badge> {s.current_period_end?.slice(0, 10)}</li>)}</ul>
          <div className="flex gap-2"><Select value={plan} onChange={(e) => setPlan(e.target.value)}>{["free", "basic", "pro", "enterprise"].map((p) => <option key={p}>{p}</option>)}</Select>
            <Input aria-label={t("months")} className="w-20" value={months} onChange={(e) => setMonths(e.target.value)} />
            <Button size="sm" onClick={() => assign.mutate()}>{t("apply")}</Button></div>
        </Card>
        <Card title={t("record_payment")}>
          {!live ? <p className="text-[13px] text-hint">—</p> : <form className="grid grid-cols-2 gap-2" onSubmit={(e) => { e.preventDefault(); record.mutate(); }}>
            <Input placeholder={t("amount")} inputMode="numeric" value={pay.amount} onChange={(e) => setPay({ ...pay, amount: e.target.value })} required />
            <Select value={pay.method} onChange={(e) => setPay({ ...pay, method: e.target.value })}>{["cash", "zaincash", "bank_transfer", "other"].map((m) => <option key={m}>{m}</option>)}</Select>
            <Input placeholder={t("months")} value={pay.months} onChange={(e) => setPay({ ...pay, months: e.target.value })} />
            <Input placeholder="ref" value={pay.reference} onChange={(e) => setPay({ ...pay, reference: e.target.value })} />
            <Button size="sm" className="col-span-2">{t("record_payment")}</Button></form>}
        </Card>
        <Card title={t("usage")} className="md:col-span-2">
          {usage.isPending ? <Loading /> : <div className="grid gap-2 text-[13px] sm:grid-cols-3">
            {Object.entries(usage.data?.entitlements ?? {}).map(([k, v]) => <div key={k} className="rounded border border-line px-2 py-1" dir="ltr">
              <b>{k}</b>: {v === null ? "∞" : String(v)}{usage.data?.usage[k] !== undefined && ` (used ${usage.data.usage[k]})`}</div>)}</div>}
          <form className="mt-3 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); override.mutate(); }}>
            <Select className="w-auto" value={ov.feature} onChange={(e) => setOv({ ...ov, feature: e.target.value })}>{features.data?.map((x) => <option key={x.key}>{x.key}</option>)}</Select>
            {feature?.value_type === "bool" ? <Select className="w-auto" value={ov.value} onChange={(e) => setOv({ ...ov, value: e.target.value })}><option value="true">true</option><option value="false">false</option></Select>
              : <Input className="w-32" placeholder="∞ = empty" value={ov.value} onChange={(e) => setOv({ ...ov, value: e.target.value })} />}
            <Button size="sm">{t("overrides")}</Button>
            <Button size="sm" type="button" variant="ghost" onClick={() => clearOv.mutate(ov.feature)}>{t("delete")}</Button>
          </form>
        </Card>
      </div>
    </Modal>
  );
}

function Plans() {
  const { t, money } = useSession();
  const qc = useQueryClient();
  const { toast } = useUi();
  const plans = useQuery({ queryKey: ["platform", "plans"], queryFn: () => get<Plan[]>("/platform/plans") });
  const features = useQuery({ queryKey: ["platform", "features"], queryFn: () => get<Feature[]>("/platform/features") });
  const [edits, setEdits] = useState<Record<string, Record<string, string>>>({});
  const save = useMutation({
    mutationFn: (p: Plan) => {
      const body: Record<string, unknown> = {};
      for (const [k, raw] of Object.entries(edits[p.id] ?? {})) {
        const f = features.data?.find((x) => x.key === k);
        body[k] = f?.value_type === "bool" ? raw === "true" : raw === "" ? null : Number(raw);
      }
      return put(`/platform/plans/${p.id}/entitlements`, body);
    },
    onSuccess: (_, p) => { setEdits({ ...edits, [p.id]: {} }); toast(t("saved")); qc.invalidateQueries({ queryKey: ["platform", "plans"] }); },
    onError: (e) => toast(errorMessage(e, t("error")), "error"),
  });
  if (plans.isPending || features.isPending) return <Loading />;
  if (plans.isError) return <ErrorBox error={plans.error} />;
  const val = (p: Plan, k: string) => edits[p.id]?.[k] ?? (p.entitlements[k] === null ? "" : String(p.entitlements[k] ?? ""));
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-card">
      <table className="w-full min-w-[720px] text-[13px]">
        <thead className="bg-bg2/60"><tr><th className="px-3 py-2 text-start">{t("features")}</th>
          {plans.data.map((p) => <th key={p.id} className="px-3 py-2 text-start">{p.name_en}<div className="font-normal text-hint">{money(p.monthly_price, p.currency)}{p.is_default && " · default"}</div></th>)}</tr></thead>
        <tbody className="divide-y divide-line">
          {features.data?.map((f) => (
            <tr key={f.key}><td className="px-3 py-1.5" dir="ltr"><b>{f.key}</b><div className="text-hint">{f.description}</div></td>
              {plans.data.map((p) => (
                <td key={p.id} className="px-3 py-1.5">
                  {f.value_type === "bool" ? (
                    <Select value={val(p, f.key)} onChange={(e) => setEdits({ ...edits, [p.id]: { ...edits[p.id], [f.key]: e.target.value } })}>
                      <option value="true">✓</option><option value="false">✕</option></Select>
                  ) : <Input placeholder="∞" inputMode="numeric" value={val(p, f.key)} onChange={(e) => setEdits({ ...edits, [p.id]: { ...edits[p.id], [f.key]: e.target.value } })} />}
                </td>))}
            </tr>))}
          <tr><td />{plans.data.map((p) => <td key={p.id} className="px-3 py-2"><Button size="sm" disabled={!Object.keys(edits[p.id] ?? {}).length} onClick={() => save.mutate(p)}>{t("save")}</Button></td>)}</tr>
        </tbody>
      </table>
    </div>
  );
}

function Stats() {
  const { t } = useSession();
  const q = useQuery({ queryKey: ["platform", "stats"], queryFn: () => get<Record<string, unknown> & { gmv_by_currency: { currency: string; gmv: number }[] }>("/platform/stats") });
  if (q.isPending) return <Loading />;
  if (q.isError) return <ErrorBox error={q.error} />;
  const d = q.data;
  const keys = ["businesses_total", "businesses_active", "businesses_suspended", "new_businesses", "orders", "delivered_orders", "ai_messages", "open_support_tickets"];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{keys.map((k) => <StatCard key={k} label={k.replaceAll("_", " ")} value={String(d[k])} />)}</div>
      <Card title="GMV (30d)"><ul className="text-[14px]">{d.gmv_by_currency.map((g) => <li key={g.currency} className="tabular">{g.currency}: {g.gmv.toLocaleString("en")}</li>)}</ul>
        {!d.gmv_by_currency.length && <p className="text-hint">{t("no_data")}</p>}</Card>
    </div>
  );
}

function Health() {
  const q = useQuery({ queryKey: ["platform", "health"], refetchInterval: 15000, queryFn: () => get<{ components: Record<string, string>; outbox_pending: number; outbox_failed_24h: number;
    bots: { username: string; webhook_status: string; last_error: string }[]; bot_service_heartbeat: number | null; worker_heartbeat: number | null }>("/platform/health") });
  if (q.isPending) return <Loading />;
  if (q.isError) return <ErrorBox error={q.error} />;
  const d = q.data;
  const age = (ts: number | null) => (ts ? `${Math.round(Date.now() / 1000 - ts)}s ago` : "never");
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card title="Components"><ul className="space-y-1 text-[14px]">
        {Object.entries(d.components).map(([k, v]) => <li key={k}>{k}: <Badge tone={v === "ok" ? "success" : "danger"}>{v}</Badge></li>)}
        <li>bot service: <Badge tone={d.bot_service_heartbeat ? "success" : "warn"}>{age(d.bot_service_heartbeat)}</Badge></li>
        <li>celery worker: <Badge tone={d.worker_heartbeat ? "success" : "warn"}>{age(d.worker_heartbeat)}</Badge></li>
        <li>outbox pending: <b className="tabular">{d.outbox_pending}</b> · failed 24h: <b className="tabular">{d.outbox_failed_24h}</b></li></ul></Card>
      <Card title="Bots"><ul className="space-y-1 text-[13px]" dir="ltr">{d.bots.map((b) => <li key={b.username}>@{b.username} <Badge tone={b.webhook_status === "error" ? "danger" : "success"}>{b.webhook_status}</Badge> {b.last_error}</li>)}</ul></Card>
    </div>
  );
}

function Tickets() {
  const { t } = useSession();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["platform", "tickets"], queryFn: () => get<Paginated<{ id: string; subject: string; status: string; business_name: string;
    messages: { id: string; body: string; is_from_platform: boolean; author_name: string }[] }>>("/platform/support-tickets") });
  const [reply, setReply] = useState<Record<string, string>>({});
  const send = useMutation({ mutationFn: (id: string) => post(`/platform/support-tickets/${id}/messages`, { body: reply[id] }),
    onSuccess: (_, id) => { setReply({ ...reply, [id]: "" }); qc.invalidateQueries({ queryKey: ["platform", "tickets"] }); } });
  if (q.isPending) return <Loading />;
  if (q.isError) return <ErrorBox error={q.error} />;
  return (
    <div className="space-y-3">{q.data.results.map((tk) => (
      <Card key={tk.id} title={`${tk.business_name} — ${tk.subject}`} actions={<Badge>{tk.status}</Badge>}>
        {tk.messages.map((m) => <p key={m.id} className={cx("mb-2 rounded p-2 text-[14px]", m.is_from_platform ? "bg-info/8" : "bg-bg2")}><span className="text-[12px] text-hint">{m.author_name}: </span>{m.body}</p>)}
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (reply[tk.id]) send.mutate(tk.id); }}>
          <Input value={reply[tk.id] ?? ""} onChange={(e) => setReply({ ...reply, [tk.id]: e.target.value })} /><Button size="sm">{t("send")}</Button></form>
      </Card>))}
      {!q.data.results.length && <p className="text-center text-hint">{t("no_data")}</p>}
    </div>
  );
}
