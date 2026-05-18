"use client";

import { useState } from "react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Mic, Upload } from "lucide-react";
import { api } from "@/lib/api";

export function UploadDialog({
  open,
  onClose,
  onSuccess,
}: {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [recording, setRecording] = useState(false);
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);
  const [uploading, setUploading] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      setFile(e.target.files[0]);
      if (!title) setTitle(e.target.files[0].name.replace(/\.[^/.]+$/, ""));
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      const chunks: BlobPart[] = [];

      recorder.ondataavailable = (e) => chunks.push(e.data);
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: "audio/webm" });
        setFile(new File([blob], "recording.webm", { type: "audio/webm" }));
        stream.getTracks().forEach((t) => t.stop());
      };

      setMediaRecorder(recorder);
      recorder.start();
      setRecording(true);
    } catch (err) {
      alert("Microphone access denied");
    }
  };

  const stopRecording = () => {
    mediaRecorder?.stop();
    setRecording(false);
    setMediaRecorder(null);
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    try {
      await api.createMeeting(file, title || undefined);
      onSuccess();
      onClose();
      setFile(null);
      setTitle("");
    } catch (err) {
      console.error("Upload failed", err);
    } finally {
      setUploading(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title="Upload Meeting Recording">
      <div className="space-y-4">
        <Input
          placeholder="Meeting title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />

        <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center">
          <input
            type="file"
            accept="audio/*,video/*"
            onChange={handleFileChange}
            className="hidden"
            id="file-upload"
          />
          <label
            htmlFor="file-upload"
            className="cursor-pointer flex flex-col items-center gap-2"
          >
            <Upload className="h-8 w-8 text-gray-400" />
            <span className="text-sm text-gray-500">
              {file ? file.name : "Click to select audio/video file"}
            </span>
          </label>
        </div>

        <div className="text-center text-sm text-gray-400">or</div>

        <Button
          variant="outline"
          className="w-full"
          onClick={recording ? stopRecording : startRecording}
        >
          <Mic className="mr-2 h-4 w-4" />
          {recording ? "Stop Recording" : "Record Audio"}
        </Button>

        <Button
          className="w-full"
          disabled={!file}
          loading={uploading}
          onClick={handleUpload}
        >
          Upload & Process
        </Button>
      </div>
    </Dialog>
  );
}
