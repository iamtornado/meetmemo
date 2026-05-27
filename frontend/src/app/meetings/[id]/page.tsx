"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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

  const {
    data: transcript,
    isLoading: transcriptLoading,
    isFetching: transcriptFetching,
    isError: transcriptError,
  } = useQuery({
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
  const [exportingDocx, setExportingDocx] = useState(false);
  const [regeneratingSummary, setRegeneratingSummary] = useState(false);
  const [regenerateMessage, setRegenerateMessage] = useState("");
  const [processError, setProcessError] = useState("");
  const [progressStep, setProgressStep] = useState<string | null>(null);
  const [pipelineActive, setPipelineActive] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isProcessing =
    meeting?.status === "processing" || pipelineActive;

  useEffect(() => {
    if (meeting?.status === "processing") {
      setPipelineActive(true);
    }
    if (meeting?.status === "completed" || meeting?.status === "failed") {
      setPipelineActive(false);
    }
  }, [meeting?.status]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const refreshMeetingData = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["meeting", meetingId] });
    queryClient.invalidateQueries({ queryKey: ["transcript", meetingId] });
    queryClient.invalidateQueries({ queryKey: ["summary", meetingId] });
  }, [meetingId, queryClient]);

  const handlePipelineEvent = useCallback(
    (data: { type: string; step?: string }) => {
      if (data.type === "pipeline_started") {
        setPipelineActive(true);
        setProgressStep(null);
        refreshMeetingData();
      }
      if (data.type === "pipeline_progress" && data.step) {
        setPipelineActive(true);
        setProgressStep(data.step);
      }
      if (data.type === "pipeline_completed" || data.type === "pipeline_failed") {
        setPipelineActive(false);
        setProgressStep(null);
        refreshMeetingData();
      }
    },
    [refreshMeetingData]
  );

  useMeetingEvents(meetingId, isProcessing, handlePipelineEvent);

  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const m = await api.getMeeting(meetingId);
        queryClient.setQueryData(["meeting", meetingId], m);
        if (m.status === "processing") {
          setPipelineActive(true);
        }
        if (m.status === "completed" || m.status === "failed") {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setPipelineActive(false);
          refreshMeetingData();
        }
      } catch {
        /* ignore transient poll errors */
      }
    }, 2000);
  }, [meetingId, queryClient, refreshMeetingData]);

  const handleProcess = async () => {
    setProcessing(true);
    setProcessError("");
    setPipelineActive(true);
    try {
      await api.processMeeting(meetingId);
      await queryClient.refetchQueries({ queryKey: ["meeting", meetingId] });
      startPolling();
    } catch (err: unknown) {
      setProcessError(err instanceof Error ? err.message : "Process failed");
      setPipelineActive(false);
    } finally {
      setProcessing(false);
    }
  };

  const summaryPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (summaryPollRef.current) clearInterval(summaryPollRef.current);
    };
  }, []);

  const stopSummaryPoll = useCallback(() => {
    if (summaryPollRef.current) {
      clearInterval(summaryPollRef.current);
      summaryPollRef.current = null;
    }
  }, []);

  const startSummaryPoll = useCallback(
    (baselineUpdatedAt: string | undefined) => {
      stopSummaryPoll();
      let attempts = 0;
      const maxAttempts = 120; // ~10 min at 5s interval

      summaryPollRef.current = setInterval(async () => {
        attempts += 1;
        try {
          const next = await api.getSummary(meetingId);
          queryClient.setQueryData(["summary", meetingId], next);
          const updated =
            baselineUpdatedAt &&
            next.updated_at &&
            next.updated_at !== baselineUpdatedAt;
          if (next.formal_minutes || updated) {
            stopSummaryPoll();
            setRegeneratingSummary(false);
            setRegenerateMessage(
              next.formal_minutes
                ? "纪要已生成"
                : "摘要已更新（若仍无纪要，请查看 worker 日志）"
            );
            setTimeout(() => setRegenerateMessage(""), 8000);
          } else if (attempts >= maxAttempts) {
            stopSummaryPoll();
            setRegeneratingSummary(false);
            setProcessError(
              "生成时间较长仍未完成，请稍后在纪要页刷新查看，或联系管理员查看 worker 日志"
            );
          }
        } catch {
          /* ignore transient poll errors */
        }
      }, 5000);
    },
    [meetingId, queryClient, stopSummaryPoll]
  );

  const handleRegenerateSummary = async () => {
    setProcessError("");
    setRegenerateMessage("");
    setRegeneratingSummary(true);
    const baselineUpdatedAt = summary?.updated_at;
    try {
      await api.regenerateSummary(meetingId);
      setRegenerateMessage(
        "已提交后台任务，正在重新生成摘要与会议纪要（长会议约需 5–15 分钟）…"
      );
      startSummaryPoll(baselineUpdatedAt);
    } catch (err: unknown) {
      setRegeneratingSummary(false);
      stopSummaryPoll();
      setProcessError(
        err instanceof Error ? err.message : "重新生成请求失败，请确认已登录且服务正常"
      );
    }
  };

  const handleUpdateMeetingMeta = async (data: {
    host?: string | null;
    recorder_unit?: string | null;
    meeting_location?: string | null;
  }) => {
    const updated = await api.updateMeeting(meetingId, data);
    queryClient.setQueryData(["meeting", meetingId], updated);
  };

  const handleExportMinutesDocx = async () => {
    const base = (meeting?.title || "会议纪要").replace(/[^\w\u4e00-\u9fff\-]+/g, "_");
    await api.exportFormalMinutesDocx(meetingId, `${base}-纪要.docx`);
  };

  const handleSpeakerRename = async (mappings: Record<string, string>) => {
    await api.renameSpeakers(meetingId, mappings);
    queryClient.invalidateQueries({ queryKey: ["transcript", meetingId] });
    queryClient.invalidateQueries({ queryKey: ["summary", meetingId] });
  };

  const handleExportTranscriptDocx = async () => {
    setExportingDocx(true);
    try {
      const base = (meeting?.title || "transcript").replace(/[^\w\u4e00-\u9fff\-]+/g, "_");
      await api.exportTranscriptDocx(meetingId, `${base}.docx`);
    } catch (err: unknown) {
      setProcessError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExportingDocx(false);
    }
  };

  if (isLoading) return <AppShell><PageLoading /></AppShell>;
  if (!meeting) return <AppShell><div className="text-center py-12 text-gray-500">Meeting not found</div></AppShell>;

  const tabs = [
    { id: "transcript", label: "Transcript" },
    { id: "summary", label: "纪要 / Summary" },
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

            {(meeting.status === "uploaded" || meeting.status === "failed") &&
              !isProcessing && (
              <Button onClick={handleProcess} disabled={processing} loading={processing}>
                <Play className="h-4 w-4 mr-2" />
                {processing
                  ? "Starting..."
                  : meeting.status === "failed"
                  ? "Retry"
                  : "Process"}
              </Button>
            )}

            {isProcessing && (
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
              onExportDocx={handleExportTranscriptDocx}
              exportDocxLoading={exportingDocx}
            />
          ) : (
            <div className="text-center py-12 text-gray-500">
              {isProcessing
                ? "Transcription in progress..."
                : transcriptLoading || transcriptFetching
                ? "正在加载转写稿（长会议约需 10–30 秒）…"
                : transcriptError
                ? "转写稿加载失败，请刷新页面重试"
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
              meeting={meeting}
              onUpdateMeeting={handleUpdateMeetingMeta}
              onRegenerate={handleRegenerateSummary}
              regenerating={regeneratingSummary}
              regenerateMessage={regenerateMessage}
              onExportMinutes={handleExportMinutesDocx}
            />
          ) : (
            <div className="text-center py-12 text-gray-500">
              {isProcessing
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
