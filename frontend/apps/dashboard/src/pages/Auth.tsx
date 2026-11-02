import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { Button, errorMessage, Field, Input, Select } from "../components/ui";
import { post, type User } from "../lib/api";
import { useSession } from "../lib/session";

function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  const { lang, setLang } = useSession();
  return (
    <div className="grid min-h-dvh place-items-center p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 grid size-12 place-items-center rounded-xl bg-accent text-2xl text-on-accent">🛒</div>
          <h1 className="text-[22px] font-bold">{title}</h1>
        </div>
        <div className="rounded-xl border border-line bg-card p-6 shadow-sm">{children}</div>
        <button type="button" className="mx-auto mt-4 block text-[13px] text-hint"
          onClick={() => setLang(lang === "ar" ? "en" : "ar")}>{lang === "ar" ? "English" : "العربية"}</button>
      </div>
    </div>
  );
}

export function LoginPage() {
  const { t, loginWith } = useSession();
  const [identifier, setId] = useState("");
  const [password, setPw] = useState("");
  const [otp, setOtp] = useState("");
  const [needOtp, setNeedOtp] = useState(false);
  const m = useMutation({
    mutationFn: () => post<{ access: string; user: User }>("/auth/login", { identifier, password, otp }),
    onSuccess: (r) => loginWith(r.access, r.user),
    onError: (e: unknown) => { if ((e as { code?: string }).code === "otp_required") setNeedOtp(true); },
  });
  return (
    <AuthCard title={t("login")}>
      <form className="space-y-4" onSubmit={(e: FormEvent) => { e.preventDefault(); m.mutate(); }}>
        <Field label={t("email_or_phone")}><Input value={identifier} onChange={(e) => setId(e.target.value)} autoComplete="username" required dir="ltr" /></Field>
        <Field label={t("password")}><Input type="password" value={password} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" required /></Field>
        {needOtp && <Field label={t("otp")}><Input value={otp} onChange={(e) => setOtp(e.target.value)} inputMode="numeric" autoComplete="one-time-code" autoFocus dir="ltr" /></Field>}
        {m.isError && !(needOtp && !otp) && <p role="alert" className="text-[13px] text-danger">{errorMessage(m.error, t("error"))}</p>}
        <Button className="w-full" disabled={m.isPending}>{t("login")}</Button>
      </form>
      <div className="mt-4 flex justify-between text-[13px]">
        <Link to="/forgot" className="text-info">{t("forgot")}</Link>
        <Link to="/register" className="text-info">{t("register")}</Link>
      </div>
    </AuthCard>
  );
}

export function RegisterPage() {
  const { t, loginWith, lang } = useSession();
  const [f, setF] = useState({ full_name: "", email: "", password: "" });
  const m = useMutation({
    mutationFn: () => post<{ access: string; user: User }>("/auth/register", { ...f, language: lang }),
    onSuccess: (r) => loginWith(r.access, r.user),
  });
  const err = m.error && "fieldErrors" in (m.error as object) ? (m.error as never as { fieldErrors(): Record<string, string> }).fieldErrors() : {};
  return (
    <AuthCard title={t("register")}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <Field label={t("full_name")}><Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} required /></Field>
        <Field label={t("email")} error={err.email}><Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} required dir="ltr" /></Field>
        <Field label={t("password")} error={err.password}><Input type="password" minLength={10} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} required autoComplete="new-password" /></Field>
        {m.isError && !Object.keys(err).length && <p role="alert" className="text-[13px] text-danger">{errorMessage(m.error, t("error"))}</p>}
        <Button className="w-full" disabled={m.isPending}>{t("register")}</Button>
      </form>
      <p className="mt-4 text-center text-[13px]">{t("have_account")} <Link to="/" className="text-info">{t("login")}</Link></p>
    </AuthCard>
  );
}

export function ForgotPage() {
  const { t } = useSession();
  const [email, setEmail] = useState("");
  const m = useMutation({ mutationFn: () => post("/auth/password/reset", { email }) });
  return (
    <AuthCard title={t("forgot")}>
      {m.isSuccess ? <p className="text-[14px]">{t("reset_sent")}</p> : (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
          <Field label={t("email")}><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required dir="ltr" /></Field>
          <Button className="w-full" disabled={m.isPending}>{t("send_reset")}</Button>
        </form>
      )}
      <Link to="/" className="mt-4 block text-center text-[13px] text-info">{t("login")}</Link>
    </AuthCard>
  );
}

export function ResetPasswordPage() {
  const { t } = useSession();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [pw, setPw] = useState("");
  const m = useMutation({
    mutationFn: () => post("/auth/password/reset/confirm", { uid: params.get("uid"), token: params.get("token"), new_password: pw }),
    onSuccess: () => setTimeout(() => navigate("/"), 1200),
  });
  return (
    <AuthCard title={t("new_password")}>
      {m.isSuccess ? <p>{t("password_changed")}</p> : (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
          <Field label={t("new_password")}><Input type="password" minLength={10} value={pw} onChange={(e) => setPw(e.target.value)} required autoComplete="new-password" /></Field>
          {m.isError && <p role="alert" className="text-[13px] text-danger">{errorMessage(m.error, t("error"))}</p>}
          <Button className="w-full" disabled={m.isPending}>{t("save")}</Button>
        </form>
      )}
    </AuthCard>
  );
}

const TYPES = ["restaurant", "cafe", "bakery", "grocery", "pharmacy", "retail", "other"];

export function OnboardingPage() {
  const { t, reload, logout } = useSession();
  const [f, setF] = useState({ name_ar: "", name_en: "", slug: "", business_type: "restaurant" });
  const m = useMutation({ mutationFn: () => post("/businesses", f), onSuccess: () => reload() });
  const err = (m.error as { fieldErrors?: () => Record<string, string> } | null)?.fieldErrors?.() ?? {};
  return (
    <AuthCard title={t("create_business")}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <Field label={t("business_name")}><Input value={f.name_ar} onChange={(e) => setF({ ...f, name_ar: e.target.value })} required /></Field>
        <Field label={t("business_name_en")}><Input value={f.name_en} onChange={(e) => setF({ ...f, name_en: e.target.value })} dir="ltr" /></Field>
        <Field label={t("slug")} error={err.slug} hint="my_restaurant"><Input value={f.slug} pattern="[a-z0-9_]{3,50}" onChange={(e) => setF({ ...f, slug: e.target.value.toLowerCase() })} required dir="ltr" /></Field>
        <Field label={t("business_type")}><Select value={f.business_type} onChange={(e) => setF({ ...f, business_type: e.target.value })}>{TYPES.map((x) => <option key={x}>{x}</option>)}</Select></Field>
        {m.isError && !err.slug && <p role="alert" className="text-[13px] text-danger">{errorMessage(m.error, t("error"))}</p>}
        <Button className="w-full" disabled={m.isPending}>{t("create")}</Button>
      </form>
      <button type="button" onClick={logout} className="mt-4 block w-full text-center text-[13px] text-hint">{t("logout")}</button>
    </AuthCard>
  );
}

export function AcceptInvitePage() {
  const { token = "" } = useParams();
  const { t, reload, user } = useSession();
  const navigate = useNavigate();
  const m = useMutation({ mutationFn: () => post(`/auth/invitations/${token}/accept`), onSuccess: async () => { await reload(); navigate("/"); } });
  return (
    <AuthCard title={t("accept_invite")}>
      <p className="mb-4 text-[14px] text-hint">{user?.email}</p>
      {m.isError && <p role="alert" className="mb-3 text-[13px] text-danger">{errorMessage(m.error, t("error"))}</p>}
      <Button className="w-full" disabled={m.isPending} onClick={() => m.mutate()}>{t("accept_invite")}</Button>
    </AuthCard>
  );
}
