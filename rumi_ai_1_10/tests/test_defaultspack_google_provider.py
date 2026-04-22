from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class TestDefaultspackGoogleProvider(unittest.TestCase):
    def test_detect_available_providers_accepts_gemini_api_key(self):
        from domain.ai_client.providers import detect_available_providers

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True):
            providers = detect_available_providers()

        self.assertIn("google", providers)

    def test_google_provider_prefers_google_api_key_when_both_are_set(self):
        from domain.ai_client.providers.google_provider import GoogleProvider

        with patch.dict(
            os.environ,
            {"GOOGLE_API_KEY": "google-key", "GEMINI_API_KEY": "gemini-key"},
            clear=True,
        ):
            provider = GoogleProvider()

        self.assertEqual(provider._api_key, "google-key")

    def test_google_provider_loads_profile_models_from_user_data(self):
        from domain.ai_client.providers.google_provider import GoogleProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "profiles"
            target_dir = profile_dir / "gemma-3-12b-it"
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "profile.json").write_text(
                json.dumps(
                    {
                        "provider_id": "google",
                        "model_id": "gemma-3-12b-it",
                        "display_name": "Gemma 3 12B IT",
                        "metadata": {"type": "chat"},
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(GoogleProvider, "PROFILE_DIR", profile_dir):
                provider = GoogleProvider()
                model_ids = {item["id"] for item in provider.list_models()}

        self.assertIn("google/gemma-3-12b-it", model_ids)
        self.assertIn("google/gemini-2.5-pro", model_ids)

    def test_google_catalog_includes_gemini_and_gemma_models(self):
        from domain.ai_client.providers import get_all_known_models

        model_ids = {item["id"] for item in get_all_known_models(provider_id="google")}

        self.assertIn("google/gemini-3-pro-preview", model_ids)
        self.assertIn("google/gemini-3-flash-preview", model_ids)
        self.assertIn("google/gemma-4-31b-it", model_ids)
        self.assertIn("google/gemma-3-27b-it", model_ids)
        self.assertIn("google/gemma-3n-e4b-it", model_ids)


if __name__ == "__main__":
    unittest.main()
