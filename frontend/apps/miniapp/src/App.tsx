import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { ApiError } from "./api";
import { Button, Empty, Spinner } from "./components/ui";
import { translate } from "./i18n";
import { CartPage } from "./pages/Cart";
import { CategoriesPage, CategoryProductsPage } from "./pages/Categories";
import { CheckoutPage } from "./pages/Checkout";
import { HomePage, SearchPage } from "./pages/Home";
import { OrderDetailPage, OrderPlacedPage, OrdersPage } from "./pages/Orders";
import { ProductDetailPage } from "./pages/ProductDetail";
import { ProfilePage, SupportPage } from "./pages/Profile";
import { SessionProvider, useBoot } from "./session";
import { tg } from "./telegram";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
      refetchOnWindowFocus: false,
    },
  },
});

const fallbackLang = tg?.initDataUnsafe.user?.language_code?.startsWith("en") ? "en" : "ar";

export function App() {
  const [boot, retry] = useBoot();
  if (boot.state === "loading") {
    return <div className="grid min-h-dvh place-items-center text-accent"><Spinner
      className="size-8" /></div>;
  }
  if (boot.state === "no-telegram") {
    return <Empty icon="✈️" title={translate(fallbackLang, "open_in_telegram")}
      hint={translate(fallbackLang, "open_in_telegram_hint")} />;
  }
  if (boot.state === "error") {
    return <Empty icon="⚠️" title={boot.message || translate(fallbackLang, "error_title")}
      action={<Button variant="soft" onClick={retry}>{translate(fallbackLang, "retry")}
      </Button>} />;
  }
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider api={boot.api} business={boot.business} customer={boot.customer}>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/categories" element={<CategoriesPage />} />
            <Route path="/c/:id" element={<CategoryProductsPage />} />
            <Route path="/p/:id" element={<ProductDetailPage />} />
            <Route path="/cart" element={<CartPage />} />
            <Route path="/checkout" element={<CheckoutPage />} />
            <Route path="/placed/:id" element={<OrderPlacedPage />} />
            <Route path="/orders" element={<OrdersPage />} />
            <Route path="/orders/:id" element={<OrderDetailPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/support" element={<SupportPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </SessionProvider>
    </QueryClientProvider>
  );
}
