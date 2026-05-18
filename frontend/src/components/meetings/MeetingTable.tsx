"use client";

import { useRouter } from "next/navigation";
import type { Meeting } from "@/types";
import { StatusBadge } from "@/components/ui/badge";
import { formatDuration, formatFileSize } from "@/lib/utils";
import { format } from "date-fns";

export function MeetingTable({
  meetings,
  onDelete,
}: {
  meetings: Meeting[];
  onDelete?: (id: string) => void;
}) {
  const router = useRouter();

  if (meetings.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        <p className="text-lg">No meetings yet</p>
        <p className="text-sm mt-1">Upload a recording to get started</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200">
            <th className="text-left py-3 px-4 font-medium text-gray-500">Title</th>
            <th className="text-left py-3 px-4 font-medium text-gray-500">Date</th>
            <th className="text-left py-3 px-4 font-medium text-gray-500">Duration</th>
            <th className="text-left py-3 px-4 font-medium text-gray-500">Size</th>
            <th className="text-left py-3 px-4 font-medium text-gray-500">Status</th>
            <th className="text-right py-3 px-4 font-medium text-gray-500">Actions</th>
          </tr>
        </thead>
        <tbody>
          {meetings.map((m) => (
            <tr
              key={m.id}
              className="border-b border-gray-100 hover:bg-gray-50 cursor-pointer"
              onClick={() => router.push(`/meetings/${m.id}`)}
            >
              <td className="py-3 px-4 font-medium text-gray-900">
                {m.title || "Untitled"}
              </td>
              <td className="py-3 px-4 text-gray-500">
                {m.date ? format(new Date(m.date), "MMM d, yyyy") : "-"}
              </td>
              <td className="py-3 px-4 text-gray-500">
                {m.duration_seconds ? formatDuration(m.duration_seconds) : "-"}
              </td>
              <td className="py-3 px-4 text-gray-500">{formatFileSize(m.file_size)}</td>
              <td className="py-3 px-4">
                <StatusBadge status={m.status} />
              </td>
              <td className="py-3 px-4 text-right">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete?.(m.id);
                  }}
                  className="text-red-500 hover:text-red-700 text-sm"
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
