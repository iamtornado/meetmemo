import { cn } from "@/lib/utils";

const badgeVariants: Record<string, string> = {
  default: "bg-blue-100 text-blue-800",
  success: "bg-green-100 text-green-800",
  warning: "bg-yellow-100 text-yellow-800",
  danger: "bg-red-100 text-red-800",
  info: "bg-gray-100 text-gray-800",
};

export function Badge({
  className,
  variant = "default",
  children,
}: {
  className?: string;
  variant?: keyof typeof badgeVariants;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        badgeVariants[variant],
        className
      )}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { label: string; variant: "default" | "success" | "warning" | "danger" | "info" }> = {
    uploading: { label: "Uploading", variant: "info" },
    uploaded: { label: "Uploaded", variant: "info" },
    processing: { label: "Processing", variant: "warning" },
    completed: { label: "Completed", variant: "success" },
    failed: { label: "Failed", variant: "danger" },
    cancelled: { label: "Cancelled", variant: "default" },
  };
  const c = config[status] || { label: status, variant: "info" as const };
  return <Badge variant={c.variant}>{c.label}</Badge>;
}
