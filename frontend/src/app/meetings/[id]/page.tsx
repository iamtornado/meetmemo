"use client";

import { useCallback, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMeetingEvents } from "@/hooks/useMeetingEvents";
import { AppShell } from "@/components/layout/AppShell";
import { TranscriptViewer } from "@/components/transcript/TranscriptViewer";
import { SummaryPanel } from "@/components/summary/SummaryPanel";
import { AudioPlayer } from "@/components/audio/AudioPlayer";
import { Tabs } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import { PageLoading } from "@/components/ui/spinner";
import { api } from "@/lib/api";
import { format } from "date-fns";
import { ArrowLeft, Play } from "lucide-react";

export default function MeetingDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const meetingId = params.id as string;
  const [activeTab, setActiveTab] = useState("transcript");

  const { data: meeting, isLoading } = useQuery({
    queryKey: ["meeting", meetingId],
    queryFn: () => api.getMeeting(meetingId),
  });

  const { data: transcript } = useQuery({
    queryKey: ["transcript", meetingId],
    queryFn: () => api.getTranscript(meetingId),
    enabled: meeting?.status === "completed",
  });

  const { data: summary } = useQuery({
    queryKey: ["summary", meetingId],
    queryFn: () => api.getSummary(meetingId),
    enabled: meeting?.status === "completed",
  });

  const [processing, setProcessing] = useState(false);
  const [processError, setProcessError] = useState("");
  const [progressStep, setProgressStep] = useState<string | null>(null);

  const handlePipelineEvent = useCallback(
    (data: { type: string; step?: string }) => {
      if (data.type === "pipeline_progress" && data.step) {
        setProgressStep(data.step);
      }
      if (
        data.type === "pipeline_completed" ||
        data.type === "pipeline_failed"
      ) {
        setProgressStep(null);
        queryClient.invalidateQueries({ queryKey: ["meeting", meetingId] });
        queryClient.invalidateQueries({ queryKey: ["transcript", meetingId] });
        queryClient.invalidateQueries({ queryKey: ["summary", meetingId] });
      }
    },
    [meetingId, queryClient]
  );

  useMeetingEvents(
    meetingId,
    meeting?.status === "processing",
    handlePipelineEvent
  );

  const handleProcess = async () => {
    setProcessing(true);
    setProcessError("");
    try {
      await api.processMeeting(meetingId);
      queryClient.invalidateQueries({ queryKey: ["meeting", meetingId] });
      // Poll for completion
      const poll = setInterval(async () => {
        try {
          const m = await api.getMeeting(meetingId);
          if (m.status === "completed" || m.status === "failed") {
            clearInterval(poll);
            queryClient.invalidateQueries({ queryKey: ["meeting", meetingId] });
            queryClient.invalidateQueries({ queryKey: ["transcript", meetingId] });
            queryClient.invalidateQueries({ queryKey: ["summary", meetingId] });
          }
        } catch {
          // polling error, ignore
        }
      }, 3000);
    } catch (err: unknown) {
      setProcessError(err instanceof Error ? err.message : "Process failed");
    } finally {
      setProcessing(false);
    }
  };

  const handleRegenerateSummary = async () => {
    await api.regenerateSummary(meetingId);
    setTimeout(() => {
      queryClient.invalidateQueries({ queryKey: ["summary", meetingId] });
    }, 10000);
  };

  const handleSpeakerRename = async (mappings: Record<string, string>) => {
    await api.renameSpeakers(meetingId, mappings);
    queryClient.invalidateQueries({ queryKey: ["transcript", meetingId] });
    queryClient.invalidateQueries({ queryKey: ["summary", meetingId] });
  };

  if (isLoading) return <AppShell><PageLoading /></AppShell>;
  if (!meeting) return <AppShell><div className="text-center py-12 text-gray-500">Meeting not found</div></AppShell>;

  const tabs = [
    { id: "transcript", label: "Transcript" },
    { id: "summary", label: "Summary" },
    { id: "audio", label: "Audio" },
  ];

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <button
            onClick={() => router.push("/meetings")}
            className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-2"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to meetings
          </button>
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                {meeting.title || "Untitled"}
              </h1>
              <div className="flex items-center gap-3 mt-1 text-sm text-gray-500">
                <StatusBadge status={meeting.status} />
                {meeting.date && <span>{format(new Date(meeting.date), "MMM d, yyyy")}</span>}
                {meeting.duration_seconds && (
                  <span>{Math.floor(meeting.duration_seconds / 60)} min</span>
                )}
              </div>
            </div>

            {(meeting.status === "uploaded" || meeting.status === "failed") && (
              <Button onClick={handleProcess} disabled={processing} loading={processing}>
                <Play className="h-4 w-4 mr-2" />
                {processing
                  ? "Starting..."
                  : meeting.status === "failed"
                  ? "Retry"
                  : "Process"}
              </Button>
            )}

            {meeting.status === "processing" && (
              <Button disabled loading>
                {progressStep
                  ? `Processing (${progressStep})...`
                  : "Processing..."}
              </Button>
            )}

            {processError && (
              <div className="mt-2 text-sm text-red-600">{processError}</div>
            )}
          </div>
        </div>

        {/* Tabs */}
        <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} />

        {/* Tab Content */}
        {activeTab === "transcript" && (
          transcript ? (
            <TranscriptViewer
              transcript={transcript}
              onSpeakerRename={handleSpeakerRename}
            />
          ) : (
            <div className="text-center py-12 text-gray-500">
              {meeting.status === "processing"
                ? "Transcription in progress..."
                : meeting.status === "uploaded"
                ? "Click Process to start transcription"
                : "No transcript available"}
            </div>
          )
        )}

        {activeTab === "summary" && (
          summary ? (
            <SummaryPanel
              summary={summary}
              onRegenerate={handleRegenerateSummary}
            />
          ) : (
            <div className="text-center py-12 text-gray-500">
              {meeting.status === "processing"
                ? "Summary generation in progress..."
                : meeting.status === "uploaded"
                ? "Click Process to generate summary"
                : "No summary available"}
            </div>
          )
        )}

        {activeTab === "audio" && (
          <div className="space-y-4">
            <AudioPlayer meetingId={meetingId} />
            <div className="p-4 bg-gray-50 rounded-lg text-sm text-gray-500">
              <p>File: {meeting.file_format?.toUpperCase()}</p>
              <p>Size: {(meeting.file_size / (1024 * 1024)).toFixed(1)} MB</p>
            </div>
          </div>
        )}

        {/* Error message */}
        {meeting.status === "failed" && meeting.error_message && (
          <div className="p-4 bg-red-50 rounded-lg text-sm text-red-600">
            Error: {meeting.error_message}
          </div>
        )}
      </div>
    </AppShell>
  );
}
