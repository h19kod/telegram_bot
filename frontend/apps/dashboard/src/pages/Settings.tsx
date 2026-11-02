import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { PageHeader } from "../components/Shell";
import { Badge, Button, Card, Empty, ErrorBox, errorMessage, Field, Input, Loading, Select, Table,
  TextArea, Toggle, useUi } from "../components/ui";
import { ApiError, del, download, get, patch, post, put, upload, type Branch, type Business,
  type Settings, type SubscriptionOverview, type SupportTicket, type TelegramOverview } from "../lib/api";
import { useBizKey, useBizPath, useSession } from "../lib/session";
import { rangeFor, SalesChart, TopProducts } from "./Overview";

export function SettingsPage() {
  const { t } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { toast } = useUi();
  const biz = useQuery({ queryKey: key("business"), queryFn: () => get<Business>(path("")) });
  const cfg = useQuery({ queryKey: key("settings"), queryFn: () => get<Settings>(path("/settings")) });
  const branches = useQuery({ queryKey: key("branches"), queryFn: () => get<Branch[]>(path("/branches")) });
  const [b, setB] = useState<Business | null>(null);
  const [s, setS] = useState<Settings | null>(null);
  const [errs, setErrs] = useState<Record<string, string>>({});
  useEffect(() => { if (biz.data) setB(biz.data); }, [biz.data]);
  useEffect(() => { if (cfg.data) setS(cfg.data); }, [cfg.data]);
  const onErr = (e: unknown) => { if (e instanceof ApiError) setErrs(e.fieldErrors()); toast(errorMessage(e, t("error")), "error"); };
  const saveBiz = useMutation({ mutationFn: () => patch(path(""), { name_ar: b!.name_ar, name_en: b!.name_en,
    description_ar: b!.description_ar, description_en: b!.description_en, phone: b!.phone, whatsapp: b!.whatsapp,
    business_type: b!.business_type, default_language: b!.default_language }),
  onSuccess: () => { toast(t("saved")); setErrs({}); qc.invalidateQueries({ queryKey: key("business") }); qc.invalidateQueries({ queryKey: ["memberships"] }); }, onError: onErr });
  const saveCfg = useMutation({ mutationFn: () => patch(path("/settings"), s), onSuccess: () => { toast(t("saved")); setErrs({}); qc.invalidateQueries({ queryKey: key("settings") }); }, onError: onErr });
  const img = useMutation({ mutationFn: (v: { kind: "logo" | "cover"; file: File }) => { const fd = new FormData(); fd.append("image", v.file); return upload(path(`/images/${v.kind}`), fd); },
    onSuccess: () => qc.invalidateQueries({ queryKey: key("business") }), onError: onErr });
  if (biz.isPending || cfg.isPending || !b || !s) return <Loading />;
  if (biz.isError) return <ErrorBox error={biz.error} />;
  const pm = (m: Settings["payment_methods"][number], on: boolean) => setS({ ...s, payment_methods: on ? [...new Set([...s.payment_methods, m])] : s.payment_methods.filter((x) => x !== m) });
  return (
    <>
      <PageHeader title={t("settings")} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title={t("settings")} actions={<Button size="sm" disabled={saveBiz.isPending} onClick={() => saveBiz.mutate()}>{t("save")}</Button>}>
          <div className="grid gap-3 sm:grid-cols-2">
            {(["logo", "cover"] as const).map((k) => (
              <Field key={k} label={t(k)}><div className="flex items-center gap-3">
                {b[k] ? <img src={b[k]!} alt="" className="size-14 rounded-lg object-cover" /> : <div className="grid size-14 place-items-center rounded-lg bg-bg2">🖼</div>}
                <input type="file" accept="image/*" className="text-[13px]" onChange={(e) => { const f = e.target.files?.[0]; if (f) img.mutate({ kind: k, file: f }); }} />
              </div></Field>
            ))}
            <Field label={t("name_ar")}><Input value={b.name_ar} onChange={(e) => setB({ ...b, name_ar: e.target.value })} /></Field>
            <Field label={t("name_en")}><Input dir="ltr" value={b.name_en} onChange={(e) => setB({ ...b, name_en: e.target.value })} /></Field>
            <Field label={t("description_ar")} className="sm:col-span-2"><TextArea value={b.description_ar} onChange={(e) => setB({ ...b, description_ar: e.target.value })} /></Field>
            <Field label={t("description_en")} className="sm:col-span-2"><TextArea dir="ltr" value={b.description_en} onChange={(e) => setB({ ...b, description_en: e.target.value })} /></Field>
            <Field label={t("phone")} error={errs.phone}><Input dir="ltr" value={b.phone} onChange={(e) => setB({ ...b, phone: e.target.value })} /></Field>
            <Field label={t("whatsapp")} error={errs.whatsapp}><Input dir="ltr" value={b.whatsapp} onChange={(e) => setB({ ...b, whatsapp: e.target.value })} /></Field>
            <Field label={t("language")}><Select value={b.default_language} onChange={(e) => setB({ ...b, default_language: e.target.value as Business["default_language"] })}><option value="ar">العربية</option><option value="en">English</option></Select></Field>
          </div>
        </Card>
        <Card title={t("ordering_rules")} actions={<Button size="sm" disabled={saveCfg.isPending} onClick={() => saveCfg.mutate()}>{t("save")}</Button>}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("min_order")} error={errs.min_order_amount}><Input inputMode="numeric" value={s.min_order_amount} onChange={(e) => setS({ ...s, min_order_amount: Number(e.target.value) || 0 })} /></Field>
            <Field label={t("cancel_window")} error={errs.customer_cancel_window_min}><Input inputMode="numeric" value={s.customer_cancel_window_min} onChange={(e) => setS({ ...s, customer_cancel_window_min: Number(e.target.value) || 0 })} /></Field>
            <Field label={t("auto_reject")} error={errs.auto_reject_after_min}><Input inputMode="numeric" value={s.auto_reject_after_min ?? ""} onChange={(e) => setS({ ...s, auto_reject_after_min: e.target.value ? Number(e.target.value) : null })} /></Field>
            <div className="flex items-end"><Toggle checked={s.allow_order_notes} onChange={(v) => setS({ ...s, allow_order_notes: v })} label={t("allow_notes")} /></div>
            <Field label={t("payment_methods")} error={errs.payment_methods} className="sm:col-span-2"><div className="flex gap-4">
              <Toggle checked={s.payment_methods.includes("cash_on_delivery")} onChange={(v) => pm("cash_on_delivery", v)} label={t("cod")} />
              <Toggle checked={s.payment_methods.includes("pay_at_pickup")} onChange={(v) => pm("pay_at_pickup", v)} label={t("pay_pickup")} /></div></Field>
            <Field label={t("welcome_ar")} className="sm:col-span-2"><TextArea value={s.welcome_message_ar} onChange={(e) => setS({ ...s, welcome_message_ar: e.target.value })} /></Field>
            <Field label={t("welcome_en")} className="sm:col-span-2"><TextArea dir="ltr" value={s.welcome_message_en} onChange={(e) => setS({ ...s, welcome_message_en: e.target.value })} /></Field>
          </div>
        </Card>
        {branches.data?.map((br) => <BranchCard key={br.id} branch={br} />)}
      </div>
    </>
  );
}

function BranchCard({ branch }: { branch: Branch }) {
  const { t } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { toast } = useUi();
  const [hours, setHours] = useState(branch.hours.map((h) => ({ ...h, opens_at: h.opens_at.slice(0, 5), closes_at: h.closes_at.slice(0, 5) })));
  const days = t("weekdays").split(",");
  const refresh = () => qc.invalidateQueries({ queryKey: key("branches") });
  const flag = useMutation({ mutationFn: (body: Partial<Branch>) => patch(path(`/branches/${branch.id}`), body), onSuccess: refresh });
  const saveHours = useMutation({ mutationFn: () => put(path(`/branches/${branch.id}/hours`), hours), onSuccess: () => { toast(t("saved")); refresh(); },
    onError: (e) => toast(errorMessage(e, t("error")), "error") });
  return (
    <Card title={<span>{branch.name_ar} <Badge tone={branch.is_open_now ? "success" : "danger"}>{branch.is_open_now ? t("open_now") : t("closed_now")}</Badge></span>}
      actions={<Button size="sm" disabled={saveHours.isPending} onClick={() => saveHours.mutate()}>{t("save")}</Button>}>
      <div className="mb-4 flex flex-wrap gap-4">
        <Toggle checked={branch.is_temporarily_closed} onChange={(v) => flag.mutate({ is_temporarily_closed: v })} label={t("temporarily_closed")} />
        <Toggle checked={branch.accepts_delivery} onChange={(v) => flag.mutate({ accepts_delivery: v })} label={t("accepts_delivery")} />
        <Toggle checked={branch.accepts_pickup} onChange={(v) => flag.mutate({ accepts_pickup: v })} label={t("accepts_pickup")} />
      </div>
      <p className="mb-2 text-[13px] font-semibold">{t("working_hours")}</p>
      {!hours.length && <p className="mb-2 text-[13px] text-hint">24/7</p>}
      <div className="space-y-2">
        {hours.map((h, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <Select aria-label="day" className="w-32" value={h.weekday} onChange={(e) => setHours(hours.map((x, j) => j === i ? { ...x, weekday: Number(e.target.value) } : x))}>
              {days.map((d, di) => <option key={di} value={di}>{d}</option>)}</Select>
            <Input type="time" className="w-32" value={h.opens_at} onChange={(e) => setHours(hours.map((x, j) => j === i ? { ...x, opens_at: e.target.value } : x))} />
            <span>–</span>
            <Input type="time" className="w-32" value={h.closes_at} onChange={(e) => setHours(hours.map((x, j) => j === i ? { ...x, closes_at: e.target.value } : x))} />
            <Button size="sm" variant="ghost" aria-label={t("delete")} onClick={() => setHours(hours.filter((_, j) => j !== i))}>✕</Button>
          </div>
        ))}
      </div>
      <Button size="sm" variant="secondary" className="mt-3" onClick={() => setHours([...hours, { weekday: 0, opens_at: "12:00", closes_at: "23:00" }])}>+ {t("add_interval")}</Button>
    </Card>
  );
}

type TgStatus = TelegramOverview;

export function TelegramPage() {
  const { t } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { toast, confirm } = useUi();
  const q = useQuery({ queryKey: key("telegram"), queryFn: () => get<TgStatus>(path("/telegram")) });
  const cfg = useQuery({ queryKey: key("settings"), queryFn: () => get<Settings>(path("/settings")) });
  const [token, setToken] = useState("");
  const [chats, setChats] = useState("");
  useEffect(() => { if (cfg.data) setChats(cfg.data.notification_chat_ids.join(", ")); }, [cfg.data]);
  const onErr = (e: unknown) => toast(errorMessage(e, t("error")), "error");
  const connect = useMutation({ mutationFn: () => put(path("/telegram"), { bot_token: token.trim() }), onSuccess: () => { setToken(""); toast(t("bot_connected")); qc.invalidateQueries({ queryKey: key("telegram") }); }, onError: onErr });
  const disconnect = useMutation({ mutationFn: () => del(path("/telegram")), onSuccess: () => qc.invalidateQueries({ queryKey: key("telegram") }), onError: onErr });
  const test = useMutation({ mutationFn: () => post<{ sent_to: number }>(path("/telegram/test-notification")), onSuccess: (r) => toast(`✓ ${r.sent_to}`), onError: onErr });
  const saveChats = useMutation({ mutationFn: () => patch(path("/settings"), { notification_chat_ids: chats.split(/[,\s]+/).filter(Boolean).map(Number) }),
    onSuccess: () => { toast(t("saved")); qc.invalidateQueries({ queryKey: key("settings") }); }, onError: onErr });
  if (q.isPending) return <Loading />;
  if (q.isError) return <ErrorBox error={q.error} />;
  const st = q.data;
  return (
    <>
      <PageHeader title={t("telegram")} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title={st.has_own_bot ? t("bot_connected") : t("connect")}>
          {st.bot ? (
            <div className="space-y-3 text-[14px]">
              <p className="text-[18px] font-semibold" dir="ltr">@{st.bot.username}</p>
              <p>{t("webhook_status")}: <Badge tone={st.bot.webhook_status === "error" ? "danger" : "success"}>{st.bot.webhook_status}</Badge></p>
              {st.bot.last_error && <p className="text-danger">{st.bot.last_error}</p>}
              <Button variant="danger" onClick={async () => { if (await confirm({ title: t("disconnect"), danger: true })) disconnect.mutate(); }}>{t("disconnect")}</Button>
            </div>
          ) : (
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); connect.mutate(); }}>
              {st.shared_bot_username && <p className="text-[14px] text-hint">{t("shared_bot")} (@{st.shared_bot_username})</p>}
              <Field label={t("bot_token")} hint={t("token_hint")}><Input type="password" autoComplete="off" dir="ltr" value={token} onChange={(e) => setToken(e.target.value)} placeholder="123456789:AA..." /></Field>
              <Button disabled={!token || connect.isPending}>{t("connect")}</Button>
            </form>
          )}
          {st.deep_link && <Field label={t("store_link")} className="mt-4"><Input readOnly dir="ltr" value={st.deep_link} onFocus={(e) => e.target.select()} /></Field>}
        </Card>
        <Card title={t("notification_chats")} actions={<Button size="sm" variant="secondary" disabled={test.isPending} onClick={() => test.mutate()}>{t("test_notification")}</Button>}>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); saveChats.mutate(); }}>
            <Input dir="ltr" value={chats} onChange={(e) => setChats(e.target.value)} placeholder="-1001234567890" />
            <Button>{t("save")}</Button>
          </form>
        </Card>
      </div>
    </>
  );
}

type SubInfo = SubscriptionOverview;

export function SubscriptionPage() {
  const { t, money, lang } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const q = useQuery({ queryKey: key("subscription"), queryFn: () => get<SubInfo>(path("/subscription")) });
  if (q.isPending) return <Loading />;
  if (q.isError) return <ErrorBox error={q.error} />;
  const d = q.data;
  const limits = Object.entries(d.entitlements).filter(([k]) => k.startsWith("max_"));
  return (
    <>
      <PageHeader title={t("subscription")} />
      <div className="space-y-4">
        <Card title={`${t("plan")}: ${d.subscription?.plan ?? "—"}`} actions={d.subscription && <Badge tone="info">{d.subscription.status}</Badge>}>
          {d.subscription?.current_period_end && <p className="mb-3 text-[14px] text-hint">{t("renews")}: {new Date(d.subscription.current_period_end).toLocaleDateString(lang === "ar" ? "ar-IQ" : "en-GB", { numberingSystem: "latn" })}</p>}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {limits.map(([k, v]) => {
              const used = d.usage[k] ?? 0;
              const pct = v === null ? 0 : Math.min(100, (used / Math.max(1, Number(v))) * 100);
              return (
                <div key={k} className="rounded-lg border border-line p-3">
                  <p className="text-[12px] text-hint" dir="ltr">{k.replace("max_", "").replaceAll("_", " ")}</p>
                  <p className="tabular font-semibold">{used} / {v === null ? t("unlimited") : String(v)}</p>
                  {v !== null && <div className="mt-2 h-1.5 rounded-full bg-bg2"><div className={pct > 85 ? "h-1.5 rounded-full bg-warn" : "h-1.5 rounded-full bg-accent"} style={{ width: `${pct}%` }} /></div>}
                </div>
              );
            })}
          </div>
        </Card>
        <Card title={t("plans")}>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {d.plans.map((p) => (
              <div key={p.code} className={p.code === d.subscription?.plan ? "rounded-lg border-2 border-accent p-4" : "rounded-lg border border-line p-4"}>
                <p className="font-bold">{lang === "en" ? p.name_en : p.name_ar}</p>
                <p className="tabular mt-1 text-[20px] font-bold">{money(p.monthly_price, p.currency)}<span className="text-[12px] font-normal text-hint">{t("per_month")}</span></p>
                <ul className="mt-3 space-y-1 text-[13px] text-hint">
                  {Object.entries(p.entitlements).map(([k, v]) => <li key={k} dir="ltr">{typeof v === "boolean" ? (v ? "✓" : "✕") : v === null ? "∞" : String(v)} {k.replace("max_", "").replaceAll("_", " ")}</li>)}
                </ul>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[13px] text-hint">{t("upgrade_hint")}</p>
        </Card>
      </div>
    </>
  );
}

export function ReportsPage() {
  const { t, can } = useSession();
  const path = useBizPath();
  const key = useBizKey();
  const biz = useQuery({ queryKey: key("business"), queryFn: () => get<Business>(path("")) });
  const [days, setDays] = useState(30);
  const r = rangeFor(days);
  const cur = biz.data?.currency ?? "IQD";
  const exportQs = `?placed_after=${r.from}T00:00:00%2B03:00&placed_before=${r.to}T23:59:59%2B03:00`;
  return (
    <>
      <PageHeader title={t("reports")} actions={<>
        <Select aria-label="range" className="w-auto" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>{t("last_7")}</option><option value={30}>{t("last_30")}</option><option value={90}>{t("last_90")}</option></Select>
        {can("reports.export") && <>
          <Button variant="secondary" size="sm" onClick={() => download(path(`/orders/export${exportQs}&format_type=csv`), "orders.csv")}>{t("export_csv")}</Button>
          <Button variant="secondary" size="sm" onClick={() => download(path(`/orders/export${exportQs}&format_type=xlsx`), "orders.xlsx")}>{t("export_xlsx")}</Button></>}
      </>} />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2"><SalesChart days={days} currency={cur} /></div>
        <TopProducts days={days} currency={cur} />
      </div>
    </>
  );
}

export function AccountPage() {
  const { t, user, reload } = useSession();
  const { toast } = useUi();
  const [pw, setPw] = useState({ old_password: "", new_password: "" });
  const [uri, setUri] = useState<string | null>(null);
  const [otp, setOtp] = useState("");
  const [code, setCode] = useState<string | null>(null);
  const onErr = (e: unknown) => toast(errorMessage(e, t("error")), "error");
  const change = useMutation({ mutationFn: () => post("/auth/password/change", pw), onSuccess: () => { toast(t("password_changed")); setPw({ old_password: "", new_password: "" }); }, onError: onErr });
  const setup = useMutation({ mutationFn: () => post<{ provisioning_uri: string }>("/auth/2fa/setup"), onSuccess: (r) => setUri(r.provisioning_uri), onError: onErr });
  const enable = useMutation({ mutationFn: () => post(user?.totp_enabled ? "/auth/2fa/disable" : "/auth/2fa/enable", { otp }), onSuccess: () => { setUri(null); setOtp(""); reload(); toast(t("saved")); }, onError: onErr });
  const link = useMutation({ mutationFn: () => post<{ code: string }>("/auth/telegram/link-code"), onSuccess: (r) => setCode(r.code), onError: onErr });
  return (
    <>
      <PageHeader title={t("account")} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title={t("change_password")}>
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); change.mutate(); }}>
            <Field label={t("old_password")}><Input type="password" autoComplete="current-password" value={pw.old_password} onChange={(e) => setPw({ ...pw, old_password: e.target.value })} /></Field>
            <Field label={t("new_password")}><Input type="password" autoComplete="new-password" minLength={10} value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></Field>
            <Button disabled={change.isPending}>{t("save")}</Button>
          </form>
        </Card>
        <Card title={t("two_factor")} actions={<Badge tone={user?.totp_enabled ? "success" : "neutral"}>{user?.totp_enabled ? "ON" : "OFF"}</Badge>}>
          {!user?.totp_enabled && !uri && <Button variant="secondary" onClick={() => setup.mutate()}>{t("enable")}</Button>}
          {(uri || user?.totp_enabled) && (
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); enable.mutate(); }}>
              {uri && <Field label={t("scan_qr")}><Input readOnly dir="ltr" value={uri} onFocus={(e) => e.target.select()} /></Field>}
              <Field label={t("otp")}><Input inputMode="numeric" dir="ltr" value={otp} onChange={(e) => setOtp(e.target.value)} autoComplete="one-time-code" /></Field>
              <Button disabled={otp.length < 6}>{user?.totp_enabled ? t("disable") : t("enable")}</Button>
            </form>
          )}
        </Card>
        <Card title={t("link_telegram")} actions={user?.has_telegram && <Badge tone="info">✈️ {t("telegram_linked")}</Badge>}>
          {code ? <p className="text-[14px]">{t("link_code_hint")} <code className="rounded bg-bg2 px-2 py-1 font-bold" dir="ltr">/link {code}</code></p>
            : <Button variant="secondary" onClick={() => link.mutate()}>{t("generate_code")}</Button>}
        </Card>
      </div>
    </>
  );
}

type Ticket = SupportTicket;

export function SupportPage() {
  const { t } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { toast } = useUi();
  const q = useQuery({ queryKey: key("tickets"), queryFn: () => get<{ results: Ticket[] }>(path("/support-tickets")) });
  const [f, setF] = useState({ subject: "", body: "" });
  const [reply, setReply] = useState<Record<string, string>>({});
  const refresh = () => qc.invalidateQueries({ queryKey: key("tickets") });
  const create = useMutation({ mutationFn: () => post(path("/support-tickets"), f), onSuccess: () => { setF({ subject: "", body: "" }); refresh(); }, onError: (e) => toast(errorMessage(e, t("error")), "error") });
  const send = useMutation({ mutationFn: (id: string) => post(path(`/support-tickets/${id}/messages`), { body: reply[id] }), onSuccess: (_, id) => { setReply({ ...reply, [id]: "" }); refresh(); } });
  return (
    <>
      <PageHeader title={t("support")} />
      <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <div className="space-y-3">
          {q.isPending ? <Loading /> : !q.data?.results.length ? <Empty>{t("no_data")}</Empty> : q.data.results.map((tk) => (
            <Card key={tk.id} title={tk.subject} actions={<Badge>{tk.status}</Badge>}>
              <div className="space-y-2">{tk.messages.map((m) => (
                <div key={m.id} className={m.is_from_platform ? "rounded-lg bg-info/8 p-3 text-[14px]" : "rounded-lg bg-bg2 p-3 text-[14px]"}>
                  <p className="text-[12px] text-hint">{m.author_name}</p><p className="whitespace-pre-line">{m.body}</p></div>))}</div>
              <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (reply[tk.id]) send.mutate(tk.id); }}>
                <Input value={reply[tk.id] ?? ""} onChange={(e) => setReply({ ...reply, [tk.id]: e.target.value })} /><Button size="sm">{t("send")}</Button></form>
            </Card>))}
        </div>
        <Card title={t("new_ticket")}>
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
            <Field label={t("subject")}><Input required value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} /></Field>
            <Field label={t("message")}><TextArea required value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} /></Field>
            <Button disabled={create.isPending}>{t("send")}</Button>
          </form>
        </Card>
      </div>
    </>
  );
}

export function AuditPage() {
  const { t, lang } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const q = useQuery({ queryKey: key("audit"), queryFn: () => get<{ id: string; actor: string; action: string; target_type: string; changes: object; created_at: string; ip: string }[]>(path("/audit-log")) });
  return (
    <>
      <PageHeader title={t("audit")} />
      {q.isPending ? <Loading /> : q.isError ? <ErrorBox error={q.error} /> : (
        <Table empty={!q.data.length} head={[t("time"), "", "", ""]}>
          {q.data.map((e) => (
            <tr key={e.id} className="align-top">
              <td className="tabular px-4 py-2 text-[13px] whitespace-nowrap text-hint">{new Date(e.created_at).toLocaleString(lang === "ar" ? "ar-IQ" : "en-GB", { numberingSystem: "latn" })}</td>
              <td className="px-4 py-2">{e.actor}</td><td className="px-4 py-2"><code dir="ltr">{e.action}</code></td>
              <td className="max-w-md truncate px-4 py-2 text-[12px] text-hint" dir="ltr">{JSON.stringify(e.changes)}</td>
            </tr>))}
        </Table>
      )}
    </>
  );
}
