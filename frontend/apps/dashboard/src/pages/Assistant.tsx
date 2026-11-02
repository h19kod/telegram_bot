import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { PageHeader } from "../components/Shell";
import { Badge, Button, Card, cx, Empty, ErrorBox, errorMessage, Field, Input, Loading, Pager,
  Select, StatCard, TextArea, Toggle, useUi } from "../components/ui";
import { del, get, patch, post, put, qs, type AIStatus, type Conversation, type Knowledge,
  type Paginated, type PlaygroundReply, type Settings } from "../lib/api";
import type { TKey } from "../lib/i18n";
import { useBizKey, useBizPath, useSession } from "../lib/session";

type Tab = "setup" | "knowledge" | "conversations" | "playground";

/** AI ordering assistant: switch, persona, knowledge base, conversations (staff take over and
 * reply) and a private playground to try it before customers do. */
export function AssistantPage() {
  const { t } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const status = useQuery({ queryKey: key("ai-status"), queryFn: () => get<AIStatus>(path("/ai/status")) });
  const [tab, setTab] = useState<Tab>("setup");
  if (status.isPending) return <Loading />;
  if (status.isError) return <ErrorBox error={status.error} />;
  const s = status.data;
  const tabs: [Tab, TKey][] = [["setup", "ai_setup"], ["knowledge", "ai_knowledge"],
    ["conversations", "ai_conversations"], ["playground", "ai_playground"]];
  return (
    <>
      <PageHeader title={`🤖 ${t("ai_assistant")}`} />
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <StatCard label={t("status")} value={!s.entitled ? <Badge tone="warn">{t("ai_not_in_plan")}</Badge>
          : !s.configured ? <Badge tone="danger">{t("ai_no_key")}</Badge>
          : s.enabled ? <Badge tone="success">{t("ai_on")}</Badge> : <Badge>{t("ai_off")}</Badge>}
          hint={`${s.provider} · ${s.model}`} />
        <StatCard label={t("ai_usage")} value={<span className="tabular">{s.messages_used}{s.messages_limit !== null ? ` / ${s.messages_limit}` : ""}</span>} hint={t("ai_this_month")} />
        <StatCard label={t("ai_waiting")} value={<span className="tabular">{s.handed_over}</span>} hint={t("ai_waiting_hint")} />
      </div>
      {!s.configured && <p role="status" className="mb-4 rounded-lg bg-danger/10 p-3 text-[14px] text-danger">⚠️ {t("ai_no_key_help")} <code dir="ltr">AI_API_KEY</code></p>}
      {!s.entitled && <p role="status" className="mb-4 rounded-lg bg-warn/10 p-3 text-[14px]">{t("ai_not_in_plan_help")}</p>}
      <div role="tablist" className="mb-4 flex flex-wrap gap-1 border-b border-line">
        {tabs.map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
            className={cx("-mb-px border-b-2 px-3 py-2 text-[14px] font-medium",
              tab === id ? "border-accent text-accent" : "border-transparent text-hint hover:text-fg")}>
            {t(label)}{id === "conversations" && s.handed_over > 0 ? ` (${s.handed_over})` : ""}</button>
        ))}
      </div>
      {tab === "setup" && <SetupTab status={s} />}
      {tab === "knowledge" && <KnowledgeTab />}
      {tab === "conversations" && <ConversationsTab />}
      {tab === "playground" && <PlaygroundTab status={s} />}
    </>
  );
}

function SetupTab({ status }: { status: AIStatus }) {
  const { t } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { toast } = useUi();
  const cfg = useQuery({ queryKey: key("settings"), queryFn: () => get<Settings>(path("/settings")) });
  const [persona, setPersona] = useState("");
  useEffect(() => { if (cfg.data) setPersona(cfg.data.ai_persona_note); }, [cfg.data]);
  const save = useMutation({
    mutationFn: (body: Partial<Settings>) => patch<Settings>(path("/settings"), body),
    onSuccess: () => { toast(t("saved")); qc.invalidateQueries({ queryKey: key("settings") }); qc.invalidateQueries({ queryKey: key("ai-status") }); },
    onError: (e) => toast(errorMessage(e, t("error")), "error"),
  });
  if (cfg.isPending) return <Loading />;
  if (cfg.isError) return <ErrorBox error={cfg.error} />;
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title={t("ai_setup")}>
        <div className="space-y-4">
          <Toggle checked={cfg.data.ai_enabled} disabled={!status.entitled || save.isPending}
            onChange={(v) => save.mutate({ ai_enabled: v })} label={t("ai_enable_for_customers")} />
          <p className="text-[13px] text-hint">{t("ai_how")}</p>
          <Field label={t("ai_persona")} hint={t("ai_persona_hint")}>
            <TextArea maxLength={1000} value={persona} onChange={(e) => setPersona(e.target.value)} />
          </Field>
          <Button disabled={save.isPending} onClick={() => save.mutate({ ai_persona_note: persona })}>{t("save")}</Button>
        </div>
      </Card>
      <Card title={t("ai_safety")}>
        <ul className="list-disc space-y-2 ps-5 text-[14px] text-hint">
          <li>{t("ai_safety_prices")}</li><li>{t("ai_safety_confirm")}</li>
          <li>{t("ai_safety_human")}</li><li>{t("ai_safety_fallback")}</li>
        </ul>
      </Card>
    </div>
  );
}

function KnowledgeTab() {
  const { t } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { toast, confirm } = useUi();
  const q = useQuery({ queryKey: key("knowledge"), queryFn: () => get<Knowledge[]>(path("/knowledge")) });
  const empty = { topic: "", answer_ar: "", answer_en: "" };
  const [form, setForm] = useState(empty);
  const [editId, setEditId] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: key("knowledge") });
  const onErr = (e: unknown) => toast(errorMessage(e, t("error")), "error");
  const save = useMutation({
    mutationFn: () => editId ? put(path(`/knowledge/${editId}`), { ...form, is_active: true }) : post(path("/knowledge"), form),
    onSuccess: () => { toast(t("saved")); setForm(empty); setEditId(null); refresh(); }, onError: onErr,
  });
  const toggle = useMutation({ mutationFn: (k: Knowledge) => patch(path(`/knowledge/${k.id}`), { is_active: !k.is_active }), onSuccess: refresh, onError: onErr });
  const remove = useMutation({ mutationFn: (id: string) => del(path(`/knowledge/${id}`)), onSuccess: refresh, onError: onErr });
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_1.3fr]">
      <Card title={editId ? t("edit") : t("ai_add_fact")}>
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (form.topic.trim() && form.answer_ar.trim()) save.mutate(); }}>
          <p className="text-[13px] text-hint">{t("ai_knowledge_hint")}</p>
          <Field label={t("ai_topic")}><Input maxLength={200} value={form.topic} placeholder={t("ai_topic_example")} onChange={(e) => setForm({ ...form, topic: e.target.value })} /></Field>
          <Field label={t("ai_answer_ar")}><TextArea maxLength={2000} value={form.answer_ar} onChange={(e) => setForm({ ...form, answer_ar: e.target.value })} /></Field>
          <Field label={t("ai_answer_en")}><TextArea dir="ltr" maxLength={2000} value={form.answer_en} onChange={(e) => setForm({ ...form, answer_en: e.target.value })} /></Field>
          <div className="flex gap-2">
            <Button disabled={!form.topic.trim() || !form.answer_ar.trim() || save.isPending}>{t("save")}</Button>
            {editId && <Button type="button" variant="ghost" onClick={() => { setEditId(null); setForm(empty); }}>{t("cancel")}</Button>}
          </div>
        </form>
      </Card>
      <Card title={t("ai_knowledge")}>
        {q.isPending ? <Loading /> : q.isError ? <ErrorBox error={q.error} /> : !q.data.length ? <Empty>{t("ai_no_knowledge")}</Empty> : (
          <ul className="divide-y divide-line">
            {q.data.map((k) => (
              <li key={k.id} className={cx("py-3", !k.is_active && "opacity-60")}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold">{k.topic}</p>
                  <div className="flex items-center gap-2">
                    <Toggle checked={k.is_active} onChange={() => toggle.mutate(k)} label="" />
                    <Button size="sm" variant="secondary" onClick={() => { setEditId(k.id); setForm({ topic: k.topic, answer_ar: k.answer_ar, answer_en: k.answer_en }); }}>{t("edit")}</Button>
                    <Button size="sm" variant="danger" onClick={async () => { if (await confirm({ title: t("are_you_sure"), danger: true })) remove.mutate(k.id); }}>{t("delete")}</Button>
                  </div>
                </div>
                <p className="mt-1 whitespace-pre-line text-[14px] text-hint">{k.answer_ar}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

const STATUS_TONE = { active: "info", handed_over: "warn", closed: "neutral" } as const;

function ConversationsTab() {
  const { t, lang } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const [f, setF] = useState({ status: "", page: 1 });
  const [openId, setOpenId] = useState<string | null>(null);
  const q = useQuery({ queryKey: key("ai-conversations", f), placeholderData: (p) => p,
    queryFn: () => get<Paginated<Conversation>>(path(`/ai/conversations${qs(f)}`)), refetchInterval: 15_000 });
  const when = (iso: string) => new Date(iso).toLocaleString(lang === "ar" ? "ar-IQ" : "en-GB", { numberingSystem: "latn", dateStyle: "short", timeStyle: "short" });
  return (
    <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
      <Card title={t("ai_conversations")} actions={
        <Select aria-label={t("status")} className="w-auto" value={f.status} onChange={(e) => setF({ status: e.target.value, page: 1 })}>
          <option value="">{t("all_statuses")}</option>
          {(["handed_over", "active", "closed"] as const).map((s) => <option key={s} value={s}>{t(`conv_${s}` as TKey)}</option>)}
        </Select>}>
        {q.isPending ? <Loading /> : q.isError ? <ErrorBox error={q.error} /> : !q.data.results.length ? <Empty>{t("ai_no_conversations")}</Empty> : (
          <>
            <ul className="-mx-4 divide-y divide-line">
              {q.data.results.map((c) => (
                <li key={c.id}>
                  <button type="button" onClick={() => setOpenId(c.id)}
                    className={cx("flex w-full items-center justify-between gap-2 px-4 py-2.5 text-start hover:bg-bg2", openId === c.id && "bg-bg2")}>
                    <span><span className="block font-medium">{c.customer_name || "—"}</span>
                      <span className="text-[12px] text-hint">{when(c.last_activity_at)}</span></span>
                    <Badge tone={STATUS_TONE[c.status]}>{t(`conv_${c.status}` as TKey)}</Badge>
                  </button>
                </li>
              ))}
            </ul>
            <Pager page={f.page} count={q.data.count} onPage={(page) => setF({ ...f, page })} />
          </>
        )}
      </Card>
      {openId ? <ConversationDetail id={openId} /> : <Card><Empty>{t("ai_pick_conversation")}</Empty></Card>}
    </div>
  );
}

function ConversationDetail({ id }: { id: string }) {
  const { t } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { toast } = useUi();
  const [text, setText] = useState("");
  const q = useQuery({ queryKey: key("ai-conversation", id), queryFn: () => get<Conversation>(path(`/ai/conversations/${id}`)), refetchInterval: 10_000 });
  const done = (c: Conversation) => {
    qc.setQueryData(key("ai-conversation", id), c);
    qc.invalidateQueries({ queryKey: key("ai-conversations") });
    qc.invalidateQueries({ queryKey: key("ai-status") });
  };
  const onErr = (e: unknown) => toast(errorMessage(e, t("error")), "error");
  const act = useMutation({ mutationFn: (a: "handover" | "release" | "close") => post<Conversation>(path(`/ai/conversations/${id}/${a}`)), onSuccess: done, onError: onErr });
  const reply = useMutation({ mutationFn: () => post<Conversation>(path(`/ai/conversations/${id}/reply`), { text: text.trim() }),
    onSuccess: (c) => { setText(""); done(c); }, onError: onErr });
  if (q.isPending) return <Card><Loading /></Card>;
  if (q.isError) return <Card><ErrorBox error={q.error} /></Card>;
  const c = q.data;
  return (
    <Card title={<span>{c.customer_name || "—"} <Badge tone={STATUS_TONE[c.status]}>{t(`conv_${c.status}` as TKey)}</Badge></span>}
      actions={<div className="flex gap-2">
        {c.status === "active" && <Button size="sm" variant="secondary" onClick={() => act.mutate("handover")}>{t("ai_take_over")}</Button>}
        {c.status === "handed_over" && <Button size="sm" variant="secondary" onClick={() => act.mutate("release")}>{t("ai_give_back")}</Button>}
        {c.status !== "closed" && <Button size="sm" variant="ghost" onClick={() => act.mutate("close")}>{t("ai_close")}</Button>}
      </div>}>
      <Messages messages={c.messages} />
      {c.status !== "closed" && (
        <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) reply.mutate(); }}>
          <Input aria-label={t("ai_reply_placeholder")} placeholder={t("ai_reply_placeholder")} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} />
          <Button disabled={!text.trim() || reply.isPending}>{t("send")}</Button>
        </form>
      )}
      {c.status === "active" && <p className="mt-2 text-[12px] text-hint">{t("ai_reply_hint")}</p>}
    </Card>
  );
}

function Messages({ messages }: { messages: Conversation["messages"] }) {
  const { t } = useSession();
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }); }, [messages.length]);
  return (
    <div className="max-h-[50vh] space-y-2 overflow-y-auto rounded-lg bg-bg2/60 p-3">
      {!messages.length && <p className="text-center text-[13px] text-hint">—</p>}
      {messages.map((m) => {
        const mine = m.role === "user";
        return (
          <div key={m.id} className={cx("flex", mine ? "justify-start" : "justify-end")}>
            <div className={cx("max-w-[80%] rounded-2xl px-3 py-2 text-[14px] whitespace-pre-line",
              mine ? "bg-card" : m.from_staff ? "bg-warn/15" : "bg-accent/12")}>
              <p className="mb-0.5 text-[11px] font-semibold text-hint">
                {mine ? t("customer") : m.from_staff ? `👤 ${t("ai_staff")}` : `🤖 ${t("ai_assistant")}`}</p>
              {m.content || (m.error ? <span className="text-danger">⚠️ {m.error}</span> : "…")}
              {m.from_staff && m.error && <p className="mt-1 text-[11px] text-danger">{m.error}</p>}
            </div>
          </div>
        );
      })}
      <div ref={end} />
    </div>
  );
}

function PlaygroundTab({ status }: { status: AIStatus }) {
  const { t } = useSession();
  const path = useBizPath();
  const key = useBizKey();
  const qc = useQueryClient();
  const [log, setLog] = useState<{ id: number; role: "user" | "ai" | "note"; text: string }[]>([]);
  const [text, setText] = useState("");
  const send = useMutation({
    mutationFn: (v: { text: string; reset?: boolean }) => post<PlaygroundReply>(path("/ai/playground"), v),
    onMutate: (v) => { if (v.text) setLog((l) => [...l, { id: Date.now(), role: "user", text: v.text }]); setText(""); },
    onSuccess: (r, v) => {
      qc.invalidateQueries({ queryKey: key("ai-status") });
      if (!v.text) return;
      setLog((l) => [...l, ...(r.reply ? [{ id: Date.now() + 1, role: "ai" as const, text: r.reply }] : []),
        ...(r.handed_over ? [{ id: Date.now() + 2, role: "note" as const, text: t("ai_would_hand_over") }] : []),
        ...(r.proposal_id ? [{ id: Date.now() + 3, role: "note" as const, text: t("ai_would_confirm") }] : [])]);
    },
    onError: (e) => setLog((l) => [...l, { id: Date.now(), role: "note", text: `⚠️ ${errorMessage(e, t("error"))}` }]),
  });
  const ready = status.configured && status.entitled;
  return (
    <Card title={t("ai_playground")} actions={<Button size="sm" variant="ghost" disabled={send.isPending}
      onClick={() => { setLog([]); send.mutate({ text: "", reset: true }); }}>{t("ai_new_chat")}</Button>}>
      <p className="mb-3 text-[13px] text-hint">{t("ai_playground_hint")}</p>
      <div className="max-h-[50vh] min-h-48 space-y-2 overflow-y-auto rounded-lg bg-bg2/60 p-3" aria-live="polite">
        {!log.length && <p className="text-center text-[13px] text-hint">{t("ai_try_example")}</p>}
        {log.map((m) => (
          <div key={m.id} className={cx("flex", m.role === "user" ? "justify-start" : m.role === "ai" ? "justify-end" : "justify-center")}>
            <div className={cx("max-w-[80%] whitespace-pre-line rounded-2xl px-3 py-2 text-[14px]",
              m.role === "user" ? "bg-card" : m.role === "ai" ? "bg-accent/12" : "text-[12px] text-hint")}>{m.text}</div>
          </div>
        ))}
        {send.isPending && <p className="text-end text-[13px] text-hint">🤖 …</p>}
      </div>
      <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim() && ready) send.mutate({ text: text.trim() }); }}>
        <Input aria-label={t("ai_playground")} placeholder={t("ai_try_example")} maxLength={1000} value={text}
          disabled={!ready} onChange={(e) => setText(e.target.value)} />
        <Button disabled={!ready || !text.trim() || send.isPending}>{t("send")}</Button>
      </form>
      {!ready && <p className="mt-2 text-[12px] text-danger">{status.entitled ? t("ai_no_key") : t("ai_not_in_plan")}</p>}
    </Card>
  );
}
