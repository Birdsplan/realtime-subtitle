# Realtime Subtitle Project Context

> Last updated: 2026-07-26  
> Primary platform: Windows 11  
> Workspace: `D:\code\realtime-subtitle`

## 1. Start Here

This repository is a fork of:

```text
https://github.com/Birdsplan/realtime-subtitle.git
```

It is being developed into a local desktop application that captures microphone or Windows system audio, performs local speech recognition, translates stable English subtitles into Chinese through the DeepSeek API, displays bilingual subtitles in an always-on-top overlay, and saves transcripts locally.

The current application is usable. Treat it as an incremental product under active development, not as a prototype that should be rewritten from scratch.

Before changing code, read these files in this order:

1. `CODEX_PROJECT_BRIEF.md` - original product constraints and development rules.
2. `CLAUDE.md` - this handoff and current operating context.
3. `TECHNICAL_IMPLEMENTATION.md` - detailed, current implementation notes in Chinese.
4. `ARCHITECTURE.md` - an early architecture snapshot; useful historically, but some details are now outdated.
5. `PACKAGING.md` - current packaging and distribution notes.

Do not modify `CODEX_PROJECT_BRIEF.md` unless the user explicitly requests it.

## 2. Product Goal

The intended experience is:

```text
Audio input
  -> local ASR
  -> speech segmentation and text stabilization
  -> DeepSeek translation
  -> bilingual floating subtitle overlay
  -> transcript logging
```

The main use case is watching English video or live content on Windows and receiving fast English transcription followed by natural Chinese translation.

Product priorities, in order:

1. Reliable Windows system-audio capture.
2. Fast and reasonably accurate local English ASR.
3. Source text displayed without waiting for translation.
4. Stable, concise Chinese translation.
5. A readable, unobtrusive subtitle overlay.
6. Clear diagnostics and recoverable failures.
7. Straightforward installation and distribution.

The user is new to software project management. Explain decisions in plain language, keep changes small, and provide concrete test steps after each change.

## 3. Current Working Configuration

The active local configuration is approximately:

```ini
[translation]
provider = deepseek
api_key_env = DEEPSEEK_API_KEY
base_url = https://api.deepseek.com
model = deepseek-v4-flash
target_lang = zh-CN
threads = 2
disable_thinking = true

[transcription]
backend = whisper
whisper_model = small.en
device = cuda
compute_type = float16
source_language = en
transcription_workers = 1

[audio]
input_mode = system
sample_rate = 16000
silence_threshold = 0.005
silence_duration = 0.8
max_phrase_duration = 8
streaming_step_size = 0.2
update_interval = 1.5
partial_transcription = true
max_partial_duration = 3.0
final_overlap_duration = 0.8
capture_buffer_seconds = 8.0

[display]
window_width = 1000
window_height = 320
max_visible_items = 3
bottom_margin = 48
position = bottom_center
original_font_size = 20
translation_font_size = 24
panel_opacity = 118
auto_hide_controls = true
```

Read the actual `config.ini` before relying on these values because the Dashboard may update it.

Never hard-code, print, commit, or expose the API key. It is stored in the Windows user environment variable `DEEPSEEK_API_KEY`. `config.ini` should not contain the real secret.

The configured DeepSeek model name is a user setting, not a guaranteed permanent API model identifier. Verify current DeepSeek documentation before changing model names or request formats.

## 4. Current Architecture

### Main modules

| File | Responsibility |
|---|---|
| `dashboard.py` | Main settings UI, startup worker, system tray, start/stop lifecycle |
| `main.py` | Composes modules and runs the real-time processing pipeline |
| `audio_capture.py` | Microphone/system-loopback capture and bounded audio ring buffer |
| `speech_segmenter.py` | Pure speech-segment finalization rules |
| `transcriber.py` | Replaceable ASR wrapper; active path is faster-whisper |
| `text_stabilizer.py` | Removes repeated text caused by overlapping final audio |
| `translator.py` | OpenAI-compatible translation wrapper configured for DeepSeek |
| `transcript_logger.py` | Thread-safe JSONL and readable TXT session logs |
| `overlay_window.py` | Always-on-top bilingual subtitle overlay |
| `config.py` | Loads `config.ini` and environment-variable overrides |

### Active data flow

```text
Windows WASAPI loopback via soundcard
  -> audio-capture-worker
  -> bounded AudioChunkBuffer
  -> Pipeline processing thread
  -> RMS-based speech segmentation
  -> serial faster-whisper ASR on CUDA
  -> overlap-prefix deduplication
  -> final source text emitted to Qt immediately
  -> DeepSeek translation thread pool
  -> translated text emitted later to the same subtitle item
  -> overlay and transcript logs
```

### Thread ownership

| Execution context | Work |
|---|---|
| Qt main thread | Dashboard, overlay, tray, widget updates |
| `StartupWorker` QThread | Pipeline/model initialization and ASR warmup |
| Pipeline Python thread | Audio consumption, accumulation, segmentation, task submission |
| Audio capture worker | Continuous device reads into the bounded buffer |
| ASR executor | One serial worker for CUDA inference |
| Translation executor | Two workers for network translation requests |

Do not perform ASR, model loading, audio blocking reads, or API requests on the Qt main thread.

## 5. Important Runtime Semantics

### Partial versus final subtitles

- Partial ASR text is fast and provisional.
- Partial text is displayed as source text only.
- Partial text is not translated and is not written as a final transcript record.
- Final ASR text is overlap-deduplicated, logged, displayed immediately, and then translated asynchronously.
- The translation area remains hidden while translation is pending; do not reintroduce a visible `Translating...` subtitle row without discussing the UX tradeoff.

The source-first behavior is intentional. A slow DeepSeek response must not block ASR or delay already recognized English text.

### Speech segmentation

`speech_segmenter.py` currently finalizes a segment using three rules:

1. Natural cut: more than 2 seconds of accumulated audio followed by 0.8 seconds of silence.
2. Soft limit: after 6 seconds, a short 0.4-second pause can finalize the segment.
3. Hard limit: after 8 seconds, finalize even without silence.

This was changed from a 0.5-second natural pause because subtitles were splitting too frequently. The 0.8-second value slightly increases finalization latency but does not reduce model inference speed.

Do not solve visual subtitle grouping by blindly increasing ASR segment length. Audio segmentation, ASR context, translation units, and visual grouping are related but separate concerns.

### Audio buffering

Audio capture and processing are decoupled through `AudioChunkBuffer`, a thread-safe bounded ring buffer. With the current settings, it holds roughly 40 chunks, or 8 seconds of audio. On overflow it drops the oldest chunk to preserve real-time behavior.

Monitor its `pushed`, `popped`, `dropped`, and `high_watermark` statistics when diagnosing missing speech.

## 6. How to Run the Application

### Normal use without a terminal

Double-click:

```text
run_dashboard_silent.vbs
```

Then click `Launch Translator` in the Dashboard.

### Debug use with terminal output

Run:

```text
run_dashboard.bat
```

Use this mode for model-loading, CUDA, audio-device, and DeepSeek errors.

The Dashboard starts quickly, but clicking `Launch Translator` loads the approximately 464 MB `small.en` model, initializes CUDA, and performs ASR warmup. A cold start of several seconds is expected. Stopping and launching again currently recreates the Pipeline and reloads the model.

Closing the Dashboard hides it to the system tray. Use the tray `Exit` command to terminate the application completely.

## 7. Tests

Run offline tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

The most recent full offline run passed 20 tests with one real DeepSeek API test skipped by design.

Important focused tests:

```text
tests/test_audio_ring_buffer.py
tests/test_config_realtime_asr.py
tests/test_deepseek_translator.py
tests/test_overlay_layout.py
tests/test_pipeline_source_first.py
tests/test_speech_segmenter.py
tests/test_text_stabilizer.py
tests/test_transcript_logger.py
```

Hardware/manual tests:

```text
tests/test_system_audio_loopback.py
tests/test_audio_capture.py
tests/test_cuda_asr.py
tests/test_asr_transcriber.py
tests/test_realtime_pipeline_smoke.py
```

The live DeepSeek test is opt-in:

```powershell
$env:RUN_DEEPSEEK_LIVE_TEST = "1"
.\.venv\Scripts\python.exe tests\test_deepseek_translator.py
```

Do not run a paid live API test unless it is necessary and the user understands that it makes a real request.

## 8. Logs and Data Boundaries

Automatic logs are written to:

```text
logs/transcript_<session>.jsonl
logs/transcript_<session>.txt
```

Manual overlay exports are written to:

```text
transcripts/
```

Raw audio and Whisper inference remain local. Stable recognized text is sent to DeepSeek for translation. Source and translated text are stored in local logs. Never include the API key in logs or diagnostics.

## 9. Known Limitations

1. RMS-based segmentation is simple amplitude detection, not semantic voice activity detection. Music and background noise can confuse it.
2. `main.py` repeatedly uses `numpy.concatenate` while accumulating audio. This is acceptable at the current scale but not ideal.
3. `transcription_workers` is conceptually configurable, but the active ASR executor is fixed to one worker. Extra transcriber creation is legacy behavior and should not be treated as working parallel ASR.
4. `Translator.translate()` currently returns normalized source text on an API failure. This can look like a successful untranslated result and should eventually use an explicit success/failure result.
5. Overlap deduplication is word-based and best suited to English whitespace tokenization.
6. The inactive MLX/FunASR paths have not received the same Windows validation as faster-whisper CUDA. The MLX path contains legacy/suspicious code and must be audited before use.
7. Translation requests can complete out of order. The overlay uses `chunk_id` to update the correct item, but completion timing may still look uneven.
8. Model loading, CUDA DLLs, NVIDIA drivers, model caches, and API setup make Windows packaging non-trivial.
9. Logs do not currently have retention or automatic cleanup.
10. The worktree is intentionally dirty and contains active user/project changes. Do not reset, revert, or replace unrelated modifications.

## 10. Development Rules

Follow these rules unless the user explicitly overrides them:

1. Inspect the current code and `git status` before editing.
2. Do not rewrite the application or introduce a new framework for a local change.
3. Keep audio capture, segmentation, ASR, translation, UI, and logging separated.
4. Prefer small, traceable changes with focused tests.
5. Do not block the Qt UI thread.
6. Do not hard-code secrets or expose them in output.
7. Work with existing uncommitted changes; never discard them automatically.
8. Avoid formatting-only churn and unrelated refactors.
9. Explain new heavy dependencies before adding them.
10. For multiple viable approaches, explain the tradeoffs and recommend the lowest-risk option.
11. Update or add a small test for changed behavior.
12. Update `TECHNICAL_IMPLEMENTATION.md` when architecture, data flow, configuration semantics, or known limitations change.

After each implementation change, report:

```text
What was checked
What was found
Files changed
How to test
Risks or limitations
Suggested next step
```

## 11. Recommended Next Priorities

Do not assume these are approved tasks; confirm priority with the user before making broad changes.

1. Add explicit translation success/failure results instead of treating source fallback as success.
2. Add startup-stage timing so model loading, CUDA initialization, and warmup delays are visible in the Dashboard.
3. Prefer the complete local Whisper cache before making Hugging Face network checks on repeat startup.
4. Consider preserving the loaded ASR model across Stop/Start if memory usage is acceptable.
5. Add runtime diagnostics for audio RMS, buffer drops, ASR latency, and translation latency.
6. Evaluate visual grouping of adjacent subtitle segments without forcing longer ASR segments.
7. Evaluate a stronger VAD only after collecting evidence from the current RMS segmenter.
8. Improve Windows packaging and first-run dependency/model checks.

## 12. Definition of a Good Change

A good change in this project:

- solves one clearly observed user problem;
- preserves the working Windows CUDA path;
- does not regress source-first subtitle display;
- keeps the Dashboard and overlay responsive;
- includes a focused automated test where practical;
- includes a simple manual verification procedure;
- documents any remaining limitation honestly.
