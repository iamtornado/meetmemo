# Diarizer Server — Remote pyannote.audio API

Standalone FastAPI server for speaker diarization. MeetMemo calls it when `DIARIZE_PROVIDER=remote`.

## Quick Start (GPU host)

```bash
cd /data/diarizer-server

pip install torch torchaudio pyannote.audio fastapi uvicorn python-multipart modelscope

export MODEL_SOURCE=modelscope
export MODELSCOPE_CACHE=/data/modelscope_cache
export CUDA_VISIBLE_DEVICES=4   # or 5 if SenseVoice uses 4 alone
export PORT=8002                # MeetMemo default DIARIZE_API_URL port

nohup python3 main.py >> server.log 2>&1 &
curl -s http://127.0.0.1:8002/health
```

MeetMemo `.env`:

```env
DIARIZE_PROVIDER=remote
DIARIZE_API_URL=http://<ai-server>:8002
DIARIZE_MERGE_MIN_OVERLAP_SEC=0.3
DIARIZE_MERGE_MIN_OVERLAP_RATIO=0.05
```

## API

### `POST /diarize`

**Request:** `multipart/form-data`, field `audio`

**Response (200):**

```json
{
  "speaker_segments": [
    {"speaker": "SPEAKER_00", "start": 0.0, "end": 2.5}
  ],
  "num_speakers": 2
}
```

### `GET /health`

```json
{"status": "ok", "device": "cuda", "pipeline_loaded": true}
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_SOURCE` | `modelscope` | `modelscope` or `huggingface` |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8001` | Listen port in code default; use **8002** for MeetMemo |

> **Note:** `main.py` defaults to port `8001`. Production MeetMemo expects **8002** — set `PORT=8002` when starting.

## Gated models & ModelScope

pyannote segmentation models may be gated on HuggingFace. For deployments in China, download via ModelScope and optionally patch `pyannote.audio` `hf_hub.py` to read local files (see historical notes in git history for this repo).

## Process management

```bash
pkill -f 'diarizer-server' || pkill -f 'diarizer-server/main.py' || true
cd /data/diarizer-server
CUDA_VISIBLE_DEVICES=4 PORT=8002 nohup python3 main.py >> server.log 2>&1 &
tail -f server.log
```

## GPU sharing with SenseVoice

On a 140GB H20, SenseVoice (~1–3GB idle) and pyannote (~0.5–2GB idle) can share one GPU. Peak usage during diarization of a 10-minute meeting may reach several GB; keep vLLM on **other** GPUs.

See [sensevoice-server/README.md](../sensevoice-server/README.md) for the recommended 8×GPU layout.
