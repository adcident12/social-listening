import { Suspense } from "react";
import Timeline from "@/components/Timeline";

export default function TimelinePage() {
  return (
    <Suspense fallback={<p className="text-sm text-neutral-500">กำลังโหลด…</p>}>
      <Timeline />
    </Suspense>
  );
}
