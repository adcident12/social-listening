"use client";
import { useEffect, useState } from "react";
import { API } from "./api";

// url เปลี่ยน (filter ใหม่) = poll ใหม่ · stale = มีข้อมูลเก่าแต่ fetch ล่าสุดพัง
// (ข้อมูลเดิมยัง render อยู่ — spec §6)
export function usePoll<T>(url: string, ms = 60_000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!url) return; // url ยังไม่พร้อม (เช่น ยังไม่เลือก group) — skip poll
    let on = true;
    const load = () =>
      fetch(`${API}${url}`, { cache: "no-store" })
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json() as Promise<T>;
        })
        .then((d) => {
          if (on) {
            setData(d);
            setError(null);
          }
        })
        .catch((e) => {
          if (on) setError(String(e));
        });
    load();
    const t = setInterval(load, ms);
    return () => {
      on = false;
      clearInterval(t);
    };
  }, [url, ms]);

  return { data, error, stale: data !== null && error !== null };
}
