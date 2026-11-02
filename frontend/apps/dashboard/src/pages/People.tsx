import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader } from "../components/Shell";
import { Badge, Button, Card, ErrorBox, errorMessage, Field, Input, Loading, Modal, Pager, Select,
  Table, Toggle, useUi } from "../components/ui";
import { del, get, patch, post, qs, type Customer, type Invitation, type Member, type Paginated,
  type Role, type Zone } from "../lib/api";
import { useBizKey, useBizPath, useSession } from "../lib/session";

export function CustomersPage() {
  const { t, money, lang, can } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { confirm, toast } = useUi();
  const [f, setF] = useState({ search: "", page: 1, ordering: "-last_order_at" });
  const q = useQuery({ queryKey: key("customers", f), placeholderData: (p) => p,
    queryFn: () => get<Paginated<Customer>>(path(`/customers${qs(f)}`)) });
  const block = useMutation({
    mutationFn: async (c: Customer) => {
      if (c.is_blocked) return post(path(`/customers/${c.id}/unblock`));
      const reason = await confirm({ title: t("block"), danger: true, input: t("reason") });
      if (!reason) return null;
      return post(path(`/customers/${c.id}/block`), { reason });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: key("customers") }),
    onError: (e) => toast(errorMessage(e, t("error")), "error"),
  });
  return (
    <>
      <PageHeader title={t("customers")}>
        <div className="mt-4 flex flex-wrap gap-2">
          <Input type="search" placeholder={t("search")} className="min-w-52 flex-1" value={f.search} onChange={(e) => setF({ ...f, search: e.target.value, page: 1 })} />
          <Select aria-label="ordering" className="w-auto" value={f.ordering} onChange={(e) => setF({ ...f, ordering: e.target.value })}>
            <option value="-last_order_at">{t("last_order")}</option><option value="-orders_count">{t("orders_count")}</option>
            <option value="-total_spent">{t("total_spent")}</option></Select>
        </div>
      </PageHeader>
      {q.isPending ? <Loading /> : q.isError ? <ErrorBox error={q.error} /> : (
        <>
          <Table empty={!q.data.results.length} head={[t("customer"), t("phone"), t("orders_count"), t("total_spent"), t("last_order"), ""]}>
            {q.data.results.map((c) => (
              <tr key={c.id}>
                <td className="px-4 py-2.5"><span className="font-medium">{c.display_name || "—"}</span>
                  {c.telegram_username && <span className="ms-1 text-[12px] text-hint" dir="ltr">@{c.telegram_username}</span>}
                  {c.is_blocked && <Badge tone="danger">{t("blocked")}</Badge>}</td>
                <td className="px-4 py-2.5"><span dir="ltr">{c.phone || "—"}</span>
                  {c.phone_verified && <span className="ms-1.5 text-success" title={t("phone_verified")} aria-label={t("phone_verified")}>✓</span>}</td>
                <td className="tabular px-4 py-2.5">{c.orders_count}</td>
                <td className="tabular px-4 py-2.5">{money(c.total_spent)}</td>
                <td className="tabular px-4 py-2.5 text-[13px] text-hint">{c.last_order_at ? new Date(c.last_order_at).toLocaleDateString(lang === "ar" ? "ar-IQ" : "en-GB", { numberingSystem: "latn" }) : "—"}</td>
                <td className="px-4 py-2.5 text-end">{can("customers.block") && <Button size="sm" variant={c.is_blocked ? "secondary" : "danger"} onClick={() => block.mutate(c)}>{c.is_blocked ? t("unblock") : t("block")}</Button>}</td>
              </tr>
            ))}
          </Table>
          <Pager page={f.page} count={q.data.count} onPage={(page) => setF({ ...f, page })} />
        </>
      )}
    </>
  );
}

export function StaffPage() {
  const { t } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { toast, confirm } = useUi();
  const members = useQuery({ queryKey: key("members"), queryFn: () => get<Member[]>(path("/members")) });
  const roles = useQuery({ queryKey: key("roles"), queryFn: () => get<Role[]>(path("/roles")) });
  const invites = useQuery({ queryKey: key("invitations"), queryFn: () => get<Invitation[]>(path("/invitations")) });
  const perms = useQuery({ queryKey: key("permissions"), queryFn: () => get<{ codename: string; description: string }[]>(path("/permissions")) });
  const [inv, setInv] = useState({ email: "", role: "" });
  const [link, setLink] = useState<string | null>(null);
  const [roleEdit, setRoleEdit] = useState<Role | "new" | null>(null);
  const onErr = (e: unknown) => toast(errorMessage(e, t("error")), "error");
  const refresh = () => qc.invalidateQueries({ predicate: (q) => ["members", "roles", "invitations"].includes(q.queryKey[2] as string) });
  const invite = useMutation({ mutationFn: () => post<Invitation>(path("/invitations"), { email: inv.email, role: inv.role || roles.data?.find((r) => !r.is_owner)?.id }),
    onSuccess: (i) => { setLink(i.accept_url); setInv({ email: "", role: "" }); refresh(); }, onError: onErr });
  const changeRole = useMutation({ mutationFn: (v: { id: string; role: string }) => patch(path(`/members/${v.id}`), { role: v.role }), onSuccess: refresh, onError: onErr });
  const remove = useMutation({ mutationFn: (id: string) => del(path(`/members/${id}`)), onSuccess: refresh, onError: onErr });
  const revoke = useMutation({ mutationFn: (id: string) => del(path(`/invitations/${id}`)), onSuccess: refresh });
  if (members.isPending || roles.isPending) return <Loading />;
  if (members.isError) return <ErrorBox error={members.error} />;
  return (
    <>
      <PageHeader title={t("staff")} />
      <div className="space-y-4">
        <Card title={t("members")}>
          <div className="divide-y divide-line">
            {members.data.map((m) => (
              <div key={m.id} className="flex flex-wrap items-center gap-3 py-2.5">
                <div className="min-w-40 flex-1"><p className="font-medium">{m.full_name || m.email}</p>
                  <p className="text-[12px] text-hint" dir="ltr">{m.email ?? m.phone}</p></div>
                {m.has_telegram && <Badge tone="info">✈️ {t("telegram_linked")}</Badge>}
                <Select aria-label={t("role")} className="w-auto" value={m.role} onChange={(e) => changeRole.mutate({ id: m.id, role: e.target.value })}>
                  {roles.data?.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</Select>
                <Button size="sm" variant="danger" onClick={async () => { if (await confirm({ title: t("are_you_sure"), danger: true })) remove.mutate(m.id); }}>{t("delete")}</Button>
              </div>
            ))}
          </div>
        </Card>
        <Card title={t("invite")}>
          <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); invite.mutate(); }}>
            <Input type="email" required placeholder={t("email")} dir="ltr" className="min-w-52 flex-1" value={inv.email} onChange={(e) => setInv({ ...inv, email: e.target.value })} />
            <Select aria-label={t("role")} className="w-auto" value={inv.role} onChange={(e) => setInv({ ...inv, role: e.target.value })}>
              {roles.data?.filter((r) => !r.is_owner).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</Select>
            <Button disabled={invite.isPending}>{t("invite")}</Button>
          </form>
          {link && <Field label={t("invite_link")} className="mt-3"><Input readOnly dir="ltr" value={link} onFocus={(e) => e.target.select()} /></Field>}
          {!!invites.data?.length && <ul className="mt-3 divide-y divide-line text-[14px]">
            {invites.data.map((i) => <li key={i.id} className="flex items-center justify-between py-2"><span dir="ltr">{i.email}</span>
              <Button size="sm" variant="ghost" onClick={() => revoke.mutate(i.id)}>{t("delete")}</Button></li>)}</ul>}
        </Card>
        <Card title={t("roles")} actions={<Button size="sm" variant="secondary" onClick={() => setRoleEdit("new")}>+ {t("new_role")}</Button>}>
          <div className="divide-y divide-line">
            {roles.data?.map((r) => (
              <div key={r.id} className="flex items-center gap-3 py-2.5">
                <span className="flex-1 font-medium">{r.name} {r.is_owner && <Badge tone="warn">owner</Badge>}</span>
                <span className="text-[13px] text-hint">{r.permissions.length} {t("permissions")} · {r.members_count}</span>
                {!r.is_owner && <Button size="sm" variant="secondary" onClick={() => setRoleEdit(r)}>{t("edit")}</Button>}
              </div>
            ))}
          </div>
        </Card>
      </div>
      {roleEdit && <RoleEditor role={roleEdit === "new" ? null : roleEdit} perms={perms.data ?? []} onClose={() => setRoleEdit(null)} onSaved={refresh} />}
    </>
  );
}

function RoleEditor({ role, perms, onClose, onSaved }: { role: Role | null;
  perms: { codename: string; description: string }[]; onClose: () => void; onSaved: () => void }) {
  const { t } = useSession();
  const path = useBizPath();
  const { toast, confirm } = useUi();
  const [name, setName] = useState(role?.name ?? "");
  const [sel, setSel] = useState<Set<string>>(new Set(role?.permissions ?? []));
  const save = useMutation({ mutationFn: () => role ? patch(path(`/roles/${role.id}`), { name, permissions: [...sel] })
    : post(path("/roles"), { name, permissions: [...sel] }), onSuccess: () => { onSaved(); onClose(); },
  onError: (e) => toast(errorMessage(e, t("error")), "error") });
  const remove = useMutation({ mutationFn: () => del(path(`/roles/${role!.id}`)), onSuccess: () => { onSaved(); onClose(); },
    onError: (e) => toast(errorMessage(e, t("error")), "error") });
  const groups = perms.reduce<Record<string, typeof perms>>((acc, p) => { const g = p.codename.split(".")[0]!; (acc[g] ??= []).push(p); return acc; }, {});
  return (
    <Modal wide open onClose={onClose} title={role?.name ?? t("new_role")} footer={<>
      {role && !role.is_system && <Button variant="danger" className="me-auto" onClick={async () => { if (await confirm({ title: t("are_you_sure"), danger: true })) remove.mutate(); }}>{t("delete")}</Button>}
      <Button variant="secondary" onClick={onClose}>{t("cancel")}</Button>
      <Button disabled={!name || save.isPending} onClick={() => save.mutate()}>{t("save")}</Button></>}>
      <Field label={t("role")}><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {Object.entries(groups).map(([g, list]) => (
          <fieldset key={g} className="rounded-lg border border-line p-3">
            <legend className="px-1 text-[13px] font-semibold">{g}</legend>
            {list.map((p) => (
              <label key={p.codename} className="flex items-center gap-2 py-1 text-[13px]">
                <input type="checkbox" checked={sel.has(p.codename)} onChange={(e) => { const n = new Set(sel); if (e.target.checked) n.add(p.codename); else n.delete(p.codename); setSel(n); }} />
                <span>{p.description}</span><code className="ms-auto text-[11px] text-hint" dir="ltr">{p.codename.split(".").slice(1).join(".")}</code>
              </label>
            ))}
          </fieldset>
        ))}
      </div>
    </Modal>
  );
}

const emptyZone = { name_ar: "", name_en: "", areas: "", fee: "", min_order: "", free_delivery_threshold: "", eta_min: "", eta_max: "", is_active: true };

export function DeliveryPage() {
  const { t, money } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { toast, confirm } = useUi();
  const q = useQuery({ queryKey: key("zones"), queryFn: () => get<Zone[]>(path("/delivery-zones")) });
  const [edit, setEdit] = useState<{ id?: string } & typeof emptyZone | null>(null);
  const n = (v: string) => (v.trim() === "" ? null : Math.max(0, Math.round(Number(v))));
  const save = useMutation({
    mutationFn: () => {
      const body = { name_ar: edit!.name_ar, name_en: edit!.name_en, areas: edit!.areas.split(/[,،]/).map((s) => s.trim()).filter(Boolean),
        fee: n(edit!.fee) ?? 0, min_order: n(edit!.min_order), free_delivery_threshold: n(edit!.free_delivery_threshold),
        eta_min: n(edit!.eta_min), eta_max: n(edit!.eta_max), is_active: edit!.is_active };
      return edit!.id ? patch(path(`/delivery-zones/${edit!.id}`), body) : post(path("/delivery-zones"), body);
    },
    onSuccess: () => { setEdit(null); qc.invalidateQueries({ queryKey: key("zones") }); },
    onError: (e) => toast(errorMessage(e, t("error")), "error"),
  });
  const remove = useMutation({ mutationFn: (id: string) => del(path(`/delivery-zones/${id}`)), onSuccess: () => qc.invalidateQueries({ queryKey: key("zones") }) });
  const s = (v: number | null) => (v === null ? "" : String(v));
  return (
    <>
      <PageHeader title={t("zones")} actions={<Button onClick={() => setEdit({ ...emptyZone })}>+ {t("new_zone")}</Button>} />
      {q.isPending ? <Loading /> : q.isError ? <ErrorBox error={q.error} /> : (
        <Table empty={!q.data.length} head={[t("zones"), t("fee"), t("min_order"), t("free_over"), t("eta"), t("active"), ""]}>
          {q.data.map((z) => (
            <tr key={z.id}>
              <td className="px-4 py-2.5"><p className="font-medium">{z.name_ar}</p><p className="text-[12px] text-hint">{z.areas.join("، ")}</p></td>
              <td className="tabular px-4 py-2.5">{money(z.fee)}</td>
              <td className="tabular px-4 py-2.5">{z.min_order !== null ? money(z.min_order) : "—"}</td>
              <td className="tabular px-4 py-2.5">{z.free_delivery_threshold !== null ? money(z.free_delivery_threshold) : "—"}</td>
              <td className="tabular px-4 py-2.5">{z.eta_min && z.eta_max ? `${z.eta_min}–${z.eta_max}` : "—"}</td>
              <td className="px-4 py-2.5">{z.is_active ? <Badge tone="success">✓</Badge> : <Badge>—</Badge>}</td>
              <td className="px-4 py-2.5"><div className="flex justify-end gap-2">
                <Button size="sm" variant="secondary" onClick={() => setEdit({ id: z.id, name_ar: z.name_ar, name_en: z.name_en, areas: z.areas.join("، "), fee: String(z.fee), min_order: s(z.min_order), free_delivery_threshold: s(z.free_delivery_threshold), eta_min: s(z.eta_min), eta_max: s(z.eta_max), is_active: z.is_active })}>{t("edit")}</Button>
                <Button size="sm" variant="danger" onClick={async () => { if (await confirm({ title: t("are_you_sure"), danger: true })) remove.mutate(z.id); }}>{t("delete")}</Button>
              </div></td>
            </tr>
          ))}
        </Table>
      )}
      {edit && (
        <Modal open onClose={() => setEdit(null)} title={edit.id ? edit.name_ar : t("new_zone")} footer={<>
          <Button variant="secondary" onClick={() => setEdit(null)}>{t("cancel")}</Button>
          <Button disabled={!edit.name_ar || save.isPending} onClick={() => save.mutate()}>{t("save")}</Button></>}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("name_ar")}><Input value={edit.name_ar} onChange={(e) => setEdit({ ...edit, name_ar: e.target.value })} /></Field>
            <Field label={t("name_en")}><Input dir="ltr" value={edit.name_en} onChange={(e) => setEdit({ ...edit, name_en: e.target.value })} /></Field>
            <Field label={t("areas")} className="sm:col-span-2"><Input value={edit.areas} onChange={(e) => setEdit({ ...edit, areas: e.target.value })} /></Field>
            <Field label={t("fee")}><Input inputMode="numeric" value={edit.fee} onChange={(e) => setEdit({ ...edit, fee: e.target.value })} /></Field>
            <Field label={t("min_order")}><Input inputMode="numeric" value={edit.min_order} onChange={(e) => setEdit({ ...edit, min_order: e.target.value })} /></Field>
            <Field label={t("free_over")}><Input inputMode="numeric" value={edit.free_delivery_threshold} onChange={(e) => setEdit({ ...edit, free_delivery_threshold: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-2"><Field label={`${t("eta")} ↓`}><Input inputMode="numeric" value={edit.eta_min} onChange={(e) => setEdit({ ...edit, eta_min: e.target.value })} /></Field>
              <Field label="↑"><Input inputMode="numeric" value={edit.eta_max} onChange={(e) => setEdit({ ...edit, eta_max: e.target.value })} /></Field></div>
            <Toggle checked={edit.is_active} onChange={(v) => setEdit({ ...edit, is_active: v })} label={t("active")} />
          </div>
        </Modal>
      )}
    </>
  );
}
