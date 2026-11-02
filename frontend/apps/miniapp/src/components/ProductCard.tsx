import { Link } from "react-router-dom";

import type { Product } from "../api";
import { useCartMutations } from "../hooks/queries";
import { useSession } from "../session";
import { haptic } from "../telegram";
import { cx, Spinner } from "./ui";

export function Price({ price, compareAt, className }: { price: number;
  compareAt?: number | null; className?: string }) {
  const { money } = useSession();
  return (
    <span className={cx("tabular inline-flex flex-wrap items-baseline gap-x-1.5", className)}>
      <span className="font-bold">{money(price)}</span>
      {compareAt ? <s className="text-[12px] text-hint">{money(compareAt)}</s> : null}
    </span>
  );
}

export function ProductImage({ product, className }: {
  product: Pick<Product, "images" | "name">;
  className?: string;
}) {
  const img = product.images[0];
  const src = img?.thumbnail || img?.url;
  return src ? (
    <img src={src} alt={product.name} loading="lazy" decoding="async"
      className={cx("h-full w-full object-cover", className)} />
  ) : (
    <div className={cx("grid h-full w-full place-items-center bg-bg2 text-4xl", className)}
      aria-hidden>🍽</div>
  );
}

export function ProductCard({ product }: { product: Product }) {
  const { t } = useSession();
  const { add } = useCartMutations();
  const quickAdd = product.is_available && !product.has_options;
  return (
    <Link to={`/p/${product.id}`} onClick={() => haptic.select()}
      className="animate-rise group flex flex-col overflow-hidden rounded-card bg-card">
      <div className="relative aspect-[4/3] overflow-hidden">
        <ProductImage product={product}
          className={cx("transition duration-300 group-active:scale-105",
            !product.is_available && "opacity-40 grayscale")} />
        {product.discount_percent ? (
          <span className="absolute start-2 top-2 rounded-full bg-danger px-2 py-0.5
            text-[11px] font-bold text-white">-{product.discount_percent}%</span>
        ) : null}
        {!product.is_available && (
          <span className="absolute inset-x-2 bottom-2 rounded-lg bg-black/60 py-1 text-center
            text-[12px] font-semibold text-white">{t("unavailable")}</span>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-1 p-3">
        <h3 className="line-clamp-2 text-[14px] leading-snug font-semibold">{product.name}</h3>
        <div className="mt-auto flex items-center justify-between gap-2 pt-1">
          <Price price={product.price} compareAt={product.compare_at_price}
            className="text-[14px]" />
          {product.is_available && (
            <button type="button" aria-label={t("add")}
              disabled={add.isPending}
              onClick={(e) => {
                if (!quickAdd) return; // has options → open the product page
                e.preventDefault();
                add.mutate({ productId: product.id, optionIds: [], quantity: 1 });
              }}
              className="grid size-8 shrink-0 place-items-center rounded-full bg-accent
                text-lg font-bold text-on-accent shadow-sm active:scale-90">
              {add.isPending ? <Spinner className="size-4" /> : "+"}
            </button>
          )}
        </div>
      </div>
    </Link>
  );
}

export function ProductGridSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3">
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="overflow-hidden rounded-card bg-card">
          <div className="skeleton aspect-[4/3]" />
          <div className="space-y-2 p-3">
            <div className="skeleton h-4 w-3/4 rounded" />
            <div className="skeleton h-4 w-1/3 rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}
