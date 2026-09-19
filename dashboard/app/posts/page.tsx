import { Suspense } from "react";
import PostList from "@/components/PostList";

export default function PostsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-neutral-500">กำลังโหลด…</p>}>
      <PostList />
    </Suspense>
  );
}
