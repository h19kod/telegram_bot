import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { Page } from "../components/Layout";
import { ProductCard, ProductGridSkeleton } from "../components/ProductCard";
import { Button, cx, Empty, ErrorState, Input } from "../components/ui";
import { useCart } from "../hooks/queries";
import { useSession } from "../session";

export function ProductGrid({ params }: { params: Record<string, string | undefined> }) {
  const { api, t } = useSession();
  const q = useInfiniteQuery({
    queryKey: ["products", params],
    queryFn: ({ pageParam }) => api.products(params, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next,
  });
  if (q.isPending) return <ProductGridSkeleton />;
  if (q.isError) return <ErrorState message={t("error_title")} retryLabel={t("retry")}
    onRetry={() => q.refetch()} />;
  const items = q.data.pages.flatMap((p) => p.results);
  if (!items.length) {
    return <Empty icon="🔍" title={params.search ? t("no_results") : t("no_products")} />;
  }
  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        {items.map((p) => <ProductCard key={p.id} product={p} />)}
      </div>
      {q.hasNextPage && (
        <div className="mt-4 flex justify-center">
          <Button variant="soft" disabled={q.isFetchingNextPage}
            onClick={() => q.fetchNextPage()}>{t("load_more")}</Button>
        </div>
      )}
    </>
  );
}

export function HomePage() {
  const { api, business, t, money } = useSession();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const active = params.get("c") ?? "";
  const [search, setSearch] = useState("");
  const cats = useQuery({ queryKey: ["categories"], queryFn: api.categories });
  const { data: cart } = useCart();

  const chips = [
    { id: "", label: t("all") },
    { id: "offers", label: t("offers") },
    ...(cats.data ?? []).map((c) => ({ id: c.id, label: c.name })),
  ];
  const gridParams = active === "offers" ? { discounted: "true" }
    : active ? { category: active } : {};

  return (
    <Page>
      <section className="-mx-4 mb-4">
        <div className="relative h-36 overflow-hidden bg-accent/15">
          {business.cover && <img src={business.cover} alt="" className="h-full w-full
            object-cover" />}
          <div className="absolute inset-0 bg-gradient-to-t from-black/45 to-transparent" />
        </div>
        <div className="relative -mt-10 flex items-end gap-3 px-4">
          <div className="grid size-20 shrink-0 place-items-center overflow-hidden rounded-2xl
            border-4 border-bg2 bg-card text-3xl shadow-sm">
            {business.logo ? <img src={business.logo} alt="" className="h-full w-full
              object-cover" /> : "🍽"}
          </div>
          <div className="min-w-0 pb-1">
            <h1 className="truncate text-[21px] font-bold">{business.name}</h1>
            <div className="flex items-center gap-2 text-[13px]">
              <span className={cx("inline-flex items-center gap-1 font-semibold",
                business.is_open ? "text-success" : "text-danger")}>
                <span className={cx("size-2 rounded-full",
                  business.is_open ? "bg-success" : "bg-danger")} />
                {business.is_open ? t("open") : t("closed")}
              </span>
              {business.min_order_amount > 0 && (
                <span className="text-hint">· {t("min_order", {
                  v: money(business.min_order_amount) })}</span>
              )}
            </div>
          </div>
        </div>
        {!business.is_active && (
          <p className="mx-4 mt-3 rounded-xl bg-danger/10 p-3 text-[14px] text-danger">
            {t("unavailable_business")}</p>
        )}
      </section>

      <form role="search" onSubmit={(e) => {
        e.preventDefault();
        if (search.trim()) navigate(`/search?q=${encodeURIComponent(search.trim())}`);
      }}>
        <Input type="search" value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder={t("search_placeholder")} enterKeyHint="search"
          className="rounded-2xl bg-card" />
      </form>

      <div className="no-scrollbar -mx-4 my-4 flex gap-2 overflow-x-auto px-4">
        {chips.map((c) => (
          <button key={c.id || "all"} type="button"
            onClick={() => setParams(c.id ? { c: c.id } : {}, { replace: true })}
            className={cx("shrink-0 rounded-full px-4 py-2 text-[14px] font-semibold transition",
              active === c.id ? "bg-fg text-bg" : "bg-card text-fg")}>
            {c.label}
          </button>
        ))}
      </div>

      <ProductGrid params={gridParams} />

      {cart && cart.item_count > 0 && (
        <Link to="/cart" className="fixed inset-x-4 bottom-[calc(env(safe-area-inset-bottom)+68px)]
          z-20 mx-auto flex max-w-[calc(36rem-2rem)] items-center justify-between rounded-2xl
          bg-accent px-4 py-3.5 font-semibold text-on-accent shadow-lg animate-rise">
          <span className="tabular grid size-7 place-items-center rounded-full bg-white/25
            text-[13px]">{cart.item_count}</span>
          <span>{t("view_cart", { total: money(cart.subtotal) })}</span>
          <span aria-hidden className="rtl:rotate-180">→</span>
        </Link>
      )}
    </Page>
  );
}

export function SearchPage() {
  const { t } = useSession();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const q = params.get("q") ?? "";
  const [value, setValue] = useState(q);
  return (
    <Page title={t("search_placeholder").replace("...", "")}>
      <form role="search" className="mb-4" onSubmit={(e) => {
        e.preventDefault();
        navigate(`/search?q=${encodeURIComponent(value.trim())}`, { replace: true });
      }}>
        <Input type="search" autoFocus value={value} onChange={(e) => setValue(e.target.value)}
          placeholder={t("search_placeholder")} enterKeyHint="search" />
      </form>
      {q && <ProductGrid params={{ search: q }} />}
    </Page>
  );
}
