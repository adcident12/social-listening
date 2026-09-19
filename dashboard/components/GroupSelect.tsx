"use client";
import { type Group } from "@/lib/api";

const selectCls =
  "rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm transition-colors focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100";

export default function GroupSelect({
  groups,
  value,
  onChange,
}: {
  groups: Group[];
  value: string;
  onChange: (gid: string) => void;
}) {
  if (groups.length === 0) return null;
  return (
    <select
      className={selectCls}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {groups.map((g) => (
        <option key={g.group_id} value={g.group_id}>
          {g.name}
        </option>
      ))}
    </select>
  );
}
