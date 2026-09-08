/**
 * 通用按钮
 */
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { LoaderCircle } from "lucide-react";
import { cn } from "../../lib/format";

type Variant = "primary" | "ghost" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
  icon?: ReactNode;
}

const variants: Record<Variant, string> = {
  primary: "bg-ink text-parchment hover:bg-soot disabled:bg-ink/25",
  ghost: "border border-ink/15 bg-white/60 text-ink/70 hover:bg-white disabled:opacity-50",
  danger: "bg-tomato text-white hover:bg-tomato/85 disabled:bg-tomato/40",
};

export function Button({
  variant = "primary",
  loading = false,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex h-9 items-center justify-center gap-2 px-4 text-sm font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-moss/40 disabled:cursor-not-allowed",
        variants[variant],
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" /> : icon}
      {children}
    </button>
  );
}
