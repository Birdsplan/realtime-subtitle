#!/usr/bin/env python3
"""
Standalone audio capture smoke test.

List devices only:

    python tests/test_audio_capture.py --list

Record 10 seconds from the default input device:

    python tests/test_audio_capture.py

Record from a specific input device:

    python tests/test_audio_capture.py --device 3 --duration 10
"""

import argparse
import datetime as dt
import os
import platform
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd


SYSTEM_AUDIO_KEYWORDS = (
    "blackhole",
    "loopback",
    "stereo mix",
    "what u hear",
    "立体声混音",
    "vb-audio",
    "vb cable",
    "cable output",
    "cable input",
    "voicemeeter",
    "monitor",
)


def _hostapi_name(hostapis, index):
    try:
        return hostapis[index]["name"]
    except Exception:
        return "unknown"


def _is_system_audio_candidate(device, hostapi_name):
    name = device["name"].lower()
    if any(keyword in name for keyword in SYSTEM_AUDIO_KEYWORDS):
        return True
    if platform.system() == "Windows" and "wasapi" in hostapi_name.lower():
        return device["max_output_channels"] > 0 and device["max_input_channels"] == 0
    return False


def list_devices():
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    default_input, default_output = sd.default.device

    print("Audio host APIs:")
    for i, hostapi in enumerate(hostapis):
        print(f"  [{i}] {hostapi['name']}")

    print("\nAudio devices:")
    for index, device in enumerate(devices):
        hostapi = _hostapi_name(hostapis, device["hostapi"])
        markers = []
        if index == default_input:
            markers.append("DEFAULT_INPUT")
        if index == default_output:
            markers.append("DEFAULT_OUTPUT")
        if _is_system_audio_candidate(device, hostapi):
            markers.append("POSSIBLE_SYSTEM_AUDIO")

        marker_text = f" ({', '.join(markers)})" if markers else ""
        print(
            f"  [{index:>2}] {device['name']} | hostapi={hostapi} | "
            f"in={device['max_input_channels']} out={device['max_output_channels']} | "
            f"default_sr={int(device['default_samplerate'])}{marker_text}"
        )

    print("\nInput devices:")
    input_devices = [
        (i, d)
        for i, d in enumerate(devices)
        if d["max_input_channels"] > 0
    ]
    if not input_devices:
        print("  No input devices found.")
    for index, device in input_devices:
        hostapi = _hostapi_name(hostapis, device["hostapi"])
        print(f"  [{index}] {device['name']} ({hostapi})")

    candidates = [
        (i, d)
        for i, d in enumerate(devices)
        if _is_system_audio_candidate(d, _hostapi_name(hostapis, d["hostapi"]))
    ]
    print("\nPossible system-audio / loopback candidates:")
    if not candidates:
        print("  None detected by name/host API.")
    for index, device in candidates:
        hostapi = _hostapi_name(hostapis, device["hostapi"])
        direction = "input-capable" if device["max_input_channels"] > 0 else "output-only"
        print(f"  [{index}] {device['name']} ({hostapi}, {direction})")

    if platform.system() == "Windows":
        print(
            "\nWindows note: output-only WASAPI devices may still require a dedicated "
            "loopback implementation or a virtual cable device before they can be "
            "captured as input."
        )


def _resolve_device(device_arg):
    if device_arg == "auto":
        return None
    try:
        return int(device_arg)
    except ValueError as exc:
        raise SystemExit("--device must be 'auto' or a numeric device index") from exc


def _write_wav(path, audio, sample_rate):
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(audio, -1.0, 1.0)
    pcm16 = (clipped * 32767).astype(np.int16)

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(pcm16.shape[1] if pcm16.ndim > 1 else 1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16.tobytes())


def record_audio(device_arg, sample_rate, channels, duration, output_dir):
    device_index = _resolve_device(device_arg)
    device_info = sd.query_devices(device_index, kind="input")

    if channels > device_info["max_input_channels"]:
        raise SystemExit(
            f"Device supports only {device_info['max_input_channels']} input channel(s); "
            f"requested {channels}."
        )

    print("Recording settings:")
    print(f"  Device: {device_info['name']}")
    print(f"  Device index: {device_info['index']}")
    print(f"  Sample rate: {sample_rate}")
    print(f"  Channels: {channels}")
    print(f"  Duration: {duration} seconds")

    try:
        sd.check_input_settings(
            device=device_index,
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
        )
    except sd.PortAudioError as exc:
        raise SystemExit(
            "Input settings are not supported by this device.\n"
            f"  Device: {device_info['name']}\n"
            f"  Sample rate: {sample_rate}\n"
            f"  Channels: {channels}\n"
            f"  PortAudio error: {exc}\n\n"
            "Try the device default sample rate from --list, or try --channels 2."
        ) from exc

    frames = int(sample_rate * duration)
    print("\nRecording now...")
    try:
        audio = sd.rec(
            frames,
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
            device=device_index,
        )
        sd.wait()
    except sd.PortAudioError as exc:
        raise SystemExit(
            "Could not open the selected input device.\n"
            f"  Device: {device_info['name']}\n"
            f"  Device index: {device_info['index']}\n"
            f"  Sample rate: {sample_rate}\n"
            f"  Channels: {channels}\n"
            f"  PortAudio error: {exc}\n\n"
            "Next things to try:\n"
            f"  1. python tests/test_audio_capture.py --device {device_info['index']} "
            f"--sample-rate {int(device_info['default_samplerate'])} --channels 2 --duration 10\n"
            "  2. If this is Stereo Mix, enable it in Windows Sound settings and set it as an allowed input device.\n"
            "  3. If it still fails, use a WASAPI loopback or virtual cable path instead."
        ) from exc

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"audio_capture_{timestamp}.wav"
    _write_wav(output_path, audio, sample_rate)

    rms = float(np.sqrt(np.mean(audio**2))) if audio.size else 0.0
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0

    print("\nSaved WAV:")
    print(f"  Path: {output_path.resolve()}")
    print(f"  Sample rate: {sample_rate}")
    print(f"  Channels: {channels}")
    print(f"  Frames: {frames}")
    print(f"  RMS: {rms:.6f}")
    print(f"  Peak: {peak:.6f}")


def parse_args():
    parser = argparse.ArgumentParser(description="List audio devices and record a WAV test file.")
    parser.add_argument("--list", action="store_true", help="List audio devices and exit.")
    parser.add_argument("--device", default="auto", help="Input device index, or 'auto'.")
    parser.add_argument("--sample-rate", type=int, default=16000, help="Recording sample rate.")
    parser.add_argument("--channels", type=int, default=1, help="Number of input channels.")
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
    print(f"sounddevice: {sd.__version__}")

    list_devices()

    if args.list:
        return

    if args.duration <= 0:
        raise SystemExit("--duration must be greater than 0")

    record_audio(
        device_arg=args.device,
        sample_rate=args.sample_rate,
        channels=args.channels,
        duration=args.duration,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    # Keep PortAudio logs readable on Windows terminals.
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
