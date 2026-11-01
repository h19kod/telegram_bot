import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

import { tg } from "../telegram";

/** Telegram BackButton bound to history (hidden on root pages). */
export function useBackButton(enabled: boolean): void {
  const navigate = useNavigate();
  useEffect(() => {
    const bb = tg?.BackButton;
    if (!bb) return;
    const back = () => navigate(-1);
    if (enabled) {
      bb.show();
      bb.onClick(back);
    } else {
      bb.hide();
    }
    return () => bb.offClick(back);
  }, [enabled, navigate]);
}

interface MainButtonOpts {
  text: string;
  visible: boolean;
  active?: boolean;
  progress?: boolean;
  onClick: () => void;
}

/** Telegram MainButton. Returns true when it is available (inside Telegram), so pages can
 * render their own in-page button otherwise (browser dev mode). */
export function useMainButton(opts: MainButtonOpts): boolean {
  const handler = useRef(opts.onClick);
  handler.current = opts.onClick;
  const available = Boolean(tg?.initData && tg.MainButton);

  useEffect(() => {
    const mb = tg?.MainButton;
    if (!available || !mb) return;
    const click = () => handler.current();
    mb.onClick(click);
    return () => {
      mb.offClick(click);
      mb.hide();
    };
  }, [available]);

  useEffect(() => {
    if (!available || !tg) return;
    const mb = tg.MainButton;
    mb.setParams({ text: opts.text, is_active: opts.active ?? true });
    if (opts.visible) mb.show();
    else mb.hide();
    if (opts.progress) mb.showProgress(false);
    else mb.hideProgress();
  }, [available, opts.text, opts.visible, opts.active, opts.progress]);

  return available;
}
