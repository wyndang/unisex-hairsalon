# backend/security.py
import re
import os
import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

_ITER = 120_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, _ITER)
    return "pbkdf2_sha256$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_b64, dk_b64 = stored.split('$')
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(dk_b64)
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, _ITER)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def normalize_phone(phone: str) -> str:
    """'+84 901.234.567' / '84901234567' -> '0901234567'"""
    p = re.sub(r'[\s.\-()]', '', phone or '')
    if p.startswith('+84'):
        p = '0' + p[3:]
    elif p.startswith('84') and len(p) == 11:
        p = '0' + p[2:]
    return p


def is_valid_phone(phone: str) -> bool:
    return bool(re.fullmatch(r'0\d{9}', phone or ''))


def is_valid_email(email: str) -> bool:
    return bool(re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email or ''))


# ---------------- Token đăng nhập (HMAC, không cần thư viện ngoài) ----------------
# BẮT BUỘC đặt AUTH_SECRET (chuỗi ngẫu nhiên dài) trong .env khi chạy thật.
_SECRET = (os.getenv("AUTH_SECRET") or base64.b64encode(os.urandom(32)).decode()).encode()
if not os.getenv("AUTH_SECRET"):
    print("[WARNING] Chưa đặt AUTH_SECRET trong .env: token sẽ mất hiệu lực mỗi lần khởi động lại server")


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip('=')


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def make_token(uid: str, role: str, ttl: int = 7 * 24 * 3600) -> str:
    body = _b64(json.dumps({"uid": uid, "role": role, "exp": int(time.time()) + ttl}).encode())
    sig = _b64(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())
    return body + "." + sig


def read_token(token: str):
    """Trả payload {uid, role, exp} hoặc None nếu sai chữ ký / hết hạn."""
    try:
        body, sig = token.split('.')
        expected = _b64(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_unb64(body))
        return data if data.get("exp", 0) > time.time() else None
    except Exception:
        return None


def hash_otp(key: str, code: str) -> str:
    return hmac.new(_SECRET, f"{key}:{code}".encode(), hashlib.sha256).hexdigest()