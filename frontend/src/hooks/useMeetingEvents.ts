"use client";

import { useEffect, useRef } from "react";
import { getToken } from "@/lib/auth";

function getApiBase(): string {
  if (typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:8000/api/v1`;
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
}

type MeetingEvent = {
  type: string;
  meeting_id?: string;
  step?: string;
  error?: string;
};

export function useMeetingEvents(
  meetingId: string | undefined,
  enabled: boolean,
  onEvent: (payload: MeetingEvent) => void
) {
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!enabled || !meetingId) return;

    const token = getToken();
    if (!token) return;

    const controller = new AbortController();
    let buffer = "";

    (async () => {
      try {
        const res = await fetch(`${getApiBase()}/events`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (!res.ok || !res.body) return;

        const reader = res.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const parts = buffer.split("\n\n");
          buffer = parts.pop() || "";

          for (const part of parts) {
            const line = part.split("\n").find((l) => l.startsWith("data: "));
            if (!line) continue;
            try {
              const data = JSON.parse(line.slice(6)) as MeetingEvent;
              if (data.meeting_id === meetingId) {
                onEventRef.current(data);
              }
            } catch {
              /* ignore */
            }
          }
        }
      } catch {
        /* aborted or disconnected */
      }
    })();

    return () => controller.abort();
  }, [meetingId, enabled]);
}
