/**
 * 流式输出开关
 */
import { useSession } from "../../store/SessionProvider";

export function StreamToggle() {
  const { streamEnabled, setStreamEnabled } = useSession();
  return (
    <label className="flex cursor-pointer select-none items-center gap-1.5 text-xs text-ink/60">
      <input
        type="checkbox"
        checked={streamEnabled}
        onChange={(e) => setStreamEnabled(e.target.checked)}
        className="h-3.5 w-3.5 accent-[#2f6b4f]"
      />
      流式输出
    </label>
  );
}
