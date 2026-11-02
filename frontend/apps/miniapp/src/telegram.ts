/** Thin typed wrapper over the official telegram-web-app.js (window.Telegram.WebApp). */

type Haptic = "light" | "medium" | "heavy" | "rigid" | "soft";
type Notify = "error" | "success" | "warning";

interface MainButton {
  setParams(p: { text?: string; color?: string; text_color?: string; is_active?: boolean;
    is_visible?: boolean }): void;
  onClick(cb: () => void): void;
  offClick(cb: () => void): void;
  show(): void;
  hide(): void;
  showProgress(leaveActive?: boolean): void;
  hideProgress(): void;
}

interface WebApp {
  initData: string;
  initDataUnsafe: { user?: { id: number; language_code?: string; first_name?: string };
    start_param?: string };
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  platform: string;
  version: string;
  ready(): void;
  expand(): void;
  isVersionAtLeast(v: string): boolean;
  onEvent(e: string, cb: () => void): void;
  offEvent(e: string, cb: () => void): void;
  MainButton: MainButton;
  BackButton: { show(): void; hide(): void; onClick(cb: () => void): void;
    offClick(cb: () => void): void };
  HapticFeedback: { impactOccurred(s: Haptic): void; notificationOccurred(t: Notify): void;
    selectionChanged(): void };
  showConfirm(message: string, cb: (ok: boolean) => void): void;
  showAlert(message: string, cb?: () => void): void;
  openTelegramLink(url: string): void;
  close(): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: WebApp };
  }
}

export const tg: WebApp | undefined = window.Telegram?.WebApp;

/** True only inside a real Telegram client (initData present). */
export const insideTelegram = Boolean(tg?.initData);

export function initTelegram(): void {
  if (!tg) return;
  tg.ready();
  tg.expand();
  applyTheme();
  tg.onEvent("themeChanged", applyTheme);
}

const THEME_VARS: Record<string, string> = {
  bg_color: "--tg-bg",
  secondary_bg_color: "--tg-bg-2",
  text_color: "--tg-text",
  hint_color: "--tg-hint",
  link_color: "--tg-link",
  button_color: "--tg-button",
  button_text_color: "--tg-button-text",
  section_bg_color: "--tg-section",
  destructive_text_color: "--tg-danger",
};

export function applyTheme(): void {
  const root = document.documentElement;
  const scheme = tg?.colorScheme ?? (matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark" : "light");
  root.dataset.theme = scheme;
  if (!tg?.themeParams) return;
  for (const [key, cssVar] of Object.entries(THEME_VARS)) {
    const value = tg.themeParams[key];
    if (value) root.style.setProperty(cssVar, value);
  }
}

export function getInitData(): string {
  if (tg?.initData) return tg.initData;
  // Documented browser development mode (see docs/DEVELOPMENT.md): a signed test initData.
  return import.meta.env.VITE_DEV_INIT_DATA ?? "";
}

export function getBusinessSlug(): string {
  const params = new URLSearchParams(location.search);
  return (
    params.get("b") ||
    tg?.initDataUnsafe.start_param ||
    import.meta.env.VITE_DEV_BUSINESS ||
    ""
  );
}

const TABLE_RE = /^[A-Za-z0-9]{1,10}$/;

/** Table number from a table-QR visit (`?table=5`, set by the bot); kept for this session. */
export function getTable(): string {
  const fromUrl = new URLSearchParams(location.search).get("table") ?? "";
  try {
    if (TABLE_RE.test(fromUrl)) sessionStorage.setItem("sop.table", fromUrl);
    const saved = sessionStorage.getItem("sop.table") ?? "";
    return TABLE_RE.test(saved) ? saved : "";
  } catch {
    return TABLE_RE.test(fromUrl) ? fromUrl : "";
  }
}

export const haptic = {
  tap: () => tg?.HapticFeedback?.impactOccurred("light"),
  success: () => tg?.HapticFeedback?.notificationOccurred("success"),
  error: () => tg?.HapticFeedback?.notificationOccurred("error"),
  select: () => tg?.HapticFeedback?.selectionChanged(),
};

export function confirmDialog(message: string): Promise<boolean> {
  if (tg?.showConfirm && tg.isVersionAtLeast("6.2")) {
    return new Promise((resolve) => tg.showConfirm(message, resolve));
  }
  return Promise.resolve(window.confirm(message));
}
