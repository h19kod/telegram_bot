import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode,
  TextareaHTMLAttributes } from "react";

export function cx(...c: (string | false | null | undefined)[]): string {
  return c.filter(Boolean).join(" ");
}

export function Button({ variant = "primary", className, ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" | "soft" }) {
  return (
    <button
      {...props}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-2xl px-4 py-3 text-[15px]",
        "font-semibold transition active:scale-[.98] disabled:opacity-50 disabled:active:scale-100",
        variant === "primary" && "bg-accent text-on-accent shadow-sm",
        variant === "soft" && "bg-accent/10 text-accent",
        variant === "ghost" && "text-fg hover:bg-line",
        variant === "danger" && "bg-danger/10 text-danger",
        className,
      )}
    />
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("rounded-card bg-card", className)}>{children}</div>;
}

export function Field({ label, error, hint, children }: { label: string; error?: string;
  hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-medium text-hint">{label}</span>
      {children}
      {error ? <span role="alert" className="mt-1 block text-[13px] text-danger">{error}</span>
        : hint ? <span className="mt-1 block text-[12px] text-hint">{hint}</span> : null}
    </label>
  );
}

const inputCls = "w-full rounded-xl border border-line bg-bg px-3.5 py-3 text-[15px] " +
  "text-fg outline-none placeholder:text-hint focus:border-accent";

export function Input(props: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  const { invalid, className, ...rest } = props;
  return <input {...rest} aria-invalid={invalid || undefined}
    className={cx(inputCls, invalid && "border-danger", className)} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx(inputCls, "min-h-24 resize-none", props.className)} />;
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cx("size-5 animate-spin", className)} viewBox="0 0 24 24" fill="none"
      aria-hidden>
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity=".2" strokeWidth="3" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3"
        strokeLinecap="round" />
    </svg>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton rounded-xl", className)} />;
}

export function Empty({ icon, title, hint, action }: { icon: string; title: string;
  hint?: string; action?: ReactNode }) {
  return (
    <div className="animate-rise flex flex-col items-center px-8 py-16 text-center">
      <div className="mb-4 grid size-20 place-items-center rounded-full bg-card text-4xl">
        {icon}
      </div>
      <p className="text-[17px] font-semibold">{title}</p>
      {hint && <p className="mt-1 text-[14px] text-hint">{hint}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry, retryLabel }: { message: string;
  onRetry?: () => void; retryLabel: string }) {
  return (
    <Empty icon="⚠️" title={message}
      action={onRetry && <Button variant="soft" onClick={onRetry}>{retryLabel}</Button>} />
  );
}

export function Stepper({ value, onChange, min = 1, max = 99, size = "md", busy }: {
  value: number; onChange: (v: number) => void; min?: number; max?: number;
  size?: "sm" | "md"; busy?: boolean }) {
  const btn = cx("grid place-items-center rounded-full bg-bg2 font-bold text-fg transition",
    "active:scale-90 disabled:opacity-40", size === "sm" ? "size-8 text-lg" : "size-10 text-xl");
  return (
    <div className="inline-flex items-center gap-3" dir="ltr">
      <button type="button" className={btn} aria-label="-" disabled={busy || value <= min}
        onClick={() => onChange(value - 1)}>−</button>
      <span className={cx("tabular min-w-6 text-center font-semibold",
        size === "sm" ? "text-[15px]" : "text-[17px]")}>{value}</span>
      <button type="button" className={btn} aria-label="+" disabled={busy || value >= max}
        onClick={() => onChange(value + 1)}>+</button>
    </div>
  );
}

export function Segmented<T extends string>({ value, options, onChange }: { value: T;
  options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="grid auto-cols-fr grid-flow-col gap-1 rounded-2xl bg-bg2 p-1">
      {options.map((o) => (
        <button key={o.value} type="button" onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          className={cx("rounded-xl px-3 py-2.5 text-[14px] font-semibold transition",
            value === o.value ? "bg-card text-fg shadow-sm" : "text-hint")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
