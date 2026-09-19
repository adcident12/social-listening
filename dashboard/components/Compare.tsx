"use client";
import { useEffect, useState } from "react";
import {
  API,
  type CompareResponse,
  type Group,
  type GroupsResponse,
} from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

const DAYS = [7, 14, 30, 90] as const;
const LOW_SAMPLE = 10;

function LowBadge({ n }: { n: number }) {
  if (n >= LOW_SAMPLE) return null;
  return (
    <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
      sample ต่ำ (n={n})
    </span>
  );
}

function DeltaArrow({ f, s }: { f: number; s: number }) {
  if (s > f) return <span className="font-semibold text-emerald-600">▲</span>;
  if (s < f) return <span className="font-semibold text-red-500">▼</span>;
  return <span className="text-neutral-400">–</span>;
}

export default function Compare() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [groupsError, setGroupsError] = useState<string | null>(null);
  const [sel, setSel] = useState<string[] | null>(null);
  const [days, setDays] = useState(7);

  useEffect(() => {
    fetch(`${API}/groups`, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<GroupsResponse>;
      })
      .then((d) => setGroups(d.groups))
      .catch((e) => setGroupsError(String(e)));
  }, []);

  const { data, error, stale } = usePoll<CompareResponse>(
    `/stats/compare?days=${days}`,
  );

  if (groupsError) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        ดึงรายชื่อกลุ่มไม่ได้ ({groupsError}) — รัน{" "}
        <code className="rounded bg-red-100 px-1">
          python -m uvicorn api:app --port 8000
        </code>
      </div>
    );
  }

  const allIds = groups.map((g) => g.group_id);
  const selIds = sel ?? allIds;
  const isSubset = selIds.length < allIds.length;
  const selected = (data?.groups ?? []).filter((g) => selIds.includes(g.group_id));
  const subsetTotal = selected.reduce((s, g) => s + g.sample_size, 0);

  const toggle = (id: string) => {
    const cur = sel ?? allIds;
    setSel(cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]);
  };

  if (!data) {
    return groupsError ? null : (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold tracking-tight">Compare</h1>
        {error ? (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            เชื่อมต่อ API ไม่ได้ ({error}) — รัน{" "}
            <code className="rounded bg-red-100 px-1">
              python -m uvicorn api:app --port 8000
            </code>
          </div>
        ) : (
          <div className="h-96 animate-pulse rounded-xl bg-neutral-100" />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {stale && (
        <div className="rounded-xl border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
          {error?.includes("503")
            ? "DB occupied — กำลัง retry ทุก 60 วิ"
            : "refresh พัง — แสดงข้อมูลล่าสุด"}
        </div>
      )}
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Compare</h1>
        <div className="flex rounded-lg border border-neutral-200 bg-white p-0.5">
          {DAYS.map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={
                days === d
                  ? "rounded-md bg-indigo-600 px-3 py-1 text-sm font-medium text-white"
                  : "rounded-md px-3 py-1 text-sm text-neutral-500 transition-colors hover:text-neutral-900"
              }
            >
              {d} วัน
            </button>
          ))}
        </div>
      </header>
      <section className="rounded-xl border border-neutral-200 bg-white p-4">
        <p className="mb-2 text-sm text-neutral-500">เลือกกลุ่ม (multi-select)</p>
        {groups.length === 0 ? (
          <div className="h-8 animate-pulse rounded-lg bg-neutral-100" />
        ) : (
          <div className="flex flex-wrap gap-2">
            {groups.map((g) => {
              const on = selIds.includes(g.group_id);
              return (
                <button
                  key={g.group_id}
                  onClick={() => toggle(g.group_id)}
                  className={
                    on
                      ? "flex items-center gap-2 rounded-lg border border-indigo-500 bg-indigo-50 px-3 py-1.5 text-sm font-medium text-indigo-700"
                      : "flex items-center gap-2 rounded-lg border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-500 transition-colors hover:border-neutral-300"
                  }
                >
                  <span
                    className={
                      on
                        ? "flex h-4 w-4 items-center justify-center rounded bg-indigo-600 text-[10px] font-bold text-white"
                        : "flex h-4 w-4 items-center justify-center rounded border border-neutral-300 bg-white"
                    }
                  >
                    {on ? "✓" : ""}
                  </span>
                  {g.name}
                </button>
              );
            })}
          </div>
        )}
      </section>
      {isSubset && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          ⚠ SoV คำนวณใหม่ตามกลุ่มที่เลือก · shared keywords ยังคำนวณจากทุกกลุ่มใน
          config (API ไม่ได้ส่ง keyword เต็มให้ recompute)
        </p>
      )}
      {selected.length === 0 ? (
        <div className="rounded-xl border border-neutral-200 bg-white p-6 text-center text-sm text-neutral-500">
          เลือกกลุ่มอย่างน้อย 1 กลุ่ม
        </div>
      ) : (
        <>
          <section className="overflow-x-auto rounded-xl border border-neutral-200 bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-neutral-200 text-left text-neutral-500">
                  <th className="px-4 py-3 font-medium">กลุ่ม</th>
                  <th className="px-4 py-3 font-medium">Share of voice</th>
                  <th className="px-4 py-3 text-right font-medium">โพสต์</th>
                  <th className="px-4 py-3 text-right font-medium">Avg engagement</th>
                  <th className="px-4 py-3 font-medium">Top keywords</th>
                </tr>
              </thead>
              <tbody>
                {selected.map((g) => {
                  const sov = subsetTotal ? g.sample_size / subsetTotal : 0;
                  return (
                    <tr key={g.group_id} className="border-b border-neutral-100 last:border-0">
                      <td className="px-4 py-3 font-medium">
                        {g.name}
                        <LowBadge n={g.sample_size} />
                      </td>
                      <td className="min-w-40 px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="h-2 flex-1 overflow-hidden rounded-full bg-neutral-100">
                            <div
                              className="h-full rounded-full bg-indigo-500"
                              style={{ width: `${sov * 100}%` }}
                            />
                          </div>
                          <span className="w-12 text-right tabular-nums text-neutral-600">
                            {(sov * 100).toFixed(1)}%
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">{g.sample_size}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{g.avg_engagement}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {g.top_keywords.length === 0 && (
                            <span className="text-neutral-400">—</span>
                          )}
                          {g.top_keywords.slice(0, 3).map((k) => (
                            <span
                              key={k.word}
                              className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-700"
                            >
                              {k.word} {k.count}
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
          <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {selected.map((g) => (
              <div key={g.group_id} className="rounded-xl border border-neutral-200 bg-white p-5">
                <h2 className="text-base font-semibold">{g.name} — keyword delta</h2>
                <p className="mb-3 text-xs text-neutral-400">
                  ครึ่งแรก {g.keyword_delta.sample_size.first_half} โพสต์ · ครึ่งหลัง{" "}
                  {g.keyword_delta.sample_size.second_half} โพสต์
                </p>
                {g.keyword_delta.items.length === 0 ? (
                  <p className="text-sm text-neutral-500">ยังไม่มี keyword ใน range นี้</p>
                ) : (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-neutral-400">
                        <th className="py-1 font-medium">Keyword</th>
                        <th className="py-1 text-right font-medium">ครึ่งแรก</th>
                        <th className="py-1 text-right font-medium">ครึ่งหลัง</th>
                        <th className="w-8 py-1" />
                      </tr>
                    </thead>
                    <tbody>
                      {g.keyword_delta.items.slice(0, 5).map((i) => (
                        <tr key={i.word} className="border-t border-neutral-100">
                          <td className="py-1.5">{i.word}</td>
                          <td className="py-1.5 text-right tabular-nums">{i.first_half}</td>
                          <td className="py-1.5 text-right tabular-nums">{i.second_half}</td>
                          <td className="py-1.5 text-right">
                            <DeltaArrow f={i.first_half} s={i.second_half} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            ))}
          </section>
          <section className="rounded-xl border border-neutral-200 bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">Shared keywords</h2>
            <p className="mb-3 text-xs text-neutral-400">
              keyword ที่ปรากฏใน ≥ 2 กลุ่ม (ทุกกลุ่มใน config)
            </p>
            {data.shared_keywords.length === 0 ? (
              <p className="text-sm text-neutral-500">ไม่มี keyword ร่วมกัน</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {data.shared_keywords.map((k) => (
                  <span
                    key={k.word}
                    className="rounded-full border border-neutral-200 bg-neutral-50 px-3 py-1 text-sm"
                  >
                    <span className="font-medium">{k.word}</span>{" "}
                    <span className="tabular-nums text-neutral-500">
                      ×{k.count} · {k.in_groups} กลุ่ม
                    </span>
                  </span>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
