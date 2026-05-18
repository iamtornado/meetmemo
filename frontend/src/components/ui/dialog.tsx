"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

export function Dialog({
  open,
  onClose,
  children,
  title,
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  title?: string;
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50" onClick={onClose} />
      <div
        className={cn(
          "relative z-50 w-full max-w-lg rounded-xl bg-white p-6 shadow-2xl mx-4",
          "max-h-[85vh] overflow-y-auto"
        )}
      >
        <div className="flex items-center justify-between mb-4">
          {title && <h2 className="text-lg font-semibold">{title}</h2>}
          <button onClick={onClose} className="p-1 rounded-md hover:bg-gray-100">
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
