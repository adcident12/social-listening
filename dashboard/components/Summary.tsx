"use client";
import { type Summary as SummaryData } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

const SEVERITY_CLS: Record<string, string> = {
  ok: "border-emerald-200 bg-emerald-50 text-emerald-900",
  warn: "border-yellow-200 bg-yellow-50 text-yellow-900",
  alert: "border-red-200 bg-red-50 text-red-900",
  high: "border-red-200 bg-red-50 text-red-900",
  info: "border-neutral-200 bg-white text-neutral-800",
};

export default function Summary() {
  const { data, error } = usePoll<SummaryData>("/summary?days=7");

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
  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-xl border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
          refresh พัง — แสดงข้อมูลล่าสุด
        </div>
      )}
      <header>
        <h1 className="text-2xl font-bold tracking-tight">สรุปวันนี้</h1>
        <p className="text-sm text-neutral-500">7 วันล่าสุด · ทุกกลุ่ม</p>
      </header>
      <section className="space-y-3">
        {data.items.map((it, i) => (
          <div
            key={i}
            className={`rounded-xl border p-4 ${SEVERITY_CLS[it.severity] ?? "border-neutral-200 bg-white text-neutral-800"}`}
          >
            <p className="text-sm leading-relaxed">{it.text}</p>
            {it.href && (
              <a
                href={it.href}
                target="_blank"
                rel="noreferrer"
                className="mt-1 inline-block text-sm font-medium text-indigo-700 hover:underline"
              >
                ดูโพสต์ต้นทาง ↗
              </a>
            )}
          </div>
        ))}
      </section>
    </div>
  );
}
