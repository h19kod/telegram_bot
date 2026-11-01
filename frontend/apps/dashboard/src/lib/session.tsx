import { formatMoney, type Lang } from "@sop/shared";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState,
  type ReactNode } from "react";

import { get, onSessionExpired, post, refreshSession, setAccessToken, setLang as setApiLang,
  type Membership, type User } from "./api";
import { tr, type TKey } from "./i18n";

interface Session {
  user: User | null;
  memberships: Membership[];
  membership: Membership | null;
  businessId: string | null;
  selectBusiness: (id: string) => void;
  can: (perm: string) => boolean;
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (k: TKey, vars?: Record<string, string | number>) => string;
  money: (amount: number, currency?: string) => string;
  loginWith: (access: string, user: User) => Promise<void>;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
  ready: boolean;
}

const Ctx = createContext<Session | null>(null);
export const useSession = () => {
  const s = useContext(Ctx);
  if (!s) throw new Error("no session");
  return s;
};

const BIZ_KEY = "sop.dashboard.business";
const LANG_KEY = "sop.dashboard.lang";

function stored(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
function store(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch { /* private mode */ }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [lang, setLangState] = useState<Lang>((stored(LANG_KEY) as Lang) || "ar");
  const [businessId, setBusinessId] = useState<string | null>(stored(BIZ_KEY));

  const memberships = useQuery({
    queryKey: ["memberships", user?.id],
    queryFn: () => get<Membership[]>("/auth/me/memberships"),
    enabled: Boolean(user),
  });

  const reload = useCallback(async () => {
    setUser(await get<User>("/auth/me"));
    await qc.invalidateQueries({ queryKey: ["memberships"] });
  }, [qc]);

  useEffect(() => {
    onSessionExpired(() => { setAccessToken(null); setUser(null); });
    refreshSession().then(async (ok) => {
      if (ok) {
        try { setUser(await get<User>("/auth/me")); } catch { /* stay logged out */ }
      }
      setReady(true);
    });
  }, []);

  useEffect(() => {
    setApiLang(lang);
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    store(LANG_KEY, lang);
  }, [lang]);

  const list = memberships.data ?? [];
  const membership = list.find((m) => m.business_id === businessId) ?? list[0] ?? null;

  const value = useMemo<Session>(() => ({
    user,
    memberships: list,
    membership,
    businessId: membership?.business_id ?? null,
    selectBusiness: (id) => { setBusinessId(id); store(BIZ_KEY, id); qc.removeQueries({
      predicate: (q) => q.queryKey[0] === "b" }); },
    can: (perm) => Boolean(membership?.permissions.includes(perm)),
    lang,
    setLang: setLangState,
    t: (k, vars) => tr(lang, k, vars),
    money: (amount, currency = "IQD") => formatMoney(amount, currency, lang),
    loginWith: async (access, u) => {
      setAccessToken(access);
      setUser(u);
      if (u.language) setLangState(u.language);
    },
    logout: async () => {
      try { await post("/auth/logout"); } finally {
        setAccessToken(null);
        setUser(null);
        qc.clear();
      }
    },
    reload,
    ready: ready && (!user || memberships.isFetched),
  }), [user, list, membership, lang, qc, reload, ready, memberships.isFetched]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Key helper: all business-scoped queries start with ["b", businessId, ...]. */
export function useBizKey() {
  const { businessId } = useSession();
  return (...parts: unknown[]) => ["b", businessId, ...parts];
}

export function useBizPath() {
  const { businessId } = useSession();
  return (path: string) => `/b/${businessId}${path}`;
}
