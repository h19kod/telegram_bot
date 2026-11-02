import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader } from "../components/Shell";
import { Button, Card, Empty, ErrorBox, errorMessage, Loading, Pager, Select, TextArea,
  useUi } from "../components/ui";
import { get, post, qs, type Paginated, type Review, type ReviewSummary } from "../lib/api";
import { useBizKey, useBizPath, useSession } from "../lib/session";

function Stars({ n, label }: { n: number; label: string }) {
  return <span role="img" aria-label={label} className="tracking-wider">
    <span className="text-warn">{"★".repeat(n)}</span><span className="text-line">{"★".repeat(5 - n)}</span></span>;
}

export function ReviewsPage() {
  const { t, lang, can } = useSession();
  const key = useBizKey();
  const path = useBizPath();
  const qc = useQueryClient();
  const { toast } = useUi();
  const [f, setF] = useState({ rating: "", page: 1 });
  const [replying, setReplying] = useState<Record<string, string>>({});
  const summary = useQuery({ queryKey: key("reviews-summary"),
    queryFn: () => get<ReviewSummary>(path("/reviews/summary")) });
  const q = useQuery({ queryKey: key("reviews", f), placeholderData: (p) => p,
    queryFn: () => get<Paginated<Review>>(path(`/reviews${qs(f)}`)) });
  const reply = useMutation({
    mutationFn: (v: { id: string; reply: string }) => post<Review>(path(`/reviews/${v.id}/reply`), { reply: v.reply }),
    onSuccess: (_, v) => {
      toast(t("saved"));
      setReplying((r) => { const n = { ...r }; delete n[v.id]; return n; });
      qc.invalidateQueries({ queryKey: key("reviews") });
    },
    onError: (e) => toast(errorMessage(e, t("error")), "error"),
  });
  const s = summary.data;
  const max = s ? Math.max(1, ...Object.values(s.distribution)) : 1;
  const date = (iso: string) => new Date(iso).toLocaleDateString(lang === "ar" ? "ar-IQ" : "en-GB", { numberingSystem: "latn" });

  return (
    <>
      <PageHeader title={t("reviews")} actions={
        <Select aria-label={t("all_ratings")} className="w-auto" value={f.rating}
          onChange={(e) => setF({ rating: e.target.value, page: 1 })}>
          <option value="">{t("all_ratings")}</option>
          {[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{t("stars_n", { n })}</option>)}
        </Select>} />
      {s && s.rating_count > 0 && (
        <Card className="mb-4">
          <div className="flex flex-wrap items-center gap-6">
            <div className="text-center">
              <p className="tabular text-[40px] font-bold leading-none">{s.rating_avg?.toFixed(1)}</p>
              <Stars n={Math.round(s.rating_avg ?? 0)} label={t("stars_n", { n: s.rating_avg ?? 0 })} />
              <p className="text-[13px] text-hint">{t("reviews_count", { n: s.rating_count })}</p>
            </div>
            <div className="min-w-48 flex-1 space-y-1">
              {[5, 4, 3, 2, 1].map((n) => {
                const v = s.distribution[String(n)] ?? 0;
                return (
                  <button key={n} type="button" onClick={() => setF({ rating: String(n), page: 1 })}
                    className="flex w-full items-center gap-2 text-[13px]" aria-label={`${t("stars_n", { n })}: ${v}`}>
                    <span className="w-6 tabular">{n}★</span>
                    <span className="h-2 flex-1 overflow-hidden rounded-full bg-bg2">
                      <span className="block h-full rounded-full bg-warn" style={{ width: `${(v / max) * 100}%` }} />
                    </span>
                    <span className="w-8 text-end tabular text-hint">{v}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </Card>
      )}
      {q.isPending ? <Loading /> : q.isError ? <ErrorBox error={q.error} /> : !q.data.results.length
        ? <Card><Empty>{t("no_reviews")}</Empty></Card> : (
        <>
          <div className="space-y-3">
            {q.data.results.map((r) => (
              <Card key={r.id}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Stars n={r.rating} label={t("stars_n", { n: r.rating })} />
                    <span className="font-medium">{r.customer_name}</span>
                  </div>
                  <span className="text-[13px] text-hint">{t("order_number", { n: r.order_number })} · {date(r.created_at)}</span>
                </div>
                <p className={r.comment ? "mt-2" : "mt-2 text-[13px] text-hint"}>{r.comment || t("no_comment")}</p>
                {r.reply && replying[r.id] === undefined && (
                  <p className="mt-2 rounded-lg bg-bg2 p-3 text-[14px]"><span className="font-semibold">{t("your_reply")}: </span>{r.reply}</p>
                )}
                {can("reviews.reply") && (replying[r.id] === undefined ? (
                  <Button size="sm" variant="secondary" className="mt-2"
                    onClick={() => setReplying({ ...replying, [r.id]: r.reply })}>{t("reply")}</Button>
                ) : (
                  <form className="mt-2 space-y-2" onSubmit={(e) => { e.preventDefault(); reply.mutate({ id: r.id, reply: replying[r.id] ?? "" }); }}>
                    <TextArea aria-label={t("your_reply")} maxLength={500} value={replying[r.id]}
                      onChange={(e) => setReplying({ ...replying, [r.id]: e.target.value })} />
                    <div className="flex gap-2">
                      <Button size="sm" type="submit" disabled={reply.isPending}>{t("save")}</Button>
                      <Button size="sm" variant="ghost" type="button" onClick={() => {
                        const n = { ...replying }; delete n[r.id]; setReplying(n); }}>{t("cancel")}</Button>
                    </div>
                  </form>
                ))}
              </Card>
            ))}
          </div>
          <Pager page={f.page} count={q.data.count} onPage={(page) => setF({ ...f, page })} />
        </>
      )}
    </>
  );
}
