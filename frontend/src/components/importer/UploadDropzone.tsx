/**
 * 上传拖拽区
 */
import { useRef, useState } from "react";
import { CloudUpload } from "lucide-react";
import { cn } from "../../lib/format";

export function UploadDropzone({ onFiles }: { onFiles: (files: FileList | File[]) => void }) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragging, setDragging] = useState(false);

  return (
    <div
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-2 border-2 border-dashed px-6 py-10 text-center transition",
        dragging
          ? "border-moss/60 bg-moss/10"
          : "border-ink/15 bg-white/40 hover:border-moss/35 hover:bg-white/60",
      )}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        e.preventDefault();
        setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (e.dataTransfer.files.length) onFiles(e.dataTransfer.files);
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          inputRef.current?.click();
        }
      }}
    >
      <CloudUpload className="h-8 w-8 text-brass" aria-hidden="true" />
      <div className="text-sm font-semibold text-ink">点击或拖拽文件到此处</div>
      <div className="text-xs text-ink/45">支持 PDF / Markdown，单个不超过 100MB，可多次上传</div>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.md"
        multiple
        hidden
        onChange={(e) => {
          if (e.target.files?.length) onFiles(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}
