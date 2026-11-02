/** 80 mm receipt for thermal printers (also "Save as PDF" for an invoice). Built with DOM
 * nodes, never innerHTML with order data, so customer text cannot inject markup. */
import type { OrderDetail } from "./api";

interface ReceiptLabels {
  shop: string;
  order: string;
  fulfilment: string;
  subtotal: string;
  delivery: string;
  discount: string;
  total: string;
  customer: string;
  notes: string;
  thanks: string;
}

const CSS = `
@page { size: 80mm auto; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; padding: 4mm; width: 80mm; font: 12px/1.45 "IBM Plex Sans Arabic", Tahoma, sans-serif; color: #000; }
h1 { font-size: 16px; margin: 0; text-align: center; }
.c { text-align: center; } .b { font-weight: 700; } .s { font-size: 11px; }
.row { display: flex; justify-content: space-between; gap: 8px; }
.row span:last-child { white-space: nowrap; font-variant-numeric: tabular-nums; }
hr { border: 0; border-top: 1px dashed #000; margin: 6px 0; }
.big { font-size: 15px; }
@media screen { body { margin: 16px auto; box-shadow: 0 0 0 1px #ddd; } }
`;

export function printReceipt(o: OrderDetail, labels: ReceiptLabels, money: (n: number) => string,
  lang: "ar" | "en", when: string) {
  const w = window.open("", "_blank", "width=420,height=700");
  if (!w) return;
  const d = w.document;
  d.documentElement.lang = lang;
  d.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  d.title = `${labels.order} #${o.number}`;
  const style = d.createElement("style");
  style.textContent = CSS;
  d.head.appendChild(style);

  const el = (tag: string, text = "", cls = "") => {
    const n = d.createElement(tag);
    if (text) n.textContent = text;
    if (cls) n.className = cls;
    d.body.appendChild(n);
    return n;
  };
  const row = (a: string, b: string, cls = "") => {
    const r = el("div", "", `row ${cls}`);
    const x = d.createElement("span"); x.textContent = a;
    const y = d.createElement("span"); y.textContent = b;
    r.append(x, y);
  };

  el("h1", labels.shop);
  el("p", `${labels.order} #${o.number}`, "c b big");
  el("p", when, "c s");
  el("p", labels.fulfilment, "c b");
  el("hr");
  for (const i of o.items) {
    const name = (lang === "en" && i.product_name_en) || i.product_name_ar;
    row(`${i.quantity} × ${name}`, money(i.line_total));
    const opts = i.options.map((x) => (lang === "en" && x.option_name_en) || x.option_name_ar);
    if (opts.length) el("div", `  ${opts.join("، ")}`, "s");
    if (i.note) el("div", `  📝 ${i.note}`, "s");
  }
  el("hr");
  row(labels.subtotal, money(o.subtotal));
  if (o.delivery_fee) row(labels.delivery, money(o.delivery_fee));
  if (o.discount_total) row(labels.discount, `-${money(o.discount_total)}`);
  row(labels.total, money(o.total), "b big");
  el("hr");
  row(labels.customer, o.customer_name);
  if (o.customer_phone) row("📞", o.customer_phone);
  if (o.address) el("div", Object.values(o.address).filter(Boolean).join(" - "), "s");
  if (o.notes) el("div", `${labels.notes}: ${o.notes}`, "s");
  el("hr");
  el("p", labels.thanks, "c");
  w.setTimeout(() => { w.focus(); w.print(); }, 250);
}
