# backend/routers/coupon_service.py
# Collection `coupons` (doc id = code, viết hoa):
#   code, description, discount_type ("percent" | "fixed"), discount_value (20 = 20% | 50000 = 50.000đ),
#   max_discount_amount (trần giảm cho %, 0 = không giới hạn), min_order_value,
#   valid_from, valid_until, usage_limit (0 = không giới hạn), used_count, is_active
import re
import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from database import db
from auth import staff_uid

router = APIRouter(prefix="/api/coupons", tags=["Coupon Service"])
CODE_RE = re.compile(r'^[A-Z0-9_-]{3,30}$')


class CouponError(Exception):
    pass


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


def evaluate_coupon(c: dict, subtotal: int, now) -> int:
    """Trả về số tiền được giảm, hoặc raise CouponError với lý do."""
    if not c.get('is_active', True):
        raise CouponError("Mã giảm giá đã bị vô hiệu hoá")
    if c.get('valid_from') and now < _aware(c['valid_from']):
        raise CouponError("Mã giảm giá chưa đến thời gian áp dụng")
    if c.get('valid_until') and now > _aware(c['valid_until']):
        raise CouponError("Mã giảm giá đã hết hạn")
    limit = int(c.get('usage_limit') or 0)
    if limit and int(c.get('used_count', 0)) >= limit:
        raise CouponError("Mã giảm giá đã hết lượt sử dụng")
    min_order = int(c.get('min_order_value') or 0)
    if subtotal < min_order:
        raise CouponError(f"Đơn hàng tối thiểu {min_order:,}đ để dùng mã này".replace(",", "."))

    value = float(c.get('discount_value') or 0)
    if c.get('discount_type') == 'percent':
        d = int(subtotal * value / 100)
        cap = int(c.get('max_discount_amount') or 0)
        if cap:
            d = min(d, cap)
    else:
        d = int(value)
    return max(0, min(d, subtotal))


class ValidateRequest(BaseModel):
    code: str
    subtotal: int


@router.post("/validate")
def validate_coupon(req: ValidateRequest):
    code = req.code.strip().upper()
    if not CODE_RE.match(code):
        raise HTTPException(status_code=400, detail="Mã giảm giá không hợp lệ")
    snap = db.collection('coupons').document(code).get()
    if not snap.exists:
        raise HTTPException(status_code=400, detail="Mã giảm giá không tồn tại")
    c = snap.to_dict()
    try:
        discount = evaluate_coupon(c, req.subtotal, datetime.datetime.now(datetime.timezone.utc))
    except CouponError as ex:
        raise HTTPException(status_code=400, detail=str(ex))
    return {"valid": True, "code": code, "discount": discount, "description": c.get('description', '')}


# ---------------- ADMIN ----------------
def _require_staff(uid: str):
    u = db.collection('users').document(uid).get()
    if not u.exists or u.to_dict().get('role') not in ('owner', 'staff'):
        raise HTTPException(status_code=403, detail="Bạn không có quyền thực hiện thao tác này")


class CouponUpsert(BaseModel):
    code: str
    description: str = ""
    discount_type: str                       # percent | fixed
    discount_value: float
    max_discount_amount: int = 0
    min_order_value: int = 0
    valid_from: Optional[datetime.datetime] = None
    valid_until: datetime.datetime
    usage_limit: int = 0
    is_active: bool = True


@router.get("/admin/all")
def admin_list(admin_uid: str = Depends(staff_uid)):
    return [{"id": d.id, **d.to_dict()} for d in db.collection('coupons').stream()]


@router.post("/admin")
def admin_upsert(req: CouponUpsert, admin_uid: str = Depends(staff_uid)):
    code = req.code.strip().upper()
    if not CODE_RE.match(code):
        raise HTTPException(status_code=400, detail="Mã chỉ gồm chữ/số/-/_ (3-30 ký tự)")
    if req.discount_type not in ("percent", "fixed") or req.discount_value <= 0:
        raise HTTPException(status_code=400, detail="Loại hoặc giá trị giảm không hợp lệ")
    if req.discount_type == "percent" and req.discount_value > 100:
        raise HTTPException(status_code=400, detail="Phần trăm giảm tối đa 100")
    ref = db.collection('coupons').document(code)
    data = req.dict()
    data['code'] = code
    old = ref.get()
    data['used_count'] = old.to_dict().get('used_count', 0) if old.exists else 0
    ref.set(data)
    return {"status": "success", "code": code}


@router.patch("/admin/{code}/toggle")
def admin_toggle(code: str, admin_uid: str = Depends(staff_uid)):
    ref = db.collection('coupons').document(code.upper())
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy mã")
    new_state = not snap.to_dict().get('is_active', True)
    ref.update({"is_active": new_state})
    return {"status": "success", "is_active": new_state}


@router.get("/public")
def public_coupons():
    """Mã đang dùng được (hiển thị gợi ý ở trang thanh toán)."""
    now, out = datetime.datetime.now(datetime.timezone.utc), []
    for d in db.collection('coupons').where('is_active', '==', True).stream():
        c = d.to_dict()
        try:
            evaluate_coupon(c, int(c.get('min_order_value') or 0), now)
        except CouponError:
            continue
        out.append({"code": d.id, "description": c.get('description', ''), "discount_type": c.get('discount_type'),
                    "discount_value": c.get('discount_value'), "min_order_value": c.get('min_order_value', 0)})
    return out