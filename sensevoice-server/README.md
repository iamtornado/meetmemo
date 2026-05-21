# SenseVoice Server — Remote ASR API (VAD)

Standalone FastAPI service wrapping FunASR **SenseVoiceSmall** with official **VAD + merge_vad** ([demo1.py](https://github.com/FunAudioLLM/SenseVoice/blob/main/demo1.py)).

MeetMemo worker calls **one** `/transcribe` per meeting when `/health` reports `vad_enabled: true`.

## Quick Start (GPU host)

```bash
cd /data/sensevoice-server

pip install funasr fastapi uvicorn python-multipart modelscope

export MODELSCOPE_CACHE=/data/modelscope_cache
export CUDA_VISIBLE_DEVICES=4
export PORT=8003

nohup python3 main.py >> server.log 2>&1 &
curl -s http://127.0.0.1:8003/health | python3 -m json.tool
```

## MeetMemo `.env`

```env
ASR_PROVIDER=sensevoice
SENSEVOICE_MODE=remote
SENSEVOICE_API_URL=http://10.27.6.1:8003
# Client-side ffmpeg slicing only if /health has no vad_enabled (legacy)
SENSEVOICE_CHUNK_SECONDS=3600
SENSEVOICE_REQUEST_TIMEOUT_MAX=7200
```

## API

### `GET /health`

```json
{
  "status": "ok",
  "vad_enabled": true,
  "merge_vad": true,
  "batch_size_s": 60,
  "merge_length_s": 15
}
```

### `POST /transcribe`

Upload full meeting WAV (16 kHz mono). Server runs VAD internally; no 300s client chunks needed.

**Response:** `text`, `word_count`, `language`, `segments[]` with `start`/`end` (seconds, **sentence-level** after micro-segment merge), `model_used`, `elapsed_seconds`.

## Server tunables

| Variable | Default | Description |
|----------|---------|-------------|
| `SENSEVOICE_VAD_MODEL` | `fsmn-vad` | FunASR VAD model id |
| `SENSEVOICE_VAD_MAX_SEGMENT_MS` | `30000` | Max ms per VAD slice before ASR |
| `SENSEVOICE_MERGE_LENGTH_S` | `15` | `merge_length_s` (demo default) |
| `SENSEVOICE_BATCH_SIZE_S` | `60` | `batch_size_s` (demo default) |
| `SENSEVOICE_OUTPUT_TIMESTAMP` | `true` | CTC timestamps for segments |
| `SENSEVOICE_DEVICE` | `cuda:0` | Inside container, use `cuda:0` with `CUDA_VISIBLE_DEVICES` |

## Restart

```bash
pkill -f 'sensevoice-server/main.py' || true
cd /data/sensevoice-server
CUDA_VISIBLE_DEVICES=4 PORT=8003 nohup python3 main.py >> server.log 2>&1 &
tail -f server.log
```

First start loads SenseVoice + VAD (~1–2 min). A 35 min meeting typically transcribes in one request (often faster than 7× client-side 300s chunks).

## GPU layout (8× H20 reference)

| GPU | Service |
|-----|---------|
| 0–3 | vLLM DeepSeek-V4-Flash |
| 4 | SenseVoice **8003** + diarizer **8002** |

See [diarizer-server/README.md](../diarizer-server/README.md).
