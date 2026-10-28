#!/usr/bin/env python3
"""
Standalone ASR smoke test for the existing Transcriber module.

Transcribe an existing WAV file:

    python tests/test_asr_transcriber.py --wav test_outputs/example.wav

Use the small faster-whisper model on CPU:

    python tests/test_asr_transcriber.py --wav test_outputs/example.wav --backend whisper --model tiny

Record system audio first, then transcribe it:

    python tests/test_asr_transcriber.py --record-system 10 --backend whisper --model tiny
"""

import argparse
import datetime as dt
import math
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio_capture import AudioCapture
from transcriber import Transcriber


def load_audio(path, target_sample_rate=16000):
    try:
        import soundfile as sf
    except ImportError as exc:
        raise SystemExit("soundfile is required to read WAV files. Install project requirements first.") from exc

    audio, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    if sample_rate != target_sample_rate:
        audio = resample_audio(audio, sample_rate, target_sample_rate)
        sample_rate = target_sample_rate

    return audio.astype(np.float32, copy=False), sample_rate


def resample_audio(audio, source_rate, target_rate):
    try:
        from scipy.signal import resample_poly
    except ImportError as exc:
        raise SystemExit("scipy is required to resample audio. Install project requirements first.") from exc

    gcd = math.gcd(source_rate, target_rate)
    up = target_rate // gcd
    down = source_rate // gcd
    return resample_poly(audio, up, down).astype(np.float32, copy=False)


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

    print("Recording system audio for ASR test...")
    print(f"  Duration: {duration} seconds")
    print(f"  Sample rate: {sample_rate}")
    print("  Tip: play a speech video or say something in a meeting/audio source.")

    chunks = []
    captured = 0
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
    path = output_dir / f"asr_system_audio_{timestamp}.wav"
    write_wav(path, audio, sample_rate)
    print(f"Saved ASR input WAV: {path.resolve()}")
    return path


def transcribe_audio(audio, args):
    language = None if args.language == "auto" else args.language
    transcriber = Transcriber(
        backend=args.backend,
        model_size=args.model,
        device=args.device,
        compute_type=args.compute_type,
        language=language,
    )

    if args.warmup:
        transcriber.warmup()

    text = transcriber.transcribe(audio)
    return text


def parse_args():
    parser = argparse.ArgumentParser(description="Run a standalone ASR transcription test.")
    parser.add_argument("--wav", type=Path, help="Path to a WAV file to transcribe.")
    parser.add_argument("--record-system", type=float, help="Record N seconds of system audio before ASR.")
    parser.add_argument("--output-dir", type=Path, default=Path("test_outputs"))
    parser.add_argument("--target-sample-rate", type=int, default=16000)
    parser.add_argument("--backend", choices=["whisper", "funasr"], default="whisper")
    parser.add_argument("--model", default="tiny", help="Whisper model size or FunASR model name.")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--language", default="auto")
    parser.add_argument("--warmup", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.wav and not args.record_system:
        raise SystemExit("Provide --wav PATH or --record-system SECONDS.")

    wav_path = args.wav
    if args.record_system:
        wav_path = record_system_audio(
            duration=args.record_system,
            sample_rate=args.target_sample_rate,
            output_dir=args.output_dir,
        )

    audio, sample_rate = load_audio(wav_path, args.target_sample_rate)
    duration = len(audio) / sample_rate if sample_rate else 0
    rms = float(np.sqrt(np.mean(audio**2))) if audio.size else 0.0
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0

    print("\nASR input:")
    print(f"  Path: {wav_path.resolve()}")
    print(f"  Sample rate: {sample_rate}")
    print(f"  Duration: {duration:.2f}s")
    print(f"  RMS: {rms:.6f}")
    print(f"  Peak: {peak:.6f}")

    text = transcribe_audio(audio, args)

    print("\nASR result:")
    print(text if text else "(empty)")


if __name__ == "__main__":
    main()
