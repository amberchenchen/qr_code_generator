from urllib.parse import urlparse, urlunparse

# Blocklist for obviously malicious domains (extend as needed)
_BLOCKED_DOMAINS = {
    "malware.com",
    "phishing-site.com",
    "evil.example",
}


def normalize_url(url: str) -> str:
    """
    Normalize URL so that http://Example.com/ and https://example.com
    are treated as the same resource:
    - Add https:// if scheme is missing
    - Lowercase scheme and host
    - Strip trailing slash from path (unless path is just '/')
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"

    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        parsed.params,
        parsed.query,
        parsed.fragment,
    ))


def validate_url(url: str) -> tuple[bool, str]:
    """
    Returns (is_valid, normalized_url_or_error_message).
    Checks: scheme, netloc presence, and domain blocklist.
    """
    try:
        normalized = normalize_url(url)
        parsed = urlparse(normalized)

        if parsed.scheme not in ("http", "https"):
            return False, "URL must use http or https scheme"

        if not parsed.netloc:
            return False, "Invalid URL: missing host"

        domain = parsed.netloc.split(":")[0]
        if domain in _BLOCKED_DOMAINS:
            return False, f"URL is blocked: {domain} is flagged as malicious"

        return True, normalized
    except Exception as exc:
        return False, f"Invalid URL: {exc}"
