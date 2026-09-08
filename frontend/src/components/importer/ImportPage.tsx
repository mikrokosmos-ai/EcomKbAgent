/**
 * 知识导入页
 */
import { useCallback } from "react";
import { useNavigate, useOutletContext, useSearchParams } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useSession } from "../../store/SessionProvider";
import { useImportTasks } from "../../hooks/useImportTasks";
import { TopBar } from "../layout/TopBar";
import { UploadDropzone } from "./UploadDropzone";
import { TaskCard } from "./TaskCard";
import { TaskSummaryBar } from "./TaskSummaryBar";
import { ContextBar } from "./ContextBar";
import { useToast } from "../ui/Toast";

export function ImportPage() {
  const { onMenu } = useOutletContext<{ onMenu: () => void }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { tasks, upload, removeTask } = useImportTasks();
  const { activeId } = useSession();
  const toast = useToast();

  const q = searchParams.get("q");

  const doneCount = tasks.filter((t) => t.phase === "completed").length;
  const runningCount = tasks.filter((t) => t.phase === "processing" || t.phase === "uploading").length;
  const failedCount = tasks.filter((t) => t.phase === "failed").length;
  const lastCompleted = [...tasks].reverse().find((t) => t.phase === "completed");

  const goChat = useCallback(() => {
    const hint = lastCompleted?.fileName;
    const chatTo = activeId ? `/chat/${activeId}` : "/chat";
    navigate(`${chatTo}${hint ? `?hint=${encodeURIComponent(hint)}` : ""}`);
  }, [navigate, lastCompleted, activeId]);

  const onFiles = useCallback(
    (files: FileList | File[]) => {
      for (const f of Array.from(files)) {
        if (!/\.(pdf|md)$/i.test(f.name)) {
          toast("error", `跳过非 PDF/MD 文件：${f.name}`);
          continue;
        }
        if (f.size > 100 * 1024 * 1024) {
          toast("error", `${f.name} 超过 100MB 上限`);
          continue;
        }
        upload(f);
      }
    },
    [upload, toast],
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <TopBar
        title="知识导入"
        subtitle="MinerU · BGE-M3 · Milvus"
        onMenu={onMenu}
        actions={
          <button
            type="button"
            onClick={goChat}
            className="inline-flex h-9 items-center gap-1.5 border border-ink/15 bg-white/60 px-3 text-sm text-ink/70 transition hover:bg-white"
          >
            <span>去问答</span>
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </button>
        }
      />

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="mx-auto flex max-w-4xl flex-col gap-4 px-4 py-6 lg:px-8">
          {q && (
            <ContextBar
              question={q}
              onClear={() => {
                const next = new URLSearchParams(searchParams);
                next.delete("q");
                setSearchParams(next, { replace: true });
              }}
            />
          )}

          <UploadDropzone onFiles={onFiles} />

          <TaskSummaryBar
            total={tasks.length}
            done={doneCount}
            running={runningCount}
            failed={failedCount}
            onGoChat={goChat}
          />

          {tasks.length === 0 ? (
            <div className="flex flex-col items-center gap-2 border border-dashed border-ink/15 bg-white/40 px-4 py-12 text-center text-sm text-ink/50">
              <span>暂无导入任务</span>
              <span className="text-xs">上传 PDF / Markdown 手册，自动完成解析、图片理解、向量化入库。</span>
            </div>
          ) : (
            <div className="space-y-3">
              {tasks.map((t) => (
                <TaskCard key={t.fileId} task={t} onRemove={removeTask} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
