"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Play, Pause, SkipBack, SkipForward } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export function AudioPlayer({
  meetingId,
  onTimeUpdate,
  onReady,
}: {
  meetingId: string;
  onTimeUpdate?: (time: number) => void;
  onReady?: () => void;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  const audioUrl = `${API_BASE}/meetings/${meetingId}/audio`;

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onTime = () => {
      setCurrentTime(audio.currentTime);
      onTimeUpdate?.(audio.currentTime);
    };
    const onMeta = () => setDuration(audio.duration);
    const onEnd = () => setPlaying(false);

    audio.addEventListener("timeupdate", onTime);
    audio.addEventListener("loadedmetadata", onMeta);
    audio.addEventListener("ended", onEnd);

    return () => {
      audio.removeEventListener("timeupdate", onTime);
      audio.removeEventListener("loadedmetadata", onMeta);
      audio.removeEventListener("ended", onEnd);
    };
  }, [onTimeUpdate]);

  const toggle = () => {
    if (!audioRef.current) return;
    if (playing) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setPlaying(!playing);
  };

  const skip = (delta: number) => {
    if (!audioRef.current) return;
    audioRef.current.currentTime = Math.max(0, Math.min(audioRef.current.currentTime + delta, duration));
  };

  const formatTime = (t: number) => {
    const m = Math.floor(t / 60);
    const s = Math.floor(t % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  return (
    <div className="flex items-center gap-4 p-4 bg-white rounded-lg border border-gray-200 shadow-sm">
      <audio ref={audioRef} src={audioUrl} preload="metadata" />

      <Button variant="ghost" size="sm" onClick={() => skip(-10)}>
        <SkipBack className="h-4 w-4" />
      </Button>

      <Button
        variant="default"
        size="icon"
        onClick={toggle}
        className="rounded-full h-10 w-10"
      >
        {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 ml-0.5" />}
      </Button>

      <Button variant="ghost" size="sm" onClick={() => skip(10)}>
        <SkipForward className="h-4 w-4" />
      </Button>

      <div className="flex-1">
        <div className="bg-gray-200 rounded-full h-2 relative">
          <div
            className="bg-blue-600 rounded-full h-2 absolute left-0 top-0 transition-all"
            style={{ width: `${duration ? (currentTime / duration) * 100 : 0}%` }}
          />
        </div>
      </div>

      <span className="text-xs text-gray-500 font-mono whitespace-nowrap">
        {formatTime(currentTime)} / {formatTime(duration)}
      </span>
    </div>
  );
}
