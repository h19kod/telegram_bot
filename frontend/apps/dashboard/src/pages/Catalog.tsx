import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { PageHeader } from "../components/Shell";
import { Badge, Button, Card, cx, Empty, ErrorBox, errorMessage, Field, Input, Loading, Modal,
  Pager, Select, Table, TextArea, Toggle, useUi } from "../components/ui";
import { ApiError, del, get, patch, post, qs, upload, type Category, type Coupon,
  type OptionGroup, type Paginated, type Product } from "../lib/api";
import { useBizKey, useBizPath, useSession } from "../lib/session";

const toInt = (v: string) => (v.trim() === "" ? null : Math.max(0, Math.round(Number(v))));

export function ProductsPage() {
  const { t, money, can } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { toast } = useUi();
  const [filters, setFilters] = useState({ search: "", category: "", availability: "", page: 1 });
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const cats = useQuery({ queryKey: key("categories"), queryFn: () => get<Category[]>(path("/categories")) });
  const q = useQuery({ queryKey: key("products", filters), placeholderData: (p) => p,
    queryFn: () => get<Paginated<Product>>(path(`/products${qs(filters)}`)) });
  const toggle = useMutation({
    mutationFn: (p: Product) => patch(path(`/products/${p.id}`), {
      availability: p.availability === "available" ? "out_of_stock" : "available" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key("products") }),
    onError: (e) => toast(errorMessage(e, t("error")), "error"),
  });
  const catName = (id: string) => cats.data?.find((c) => c.id === id)?.name_ar ?? "";
  const canEdit = can("catalog.edit");
  return (
    <>
      <PageHeader title={t("products")} actions={canEdit && <Button onClick={() => setEditing("new")}>+ {t("new_product")}</Button>}>
        <div className="mt-4 flex flex-wrap gap-2">
          <Input type="search" placeholder={t("search")} className="min-w-52 flex-1" value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value, page: 1 })} />
          <Select aria-label={t("category")} className="w-auto" value={filters.category} onChange={(e) => setFilters({ ...filters, category: e.target.value, page: 1 })}>
            <option value="">{t("categories")}</option>{cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name_ar}</option>)}
          </Select>
          <Select aria-label={t("availability")} className="w-auto" value={filters.availability} onChange={(e) => setFilters({ ...filters, availability: e.target.value, page: 1 })}>
            <option value="">{t("availability")}</option><option value="available">{t("available")}</option>
            <option value="out_of_stock">{t("out_of_stock")}</option><option value="hidden">{t("hidden")}</option>
          </Select>
        </div>
      </PageHeader>
      {q.isPending ? <Loading /> : q.isError ? <ErrorBox error={q.error} onRetry={() => q.refetch()} /> : (
        <>
          <Table empty={!q.data.results.length} head={["", t("name_ar"), t("category"), t("price"), t("stock"), t("availability")]}>
            {q.data.results.map((p) => (
              <tr key={p.id} className="hover:bg-bg2/60">
                <td className="w-14 px-4 py-2">{p.images[0] ? <img src={p.images[0].thumbnail || p.images[0].image} alt="" className="size-10 rounded-md object-cover" />
                  : <div className="grid size-10 place-items-center rounded-md bg-bg2">🍽</div>}</td>
                <td className="px-4 py-2"><button type="button" className="text-start font-medium hover:text-accent" onClick={() => setEditing(p.id)}>{p.name_ar}</button>
                  {p.option_groups.length > 0 && <div className="text-[12px] text-hint">{p.option_groups.map((g) => g.name_ar).join(" · ")}</div>}</td>
                <td className="px-4 py-2 text-[13px]">{catName(p.category)}</td>
                <td className="tabular px-4 py-2">{money(p.price)}{p.compare_at_price && <s className="ms-1 text-[12px] text-hint">{money(p.compare_at_price)}</s>}</td>
                <td className="tabular px-4 py-2">{p.track_stock ? p.stock_quantity : "∞"}</td>
                <td className="px-4 py-2">{p.availability === "hidden" ? <Badge>{t("hidden")}</Badge> :
                  <Toggle checked={p.availability === "available"} disabled={!canEdit || toggle.isPending}
                    onChange={() => toggle.mutate(p)} label={t(p.availability === "available" ? "available" : "out_of_stock")} />}</td>
              </tr>
            ))}
          </Table>
          <Pager page={filters.page} count={q.data.count} onPage={(page) => setFilters({ ...filters, page })} />
        </>
      )}
      {editing && <ProductEditor id={editing} categories={cats.data ?? []} onClose={() => setEditing(null)} onSaved={(id) => setEditing(id)} />}
    </>
  );
}

type Form = { category: string; name_ar: string; name_en: string; description_ar: string;
  description_en: string; sku: string; price: string; compare_at_price: string;
  availability: Product["availability"]; track_stock: boolean; stock_quantity: string; prep_time_min: string };

function ProductEditor({ id, categories, onClose, onSaved }: { id: string; categories: Category[];
  onClose: () => void; onSaved: (id: string) => void }) {
  const { t, can } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { toast, confirm } = useUi();
  const isNew = id === "new";
  const q = useQuery({ queryKey: key("product", id), enabled: !isNew, queryFn: () => get<Product>(path(`/products/${id}`)) });
  const [f, setF] = useState<Form>({ category: categories[0]?.id ?? "", name_ar: "", name_en: "", description_ar: "",
    description_en: "", sku: "", price: "", compare_at_price: "", availability: "available", track_stock: false,
    stock_quantity: "", prep_time_min: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    const p = q.data;
    if (p) setF({ category: p.category, name_ar: p.name_ar, name_en: p.name_en, description_ar: p.description_ar,
      description_en: p.description_en, sku: p.sku, price: String(p.price), compare_at_price: p.compare_at_price?.toString() ?? "",
      availability: p.availability, track_stock: p.track_stock, stock_quantity: p.stock_quantity?.toString() ?? "",
      prep_time_min: p.prep_time_min?.toString() ?? "" });
  }, [q.data]);
  const refresh = () => { qc.invalidateQueries({ queryKey: key("products") }); qc.invalidateQueries({ queryKey: key("product", id) }); };
  const save = useMutation({
    mutationFn: () => {
      const body = { ...f, price: toInt(f.price), compare_at_price: toInt(f.compare_at_price),
        stock_quantity: f.track_stock ? toInt(f.stock_quantity) : null, prep_time_min: toInt(f.prep_time_min) };
      return isNew ? post<Product>(path("/products"), body) : patch<Product>(path(`/products/${id}`), body);
    },
    onSuccess: (p) => { toast(t("saved")); setErrors({}); refresh(); if (isNew) onSaved(p.id); },
    onError: (e) => { if (e instanceof ApiError) setErrors(e.fieldErrors()); toast(errorMessage(e, t("error")), "error"); },
  });
  const remove = useMutation({ mutationFn: () => del(path(`/products/${id}`)), onSuccess: () => { refresh(); onClose(); } });
  const dup = useMutation({ mutationFn: () => post<Product>(path(`/products/${id}/duplicate`)), onSuccess: (p) => { refresh(); onSaved(p.id); } });
  const uploadImg = useMutation({
    mutationFn: (file: File) => { const fd = new FormData(); fd.append("image", file); return upload(path(`/products/${id}/images`), fd); },
    onSuccess: refresh, onError: (e) => toast(errorMessage(e, t("error")), "error"),
  });
  const delImg = useMutation({ mutationFn: (imgId: string) => del(path(`/products/${id}/images/${imgId}`)), onSuccess: refresh });
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((x) => ({ ...x, [k]: v }));
  const canPrice = can("catalog.edit_prices");
  return (
    <Modal wide open onClose={onClose} title={isNew ? t("new_product") : f.name_ar || "…"} footer={<>
      {!isNew && <Button variant="danger" className="me-auto" onClick={async () => { if (await confirm({ title: t("are_you_sure"), danger: true })) remove.mutate(); }}>{t("delete")}</Button>}
      {!isNew && <Button variant="secondary" disabled={dup.isPending} onClick={() => dup.mutate()}>{t("duplicate")}</Button>}
      <Button variant="secondary" onClick={onClose}>{t("close")}</Button>
      <Button disabled={save.isPending} onClick={() => save.mutate()}>{t("save")}</Button>
    </>}>
      {!isNew && q.isPending ? <Loading /> : (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("name_ar")} error={errors.name_ar}><Input value={f.name_ar} onChange={(e) => set("name_ar", e.target.value)} /></Field>
            <Field label={t("name_en")} error={errors.name_en}><Input dir="ltr" value={f.name_en} onChange={(e) => set("name_en", e.target.value)} /></Field>
            <Field label={t("category")} error={errors.category}><Select value={f.category} onChange={(e) => set("category", e.target.value)}>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name_ar}</option>)}</Select></Field>
            <Field label={t("availability")}><Select value={f.availability} onChange={(e) => set("availability", e.target.value as Form["availability"])}>
              <option value="available">{t("available")}</option><option value="out_of_stock">{t("out_of_stock")}</option><option value="hidden">{t("hidden")}</option></Select></Field>
            <Field label={t("price")} error={errors.price}><Input inputMode="numeric" disabled={!canPrice} value={f.price} onChange={(e) => set("price", e.target.value)} /></Field>
            <Field label={t("compare_at")} error={errors.compare_at_price}><Input inputMode="numeric" disabled={!canPrice} value={f.compare_at_price} onChange={(e) => set("compare_at_price", e.target.value)} /></Field>
            <Field label={t("description_ar")} className="sm:col-span-2"><TextArea value={f.description_ar} onChange={(e) => set("description_ar", e.target.value)} /></Field>
            <Field label={t("description_en")} className="sm:col-span-2"><TextArea dir="ltr" value={f.description_en} onChange={(e) => set("description_en", e.target.value)} /></Field>
            <Field label={t("sku")} error={errors.sku}><Input dir="ltr" value={f.sku} onChange={(e) => set("sku", e.target.value)} /></Field>
            <Field label={t("prep_time")}><Input inputMode="numeric" value={f.prep_time_min} onChange={(e) => set("prep_time_min", e.target.value)} /></Field>
            <div className="flex items-end gap-3"><Toggle checked={f.track_stock} onChange={(v) => set("track_stock", v)} label={t("track_stock")} /></div>
            {f.track_stock && <Field label={t("stock")} error={errors.stock_quantity}><Input inputMode="numeric" value={f.stock_quantity} onChange={(e) => set("stock_quantity", e.target.value)} /></Field>}
          </div>
          {!isNew && q.data && <>
            <Card title={t("images")} actions={
              <label className="cursor-pointer rounded-lg border border-line px-2.5 py-1.5 text-[13px] font-semibold hover:bg-bg2">
                {uploadImg.isPending ? "…" : t("upload_image")}
                <input type="file" accept="image/jpeg,image/png,image/webp" className="sr-only"
                  onChange={(e) => { const file = e.target.files?.[0]; if (file) uploadImg.mutate(file); e.target.value = ""; }} />
              </label>}>
              {!q.data.images.length ? <Empty>{t("no_data")}</Empty> : (
                <div className="flex flex-wrap gap-3">
                  {q.data.images.map((img) => (
                    <div key={img.id} className="relative">
                      <img src={img.thumbnail || img.image} alt="" className="size-24 rounded-lg object-cover" />
                      <button type="button" aria-label={t("delete")} onClick={() => delImg.mutate(img.id)}
                        className="absolute -top-2 -end-2 grid size-6 place-items-center rounded-full bg-danger text-[12px] text-white">✕</button>
                    </div>
                  ))}
                </div>
              )}
            </Card>
            <OptionGroups product={q.data} onChange={refresh} />
          </>}
        </div>
      )}
    </Modal>
  );
}

function OptionGroups({ product, onChange }: { product: Product; onChange: () => void }) {
  const { t, money } = useSession();
  const path = useBizPath();
  const { toast, confirm } = useUi();
  const [g, setG] = useState({ name_ar: "", selection_type: "single", is_required: false, max_select: "3" });
  const [opt, setOpt] = useState<Record<string, { name_ar: string; price_delta: string }>>({});
  const onErr = (e: unknown) => toast(errorMessage(e, t("error")), "error");
  const addGroup = useMutation({ mutationFn: () => post(path(`/products/${product.id}/option-groups`), {
    name_ar: g.name_ar, selection_type: g.selection_type, is_required: g.is_required,
    min_select: g.is_required ? 1 : 0, max_select: g.selection_type === "single" ? 1 : Number(g.max_select) || 1 }),
    onSuccess: () => { setG({ ...g, name_ar: "" }); onChange(); }, onError: onErr });
  const delGroup = useMutation({ mutationFn: (gid: string) => del(path(`/option-groups/${gid}`)), onSuccess: onChange, onError: onErr });
  const addOpt = useMutation({ mutationFn: (gid: string) => post(path(`/option-groups/${gid}/options`), {
    name_ar: opt[gid]?.name_ar, price_delta: toInt(opt[gid]?.price_delta ?? "") ?? 0 }),
    onSuccess: (_, gid) => { setOpt({ ...opt, [gid]: { name_ar: "", price_delta: "" } }); onChange(); }, onError: onErr });
  const delOpt = useMutation({ mutationFn: (oid: string) => del(path(`/options/${oid}`)), onSuccess: onChange, onError: onErr });
  const togOpt = useMutation({ mutationFn: (o: { id: string; is_available: boolean }) => patch(path(`/options/${o.id}`), { is_available: !o.is_available }), onSuccess: onChange });
  return (
    <Card title={t("option_groups")}>
      <div className="space-y-4">
        {product.option_groups.map((grp: OptionGroup) => (
          <div key={grp.id} className="rounded-lg border border-line p-3">
            <div className="mb-2 flex items-center gap-2">
              <span className="font-semibold">{grp.name_ar}</span>
              <Badge>{grp.selection_type === "single" ? t("single") : `${t("multiple")} ≤${grp.max_select}`}</Badge>
              {grp.min_select > 0 && <Badge tone="warn">{t("required")}</Badge>}
              <button type="button" className="ms-auto text-[13px] text-danger" onClick={async () => { if (await confirm({ title: t("are_you_sure"), danger: true })) delGroup.mutate(grp.id); }}>{t("delete")}</button>
            </div>
            <ul className="divide-y divide-line text-[14px]">
              {grp.options.map((o) => (
                <li key={o.id} className={cx("flex items-center gap-3 py-1.5", !o.is_available && "opacity-50")}>
                  <span className="flex-1">{o.name_ar}</span>
                  <span className="tabular text-hint">{o.price_delta ? `+${money(o.price_delta)}` : ""}</span>
                  <Toggle checked={o.is_available} onChange={() => togOpt.mutate(o)} label="" />
                  <button type="button" aria-label={t("delete")} className="text-danger" onClick={() => delOpt.mutate(o.id)}>✕</button>
                </li>
              ))}
            </ul>
            <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (opt[grp.id]?.name_ar) addOpt.mutate(grp.id); }}>
              <Input placeholder={t("new_option")} value={opt[grp.id]?.name_ar ?? ""} onChange={(e) => setOpt({ ...opt, [grp.id]: { price_delta: opt[grp.id]?.price_delta ?? "", name_ar: e.target.value } })} />
              <Input placeholder={t("price_delta")} inputMode="numeric" className="w-32" value={opt[grp.id]?.price_delta ?? ""} onChange={(e) => setOpt({ ...opt, [grp.id]: { name_ar: opt[grp.id]?.name_ar ?? "", price_delta: e.target.value } })} />
              <Button size="sm" variant="secondary">{t("add")}</Button>
            </form>
          </div>
        ))}
        <form className="flex flex-wrap items-end gap-2 rounded-lg bg-bg2/60 p-3" onSubmit={(e) => { e.preventDefault(); if (g.name_ar) addGroup.mutate(); }}>
          <Field label={t("new_group")} className="min-w-40 flex-1"><Input value={g.name_ar} onChange={(e) => setG({ ...g, name_ar: e.target.value })} placeholder="الحجم / الإضافات" /></Field>
          <Select className="w-auto" value={g.selection_type} onChange={(e) => setG({ ...g, selection_type: e.target.value })}>
            <option value="single">{t("single")}</option><option value="multiple">{t("multiple")}</option></Select>
          {g.selection_type === "multiple" && <Input aria-label={t("max_select")} className="w-20" inputMode="numeric" value={g.max_select} onChange={(e) => setG({ ...g, max_select: e.target.value })} />}
          <Toggle checked={g.is_required} onChange={(v) => setG({ ...g, is_required: v })} label={t("required")} />
          <Button size="sm">{t("add")}</Button>
        </form>
      </div>
    </Card>
  );
}

export function CategoriesPage() {
  const { t, can } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { toast, confirm } = useUi();
  const q = useQuery({ queryKey: key("categories"), queryFn: () => get<Category[]>(path("/categories")) });
  const [form, setForm] = useState({ name_ar: "", name_en: "" });
  const [edit, setEdit] = useState<Category | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: key("categories") });
  const onErr = (e: unknown) => toast(errorMessage(e, t("error")), "error");
  const create = useMutation({ mutationFn: () => post(path("/categories"), form), onSuccess: () => { setForm({ name_ar: "", name_en: "" }); refresh(); }, onError: onErr });
  const update = useMutation({ mutationFn: (c: Partial<Category> & { id: string }) => patch(path(`/categories/${c.id}`), c), onSuccess: () => { setEdit(null); refresh(); }, onError: onErr });
  const remove = useMutation({ mutationFn: (id: string) => del(path(`/categories/${id}`)), onSuccess: refresh, onError: onErr });
  const reorder = useMutation({ mutationFn: (ids: string[]) => post(path("/categories/reorder"), { ids }), onSuccess: refresh });
  const img = useMutation({ mutationFn: (v: { id: string; file: File }) => { const fd = new FormData(); fd.append("image", v.file); return upload(path(`/categories/${v.id}/image`), fd); }, onSuccess: refresh, onError: onErr });
  const canEdit = can("catalog.edit");
  function move(i: number, d: number) {
    const ids = (q.data ?? []).map((c) => c.id);
    const j = i + d;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j]!, ids[i]!];
    reorder.mutate(ids);
  }
  return (
    <>
      <PageHeader title={t("categories")} />
      {canEdit && (
        <form className="mb-4 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); if (form.name_ar) create.mutate(); }}>
          <Input placeholder={t("name_ar")} className="min-w-40 flex-1" value={form.name_ar} onChange={(e) => setForm({ ...form, name_ar: e.target.value })} />
          <Input placeholder={t("name_en")} dir="ltr" className="min-w-40 flex-1" value={form.name_en} onChange={(e) => setForm({ ...form, name_en: e.target.value })} />
          <Button disabled={create.isPending}>+ {t("add")}</Button>
        </form>
      )}
      {q.isPending ? <Loading /> : q.isError ? <ErrorBox error={q.error} /> : (
        <Table empty={!q.data.length} head={["", t("name_ar"), t("name_en"), t("products_count"), t("active"), ""]}>
          {q.data.map((c, i) => (
            <tr key={c.id}>
              <td className="w-16 px-4 py-2">
                <label className={cx("block size-10 overflow-hidden rounded-md bg-bg2", canEdit && "cursor-pointer")}>
                  {c.image ? <img src={c.image} alt="" className="size-full object-cover" /> : <span className="grid size-full place-items-center">📂</span>}
                  {canEdit && <input type="file" accept="image/*" className="sr-only" onChange={(e) => { const file = e.target.files?.[0]; if (file) img.mutate({ id: c.id, file }); }} />}
                </label>
              </td>
              <td className="px-4 py-2 font-medium">{edit?.id === c.id ? <Input value={edit.name_ar} onChange={(e) => setEdit({ ...edit, name_ar: e.target.value })} /> : c.name_ar}</td>
              <td className="px-4 py-2" dir="ltr">{edit?.id === c.id ? <Input value={edit.name_en} onChange={(e) => setEdit({ ...edit, name_en: e.target.value })} /> : c.name_en}</td>
              <td className="tabular px-4 py-2">{c.products_count}</td>
              <td className="px-4 py-2"><Toggle checked={c.is_active} disabled={!canEdit} onChange={(v) => update.mutate({ id: c.id, is_active: v })} label="" /></td>
              <td className="px-4 py-2">{canEdit && <div className="flex justify-end gap-1">
                <Button size="sm" variant="ghost" aria-label="up" onClick={() => move(i, -1)}>↑</Button>
                <Button size="sm" variant="ghost" aria-label="down" onClick={() => move(i, 1)}>↓</Button>
                {edit?.id === c.id ? <Button size="sm" onClick={() => update.mutate({ id: c.id, name_ar: edit.name_ar, name_en: edit.name_en })}>{t("save")}</Button>
                  : <Button size="sm" variant="secondary" onClick={() => setEdit(c)}>{t("edit")}</Button>}
                <Button size="sm" variant="danger" onClick={async () => { if (await confirm({ title: t("are_you_sure"), danger: true })) remove.mutate(c.id); }}>{t("delete")}</Button>
              </div>}</td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}

export function DiscountsPage() {
  const { t, money } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { toast } = useUi();
  const q = useQuery({ queryKey: key("products", "all"), queryFn: () => get<Paginated<Product>>(path("/products?page_size=100")) });
  const [pct, setPct] = useState<Record<string, string>>({});
  const apply = useMutation({
    mutationFn: (v: { p: Product; percent: number | null }) => {
      const base = v.p.compare_at_price ?? v.p.price;
      return patch(path(`/products/${v.p.id}`), v.percent ? { compare_at_price: base, price: Math.round(base * (100 - v.percent) / 100) }
        : { price: base, compare_at_price: null });
    },
    onSuccess: () => { toast(t("saved")); qc.invalidateQueries({ queryKey: key("products") }); },
    onError: (e) => toast(errorMessage(e, t("error")), "error"),
  });
  return (
    <>
      <PageHeader title={t("discounts")} />
      <Coupons />
      <h2 className="mt-6 mb-1 text-[17px] font-bold">{t("product_discounts")}</h2>
      <p className="mb-3 text-[14px] text-hint">{t("discount_hint")}</p>
      {q.isPending ? <Loading /> : q.isError ? <ErrorBox error={q.error} /> : (
        <Table empty={!q.data.results.length} head={[t("name_ar"), t("compare_at"), t("price"), t("discount_pct"), ""]}>
          {q.data.results.map((p) => {
            const current = p.compare_at_price ? Math.round(100 * (p.compare_at_price - p.price) / p.compare_at_price) : 0;
            return (
              <tr key={p.id}>
                <td className="px-4 py-2 font-medium">{p.name_ar}</td>
                <td className="tabular px-4 py-2 text-hint">{p.compare_at_price ? money(p.compare_at_price) : "—"}</td>
                <td className="tabular px-4 py-2 font-semibold">{money(p.price)}</td>
                <td className="px-4 py-2"><Input className="w-24" inputMode="numeric" placeholder={current ? `${current}%` : "%"}
                  value={pct[p.id] ?? ""} onChange={(e) => setPct({ ...pct, [p.id]: e.target.value })} /></td>
                <td className="px-4 py-2"><div className="flex justify-end gap-2">
                  <Button size="sm" disabled={!pct[p.id] || Number(pct[p.id]) <= 0 || Number(pct[p.id]) >= 100}
                    onClick={() => { apply.mutate({ p, percent: Number(pct[p.id]) }); setPct({ ...pct, [p.id]: "" }); }}>{t("apply")}</Button>
                  {p.compare_at_price && <Button size="sm" variant="secondary" onClick={() => apply.mutate({ p, percent: null })}>{t("remove_discount")}</Button>}
                </div></td>
              </tr>
            );
          })}
        </Table>
      )}
    </>
  );
}

function Coupons() {
  const { t, money, lang } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { toast, confirm } = useUi();
  const q = useQuery({ queryKey: key("coupons"), queryFn: () => get<Coupon[]>(path("/coupons")) });
  const empty = { code: "", kind: "percent", value: "", max_discount: "", min_order: "", usage_limit: "",
    per_customer_limit: "1", ends_at: "" };
  const [f, setF] = useState(empty);
  const [errs, setErrs] = useState<Record<string, string>>({});
  const refresh = () => qc.invalidateQueries({ queryKey: key("coupons") });
  const create = useMutation({
    mutationFn: () => post(path("/coupons"), { code: f.code, kind: f.kind, value: toInt(f.value) ?? 0,
      max_discount: toInt(f.max_discount), min_order: toInt(f.min_order) ?? 0, usage_limit: toInt(f.usage_limit),
      per_customer_limit: toInt(f.per_customer_limit), ends_at: f.ends_at ? `${f.ends_at}T23:59:59+03:00` : null }),
    onSuccess: () => { setF(empty); setErrs({}); refresh(); toast(t("saved")); },
    onError: (e) => { if (e instanceof ApiError) setErrs(e.fieldErrors()); toast(errorMessage(e, t("error")), "error"); },
  });
  const toggle = useMutation({ mutationFn: (c: Coupon) => patch(path(`/coupons/${c.id}`), { is_active: !c.is_active }), onSuccess: refresh });
  const remove = useMutation({ mutationFn: (id: string) => del(path(`/coupons/${id}`)), onSuccess: refresh });
  return (
    <Card title={t("coupons")}>
      {q.isError ? <ErrorBox error={q.error} /> : (
        <>
          <form className="mb-4 grid gap-2 sm:grid-cols-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
            <Field label={t("code")} error={errs.code}><Input dir="ltr" className="uppercase" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} required /></Field>
            <Field label={t("kind")}><Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
              <option value="percent">{t("percent")}</option><option value="fixed">{t("fixed")}</option></Select></Field>
            <Field label={t("value")} error={errs.value}><Input inputMode="numeric" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} required /></Field>
            <Field label={t("max_discount")}><Input inputMode="numeric" value={f.max_discount} onChange={(e) => setF({ ...f, max_discount: e.target.value })} /></Field>
            <Field label={t("min_order")}><Input inputMode="numeric" value={f.min_order} onChange={(e) => setF({ ...f, min_order: e.target.value })} /></Field>
            <Field label={t("usage_limit")}><Input inputMode="numeric" placeholder="∞" value={f.usage_limit} onChange={(e) => setF({ ...f, usage_limit: e.target.value })} /></Field>
            <Field label={t("per_customer")}><Input inputMode="numeric" placeholder="∞" value={f.per_customer_limit} onChange={(e) => setF({ ...f, per_customer_limit: e.target.value })} /></Field>
            <Field label={t("ends")} error={errs.ends_at}><Input type="date" value={f.ends_at} onChange={(e) => setF({ ...f, ends_at: e.target.value })} /></Field>
            <div className="sm:col-span-4"><Button disabled={create.isPending}>+ {t("new_coupon")}</Button></div>
          </form>
          <Table empty={!q.data?.length} head={[t("code"), t("value"), t("min_order"), t("used"), t("ends"), t("active"), ""]}>
            {q.data?.map((c) => (
              <tr key={c.id}>
                <td className="px-4 py-2 font-mono font-semibold" dir="ltr">{c.code}</td>
                <td className="tabular px-4 py-2">{c.kind === "percent" ? `${c.value}%` : money(c.value)}{c.max_discount !== null && <span className="text-[12px] text-hint"> ≤ {money(c.max_discount)}</span>}</td>
                <td className="tabular px-4 py-2">{c.min_order ? money(c.min_order) : "—"}</td>
                <td className="tabular px-4 py-2">{c.used_count}{c.usage_limit !== null && ` / ${c.usage_limit}`}</td>
                <td className="tabular px-4 py-2 text-[13px]">{c.ends_at ? new Date(c.ends_at).toLocaleDateString(lang === "ar" ? "ar-IQ" : "en-GB", { numberingSystem: "latn" }) : "—"}</td>
                <td className="px-4 py-2"><Toggle checked={c.is_active} onChange={() => toggle.mutate(c)} label="" /></td>
                <td className="px-4 py-2 text-end"><Button size="sm" variant="danger" onClick={async () => { if (await confirm({ title: t("are_you_sure"), danger: true })) remove.mutate(c.id); }}>{t("delete")}</Button></td>
              </tr>
            ))}
          </Table>
        </>
      )}
    </Card>
  );
}
