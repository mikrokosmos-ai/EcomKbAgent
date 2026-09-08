/**
 * 导入链路步骤条（9 步）
 */
import { Check, Circle, LoaderCircle } from "lucide-react";
import { IMPORT_STEPS } from "../../lib/nodes";
import { cn } from "../../lib/format";

type StepStatus = "pending" | "running" | "success";

function statusFor(key: string, doneList: string[], runningList: string[]): StepStatus {
  if (doneList.includes(key)) return "success";
  if (runningList.includes(key)) return "running";
  return "pending";
}

export function ImportStepRail({
  doneList,
  runningList,
}: {
  doneList: string[];
  runningList: string[];
}) {
  const known = new Set(IMPORT_STEPS.map((s) => s.key));
  const unknownDone = doneList.filter((k) => !known.has(k));

  return (
    <div className="mt-3 space-y-1">
      {IMPORT_STEPS.map((step) => {
        const status = statusFor(step.key, doneList, runningList);
        return (
          <div key={step.key} className="flex items-center gap-2 text-xs">
            <span
              className={cn(
                "grid h-5 w-5 shrink-0 place-items-center rounded-full",
                status === "pending" && "bg-ink/5 text-ink/35",
                status === "running" && "bg-brass/20 text-brass",
                status === "success" && "bg-moss/15 text-moss",
              )}
            >
              {status === "running" ? (
                <LoaderCircle className="h-3 w-3 animate-spin" aria-hidden="true" />
              ) : status === "success" ? (
                <Check className="h-3 w-3" aria-hidden="true" />
              ) : (
                <Circle className="h-3 w-3" aria-hidden="true" />
              )}
            </span>
            <span className={status === "pending" ? "text-ink/40" : "text-ink/80"}>{step.label}</span>
          </div>
        );
      })}
      {unknownDone.length > 0 && (
        <div className="pt-2 text-[11px] text-ink/40">其他事件：{unknownDone.join("、")}</div>
      )}
    </div>
  );
}
