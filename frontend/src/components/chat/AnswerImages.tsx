/**
 * 参考图片展示
 */
import { ExternalLink } from "lucide-react";

export function AnswerImages({ urls }: { urls: string[] }) {
  return (
    <div className="mt-3 flex flex-col gap-3">
      {urls.map((url) => (
        <div key={url} className="flex flex-col gap-1">
          <img
            src={url}
            alt="参考图片"
            loading="lazy"
            referrerPolicy="no-referrer"
            className="block max-h-[600px] w-auto max-w-full border border-ink/10 bg-white shadow-line"
            onError={(e) => {
              e.currentTarget.style.display = "none";
            }}
          />
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 break-all text-xs text-ink/45 transition hover:text-ink"
          >
            <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
            {url}
          </a>
        </div>
      ))}
    </div>
  );
}
