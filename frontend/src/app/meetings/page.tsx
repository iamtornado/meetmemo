"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { MeetingTable } from "@/components/meetings/MeetingTable";
import { UploadDialog } from "@/components/meetings/UploadDialog";
import { Button } from "@/components/ui/button";
import { PageLoading } from "@/components/ui/spinner";
import { api } from "@/lib/api";
import { Plus } from "lucide-react";

export default function MeetingsPage() {
  const [uploadOpen, setUploadOpen] = useState(false);
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["meetings", page],
    queryFn: () => api.listMeetings({ page, page_size: 20 }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteMeeting(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["meetings"] }),
  });

  if (isLoading) return <AppShell><PageLoading /></AppShell>;

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Meetings</h1>
            <p className="text-sm text-gray-500 mt-1">
              {data?.total || 0} total meetings
            </p>
          </div>
          <Button onClick={() => setUploadOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Upload
          </Button>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
          <MeetingTable
            meetings={data?.items || []}
            onDelete={(id) => {
              if (confirm("Delete this meeting?")) deleteMutation.mutate(id);
            }}
          />
        </div>

        {/* Pagination */}
        {data && data.total_pages > 1 && (
          <div className="flex items-center justify-center gap-2 mt-6">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <span className="text-sm text-gray-500">
              Page {page} of {data.total_pages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= data.total_pages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        )}
      </div>

      <UploadDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onSuccess={() => queryClient.invalidateQueries({ queryKey: ["meetings"] })}
      />
    </AppShell>
  );
}
