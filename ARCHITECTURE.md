# Architecture Notes

This note summarizes the current repository before any functional changes.
It is based on reading the existing code and project brief only.

## 1. Project Startup Entry

There are three practical startup paths:

- `start_windows.bat`
  - Activates `.venv`.
  - Runs `python reloader.py`.
- `start_mac.sh`
  - Activates `.venv`.
  - Runs `python reloader.py`.
- `reloader.py`
  - Starts `launcher.py` as a child process.
  - Watches root-level `.py` and `.ini` files.
  - Restarts the child process on changes.

The GUI startup chain is:

```text
start_windows.bat / start_mac.sh
  -> reloader.py
  -> launcher.py
  -> dashboard.py
  -> main.Pipeline + overlay_window.OverlayWindow
```

Direct developer entry points also exist:

- `python launcher.py`: opens the launcher, checks dependencies, then opens the dashboard.
- `python dashboard.py`: opens the control center directly.
- `python main.py`: starts the overlay session directly without the launcher/dashboard.

## 2. Main Configuration Files

- `config.py`
  - Defines the global `config = Config()` object.
  - Reads `config.ini` from the repository root if present.
  - Falls back to defaults when `config.ini` is missing.
  - Environment variables currently supported:
    - `OPENAI_BASE_URL`
    - `OPENAI_API_KEY`
- `config.ini.example`
  - Shows the expected sections:
    - `[api]`
    - `[translation]`
    - `[display]`
    - `[transcription]`
    - `[audio]`
  - Contains an example API key value; future changes should avoid committing real secrets.
- `dashboard.py`
  - Saves UI-edited settings back to `config.ini`.
- `settings_window.py`
  - Older/smaller settings window that also writes to `config.ini`.

Important current config fields:

- API/translation:
  - `api.base_url`
  - `api.api_key`
  - `translation.model`
  - `translation.target_lang`
  - `translation.threads`
- ASR:
  - `transcription.backend`
  - `transcription.whisper_model`
  - `transcription.funasr_model`
  - `transcription.device`
  - `transcription.compute_type`
  - `transcription.source_language`
  - `transcription.transcription_workers`
- Audio:
  - `audio.device_index`
  - `audio.sample_rate`
  - `audio.silence_threshold`
  - `audio.silence_duration`
  - `audio.chunk_duration`
  - `audio.max_phrase_duration`
  - `audio.streaming_mode`
  - `audio.streaming_interval`
  - `audio.streaming_step_size`
  - `audio.update_interval`
  - `audio.streaming_overlap`
- Display:
  - `display.display_duration`
  - `display.window_width`
  - `display.window_height`

## 3. Audio Capture Module

Primary file: `audio_capture.py`

Main class:

- `AudioCapture`

Current responsibilities:

- Opens a `sounddevice.InputStream`.
- Captures mono float32 audio.
- Provides two capture styles:
  - `generator()`: yields small raw audio chunks continuously.
  - `start()` plus `get_audio_stream()`: starts a background recording thread and yields completed phrases from an internal queue.

Current production path:

- `main.Pipeline.processing_loop()` uses `self.audio.generator()`.
- It does not call `AudioCapture.start()` in the active path.
- Buffering, silence detection, and final segment decisions are currently handled mostly in `main.py`, not inside `audio_capture.py`.
- `AudioCapture.generator()` now supports:
  - `input_mode = microphone`: uses `sounddevice.InputStream`.
  - `input_mode = system`: uses `soundcard` loopback from the default speaker or configured loopback index.

Platform notes:

- macOS system audio is expected to use BlackHole or a multi-output device.
- Windows installer text recommends VB-CABLE for system audio.
- Windows system audio has a basic `soundcard` loopback path for the active default speaker.

Related file:

- `audio_device_manager.py`
  - macOS-only helper.
  - Uses `sounddevice` and macOS automation helpers to guide multi-output device setup.
  - Raises an error on non-macOS platforms.

## 4. ASR / Speech Recognition Module

Primary file: `transcriber.py`

Main class:

- `Transcriber`

Supported backends:

- `whisper`
  - Uses `faster_whisper.WhisperModel`.
- `mlx`
  - Intended to use `mlx_whisper` on Apple Silicon.
- `funasr`
  - Uses `funasr.AutoModel`.

Current ASR flow:

```text
numpy float32 audio buffer
  -> Transcriber.transcribe(audio_data, prompt=previous_final_text)
  -> backend-specific transcribe method
  -> hallucination / prompt echo filters
  -> text string
```

Current text cleanup/stability behavior:

- `Transcriber._is_hallucination()` filters repeated low-information output.
- `Transcriber._is_prompt_echo()` filters output that appears to repeat the prompt.
- `main.Pipeline` uses `last_final_text` as the prompt/context for later ASR calls.

Important observations:

- There is no separate text stabilization/segmentation module yet.
- Segmentation currently lives in `main.Pipeline.processing_loop()`.
- The MLX initializer currently contains a bare `sssss` statement, so the `mlx` backend appears likely to fail if selected.
- `tests/test_asr_transcriber.py` can now verify ASR independently from a WAV file or freshly recorded system audio. The `faster-whisper` `tiny` CPU/int8 path has been smoke-tested with a recorded system-audio sample.

## 5. Translation Module

Primary file: `translator.py`

Main class:

- `Translator`

Current behavior:

- Uses the `openai` Python client.
- Calls an OpenAI-compatible chat completions API.
- Supports custom `base_url`, which makes it compatible with local servers and other OpenAI-compatible providers.
- Reads fallback environment variables:
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL`
- Maintains a small previous-text / previous-translation context.
- Strips `<think>...</think>` blocks from reasoning-model responses.
- Returns an error string or original text on failure instead of raising in most cases.

Current translation call path:

```text
main.Pipeline._run_translation(text, chunk_id)
  -> self.translator.translate(text)
  -> OpenAI-compatible chat.completions.create(...)
  -> translated string
  -> Qt signal to overlay window
```

The current module is provider-generic, not DeepSeek-specific.

## 6. Floating Subtitle UI Module

Primary file: `overlay_window.py`

Main classes:

- `LogItem`
  - Displays one subtitle/transcript segment.
  - Shows original text and translated text.
- `ResizeHandle`
  - Custom resize handle widget.
- `OverlayWindow`
  - Frameless, translucent, always-on-top PyQt6 window.
  - Stores transcript data in memory.
  - Saves session transcripts to `transcripts/transcript_YYYYMMDD_HHMMSS.txt`.
  - Emits `stop_requested`.

Current update path:

```text
Pipeline.signals.update_text.emit(chunk_id, original, translated)
  -> OverlayWindow.update_text(chunk_id, original, translated)
  -> create or update LogItem
  -> update in-memory transcript_data
```

UI notes:

- Original text is shown smaller and grey.
- Translation is shown larger and white.
- The overlay scrolls to the latest segment.
- macOS-specific AppKit logic attempts to keep the window visible across Spaces.

## 7. Dashboard / Control UI

Primary file: `dashboard.py`

Main classes:

- `Dashboard`
  - Main control center.
  - Tabs for Home, Audio, Device Manager, Transcription, Translation.
  - Saves settings to `config.ini`.
  - Starts and stops the live pipeline.
- `StartupWorker`
  - A `QThread` used to initialize `main.Pipeline` without freezing the dashboard.

Dashboard start flow:

```text
Dashboard.on_start()
  -> StartupWorker.run()
  -> create main.Pipeline in background QThread
  -> Dashboard.on_pipeline_ready()
  -> create OverlayWindow on main UI thread
  -> connect Pipeline signals to OverlayWindow
  -> Pipeline.start()
```

The dashboard also has API model refresh logic that calls the OpenAI-compatible models endpoint.

## 8. Data Flow From Audio Input To Subtitle Display

Current active runtime flow:

```text
sounddevice.InputStream or soundcard loopback
  -> AudioCapture.generator()
  -> main.Pipeline.processing_loop()
  -> accumulate small audio chunks into buffer
  -> partial ASR updates every config.update_interval
  -> final segment cut by silence / soft limit / hard max duration
  -> Transcriber.transcribe()
  -> emit original text to OverlayWindow
  -> Translator.translate() in translation executor
  -> emit translated text to OverlayWindow
  -> OverlayWindow stores and displays segment
  -> optional transcript save to transcripts/*.txt
```

Partial updates:

- Partial chunks are transcribed.
- Partial chunks update the original text only.
- Partial chunks do not trigger translation.

Final updates:

- Final chunks are transcribed.
- The original text is emitted immediately with `(translating...)`.
- Translation is run asynchronously.
- The translated text is emitted when ready.

## 9. Threading / Async Design

Threading currently exists in several places:

- `launcher.DependencyInstaller`
  - `QThread` for dependency installation/checking.
- `dashboard.StartupWorker`
  - `QThread` for pipeline initialization and ASR model warmup.
- `main.Pipeline.start()`
  - Python `threading.Thread` for the audio/ASR/translation processing loop.
- `main.Pipeline.processing_loop()`
  - `ThreadPoolExecutor(max_workers=1)` for transcription jobs.
  - `ThreadPoolExecutor(max_workers=config.translation_threads)` for translation jobs.
- `audio_capture.AudioCapture.start()`
  - Legacy/alternate background recording thread path.
- `sounddevice.InputStream`
  - Native audio stream reads.

UI safety:

- The pipeline emits PyQt signals from worker/background threads.
- The overlay receives those signals on the Qt side and updates widgets.
- This is the right general direction for avoiding direct UI updates from worker threads.

Current async caveats:

- ASR is serialized by `ThreadPoolExecutor(max_workers=1)` even though some code creates multiple `Transcriber` instances.
- Translation is concurrent and controlled by `translation.threads`.
- `settings_window.py` contains comments about avoiding unsafe UI updates from worker threads, but the active dashboard path is the main settings UI.

## 10. Current Dependencies

From `requirements.txt`:

- `PyQt6`
- `faster-whisper`
- `sounddevice`
- `numpy`
- `openai`
- `pyobjc-framework-CoreAudio; sys_platform == 'darwin'`
- `funasr`
- `modelscope`
- `watchdog`

Additional imports observed in code:

- Standard library:
  - `configparser`
  - `ctypes`
  - `os`
  - `platform`
  - `queue`
  - `re`
  - `signal`
  - `subprocess`
  - `sys`
  - `threading`
  - `time`
  - `concurrent.futures`
- Optional/runtime:
  - `httpx`
  - `torch`
  - `mlx_whisper`
  - `AppKit`
  - `objc`
  - `CoreAudio`

System-level dependencies mentioned:

- FFmpeg
- BlackHole on macOS for system audio capture
- VB-CABLE or similar on Windows for system audio capture
- SwitchAudioSource on macOS as an optional helper

## 11. Potential Insertion Point For DeepSeek Translation

Lowest-risk insertion point:

- Replace or extend `translator.Translator` while keeping its public call shape stable:

```python
translated = self.translator.translate(text)
```

Why this is low risk:

- `main.Pipeline` already treats translation as a separate component.
- Translation is already called only for final/stable chunks.
- Translation already runs in a background executor.
- UI updates already tolerate a delayed translation result.
- The current client already supports OpenAI-compatible `base_url`, which is likely close to the DeepSeek API shape, but this must be verified against current official DeepSeek docs before implementation.

Recommended future shape:

```python
class Translator:
    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "zh-CN") -> str:
        ...
```

Recommended DeepSeek config additions later:

```ini
[translation]
provider = deepseek
api_key_env = DEEPSEEK_API_KEY
base_url = https://api.deepseek.com
model = <verify from official DeepSeek docs>
target_lang = zh-CN
```

Implementation notes for later:

- Do not hard-code the DeepSeek API key.
- Prefer `DEEPSEEK_API_KEY` or a config field that names the environment variable.
- Keep translation failures non-fatal.
- Add caching for repeated source text.
- Keep context short; do not resend the full transcript.
- Add a small standalone test script before wiring broader behavior.

## 12. Current Gaps / Uncertainties

- No dedicated text stabilization module exists yet; stabilization is mixed into `main.py` and `transcriber.py`.
- No dedicated transcript storage module exists yet; saving is currently handled by `OverlayWindow`.
- Windows system audio capture is not implemented via WASAPI loopback; current guidance relies on virtual cable devices.
- `config.ini` is not present in this checkout; the app will use defaults unless a user creates/saves config.
- `config.ini.example` contains an API key-like value and should not be treated as a safe secret pattern.
- `transcripts/` is created only when the user saves from the overlay; it is not present initially.
- `overlay_window.py` defines `OverlayWindow` twice; the second definition is the active one.
- The MLX backend appears likely to fail because `_init_mlx()` contains a bare `sssss` statement.
- There is no automated test for the full pipeline, audio capture, translation, or overlay behavior yet.

## 13. Files Inspected

- `CODEX_PROJECT_BRIEF.md`
- `README.md`
- `requirements.txt`
- `requirements_spec.md`
- `config.ini.example`
- `config.py`
- `main.py`
- `launcher.py`
- `reloader.py`
- `audio_capture.py`
- `audio_device_manager.py`
- `transcriber.py`
- `translator.py`
- `overlay_window.py`
- `dashboard.py`
- `settings_window.py`
- `test_funasr.py`
- `install_windows.bat`
- `start_windows.bat`
- `install_mac.sh`
- `start_mac.sh`

## 14. Suggested Next Step

Before functional development, confirm this architecture understanding.

After confirmation, the safest next implementation step is probably one small, testable module at a time. For the DeepSeek path, start by adding a provider-aware translator wrapper and a small translation test script, while preserving the existing `Pipeline -> Translator.translate()` integration point.
