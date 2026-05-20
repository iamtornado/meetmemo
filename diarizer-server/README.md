# Diarizer Server — Remote pyannote.audio API

A standalone FastAPI server that runs pyannote speaker diarization on a remote
machine and exposes an HTTP API for the MeetMemo worker to call.

## Quick Start

```bash
# 1. Install dependencies
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install pyannote.audio fastapi uvicorn python-multipart httpx modelscope

# 2. Download models from ModelScope (preferred in China)
#    Models are stored in /data/models/pyannote/
export MODEL_SOURCE=modelscope

# 3. Patch pyannote's HuggingFace downloader to use local files
#    (Required because gated models like pyannote/segmentation-3.0
#     are inaccessible from China without a HF token)
python3 -c "
from pathlib import Path
p = Path.home() / '.local' / 'lib' / 'python3.12' / 'site-packages' / 'pyannote' / 'audio' / 'utils' / 'hf_hub.py'
content = p.read_text()
old = '''    if isinstance(token, str) and not token.startswith(\"hf_\"):
        token = None

    try:'''
new = '''    if isinstance(token, str) and not token.startswith(\"hf_\"):
        token = None

    # --- MeetMemo patch: redirect gated models to /data/models/pyannote/ ---
    _local_base = Path(\"/data/models/pyannote\")
    _gated_ids = {\"pyannote/segmentation-3.0\", \"pyannote/speaker-diarization-3.1\", \"pyannote/speaker-diarization-community-1\"}
    if model_id in _gated_ids:
        _fname = asset_file.value if isinstance(asset_file, AssetFileName) else str(asset_file)
        _local_path = _local_base / model_id.split(\"/\", 1)[-1]
        if subfolder:
            _local_path = _local_path / subfolder
        _local_path = _local_path / _fname
        if _local_path.exists():
            import logging
            logging.getLogger(__name__).info(f\"Using local file for {model_id}/{_fname}\")
            return str(_local_path)
    # --- End MeetMemo patch ---

    try:'''
content = content.replace(old, new, 1)
p.write_text(content)
print('hf_hub.py patched')
"

# 4. Run the server
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
{"status": "ok", "device": "cpu", "pipeline_loaded": true}
```

## Deployment

The server is deployed on `10.65.37.237:8001`. It runs on CPU because the
Quadro P2000 (SM 6.1) is incompatible with PyTorch >= 2.8 required by
pyannote-audio 4.0.4.

### Process management

```bash
# Check process
ps aux | grep 'python3 main.py'

# Tail logs
tail -f ~/diarizer-server/server.log

# Restart
pkill -f 'python3 main.py'
cd ~/diarizer-server && nohup python3 main.py > server.log 2>&1 &
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MODEL_SOURCE` | `modelscope` | `huggingface` or `modelscope` |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8001` | Listen port |

## Known Issues

- **CPU only**: Quadro P2000 (Pascal SM 6.1) is not supported by PyTorch >= 2.8.
  CPU diarization of a 1-hour meeting takes ~70 minutes.
- **NO_PROXY parsing bug**: The host has `ALL_PROXY=socks5://...` and
  `NO_PROXY` with IPv6 addresses. httpx 0.28.1 crashes on this config.
  The `main.py` strips these vars on startup.
- **Gated models**: pyannote segmentation and diarization models are gated on
  HuggingFace. The `hf_hub.py` patch redirects to locally-downloaded
  (via ModelScope) copies.
