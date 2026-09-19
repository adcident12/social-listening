"use client";
import Link from "next/link";
import { useState } from "react";
import { API, type PostsResponse } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";
import { timeAgo, fullDateTime } from "@/lib/format";

const LIMIT = 50;
const inputCls =
  "rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm transition-colors focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100";

export default function PostList() {
  const [q, setQ] = useState("");
  const [poster, setPoster] = useState("");
  const [sort, setSort] = useState<"date" | "engagement">("date");
  const [page, setPage] = useState(0);

  const qs = new URLSearchParams({
    sort,
    limit: String(LIMIT),
    offset: String(page * LIMIT),
  });
  if (q) qs.set("q", q);
  if (poster) qs.set("poster", poster);
  const { data, error } = usePoll<PostsResponse>(`/posts?${qs}`);

  const posts = data?.posts ?? [];
  const eng = (p: { reaction_count: number; comment_count: number; share_count: number }) =>
    p.reaction_count + p.comment_count + p.share_count;

  return (
    <div className="space-y-4">
      {error && !data && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          เชื่อมต่อ API ไม่ได้ ({error}) — รัน{" "}
          <code className="rounded bg-red-100 px-1">
            python -m uvicorn api:app --port 8000
          </code>
        </div>
      )}
      {error && data && (
        <div className="rounded-xl border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
          {error.includes("503")
            ? "DB occupied — กำลัง retry ทุก 60 วิ"
            : "refresh พัง — แสดงข้อมูลล่าสุด"}
        </div>
      )}
      <h1 className="text-2xl font-bold tracking-tight">Posts</h1>
      <div className="flex flex-wrap items-center gap-2">
        <input
          className={`${inputCls} w-56`}
          placeholder="ค้นหาในข้อความ…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(0);
          }}
        />
        <input
          className={`${inputCls} w-40`}
          placeholder="ชื่อผู้โพสต์"
          value={poster}
          onChange={(e) => {
            setPoster(e.target.value);
            setPage(0);
          }}
        />
        <select
          className={inputCls}
          value={sort}
          onChange={(e) => {
            setSort(e.target.value as "date" | "engagement");
            setPage(0);
          }}
        >
          <option value="date">ล่าสุดก่อน</option>
          <option value="engagement">engagement สูงสุด</option>
        </select>
        <a
          href={`${API}/export?${qs}`}
          download
          className="rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm transition-colors hover:bg-neutral-50"
        >
          Export CSV
        </a>
        <span className="ml-auto text-sm tabular-nums text-neutral-500">
          {data?.total ?? 0} โพสต์
        </span>
      </div>
      <div className="overflow-hidden rounded-xl border border-neutral-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-neutral-50 text-left text-xs font-medium uppercase tracking-wide text-neutral-500">
            <tr>
              <th className="px-4 py-3">เวลา</th>
              <th className="px-4 py-3">ผู้โพสต์</th>
              <th className="px-4 py-3">ข้อความ</th>
              <th className="px-4 py-3 text-right">ปฏิกิริยา · ความเห็น · แชร์</th>
              <th className="px-4 py-3 text-right">Engagement</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {posts.map((p) => (
              <tr
                key={p.post_id}
                className="border-t border-neutral-100 align-top transition-colors hover:bg-neutral-50"
              >
                <td
                  className="whitespace-nowrap px-4 py-3 text-neutral-500"
                  title={fullDateTime(p.created_at)}
                >
                  {timeAgo(p.created_at)}
                </td>
                <td className="whitespace-nowrap px-4 py-3">{p.poster_name ?? "—"}</td>
                <td className="px-4 py-3">
                  <span className="line-clamp-2">{(p.body ?? "").slice(0, 120)}</span>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-neutral-500">
                  {p.reaction_count} · {p.comment_count} · {p.share_count}
                </td>
                <td className="px-4 py-3 text-right">
                  <span className="inline-flex rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-semibold tabular-nums text-indigo-700">
                    {eng(p)}
                  </span>
                </td>
                <td className="px-4 py-3 text-right">
                  <Link
                    href={`/posts/${p.post_id}`}
                    className="text-sm font-medium text-indigo-700 hover:underline"
                  >
                    ดู →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && posts.length === 0 && (
          <p className="p-8 text-center text-sm text-neutral-500">ไม่พบโพสต์</p>
        )}
      </div>
      <div className="flex gap-2 text-sm">
        <button
          disabled={page === 0}
          onClick={() => setPage((p) => p - 1)}
          className="rounded-lg border border-neutral-300 bg-white px-4 py-2 shadow-sm transition-colors hover:bg-neutral-50 disabled:opacity-40"
        >
          ก่อนหน้า
        </button>
        <button
          disabled={posts.length < LIMIT}
          onClick={() => setPage((p) => p + 1)}
          className="rounded-lg border border-neutral-300 bg-white px-4 py-2 shadow-sm transition-colors hover:bg-neutral-50 disabled:opacity-40"
        >
          ถัดไป
        </button>
      </div>
    </div>
  );
}
