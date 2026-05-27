"use client";

import { useEffect, useState } from "react";
import type { Meeting } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function MeetingMinutesMeta({
  meeting,
  onSave,
}: {
  meeting: Meeting;
  onSave: (data: {
    host?: string | null;
    recorder_unit?: string | null;
    meeting_location?: string | null;
  }) => Promise<void>;
}) {
  const [host, setHost] = useState(meeting.host ?? "");
  const [recorderUnit, setRecorderUnit] = useState(meeting.recorder_unit ?? "");
  const [location, setLocation] = useState(meeting.meeting_location ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setHost(meeting.host ?? "");
    setRecorderUnit(meeting.recorder_unit ?? "");
    setLocation(meeting.meeting_location ?? "");
  }, [meeting.host, meeting.recorder_unit, meeting.meeting_location]);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await onSave({
        host: host.trim() || null,
        recorder_unit: recorderUnit.trim() || null,
        meeting_location: location.trim() || null,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">纪要要素（生成前可填写）</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-gray-500">
          主持默认为「董事长」；记录单位、地点请按本次会议实际情况填写。保存后点击「重新生成」以更新纪要正文。
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <label className="space-y-1">
            <span className="text-xs text-gray-600">会议主持</span>
            <Input
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder="董事长"
            />
          </label>
          <label className="space-y-1">
            <span className="text-xs text-gray-600">记录单位</span>
            <Input
              value={recorderUnit}
              onChange={(e) => setRecorderUnit(e.target.value)}
              placeholder="如：人工智能技术中心"
            />
          </label>
          <label className="space-y-1">
            <span className="text-xs text-gray-600">会议地点</span>
            <Input
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="如：集团总部会议室"
            />
          </label>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={handleSave} loading={saving} disabled={saving}>
            保存要素
          </Button>
          {saved && <span className="text-xs text-green-600">已保存</span>}
        </div>
      </CardContent>
    </Card>
  );
}
