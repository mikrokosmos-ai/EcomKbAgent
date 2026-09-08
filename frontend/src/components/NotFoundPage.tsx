/**
 * 404 页面
 */
import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-4 text-center">
      <div className="text-5xl font-semibold text-ink">404</div>
      <p className="text-sm text-ink/60">页面不存在</p>
      <div className="flex gap-3">
        <Link to="/chat" className="border border-ink/15 bg-white/60 px-4 py-2 text-sm text-ink/70 transition hover:bg-white">
          返回问答
        </Link>
        <Link to="/import" className="border border-ink/15 bg-white/60 px-4 py-2 text-sm text-ink/70 transition hover:bg-white">
          去导入
        </Link>
      </div>
    </div>
  );
}
