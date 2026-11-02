import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { NAV, Shell } from "./components/Shell";
import { Loading, UiProvider } from "./components/ui";
import { ApiError } from "./lib/api";
import { LiveProvider } from "./lib/live";
import { SessionProvider, useSession } from "./lib/session";
import { AcceptInvitePage, ForgotPage, LoginPage, OnboardingPage, RegisterPage,
  ResetPasswordPage } from "./pages/Auth";
import { CategoriesPage, DiscountsPage, ProductsPage } from "./pages/Catalog";
import { OrdersPage } from "./pages/Orders";
import { OverviewPage } from "./pages/Overview";
import { CustomersPage, DeliveryPage, StaffPage } from "./pages/People";
import { AssistantPage } from "./pages/Assistant";
import { ReviewsPage } from "./pages/Reviews";
import { PlatformPage } from "./pages/Platform";
import { AccountPage, AuditPage, ReportsPage, SettingsPage, SubscriptionPage, SupportPage,
  TelegramPage } from "./pages/Settings";

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, refetchOnWindowFocus: false,
    retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 2 } },
});

function Guard({ perm, children }: { perm?: string; children: ReactNode }) {
  const { can, t } = useSession();
  if (perm && !can(perm)) return <div className="py-20 text-center text-hint">{t("permission_denied")}</div>;
  return <>{children}</>;
}

function Home() {
  const { can } = useSession();
  if (can("reports.view")) return <OverviewPage />;
  const first = NAV.find((n) => n.perm && can(n.perm));
  return <Navigate to={first?.to ?? "/account"} replace />;
}

function Routed() {
  const { ready, user, memberships } = useSession();
  if (!ready) return <Loading />;
  if (!user) {
    return (
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/forgot" element={<ForgotPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="*" element={<LoginPage />} />
      </Routes>
    );
  }
  if (!memberships.length) {
    return (
      <Routes>
        <Route path="/invite/:token" element={<AcceptInvitePage />} />
        {user.is_platform_admin && <Route path="/platform/*" element={<div className="p-6"><PlatformPage /></div>} />}
        <Route path="*" element={user.is_platform_admin ? <Navigate to="/platform" replace /> : <OnboardingPage />} />
      </Routes>
    );
  }
  const p = (perm: string | undefined, el: ReactNode) => <Guard perm={perm}>{el}</Guard>;
  return (
    <LiveProvider>
      <Routes>
        <Route path="/invite/:token" element={<AcceptInvitePage />} />
        <Route element={<Shell />}>
          <Route index element={<Home />} />
          <Route path="orders" element={p("orders.view", <OrdersPage />)} />
          <Route path="products" element={p("catalog.view", <ProductsPage />)} />
          <Route path="categories" element={p("catalog.view", <CategoriesPage />)} />
          <Route path="discounts" element={p("catalog.edit_prices", <DiscountsPage />)} />
          <Route path="customers" element={p("customers.view", <CustomersPage />)} />
          <Route path="reviews" element={p("orders.view", <ReviewsPage />)} />
          <Route path="assistant" element={p("ai.manage", <AssistantPage />)} />
          <Route path="staff" element={p("staff.manage", <StaffPage />)} />
          <Route path="delivery" element={p("delivery.manage", <DeliveryPage />)} />
          <Route path="reports" element={p("reports.view", <ReportsPage />)} />
          <Route path="settings" element={p("settings.edit", <SettingsPage />)} />
          <Route path="telegram" element={p("telegram.edit", <TelegramPage />)} />
          <Route path="subscription" element={<SubscriptionPage />} />
          <Route path="support" element={p("settings.edit", <SupportPage />)} />
          <Route path="audit" element={p("settings.edit", <AuditPage />)} />
          <Route path="account" element={<AccountPage />} />
          {user.is_platform_admin && <Route path="platform/*" element={<PlatformPage />} />}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </LiveProvider>
  );
}

export function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <SessionProvider>
          <UiProvider><Routed /></UiProvider>
        </SessionProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
