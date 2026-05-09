import hashlib
import os
import string

BASE62 = string.ascii_letters + string.digits  # [A-Za-z0-9], 62 chars


def _int_to_base62(num: int) -> str:
    if num == 0:
        return BASE62[0]
    digits = []
    while num > 0:
        digits.append(BASE62[num % 62])
        num //= 62
    return "".join(reversed(digits))


def generate_token(url: str, length: int = 7) -> str:
    """
    SHA-256(url + nonce) → first 8 bytes → Base62 [A-Za-z0-9] → first `length` chars

    nonce = os.urandom(16)  — cryptographically random, eliminates timing collisions
    Caller retries on DB uniqueness conflict (collision retry loop in qr_router.py).
    """
    nonce = os.urandom(16)
    payload = url.encode() + nonce
    hash_bytes = hashlib.sha256(payload).digest()
    num = int.from_bytes(hash_bytes[:8], "big")
    token = _int_to_base62(num)
    return token[:length].ljust(length, BASE62[0])
