/**
 * 确认弹窗
 */
import { useEffect, type ReactNode } from "react";

export function Modal({
  open,
  title,
  description,
  onClose,
  onConfirm,
  confirmLabel = "确认",
  danger = false,
}: {
  open: boolean;
  title: string;
  description: ReactNode;
  onClose: () => void;
  onConfirm: () => void;
  confirmLabel?: string;
  danger?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-[min(92vw,380px)] border border-ink/15 bg-parchment p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 text-sm font-semibold text-ink">{title}</div>
        <div className="mb-5 text-sm leading-6 text-ink/70">{description}</div>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="h-9 border border-ink/15 bg-white/60 px-4 text-sm text-ink/70 transition hover:bg-white"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={
              danger
                ? "h-9 bg-tomato px-4 text-sm font-semibold text-white transition hover:bg-tomato/85"
                : "h-9 bg-ink px-4 text-sm font-semibold text-parchment transition hover:bg-soot"
            }
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
