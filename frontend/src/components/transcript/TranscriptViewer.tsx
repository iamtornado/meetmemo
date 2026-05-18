"use client";

import { useState } from "react";
import type { Transcript as TranscriptType, TranscriptSegment } from "@/types";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog } from "@/components/ui/dialog";
import { format } from "date-fns";

export function TranscriptViewer({
  transcript,
  onSpeakerRename,
  onSeek,
}: {
  transcript: TranscriptType;
  onSpeakerRename?: (mappings: Record<string, string>) => void;
  onSeek?: (time: number) => void;
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

  const handleRename = () => {
    onSpeakerRename?.(renameMappings);
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
        {speakers.size > 0 && (
          <Button variant="outline" size="sm" onClick={() => setShowRename(true)}>
            Rename Speakers
          </Button>
        )}
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
        title="Rename Speakers"
      >
        <div className="space-y-3">
          {Array.from(speakers.entries()).map(([id, name]) => (
            <div key={id} className="flex items-center gap-2">
              <span className="text-sm font-medium w-24 text-gray-600">{id}:</span>
              <Input
                defaultValue={name}
                placeholder="Enter name"
                onChange={(e) =>
                  setRenameMappings((prev) => ({ ...prev, [id]: e.target.value }))
                }
              />
            </div>
          ))}
          <Button className="w-full" onClick={handleRename}>
            Apply Names
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
