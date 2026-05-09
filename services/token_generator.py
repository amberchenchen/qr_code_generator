import hashlib
import string
import time

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
    hash(url + timestamp_ns) → SHA-256 → first 8 bytes → Base62 → first `length` chars
    Following the diagram: hash → SHA-256 → byte values → Base62 [A-Za-z0-9]
    e.g. 3842 → 61 remainder → 'y', then 61/62 = 0 remainder 61 → 'z', so 3842 → "zy"
    """
    seed = f"{url}{time.time_ns()}"
    hash_bytes = hashlib.sha256(seed.encode()).digest()
    num = int.from_bytes(hash_bytes[:8], "big")
    token = _int_to_base62(num)
    # Pad to ensure minimum length (very rare edge case for small nums)
    return token[:length].ljust(length, BASE62[0])
