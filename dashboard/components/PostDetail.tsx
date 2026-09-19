"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { type Post } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";
import { timeAgo, fullDateTime } from "@/lib/format";

const SENTIMENT: Record<string, { cls: string; label: string }> = {
  positive: { cls: "bg-emerald-100 text-emerald-800", label: "บวก" },
  neutral: { cls: "bg-neutral-100 text-neutral-700", label: "กลาง" },
  negative: { cls: "bg-red-100 text-red-800", label: "ลบ" },
};

export default function PostDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = usePoll<Post>(`/posts/${encodeURIComponent(id)}`);

  if (!data) {
    return (
      <p className="rounded-xl border border-neutral-200 bg-white p-6 text-sm text-neutral-500">
        {error ? `ไม่พบโพสต์ (${error})` : "กำลังโหลด…"}
      </p>
    );
  }
  const name = data.poster_name ?? "ไม่ทราบชื่อ";
  return (
    <article className="mx-auto max-w-3xl space-y-4">
      <Link
        href="/posts"
        className="text-sm text-neutral-500 transition-colors hover:text-neutral-900"
      >
        ← กลับไป list
      </Link>
      <div className="rounded-xl border border-neutral-200 bg-white p-6">
        <header className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-indigo-100 text-lg font-bold text-indigo-700">
            {name.charAt(0).toUpperCase()}
          </span>
          <div>
            <h1 className="text-lg font-bold">{name}</h1>
            <p
              className="text-sm text-neutral-500"
              title={fullDateTime(data.created_at)}
            >
              {timeAgo(data.created_at)}
            </p>
          </div>
        </header>
        {data.sentiment && SENTIMENT[data.sentiment] && (
          <span
            className={`mt-3 inline-block rounded-full px-2 py-0.5 text-xs font-medium ${SENTIMENT[data.sentiment].cls}`}
          >
            {SENTIMENT[data.sentiment].label}
          </span>
        )}
        <p className="mt-4 whitespace-pre-wrap leading-relaxed">
          {data.body ?? "(ไม่มีข้อความ)"}
        </p>
        {data.summary && (
          <div className="mt-4 border border-neutral-200 bg-neutral-50 p-3 text-sm">
            <span className="font-medium text-neutral-500">สรุปโดย AI: </span>
            <span className="text-neutral-700">{data.summary}</span>
          </div>
        )}
        {data.keywords.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {data.keywords.map((k) => (
              <span
                key={k}
                className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs text-indigo-700"
              >
                {k}
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-neutral-200 bg-white p-4">
        <div className="flex gap-6">
          <span className="text-sm">
            <span className="text-lg font-bold tabular-nums">
              {data.reaction_count}
            </span>{" "}
            <span className="text-neutral-500">ปฏิกิริยา</span>
          </span>
          <span className="text-sm">
            <span className="text-lg font-bold tabular-nums">
              {data.comment_count}
            </span>{" "}
            <span className="text-neutral-500">ความเห็น</span>
          </span>
          <span className="text-sm">
            <span className="text-lg font-bold tabular-nums">
              {data.share_count}
            </span>{" "}
            <span className="text-neutral-500">แชร์</span>
          </span>
        </div>
        {data.permalink && (
          <a
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700"
            href={data.permalink}
            target="_blank"
            rel="noreferrer"
          >
            เปิดใน Facebook ↗
          </a>
        )}
      </div>
    </article>
  );
}
