import type { Lang } from "@sop/shared";
import { formatMoney } from "@sop/shared";
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useState,
  type ReactNode } from "react";

import { StoreApi, type BusinessInfo, type Customer } from "./api";
import { translate, type TKey } from "./i18n";
import { getBusinessSlug, getInitData, tg } from "./telegram";

interface Session {
  api: StoreApi;
  business: BusinessInfo;
  customer: Customer;
  lang: Lang;
  setLang: (l: Lang) => void;
  setCustomer: (c: Customer) => void;
  t: (key: TKey, vars?: Record<string, string | number>) => string;
  money: (amount: number) => string;
}

const Ctx = createContext<Session | null>(null);

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession outside SessionProvider");
  return s;
}

type Boot =
  | { state: "loading" }
  | { state: "no-telegram" }
  | { state: "error"; message: string }
  | { state: "ready"; api: StoreApi; business: BusinessInfo; customer: Customer };

function initialLang(initData: string): Lang {
  // Prefer the Telegram user's language (from initData, also in browser dev mode).
  let code = tg?.initDataUnsafe.user?.language_code;
  if (!code) {
    try {
      const user = JSON.parse(new URLSearchParams(initData).get("user") ?? "{}");
      code = user.language_code;
    } catch {
      code = undefined;
    }
  }
  return code?.startsWith("en") ? "en" : "ar";
}

export function useBoot(): [Boot, () => void] {
  const [boot, setBoot] = useState<Boot>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const initData = getInitData();
    const slug = getBusinessSlug();
    if (!initData || !slug) {
      setBoot({ state: "no-telegram" });
      return;
    }
    const api = new StoreApi(slug, initData);
    api.lang = initialLang(initData);
    applyDocumentLang(api.lang); // before any content renders: no RTL↔LTR flip (layout shift)
    api
      .openSession()
      .then(async ({ business, customer }) => {
        if (customer.language !== api.lang) {
          api.lang = customer.language; // saved preference wins; re-localise business info
          applyDocumentLang(api.lang);
          business = await api.info();
        }
        setBoot({ state: "ready", api, business, customer });
      })
      .catch((e: Error) => setBoot({ state: "error", message: e.message }));
  }, [attempt]);
  return [boot, () => setAttempt((n) => n + 1)];
}

function applyDocumentLang(lang: Lang): void {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
}

export function SessionProvider(props: { api: StoreApi; business: BusinessInfo;
  customer: Customer; children: ReactNode }) {
  const [customer, setCustomer] = useState(props.customer);
  const [lang, setLangState] = useState<Lang>(props.customer.language);

  useLayoutEffect(() => {
    applyDocumentLang(lang);
    document.title = props.business.name;
    props.api.lang = lang;
  }, [lang, props.api, props.business.name]);

  const setLang = useCallback((l: Lang) => setLangState(l), []);
  const value = useMemo<Session>(() => ({
    api: props.api,
    business: props.business,
    customer,
    lang,
    setLang,
    setCustomer,
    t: (key, vars) => translate(lang, key, vars),
    money: (amount) => formatMoney(amount, props.business.currency, lang),
  }), [props.api, props.business, customer, lang, setLang]);
  return <Ctx.Provider value={value}>{props.children}</Ctx.Provider>;
}
