/**
 * 导入任务：上传单个文件 + 轮询进度
 */
import { useCallback } from "react";
import { useSession } from "../store/SessionProvider";
import { uploadFile } from "../lib/kbApi";
import { makeId } from "../lib/session";
import type { ImportTask } from "../types/importer";

export function useImportTasks() {
  const { tasks, addTask, patchTask, removeTask } = useSession();

  const upload = useCallback(
    async (file: File) => {
      const fileId = makeId();
      const task: ImportTask = {
        id: "",
        fileId,
        fileName: file.name,
        fileSize: file.size,
        phase: "uploading",
        status: "processing",
        progress: 0,
        doneList: [],
        runningList: ["开始上传文件"],
      };
      addTask(task);

      try {
        const res = await uploadFile(file);
        const taskId = res.task_ids?.[0] ?? "";
        if (!taskId) throw new Error("后端未返回任务 ID");
        patchTask(fileId, {
          id: taskId,
          phase: "processing",
          progress: 5,
          doneList: ["开始上传文件"],
          runningList: [],
        });
      } catch (err) {
        patchTask(fileId, {
          phase: "failed",
          status: "failed",
          runningList: [],
          error: err instanceof Error ? err.message : String(err),
        });
      }
    },
    [addTask, patchTask],
  );

  return { tasks, upload, removeTask };
}
