"use client";

import { useState } from "react";
import type { Transcript as TranscriptType, TranscriptSegment } from "@/types";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog } from "@/components/ui/dialog";
import { Download } from "lucide-react";

export function TranscriptViewer({
  transcript,
  onSpeakerRename,
  onSeek,
  onExportDocx,
  exportDocxLoading,
}: {
  transcript: TranscriptType;
  onSpeakerRename?: (mappings: Record<string, string>) => void;
  onSeek?: (time: number) => void;
  onExportDocx?: () => void;
  exportDocxLoading?: boolean;
}) {
  const [showRename, setShowRename] = useState(false);
  const [renameMappings, setRenameMappings] = useState<Record<string, string>>({});

  // Collect unique speakers
  const speakers = new Map<string, string>();
  transcript.segments.forEach((s) => {
    if (s.speaker_id) {
      speakers.set(s.speaker_id, s.speaker_name || s.speaker_id);
    }
  });

  const openRenameDialog = () => {
    const initial: Record<string, string> = {};
    speakers.forEach((name, id) => {
      initial[id] = name;
    });
    setRenameMappings(initial);
    setShowRename(true);
  };

  const handleRename = () => {
    const payload: Record<string, string> = {};
    speakers.forEach((_, id) => {
      const name = (renameMappings[id] ?? "").trim();
      if (name) {
        payload[id] = name;
      }
    });
    onSpeakerRename?.(payload);
    setShowRename(false);
  };

  const speakerColors = [
    "text-blue-600",
    "text-green-600",
    "text-purple-600",
    "text-orange-600",
    "text-pink-600",
    "text-teal-600",
  ];

  const getSpeakerColor = (id: string | null) => {
    if (!id) return "text-gray-500";
    const idx = Array.from(speakers.keys()).indexOf(id);
    return speakerColors[idx % speakerColors.length];
  };

  if (!transcript.segments?.length) {
    return (
      <div className="text-center py-8 text-gray-500">
        No transcript segments available
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-500">
          {transcript.word_count} words · {transcript.language}
        </div>
        <div className="flex items-center gap-2">
          {onExportDocx && (
            <Button
              variant="outline"
              size="sm"
              onClick={onExportDocx}
              disabled={exportDocxLoading}
            >
              <Download className="h-4 w-4 mr-1" />
              {exportDocxLoading ? "导出中…" : "导出 Word"}
            </Button>
          )}
          {speakers.size > 0 && onSpeakerRename && (
            <Button variant="outline" size="sm" onClick={openRenameDialog}>
              编辑说话人姓名
            </Button>
          )}
        </div>
      </div>

      <div className="space-y-2">
        {transcript.segments.map((seg) => (
          <Card
            key={seg.id || seg.seq_number}
            className="hover:border-blue-200 cursor-pointer transition-colors"
            onClick={() => onSeek?.(seg.start_time)}
          >
            <CardContent className="p-4">
              <div className="flex items-start gap-3">
                <span className="text-xs text-gray-400 font-mono mt-1 whitespace-nowrap">
                  {formatTimestamp(seg.start_time)}
                </span>
                {seg.speaker_id && (
                  <span
                    className={`text-sm font-semibold whitespace-nowrap mt-0.5 ${getSpeakerColor(
                      seg.speaker_id
                    )}`}
                  >
                    {seg.speaker_name || seg.speaker_id}
                  </span>
                )}
                <p className="text-sm text-gray-800 flex-1">{seg.text}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog
        open={showRename}
        onClose={() => setShowRename(false)}
        title="编辑说话人姓名"
      >
        <div className="space-y-3">
          <p className="text-sm text-gray-500">
            系统标签（如 SPEAKER_01）可改为真实姓名，转写与摘要参会人将同步更新。
          </p>
          {Array.from(speakers.entries()).map(([id, name]) => (
            <div key={id} className="flex items-center gap-2">
              <span className="text-sm font-medium w-28 text-gray-600 shrink-0">{id}</span>
              <Input
                value={renameMappings[id] ?? name}
                placeholder="输入姓名"
                onChange={(e) =>
                  setRenameMappings((prev) => ({ ...prev, [id]: e.target.value }))
                }
              />
            </div>
          ))}
          <Button className="w-full" onClick={handleRename}>
            保存
          </Button>
        </div>
      </Dialog>
    </div>
  );
}

function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}
