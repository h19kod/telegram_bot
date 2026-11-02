import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import type { OptionGroup, ProductDetail } from "../api";
import { ActionBar, Page } from "../components/Layout";
import { Price, ProductImage } from "../components/ProductCard";
import { Button, cx, ErrorState, Input, Skeleton, Stepper } from "../components/ui";
import { useCartMutations } from "../hooks/queries";
import { useMainButton } from "../hooks/telegram";
import { useSession } from "../session";
import { haptic } from "../telegram";

function defaults(p: ProductDetail): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const g of p.option_groups) {
    out[g.id] = g.options.filter((o) => o.is_default && o.is_available).slice(0, g.max_select)
      .map((o) => o.id);
  }
  return out;
}

export function ProductDetailPage() {
  const { id = "" } = useParams();
  const { api, t } = useSession();
  const q = useQuery({ queryKey: ["product", id], queryFn: () => api.product(id) });
  if (q.isPending) {
    return <Page><Skeleton className="-mx-4 aspect-square rounded-none" />
      <Skeleton className="mt-4 h-7 w-2/3" /><Skeleton className="mt-3 h-20" /></Page>;
  }
  if (q.isError) return <Page><ErrorState message={t("error_title")} retryLabel={t("retry")}
    onRetry={() => q.refetch()} /></Page>;
  return <ProductView product={q.data} />;
}

function ProductView({ product }: { product: ProductDetail }) {
  const { t, money } = useSession();
  const navigate = useNavigate();
  const { add } = useCartMutations();
  const [sel, setSel] = useState<Record<string, string[]>>(() => defaults(product));
  const [qty, setQty] = useState(1);
  const [note, setNote] = useState("");
  const [imgIdx, setImgIdx] = useState(0);
  const [showErrors, setShowErrors] = useState(false);
  const groups = product.option_groups;

  const missing = groups.filter((g) => (sel[g.id]?.length ?? 0) < g.min_select);
  // Display-only estimate; the cart total shown afterwards always comes from the server.
  const unit = useMemo(() => product.price + groups.reduce((sum, g) => sum + g.options
    .filter((o) => sel[g.id]?.includes(o.id)).reduce((s, o) => s + o.price_delta, 0), 0),
  [product, groups, sel]);

  function toggle(g: OptionGroup, optionId: string) {
    haptic.select();
    setSel((prev) => {
      const cur = prev[g.id] ?? [];
      if (g.selection_type === "single") return { ...prev, [g.id]: [optionId] };
      if (cur.includes(optionId)) return { ...prev, [g.id]: cur.filter((x) => x !== optionId) };
      if (cur.length >= g.max_select) return prev;
      return { ...prev, [g.id]: [...cur, optionId] };
    });
  }

  function submit() {
    if (missing.length) {
      setShowErrors(true);
      haptic.error();
      document.getElementById(`g-${missing[0]?.id}`)?.scrollIntoView({ behavior: "smooth",
        block: "center" });
      return;
    }
    add.mutate({ productId: product.id, optionIds: Object.values(sel).flat(), quantity: qty,
      note: note.trim() }, { onSuccess: () => navigate(-1) });
  }

  const label = `${t("add_to_cart")} · ${money(unit * qty)}`;
  const mainButton = useMainButton({ text: label, visible: product.is_available,
    progress: add.isPending, onClick: submit });

  useEffect(() => { window.scrollTo(0, 0); }, []);

  return (
    <Page bottomPad>
      <div className="-mx-4 relative aspect-square max-h-[55vh] w-[calc(100%+2rem)] bg-card">
        {product.images.length ? (
          <img src={product.images[imgIdx]?.url ?? ""} alt={product.name}
            className="h-full w-full object-cover" />
        ) : <ProductImage product={product} />}
        {product.images.length > 1 && (
          <div className="absolute inset-x-0 bottom-3 flex justify-center gap-1.5" dir="ltr">
            {product.images.map((_, i) => (
              <button key={i} type="button" aria-label={`image ${i + 1}`}
                onClick={() => setImgIdx(i)}
                className={cx("h-1.5 rounded-full transition-all",
                  i === imgIdx ? "w-5 bg-white" : "w-1.5 bg-white/60")} />
            ))}
          </div>
        )}
      </div>

      <div className="animate-rise -mt-6 relative rounded-t-3xl bg-bg2 pt-5">
        <div className="flex items-start justify-between gap-3">
          <h1 className="text-[22px] leading-tight font-bold">{product.name}</h1>
          {product.discount_percent ? (
            <span className="shrink-0 rounded-full bg-danger px-2.5 py-1 text-[12px] font-bold
              text-on-danger">-{product.discount_percent}%</span>
          ) : null}
        </div>
        <Price price={product.price} compareAt={product.compare_at_price}
          className="mt-1 text-[18px] text-accent" />
        {product.prep_time_min ? <p className="mt-1 text-[13px] text-hint">⏱ {product
          .prep_time_min} {t("minutes")}</p> : null}
        {product.description && (
          <p className="mt-3 text-[15px] leading-relaxed whitespace-pre-line text-hint">
            {product.description}</p>
        )}

        {groups.map((g) => {
          const invalid = showErrors && missing.includes(g);
          return (
            <section key={g.id} id={`g-${g.id}`} className={cx("mt-5 rounded-card bg-card p-4",
              invalid && "ring-2 ring-danger")}>
              <div className="mb-2 flex items-center justify-between">
                <h2 id={`gl-${g.id}`} className="font-semibold">{g.name}</h2>
                <span className={cx("rounded-full px-2 py-0.5 text-[12px]",
                  g.min_select ? "bg-accent/10 text-accent" : "bg-bg2 text-hint")}>
                  {g.min_select ? t("required") : t("choose_up_to", { n: g.max_select })}
                </span>
              </div>
              <div role={g.selection_type === "single" ? "radiogroup" : "group"}
                aria-labelledby={`gl-${g.id}`}>
                {g.options.map((o) => {
                  const on = sel[g.id]?.includes(o.id) ?? false;
                  return (
                    <div key={o.id}>
                      <button type="button" disabled={!o.is_available}
                        role={g.selection_type === "single" ? "radio" : "checkbox"}
                        aria-checked={on} onClick={() => toggle(g, o.id)}
                        className="flex w-full items-center gap-3 border-b border-line py-3
                          text-start last:border-0 disabled:opacity-40">
                        <span className={cx("grid size-5 shrink-0 place-items-center border-2",
                          g.selection_type === "single" ? "rounded-full" : "rounded-md",
                          on ? "border-accent bg-accent text-on-accent" : "border-hint/50")}>
                          {on && <span className="text-[11px]">✓</span>}
                        </span>
                        <span className="flex-1">{o.name}</span>
                        {o.price_delta > 0 && <span className="tabular text-[14px] text-hint">
                          +{money(o.price_delta)}</span>}
                      </button>
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })}

        {product.is_available && (
          <>
            <Input className="mt-5" value={note} maxLength={200}
              onChange={(e) => setNote(e.target.value)} placeholder={t("note_placeholder")} />
            <div className="mt-5 flex justify-center">
              <Stepper value={qty} onChange={setQty} />
            </div>
          </>
        )}
        {!product.is_available && (
          <p className="mt-6 rounded-xl bg-danger/10 p-3 text-center font-semibold
            text-danger">{t("unavailable")}</p>
        )}
      </div>

      {!mainButton && product.is_available && (
        <ActionBar>
          <Button className="w-full" disabled={add.isPending} onClick={submit}>{label}</Button>
        </ActionBar>
      )}
    </Page>
  );
}
