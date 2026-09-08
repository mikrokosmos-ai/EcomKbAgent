/**
 * 问答空态
 */
import { Image as ImageIcon, MessagesSquare, Search, Sparkles, UploadCloud } from "lucide-react";
import { Link } from "react-router-dom";

const highlights = [
  { label: "混合检索", icon: Search },
  { label: "图文回链", icon: ImageIcon },
  { label: "多轮会话", icon: MessagesSquare },
];

export function EmptyChat({
  examples,
  onUseExample,
}: {
  examples: string[];
  onUseExample: (q: string) => void;
}) {
  return (
    <div className="mx-auto flex min-h-full max-w-5xl flex-col justify-center px-4 py-12">
      <div className="mb-10 max-w-3xl">
        <div className="mb-5 inline-flex items-center gap-2 border border-moss/25 bg-moss/10 px-3 py-1.5 text-sm font-semibold text-moss">
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          掌柜智库
        </div>
        <h1 className="text-balance text-4xl font-semibold leading-tight text-ink sm:text-6xl">
          商品知识库问答
        </h1>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {highlights.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.label} className="border border-ink/10 bg-white/55 px-4 py-4">
              <Icon className="mb-5 h-5 w-5 text-brass" aria-hidden="true" />
              <div className="text-sm font-semibold text-ink">{item.label}</div>
            </div>
          );
        })}
      </div>

      <div className="mt-6 grid gap-3 md:grid-cols-2">
        {examples.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => onUseExample(example)}
            className="min-h-20 border border-ink/10 bg-[#fffaf1]/75 px-4 py-4 text-left text-[15px] leading-6 text-ink transition hover:-translate-y-0.5 hover:border-moss/35 hover:bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-moss/35"
          >
            {example}
          </button>
        ))}
      </div>

      <Link
        to="/import"
        className="mt-8 inline-flex items-center gap-2 self-start border border-ink/10 bg-white/55 px-4 py-3 text-sm text-ink/70 transition hover:border-moss/35 hover:bg-white"
      >
        <UploadCloud className="h-4 w-4" aria-hidden="true" />
        知识库还是空的？前往导入文档 →
      </Link>
    </div>
  );
}
