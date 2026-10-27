# backend/auth.py - dependency xác thực cho các router (đọc header "Authorization: Bearer <token>")
from typing import Optional
from fastapi import Header, HTTPException, Depends
from database import db
from security import read_token


def _parse(authorization: Optional[str]):
    if not authorization:
        return None
    parts = authorization.split()
    data = read_token(parts[1]) if len(parts) == 2 and parts[0].lower() == "bearer" else None
    if not data:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại")
    return data


def optional_user(authorization: Optional[str] = Header(None)):
    """Khách vãng lai -> None; có token sai/hết hạn -> 401."""
    return _parse(authorization)


def current_user(authorization: Optional[str] = Header(None)) -> dict:
    data = _parse(authorization)
    if not data:
        raise HTTPException(status_code=401, detail="Vui lòng đăng nhập")
    return data


def staff_uid(user: dict = Depends(current_user)) -> str:
    """Chỉ owner/staff (kiểm tra lại role trong DB, không tin hoàn toàn vào token)."""
    snap = db.collection('users').document(user['uid']).get()
    if not snap.exists or snap.to_dict().get('role') not in ('owner', 'staff'):
        raise HTTPException(status_code=403, detail="Bạn không có quyền thực hiện thao tác này")
    return user['uid']