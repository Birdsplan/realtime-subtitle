#!/usr/bin/env python3
"""
Smoke test for faster-whisper CUDA acceleration.

Examples:

    python tests/test_cuda_asr.py
    python tests/test_cuda_asr.py --model base.en --wav test_outputs/sample.wav
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from transcriber import Transcriber


def load_wav(path, target_sample_rate):
    import soundfile as sf

    audio, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    if sample_rate != target_sample_rate:
        from scipy.signal import resample_poly
        import math

        gcd = math.gcd(sample_rate, target_sample_rate)
        audio = resample_poly(audio, target_sample_rate // gcd, sample_rate // gcd)

    return audio.astype(np.float32, copy=False)


def require_cuda():
    import ctranslate2

    device_count = ctranslate2.get_cuda_device_count()
    print(f"CTranslate2: {ctranslate2.__version__}")
    print(f"CUDA devices: {device_count}")
    if device_count < 1:
        raise SystemExit("No CUDA device is visible to CTranslate2.")

    compute_types = ctranslate2.get_supported_compute_types("cuda")
    print(f"CUDA compute types: {sorted(compute_types)}")
    if "float16" not in compute_types:
        raise SystemExit("CTranslate2 CUDA is visible, but float16 is not supported.")


def parse_args():
    parser = argparse.ArgumentParser(description="Test faster-whisper CUDA inference.")
    parser.add_argument("--model", default="base.en")
    parser.add_argument("--language", default="en")
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--wav", type=Path)
    return parser.parse_args()


def main():
    args = parse_args()
    require_cuda()

    if args.wav:
        audio = load_wav(args.wav, args.sample_rate)
    else:
        audio = np.zeros(args.sample_rate, dtype=np.float32)

    load_started = time.perf_counter()
    transcriber = Transcriber(
        backend="whisper",
        model_size=args.model,
        device="cuda",
        compute_type=args.compute_type,
        language=args.language,
    )
    load_seconds = time.perf_counter() - load_started

    transcribe_started = time.perf_counter()
    text = transcriber.transcribe(audio)
    transcribe_seconds = time.perf_counter() - transcribe_started

    duration = len(audio) / args.sample_rate if args.sample_rate else 0.0
    realtime_factor = transcribe_seconds / duration if duration else 0.0

    print("\nCUDA ASR smoke result:")
    print(f"  Model: {args.model}")
    print(f"  Audio duration: {duration:.2f}s")
    print(f"  Model load: {load_seconds:.2f}s")
    print(f"  Transcribe: {transcribe_seconds:.2f}s")
    print(f"  Realtime factor: {realtime_factor:.2f}x")
    print(f"  Text: {text or '(empty)'}")


if __name__ == "__main__":
    main()
