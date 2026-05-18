from __future__ import annotations

import logging
from pathlib import Path

from app.config import settings
from app.tasks.diarizer.base import BaseDiarizer, DiarizationResult, DiarizationSegment

logger = logging.getLogger(__name__)


class LocalDiarizer(BaseDiarizer):
    """Diarization provider using pyannote.audio pipeline running locally.

    Runs the full pyannote speaker-diarization-3.1 pipeline inside the container.
    Model files are downloaded from ModelScope (since HuggingFace is unreachable in CN)
    and symlinked into the HuggingFace cache structure.
    """

    def __init__(self):
        self._pipeline = None

    def get_model_name(self) -> str:
        return "pyannote/speaker-diarization-3.1"

    def diarize(self, audio_path: str) -> DiarizationResult:
        """Run pyannote diarization pipeline on the given audio file."""
        pipeline = self._get_pipeline()
        if pipeline is None:
            logger.warning("Diarization pipeline unavailable, returning empty result")
            return DiarizationResult()

        import torch
        pipeline.to(torch.device("cpu"))
        result = pipeline(audio_path, num_workers=0)

        # pyannote 3.1 returns DiarizeOutput; access the annotation
        diarization = result.speaker_diarization

        # Convert pyannote output to DiarizationSegment list
        speaker_segments: list[DiarizationSegment] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speaker_segments.append(
                DiarizationSegment(
                    speaker=speaker,
                    start=turn.start,
                    end=turn.end,
                )
            )

        num_speakers = len(set(s.speaker for s in speaker_segments))
        logger.info(
            f"Local pyannote diarization complete: "
            f"{len(speaker_segments)} segments, {num_speakers} speakers"
        )

        return DiarizationResult(
            speaker_segments=speaker_segments,
            num_speakers=num_speakers,
        )

    # ------------------------------------------------------------------
    # Pipeline singleton + ModelScope download helpers
    # ------------------------------------------------------------------

    _pipeline_instance = None

    def _get_pipeline(self):
        """Lazy-loaded singleton for pyannote diarization pipeline."""
        if self._pipeline is not None:
            return self._pipeline

        from pyannote.audio import Pipeline

        logger.info("Loading pyannote diarization pipeline...")

        model_path = self._ensure_diarization_model()
        if not model_path:
            logger.warning("Diarization model unavailable")
            return None

        try:
            self._pipeline = Pipeline.from_pretrained(model_path, token=False)
        except Exception as e:
            logger.warning(f"Failed to load pyannote pipeline: {e}")
            self._pipeline = None

        if self._pipeline is not None:
            import torch
            if torch.cuda.is_available():
                self._pipeline.to(torch.device("cuda"))
            logger.info("Diarization pipeline loaded")

        return self._pipeline

    # --- ModelScope download helpers (same logic as original diarize.py) ---

    DIARIZATION_MODELSCOPE_REPO = "pyannote/speaker-diarization-3.1"
    DIARIZATION_SUB_MODELS = {
        "pyannote/segmentation-3.0": "pyannote/segmentation-3.0",
        "pyannote/wespeaker-voxceleb-resnet34-LM": "pyannote/wespeaker-voxceleb-resnet34-LM",
        "pyannote/speaker-diarization-community-1": "pyannote/speaker-diarization-community-1",
    }

    def _ensure_diarization_model(self) -> str | None:
        """Download diarization pipeline + all sub-models from ModelScope into
        HuggingFace cache structure (since HuggingFace is unreachable in CN)."""
        import hashlib

        hf_cache_base = Path.home() / ".cache" / "huggingface" / "hub"
        cache_dir = Path(settings.STORAGE_PATH) / "models" / "pyannote" / "speaker-diarization-3.1"

        all_models: dict[str, str] = {
            "pyannote/speaker-diarization-3.1": self.DIARIZATION_MODELSCOPE_REPO,
        }
        all_models.update(self.DIARIZATION_SUB_MODELS)

        for model_id, ms_repo in all_models.items():
            hf_model_id = f"models--{model_id.replace('/', '--')}"
            hf_model_dir = hf_cache_base / hf_model_id
            if hf_model_dir.exists() and (hf_model_dir / "snapshots").exists():
                logger.info(f"Model {model_id} already in HF cache")
                continue

            local_dir = Path(settings.STORAGE_PATH) / "models" / model_id
            local_dir.mkdir(parents=True, exist_ok=True)

            if not list(local_dir.iterdir()) or all(
                f.name.startswith(".") for f in local_dir.iterdir()
            ):
                try:
                    from modelscope.hub.snapshot_download import snapshot_download

                    logger.info(f"Downloading {model_id} from ModelScope ({ms_repo})...")
                    snapshot_download(
                        ms_repo,
                        cache_dir=str(local_dir.parent),
                        local_dir=str(local_dir),
                    )
                    logger.info(f"Downloaded {model_id} to {local_dir}")
                except Exception as e:
                    logger.warning(f"Failed to download {model_id}: {e}")
                    continue

            # Create HuggingFace cache structure (symlinks to our local storage)
            hf_snapshots_dir = hf_model_dir / "snapshots"
            hf_snapshots_dir.mkdir(parents=True, exist_ok=True)

            snapshot_id = hashlib.md5(str(local_dir).encode()).hexdigest()[:12]
            snapshot_dir = hf_snapshots_dir / snapshot_id
            snapshot_dir.mkdir(parents=True, exist_ok=True)

            self._symlink_tree(local_dir, snapshot_dir)

            refs_dir = hf_model_dir / "refs"
            refs_dir.mkdir(parents=True, exist_ok=True)
            (refs_dir / "main").write_text(snapshot_id)

            logger.info(f"HF cache created for {model_id} -> {snapshot_dir}")

        import os as _os
        _os.environ.setdefault("HF_HUB_OFFLINE", "1")

        return str(cache_dir)

    @staticmethod
    def _symlink_tree(src: Path, dst: Path) -> None:
        """Recursively symlink all non-hidden files from src to dst."""
        import os as _os

        for f in src.iterdir():
            if f.name.startswith("."):
                continue
            dst_path = dst / f.name
            if f.is_dir():
                dst_path.mkdir(parents=True, exist_ok=True)
                LocalDiarizer._symlink_tree(f, dst_path)
            elif not dst_path.exists():
                _os.symlink(f.absolute(), dst_path)
