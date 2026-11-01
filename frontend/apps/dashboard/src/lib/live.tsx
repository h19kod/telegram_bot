/** Realtime order events over WebSocket with a single-use ticket; plays a chime on new orders. */
import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { get, post } from "./api";
import { useSession } from "./session";

interface Live { connected: boolean; pending: number; lastEvent: unknown }
const Ctx = createContext<Live>({ connected: false, pending: 0, lastEvent: null });
export const useLiveOrders = () => useContext(Ctx);

function chime() {
  try {
    const ac = new AudioContext();
    [880, 1175].forEach((f, i) => {
      const o = ac.createOscillator();
      const g = ac.createGain();
      o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, ac.currentTime + i * 0.18);
      g.gain.exponentialRampToValueAtTime(0.25, ac.currentTime + i * 0.18 + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + i * 0.18 + 0.35);
      o.connect(g).connect(ac.destination);
      o.start(ac.currentTime + i * 0.18);
      o.stop(ac.currentTime + i * 0.18 + 0.4);
    });
  } catch { /* audio blocked until user interaction */ }
}

export function LiveProvider({ children }: { children: ReactNode }) {
  const { businessId, can, t } = useSession();
  const qc = useQueryClient();
  const [state, setState] = useState<Live>({ connected: false, pending: 0, lastEvent: null });
  const retry = useRef(0);

  useEffect(() => {
    if (!businessId || !can("orders.view")) return;
    let ws: WebSocket | null = null;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const refreshPending = () => get<{ count: number }>(`/b/${businessId}/orders?status=pending&page_size=1`)
      .then((o) => setState((s) => ({ ...s, pending: o.count }))).catch(() => undefined);

    async function connect() {
      try {
        const { ticket } = await post<{ ticket: string }>("/auth/ws-ticket");
        const proto = location.protocol === "https:" ? "wss" : "ws";
        ws = new WebSocket(`${proto}://${location.host}/ws/b/${businessId}/?ticket=${ticket}`);
        ws.onopen = () => { retry.current = 0; setState((s) => ({ ...s, connected: true })); };
        ws.onmessage = (m) => {
          const ev = JSON.parse(m.data);
          qc.invalidateQueries({ queryKey: ["b", businessId, "orders"] });
          qc.invalidateQueries({ queryKey: ["b", businessId, "order", ev.order_id] });
          qc.invalidateQueries({ queryKey: ["b", businessId, "overview"] });
          if (ev.type === "order.created") {
            chime();
            if (Notification?.permission === "granted") new Notification(`${t("new_order")} #${ev.number}`);
          }
          setState((s) => ({ ...s, lastEvent: ev }));
          refreshPending();
        };
        ws.onclose = () => {
          setState((s) => ({ ...s, connected: false }));
          if (!stopped) timer = setTimeout(connect, Math.min(30000, 1000 * 2 ** retry.current++));
        };
      } catch {
        if (!stopped) timer = setTimeout(connect, Math.min(30000, 1000 * 2 ** retry.current++));
      }
    }
    refreshPending();
    connect();
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
    return () => { stopped = true; clearTimeout(timer); ws?.close(); };
  }, [businessId]); // eslint-disable-line react-hooks/exhaustive-deps

  return <Ctx.Provider value={state}>{children}</Ctx.Provider>;
}
