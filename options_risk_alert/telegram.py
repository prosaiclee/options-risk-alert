from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TELEGRAM_LIMIT = 4096


@dataclass(frozen=True)
class TelegramResult:
    ok: bool
    message: str
    response: dict[str, Any] | None = None


def send_telegram_message(
    text: str,
    *,
    token: str | None = None,
    chat_id: str | None = None,
    timeout: int = 15,
) -> TelegramResult:
    bot_token, target_chat_id = telegram_credentials(token=token, chat_id=chat_id)
    if not bot_token:
        return TelegramResult(False, "TELEGRAM_BOT_TOKEN is not set.")
    if not target_chat_id:
        return TelegramResult(False, "TELEGRAM_CHAT_ID is not set.")

    body = urlencode(
        {
            "chat_id": target_chat_id,
            "text": truncate_for_telegram(text),
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return TelegramResult(False, str(exc))
    return TelegramResult(bool(payload.get("ok")), "sent" if payload.get("ok") else str(payload), payload)


def send_telegram_document(
    path: str | Path,
    *,
    caption: str = "",
    token: str | None = None,
    chat_id: str | None = None,
    timeout: int = 30,
) -> TelegramResult:
    bot_token, target_chat_id = telegram_credentials(token=token, chat_id=chat_id)
    if not bot_token:
        return TelegramResult(False, "TELEGRAM_BOT_TOKEN is not set.")
    if not target_chat_id:
        return TelegramResult(False, "TELEGRAM_CHAT_ID is not set.")

    document_path = Path(path)
    if not document_path.exists():
        return TelegramResult(False, f"Document does not exist: {document_path}")

    body, content_type = multipart_form_data(
        fields={
            "chat_id": target_chat_id,
            "caption": truncate_caption(caption),
        },
        files={
            "document": document_path,
        },
    )
    request = Request(
        f"https://api.telegram.org/bot{bot_token}/sendDocument",
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return TelegramResult(False, str(exc))
    return TelegramResult(bool(payload.get("ok")), "sent" if payload.get("ok") else str(payload), payload)


def get_telegram_updates(
    *,
    token: str | None = None,
    offset: int | None = None,
    timeout_seconds: int = 10,
    request_timeout: int = 20,
) -> TelegramResult:
    env_file = read_env_file()
    bot_token = token or os.environ.get("TELEGRAM_BOT_TOKEN") or env_file.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return TelegramResult(False, "TELEGRAM_BOT_TOKEN is not set.")
    params = {"timeout": str(timeout_seconds)}
    if offset is not None:
        params["offset"] = str(offset)
    request = Request(f"https://api.telegram.org/bot{bot_token}/getUpdates?{urlencode(params)}")
    try:
        with urlopen(request, timeout=request_timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return TelegramResult(False, str(exc))
    return TelegramResult(bool(payload.get("ok")), "ok" if payload.get("ok") else str(payload), payload)


def telegram_credentials(*, token: str | None = None, chat_id: str | None = None) -> tuple[str | None, str | None]:
    env_file = read_env_file()
    bot_token = token or os.environ.get("TELEGRAM_BOT_TOKEN") or env_file.get("TELEGRAM_BOT_TOKEN")
    target_chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID") or env_file.get("TELEGRAM_CHAT_ID")
    return bot_token, target_chat_id


def multipart_form_data(*, fields: dict[str, str], files: dict[str, Path]) -> tuple[bytes, str]:
    boundary = "----OptionsRiskAlertBoundary7MA4YWxkTrZu0gW"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, path in files.items():
        filename = path.name
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8"),
                b"Content-Type: text/html\r\n\r\n",
                path.read_bytes(),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def truncate_for_telegram(text: str) -> str:
    if len(text) <= TELEGRAM_LIMIT:
        return text
    suffix = "\n\n... truncated"
    return text[: TELEGRAM_LIMIT - len(suffix)] + suffix


def truncate_caption(text: str) -> str:
    if len(text) <= 1024:
        return text
    suffix = "... truncated"
    return text[: 1024 - len(suffix)] + suffix


def read_env_file(path: str | Path = ".env") -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values
