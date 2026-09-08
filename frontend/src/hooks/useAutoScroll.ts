/**
 * 自动滚动：内容增长时吸底，用户上滑后暂停
 */
import { useCallback, useEffect, useRef, useState } from "react";

export function useAutoScroll<T>(dep: T) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || paused) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [dep, paused]);

  const onScroll = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    setPaused(!nearBottom);
  }, []);

  return { ref, onScroll, paused };
}
