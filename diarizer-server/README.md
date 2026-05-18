# Diarizer Server — Remote pyannote.audio API

A standalone FastAPI server that runs pyannote speaker diarization on a GPU
and exposes an HTTP API for the MeetMemo worker to call.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your HuggingFace token (required for pyannote model access)
export HF_TOKEN=hf_xxxxxxxxxxxx

# 3. Run the server
python main.py
# → Listening on http://0.0.0.0:8001
```

## API

### POST /diarize

Send an audio file for speaker diarization.

**Request:** `multipart/form-data` with field `audio`

**Response (200):**
```json
{
    "speaker_segments": [
        {"speaker": "SPEAKER_00", "start": 0.0, "end": 2.5},
        {"speaker": "SPEAKER_01", "start": 2.5, "end": 5.0}
    ],
    "num_speakers": 2
}
```

### GET /health

Health check.

**Response (200):**
```json
{"status": "ok", "device": "cuda"}
```

## Docker Deployment

```bash
docker build -t diarizer-server .
docker run --gpus all -p 8001:8001 -e HF_TOKEN=hf_xxx diarizer-server
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `HF_TOKEN` | (required) | HuggingFace token for pyannote model access |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8001` | Listen port |
| `MODEL_SOURCE` | `huggingface` | `huggingface` or `modelscope` |
