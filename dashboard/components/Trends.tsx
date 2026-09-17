"use client";
import Link from "next/link";
import { type Stats } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

export default function Trends() {
  const { data, error } = usePoll<Stats>("/stats?days=7");

  if (!data) {
    return (
      <div className="rounded bg-red-50 p-3 text-sm text-red-700">
        เชื่อมต่อ API ไม่ได้ ({error}) — รัน{" "}
        <code>python -m uvicorn api:app --port 8000</code>
      </div>
    );
  }
  const max = data.top_keywords[0]?.count ?? 1;
  return (
    <div className="space-y-8">
      {error && (
        <div className="rounded bg-yellow-50 p-2 text-sm text-yellow-800">
          {error.includes("503")
            ? "DB occupied — กำลัง retry ทุก 60 วิ"
            : "refresh พัง — แสดงข้อมูลล่าสุด"}
        </div>
      )}
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-bold">{data.group} — 7 วันล่าสุด</h1>
        <span className="text-sm text-neutral-500">
          {data.new_since_yesterday} โพสต์ใหม่ 24 ชม. · {data.total_posts} posts ·
          ล่าสุด {data.last_fetched?.slice(0, 16)}
        </span>
      </header>
      <section>
        <h2 className="mb-2 text-lg font-semibold">Top keywords</h2>
        {data.top_keywords.length === 0 && (
          <p className="text-sm text-neutral-500">ยังไม่มีโพสต์ใน range นี้</p>
        )}
        {data.top_keywords.map((k) => (
          <div key={k.word} className="mb-1 flex items-center gap-2">
            <span className="w-40 truncate">{k.word}</span>
            <div className="h-4 flex-1 rounded bg-neutral-100">
              <div
                className="h-full rounded bg-blue-600"
                style={{ width: `${(k.count / max) * 100}%` }}
              />
            </div>
            <span className="w-20 text-right text-sm">
              {k.count} · {(k.pct * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </section>
      <section className="grid grid-cols-1 gap-8 sm:grid-cols-2">
        <div>
          <h2 className="mb-2 text-lg font-semibold">Top posters</h2>
          {data.top_posters.length === 0 && (
            <p className="text-sm text-neutral-500">ยังไม่มีโพสต์ใน range นี้</p>
          )}
          <ol className="list-decimal pl-5">
            {data.top_posters.map((p) => (
              <li key={p.name}>
                {p.name} — {p.count}
              </li>
            ))}
          </ol>
        </div>
        <div>
          <h2 className="mb-2 text-lg font-semibold">Top posts by engagement</h2>
          <ul className="space-y-3">
            {data.top_posts.map((p) => (
              <li key={p.post_id}>
                <Link
                  href={`/posts/${p.post_id}`}
                  className="text-sm text-blue-700 hover:underline"
                >
                  [{p.engagement}] {p.created_at ?? "—"} — {p.poster_name}
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
