"""lib.hf_client の単体テスト（ネットワークなし・純粋ロジック部分のみ）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.hf_client import guess_model_kind


def test_guess_model_kind_vae():
    assert guess_model_kind("sdxl_vae.safetensors") == "vae"


def test_guess_model_kind_lora():
    assert guess_model_kind("my_character_lora_v2.safetensors") == "loras"


def test_guess_model_kind_checkpoint_fallback():
    assert guess_model_kind("unknown_model.safetensors") == "checkpoints"


def test_guess_model_kind_other_fallback():
    assert guess_model_kind("weird_file.bin") == "other"


def test_guess_model_kind_text_encoder():
    assert guess_model_kind("t5xxl_fp8.safetensors") == "text_encoders"
