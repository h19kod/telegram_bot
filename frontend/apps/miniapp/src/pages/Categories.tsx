import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { Page } from "../components/Layout";
import { Empty, ErrorState, Skeleton } from "../components/ui";
import { useSession } from "../session";
import { ProductGrid } from "./Home";

export function CategoriesPage() {
  const { api, t } = useSession();
  const q = useQuery({ queryKey: ["categories"], queryFn: api.categories });
  return (
    <Page title={t("categories")}>
      {q.isPending ? <div className="grid grid-cols-2 gap-3">{[1, 2, 3, 4].map((i) =>
        <Skeleton key={i} className="aspect-[4/3]" />)}</div>
        : q.isError ? <ErrorState message={t("error_title")} retryLabel={t("retry")}
          onRetry={() => q.refetch()} />
        : !q.data.length ? <Empty icon="📂" title={t("no_products")} />
        : (
          <div className="grid grid-cols-2 gap-3">
            {q.data.map((c) => (
              <Link key={c.id} to={`/c/${c.id}`} className="animate-rise relative aspect-[4/3]
                overflow-hidden rounded-card bg-card">
                {c.image ? <img src={c.image} alt="" className="h-full w-full object-cover" />
                  : <div className="grid h-full place-items-center text-4xl">🍽</div>}
                <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70
                  to-transparent p-3 pt-8 font-semibold text-white">{c.name}</span>
              </Link>
            ))}
          </div>
        )}
    </Page>
  );
}

export function CategoryProductsPage() {
  const { id = "" } = useParams();
  const { api, t } = useSession();
  const cats = useQuery({ queryKey: ["categories"], queryFn: api.categories });
  const name = cats.data?.find((c) => c.id === id)?.name ?? t("menu");
  return <Page title={name}><ProductGrid params={{ category: id }} /></Page>;
}
