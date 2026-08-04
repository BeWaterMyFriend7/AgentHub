from __future__ import annotations

import base64
import ctypes
import json
import os
import threading
from pathlib import Path
from typing import Callable


def _data_blob(data: bytes) -> tuple[ctypes.Structure, ctypes.Structure]:
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.c_ulong),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(
        len(data),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)),
    )
    return DATA_BLOB(), blob_in


def _dpapi_protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise OSError("Windows DPAPI 仅可用于 Windows。")
    blob_out, blob_in = _data_blob(data)
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise OSError("CryptProtectData 调用失败。")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _dpapi_unprotect(ciphertext: bytes) -> bytes:
    if os.name != "nt":
        raise OSError("Windows DPAPI 仅可用于 Windows。")
    blob_out, blob_in = _data_blob(ciphertext)
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise OSError("CryptUnprotectData 调用失败。")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


class SecretStore:
    """本地加密保存 Provider API Key；文件不保存明文，读取时按需解密。"""

    def __init__(
        self,
        path: str | Path,
        *,
        protect: Callable[[bytes], bytes] | None = None,
        unprotect: Callable[[bytes], bytes] | None = None,
    ) -> None:
        self._path = Path(path).expanduser()
        self._protect = protect or _dpapi_protect
        self._unprotect = unprotect or _dpapi_unprotect
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    def save(self, provider_id: str, api_key: str) -> None:
        ciphertext = base64.b64encode(
            self._protect(api_key.encode("utf-8"))
        ).decode("ascii")
        with self._lock:
            payload = self._read()
            secrets = payload.setdefault("secrets", {})
            secrets[provider_id] = {"ciphertext": ciphertext}
            self._write(payload)

    def get(self, provider_id: str) -> str | None:
        with self._lock:
            payload = self._read()
            entry = payload.get("secrets", {}).get(provider_id)
        if not entry or not isinstance(entry, dict):
            return None
        try:
            ciphertext = base64.b64decode(entry["ciphertext"])
        except (KeyError, ValueError):
            return None
        return self._unprotect(ciphertext).decode("utf-8")

    def delete(self, provider_id: str) -> bool:
        with self._lock:
            payload = self._read()
            secrets = payload.get("secrets", {})
            if provider_id not in secrets:
                return False
            del secrets[provider_id]
            self._write(payload)
            return True

    def has(self, provider_id: str) -> bool:
        with self._lock:
            payload = self._read()
            return provider_id in payload.get("secrets", {})

    def _read(self) -> dict[str, object]:
        if not self._path.is_file():
            return {"version": 1, "secrets": {}}
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("SecretStore 文件格式无效。")
        secrets = payload.get("secrets", {})
        if not isinstance(secrets, dict):
            raise ValueError("SecretStore secrets 字段格式无效。")
        return {"version": 1, "secrets": secrets}

    def _write(self, payload: dict[str, object]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self._path)
