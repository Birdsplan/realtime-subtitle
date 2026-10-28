#!/usr/bin/env python3
"""
Short end-to-end smoke test without opening the GUI.

It records system audio, transcribes it locally, and optionally translates the
recognized text with DeepSeek.

Example:

    python tests/test_realtime_pipeline_smoke.py --duration 8 --translate
"""

import argparse
import datetime as dt
import os
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio_capture import AudioCapture
from transcriber import Transcriber
from translator import Translator


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


def write_wav(path, audio, sample_rate):
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(audio, -1.0, 1.0)
    pcm16 = (clipped * 32767).astype(np.int16)

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16.tobytes())


def record_system_audio(duration, sample_rate, output_dir):
    frames = int(duration * sample_rate)
    capture = AudioCapture(
        input_mode="system",
        sample_rate=sample_rate,
        streaming_step_size=0.2,
    )

    chunks = []
    captured = 0
    print("Recording system audio...")
    print(f"  Duration: {duration}s")
    print(f"  Sample rate: {sample_rate}")
    print("  Tip: play a speech video while this runs.")

    try:
        for chunk in capture.generator():
            chunks.append(chunk)
            captured += len(chunk)
            if captured >= frames:
                break
    finally:
        capture.stop()

    if chunks:
        audio = np.concatenate(chunks)[:frames]
    else:
        audio = np.zeros(frames, dtype=np.float32)

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    wav_path = output_dir / f"pipeline_smoke_system_audio_{timestamp}.wav"
    write_wav(wav_path, audio, sample_rate)
    return audio, wav_path


def transcribe(audio, args):
    language = None if args.language == "auto" else args.language
    transcriber = Transcriber(
        backend=args.backend,
        model_size=args.model,
        device=args.device,
        compute_type=args.compute_type,
        language=language,
    )
    return transcriber.transcribe(audio)


def translate(text, args):
    translator = Translator(
        provider="deepseek",
        api_key_env=args.api_key_env,
        base_url=args.base_url,
        model=args.translation_model,
        target_lang=args.target_lang,
        disable_thinking=True,
    )
    return translator.translate(text, use_context=False, source_lang=args.language, target_lang=args.target_lang)


def parse_args():
    parser = argparse.ArgumentParser(description="Record system audio, transcribe, and optionally translate.")
    parser.add_argument("--wav", type=Path, help="Use an existing WAV instead of recording system audio.")
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--output-dir", type=Path, default=Path("test_outputs"))
    parser.add_argument("--backend", choices=["whisper", "funasr"], default="whisper")
    parser.add_argument("--model", default="tiny")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--language", default="auto")
    parser.add_argument("--translate", action="store_true")
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--base-url", default="https://api.deepseek.com")
    parser.add_argument("--translation-model", default="deepseek-v4-flash")
    parser.add_argument("--target-lang", default="zh-CN")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.wav:
        wav_path = args.wav
        audio = load_wav(wav_path, args.sample_rate)
    else:
        audio, wav_path = record_system_audio(args.duration, args.sample_rate, args.output_dir)
    rms = float(np.sqrt(np.mean(audio**2))) if audio.size else 0.0
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0

    print("\nRecorded audio:")
    print(f"  Path: {wav_path.resolve()}")
    print(f"  RMS: {rms:.6f}")
    print(f"  Peak: {peak:.6f}")

    text = transcribe(audio, args)
    print("\nASR:")
    print(text if text else "(empty)")

    if args.translate:
        if not text:
            print("\nTranslation skipped because ASR result is empty.")
            return
        if not os.getenv(args.api_key_env):
            raise SystemExit(f"{args.api_key_env} is not set for this process.")

        translated = translate(text, args)
        print("\nTranslation:")
        print(translated if translated else "(empty)")


if __name__ == "__main__":
    main()
