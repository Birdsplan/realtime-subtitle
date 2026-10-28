import os
import re

class Translator:
    DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com"
    DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-flash"

    def __init__(
        self,
        api_key=None,
        base_url=None,
        model=None,
        target_lang="Chinese",
        provider="openai",
        api_key_env=None,
        disable_thinking=None,
        request_timeout=10.0,
        client=None,
    ):
        """
        Translates text using an OpenAI-compatible LLM API.
        
        Args:
            api_key: API key. If omitted, read from api_key_env.
            base_url: Optional base URL.
            model: Model name to use.
            target_lang: The target language for translation.
            provider: Provider name, currently "openai" or "deepseek".
            api_key_env: Environment variable name that stores the API key.
            disable_thinking: For DeepSeek, disable thinking mode for lower-latency translation.
            request_timeout: Per-request timeout in seconds.
            client: Optional injected client, used by tests.
        """
        self.provider = (provider or "openai").lower()
        self.target_lang = target_lang
        self.request_timeout = request_timeout
        
        if self.provider == "deepseek":
            api_key_env = api_key_env or "DEEPSEEK_API_KEY"
            base_url = base_url or os.getenv("DEEPSEEK_BASE_URL") or self.DEEPSEEK_DEFAULT_BASE_URL
            model = model or os.getenv("DEEPSEEK_MODEL") or self.DEEPSEEK_DEFAULT_MODEL
            if disable_thinking is None:
                disable_thinking = True
        else:
            api_key_env = api_key_env or "OPENAI_API_KEY"
            base_url = base_url or os.getenv("OPENAI_BASE_URL")
            model = model or "gpt-3.5-turbo"
            if disable_thinking is None:
                disable_thinking = False

        self.api_key_env = api_key_env
        self.base_url = base_url
        self.model = model
        self.disable_thinking = disable_thinking

        # If no key provided, check env. Some local servers do not need a real key,
        # but the OpenAI client still requires a non-empty string.
        if not api_key:
            api_key = os.getenv(api_key_env, "dummy-key-for-local")
        
        if client is None:
            try:
                from openai import OpenAI
                import httpx
            except ImportError as e:
                raise ImportError(
                    "The translator requires dependencies from requirements.txt. "
                    "Run the project installer or install the 'openai' and 'httpx' packages."
                ) from e

            # Create HTTP client with SSL verification disabled (for self-signed certs)
            http_client = httpx.Client(verify=False)
            self.client = OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)
        else:
            self.client = client
        
        # Logging
        print(f"[Translator] Initialized:")
        print(f"  - Provider: {self.provider}")
        print(f"  - Base URL: {base_url or 'https://api.openai.com/v1 (default)'}")
        print(f"  - Model: {model}")
        print(f"  - Target Language: {target_lang}")
        print(f"  - API Key Env: {api_key_env}")
        print(f"  - API Key: {self._mask_secret(api_key)}")
        
        # Context carryover for sentence continuity
        self.previous_text = ""
        self.previous_translation = ""
        self.cache = {}

    def _mask_secret(self, value):
        if not value:
            return "(empty)"
        return "***"

    def _strip_thinking(self, text):
        """Remove <think>...</think> tags from response (for reasoning models)"""
        # Remove think tags and their content
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return cleaned.strip()

    def _build_system_prompt(self, target_lang, source_lang, use_context):
        """Build a concise subtitle translation prompt."""
        source_hint = ""
        if source_lang and source_lang != "auto":
            source_hint = f" from {source_lang}"

        if self.provider == "deepseek":
            prompt = (
                "You are a real-time subtitle translation engine. "
                f"Translate the following speech transcript{source_hint} into concise, natural {target_lang}. "
                "Do not explain. Do not add information. "
                "Preserve technical terms, names, numbers, and acronyms. "
                "Return only the translation."
            )
        else:
            prompt = (
                "You are a professional real-time translator. "
                f"Translate the following user input{source_hint} into {target_lang}. "
                "Do not add any explanations, just output the translation."
            )

        if use_context and self.previous_text:
            prompt += (
                "\n\nUse this previous segment only for continuity; do not repeat it:\n"
                f"Previous source: \"{self.previous_text}\"\n"
                f"Previous translation: \"{self.previous_translation}\""
            )

        return prompt

    def translate(self, text, use_context=True, source_lang="auto", target_lang=None):
        """
        Translates the given text. Returns the translated string.
        Uses previous transcription as context for better continuity.
        """
        if not text or not text.strip():
            return ""

        normalized_text = text.strip()
        target_lang = target_lang or self.target_lang
        cache_key = (source_lang or "auto", target_lang, normalized_text)
        if cache_key in self.cache:
            return self.cache[cache_key]

        system_prompt = self._build_system_prompt(target_lang, source_lang, use_context)

        request_kwargs = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": normalized_text},
            ],
            "temperature": 0.3,
            "max_tokens": 500,
            "timeout": self.request_timeout,
        }

        if self.provider == "deepseek" and self.disable_thinking:
            request_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

        try:
            response = self.client.chat.completions.create(**request_kwargs)
            raw_result = response.choices[0].message.content.strip()
            # Strip thinking tags if present
            result = self._strip_thinking(raw_result)
            
            # Store for next translation context
            self.previous_text = normalized_text
            self.previous_translation = result
            self.cache[cache_key] = result
            
            return result
        except Exception as e:
            print(f"Translation Error: {e}")
            return normalized_text

if __name__ == "__main__":
    # Test
    print("Testing Translator (simulated)...")
    # This will likely fail if no real server is running, so we wrap in try
    t = Translator(target_lang="Spanish")
    print(t.translate("Hello world"))
