/**
 * 查询链路流程图（仿 EcomQueryAgent StepRail）
 * 按 LangGraph 真实拓扑：三路召回 → RRF → 重排 → 生成答案，含「需澄清」短路支线。
 */
import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, ChevronUp, Circle, LoaderCircle, X } from "lucide-react";
import { cn } from "../../lib/format";
import {
  QUERY_CANVAS_H,
  QUERY_CANVAS_W,
  QUERY_FLOW_CONNECTORS,
  QUERY_FLOW_NODES,
  QUERY_FLOW_SHORT_CIRCUIT,
} from "../../lib/nodes";
import type { ProgressStatus, StepState } from "../../types/query";

type FlowStatus = ProgressStatus | "pending";

function getStatusMap(steps: StepState[]) {
  return steps.reduce<Record<string, StepState>>((map, item) => {
    map[item.step] = item;
    return map;
  }, {});
}

function statusFor(step: string, map: Record<string, StepState>): FlowStatus {
  return map[step]?.status ?? "pending";
}

function NodeIcon({ status }: { status: FlowStatus }) {
  if (status === "running") return <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />;
  if (status === "success") return <Check className="h-3.5 w-3.5" aria-hidden="true" />;
  if (status === "error") return <X className="h-3.5 w-3.5" aria-hidden="true" />;
  return <Circle className="h-3.5 w-3.5" aria-hidden="true" />;
}

function FlowNodeCard({ node, status }: { node: { step: string; x: number; y: number; w?: number }; status: FlowStatus }) {
  const width = node.w ?? 156;
  return (
    <div className="absolute -translate-x-1/2" style={{ left: node.x, top: node.y, width }}>
      <div
        className={cn(
          "flex h-10 items-center gap-2 border px-3 text-sm font-semibold shadow-line transition",
          status === "pending" && "border-ink/10 bg-white/55 text-ink/45",
          status === "running" && "border-brass/45 bg-brass/15 text-ink",
          status === "success" && "border-moss/25 bg-moss/10 text-ink",
          status === "error" && "border-tomato/35 bg-tomato/10 text-tomato",
        )}
      >
        <span
          className={cn(
            "grid h-6 w-6 shrink-0 place-items-center rounded-full",
            status === "pending" && "bg-ink/5 text-ink/35",
            status === "running" && "bg-brass/20 text-brass",
            status === "success" && "bg-moss/15 text-moss",
            status === "error" && "bg-tomato/15 text-tomato",
          )}
        >
          <NodeIcon status={status} />
        </span>
        <span className="min-w-0 flex-1 truncate">{node.step}</span>
      </div>
    </div>
  );
}

export function PipelineFlow({ steps = [] }: { steps?: StepState[] }) {
  if (steps.length === 0) return null;

  const [expanded, setExpanded] = useState(true);
  const [scale, setScale] = useState(1);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!expanded) return;
    const el = containerRef.current;
    if (!el) return;
    const update = () => {
      const width = el.clientWidth;
      setScale(width > 0 ? Math.min(1, width / QUERY_CANVAS_W) : 1);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [expanded]);

  const statusMap = getStatusMap(steps);
  const runningStep = steps.find((item) => item.status === "running");
  const doneCount = steps.filter((item) => item.status === "success").length;

  // 澄清短路判定：已生成答案但未进入检索（无切片搜索/倒排融合）
  const shortCircuited =
    statusMap["生成答案"]?.status === "success" &&
    statusMap["切片搜索"]?.status !== "success" &&
    statusMap["倒排融合"]?.status !== "success";

  return (
    <section className="mt-4 border border-ink/10 bg-white/40 px-3 py-4 shadow-line">
      <div className="mb-3 flex items-center justify-between gap-3 px-1">
        <div className="flex items-center gap-2">
          <div className="text-sm font-semibold text-ink">执行流程</div>
          <div className="text-xs text-ink/45">LangGraph · RRF + Rerank</div>
        </div>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="inline-flex items-center gap-1 rounded-full border border-ink/10 px-2.5 py-1 text-xs text-ink/55 transition hover:border-moss/35 hover:bg-moss/10 hover:text-ink"
        >
          {expanded ? (
            <>
              收起
              <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
            </>
          ) : (
            <>
              展开
              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
            </>
          )}
        </button>
      </div>

      {expanded ? (
        <div ref={containerRef} className="overflow-hidden">
          <div style={{ height: QUERY_CANVAS_H * scale }}>
            <div
              className="relative"
              style={{
                width: QUERY_CANVAS_W,
                height: QUERY_CANVAS_H,
                transform: `scale(${scale})`,
                transformOrigin: "top left",
              }}
            >
              <svg
                className="pointer-events-none absolute inset-0 h-full w-full"
                viewBox={`0 0 ${QUERY_CANVAS_W} ${QUERY_CANVAS_H}`}
                fill="none"
                aria-hidden="true"
              >
                <defs>
                  <marker id="flow-arrow" markerHeight="8" markerWidth="8" orient="auto" refX="6" refY="4">
                    <path d="M0 0 L8 4 L0 8 Z" fill="rgba(32,32,29,0.58)" />
                  </marker>
                </defs>
                {QUERY_FLOW_CONNECTORS.map((path) => (
                  <path key={path} d={path} stroke="rgba(32,32,29,0.5)" strokeWidth="1.5" markerEnd="url(#flow-arrow)" />
                ))}
                {shortCircuited && (
                  <path
                    d={QUERY_FLOW_SHORT_CIRCUIT}
                    stroke="rgba(32,32,29,0.5)"
                    strokeWidth="1.5"
                    strokeDasharray="4 4"
                    markerEnd="url(#flow-arrow)"
                  />
                )}
                {shortCircuited && (
                  <text x="560" y="70" fill="rgba(32,32,29,0.55)" fontSize="12" fontWeight="500" textAnchor="middle">
                    需澄清
                  </text>
                )}
              </svg>

              {QUERY_FLOW_NODES.map((node) => (
                <FlowNodeCard key={node.step} node={node} status={statusFor(node.step, statusMap)} />
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="px-1 text-xs text-ink/50">
          {runningStep ? `正在执行：${runningStep.step}` : `已完成 ${doneCount} 个步骤`}
        </div>
      )}
    </section>
  );
}
