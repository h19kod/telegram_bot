import { useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";

import type { TKey } from "../lib/i18n";
import { useSession } from "../lib/session";
import { useLiveOrders } from "../lib/live";
import { cx, Select } from "./ui";

export const NAV: { to: string; key: TKey; icon: string; perm?: string }[] = [
  { to: "/", key: "overview", icon: "📊", perm: "reports.view" },
  { to: "/orders", key: "orders", icon: "🧾", perm: "orders.view" },
  { to: "/products", key: "products", icon: "🍔", perm: "catalog.view" },
  { to: "/categories", key: "categories", icon: "📂", perm: "catalog.view" },
  { to: "/discounts", key: "discounts", icon: "🏷️", perm: "catalog.edit_prices" },
  { to: "/customers", key: "customers", icon: "👥", perm: "customers.view" },
  { to: "/reviews", key: "reviews", icon: "⭐", perm: "orders.view" },
  { to: "/staff", key: "staff", icon: "🧑‍🍳", perm: "staff.manage" },
  { to: "/delivery", key: "delivery", icon: "🛵", perm: "delivery.manage" },
  { to: "/reports", key: "reports", icon: "📈", perm: "reports.view" },
  { to: "/settings", key: "settings", icon: "⚙️", perm: "settings.edit" },
  { to: "/telegram", key: "telegram", icon: "✈️", perm: "telegram.edit" },
  { to: "/subscription", key: "subscription", icon: "💳" },
  { to: "/support", key: "support", icon: "🛟", perm: "settings.edit" },
  { to: "/audit", key: "audit", icon: "📜", perm: "settings.edit" },
];

export function Shell() {
  const { t, user, memberships, membership, selectBusiness, can, logout, lang, setLang } = useSession();
  const [open, setOpen] = useState(false);
  const live = useLiveOrders();
  const name = (m: typeof membership) => (lang === "en" && m?.business_name_en) || m?.business_name_ar;
  const nav = NAV.filter((n) => !n.perm || can(n.perm));

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[250px_1fr]">
      <aside className={cx("fixed inset-y-0 start-0 z-40 w-[250px] border-e border-line bg-card transition-transform lg:sticky lg:top-0 lg:h-dvh",
        !open && "max-lg:ltr:-translate-x-full max-lg:rtl:translate-x-full")}>
        <div className="flex h-full flex-col">
          <div className="border-b border-line p-4">
            <p className="text-[12px] text-hint">{t("app")}</p>
            {memberships.length > 1 ? (
              <Select aria-label={t("choose_business")} className="mt-1 font-semibold"
                value={membership?.business_id} onChange={(e) => selectBusiness(e.target.value)}>
                {memberships.map((m) => <option key={m.business_id} value={m.business_id}>{name(m)}</option>)}
              </Select>
            ) : <p className="mt-0.5 truncate font-bold">{name(membership)}</p>}
            <p className="mt-1 text-[12px] text-hint">{membership?.role}</p>
          </div>
          <nav className="flex-1 overflow-y-auto p-2">
            {nav.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === "/"} onClick={() => setOpen(false)}
                className={({ isActive }) => cx("flex items-center gap-3 rounded-lg px-3 py-2 text-[14px]",
                  isActive ? "bg-accent/10 font-semibold text-accent" : "text-fg/80 hover:bg-bg2")}>
                <span aria-hidden>{n.icon}</span>{t(n.key)}
                {n.to === "/orders" && live.pending > 0 && (
                  <span className="tabular ms-auto rounded-full bg-accent px-1.5 text-[11px] font-bold text-on-accent">{live.pending}</span>
                )}
              </NavLink>
            ))}
            {user?.is_platform_admin && (
              <NavLink to="/platform" onClick={() => setOpen(false)}
                className={({ isActive }) => cx("mt-2 flex items-center gap-3 rounded-lg border-t border-line px-3 py-2 pt-3 text-[14px]",
                  isActive ? "font-semibold text-accent" : "text-fg/80 hover:bg-bg2")}>
                <span aria-hidden>🛡️</span>{t("platform")}</NavLink>
            )}
          </nav>
          <div className="space-y-1 border-t border-line p-2 text-[14px]">
            <NavLink to="/account" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-bg2">
              <span aria-hidden>👤</span><span className="truncate">{user?.full_name || user?.email}</span></NavLink>
            <button type="button" onClick={() => setLang(lang === "ar" ? "en" : "ar")}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2 hover:bg-bg2">
              <span aria-hidden>🌐</span>{lang === "ar" ? "English" : "العربية"}</button>
            <button type="button" onClick={logout}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-danger hover:bg-danger/8">
              <span aria-hidden>⎋</span>{t("logout")}</button>
          </div>
        </div>
      </aside>
      {open && <button aria-label="close menu" className="fixed inset-0 z-30 bg-black/30 lg:hidden" onClick={() => setOpen(false)} />}
      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-line bg-bg/90 px-4 py-3 backdrop-blur lg:hidden">
          <button type="button" aria-label="menu" onClick={() => setOpen(true)} className="rounded-lg border border-line px-2.5 py-1.5">☰</button>
          <span className="truncate font-semibold">{name(membership)}</span>
        </header>
        <main className="mx-auto max-w-7xl p-4 lg:p-6"><Outlet /></main>
      </div>
    </div>
  );
}

export function PageHeader({ title, actions, children }: { title: string; actions?: ReactNode;
  children?: ReactNode }) {
  return (
    <div className="mb-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-[22px] font-bold">{title}</h1>
        <div className="flex flex-wrap items-center gap-2">{actions}</div>
      </div>
      {children}
    </div>
  );
}
