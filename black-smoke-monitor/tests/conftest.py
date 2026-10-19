import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from dotenv import dotenv_values
import io

import config

BASE = {k: v for k, v in dotenv_values(stream=io.StringIO(config.ENV_TEMPLATE)).items()}


def make_env(tmp_path, **over):
    env = dict(BASE, SCREENSHOT_DIR=str(tmp_path / "shots"), MODEL_PATH=str(tmp_path / "m.onnx"))
    env.update({k: str(v) for k, v in over.items()})
    return env


@pytest.fixture
def settings(tmp_path):
    return config.load_settings(make_env(tmp_path))


@pytest.fixture
def mk(tmp_path):
    return lambda **over: config.load_settings(make_env(tmp_path, **over))
