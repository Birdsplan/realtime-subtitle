#!/usr/bin/env python3
"""
Standalone Windows system-audio loopback smoke test.

List loopback devices:

    python tests/test_system_audio_loopback.py --list

Record 10 seconds from the default speaker loopback:

    python tests/test_system_audio_loopback.py --duration 10

Record from a specific loopback index shown by --list:

    python tests/test_system_audio_loopback.py --loopback-index 1 --duration 10
"""

import argparse
import datetime as dt
import platform
import sys
import wave
from pathlib import Path

import numpy as np
import soundcard as sc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _write_wav(path, audio, sample_rate):
    path.parent.mkdir(parents=True, exist_ok=True)
    if audio.ndim == 1:
        audio = audio[:, None]

    clipped = np.clip(audio, -1.0, 1.0)
    pcm16 = (clipped * 32767).astype(np.int16)

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(pcm16.shape[1])
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16.tobytes())


def _device_label(device):
    return repr(device).strip("<>")


def list_devices():
    speakers = sc.all_speakers()
    loopbacks = sc.all_microphones(include_loopback=True)
    loopbacks = [device for device in loopbacks if device.isloopback]
    default_speaker = sc.default_speaker()

    print("Speakers:")
    for index, speaker in enumerate(speakers):
        marker = " DEFAULT" if speaker.name == default_speaker.name else ""
        print(f"  [{index}] {_device_label(speaker)}{marker}")

    print("\nLoopback devices:")
    if not loopbacks:
        print("  No loopback devices found.")
    for index, loopback in enumerate(loopbacks):
        marker = " DEFAULT_SPEAKER_LOOPBACK" if loopback.name == default_speaker.name else ""
        print(f"  [{index}] {_device_label(loopback)}{marker}")

    return loopbacks, default_speaker


def choose_loopback(loopbacks, default_speaker, loopback_index):
    if not loopbacks:
        raise SystemExit("No loopback devices found.")

    if loopback_index is not None:
        if loopback_index < 0 or loopback_index >= len(loopbacks):
            raise SystemExit(f"--loopback-index must be between 0 and {len(loopbacks) - 1}")
        return loopbacks[loopback_index]

    for loopback in loopbacks:
        if loopback.name == default_speaker.name:
            return loopback

    return loopbacks[0]


def record_loopback(loopback, sample_rate, duration, output_dir):
    frames = int(sample_rate * duration)
    print("\nRecording settings:")
    print(f"  Loopback: {_device_label(loopback)}")
    print(f"  Sample rate: {sample_rate}")
    print(f"  Duration: {duration} seconds")
    print("  Tip: play a video or music during this window.")

    print("\nRecording now...")
    with loopback.recorder(samplerate=sample_rate) as recorder:
        audio = recorder.record(numframes=frames)

    if audio.shape[0] > frames:
        audio = audio[:frames]

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"system_audio_loopback_{timestamp}.wav"
    _write_wav(output_path, audio, sample_rate)

    rms = float(np.sqrt(np.mean(audio**2))) if audio.size else 0.0
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0

    print("\nSaved WAV:")
    print(f"  Path: {output_path.resolve()}")
    print(f"  Sample rate: {sample_rate}")
    print(f"  Channels: {audio.shape[1] if audio.ndim > 1 else 1}")
    print(f"  Frames: {audio.shape[0]}")
    print(f"  RMS: {rms:.6f}")
    print(f"  Peak: {peak:.6f}")

    if rms == 0.0 and peak == 0.0:
        print(
            "\nWarning: captured pure silence. Check that audio is playing through "
            "the selected speaker device."
        )


def record_via_audio_capture(loopback_index, sample_rate, duration, output_dir):
    from audio_capture import AudioCapture

    frames = int(sample_rate * duration)
    capture = AudioCapture(
        input_mode="system",
        loopback_index=loopback_index,
        sample_rate=sample_rate,
        streaming_step_size=0.2,
    )

    print("\nRecording settings:")
    print("  Source: AudioCapture(input_mode='system')")
    print(f"  Loopback index: {loopback_index if loopback_index is not None else 'auto'}")
    print(f"  Sample rate: {sample_rate}")
    print(f"  Duration: {duration} seconds")
    print("  Tip: play a video or music during this window.")

    chunks = []
    captured = 0
    print("\nRecording now...")
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
    output_path = output_dir / f"audio_capture_system_loopback_{timestamp}.wav"
    _write_wav(output_path, audio, sample_rate)

    rms = float(np.sqrt(np.mean(audio**2))) if audio.size else 0.0
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0

    print("\nSaved WAV:")
    print(f"  Path: {output_path.resolve()}")
    print(f"  Sample rate: {sample_rate}")
    print("  Channels: 1")
    print(f"  Frames: {audio.shape[0]}")
    print(f"  RMS: {rms:.6f}")
    print(f"  Peak: {peak:.6f}")


def parse_args():
    parser = argparse.ArgumentParser(description="Record Windows system audio via loopback.")
    parser.add_argument("--list", action="store_true", help="List speakers/loopbacks and exit.")
    parser.add_argument("--loopback-index", type=int, help="Loopback index from --list.")
    parser.add_argument(
        "--via-audio-capture",
        action="store_true",
        help="Record through the project's AudioCapture system mode.",
    )
    parser.add_argument("--sample-rate", type=int, default=48000, help="Recording sample rate.")
    parser.add_argument("--duration", type=float, default=10.0, help="Recording duration in seconds.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("test_outputs"),
        help="Directory for generated WAV files.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print(f"Platform: {platform.system()} {platform.release()}")
    print("Backend: soundcard loopback")

    loopbacks, default_speaker = list_devices()
    if args.list:
        return

    if args.duration <= 0:
        raise SystemExit("--duration must be greater than 0")

    if args.via_audio_capture:
        record_via_audio_capture(
            loopback_index=args.loopback_index,
            sample_rate=args.sample_rate,
            duration=args.duration,
            output_dir=args.output_dir,
        )
    else:
        loopback = choose_loopback(loopbacks, default_speaker, args.loopback_index)
        record_loopback(
            loopback=loopback,
            sample_rate=args.sample_rate,
            duration=args.duration,
            output_dir=args.output_dir,
        )


if __name__ == "__main__":
    main()
