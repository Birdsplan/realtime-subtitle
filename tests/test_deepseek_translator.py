#!/usr/bin/env python3
"""
Small test script for the DeepSeek translator integration.

Default mode is offline and does not call the DeepSeek API:

    python tests/test_deepseek_translator.py

Optional live smoke test:

    set DEEPSEEK_API_KEY=your_key_here
    set RUN_DEEPSEEK_LIVE_TEST=1
    python tests/test_deepseek_translator.py
"""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from translator import Translator


class FakeMessage:
    content = "你好，世界。"


class FakeChoice:
    message = FakeMessage()


class FakeResponse:
    choices = [FakeChoice()]


class FakeCompletions:
    def __init__(self):
        self.calls = 0
        self.last_kwargs = None

    def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return FakeResponse()


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FakeClient:
    def __init__(self):
        self.chat = FakeChat()


class DeepSeekTranslatorTests(unittest.TestCase):
    def test_deepseek_defaults(self):
        translator = Translator(
            provider="deepseek",
            api_key="test-key",
            target_lang="zh-CN",
            client=FakeClient(),
        )

        self.assertEqual(translator.provider, "deepseek")
        self.assertEqual(translator.base_url, "https://api.deepseek.com")
        self.assertEqual(translator.model, "deepseek-v4-flash")
        self.assertEqual(translator.api_key_env, "DEEPSEEK_API_KEY")
        self.assertTrue(translator.disable_thinking)

    def test_strip_thinking_tags(self):
        translator = Translator(provider="deepseek", api_key="test-key", client=FakeClient())

        result = translator._strip_thinking("<think>hidden reasoning</think>Final answer")

        self.assertEqual(result, "Final answer")

    def test_translate_uses_deepseek_options_and_cache(self):
        translator = Translator(
            provider="deepseek",
            api_key="test-key",
            target_lang="zh-CN",
            client=FakeClient(),
        )
        fake_client = translator.client

        first = translator.translate(
            "Hello, world.",
            use_context=False,
            source_lang="en",
            target_lang="zh-CN",
        )
        second = translator.translate(
            "Hello, world.",
            use_context=False,
            source_lang="en",
            target_lang="zh-CN",
        )

        self.assertEqual(first, "你好，世界。")
        self.assertEqual(second, "你好，世界。")
        self.assertEqual(fake_client.chat.completions.calls, 1)

        request = fake_client.chat.completions.last_kwargs
        self.assertEqual(request["model"], "deepseek-v4-flash")
        self.assertEqual(
            request["extra_body"],
            {"thinking": {"type": "disabled"}},
        )
        self.assertIn("Return only the translation", request["messages"][0]["content"])

    @unittest.skipUnless(
        os.getenv("RUN_DEEPSEEK_LIVE_TEST") == "1",
        "set RUN_DEEPSEEK_LIVE_TEST=1 to call the real DeepSeek API",
    )
    def test_live_deepseek_translation(self):
        if not os.getenv("DEEPSEEK_API_KEY"):
            self.fail("DEEPSEEK_API_KEY is required for the live DeepSeek test")

        translator = Translator(provider="deepseek", target_lang="zh-CN")
        result = translator.translate(
            "Hello, this is a short connection test.",
            use_context=False,
            source_lang="en",
            target_lang="zh-CN",
        )

        print(f"\nLive DeepSeek result: {result}")
        self.assertTrue(result)
        self.assertNotEqual(result, "Hello, this is a short connection test.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
