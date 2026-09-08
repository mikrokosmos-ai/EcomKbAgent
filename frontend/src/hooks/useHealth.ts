/**
 * 健康检查心跳
 */
import { useEffect, useState } from "react";
import { health } from "../lib/kbApi";

export function useHealth(intervalMs = 5000) {
  const [online, setOnline] = useState(false);

  useEffect(() => {
    let alive = true;
    const check = async () => {
      try {
        await health();
        if (alive) setOnline(true);
      } catch {
        if (alive) setOnline(false);
      }
    };
    check();
    const t = window.setInterval(check, intervalMs);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, [intervalMs]);

  return online;
}
