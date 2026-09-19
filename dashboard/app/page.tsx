import { Suspense } from "react";
import Trends from "@/components/Trends";

export default function Home() {
  return (
    <Suspense fallback={<p className="text-sm text-neutral-500">กำลังโหลด…</p>}>
      <Trends />
    </Suspense>
  );
}
