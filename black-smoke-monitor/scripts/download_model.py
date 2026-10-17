"""One-time model download into MODEL_LOCAL_DIR (needs internet). Logs revision + license."""
import _path  # noqa: F401
from huggingface_hub import model_info, snapshot_download

from smoke_monitor.config import load_config

cfg = load_config(check_placeholders=False, require_smtp=False)
info = model_info(cfg.model_id)
print(f"Model: {cfg.model_id}\nRevision: {info.sha}\nLicense tag: {info.card_data.license if info.card_data else 'unknown'}")
cfg.model_local_dir.mkdir(parents=True, exist_ok=True)
snapshot_download(cfg.model_id, revision=info.sha, local_dir=str(cfg.model_local_dir),
                  allow_patterns=["*.json", "*.txt", "model.safetensors"])
(cfg.model_local_dir / "REVISION.txt").write_text(f"{cfg.model_id}@{info.sha}\n")
from smoke_monitor.detector import GroundingDinoDetector  # verify it loads from disk

GroundingDinoDetector(cfg.model_local_dir, cfg.detection_prompt, cfg.box_threshold, cfg.text_threshold, "cpu")
print(f"OK: model downloaded to {cfg.model_local_dir} and loads offline. Pin revision {info.sha} in THIRD_PARTY_LICENSES.md.")
