"""
Quick smoke-test matching the verification checklist in PROMPT.md.
Run: python test_api.py
"""
import urllib.request
import urllib.error
import json


BASE = "http://localhost:8000"


def request(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(NoRedirect)


def get_redirect(path):
    try:
        _opener.open(BASE + path)
        return None, None
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location")


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))


# 1. Create
status, body = request("POST", "/api/qr/create", {"url": "https://example.com"})
check("POST /api/qr/create → 200", status == 200)
token = body.get("token", "")
check("Response has token", bool(token), token)
check("Response has short_url", "short_url" in body)
check("Response has qr_code_url", "qr_code_url" in body)
print(f"     token = {token}")

# 2. Redirect → 302
code, location = get_redirect(f"/r/{token}")
check("GET /r/{token} → 302", code == 302, f"got {code}, Location: {location}")

# 3. Get info
status, body = request("GET", f"/api/qr/{token}")
check("GET /api/qr/{token} → 200", status == 200)
check("Info token matches", body.get("token") == token)

# 4. Update URL
status, body = request("PATCH", f"/api/qr/{token}", {"url": "https://new-url.com"})
check("PATCH /api/qr/{token} → 200", status == 200)
check("original_url updated", body.get("original_url") == "https://new-url.com/")

# 5. Redirect now goes to new URL
code, location = get_redirect(f"/r/{token}")
check("Redirect after PATCH → new-url", location and "new-url" in location, f"Location: {location}")

# 6. Delete
status, body = request("DELETE", f"/api/qr/{token}")
check("DELETE /api/qr/{token} → 200", status == 200)

# 7. Redirect after delete → 410
code, _ = get_redirect(f"/r/{token}")
check("Redirect after DELETE → 410", code == 410, f"got {code}")

# 8. Non-existent token → 404
code, _ = get_redirect("/r/INVALID")
check("GET /r/INVALID → 404", code == 404, f"got {code}")

# 9. QR image → 200 image/png (create fresh token first)
_, img_body = request("POST", "/api/qr/create", {"url": "https://example.com"})
img_token = img_body["token"]
img_req = urllib.request.Request(BASE + f"/api/qr/{img_token}/image")
with urllib.request.urlopen(img_req) as resp:
    ct = resp.headers.get("Content-Type")
    size = len(resp.read())
check("GET /api/qr/{token}/image → 200 image/png", ct == "image/png", f"Content-Type: {ct}, size: {size}B")

# 10. Analytics
status, body = request("GET", f"/api/qr/{img_token}/analytics")
check("GET /api/qr/{token}/analytics → 200", status == 200)
check("Analytics has total_scans", "total_scans" in body)
check("Analytics has scans_by_day", "scans_by_day" in body)
