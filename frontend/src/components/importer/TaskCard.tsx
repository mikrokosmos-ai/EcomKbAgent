/**
 * 单文件导入任务卡片
 */
import { useState } from "react";
import { ChevronDown, ChevronUp, FileText, Trash2 } from "lucide-react";
import { Badge, type BadgeTone } from "../ui/Badge";
import { ProgressBar } from "../ui/ProgressBar";
import { ImportStepRail } from "./ImportStepRail";
import { formatBytes } from "../../lib/format";
import type { ImportTask } from "../../types/importer";

const phaseMeta: Record<ImportTask["phase"], { label: string; tone: BadgeTone }> = {
  validating: { label: "校验中", tone: "neutral" },
  uploading: { label: "上传中", tone: "running" },
  processing: { label: "处理中", tone: "running" },
  completed: { label: "已完成", tone: "success" },
  failed: { label: "失败", tone: "error" },
};

export function TaskCard({
  task,
  onRemove,
}: {
  task: ImportTask;
  onRemove: (key: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const meta = phaseMeta[task.phase];

  return (
    <div className="border border-ink/10 bg-white/55 shadow-line">
      <div className="flex items-center gap-3 px-4 py-3">
        <FileText className="h-5 w-5 shrink-0 text-ink/45" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-ink">{task.fileName}</div>
          <div className="text-xs text-ink/45">{formatBytes(task.fileSize)}</div>
        </div>
        <Badge tone={meta.tone}>{meta.label}</Badge>
        <button
          type="button"
          onClick={() => onRemove(task.fileId)}
          className="grid h-8 w-8 shrink-0 place-items-center text-ink/40 transition hover:text-tomato"
          title="移除"
          aria-label="移除"
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      {task.phase !== "failed" && (
        <div className="px-4 pb-3">
          <ProgressBar value={task.progress} tone={task.phase === "completed" ? "moss" : "brass"} />
        </div>
      )}

      {task.error && (
        <div className="mx-4 mb-3 border border-tomato/30 bg-tomato/10 px-3 py-2 text-sm text-tomato">
          {task.error}
        </div>
      )}

      {(task.phase === "processing" || task.phase === "completed") && (
        <div className="border-t border-ink/10 px-4 py-3">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="inline-flex items-center gap-1 text-xs text-ink/55 transition hover:text-ink"
          >
            {open ? (
              <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            日志（已完成 {task.doneList.length}，进行中 {task.runningList.length}）
          </button>
          {open && <ImportStepRail doneList={task.doneList} runningList={task.runningList} />}
        </div>
      )}
    </div>
  );
}
