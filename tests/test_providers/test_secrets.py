from __future__ import annotations

import os
import tempfile
import unittest
import base64
import json
from pathlib import Path

from agent_hub.providers.secrets import SecretStore


def _fake_protect(data: bytes) -> bytes:
    return b"enc(" + data + b")"


def _fake_unprotect(ciphertext: bytes) -> bytes:
    return ciphertext[4:-1]


class SecretStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "secrets.json"
        self.store = SecretStore(
            self.path,
            protect=_fake_protect,
            unprotect=_fake_unprotect,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_save_get_delete_roundtrip_never_persists_plaintext(self) -> None:
        self.store.save("openai", "sk-plain-secret")

        self.assertEqual(self.store.get("openai"), "sk-plain-secret")
        self.assertTrue(self.store.has("openai"))
        content = self.path.read_text(encoding="utf-8")
        self.assertNotIn("sk-plain-secret", content)
        ciphertext = base64.b64decode(
            json.loads(content)["secrets"]["openai"]["ciphertext"]
        )
        self.assertEqual(ciphertext, b"enc(sk-plain-secret)")

        self.assertTrue(self.store.delete("openai"))
        self.assertFalse(self.store.has("openai"))
        self.assertIsNone(self.store.get("openai"))
        self.assertFalse(self.store.delete("openai"))

    def test_missing_or_corrupt_entry_returns_none(self) -> None:
        self.assertIsNone(self.store.get("missing"))

        self.path.write_text("{not-json", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.get("openai")

    def test_save_overwrites_previous_value(self) -> None:
        self.store.save("openai", "first")
        self.store.save("openai", "second")

        self.assertEqual(self.store.get("openai"), "second")

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI 仅可在 Windows 验证")
    def test_windows_dpapi_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = SecretStore(Path(temporary) / "secrets.json")
            store.save("openai", "dpapi-secret")
            self.assertEqual(store.get("openai"), "dpapi-secret")


if __name__ == "__main__":
    unittest.main()
