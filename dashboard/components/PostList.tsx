"use client";
import Link from "next/link";
import { useState } from "react";
import { type PostsResponse } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

const LIMIT = 50;

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
        <div className="rounded bg-red-50 p-3 text-sm text-red-700">
          เชื่อมต่อ API ไม่ได้ ({error}) — รัน{" "}
          <code>python -m uvicorn api:app --port 8000</code>
        </div>
      )}
      {error && data && (
        <div className="rounded bg-yellow-50 p-2 text-sm text-yellow-800">
          {error.includes("503")
            ? "DB occupied — กำลัง retry ทุก 60 วิ"
            : "refresh พัง — แสดงข้อมูลล่าสุด"}
        </div>
      )}
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setPage(0);
        }}
      >
        <input
          className="rounded border px-2 py-1 text-sm"
          placeholder="ค้นหาในข้อความ…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <input
          className="rounded border px-2 py-1 text-sm"
          placeholder="poster"
          value={poster}
          onChange={(e) => setPoster(e.target.value)}
        />
        <select
          className="rounded border px-2 py-1 text-sm"
          value={sort}
          onChange={(e) => setSort(e.target.value as "date" | "engagement")}
        >
          <option value="date">ล่าสุดก่อน</option>
          <option value="engagement">engagement สูงสุด</option>
        </select>
        <button className="rounded bg-blue-600 px-3 py-1 text-sm text-white">
          ค้นหา
        </button>
        <span className="text-sm text-neutral-500">{data?.total ?? 0} posts</span>
      </form>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-neutral-500">
            <th className="py-1 pr-2">เวลา</th>
            <th className="py-1 pr-2">poster</th>
            <th className="py-1 pr-2">ข้อความ</th>
            <th className="py-1 pr-2 text-right">R/C/S</th>
            <th className="py-1 pr-2 text-right">engagement</th>
            <th className="py-1" />
          </tr>
        </thead>
        <tbody>
          {posts.map((p) => (
            <tr key={p.post_id} className="border-b align-top">
              <td className="whitespace-nowrap py-2 pr-2 text-neutral-500">
                {(p.created_at ?? "—").slice(0, 16)}
              </td>
              <td className="whitespace-nowrap py-2 pr-2">{p.poster_name ?? "—"}</td>
              <td className="py-2 pr-2">{(p.body ?? "").slice(0, 120)}</td>
              <td className="whitespace-nowrap py-2 pr-2 text-right text-neutral-500">
                {p.reaction_count}/{p.comment_count}/{p.share_count}
              </td>
              <td className="py-2 pr-2 text-right">{eng(p)}</td>
              <td className="py-2 text-right">
                <Link href={`/posts/${p.post_id}`} className="text-blue-700 hover:underline">
                  เปิด
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {data && posts.length === 0 && (
        <p className="text-sm text-neutral-500">ไม่พบโพสต์</p>
      )}
      <div className="flex gap-2 text-sm">
        <button
          disabled={page === 0}
          onClick={() => setPage((p) => p - 1)}
          className="rounded border px-3 py-1 disabled:opacity-40"
        >
          ก่อนหน้า
        </button>
        <button
          disabled={posts.length < LIMIT}
          onClick={() => setPage((p) => p + 1)}
          className="rounded border px-3 py-1 disabled:opacity-40"
        >
          ถัดไป
        </button>
      </div>
    </div>
  );
}
