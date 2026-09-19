import { Suspense } from "react";
import PostDetail from "@/components/PostDetail";

export default function PostPage() {
  return (
    <Suspense fallback={<p className="text-sm text-neutral-500">กำลังโหลด…</p>}>
      <PostDetail />
    </Suspense>
  );
}
