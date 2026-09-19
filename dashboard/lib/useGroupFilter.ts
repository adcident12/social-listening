"use client";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { API, type Group, type GroupsResponse } from "./api";

// กลุ่มที่เลือก = URL param ?group_id= (shareable, refresh แล้วจำ)
// ไม่มี param = กลุ่มแรกใน config.toml (default เดิมของ API)
export function useGroupFilter() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [groups, setGroups] = useState<Group[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/groups`, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<GroupsResponse>;
      })
      .then((d) => setGroups(d.groups))
      .catch((e) => setError(String(e)));
  }, []);

  const first = groups[0]?.group_id ?? "";
  const gid = searchParams.get("group_id") ?? first;

  const setGroup = (value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value && value !== first) params.set("group_id", value);
    else params.delete("group_id");
    const qs = params.toString();
    router.replace(`${window.location.pathname}${qs ? `?${qs}` : ""}`, { scroll: false });
  };

  return { groups, gid, setGroup, error };
}
