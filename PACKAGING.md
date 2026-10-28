# Sharing and Packaging Notes

## Local launchers

- `run_dashboard.bat`: starts the app with a terminal window. Use this when debugging ASR, audio, translation, or CUDA logs.
- `run_dashboard_silent.vbs`: starts the app without a terminal window. Use this for daily viewing after the project is configured.

## Recommended way to share during MVP

For now, share the project as a source folder instead of a single `.exe`.

Why:

- The app depends on local audio devices, GPU/CUDA support, and a user-specific DeepSeek API key.
- Whisper models are cached in the user's Hugging Face cache, not inside the project folder.
- A one-file exe would be large and harder to debug at this stage.

Suggested steps for a friend:

1. Install Python 3.12 or use Anaconda.
2. Clone or unzip this project.
3. Run `install_windows.bat` or let Codex create `.venv` and install dependencies.
4. Set their own `DEEPSEEK_API_KEY`.
5. Start with `run_dashboard.bat` first to confirm logs are healthy.
6. Use `run_dashboard_silent.vbs` after everything works.

Do not share your own API key.

## Model and CUDA notes

- `base.en` and `small.en` are downloaded the first time they are used.
- NVIDIA GPU users should use:

```ini
device = cuda
compute_type = float16
```

- Non-NVIDIA users should fall back to:

```ini
device = cpu
compute_type = int8
```

## Future one-click packaging

When the app behavior is stable, use PyInstaller or Nuitka to build a Windows desktop package.

Expected challenges:

- PyQt6 packaging size.
- faster-whisper / CTranslate2 native DLLs.
- CUDA runtime compatibility.
- Whisper model download/cache behavior.
- User-specific API key setup.

Recommended future release shape:

- `RealtimeSubtitle.exe`
- `config.ini`
- `README_FIRST_RUN.md`
- No bundled API key.
- Optional first-run model download step.
