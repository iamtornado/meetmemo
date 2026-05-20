"""Standalone pyannote diarization API server.

Deploy on a GPU server and configure MeetMemo with:
    DIARIZE_PROVIDER=remote
    DIARIZE_API_URL=http://your-gpu-server:8001

HuggingFace token is required for pyannote model access.
Set via HF_TOKEN environment variable.
"""

from __future__ import annotations

import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# NOTE: On the target server (10.65.37.237), the pyannote source file
# pyannote/audio/utils/hf_hub.py has been directly patched to redirect
# gated model downloads (segmentation-3.0, etc.) to /data/models/pyannote/.
# If deploying to a new server, that patch must be applied as well, OR
# this Python-level patch must be made before the Pipeline import.
# See diarizer-server/README.md for details.

# ---------------------------------------------------------------------------
# Environment fix: host has ALL_PROXY=socks5 which breaks httpx.
# Also Quadro P2000 (SM 6.1) is too old for torch>=2.8, so force CPU.
# Keep HTTP_PROXY for any remaining hub access.
# ---------------------------------------------------------------------------
_HTTP_PROXY = os.environ.get("HTTP_PROXY", "")
for _key in ("ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
    os.environ.pop(_key, None)
if _HTTP_PROXY:
    for _key in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        os.environ.setdefault(_key, _HTTP_PROXY)
os.environ["CUDA_VISIBLE_DEVICES"] = ""


# ---------------------------------------------------------------------------
# Patch pyannote's hf_hub downloader BEFORE importing Pipeline
# ---------------------------------------------------------------------------
# pyannote 4.0.4 uses hf_hub_download("pyannote/segmentation-3.0", ...)
# internally.  On this server the models are stored locally under
# /data/models/pyannote/ so we redirect those calls to local paths.
# Gated HuggingFace repos (segmentation, diarization) are inaccessible
# without a token; we already have the files via ModelScope download.

import pyannote.audio.utils.hf_hub as _hf_utils
import huggingface_hub

_orig_hf_hub_download = _hf_utils.download_from_hf_hub

_LOCAL_MODEL_DIR = Path("/data/models/pyannote")


def _patched_download_from_hf_hub(
    model_id: str,
    asset_file,
    *,
    subfolder=None,
    revision=None,
    cache_dir=None,
    token=None,
):
    """Redirect gated model downloads to local /data/models/pyannote/."""
    # Only redirect known gated models to local path
    if model_id in (
        "pyannote/segmentation-3.0",
        "pyannote/speaker-diarization-3.1",
        "pyannote/speaker-diarization-community-1",
    ):
        # Determine the filename
        if hasattr(asset_file, "value"):
            filename = asset_file.value
        else:
            filename = str(asset_file)

        # Strip org prefix: model_id "pyannote/segmentation-3.0" ->
        # local dir "/data/models/pyannote/segmentation-3.0"
        local_dir = model_id.split("/", 1)[-1]
        local_path = _LOCAL_MODEL_DIR / local_dir
        if subfolder:
            local_path = local_path / subfolder
        local_path = local_path / filename

        if local_path.exists():
            logger.info(f"Using local file for {model_id}/{filename}")
            return str(local_path)

    # For wespeaker or non-gated models, let huggingface_hub handle it
    # with local_files_only=True to avoid network delays
    try:
        return huggingface_hub.hf_hub_download(
            model_id,
            asset_file.value if hasattr(asset_file, "value") else asset_file,
            subfolder=subfolder,
            repo_type="model",
            revision=revision,
            cache_dir=cache_dir,
            token=token,
            local_files_only=True,
        )
    except Exception:
        pass

    # Last resort: original call (may fail with 401 for gated models)
    return _orig_hf_hub_download(
        model_id, asset_file,
        subfolder=subfolder, revision=revision,
        cache_dir=cache_dir, token=token,
    )


_hf_utils.download_from_hf_hub = _patched_download_from_hf_hub


# ---------------------------------------------------------------------------
# Global pipeline (lazy-loaded singleton)
# ---------------------------------------------------------------------------

_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    from pyannote.audio import Pipeline
    import torch

    hf_token = os.environ.get("HF_TOKEN", "")
    model_source = os.environ.get("MODEL_SOURCE", "modelscope")

    logger.info("Loading pyannote diarization pipeline...")

    if model_source == "modelscope":
        # ModelScope mode — download and symlink into HF cache
        _ensure_modelscope_models()
        model_path = str(
            Path("/data") / "models" / "pyannote" / "speaker-diarization-3.1"
        )
        _pipeline = Pipeline.from_pretrained(model_path, token=False)
    else:
        # HuggingFace mode — requires HF_TOKEN
        if not hf_token:
            raise RuntimeError(
                "HF_TOKEN environment variable is required for HuggingFace mode. "
                "Set HF_TOKEN or use MODEL_SOURCE=modelscope."
            )
        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )

    if torch.cuda.is_available():
        _pipeline.to(torch.device("cuda"))
        logger.info("Pipeline moved to GPU")
    else:
        logger.warning("CUDA not available — running on CPU (will be slow)")

    logger.info("Diarization pipeline loaded successfully")
    return _pipeline


# ---------------------------------------------------------------------------
# ModelScope helpers (same approach as MeetMemo worker)
# ---------------------------------------------------------------------------

MODELSCOPE_REPO = "pyannote/speaker-diarization-3.1"
SUB_MODELS = {
    "pyannote/segmentation-3.0": "pyannote/segmentation-3.0",
    "pyannote/wespeaker-voxceleb-resnet34-LM": "pyannote/wespeaker-voxceleb-resnet34-LM",
    "pyannote/speaker-diarization-community-1": "pyannote/speaker-diarization-community-1",
}


def _ensure_modelscope_models():
    import hashlib
    from modelscope.hub.snapshot_download import snapshot_download

    hf_cache_base = Path.home() / ".cache" / "huggingface" / "hub"
    all_models = {"pyannote/speaker-diarization-3.1": MODELSCOPE_REPO}
    all_models.update(SUB_MODELS)

    for model_id, ms_repo in all_models.items():
        hf_model_id = f"models--{model_id.replace('/', '--')}"
        hf_model_dir = hf_cache_base / hf_model_id
        if hf_model_dir.exists() and (hf_model_dir / "snapshots").exists():
            logger.info(f"Model {model_id} already in HF cache")
            continue

        local_dir = Path("/data") / "models" / model_id
        local_dir.mkdir(parents=True, exist_ok=True)

        if not list(local_dir.iterdir()) or all(
            f.name.startswith(".") for f in local_dir.iterdir()
        ):
            logger.info(f"Downloading {model_id} from ModelScope ({ms_repo})...")
            snapshot_download(
                ms_repo,
                cache_dir=str(local_dir.parent),
                local_dir=str(local_dir),
            )
            logger.info(f"Downloaded {model_id} to {local_dir}")

        # Symlink into HuggingFace cache
        hf_snapshots_dir = hf_model_dir / "snapshots"
        hf_snapshots_dir.mkdir(parents=True, exist_ok=True)
        snapshot_id = hashlib.md5(str(local_dir).encode()).hexdigest()[:12]
        snapshot_dir = hf_snapshots_dir / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        _symlink_tree(local_dir, snapshot_dir)

        refs_dir = hf_model_dir / "refs"
        refs_dir.mkdir(parents=True, exist_ok=True)
        (refs_dir / "main").write_text(snapshot_id)
        logger.info(f"HF cache created for {model_id} -> {snapshot_dir}")

    os.environ.setdefault("HF_HUB_OFFLINE", "1")


def _symlink_tree(src: Path, dst: Path) -> None:
    for f in src.iterdir():
        if f.name.startswith("."):
            continue
        dst_path = dst / f.name
        if f.is_dir():
            dst_path.mkdir(parents=True, exist_ok=True)
            _symlink_tree(f, dst_path)
        elif not dst_path.exists():
            os.symlink(f.absolute(), dst_path)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load the pipeline on startup."""
    logger.info("Starting diarizer server...")
    try:
        get_pipeline()
    except Exception as e:
        logger.error(f"Failed to load pipeline on startup: {e}")
        logger.warning("Server will start but /diarize endpoint may fail")
    yield


app = FastAPI(
    title="MeetMemo Diarizer Server",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    return {
        "status": "ok",
        "device": device,
        "pipeline_loaded": _pipeline is not None,
    }


@app.post("/diarize")
async def diarize(audio: UploadFile = File(...)):
    """Receive an audio file, run pyannote diarization, return speaker segments."""
    pipeline = get_pipeline()
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Diarization pipeline not loaded")

    # Save uploaded file to a temporary location
    suffix = Path(audio.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        content = await audio.read()
        tmp.write(content)

    try:
        import torch

        # Run diarization
        result = pipeline(tmp_path, num_workers=0)
        diarization = result.speaker_diarization

        speaker_segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speaker_segments.append({
                "speaker": speaker,
                "start": turn.start,
                "end": turn.end,
            })

        num_speakers = len(set(s["speaker"] for s in speaker_segments))

        logger.info(
            f"Diarized {audio.filename}: {len(speaker_segments)} segments, "
            f"{num_speakers} speakers"
        )

        return {
            "speaker_segments": speaker_segments,
            "num_speakers": num_speakers,
        }

    except Exception as e:
        logger.error(f"Diarization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8001"))
    uvicorn.run(app, host=host, port=port, workers=1)
