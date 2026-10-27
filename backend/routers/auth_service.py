# backend/routers/auth_service.py
# Đăng ký có OTP (email hoặc SĐT) -> đăng nhập bằng SĐT HOẶC email + cùng 1 mật khẩu -> token.
# Hồ sơ: /me, đổi tên, avatar, lịch sử điểm.
import os
import re
import uuid
import hmac
import hashlib
import secrets
import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from google.cloud import firestore as gcf
from database import db
from auth import current_user
from security import (hash_password, verify_password, normalize_phone, is_valid_phone, is_valid_email,
                      make_token, hash_otp)
import email_utils

router = APIRouter(prefix="/api/auth", tags=["Auth Service"])
OTP_TTL, OTP_COOLDOWN, OTP_MAX_TRIES = 300, 60, 5
AVATAR_RE = re.compile(r'^data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$')


class RegisterRequest(BaseModel):
    full_name: str
    phone: str
    email: str
    password: str
    channel: str = "email"             # nơi nhận OTP: email | phone


class VerifyRequest(BaseModel):
    email: str
    code: str


class LoginRequest(BaseModel):
    identifier: Optional[str] = None   # SĐT hoặc email
    phone: Optional[str] = None        # tương thích bản cũ
    password: str


class ProfileUpdate(BaseModel):
    full_name: str


class AvatarUpload(BaseModel):
    data_url: str


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _find(field: str, value: str):
    return list(db.collection('users').where(field, '==', value).limit(5).stream())


def _otp_ref(email: str):
    return db.collection('otp_codes').document("register_" + hashlib.sha256(email.encode()).hexdigest()[:32])


def _mask(value: str, channel: str) -> str:
    if channel == "phone":
        return value[:3] + "****" + value[-3:]
    name, _, dom = value.partition("@")
    return name[:2] + "***@" + dom


def _send_sms(phone: str, text: str):
    """Chưa gắn nhà cung cấp SMS (eSMS, SpeedSMS, Twilio...). Hiện chỉ in ra console để thử nghiệm."""
    print(f"[SMS -> {phone}] {text}")


def _public(u: dict) -> dict:
    return {"uid": u['uid'], "role": u.get('role', 'customer'), "full_name": u.get('full_name', ''),
            "email": u.get('email', ''), "phone": u.get('phone', ''), "points": int(u.get('points', 0)),
            "total_spent": int(u.get('total_spent', 0)), "avatar_url": u.get('avatar_url', ''),
            "created_at": u.get('created_at')}


def _session(u: dict) -> dict:
    return {"token": make_token(u['uid'], u.get('role', 'customer')), "user": _public(u)}


# ---------------- ĐĂNG KÝ (2 bước: gửi OTP -> xác nhận OTP mới tạo tài khoản) ----------------
@router.post("/register/request")
def register_request(req: RegisterRequest, background: BackgroundTasks):
    name = req.full_name.strip()
    phone = normalize_phone(req.phone)
    email = req.email.strip().lower()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Vui lòng nhập họ và tên")
    if not is_valid_phone(phone):
        raise HTTPException(status_code=400, detail="Số điện thoại không hợp lệ (10 số, bắt đầu bằng 0)")
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="Email không hợp lệ")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Mật khẩu tối thiểu 6 ký tự")
    if req.channel not in ("email", "phone"):
        raise HTTPException(status_code=400, detail="Kênh nhận OTP không hợp lệ")
    if _find('phone', phone):
        raise HTTPException(status_code=409, detail="Số điện thoại đã được đăng ký")
    if _find('email', email):
        raise HTTPException(status_code=409, detail="Email đã được đăng ký")

    ref, now = _otp_ref(email), _now()
    old = ref.get()
    if old.exists and (now - old.to_dict()['created_at']).total_seconds() < OTP_COOLDOWN:
        raise HTTPException(status_code=429, detail="Vui lòng đợi 60 giây trước khi yêu cầu gửi lại mã")

    code = f"{secrets.randbelow(10 ** 6):06d}"
    ref.set({"purpose": "register", "email": email, "phone": phone, "full_name": name, "channel": req.channel,
             "password_hash": hash_password(req.password), "code_hash": hash_otp(email, code),
             "attempts": 0, "created_at": now, "expires_at": now + datetime.timedelta(seconds=OTP_TTL)})

    if req.channel == "phone":
        background.add_task(_send_sms, phone, f"UNISEX Salon: ma xac nhan cua ban la {code} (hieu luc 5 phut)")
    else:
        html = (f'<div style="font-family:Arial,sans-serif;padding:20px;border:1px solid #f5a623;border-radius:8px;">'
                f'<h2 style="color:#f5a623;">Mã xác nhận đăng ký - UNISEX Salon</h2><p>Xin chào <strong>{email_utils.e(name)}</strong>,</p>'
                f'<p>Mã OTP của bạn: <strong style="font-size:26px;color:#d35400;letter-spacing:3px;">{code}</strong></p>'
                f'<p><i>Mã có hiệu lực 5 phút. Nếu không phải bạn đăng ký, hãy bỏ qua email này.</i></p></div>')
        background.add_task(email_utils.send_email, email, "[UNISEX Salon] Mã xác nhận đăng ký", html)

    resp = {
        "status": "otp_sent",
        "channel": req.channel,
        "sent_to": _mask(phone if req.channel == "phone" else email, req.channel),
        "expires_in": OTP_TTL
    }
    dev_flag = (os.getenv("OTP_DEV_ECHO") or "").strip()
    if dev_flag and dev_flag != "0" or req.channel == "phone":
        # Nếu chọn SMS (chưa có nhà mạng) hoặc đang bật OTP_DEV_ECHO trong .env thì trả luôn mã để test
        resp["dev_code"] = code
    return resp


@router.post("/register/verify")
def register_verify(req: VerifyRequest):
    email = req.email.strip().lower()
    ref = _otp_ref(email)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status_code=400, detail="Chưa có yêu cầu đăng ký hoặc mã đã hết hạn")
    d = snap.to_dict()
    if _now() > d['expires_at']:
        ref.delete()
        raise HTTPException(status_code=400, detail="Mã OTP đã hết hạn, vui lòng gửi lại")
    if d.get('attempts', 0) >= OTP_MAX_TRIES:
        raise HTTPException(status_code=429, detail="Nhập sai quá nhiều lần, vui lòng yêu cầu mã mới")
    if not hmac.compare_digest(hash_otp(email, req.code.strip()), d['code_hash']):
        ref.update({"attempts": gcf.Increment(1)})
        raise HTTPException(status_code=400, detail="Mã OTP không chính xác")
    if _find('phone', d['phone']) or _find('email', email):
        raise HTTPException(status_code=409, detail="Số điện thoại hoặc email đã được đăng ký")

    uid = "user_" + uuid.uuid4().hex[:10]
    user = {"uid": uid, "role": "customer", "full_name": d['full_name'], "email": email, "phone": d['phone'],
            "password_hash": d['password_hash'], "total_spent": 0, "points": 0, "avatar_url": "",
            "email_verified": d['channel'] == "email", "phone_verified": d['channel'] == "phone",
            "created_at": _now()}
    db.collection('users').document(uid).set(user)
    ref.delete()
    return _session(user)


# ---------------- ĐĂNG NHẬP ----------------
@router.post("/login")
def login(req: LoginRequest):
    ident = (req.identifier or req.phone or "").strip()
    if not ident or not req.password:
        raise HTTPException(status_code=400, detail="Vui lòng nhập tài khoản và mật khẩu")
    if '@' in ident:
        docs = _find('email', ident.lower())
    else:
        docs = _find('phone', normalize_phone(ident)) or _find('phone', ident)

    for d in docs:
        u = d.to_dict()
        ok = False
        if u.get('password_hash'):
            ok = verify_password(req.password, u['password_hash'])
        elif u.get('password') is not None and u['password'] == req.password:
            ok = True   # tài khoản cũ lưu mật khẩu thô -> tự nâng cấp sang băm
            d.reference.update({"password_hash": hash_password(req.password), "password": gcf.DELETE_FIELD})
        if ok:
            return _session(u)
    raise HTTPException(status_code=401, detail="Sai tài khoản hoặc mật khẩu")


# ---------------- HỒ SƠ ----------------
def _me(uid: str) -> dict:
    snap = db.collection('users').document(uid).get()
    if not snap.exists:
        raise HTTPException(status_code=401, detail="Tài khoản không tồn tại")
    return snap.to_dict()


@router.get("/me")
def get_me(user: dict = Depends(current_user)):
    return _public(_me(user['uid']))


@router.patch("/me")
def update_me(req: ProfileUpdate, user: dict = Depends(current_user)):
    name = req.full_name.strip()
    if len(name) < 2 or len(name) > 60:
        raise HTTPException(status_code=400, detail="Họ tên phải từ 2 đến 60 ký tự")
    db.collection('users').document(user['uid']).update({"full_name": name})
    return _public(_me(user['uid']))


@router.post("/me/avatar")
def upload_avatar(req: AvatarUpload, user: dict = Depends(current_user)):
    """Avatar nhỏ (frontend nén về ~256px) lưu thẳng vào Firestore dạng data URL."""
    if len(req.data_url) > 400_000 or not AVATAR_RE.match(req.data_url):
        raise HTTPException(status_code=400, detail="Ảnh không hợp lệ hoặc quá lớn (tối đa ~300KB, jpg/png/webp)")
    db.collection('users').document(user['uid']).update({"avatar_url": req.data_url})
    return {"status": "success", "avatar_url": req.data_url}


@router.get("/me/points")
def points_history(limit: int = 50, user: dict = Depends(current_user)):
    docs = db.collection('point_transactions').where('user_id', '==', user['uid']).stream()
    rows = [{"id": d.id, **d.to_dict()} for d in docs]
    rows.sort(key=lambda r: str(r.get('created_at', '')), reverse=True)
    return rows[:min(limit, 200)]