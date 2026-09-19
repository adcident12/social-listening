"use client";
import { useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import GroupSelect from "@/components/GroupSelect";
import { type TimelineBucket, type TimelineResponse } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";
import { useGroupFilter } from "@/lib/useGroupFilter";

const DAYS = [7, 14, 30, 60, 90] as const;

function Tip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: TimelineBucket & { label: string } }[];
}) {
  if (!active || !payload?.length) return null;
  const b = payload[0].payload;
  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-3 text-sm shadow-md">
      <p className="font-medium">{b.date}</p>
      <p className="text-neutral-600">โพสต์: {b.posts}</p>
      <p className="text-neutral-600">Engagement: {b.engagement}</p>
      {b.top_keyword && (
        <p className="text-neutral-500">
          Top keyword: <span className="font-medium text-neutral-700">{b.top_keyword}</span>
        </p>
      )}
    </div>
  );
}

export default function Timeline() {
  const [days, setDays] = useState(30);
  const { groups, gid, setGroup, error: groupsError } = useGroupFilter();

  const { data, error, stale } = usePoll<TimelineResponse>(
    gid ? `/stats/timeline?days=${days}&group_id=${gid}` : "",
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

  const chartData = (data?.buckets ?? []).map((b) => ({
    ...b,
    label: `${Number(b.date.slice(8, 10))}/${Number(b.date.slice(5, 7))}`,
  }));
  const allZero = data !== null && data.buckets.every((b) => b.posts === 0);

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
        <h1 className="text-2xl font-bold tracking-tight">Timeline</h1>
        <div className="flex flex-wrap items-center gap-3">
          <GroupSelect groups={groups} value={gid} onChange={setGroup} />
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
                {d}
              </button>
            ))}
          </div>
        </div>
      </header>
      {!data ? (
        error ? (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            เชื่อมต่อ API ไม่ได้ ({error}) — รัน{" "}
            <code className="rounded bg-red-100 px-1">
              python -m uvicorn api:app --port 8000
            </code>
          </div>
        ) : (
          <div className="h-96 animate-pulse rounded-xl bg-neutral-100" />
        )
      ) : (
        <section className="rounded-xl border border-neutral-200 bg-white p-5">
          <div className="mb-4 flex items-baseline justify-between">
            <h2 className="text-lg font-semibold">
              {data.group} · รายวัน ({data.days} วัน, {data.timezone})
            </h2>
          </div>
          {allZero ? (
            <div className="flex h-72 items-center justify-center text-sm text-neutral-500">
              ยังไม่มีโพสต์ใน range นี้
            </div>
          ) : (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                  <XAxis dataKey="label" tick={{ fontSize: 12 }} minTickGap={24} />
                  <YAxis
                    yAxisId="posts"
                    allowDecimals={false}
                    tick={{ fontSize: 12 }}
                    width={32}
                  />
                  <YAxis
                    yAxisId="eng"
                    orientation="right"
                    tick={{ fontSize: 12 }}
                    width={40}
                  />
                  <Tooltip content={<Tip />} />
                  <Legend />
                  <Bar
                    yAxisId="posts"
                    dataKey="posts"
                    name="โพสต์"
                    fill="#6366f1"
                    radius={[3, 3, 0, 0]}
                  />
                  <Line
                    yAxisId="eng"
                    dataKey="engagement"
                    name="Engagement"
                    stroke="#f59e0b"
                    strokeWidth={2}
                    dot={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
