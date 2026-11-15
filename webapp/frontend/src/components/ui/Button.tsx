import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "../../lib/utils";

type Variant = "default" | "primary" | "ghost" | "danger";
type Size = "md" | "sm" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

const VARIANT_CLASS: Record<Variant, string> = {
  default: "btn",
  primary: "btn btn-primary",
  ghost: "btn btn-ghost",
  danger: "btn btn-danger",
};

export function Button({
  variant = "default",
  size = "md",
  loading = false,
  icon,
  className,
  children,
  disabled,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        VARIANT_CLASS[variant],
        size === "sm" && "btn-sm",
        size === "lg" && "btn-lg",
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <Loader2 size={14} className="animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  children: ReactNode;
}

export function IconButton({ label, className, children, type = "button", ...rest }: IconButtonProps) {
  return (
    <button
      type={type}
      className={cn("btn btn-icon", className)}
      aria-label={label}
      title={label}
      {...rest}
    >
      {children}
    </button>
  );
}
