import sounddevice as sd
import numpy as np
import queue
import threading
import time
from collections import deque


class AudioBufferClosed(Exception):
    pass


class AudioChunkBuffer:
    """Thread-safe bounded ring buffer that drops the oldest chunk on overflow."""

    def __init__(self, max_chunks):
        if max_chunks < 1:
            raise ValueError("max_chunks must be at least 1")
        self.max_chunks = max_chunks
        self._chunks = deque()
        self._condition = threading.Condition()
        self._closed = False
        self.pushed_chunks = 0
        self.popped_chunks = 0
        self.dropped_chunks = 0
        self.high_watermark = 0

    def put(self, chunk):
        with self._condition:
            if self._closed:
                return False
            dropped = False
            if len(self._chunks) >= self.max_chunks:
                self._chunks.popleft()
                self.dropped_chunks += 1
                dropped = True
            self._chunks.append(chunk)
            self.pushed_chunks += 1
            self.high_watermark = max(self.high_watermark, len(self._chunks))
            self._condition.notify()
            return dropped

    def get(self, timeout=None):
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            while not self._chunks:
                if self._closed:
                    raise AudioBufferClosed
                if deadline is None:
                    self._condition.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise queue.Empty
                self._condition.wait(remaining)

            self.popped_chunks += 1
            return self._chunks.popleft()

    def close(self):
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def stats(self):
        with self._condition:
            return {
                "capacity": self.max_chunks,
                "queued": len(self._chunks),
                "pushed": self.pushed_chunks,
                "popped": self.popped_chunks,
                "dropped": self.dropped_chunks,
                "high_watermark": self.high_watermark,
                "closed": self._closed,
            }

class AudioCapture:
    def __init__(self, device_index=None, sample_rate=16000, chunk_duration=0.1, 
                 silence_threshold=0.01, silence_duration=1.0, max_phrase_duration=5.0,
                 streaming_mode=False, streaming_interval=1.5, streaming_step_size=0.2, streaming_overlap=0.3,
                 input_mode="microphone", loopback_index=None, capture_buffer_seconds=8.0):
        """
        Captures audio and yields segments containing speech.
        
        Args:
            input_mode: "microphone" for sounddevice input, or "system" for system-audio loopback.
            device_index: Index of input device (None for default).
            loopback_index: Index from soundcard loopback device list, or None for default speaker.
            sample_rate: Audio sample rate (default 16000 for Whisper).
            chunk_duration: Duration of each small read in seconds.
            silence_threshold: RMS amplitude threshold for "silence".
            silence_duration: How many seconds of silence triggers a segment cut.
            max_phrase_duration: Force processing after this many seconds even without silence.
            streaming_mode: If True, emit audio at fixed intervals (no VAD).
            streaming_interval: Seconds between audio emissions in streaming mode.
            streaming_overlap: Seconds of overlap between chunks in streaming mode.
            capture_buffer_seconds: Maximum raw audio buffered between capture and processing.
        """
        self.input_mode = (input_mode or "microphone").lower()
        self.device_index = device_index
        self.loopback_index = loopback_index
        self.sample_rate = sample_rate
        self.block_size = int(sample_rate * chunk_duration)
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.max_phrase_duration = max_phrase_duration
        
        # Streaming mode settings
        self.streaming_mode = streaming_mode
        self.streaming_interval = streaming_interval
        self.streaming_step_size = streaming_step_size
        self.streaming_overlap = streaming_overlap
        self.capture_buffer_seconds = max(streaming_step_size, capture_buffer_seconds)
        
        self.audio_queue = queue.Queue()
        self.running = False
        self.thread = None
        self.capture_thread = None
        self.capture_buffer = None
        self.capture_error = None
        self._last_buffer_warning = 0.0
        self._capture_stats_logged = False

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._record_loop, daemon=True)
        self.thread.start()
        
        # Log audio device info
        print("[AudioCapture] Starting...")
        print(f"  Input Mode: {self.input_mode}")
        print(f"  Sample Rate: {self.sample_rate} Hz")
        print(f"  Silence Threshold: {self.silence_threshold}")
        print(f"  Silence Duration: {self.silence_duration}s")
        
        # Get device info
        if self.device_index is None:
            default_device = sd.query_devices(kind='input')
            print(f"  Using DEFAULT input device:")
            print(f"    Name: {default_device['name']}")
            print(f"    Index: {default_device['index']}")
            print(f"    Channels: {default_device['max_input_channels']}")
        else:
            device_info = sd.query_devices(self.device_index)
            print(f"  Using device index {self.device_index}:")
            print(f"    Name: {device_info['name']}")
            print(f"    Channels: {device_info['max_input_channels']}")
        
        print("\n[AudioCapture] Available input devices:")
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if d['max_input_channels'] > 0:
                marker = " <-- SELECTED" if (self.device_index == i or (self.device_index is None and d == sd.query_devices(kind='input'))) else ""
                print(f"    [{i}] {d['name']} ({d['max_input_channels']} ch){marker}")

    def stop(self):
        self.running = False
        if self.capture_buffer:
            self.capture_buffer.close()
        if self.capture_thread and self.capture_thread is not threading.current_thread():
            self.capture_thread.join(timeout=2)
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)
        self._log_capture_stats()
        print("Audio capture stopped.")

    def generator(self):
        """Yield raw chunks while a dedicated worker continuously reads the audio device."""
        if self.capture_thread and self.capture_thread.is_alive():
            raise RuntimeError("Audio capture generator is already running")

        step_size = max(0.01, self.streaming_step_size)
        capacity = max(2, int(np.ceil(self.capture_buffer_seconds / step_size)))
        self.capture_buffer = AudioChunkBuffer(capacity)
        self.capture_error = None
        self._capture_stats_logged = False
        self.running = True
        self.capture_thread = threading.Thread(
            target=self._capture_worker,
            name="audio-capture-worker",
            daemon=True,
        )
        self.capture_thread.start()
        print(
            f"[Audio] Capture worker started "
            f"(buffer={self.capture_buffer_seconds:.1f}s, capacity={capacity} chunks)"
        )

        try:
            while True:
                try:
                    yield self.capture_buffer.get(timeout=0.5)
                except queue.Empty:
                    if not self.capture_thread.is_alive():
                        break
                except AudioBufferClosed:
                    break
        finally:
            self.running = False
            self.capture_buffer.close()
            if self.capture_thread is not threading.current_thread():
                self.capture_thread.join(timeout=2)
            self._log_capture_stats()

        if self.capture_error:
            raise RuntimeError(f"Audio capture worker failed: {self.capture_error}") from self.capture_error

    def _capture_worker(self):
        source = (
            self._system_loopback_generator
            if self.input_mode in ("system", "system_audio", "loopback")
            else self._microphone_generator
        )
        try:
            for chunk in source():
                if not self.running:
                    break
                dropped = self.capture_buffer.put(chunk)
                if dropped and time.monotonic() - self._last_buffer_warning > 3.0:
                    stats = self.capture_buffer.stats()
                    print(
                        "[Audio] Capture buffer overflow; dropped oldest chunk "
                        f"(dropped={stats['dropped']}, queued={stats['queued']}/{stats['capacity']})"
                    )
                    self._last_buffer_warning = time.monotonic()
        except Exception as e:
            self.capture_error = e
            print(f"[Audio] Capture worker error: {e}")
        finally:
            self.capture_buffer.close()

    def _log_capture_stats(self):
        if not self.capture_buffer or self._capture_stats_logged:
            return
        stats = self.capture_buffer.stats()
        print(
            "[Audio] Capture buffer stats: "
            f"pushed={stats['pushed']}, popped={stats['popped']}, "
            f"dropped={stats['dropped']}, high_watermark={stats['high_watermark']}/{stats['capacity']}"
        )
        self._capture_stats_logged = True

    def _microphone_generator(self):
        """Yield mono microphone chunks from sounddevice."""
        if self.device_index is None:
             # Just safety check, usually handled in start()
             pass
             
        # Use configured step size
        block_size = int(self.sample_rate * self.streaming_step_size)
        print(f"[Audio] Starting raw processing stream (step={self.streaming_step_size}s)")
        
        try:
            with sd.InputStream(device=self.device_index, channels=1, samplerate=self.sample_rate, 
                                blocksize=block_size, dtype='float32') as stream:
                 self.running = True
                 while self.running:
                     data, overflow = stream.read(block_size)
                     if overflow:
                         print("Audio overflow")
                     yield data.flatten()
        except Exception as e:
            print(f"\n[ERROR] Audio Device Initialization Failed: {e}")
            print("Possible causes:")
            print("1. Terminal/App does not have Microphone Permissions (System Settings > Privacy > Microphone)")
            print(f"2. Sample rate {self.sample_rate}Hz not supported by device (Try 44100 or 48000)")
            print("3. Invalid device index in config.ini (Try 'auto' or check 'python audio_capture.py')")
            self.running = False
            # Yield silence to prevent immediate crash if running in loop
            yield np.zeros(block_size, dtype=np.float32)
            
        print("[Audio] Generator stopped.")

    def _system_loopback_generator(self):
        """Yield mono system-audio chunks from the default speaker loopback."""
        block_size = int(self.sample_rate * self.streaming_step_size)
        print(f"[Audio] Starting system loopback stream (step={self.streaming_step_size}s)")

        try:
            import soundcard as sc
            import warnings

            try:
                from soundcard.mediafoundation import SoundcardRuntimeWarning
                warnings.filterwarnings(
                    "once",
                    message="data discontinuity in recording",
                    category=SoundcardRuntimeWarning,
                )
            except Exception:
                warnings.filterwarnings("once", message="data discontinuity in recording")

            loopbacks = [
                device for device in sc.all_microphones(include_loopback=True)
                if getattr(device, "isloopback", False)
            ]
            if not loopbacks:
                raise RuntimeError("No system-audio loopback devices found")

            loopback = self._select_loopback_device(sc, loopbacks)
            print(f"[Audio] Using system loopback: {loopback}")
            print(f"[Audio] Sample Rate: {self.sample_rate} Hz")

            with loopback.recorder(samplerate=self.sample_rate) as recorder:
                self.running = True
                while self.running:
                    data = recorder.record(numframes=block_size)
                    if data is None or data.size == 0:
                        yield np.zeros(block_size, dtype=np.float32)
                        continue

                    if data.ndim > 1:
                        data = data.mean(axis=1)

                    yield data.astype(np.float32, copy=False)

        except Exception as e:
            print(f"\n[ERROR] System Audio Loopback Initialization Failed: {e}")
            print("Possible causes:")
            print("1. No active Windows speaker output device is available")
            print("2. The selected loopback index is invalid")
            print("3. The 'soundcard' package is missing or cannot access WASAPI loopback")
            self.running = False
            yield np.zeros(block_size, dtype=np.float32)

        print("[Audio] System loopback generator stopped.")

    def _select_loopback_device(self, sc, loopbacks):
        if self.loopback_index is not None:
            if 0 <= self.loopback_index < len(loopbacks):
                return loopbacks[self.loopback_index]
            raise RuntimeError(
                f"Invalid loopback_index={self.loopback_index}; available range is 0-{len(loopbacks) - 1}"
            )

        default_speaker = sc.default_speaker()
        for loopback in loopbacks:
            if loopback.name == default_speaker.name:
                return loopback

        return loopbacks[0]

    def get_audio_stream(self):
        """Generator that yields numpy arrays of float32 audio containing speech."""
        while self.running:
            try:
                # Get a segment from the queue
                audio_segment = self.audio_queue.get(timeout=1)
                yield audio_segment
            except queue.Empty:
                continue

    def _record_loop(self):
        if self.streaming_mode:
            self._streaming_record_loop()
        else:
            self._vad_record_loop()
    
    def _streaming_record_loop(self):
        """Continuous streaming: emit audio every streaming_interval seconds with overlap"""
        print(f"[Audio] Streaming mode: interval={self.streaming_interval}s, overlap={self.streaming_overlap}s")
        
        interval_samples = int(self.sample_rate * self.streaming_interval)
        overlap_samples = int(self.sample_rate * self.streaming_overlap)
        
        # Ring buffer to hold audio with overlap
        buffer = np.array([], dtype=np.float32)
        
        with sd.InputStream(device=self.device_index, channels=1, samplerate=self.sample_rate,
                            blocksize=self.block_size, dtype='float32') as stream:
            
            last_emit_time = time.time()
            
            while self.running:
                audio_chunk, _ = stream.read(self.block_size)
                audio_chunk = audio_chunk.flatten()
                buffer = np.concatenate([buffer, audio_chunk])
                
                # Check if it's time to emit
                if time.time() - last_emit_time >= self.streaming_interval:
                    if len(buffer) > 0:
                        # Check if there's any audio (not pure silence)
                        rms = np.sqrt(np.mean(buffer**2))
                        if rms > self.silence_threshold * 0.5:  # Lower threshold for streaming
                            duration = len(buffer) / self.sample_rate
                            print(f"[Audio] Streaming emit: {duration:.2f}s, RMS={rms:.4f}")
                            self.audio_queue.put(buffer.copy())
                        
                        # Keep overlap for context, discard the rest
                        if len(buffer) > overlap_samples:
                            buffer = buffer[-overlap_samples:]
                        
                    last_emit_time = time.time()
    
    def _vad_record_loop(self):
        """VAD-based recording: wait for speech and silence"""
        # Buffer to hold current speech phrase
        current_phrase = []
        silence_start_time = None
        has_speech = False
        
        def callback(indata, frames, time_info, status):
            if status:
                print(status)
            if not self.running:
                raise sd.CallbackAbort
            
            # Make a copy of data
            audio_chunk = indata.copy().flatten()
            
            # Simple VAD: Check RMS (Root Mean Square) amplitude
            rms = np.sqrt(np.mean(audio_chunk**2))
            
            # Communicate via non-local variables (or just process here)
            # Since callback is in a separate thread managed by sounddevice, 
            # we need to be careful. However, pure python processing in callback 
            # might block if too slow. 
            # Better strategy: push raw chunks to a processing queue, 
            # but for simplicity, let's use a shared list with lock or just a queue for raw chunks.
            pass

        # To avoid complexity with callbacks, let's use a blocking read in this thread
        # sounddevice.InputStream logic
        
        with sd.InputStream(device=self.device_index, channels=1, samplerate=self.sample_rate, 
                            blocksize=self.block_size, callback=None, dtype='float32') as stream:
            
            debug_counter = 0
            max_rms_seen = 0
            phrase_start_time = None  # Track when current phrase started
            
            while self.running:
                audio_chunk, overflow = stream.read(self.block_size)
                audio_chunk = audio_chunk.flatten()
                
                rms = np.sqrt(np.mean(audio_chunk**2))
                max_rms_seen = max(max_rms_seen, rms)
                
                # Debug logging every 2 seconds
                debug_counter += 1
                if debug_counter % 20 == 0:
                    status = "SPEECH" if has_speech else "silent"
                    phrase_dur = time.time() - phrase_start_time if phrase_start_time else 0
                    print(f"[Audio] RMS: {rms:.4f} | Max: {max_rms_seen:.4f} | Threshold: {self.silence_threshold} | {status} | Phrase: {phrase_dur:.1f}s")
                
                # Always collect audio if above threshold
                if rms > self.silence_threshold:
                    if not has_speech:
                        has_speech = True
                        phrase_start_time = time.time()
                        print(f"[Audio] Speech detected! RMS={rms:.4f}")
                    current_phrase.append(audio_chunk)
                    silence_start_time = None
                else:
                    if has_speech:
                        current_phrase.append(audio_chunk)
                        
                        if silence_start_time is None:
                            silence_start_time = time.time()
                        elif time.time() - silence_start_time > self.silence_duration:
                            # Silence long enough, cut phrase
                            self._emit_phrase(current_phrase, "silence")
                            current_phrase = []
                            has_speech = False
                            silence_start_time = None
                            phrase_start_time = None
                
                # Force cut if phrase is too long (real-time requirement)
                if has_speech and phrase_start_time:
                    phrase_duration = time.time() - phrase_start_time
                    if phrase_duration >= self.max_phrase_duration:
                        self._emit_phrase(current_phrase, "max_time")
                        current_phrase = []
                        has_speech = False
                        silence_start_time = None
                        phrase_start_time = None
    
    def _emit_phrase(self, phrase_chunks, reason):
        """Helper to emit a complete phrase"""
        if not phrase_chunks:
            return
        full_phrase = np.concatenate(phrase_chunks)
        duration = len(full_phrase) / self.sample_rate
        print(f"[Audio] Phrase complete ({reason}): {duration:.2f}s")
        self.audio_queue.put(full_phrase)

if __name__ == "__main__":
    # Test
    print("Available devices:")
    print(sd.query_devices())
    
    cap = AudioCapture()
    cap.start()
    try:
        for i, segment in enumerate(cap.get_audio_stream()):
            print(f"Got audio segment {i}: length {len(segment)/16000:.2f}s")
    except KeyboardInterrupt:
        cap.stop()
