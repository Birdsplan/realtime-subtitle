import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
import signal
import threading
import queue
import time
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from audio_capture import AudioCapture
from transcriber import Transcriber
from translator import Translator
from overlay_window import OverlayWindow
from config import config
from transcript_logger import TranscriptLogger
from text_stabilizer import remove_repeated_prefix
from speech_segmenter import get_segment_cut_reason

class WorkerSignals(QObject):
    update_text = pyqtSignal(int, str, str)  # (chunk_id, original, translated)
    status = pyqtSignal(str, str)  # (level, message)

class Pipeline(QObject):
    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()
        self.running = True
        self.transcript_logger = TranscriptLogger()
        
        # Print config for debugging
        config.print_config()
        
        # Initialize components
        self.audio = AudioCapture(
            input_mode=config.audio_input_mode,
            device_index=config.device_index,
            loopback_index=config.loopback_index,
            sample_rate=config.sample_rate,
            silence_threshold=config.silence_threshold,
            silence_duration=config.silence_duration,
            chunk_duration=config.chunk_duration,
            max_phrase_duration=config.max_phrase_duration,
            streaming_mode=config.streaming_mode,
            streaming_interval=config.streaming_interval,
            streaming_step_size=config.streaming_step_size,
            streaming_overlap=config.streaming_overlap,
            capture_buffer_seconds=config.capture_buffer_seconds,
        )
        
        # Initialize Transcriber
        print(f"[Pipeline] Initializing Transcriber with backend={config.asr_backend}, device={config.whisper_device}...")
        
        # Determine model size based on backend
        if config.asr_backend == "funasr":
            model_size = config.funasr_model
        else:
            model_size = config.whisper_model
            
        self.transcriber = Transcriber(
            backend=config.asr_backend,
            model_size=model_size,
            device=config.whisper_device,
            compute_type=config.whisper_compute_type,
            language=config.source_language
        )
        
        # Initialize Translator
        print(f"[Pipeline] Initializing Translator (target={config.target_lang})...")
        self.translator = Translator(
            target_lang=config.target_lang,
            base_url=config.api_base_url,
            api_key=config.api_key,
            model=config.model,
            provider=config.translation_provider,
            api_key_env=config.api_key_env,
            disable_thinking=config.translation_disable_thinking
        )
        
        # Warmup Transcriber (Critical for MLX/GPU)
        self.transcriber.warmup()
        self.signals.status.emit("ready", "Pipeline ready")

    def start(self):
        """Start the processing pipeline in a dedicated thread"""
        # self.audio.start() # DISABLE: Generator manages its own stream. calling this causes double-stream error on macOS
        self.thread = threading.Thread(target=self.processing_loop)
        self.thread.daemon = True
        self.thread.start()
        self.signals.status.emit("running", "Listening")

    def stop(self):
        print("\n[Pipeline] Stopping...")
        self.signals.status.emit("stopping", "Stopping")
        self.running = False
        self.audio.stop()
        if self.thread.is_alive():
            self.thread.join(timeout=2)
        print("[Pipeline] Stopped.")
        self.signals.status.emit("stopped", "Stopped")

    def processing_loop(self):
        """Fully parallel pipeline: multiple concurrent transcription + translation"""
        print("Pipeline processing loop started (FULLY PARALLEL mode).")
        self.signals.status.emit("running", "Capturing audio")
        
        # Create multiple transcribers for concurrent processing
        # CHECK: If using MLX, force 1 worker (MLX is not thread-safe for parallel inference in this way)
        is_mlx = (config.asr_backend == "mlx")
        
        if is_mlx:
            print("[Pipeline] MLX backend detected - forcing single worker (MLX uses GPU parallelism internaly)")
            num_transcription_workers = 1
        else:
            num_transcription_workers = config.transcription_workers
            
        print(f"[Pipeline] Using {num_transcription_workers} transcription workers...")
        
        # Determine model size based on backend
        if config.asr_backend == "funasr":
            model_size = config.funasr_model
        else:
            model_size = config.whisper_model
        
        transcribers = [self.transcriber]  # Reuse existing one
        for i in range(num_transcription_workers - 1):
            t = Transcriber(
                backend=config.asr_backend,
                model_size=model_size,
                device=config.whisper_device,
                compute_type=config.whisper_compute_type,
                language=config.source_language
            )
            transcribers.append(t)
        """Accumulating Buffer Processing Loop (Word-by-Word Streaming)"""
        print("[Pipeline] processing loop started (Accumulating Mode).")
        
        import numpy as np
        
        # Executors
        transcribe_executor = ThreadPoolExecutor(max_workers=1) # Serial transcription
        translate_executor = ThreadPoolExecutor(max_workers=config.translation_threads)
        
        # State
        buffer = np.array([], dtype=np.float32)
        chunk_id = 1
        last_update_time = time.time()
        phrase_start_time = time.time()
        active_transcription_future = None
        last_skipped_partial_log = 0.0
        
        # Generator yielding small chunks (e.g. 0.2s)
        audio_gen = self.audio.generator()
        
        # Context Management
        self.last_final_text = ""

        try:
            for audio_chunk in audio_gen:
                if not self.running:
                    break
                buffer = np.concatenate([buffer, audio_chunk])
                now = time.time()
                buffer_duration = len(buffer) / self.audio.sample_rate
                
                cut_reason = get_segment_cut_reason(
                    buffer,
                    self.audio.sample_rate,
                    self.audio.silence_threshold,
                    config.silence_duration,
                    self.audio.max_phrase_duration,
                )
                should_finalize = cut_reason is not None
                
                if should_finalize and buffer_duration > 0.5:
                    # FINALIZE
                    final_buffer = buffer.copy()
                    cid = chunk_id
                    
                    # Store current prompt to pass to task (thread safety)
                    prompt = self.last_final_text
                    
                    # PRE-CHECK: Is the entire buffer actually silence?
                    # (Prevent infinite loop of repeating prompt on empty audio)
                    overall_rms = np.sqrt(np.mean(final_buffer**2))
                    keep_overlap = False
                    if overall_rms < self.audio.silence_threshold:
                         print(f"[Pipeline] Skipped silent chunk {cid} (RMS={overall_rms:.4f})")
                         self.signals.status.emit("running", "Waiting for speech")
                    else:
                        keep_overlap = config.final_overlap_duration > 0
                        print(
                            f"[Pipeline] Finalizing chunk {cid} "
                            f"(reason={cut_reason}, duration={buffer_duration:.1f}s)"
                        )
                        # Submit Final Task
                        # Pass prompt AND translate_executor for async translation
                        self.signals.status.emit("transcribing", "Finalizing speech")
                        active_transcription_future = transcribe_executor.submit(
                            self._process_final_chunk,
                            final_buffer,
                            cid,
                            prompt,
                            translate_executor,
                        )
                    
                    # Reset
                    overlap_samples = int(self.audio.sample_rate * config.final_overlap_duration)
                    if keep_overlap and overlap_samples > 0 and len(final_buffer) > overlap_samples:
                        buffer = final_buffer[-overlap_samples:].copy()
                    else:
                        buffer = np.array([], dtype=np.float32)
                    chunk_id += 1
                    phrase_start_time = now
                    last_update_time = now
                    
                # 2. Partial Update if: Interval passed AND not finalizing
                elif now - last_update_time > config.update_interval and buffer_duration > 0.5:
                    # PARTIAL UPDATE
                    partial_buffer = buffer.copy()
                    prompt = self.last_final_text
                    transcription_busy = (
                        active_transcription_future is not None
                        and not active_transcription_future.done()
                    )
                    
                    # RMS Check to avoid partial hallucination on silence
                    rms = np.sqrt(np.mean(partial_buffer**2))
                    if not config.partial_transcription:
                        pass
                    elif transcription_busy:
                        if now - last_skipped_partial_log > 3.0:
                            print("[Pipeline] Skipping partial ASR while previous transcription is still running")
                            self.signals.status.emit("transcribing", "ASR busy; waiting for final segment")
                            last_skipped_partial_log = now
                    elif buffer_duration > config.max_partial_duration:
                        pass
                    elif rms > self.audio.silence_threshold:
                        self.signals.status.emit("transcribing", "Recognizing speech")
                        active_transcription_future = transcribe_executor.submit(
                            self._process_partial_chunk,
                            partial_buffer,
                            chunk_id,
                            prompt,
                        )
                    
                    last_update_time = now
                    
        except Exception as e:
            print(f"[Pipeline] Error in loop: {e}")
            self.signals.status.emit("error", f"Pipeline error: {e}")
        finally:
            transcribe_executor.shutdown(wait=False)
            translate_executor.shutdown(wait=False)

    def _process_partial_chunk(self, audio_data, chunk_id, prompt=""):
        """Transcribe and update UI (No translation)"""
        try:
            # Use accumulated context as prompt
            text = self.transcriber.transcribe(audio_data, prompt=prompt)
            if text:
                self.signals.update_text.emit(chunk_id, text, "")
        except Exception as e:
            print(f"[Partial {chunk_id}] Error: {e}")

    def _process_final_chunk(self, audio_data, chunk_id, prompt="", translate_executor=None):
        """Transcribe, Log, and Trigger Translation Async"""
        try:
            text = self.transcriber.transcribe(audio_data, prompt=prompt)
            if text:
                deduped_text = remove_repeated_prefix(text, self.last_final_text)
                if deduped_text != text:
                    print(f"[Final {chunk_id}] Removed overlapped prefix: {text} -> {deduped_text}")
                    text = deduped_text
                if not text:
                    print(f"[Final {chunk_id}] Skipped duplicate overlap")
                    return

                print(f"[Final {chunk_id}] Transcribed: {text}")
                self.transcript_logger.record(chunk_id, original=text, status="transcribed")
                self.signals.status.emit("translating", "Translating")
                # Save for context (only if meaningful)
                if len(text.split()) > 2:
                    self.last_final_text = text
                
                # Show stable source text immediately; translation arrives separately.
                self.signals.update_text.emit(chunk_id, text, "")
                
                # Offload translation to separate thread so we don't block next transcription
                if translate_executor:
                    translate_executor.submit(self._run_translation, text, chunk_id)
            else:
                pass
        except Exception as e:
            print(f"[Final {chunk_id}] Error: {e}")

    def _run_translation(self, text, chunk_id):
        """Run translation in background and emit result"""
        try:
            translated = self.translator.translate(text)
            print(f"[Final {chunk_id}] Translated: {translated}")
            self.transcript_logger.record(
                chunk_id,
                original=text,
                translated=translated,
                status="translated",
            )
            self.signals.status.emit("running", "Listening")
            self.signals.update_text.emit(chunk_id, text, translated)
        except Exception as e:
            print(f"[Translation {chunk_id}] Failed: {e}")
            self.transcript_logger.record(
                chunk_id,
                original=text,
                translated="",
                status="translation_failed",
                error=e,
            )
            self.signals.status.emit("error", f"Translation failed: {e}")
            self.signals.update_text.emit(chunk_id, text, "[Translation Failed]")
    
    def _transcribe_chunk(self, transcriber, audio_chunk, chunk_id):
        """Transcribe a single chunk and log timing"""
        t0 = time.time()
        text = transcriber.transcribe(audio_chunk)
        t1 = time.time()
        print(f"[Chunk {chunk_id}] Transcribed in {t1-t0:.2f}s: {text if text else '(empty)'}")
        return text
    
    def _translate_and_log(self, text, chunk_id=0):
        """Translate text and log result"""
        t0 = time.time()
        translated_text = self.translator.translate(text)
        t1 = time.time()
        print(f"[Chunk {chunk_id}] Translated in {t1-t0:.2f}s: {translated_text}")
        return (text, translated_text)

# Global reference for signal handler
_pipeline = None
_app = None

def signal_handler(sig, frame):
    """Handle Ctrl-C gracefully"""
    print("\n[Main] Ctrl-C received, force killing...")
    os._exit(0)

def start_overlay_session():
    """Start the overlay and pipeline without blocking (for use in Dashboard)"""
    global _pipeline, _app
    
    # Initialize Overlay Window
    window = OverlayWindow(
        display_duration=config.display_duration,
        window_width=config.window_width,
        window_height=config.window_height,
        max_visible_items=config.max_visible_items,
        bottom_margin=config.overlay_bottom_margin,
        position=config.overlay_position,
        original_font_size=config.original_font_size,
        translation_font_size=config.translation_font_size,
        panel_opacity=config.panel_opacity,
        auto_hide_controls=config.auto_hide_controls,
    )
    window.show()
    
    # Logic
    _pipeline = Pipeline()
    
    # Connect signals
    _pipeline.signals.update_text.connect(window.update_text)
    
    # Start pipeline
    _pipeline.start()
    
    return window, _pipeline

def main():
    global _pipeline, _app
    
    # Set up signal handler for Ctrl-C
    signal.signal(signal.SIGINT, signal_handler)
    
    _app = QApplication.instance()
    if not _app:
        _app = QApplication(sys.argv)
    
    # Start session
    win, pipe = start_overlay_session()
    
    # Timer to let Python interpreter handle signals (Ctrl-C)
    timer = QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)
    
    try:
        sys.exit(_app.exec())
    except SystemExit:
        pass
    finally:
        if _pipeline:
            _pipeline.stop()

if __name__ == "__main__":
    main()
