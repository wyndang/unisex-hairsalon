# backend/routers/orders_service.py
# Đặt hàng: coupon + điểm thưởng + thanh toán (COD / thẻ giả lập / banking giả lập),
# luồng trạng thái đơn, lịch sử mua hàng, email thông báo và API doanh thu cho Admin.
#
# Collections:
#   orders              : 1 doc / đơn hàng
#   purchases           : 1 doc / (đơn x sản phẩm) -> kiểm tra quyền đánh giá
#   point_transactions  : nhật ký điểm (earn | redeem | refund)
#   coupons             : xem coupon_service.py
#
# Trạng thái:
#   payment_status : pending | paid | cancelled | refunded
#   order_status   : pending_confirm (Chờ xác nhận) -> preparing (Chờ lấy hàng)
#                    -> shipping (Chờ giao hàng) -> completed (Hoàn tất / Đánh giá) | cancelled
#
# Công thức tiền:
#   total = subtotal - discount(coupon) - points_used        (1 điểm = 1đ)
#   Điểm thưởng = 1% * total, chỉ cộng khi đơn chuyển sang "completed".
import os
import re
import random
import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from google.cloud import firestore as gcf
from database import db
from security import normalize_phone, is_valid_phone, is_valid_email
from routers.coupon_service import evaluate_coupon, CouponError, CODE_RE
import email_utils
from auth import current_user, optional_user, staff_uid

router = APIRouter(prefix="/api/orders", tags=["Order Service"])
GUEST_ID = "guest"
EARN_RATE = 0.01
FLOW = ["pending_confirm", "preparing", "shipping", "completed"]
PAYMENT_METHODS = ("cod", "card", "banking")


# ---------------- MODELS ----------------
class CartItem(BaseModel):
    product_id: str
    quantity: int


class CardInfo(BaseModel):          # chỉ giả lập: KHÔNG lưu số thẻ, chỉ lưu 4 số cuối
    number: str = ""
    holder: str = ""
    expiry: str = ""                # MM/YY
    cvv: str = ""


class CheckoutRequest(BaseModel):
    customer_id: Optional[str] = None      # None / "guest" = khách vãng lai
    customer_name: str = ""
    phone_source: str = "account"          # account (SĐT đã đăng ký) | custom (nhập số khác)
    customer_phone: str = ""               # bắt buộc với khách vãng lai hoặc phone_source=custom
    customer_email: str = ""               # bắt buộc với khách vãng lai (user đã đăng nhập: lấy từ tài khoản)
    shipping_address: str
    note: str = ""
    payment_method: str                    # cod | card | banking
    card: Optional[CardInfo] = None
    bank_ref: str = ""                     # mã giao dịch giả lập (để trống -> hệ thống tự sinh)
    coupon_code: str = ""
    points_to_use: int = 0
    items: List[CartItem]


class PreviewRequest(BaseModel):
    customer_id: Optional[str] = None
    items: List[CartItem]
    coupon_code: str = ""
    points_to_use: int = 0


# ---------------- HELPERS ----------------
def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _purchase_ref(order_id: str, product_id: str):
    return db.collection('purchases').document(f"{order_id}_{product_id}")


def _require_staff(uid: str):
    u = db.collection('users').document(uid).get()
    if not u.exists or u.to_dict().get('role') not in ('owner', 'staff'):
        raise HTTPException(status_code=403, detail="Bạn không có quyền thực hiện thao tác này")


def _merge_items(items: List[CartItem]) -> dict:
    if not items:
        raise HTTPException(status_code=400, detail="Giỏ hàng đang trống")
    merged = {}
    for it in items:
        if not 1 <= it.quantity <= 99:
            raise HTTPException(status_code=400, detail="Số lượng mỗi sản phẩm phải từ 1 đến 99")
        merged[it.product_id] = merged.get(it.product_id, 0) + it.quantity
    return merged


def _build_lines(merged: dict, snaps: dict):
    """Giá + tồn kho luôn lấy từ DB, không tin dữ liệu từ client."""
    lines, subtotal = [], 0
    for pid, qty in merged.items():
        snap = snaps[pid]
        if not snap.exists or not snap.to_dict().get('is_active', True):
            raise HTTPException(status_code=404, detail="Có sản phẩm không còn được bán, vui lòng làm mới giỏ hàng")
        p = snap.to_dict()
        if int(p.get('stock', 0)) < qty:
            raise HTTPException(status_code=400,
                                detail=f"“{p['name']}” chỉ còn {int(p.get('stock', 0))} sản phẩm trong kho")
        line_total = int(p['price']) * qty
        subtotal += line_total
        lines.append({
            "product_id": pid, "name": p['name'], "brand": p.get('brand'), "type": p.get('type'),
            "img": p.get('img'), "unit_price": int(p['price']), "quantity": qty, "line_total": line_total
        })
    return lines, subtotal


def _apply_discounts(subtotal, coupon_snap, points_req, points_balance, now):
    """Trả (discount, points_used, total). Coupon sai -> HTTP 400."""
    discount = 0
    if coupon_snap is not None:
        if not coupon_snap.exists:
            raise HTTPException(status_code=400, detail="Mã giảm giá không tồn tại")
        try:
            discount = evaluate_coupon(coupon_snap.to_dict(), subtotal, now)
        except CouponError as ex:
            raise HTTPException(status_code=400, detail=str(ex))
    after = subtotal - discount
    pts = min(max(0, int(points_req or 0)), max(0, int(points_balance)), after)
    return discount, pts, after - pts


def _clean_code(code: str) -> str:
    code = (code or "").strip().upper()
    if code and not CODE_RE.match(code):
        raise HTTPException(status_code=400, detail="Mã giảm giá không hợp lệ")
    return code


def _resolve_identity(req: CheckoutRequest):
    """Trả (customer_id, user_ref, ident). User đã đăng nhập: lấy email/SĐT từ tài khoản."""
    cid = (req.customer_id or GUEST_ID).strip() or GUEST_ID
    name = req.customer_name.strip()
    if cid == GUEST_ID:
        phone = normalize_phone(req.customer_phone)
        email = req.customer_email.strip().lower()
        if len(name) < 2:
            raise HTTPException(status_code=400, detail="Vui lòng nhập họ và tên")
        if not is_valid_phone(phone):
            raise HTTPException(status_code=400, detail="Số điện thoại không hợp lệ (10 số, bắt đầu bằng 0)")
        if not is_valid_email(email):
            raise HTTPException(status_code=400, detail="Vui lòng nhập email hợp lệ để nhận xác nhận đơn hàng")
        return cid, None, {"name": name, "phone": phone, "email": email,
                           "phone_source": "custom", "account_phone": None}

    user_ref = db.collection('users').document(cid)
    snap = user_ref.get()
    if not snap.exists:
        raise HTTPException(status_code=401, detail="Tài khoản không hợp lệ, vui lòng đăng nhập lại")
    u = snap.to_dict()
    account_phone = u.get('phone', '')
    if req.phone_source == "custom":
        phone = normalize_phone(req.customer_phone)
        if not is_valid_phone(phone):
            raise HTTPException(status_code=400, detail="Số điện thoại không hợp lệ (10 số, bắt đầu bằng 0)")
    else:
        phone = account_phone
    return cid, user_ref, {"name": name or u.get('full_name', ''), "phone": phone,
                           "email": u.get('email', ''),
                           "phone_source": "custom" if req.phone_source == "custom" else "account",
                           "account_phone": account_phone}


def _build_payment_info(req: CheckoutRequest) -> dict:
    """Giả lập: chỉ kiểm tra định dạng sơ bộ, KHÔNG lưu số thẻ / CVV."""
    if req.payment_method == "card":
        c = req.card or CardInfo()
        digits = re.sub(r'\D', '', c.number)
        if not 13 <= len(digits) <= 19:
            raise HTTPException(status_code=400, detail="Số thẻ không hợp lệ (13-19 chữ số)")
        if not c.holder.strip():
            raise HTTPException(status_code=400, detail="Vui lòng nhập tên chủ thẻ")
        if not re.fullmatch(r'(0[1-9]|1[0-2])/\d{2}', c.expiry.strip()):
            raise HTTPException(status_code=400, detail="Ngày hết hạn thẻ phải dạng MM/YY")
        if not re.fullmatch(r'\d{3,4}', c.cvv.strip()):
            raise HTTPException(status_code=400, detail="CVV gồm 3-4 chữ số")
        return {"card_last4": digits[-4:], "card_holder": c.holder.strip().upper()}
    if req.payment_method == "banking":
        ref = req.bank_ref.strip() or "BK" + str(random.randint(10**9, 10**10 - 1))
        return {"bank_ref": ref[:40]}
    return {}


def _log_points(tx, user_id, order, kind, points, note):
    tx.set(db.collection('point_transactions').document(), {
        "user_id": user_id, "order_id": order['id'], "order_code": order['order_code'],
        "type": kind, "points": points, "note": note, "created_at": _now()
    })


# ---------------- EMAIL ----------------
_SUBJECT = {
    "paid": "Thanh toán thành công",
    "cod_placed": "Đặt hàng thành công",
    "cod_paid": "Đã nhận thanh toán",
    "completed": "Đơn hàng hoàn tất",
}


def _notify(order: dict, kind: str):
    """Chạy nền: email cho khách + email cho admin (đơn mới)."""
    try:
        code = order['order_code']
        if order.get('customer_email'):
            email_utils.send_email(order['customer_email'], f"[UNISEX Salon] {_SUBJECT[kind]} - {code}",
                                   email_utils.order_email_html(order, kind))
        if kind in ("paid", "cod_placed"):
            admin = os.getenv("ADMIN_EMAIL") or os.getenv("SMTP_EMAIL")
            if admin:
                email_utils.send_email(admin, f"🛒 Đơn hàng mới {code} - {email_utils.money(order['total'])}",
                                       email_utils.admin_order_email_html(order))
    except Exception as ex:
        print(f"[ERROR] Gửi email đơn hàng: {ex}")


# ---------------------------------------------------------------
# XEM TRƯỚC GIÁ (dùng cho trang checkout: áp mã + điểm trước khi bấm thanh toán)
# ---------------------------------------------------------------
@router.post("/preview")
def preview(req: PreviewRequest, user: Optional[dict] = Depends(optional_user)):
    req.customer_id = user['uid'] if user else None
    merged = _merge_items(req.items)
    snaps = {pid: db.collection('products').document(pid).get() for pid in merged}
    _, subtotal = _build_lines(merged, snaps)
    now = _now()

    balance = 0
    cid = (req.customer_id or GUEST_ID).strip() or GUEST_ID
    if cid != GUEST_ID:
        u = db.collection('users').document(cid).get()
        balance = int(u.to_dict().get('points', 0)) if u.exists else 0

    discount, coupon_error, code = 0, None, (req.coupon_code or "").strip().upper()
    if code:
        try:
            discount = evaluate_coupon_by_code(code, subtotal, now)
        except HTTPException as ex:
            coupon_error, code = ex.detail, ""
    after = subtotal - discount
    pts = min(max(0, req.points_to_use), balance, after)
    total = after - pts
    return {"subtotal": subtotal, "coupon_code": code or None, "coupon_error": coupon_error,
            "discount": discount, "points_balance": balance, "points_used": pts, "total": total,
            "points_to_earn": int(total * EARN_RATE) if cid != GUEST_ID else 0}


def evaluate_coupon_by_code(code, subtotal, now):
    code = _clean_code(code)
    snap = db.collection('coupons').document(code).get()
    if not snap.exists:
        raise HTTPException(status_code=400, detail="Mã giảm giá không tồn tại")
    try:
        return evaluate_coupon(snap.to_dict(), subtotal, now)
    except CouponError as ex:
        raise HTTPException(status_code=400, detail=str(ex))


# ---------------------------------------------------------------
# CHECKOUT
# ---------------------------------------------------------------
@gcf.transactional
def _checkout_tx(tx, req, merged, order_ref, user_ref, customer_id, ident, pay_info, coupon_code, is_paid, now):
    # --- ĐỌC TRƯỚC ---
    snaps = {pid: db.collection('products').document(pid).get(transaction=tx) for pid in merged}
    coupon_ref = db.collection('coupons').document(coupon_code) if coupon_code else None
    coupon_snap = coupon_ref.get(transaction=tx) if coupon_ref else None
    user_snap = user_ref.get(transaction=tx) if user_ref else None

    lines, subtotal = _build_lines(merged, snaps)
    balance = int(user_snap.to_dict().get('points', 0)) if user_snap is not None and user_snap.exists else 0
    discount, pts, total = _apply_discounts(subtotal, coupon_snap, req.points_to_use, balance, now)

    order = {
        "id": order_ref.id,
        "order_code": "UNI" + now.strftime("%y%m%d") + f"{random.randint(0, 99999):05d}",
        "customer_id": customer_id,
        "is_guest": customer_id == GUEST_ID,
        "customer_name": ident['name'],
        "customer_phone": ident['phone'],
        "customer_email": ident['email'],
        "phone_source": ident['phone_source'],     # account | custom
        "account_phone": ident['account_phone'],   # SĐT đăng ký (để admin đối chiếu)
        "shipping_address": req.shipping_address.strip(),
        "note": req.note.strip(),
        "items": lines,
        "total_items": sum(l['quantity'] for l in lines),
        "subtotal": subtotal,
        "coupon_code": coupon_code or None,
        "discount": discount,
        "points_used": pts,                         # 1 điểm = 1đ
        "total": total,                             # = subtotal - discount - points_used
        "payment_method": req.payment_method,
        "payment_info": pay_info,
        "payment_status": "paid" if is_paid else "pending",
        "order_status": "pending_confirm",
        "status_history": [{"status": "pending_confirm", "at": now}],
        "points_earned": 0,
        "points_awarded": False,
        "created_at": now,
        "paid_at": now if is_paid else None,
    }

    # --- GHI ---
    tx.set(order_ref, order)
    for ln in lines:
        upd = {"stock": gcf.Increment(-ln['quantity'])}          # giữ hàng ngay khi đặt
        if is_paid:
            upd["sold_count"] = gcf.Increment(ln['quantity'])
        tx.update(db.collection('products').document(ln['product_id']), upd)
        tx.set(_purchase_ref(order_ref.id, ln['product_id']), {
            "order_id": order_ref.id, "order_code": order["order_code"],
            "customer_id": customer_id, "product_id": ln['product_id'],
            "product_name": ln['name'], "brand": ln['brand'], "type": ln['type'],
            "quantity": ln['quantity'], "unit_price": ln['unit_price'], "line_total": ln['line_total'],
            "status": "paid" if is_paid else "pending",
            "can_review": False,                                  # chỉ true khi đơn hoàn tất & đã thanh toán
            "created_at": now, "paid_at": now if is_paid else None,
        })
    if coupon_ref is not None:
        tx.update(coupon_ref, {"used_count": gcf.Increment(1)})
    if user_ref is not None:
        upd = {}
        if pts:
            upd["points"] = gcf.Increment(-pts)
            _log_points(tx, customer_id, order, "redeem", -pts, "Dùng điểm khi thanh toán")
        if is_paid and total:
            upd["total_spent"] = gcf.Increment(total)
        if upd:
            tx.update(user_ref, upd)
    return order


@router.post("/checkout")
def checkout(req: CheckoutRequest, background: BackgroundTasks, user: Optional[dict] = Depends(optional_user)):
    req.customer_id = user['uid'] if user else GUEST_ID      # danh tính lấy từ token, không tin body
    if req.payment_method not in PAYMENT_METHODS:
        raise HTTPException(status_code=400, detail="Hình thức thanh toán không hợp lệ")
    if not req.shipping_address.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập địa chỉ giao hàng")
    merged = _merge_items(req.items)
    customer_id, user_ref, ident = _resolve_identity(req)
    pay_info = _build_payment_info(req)
    coupon_code = _clean_code(req.coupon_code)
    is_paid = req.payment_method in ("card", "banking")      # giả lập: thanh toán online = paid ngay

    order_ref = db.collection('orders').document()
    order = _checkout_tx(db.transaction(), req, merged, order_ref, user_ref, customer_id, ident,
                         pay_info, coupon_code, is_paid, _now())
    background.add_task(_notify, order, "paid" if is_paid else "cod_placed")
    return {"status": "success", "order": order}


# ---------------------------------------------------------------
# LỊCH SỬ & THEO DÕI ĐƠN CỦA KHÁCH
# ---------------------------------------------------------------
def _brief(o: dict) -> dict:
    return {"id": o['id'], "order_code": o['order_code'], "created_at": o.get('created_at'),
            "total": o['total'], "total_items": o.get('total_items'),
            "order_status": o['order_status'], "payment_status": o['payment_status'],
            "items": [{"product_id": i['product_id'], "name": i['name'], "img": i.get('img'),
                       "quantity": i['quantity']} for i in o['items'][:3]],
            "more_items": max(0, len(o['items']) - 3)}


def _orders_of(customer_id: str):
    docs = db.collection('orders').where('customer_id', '==', customer_id).stream()
    orders = [{"id": d.id, **d.to_dict()} for d in docs]
    orders.sort(key=lambda o: str(o.get('created_at', '')), reverse=True)
    return orders


@router.get("/my")
def my_orders(status: Optional[str] = None, user: dict = Depends(current_user)):
    orders = _orders_of(user['uid'])
    if status:
        orders = [o for o in orders if o.get('order_status') == status]
    return orders


@router.get("/my/summary")
def my_summary(user: dict = Depends(current_user)):
    customer_id = user['uid']
    """Số đếm cho các icon kiểu Shopee + danh sách tóm tắt để hiện popup khi bấm vào icon."""
    orders = _orders_of(customer_id)
    groups = {s: [_brief(o) for o in orders if o.get('order_status') == s]
              for s in ("pending_confirm", "preparing", "shipping")}

    reviewed = {d.to_dict().get('product_id')
                for d in db.collection('reviews').where('customer_id', '==', customer_id).stream()}
    to_review = []
    for o in orders:
        if o.get('order_status') == 'completed' and o.get('payment_status') == 'paid':
            for i in o['items']:
                if i['product_id'] not in reviewed:
                    to_review.append({"order_id": o['id'], "order_code": o['order_code'],
                                      "product_id": i['product_id'], "name": i['name'],
                                      "img": i.get('img'), "created_at": o.get('created_at')})
    counts = {s: len(v) for s, v in groups.items()}
    counts["to_review"] = len(to_review)
    return {"counts": counts, "orders": groups, "to_review": to_review}


# ---------------------------------------------------------------
# ADMIN
# ---------------------------------------------------------------
@router.get("/admin/all")
def admin_list_orders(payment_status: Optional[str] = None, order_status: Optional[str] = None,
                      limit: int = 200, admin_uid: str = Depends(staff_uid)):
    q = db.collection('orders')
    if payment_status:
        q = q.where('payment_status', '==', payment_status)
    orders = [{"id": d.id, **d.to_dict()} for d in q.stream()]
    if order_status:
        orders = [o for o in orders if o.get('order_status') == order_status]
    orders.sort(key=lambda o: str(o.get('created_at', '')), reverse=True)
    return orders[:limit]


@router.get("/admin/summary")
def admin_summary(admin_uid: str = Depends(staff_uid)):
    """Doanh thu thực thu (sau giảm giá & điểm), chỉ tính đơn đã thanh toán."""
    revenue = discount = points_used = units = n = 0
    by_product, by_day, by_method = {}, {}, {}
    for d in db.collection('orders').where('payment_status', '==', 'paid').stream():
        o = d.to_dict()
        n += 1
        revenue += o['total']
        discount += o.get('discount', 0)
        points_used += o.get('points_used', 0)
        units += o.get('total_items', 0)
        by_method[o['payment_method']] = by_method.get(o['payment_method'], 0) + o['total']
        day = str(o.get('paid_at') or o.get('created_at'))[:10]
        by_day[day] = by_day.get(day, 0) + o['total']
        for i in o['items']:
            bp = by_product.setdefault(i['product_id'], {"product_id": i['product_id'], "name": i['name'],
                                                          "quantity": 0, "revenue": 0})
            bp['quantity'] += i['quantity']
            bp['revenue'] += i['line_total']
    top = sorted(by_product.values(), key=lambda x: x['quantity'], reverse=True)[:10]
    return {"revenue": revenue, "paid_orders": n, "units_sold": units,
            "total_discount": discount, "total_points_used": points_used,
            "revenue_by_method": by_method, "revenue_by_day": dict(sorted(by_day.items())),
            "top_products": top}


# ---------- đổi trạng thái: chỉ đi tiến từng bước ----------
@gcf.transactional
def _status_tx(tx, order_ref, new_status, now):
    snap = order_ref.get(transaction=tx)
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
    o = {"id": order_ref.id, **snap.to_dict()}
    cur = o['order_status']
    if cur not in FLOW or FLOW.index(new_status) != FLOW.index(cur) + 1:
        raise HTTPException(status_code=400, detail="Chỉ được chuyển sang bước kế tiếp của đơn hàng")

    upd = {"order_status": new_status,
           "status_history": list(o.get('status_history', [])) + [{"status": new_status, "at": now}]}
    guest = o.get('customer_id') in (None, GUEST_ID)

    if new_status == "completed":
        newly_paid = o['payment_status'] == 'pending'     # COD: giao xong = đã thu tiền
        if newly_paid:
            upd.update({"payment_status": "paid", "paid_at": now})
            for it in o['items']:
                tx.update(db.collection('products').document(it['product_id']),
                          {"sold_count": gcf.Increment(it['quantity'])})
            if not guest and o['total']:
                tx.update(db.collection('users').document(o['customer_id']),
                          {"total_spent": gcf.Increment(o['total'])})
        for it in o['items']:                             # mở quyền đánh giá
            p = {"can_review": True}
            if newly_paid:
                p.update({"status": "paid", "paid_at": now})
            tx.update(_purchase_ref(order_ref.id, it['product_id']), p)
        if not guest and not o.get('points_awarded'):
            earned = int(o['total'] * EARN_RATE)
            upd.update({"points_earned": earned, "points_awarded": True})
            if earned > 0:
                tx.update(db.collection('users').document(o['customer_id']),
                          {"points": gcf.Increment(earned)})
                _log_points(tx, o['customer_id'], o, "earn", earned, "Thưởng 1% giá trị đơn hàng hoàn tất")
    tx.update(order_ref, upd)
    return {**o, **upd}


@router.patch("/{order_id}/status")
def update_order_status(order_id: str, status: str, background: BackgroundTasks, admin_uid: str = Depends(staff_uid)):
    if status not in FLOW[1:]:
        raise HTTPException(status_code=400, detail="Trạng thái không hợp lệ")
    o = _status_tx(db.transaction(), db.collection('orders').document(order_id), status, _now())
    if status == "completed":
        background.add_task(_notify, o, "completed")
    return {"status": "success", "order_status": status, "points_earned": o.get('points_earned', 0)}


# ---------- xác nhận đã thu tiền (COD) trước khi giao xong ----------
@gcf.transactional
def _confirm_tx(tx, order_ref, now):
    snap = order_ref.get(transaction=tx)
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
    o = {"id": order_ref.id, **snap.to_dict()}
    if o['payment_status'] != 'pending' or o['order_status'] == 'cancelled':
        raise HTTPException(status_code=400, detail="Đơn hàng không ở trạng thái chờ thanh toán")
    upd = {"payment_status": "paid", "paid_at": now}
    tx.update(order_ref, upd)
    for it in o['items']:
        tx.update(_purchase_ref(order_ref.id, it['product_id']), {"status": "paid", "paid_at": now})
        tx.update(db.collection('products').document(it['product_id']),
                  {"sold_count": gcf.Increment(it['quantity'])})
    if o.get('customer_id') not in (None, GUEST_ID) and o['total']:
        tx.update(db.collection('users').document(o['customer_id']),
                  {"total_spent": gcf.Increment(o['total'])})
    return {**o, **upd}


@router.patch("/{order_id}/confirm-payment")
def confirm_payment(order_id: str, background: BackgroundTasks, admin_uid: str = Depends(staff_uid)):
    o = _confirm_tx(db.transaction(), db.collection('orders').document(order_id), _now())
    background.add_task(_notify, o, "cod_paid")
    return {"status": "success"}


# ---------- huỷ đơn: hoàn kho, hoàn mã, hoàn điểm, đảo doanh thu nếu đã thanh toán ----------
@gcf.transactional
def _cancel_tx(tx, order_ref, by_customer_id, now):
    snap = order_ref.get(transaction=tx)
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
    o = {"id": order_ref.id, **snap.to_dict()}
    if by_customer_id is not None:
        if o.get('customer_id') != by_customer_id:
            raise HTTPException(status_code=403, detail="Bạn không có quyền huỷ đơn này")
        allowed = ("pending_confirm",)
    else:
        allowed = ("pending_confirm", "preparing")
    if o['order_status'] not in allowed:
        raise HTTPException(status_code=400, detail="Đơn hàng ở trạng thái này không thể huỷ")

    was_paid = o['payment_status'] == 'paid'
    tx.update(order_ref, {"payment_status": "refunded" if was_paid else "cancelled",
                          "order_status": "cancelled", "cancelled_at": now,
                          "status_history": list(o.get('status_history', [])) + [{"status": "cancelled", "at": now}]})
    for it in o['items']:
        tx.update(_purchase_ref(order_ref.id, it['product_id']), {"status": "cancelled", "can_review": False})
        upd = {"stock": gcf.Increment(it['quantity'])}
        if was_paid:
            upd["sold_count"] = gcf.Increment(-it['quantity'])
        tx.update(db.collection('products').document(it['product_id']), upd)
    if o.get('coupon_code'):
        tx.update(db.collection('coupons').document(o['coupon_code']), {"used_count": gcf.Increment(-1)})
    if o.get('customer_id') not in (None, GUEST_ID):
        upd = {}
        if o.get('points_used'):
            upd["points"] = gcf.Increment(o['points_used'])
            _log_points(tx, o['customer_id'], o, "refund", o['points_used'], "Hoàn điểm do huỷ đơn")
        if was_paid and o['total']:
            upd["total_spent"] = gcf.Increment(-o['total'])
        if upd:
            tx.update(db.collection('users').document(o['customer_id']), upd)


@router.patch("/{order_id}/cancel")
def cancel_order(order_id: str, admin_uid: str = Depends(staff_uid)):
    _cancel_tx(db.transaction(), db.collection('orders').document(order_id), None, _now())
    return {"status": "success"}


@router.patch("/{order_id}/cancel-by-customer")
def cancel_by_customer(order_id: str, user: dict = Depends(current_user)):
    _cancel_tx(db.transaction(), db.collection('orders').document(order_id), user['uid'], _now())
    return {"status": "success"}