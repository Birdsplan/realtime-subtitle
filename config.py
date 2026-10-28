import configparser
import os

class Config:
    """Centralized configuration loaded from config.ini"""
    
    def __init__(self, config_path=None):
        if config_path is None:
            # Look for config.ini in the same directory as this script
            config_path = os.path.join(os.path.dirname(__file__), "config.ini")
        
        self.config = configparser.ConfigParser()
        
        if os.path.exists(config_path):
            self.config.read(config_path)
            print(f"[Config] Loaded from: {config_path}")
        else:
            print(f"[Config] Warning: {config_path} not found, using defaults/env vars")
        
        # Translation provider settings
        default_provider = "deepseek" if os.getenv("DEEPSEEK_API_KEY") else "openai"
        self.translation_provider = self._get("translation", "provider", default_provider).lower()
        default_api_key_env = "DEEPSEEK_API_KEY" if self.translation_provider == "deepseek" else "OPENAI_API_KEY"
        self.api_key_env = self._get("translation", "api_key_env", default_api_key_env)
        
        # API settings (env vars take precedence)
        configured_base_url = (
            self._get("translation", "base_url")
            or self._get("api", "base_url")
            or None
        )
        if self.translation_provider == "deepseek":
            self.api_base_url = os.getenv("DEEPSEEK_BASE_URL") or configured_base_url or "https://api.deepseek.com"
        else:
            self.api_base_url = os.getenv("OPENAI_BASE_URL") or configured_base_url or None
        
        self.api_key = (
            os.getenv(self.api_key_env)
            or self._get("api", "api_key")
            or "dummy-key-for-local"
        )
        
        # Translation settings
        default_model = "deepseek-v4-flash" if self.translation_provider == "deepseek" else "gpt-3.5-turbo"
        self.model = self._get("translation", "model", default_model)
        default_target_lang = "zh-CN" if self.translation_provider == "deepseek" else "Chinese"
        self.target_lang = self._get("translation", "target_lang", default_target_lang)
        self.translation_threads = self._getint("translation", "threads", 4)
        self.translation_disable_thinking = self._get("translation", "disable_thinking", "true").lower() == "true"
        
        # Transcription settings
        self.asr_backend = self._get("transcription", "backend", "whisper").lower()
        self.whisper_model = self._get("transcription", "whisper_model", "base")
        self.funasr_model = self._get("transcription", "funasr_model", "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch")
        self.whisper_device = self._get("transcription", "device", "cpu")
        self.whisper_compute_type = self._get("transcription", "compute_type", "int8")
        self.source_language = self._get("transcription", "source_language", "auto")
        if self.source_language == "auto":
            self.source_language = None  # Whisper uses None for auto-detect
        self.transcription_workers = self._getint("transcription", "transcription_workers", 2)
        
        # Audio settings
        self.audio_input_mode = self._get("audio", "input_mode", "microphone").lower()
        self.sample_rate = self._getint("audio", "sample_rate", 16000)
        self.silence_threshold = self._getfloat("audio", "silence_threshold", 0.01)
        self.silence_duration = self._getfloat("audio", "silence_duration", 0.8)
        self.chunk_duration = self._getfloat("audio", "chunk_duration", 0.5)
        loopback_idx_str = self._get("audio", "loopback_index", "auto")
        if loopback_idx_str.isdigit():
            self.loopback_index = int(loopback_idx_str)
        else:
            self.loopback_index = None
        
        # Device index: 'auto' or empty = auto-detect BlackHole, or set a specific index
        device_idx_str = self._get("audio", "device_index", "auto")
        if device_idx_str.isdigit():
            self.device_index = int(device_idx_str)
        elif device_idx_str.lower() in ("auto", ""):
            self.device_index = self._find_blackhole_device()
        else:
            self.device_index = None
            
        # Max phrase duration - force processing after N seconds
        self.max_phrase_duration = self._getfloat("audio", "max_phrase_duration", 5.0)
        
        # Streaming mode settings
        self.streaming_mode = self._get("audio", "streaming_mode", "false").lower() == "true"
        self.streaming_interval = self._getfloat("audio", "streaming_interval", 1.5)
        self.streaming_step_size = self._getfloat("audio", "streaming_step_size", 0.2)
        self.update_interval = self._getfloat("audio", "update_interval", 0.5)
        self.streaming_overlap = self._getfloat("audio", "streaming_overlap", 0.3)
        self.partial_transcription = self._get("audio", "partial_transcription", "true").lower() == "true"
        self.max_partial_duration = self._getfloat("audio", "max_partial_duration", 3.0)
        self.final_overlap_duration = self._getfloat("audio", "final_overlap_duration", 0.8)
        self.capture_buffer_seconds = self._getfloat("audio", "capture_buffer_seconds", 8.0)
        
        # Display settings
        self.display_duration = self._getfloat("display", "display_duration", 3.0)
        self.window_width = self._getint("display", "window_width", 1000)
        self.window_height = self._getint("display", "window_height", 320)
        self.max_visible_items = self._getint("display", "max_visible_items", 3)
        self.overlay_bottom_margin = self._getint("display", "bottom_margin", 48)
        self.overlay_position = self._get("display", "position", "bottom_center").lower()
        self.original_font_size = self._getint("display", "original_font_size", 16)
        self.translation_font_size = self._getint("display", "translation_font_size", 24)
        self.panel_opacity = self._getint("display", "panel_opacity", 118)
        self.auto_hide_controls = self._get("display", "auto_hide_controls", "true").lower() == "true"
    
    def _get(self, section, key, fallback=""):
        try:
            value = self.config.get(section, key)
            return value if value else fallback
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback
    
    def _getint(self, section, key, fallback=0):
        try:
            return self.config.getint(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return fallback
    
    def _getfloat(self, section, key, fallback=0.0):
        try:
            return self.config.getfloat(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return fallback
    
    def _find_blackhole_device(self):
        """Auto-detect BlackHole audio device index"""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            for i, d in enumerate(devices):
                if d['max_input_channels'] > 0 and 'blackhole' in d['name'].lower():
                    print(f"[Config] Auto-detected BlackHole device: [{i}] {d['name']}")
                    return i
            print("[Config] BlackHole not found, using default input device")
            return None
        except Exception as e:
            print(f"[Config] Error detecting audio devices: {e}")
            return None
    
    def print_config(self):
        """Print current configuration for debugging"""
        print("[Config] Current settings:")
        print(f"  Translation Provider: {self.translation_provider}")
        print(f"  API Base URL: {self.api_base_url or '(default OpenAI)'}")
        print(f"  API Key Env: {self.api_key_env}")
        print(f"  API Key: {self._mask_secret(self.api_key)}")
        print(f"  Model: {self.model}")
        print(f"  Target Language: {self.target_lang}")
        print(f"  ASR Backend: {self.asr_backend}")
        print(f"  Whisper Model: {self.whisper_model}")
        print(f"  FunASR Model: {self.funasr_model}")
        print(f"  Audio Input Mode: {self.audio_input_mode}")
        print(f"  Loopback Index: {self.loopback_index if self.loopback_index is not None else 'auto'}")
        print(f"  Sample Rate: {self.sample_rate}")
        print(f"  Partial ASR: {self.partial_transcription}")
        print(f"  Max Partial Duration: {self.max_partial_duration}s")
        print(f"  Final Overlap Duration: {self.final_overlap_duration}s")
        print(f"  Capture Buffer: {self.capture_buffer_seconds}s")
        print(f"  Overlay Size: {self.window_width}x{self.window_height}")
        print(f"  Overlay Visible Items: {self.max_visible_items}")
        print(f"  Overlay Position: {self.overlay_position}")
        print(f"  Overlay Font Sizes: {self.original_font_size}/{self.translation_font_size}")

    def _mask_secret(self, value):
        if not value:
            return "(empty)"
        return "***"

# Global config instance
config = Config()
