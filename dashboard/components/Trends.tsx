"use client";
import Link from "next/link";
import { useState } from "react";
import { type Stats } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";
import { timeAgo } from "@/lib/format";

const DAYS = [7, 14, 30] as const;

const SENTIMENT_STYLE: Record<string, { cls: string; label: string }> = {
  positive: { cls: "bg-emerald-100 text-emerald-800", label: "บวก" },
  neutral: { cls: "bg-neutral-100 text-neutral-700", label: "กลาง" },
  negative: { cls: "bg-red-100 text-red-800", label: "ลบ" },
  unanalyzed: { cls: "bg-amber-100 text-amber-800", label: "ยังไม่ได้วิเคราะห์" },
};

function freshnessBadge(iso: string | null): { cls: string; dot: string } {
  if (!iso) return { cls: "bg-red-100 text-red-800", dot: "🔴" };
  const mins = (Date.now() - new Date(iso).getTime()) / 60_000;
  if (mins <= 60) return { cls: "bg-emerald-100 text-emerald-800", dot: "🟢" };
  if (mins <= 1440) return { cls: "bg-yellow-100 text-yellow-800", dot: "🟡" };
  return { cls: "bg-red-100 text-red-800", dot: "🔴" };
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-4">
      <p className="text-sm text-neutral-500">{label}</p>
      <p className="mt-1 truncate text-2xl font-bold tabular-nums">{value}</p>
      {sub && <p className="text-xs text-neutral-400">{sub}</p>}
    </div>
  );
}

export default function Trends() {
  const [days, setDays] = useState(7);
  const { data, error } = usePoll<Stats>(`/stats?days=${days}`);

  if (!data) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        เชื่อมต่อ API ไม่ได้ ({error}) — รัน{" "}
        <code className="rounded bg-red-100 px-1">
          python -m uvicorn api:app --port 8000
        </code>
      </div>
    );
  }
  const max = data.top_keywords[0]?.count ?? 1;
  const topKw = data.top_keywords[0];
  const topPoster = data.top_posters[0];
  const sentiment = data.sentiment.filter((s) => s.count > 0);
  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-xl border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
          {error.includes("503")
            ? "DB occupied — กำลัง retry ทุก 60 วิ"
            : "refresh พัง — แสดงข้อมูลล่าสุด"}
        </div>
      )}
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{data.group}</h1>
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${freshnessBadge(data.last_fetched).cls}`}
          >
            {freshnessBadge(data.last_fetched).dot} อัปเดตล่าสุด{" "}
            {timeAgo(data.last_fetched)}
          </span>
        </div>
        <div className="flex rounded-lg border border-neutral-200 bg-white p-0.5">
          {DAYS.map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={
                days === d
                  ? "rounded-md bg-indigo-600 px-3 py-1 text-sm font-medium text-white"
                  : "rounded-md px-3 py-1 text-sm text-neutral-500 transition-colors hover:text-neutral-900"
              }
            >
              {d} วัน
            </button>
          ))}
        </div>
      </header>
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label={`โพสต์ (${days} วัน)`} value={String(data.total_posts)} />
        <StatCard label="โพสต์ใหม่ 24 ชม." value={String(data.new_since_yesterday)} />
        <StatCard
          label="Top keyword"
          value={topKw?.word ?? "—"}
          sub={topKw ? `${topKw.count} ครั้ง` : undefined}
        />
        <StatCard
          label="Top poster"
          value={topPoster?.name ?? "—"}
          sub={topPoster ? `${topPoster.count} โพสต์` : undefined}
        />
      </section>
      <section className="rounded-xl border border-neutral-200 bg-white p-5">
        <h2 className="mb-4 text-lg font-semibold">Sentiment</h2>
        {sentiment.length === 0 ? (
          <p className="text-sm text-neutral-500">ยังไม่มีโพสต์ใน range นี้</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {sentiment.map((s) => {
              const style = SENTIMENT_STYLE[s.label];
              return (
                <span
                  key={s.label}
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${style?.cls ?? "bg-neutral-100 text-neutral-700"}`}
                >
                  {style?.label ?? s.label} {s.count}
                </span>
              );
            })}
          </div>
        )}
      </section>
      <section className="rounded-xl border border-neutral-200 bg-white p-5">
        <h2 className="mb-4 text-lg font-semibold">Top keywords</h2>
        {data.top_keywords.length === 0 && (
          <p className="text-sm text-neutral-500">ยังไม่มีโพสต์ใน range นี้</p>
        )}
        <div className="space-y-2">
          {data.top_keywords.map((k) => (
            <div key={k.word} className="flex items-center gap-3">
              <span className="w-44 truncate text-sm">{k.word}</span>
              <div className="h-5 flex-1 overflow-hidden rounded-full bg-neutral-100">
                <div
                  className="h-full rounded-full bg-indigo-500"
                  style={{ width: `${(k.count / max) * 100}%` }}
                />
              </div>
              <span className="w-24 text-right text-sm tabular-nums text-neutral-600">
                {k.count} · {(k.pct * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      </section>
      <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-neutral-200 bg-white p-5">
          <h2 className="mb-4 text-lg font-semibold">Top posters</h2>
          {data.top_posters.length === 0 && (
            <p className="text-sm text-neutral-500">ยังไม่มีโพสต์ใน range นี้</p>
          )}
          <ol className="space-y-2">
            {data.top_posters.map((p, i) => (
              <li key={p.name} className="flex items-center gap-3">
                <span
                  className={
                    i < 3
                      ? "flex h-6 w-6 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-700"
                      : "flex h-6 w-6 items-center justify-center rounded-full bg-neutral-100 text-xs font-medium text-neutral-500"
                  }
                >
                  {i + 1}
                </span>
                <span className="flex-1 truncate text-sm">{p.name}</span>
                <span className="text-sm tabular-nums text-neutral-500">
                  {p.count} โพสต์
                </span>
              </li>
            ))}
          </ol>
        </div>
        <div className="rounded-xl border border-neutral-200 bg-white p-5">
          <h2 className="mb-4 text-lg font-semibold">โพสต์ engagement สูงสุด</h2>
          {data.top_posts.length === 0 && (
            <p className="text-sm text-neutral-500">ยังไม่มีโพสต์ใน range นี้</p>
          )}
          <ul className="space-y-4">
            {data.top_posts.map((p) => (
              <li key={p.post_id}>
                <Link
                  href={`/posts/${p.post_id}`}
                  className="text-sm font-medium text-indigo-700 hover:underline"
                >
                  {p.poster_name ?? "ไม่ทราบชื่อ"}
                  <span className="ml-2 font-normal text-neutral-400">
                    {p.engagement} engagement · {timeAgo(p.created_at)}
                  </span>
                </Link>
                <p className="text-sm text-neutral-600">{p.snippet}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}
