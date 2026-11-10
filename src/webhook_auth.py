import base64
import binascii
import logging
import time

from ecdsa import BadSignatureError, Ed25519, VerifyingKey
from fastapi import HTTPException, Request

from src.config import get_worker_setting, settings

logger = logging.getLogger(__name__)
MAX_WEBHOOK_AGE_SECONDS = 300


async def verify_telnyx_signature(request: Request) -> None:
    env = request.scope.get("env")
    public_key = get_worker_setting(env, "TELNYX_PUBLIC_KEY") if env is not None else settings.telnyx_public_key
    try:
        if not isinstance(public_key, str):
            raise ValueError("Missing public key")
        key_bytes = base64.b64decode(public_key, validate=True)
        if len(key_bytes) != 32:
            raise ValueError("Invalid public key length")
        key = VerifyingKey.from_string(key_bytes, curve=Ed25519)
    except (ValueError, binascii.Error) as exc:
        logger.error("webhook_verification_unconfigured")
        raise HTTPException(status_code=503, detail="Telnyx webhook verification is not configured") from exc

    signature = request.headers.get("telnyx-signature-ed25519", "")
    timestamp = request.headers.get("telnyx-timestamp", "")
    try:
        if not timestamp.isascii() or not timestamp.isdigit() or len(timestamp) > 12:
            raise ValueError("Invalid timestamp")
        if abs(time.time() - int(timestamp)) > MAX_WEBHOOK_AGE_SECONDS:
            raise ValueError("Expired timestamp")
        signature_bytes = base64.b64decode(signature, validate=True)
        if len(signature_bytes) != 64:
            raise ValueError("Invalid signature length")
        message = timestamp.encode("ascii") + b"|" + await request.body()
        key.verify(signature_bytes, message)
    except (ValueError, binascii.Error, BadSignatureError) as exc:
        logger.warning("webhook_signature_rejected")
        raise HTTPException(status_code=401, detail="Invalid Telnyx webhook signature or timestamp") from exc
