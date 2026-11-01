import { createContext, useCallback, useContext, useEffect, useRef, useState,
  type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode,
  type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

import { ApiError } from "../lib/api";
import { useSession } from "../lib/session";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

type Variant = "primary" | "secondary" | "ghost" | "danger";
export function Button({ variant = "primary", size = "md", className, ...p }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" }) {
  return <button {...p} className={cx(
    "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition",
    "disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
    size === "sm" ? "px-2.5 py-1.5 text-[13px]" : "px-4 py-2.5 text-[14px]",
    variant === "primary" && "bg-accent text-white hover:bg-accent/90",
    variant === "secondary" && "border border-line bg-card hover:bg-bg2",
    variant === "ghost" && "hover:bg-bg2",
    variant === "danger" && "bg-danger/10 text-danger hover:bg-danger/15",
    className)} />;
}

const field = "rounded-lg border border-line bg-card px-3 py-2 text-[14px] outline-none " +
  "placeholder:text-hint focus:border-accent focus:ring-2 focus:ring-accent/20 disabled:opacity-60";

/** Full width unless the caller sets an explicit width (w-*) or flex sizing. */
const width = (c?: string) => (c && /(^|\s)(w-|min-w-|flex-1)/.test(c) ? "" : "w-full");
export const Input = ({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) =>
  <input {...p} className={cx(field, width(className), className)} />;
export const Select = ({ className, ...p }: SelectHTMLAttributes<HTMLSelectElement>) =>
  <select {...p} className={cx(field, width(className), "pe-8", className)} />;
export const TextArea = ({ className, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement>) =>
  <textarea {...p} className={cx(field, "w-full min-h-20", className)} />;

export function Field({ label, error, hint, children, className }: { label: string;
  error?: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cx("block", className)}>
      <span className="mb-1 block text-[13px] font-medium text-fg/80">{label}</span>
      {children}
      {error ? <span role="alert" className="mt-1 block text-[12px] text-danger">{error}</span>
        : hint ? <span className="mt-1 block text-[12px] text-hint">{hint}</span> : null}
    </label>
  );
}

export function Toggle({ checked, onChange, label, disabled }: { checked: boolean;
  onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2.5 text-[14px]">
      <button type="button" role="switch" aria-checked={checked} disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cx("relative h-6 w-10 rounded-full transition disabled:opacity-50",
          checked ? "bg-accent" : "bg-line")}>
        <span className={cx("absolute top-0.5 size-5 rounded-full bg-white shadow transition-all",
          checked ? "start-[18px]" : "start-0.5")} />
      </button>
      {label}
    </label>
  );
}

export function Card({ title, actions, children, className }: { title?: ReactNode;
  actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-xl border border-line bg-card", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="font-semibold">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "success" |
  "warn" | "danger" | "info"; children: ReactNode }) {
  return <span className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-semibold",
    tone === "neutral" && "bg-bg2 text-fg/70", tone === "success" && "bg-success/12 text-success",
    tone === "warn" && "bg-warn/15 text-warn", tone === "danger" && "bg-danger/10 text-danger",
    tone === "info" && "bg-info/12 text-info")}>{children}</span>;
}

export function Spinner() {
  return <svg className="size-5 animate-spin text-accent" viewBox="0 0 24 24" fill="none" aria-hidden>
    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity=".2" strokeWidth="3" />
    <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
  </svg>;
}

export function Loading() {
  const { t } = useSession();
  return <div className="flex items-center justify-center gap-2 py-16 text-hint"><Spinner />{t("loading")}</div>;
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useSession();
  const msg = error instanceof ApiError ? (error.status === 403 ? t("permission_denied")
    : error.message) : t("error");
  return <div role="alert" className="flex items-center justify-between rounded-lg bg-danger/8 p-4 text-danger">
    <span>{msg}</span>{onRetry && <Button variant="secondary" size="sm" onClick={onRetry}>{t("retry")}</Button>}
  </div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="py-12 text-center text-hint">{children}</div>;
}

export function Modal({ open, onClose, title, children, footer, wide }: { open: boolean;
  onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} onCancel={onClose}
      className={cx("m-auto max-h-[90dvh] w-[calc(100%-2rem)] rounded-xl border border-line bg-card p-0 text-fg shadow-2xl backdrop:bg-black/40",
        wide ? "max-w-3xl" : "max-w-lg")}>
      {open && <>
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-card px-5 py-3.5">
          <h2 className="text-[16px] font-semibold">{title}</h2>
          <button type="button" onClick={onClose} aria-label="close" className="rounded-md p-1 text-hint hover:bg-bg2">✕</button>
        </header>
        <div className="p-5">{children}</div>
        {footer && <footer className="sticky bottom-0 flex justify-end gap-2 border-t border-line bg-card px-5 py-3">{footer}</footer>}
      </>}
    </dialog>
  );
}

// ---- Confirm dialog & toasts --------------------------------------------------------------

interface ConfirmOpts { title: string; body?: string; danger?: boolean; input?: string }
interface UiCtx {
  toast: (msg: string, tone?: "success" | "error") => void;
  confirm: (o: ConfirmOpts) => Promise<string | false>;
}
const Ui = createContext<UiCtx | null>(null);
export const useUi = () => useContext(Ui)!;

export function UiProvider({ children }: { children: ReactNode }) {
  const { t } = useSession();
  const [toasts, setToasts] = useState<{ id: number; msg: string; tone: string }[]>([]);
  const [dlg, setDlg] = useState<(ConfirmOpts & { resolve: (v: string | false) => void }) | null>(null);
  const [text, setText] = useState("");
  const toast = useCallback((msg: string, tone: "success" | "error" = "success") => {
    const id = Date.now() + Math.random();
    setToasts((x) => [...x, { id, msg, tone }]);
    setTimeout(() => setToasts((x) => x.filter((y) => y.id !== id)), 4000);
  }, []);
  const confirm = useCallback((o: ConfirmOpts) => new Promise<string | false>((resolve) => {
    setText("");
    setDlg({ ...o, resolve });
  }), []);
  const close = (v: string | false) => { dlg?.resolve(v); setDlg(null); };
  return (
    <Ui.Provider value={{ toast, confirm }}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 start-4 z-[100] flex flex-col gap-2">
        {toasts.map((x) => (
          <div key={x.id} className={cx("pointer-events-auto rounded-lg px-4 py-3 text-[14px] font-medium text-white shadow-lg",
            x.tone === "error" ? "bg-danger" : "bg-fg text-bg")}>{x.msg}</div>
        ))}
      </div>
      <Modal open={Boolean(dlg)} onClose={() => close(false)} title={dlg?.title ?? ""}
        footer={<>
          <Button variant="secondary" onClick={() => close(false)}>{t("cancel")}</Button>
          <Button variant={dlg?.danger ? "danger" : "primary"}
            disabled={Boolean(dlg?.input) && text.trim().length < 2}
            onClick={() => close(dlg?.input ? text.trim() : "ok")}>{t("confirm")}</Button>
        </>}>
        {dlg?.body && <p className="text-[14px] text-fg/80">{dlg.body}</p>}
        {dlg?.input && <Field label={dlg.input} className="mt-3">
          <Input autoFocus value={text} onChange={(e) => setText(e.target.value)} maxLength={300} />
        </Field>}
      </Modal>
    </Ui.Provider>
  );
}

export function errorMessage(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.message : fallback;
}

export function StatCard({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-card p-4">
      <p className="text-[13px] text-hint">{label}</p>
      <p className="tabular mt-1 text-[24px] leading-tight font-bold">{value}</p>
      {hint && <p className="mt-1 text-[12px] text-hint">{hint}</p>}
    </div>
  );
}

export function Table({ head, children, empty }: { head: ReactNode[]; children: ReactNode;
  empty?: boolean }) {
  const { t } = useSession();
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-card">
      <table className="w-full min-w-[640px] text-[14px]">
        <thead className="bg-bg2/60 text-[12px] text-hint">
          <tr>{head.map((h, i) => <th key={i} scope="col" className="px-4 py-2.5 text-start font-semibold">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
      {empty && <Empty>{t("no_data")}</Empty>}
    </div>
  );
}

export function Pager({ page, count, pageSize = 25, onPage }: { page: number; count: number;
  pageSize?: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="mt-3 flex items-center justify-center gap-2 text-[13px]" dir="ltr">
      <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>‹</Button>
      <span className="tabular">{page} / {pages}</span>
      <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>›</Button>
    </div>
  );
}
