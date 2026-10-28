# Codex Project Brief: Local Real-time Subtitle + Translation Tool

## 1. Project Background

This project is based on a forked GitHub repository:

```text
https://github.com/Birdsplan/realtime-subtitle.git
```

Local project path:

```text
D:\code\realtime-subtitle
```

The goal is to develop a **local real-time subtitle and translation desktop tool**.

The intended workflow is:

```text
Audio input
  ↓
Local speech recognition / ASR
  ↓
Text stabilization / segmentation
  ↓
DeepSeek API translation
  ↓
Floating bilingual subtitle window
  ↓
Transcript logging
```

The user is new to software project development, so all changes must be **small, traceable, and easy to verify**.

Do not rush into large refactoring.

---

## 2. Overall Development Goal

The MVP should support:

1. Capture microphone audio.
2. Capture Windows system audio if feasible.
3. Transcribe speech locally.
4. Translate stable subtitle segments using DeepSeek API.
5. Display original text and translated text in a floating always-on-top subtitle window.
6. Save transcript and translation logs.

The first usable version should prioritize **stability and clarity**, not perfect real-time simultaneous interpretation.

---

## 3. Non-goals for the MVP

Do not implement these features in the early stage unless explicitly requested:

- Speaker diarization.
- Speech synthesis / TTS.
- Perfect SRT alignment.
- Multi-user server mode.
- Cloud ASR.
- Complex account system.
- Complex plugin architecture.
- Full UI redesign.
- Large-scale rewrite of the whole repository.

---

## 4. Development Principles

Please follow these rules strictly:

1. **Do not rewrite the whole project unless explicitly requested.**
2. Before modifying code, explain the current module structure and data flow.
3. Each change must be small and testable.
4. Keep the following modules separated:
   - audio capture
   - ASR / speech recognition
   - translation
   - text stabilization / segmentation
   - UI / floating subtitle window
   - transcript storage
5. Do not hard-code API keys.
6. Use environment variables or config files for API keys and endpoints.
7. Do not block the UI thread with ASR or translation requests.
8. Add or update a small test script for every new functional module.
9. After each change, summarize:
   - files changed
   - reason for change
   - how to test
   - known limitations
10. Avoid changing formatting-only files unless necessary.
11. Avoid introducing heavy dependencies without explaining why they are needed.
12. If there are multiple possible implementations, propose the options first and recommend the lowest-risk one.

---

## 5. First Task: Understand the Existing Project

Before modifying functional code, please inspect the repository and create an architecture note.

Required output:

```text
ARCHITECTURE.md
```

This file should describe:

1. Project startup entry.
2. Main configuration files.
3. Audio capture module.
4. ASR / speech recognition module.
5. Translation module.
6. Floating subtitle UI module.
7. Data flow from audio input to subtitle display.
8. Threading / async design, if any.
9. Current dependencies.
10. Potential insertion point for DeepSeek translation.

Important restriction:

> For this first task, do not modify functional code. Only create or update `ARCHITECTURE.md`.

---

## 6. Translation Requirement

The user has purchased DeepSeek API and intends to use it for translation.

The translation module should eventually be implemented behind a clean interface, for example:

```python
class Translator:
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        ...
```

Recommended behavior:

1. Translate only stable subtitle segments, not every partial ASR update.
2. Use a short context window if necessary, but avoid sending the whole transcript repeatedly.
3. Cache repeated source text to reduce duplicate API calls.
4. If the API fails, the program should not crash.
5. If translation fails, show the original subtitle and log the error.
6. The API key should be read from an environment variable or config file, not hard-coded.

Suggested environment variable name:

```text
DEEPSEEK_API_KEY
```

Possible configuration fields:

```yaml
translation:
  provider: deepseek
  api_key_env: DEEPSEEK_API_KEY
  base_url: https://api.deepseek.com
  model: <check-current-deepseek-docs-before-finalizing>
  target_language: zh-CN
```

Before final implementation, verify the latest DeepSeek API model names and request format from official documentation.

Suggested translation prompt:

```text
You are a real-time subtitle translation engine.
Translate the following speech transcript into concise, natural Chinese.
Do not explain.
Do not add information.
Preserve technical terms, names, numbers, and acronyms.
Return only the translation.
```

---

## 7. Audio Capture Requirement

The tool should eventually support two input modes:

1. Microphone input.
2. Windows system audio input.

For Windows system audio, investigate WASAPI loopback support.

Development rule:

> Build and test audio capture independently before connecting it to ASR.

A useful test script would be:

```text
tests/test_audio_capture.py
```

Expected test behavior:

1. List available audio input devices.
2. Identify possible loopback/system-audio devices if available.
3. Record 10 seconds of audio.
4. Save it as a WAV file.
5. Print sample rate, channel count, and output path.

---

## 8. ASR Requirement

The ASR module should remain replaceable.

Possible ASR backends:

- faster-whisper
- FunASR / SenseVoice
- existing repository backend

For the MVP, use the existing repository ASR backend first unless there is a strong reason to replace it.

Do not connect ASR to very small raw audio chunks without stabilization. Prefer this basic strategy:

```text
audio frames
  ↓
VAD / silence detection
  ↓
accumulate speech segment
  ↓
ASR
  ↓
text stabilization / deduplication
  ↓
translation
```

---

## 9. Subtitle Display Requirement

The UI should eventually display:

```text
Original subtitle
Translated subtitle
```

Recommended behavior:

1. The original text may update faster.
2. The translated text should update only after the source text is stable.
3. Show only recent subtitle lines in the floating window.
4. Save the full transcript to logs.
5. The subtitle window should remain non-blocking and responsive.

---

## 10. Logging Requirement

The program should save useful runtime logs.

Suggested log types:

1. ASR raw output.
2. Stable source segments.
3. Translation output.
4. API errors.
5. Audio device selection.
6. Runtime exceptions.

Do not expose API keys in logs.

---

## 11. Git Repository Situation

Git is installed locally.

Verified command:

```powershell
git --version
```

Output:

```text
git version 2.54.0.windows.1
```

The repository was cloned successfully using a temporary Git proxy command:

```powershell
cd D:\code

git -c http.proxy=http://127.0.0.1:7897 `
    -c https.proxy=http://127.0.0.1:7897 `
    clone --depth 1 https://github.com/Birdsplan/realtime-subtitle.git
```

The proxy software is Clash Verge.

Clash Verge port shown in settings:

```text
7897
```

Important:

- The previous clone used a one-time proxy setting.
- It did not permanently configure Git global proxy.
- Future `git pull` or `git push` operations may fail if GitHub access is unstable.
- If network errors occur, use the temporary proxy form again.

Example:

```powershell
git -c http.proxy=http://127.0.0.1:7897 `
    -c https.proxy=http://127.0.0.1:7897 `
    pull
```

or:

```powershell
git -c http.proxy=http://127.0.0.1:7897 `
    -c https.proxy=http://127.0.0.1:7897 `
    push
```

If a permanent Git proxy is needed, use:

```powershell
git config --global http.proxy http://127.0.0.1:7897
git config --global https.proxy http://127.0.0.1:7897
```

To remove permanent Git proxy:

```powershell
git config --global --unset http.proxy
git config --global --unset https.proxy
```

To check current Git proxy settings:

```powershell
git config --global --get http.proxy
git config --global --get https.proxy
```

If no output is shown, no global Git proxy is configured.

---

## 12. Suggested Git Workflow

Recommended development branch:

```powershell
git checkout -b deepseek-mvp
```

Before making changes, check status:

```powershell
git status
```

After each logical change:

```powershell
git status
git diff
```

Do not create huge commits containing unrelated changes.

Suggested commit style:

```text
docs: add architecture note
feat: add DeepSeek translator wrapper
test: add audio capture test script
fix: handle translation API timeout
```

---

## 13. Immediate Next Steps

Please proceed in this order:

1. Inspect the repository structure.
2. Identify startup entry and main modules.
3. Create `ARCHITECTURE.md`.
4. Do not modify functional code yet.
5. Report:
   - what files were inspected
   - what the current data flow is
   - where translation can be replaced by DeepSeek
   - what uncertainties remain

Only after the user confirms the architecture understanding should functional development begin.

---

## 14. Communication Style for This Project

The user needs clear project management support.

When reporting progress, please use this format:

```text
## What I checked

## What I found

## Files changed

## How to test

## Risks / limitations

## Suggested next step
```

Avoid vague summaries such as "I improved the project." Be specific and verifiable.
