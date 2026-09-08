/**
 * 导入任务轮询：全局常驻（AppShell 挂载），切走路由后继续轮询。
 */
import { useEffect, useRef } from "react";
import { useSession } from "../store/SessionProvider";
import { getTaskStatus } from "../lib/kbApi";
import { importProgress } from "../lib/nodes";

export function useImportPoller() {
  const { tasks, patchTask } = useSession();
  const processingIds = tasks
    .filter((t) => t.phase === "processing" && t.id)
    .map((t) => t.id)
    .sort()
    .join(",");
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    if (!processingIds) {
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    const tick = async () => {
      const ids = processingIds.split(",").filter(Boolean);
      for (const id of ids) {
        try {
          const res = await getTaskStatus(id);
          if (res.status === "completed") {
            patchTask(id, {
              phase: "completed",
              status: "completed",
              progress: 100,
              doneList: res.done_list,
              runningList: [],
            });
          } else if (res.status === "failed") {
            patchTask(id, { phase: "failed", status: "failed", doneList: res.done_list, runningList: [] });
          } else {
            patchTask(id, {
              phase: "processing",
              status: res.status,
              progress: importProgress(res.done_list),
              doneList: res.done_list,
              runningList: res.running_list,
            });
          }
        } catch {
          // 单次轮询失败忽略，等待下一轮
        }
      }
    };

    if (intervalRef.current === null) {
      tick();
      intervalRef.current = window.setInterval(tick, 2000);
    }

    return () => {
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [processingIds, patchTask]);
}
