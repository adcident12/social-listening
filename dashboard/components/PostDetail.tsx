"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { type Post } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

export default function PostDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = usePoll<Post>(`/posts/${encodeURIComponent(id)}`);

  if (!data) {
    return (
      <p className="text-sm text-neutral-500">
        {error ? `ไม่พบโพสต์ (${error})` : "กำลังโหลด…"}
      </p>
    );
  }
  const eng = data.reaction_count + data.comment_count + data.share_count;
  return (
    <article className="max-w-2xl space-y-4">
      <header>
        <h1 className="text-xl font-bold">{data.poster_name ?? "ไม่ทราบชื่อ"}</h1>
        <p className="text-sm text-neutral-500">
          {data.created_at ?? "—"} · engagement {eng} (R {data.reaction_count} / C{" "}
          {data.comment_count} / S {data.share_count})
        </p>
      </header>
      <p className="whitespace-pre-wrap leading-relaxed">
        {data.body ?? "(ไม่มีข้อความ)"}
      </p>
      {data.keywords.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {data.keywords.map((k) => (
            <span key={k} className="rounded bg-neutral-100 px-2 py-0.5 text-xs">
              {k}
            </span>
          ))}
        </div>
      )}
      {data.permalink && (
        <a
          className="inline-block text-blue-700 hover:underline"
          href={data.permalink}
          target="_blank"
          rel="noreferrer"
        >
          เปิดใน Facebook ↗
        </a>
      )}
      <Link href="/posts" className="block text-sm text-neutral-500">
        ← กลับไป list
      </Link>
    </article>
  );
}
