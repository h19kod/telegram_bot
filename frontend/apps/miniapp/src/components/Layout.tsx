import type { ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import { useBackButton } from "../hooks/telegram";
import { useCart } from "../hooks/queries";
import { useSession } from "../session";
import { insideTelegram } from "../telegram";
import { cx } from "./ui";

const ROOTS = ["/", "/orders", "/cart", "/profile"];

export function Page({ title, children, actions, bottomPad = true }: { title?: string;
  children: ReactNode; actions?: ReactNode; bottomPad?: boolean }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const isRoot = ROOTS.includes(pathname);
  useBackButton(!isRoot);
  return (
    <div className={cx("mx-auto min-h-dvh max-w-xl", bottomPad && "pb-28")}>
      {title && (
        <header className="sticky top-0 z-20 flex items-center gap-2 bg-bg2/85 px-4 py-3
          backdrop-blur-md">
          {!isRoot && !insideTelegram && (
            <button type="button" onClick={() => navigate(-1)} aria-label="back"
              className="grid size-9 place-items-center rounded-full bg-card text-lg
              rtl:rotate-180">←</button>
          )}
          <h1 className="flex-1 truncate text-[19px] font-bold">{title}</h1>
          {actions}
        </header>
      )}
      <main className="px-4">{children}</main>
      {isRoot && <TabBar />}
    </div>
  );
}

function TabBar() {
  const { t } = useSession();
  const { data: cart } = useCart();
  const tabs = [
    { to: "/", icon: "🏠", label: t("home") },
    { to: "/orders", icon: "📦", label: t("my_orders") },
    { to: "/cart", icon: "🛒", label: t("cart"), badge: cart?.item_count },
    { to: "/profile", icon: "👤", label: t("profile") },
  ];
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-card/95
      pb-[env(safe-area-inset-bottom)] backdrop-blur-md">
      <div className="mx-auto grid max-w-xl grid-cols-4">
        {tabs.map((tab) => (
          <NavLink key={tab.to} to={tab.to} end
            className={({ isActive }) => cx("relative flex flex-col items-center gap-0.5 py-2.5",
              "text-[11px] font-medium", isActive ? "text-accent" : "text-hint")}>
            <span className="text-[20px] leading-none" aria-hidden>{tab.icon}</span>
            {tab.label}
            {tab.badge ? (
              <span className="tabular absolute top-1 start-1/2 ms-2 min-w-5 rounded-full
                bg-accent px-1 text-[11px] leading-5 font-bold text-on-accent">{tab.badge}</span>
            ) : null}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}

/** Fallback action bar for browser dev mode (inside Telegram the MainButton is used). */
export function ActionBar({ children }: { children: ReactNode }) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-card/95 p-3
      pb-[calc(env(safe-area-inset-bottom)+12px)] backdrop-blur-md">
      <div className="mx-auto max-w-xl">{children}</div>
    </div>
  );
}
