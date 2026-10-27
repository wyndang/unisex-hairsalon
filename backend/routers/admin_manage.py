# backend/routers/admin_manage.py
# Quản trị: thống kê, booking (hoàn tất / huỷ + giải phóng lịch / ảnh trước-sau), thông báo cho staff,
# CRUD Dịch vụ - Sản phẩm - Nhân viên (Stylist) - Tài khoản, lịch sử booking của khách.
#
# Phân quyền:  owner = toàn quyền | staff = xem/xử lý booking, thông báo
import re
import uuid
import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from google.cloud import firestore as gcf
from database import db
from auth import current_user, staff_uid
from security import hash_password, normalize_phone, is_valid_phone, is_valid_email
from email_utils import send_email, money, vn_time, e

router = APIRouter(prefix="/api/manage", tags=["Admin Management"])
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))
ACTIVE_BOOKING = ("confirmed", "pending_payment", "paid")
HHMM = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _today() -> str:
    return datetime.datetime.now(VN_TZ).strftime("%Y-%m-%d")


def _day(x) -> str:
    if not x:
        return ""
    if isinstance(x, str):
        try:
            x = datetime.datetime.fromisoformat(x)
        except ValueError:
            return x[:10]
    if x.tzinfo is None:
        x = x.replace(tzinfo=datetime.timezone.utc)
    return x.astimezone(VN_TZ).strftime("%Y-%m-%d")


def owner_uid(user: dict = Depends(current_user)) -> str:
    snap = db.collection('users').document(user['uid']).get()
    if not snap.exists or snap.to_dict().get('role') != 'owner':
        raise HTTPException(status_code=403, detail="Chỉ quản trị viên (owner) mới được thực hiện thao tác này")
    return user['uid']


def _check_image(v: str):
    if v and v.startswith('data:'):
        if not v.startswith('data:image/') or len(v) > 400_000:
            raise HTTPException(status_code=400, detail="Ảnh tải lên không hợp lệ hoặc quá lớn (tối đa ~300KB)")


# =====================================================================
# THÔNG BÁO CHO STAFF / OWNER   (collection `notifications`, mỗi người nhận 1 doc)
# =====================================================================
def notify_staff(title: str, message: str, kind: str = "info", ref: Optional[dict] = None):
    """Gửi thông báo trong hệ thống tới TẤT CẢ tài khoản staff + owner.
    Có thể import & gọi ở nơi khác, vd booking_service.create_booking khi có lịch hẹn mới."""
    try:
        batch, n, now = db.batch(), 0, _now()
        for u in db.collection('users').where('role', 'in', ['staff', 'owner']).stream():
            batch.set(db.collection('notifications').document(), {
                "recipient_uid": u.id, "type": kind, "title": title, "message": message,
                "ref": ref or {}, "is_read": False, "created_at": now})
            n += 1
        if n:
            batch.commit()
    except Exception as ex:
        print("[WARN] notify_staff:", ex)


def _my_notifs(uid: str, role: str):
    out = []
    for d in db.collection('notifications').stream():
        n = d.to_dict()
        rec = n.get('recipient_uid')
        if rec == uid or (rec is None and role == 'owner'):   # thông báo cũ chưa có người nhận -> owner
            out.append({"id": d.id, **n})
    out.sort(key=lambda n: str(n.get('created_at', '')), reverse=True)
    return out


@router.get("/notifications")
def notifications(user: dict = Depends(current_user), uid: str = Depends(staff_uid)):
    return _my_notifs(uid, user.get('role'))[:100]


@router.post("/notifications/read-all")
def read_all(user: dict = Depends(current_user), uid: str = Depends(staff_uid)):
    for n in _my_notifs(uid, user.get('role')):
        if not n.get('is_read'):
            db.collection('notifications').document(n['id']).update({"is_read": True})
    return {"status": "success"}


@router.patch("/notifications/{nid}/read")
def read_one(nid: str, uid: str = Depends(staff_uid)):
    ref = db.collection('notifications').document(nid)
    if ref.get().exists:
        ref.update({"is_read": True})
    return {"status": "success"}


@router.get("/badges")
def badges(user: dict = Depends(current_user), uid: str = Depends(staff_uid)):
    pending_orders = sum(1 for _ in db.collection('orders').where('order_status', '==', 'pending_confirm').stream())
    today = _today()
    upcoming = sum(1 for d in db.collection('bookings').where('status', 'in', list(ACTIVE_BOOKING)).stream()
                   if (d.to_dict().get('date') or '') >= today)
    unread = sum(1 for n in _my_notifs(uid, user.get('role')) if not n.get('is_read'))
    return {"pending_orders": pending_orders, "upcoming_bookings": upcoming, "unread": unread}


# =====================================================================
# THỐNG KÊ DOANH THU
# =====================================================================
def compute_stats(orders: list, bookings: list, products: list, days: int, today: str) -> dict:
    today_d = datetime.date.fromisoformat(today)
    series = {(today_d - datetime.timedelta(days=i)).isoformat(): {"shop": 0, "service": 0} for i in range(days)}
    shop_rev = units = paid_orders = 0
    top_p, top_s, top_st = {}, {}, {}
    order_status = {}
    for o in orders:
        order_status[o.get('order_status', '?')] = order_status.get(o.get('order_status', '?'), 0) + 1
        if o.get('payment_status') != 'paid' or o.get('order_status') == 'cancelled':
            continue
        t = int(o.get('total', 0))
        shop_rev += t
        paid_orders += 1
        day = _day(o.get('paid_at') or o.get('created_at'))
        if day in series:
            series[day]["shop"] += t
        for it in o.get('items', []):
            q = int(it.get('quantity', 0))
            units += q
            p = top_p.setdefault(it.get('product_id', it.get('name')), {"name": it.get('name'), "quantity": 0, "revenue": 0})
            p["quantity"] += q
            p["revenue"] += int(it.get('line_total', 0))

    svc_rev = upcoming_value = 0
    b_status = {}
    for b in bookings:
        st = b.get('status', '?')
        b_status[st] = b_status.get(st, 0) + 1
        price = int(b.get('total_price', 0))
        if st == 'completed':
            svc_rev += price
            day = _day(b.get('completed_at')) or b.get('date', '')
            if day in series:
                series[day]["service"] += price
            s = top_s.setdefault(b.get('service_name'), {"name": b.get('service_name'), "count": 0, "revenue": 0})
            s["count"] += 1
            s["revenue"] += price
            t = top_st.setdefault(b.get('staff_name'), {"name": b.get('staff_name'), "count": 0, "revenue": 0})
            t["count"] += 1
            t["revenue"] += price
        elif st in ACTIVE_BOOKING and (b.get('date') or '') >= today:
            upcoming_value += price

    low = sorted([{"id": p.get('id'), "name": p.get('name'), "stock": int(p.get('stock', 0))}
                  for p in products if p.get('is_active', True) and int(p.get('stock', 0)) <= 5],
                 key=lambda x: x["stock"])[:10]
    by_day = [{"day": d, **v} for d, v in sorted(series.items())]
    return {
        "total_revenue": shop_rev + svc_rev, "shop_revenue": shop_rev, "service_revenue": svc_rev,
        "upcoming_value": upcoming_value, "units_sold": units, "paid_orders": paid_orders,
        "bookings_completed": b_status.get('completed', 0), "bookings_cancelled": b_status.get('cancelled', 0),
        "bookings_upcoming": sum(b_status.get(k, 0) for k in ACTIVE_BOOKING),
        "booking_status": b_status, "order_status": order_status,
        "period_total": sum(v["shop"] + v["service"] for v in series.values()), "days": days,
        "by_day": by_day,
        "top_products": sorted(top_p.values(), key=lambda x: x["quantity"], reverse=True)[:8],
        "top_services": sorted(top_s.values(), key=lambda x: x["count"], reverse=True)[:8],
        "top_stylists": sorted(top_st.values(), key=lambda x: x["count"], reverse=True)[:8],
        "low_stock": low,
    }


@router.get("/stats")
def stats(days: int = 30, _: str = Depends(owner_uid)):
    days = max(1, min(days, 365))
    orders = [d.to_dict() for d in db.collection('orders').stream()]
    bookings = [d.to_dict() for d in db.collection('bookings').stream()]
    products = [{"id": d.id, **d.to_dict()} for d in db.collection('products').stream()]
    res = compute_stats(orders, bookings, products, days, _today())
    res["customers_total"] = sum(1 for _ in db.collection('users').where('role', '==', 'customer').stream())
    return res


# =====================================================================
# BOOKING
# =====================================================================
class BookingStatusReq(BaseModel):
    status: str                                 # completed | cancelled
    result_note: Optional[str] = None
    services_done: Optional[List[str]] = None
    reason: Optional[str] = None


class NoteReq(BaseModel):
    result_note: str = ""
    services_done: Optional[List[str]] = None


class PhotoReq(BaseModel):
    data_url: str
    phase: str = "after"                        # before | after
    caption: str = ""


def _booking_view(d, doc_id=None):
    b = dict(d)
    b["id"] = doc_id or d.get("id")
    return b


@router.get("/bookings")
def list_bookings(status: Optional[str] = None, date: Optional[str] = None, _: str = Depends(staff_uid)):
    out = []
    for d in db.collection('bookings').stream():
        b = d.to_dict()
        if status and b.get('status') != status:
            continue
        if date and b.get('date') != date:
            continue
        out.append(_booking_view(b, d.id))
    out.sort(key=lambda b: (b.get('date', ''), b.get('time', '')), reverse=True)
    return out[:300]


def _photos(bref):
    ph = [{"id": p.id, **p.to_dict()} for p in bref.collection('photos').stream()]
    ph.sort(key=lambda p: str(p.get('created_at', '')))
    return ph


@router.get("/bookings/{bid}")
def booking_detail(bid: str, _: str = Depends(staff_uid)):
    bref = db.collection('bookings').document(bid)
    snap = bref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn")
    return {**_booking_view(snap.to_dict(), bid), "photos": _photos(bref)}


@router.patch("/bookings/{bid}/note")
def booking_note(bid: str, req: NoteReq, _: str = Depends(staff_uid)):
    bref = db.collection('bookings').document(bid)
    if not bref.get().exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn")
    upd = {"result_note": req.result_note.strip()[:1000]}
    if req.services_done is not None:
        upd["services_done"] = [s.strip()[:120] for s in req.services_done if s.strip()][:20]
    bref.update(upd)
    return {"status": "success"}


@router.post("/bookings/{bid}/photos")
def add_photo(bid: str, req: PhotoReq, _: str = Depends(staff_uid)):
    bref = db.collection('bookings').document(bid)
    if not bref.get().exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn")
    if req.phase not in ("before", "after"):
        raise HTTPException(status_code=400, detail="phase phải là before hoặc after")
    if not req.data_url.startswith("data:image/") or len(req.data_url) > 900_000:
        raise HTTPException(status_code=400, detail="Ảnh không hợp lệ hoặc quá lớn")
    if sum(1 for _p in bref.collection('photos').select([]).stream()) >= 16:
        raise HTTPException(status_code=400, detail="Mỗi lịch hẹn tối đa 16 ảnh")
    ref = bref.collection('photos').document()
    ref.set({"data_url": req.data_url, "phase": req.phase, "caption": req.caption[:120], "created_at": _now()})
    return {"status": "success", "id": ref.id}


@router.delete("/bookings/{bid}/photos/{pid}")
def del_photo(bid: str, pid: str, _: str = Depends(staff_uid)):
    db.collection('bookings').document(bid).collection('photos').document(pid).delete()
    return {"status": "success"}


@gcf.transactional
def _complete_tx(tx, bref, uref, now, by, note, services):
    snap = bref.get(transaction=tx)
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn")
    d = snap.to_dict()
    if d.get('status') not in ('confirmed', 'paid'):
        raise HTTPException(status_code=400, detail=f"Chỉ hoàn tất được lịch hẹn đã xác nhận hoặc đã trả trước (hiện tại: {d.get('status')})")
    user_snap = uref.get(transaction=tx) if uref is not None else None
    upd = {"status": "completed", "completed_at": now, "completed_by": by, "in_history": True,
           "payment_collected": True,
           "services_done": services or [f"{d.get('service_name')} ({d.get('tier_name')})"]}
    if note is not None:
        upd["result_note"] = note
    tx.update(bref, upd)
    if user_snap is not None and user_snap.exists:
        tx.update(uref, {"total_spent": gcf.Increment(int(d.get('total_price', 0)))})
    return {**d, **upd}


@gcf.transactional
def _cancel_tx(tx, bref, sref, now, by, reason):
    snap = bref.get(transaction=tx)
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn")
    d = snap.to_dict()
    if d.get('status') not in ACTIVE_BOOKING:
        raise HTTPException(status_code=400, detail=f"Không thể huỷ lịch hẹn ở trạng thái '{d.get('status')}'")
    sched = sref.get(transaction=tx)
    if sched.exists:   # GIẢI PHÓNG khung giờ của nhân viên
        slots = [s for s in (sched.to_dict().get('bookings') or []) if s.get('booking_id') != bref.id]
        tx.set(sref, {"bookings": slots}, merge=True)
    upd = {"status": "cancelled", "cancelled_at": now, "cancelled_by": by, "cancel_reason": reason,
           "in_history": False, "refund_needed": d.get('status') == 'paid'}
    tx.update(bref, upd)
    return {**d, **upd}


def _booking_mail(b: dict, kind: str) -> str:
    when = f"{e(b.get('time', ''))} - {e(b.get('end_time', ''))}, ngày {e(b.get('date', ''))}"
    rows = (f"<li><strong>Dịch vụ:</strong> {e(b.get('service_name', ''))} ({e(b.get('tier_name', ''))})</li>"
            f"<li><strong>Stylist:</strong> {e(b.get('staff_name', ''))}</li>"
            f"<li><strong>Thời gian:</strong> {when}</li>"
            f"<li><strong>Số tiền:</strong> {money(b.get('total_price', 0))}</li>")
    if kind == "completed":
        done = "".join(f"<li>{e(x)}</li>" for x in b.get('services_done', []))
        note = f"<p><strong>Ghi chú của stylist:</strong> {e(b['result_note'])}</p>" if b.get('result_note') else ""
        return f"""<div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;padding:20px;border:1px solid #2ecc71;border-radius:8px;">
            <h2 style="color:#2ecc71;margin-top:0;">Cảm ơn bạn đã sử dụng dịch vụ - UNISEX Salon</h2>
            <p>Xin chào <strong>{e(b.get('customer_name', ''))}</strong>, lịch hẹn của bạn đã hoàn tất:</p>
            <ul style="line-height:1.8">{rows}</ul>
            <p><strong>Những gì đã thực hiện:</strong></p><ul>{done}</ul>{note}
            <p>Bạn có thể xem lại chi tiết và hình ảnh trước/sau khi làm trong <strong>Trang cá nhân &gt; Lịch sử booking</strong>.</p></div>"""
    reason = f"<p><strong>Lý do:</strong> {e(b.get('cancel_reason') or 'Lịch hẹn không được thực hiện')}</p>"
    refund = ("<p>Bạn đã thanh toán trước: cửa hàng sẽ liên hệ để hoàn tiền cho bạn.</p>" if b.get('refund_needed') else "")
    return f"""<div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;padding:20px;border:1px solid #e74c3c;border-radius:8px;">
        <h2 style="color:#e74c3c;margin-top:0;">Lịch hẹn đã được huỷ - UNISEX Salon</h2>
        <p>Xin chào <strong>{e(b.get('customer_name', ''))}</strong>, lịch hẹn sau đã được huỷ:</p>
        <ul style="line-height:1.8">{rows}</ul>{reason}{refund}
        <p>Bạn có thể đặt lại lịch bất cứ lúc nào trên website. Cảm ơn bạn!</p></div>"""


@router.patch("/bookings/{bid}/status")
def booking_status(bid: str, req: BookingStatusReq, bg: BackgroundTasks, uid: str = Depends(staff_uid)):
    if req.status not in ("completed", "cancelled"):
        raise HTTPException(status_code=400, detail="Trạng thái chỉ có thể là completed hoặc cancelled")
    bref = db.collection('bookings').document(bid)
    snap = bref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn")
    d = snap.to_dict()
    cid = d.get('customer_id')
    uref = db.collection('users').document(cid) if cid and cid != 'guest' else None
    now = _now()

    if req.status == "completed":
        note = req.result_note.strip()[:1000] if req.result_note is not None else None
        services = [s.strip()[:120] for s in (req.services_done or []) if s.strip()][:20]
        b = _complete_tx(db.transaction(), bref, uref, now, uid, note, services)
        subject = "[UNISEX Salon] Cảm ơn bạn đã sử dụng dịch vụ"
        notify_staff("Booking đã hoàn tất",
                     f"{b.get('customer_name')} · {b.get('service_name')} · {b.get('date')} {b.get('time')} · Stylist {b.get('staff_name')}",
                     "booking_completed", {"booking_id": bid})
    else:
        sref = db.collection('daily_schedules').document(f"{d.get('staff_id')}_{d.get('date')}")
        b = _cancel_tx(db.transaction(), bref, sref, now, uid, (req.reason or "").strip()[:300])
        subject = "[UNISEX Salon] Lịch hẹn của bạn đã được huỷ"
        try:   # vô hiệu hoá OTP thanh toán còn treo (nếu có)
            db.collection('otp_transactions').document(bid).update({"is_used": True})
        except Exception:
            pass
        notify_staff("Booking đã huỷ - lịch được giải phóng",
                     f"{b.get('customer_name')} · {b.get('service_name')} · {b.get('date')} {b.get('time')} · Stylist {b.get('staff_name')}",
                     "booking_cancelled", {"booking_id": bid})
    if b.get('customer_email'):
        bg.add_task(send_email, b['customer_email'], subject, _booking_mail(b, req.status))
    return {"status": "success", "booking_status": req.status}


# --------- Khách hàng xem lại booking (CHỈ booking đã được admin xác nhận hoàn tất mới thành lịch sử) ---------
@router.get("/my/bookings")
def my_bookings(user: dict = Depends(current_user)):
    upcoming, history = [], []
    for d in db.collection('bookings').where('customer_id', '==', user['uid']).stream():
        b = _booking_view(d.to_dict(), d.id)
        if b.get('status') == 'completed':
            b["photo_count"] = sum(1 for _p in d.reference.collection('photos').select([]).stream())
            history.append(b)
        elif b.get('status') in ACTIVE_BOOKING:
            upcoming.append(b)
        # booking đã huỷ KHÔNG hiện trong lịch sử
    upcoming.sort(key=lambda b: (b.get('date', ''), b.get('time', '')))
    history.sort(key=lambda b: str(b.get('completed_at', '')), reverse=True)
    return {"upcoming": upcoming, "history": history}


@router.get("/my/bookings/{bid}")
def my_booking_detail(bid: str, user: dict = Depends(current_user)):
    bref = db.collection('bookings').document(bid)
    snap = bref.get()
    if not snap.exists or snap.to_dict().get('customer_id') != user['uid'] or snap.to_dict().get('status') != 'completed':
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch sử booking")
    ph = _photos(bref)
    return {**_booking_view(snap.to_dict(), bid),
            "before": [p for p in ph if p.get('phase') == 'before'],
            "after": [p for p in ph if p.get('phase') != 'before']}


# =====================================================================
# NHÂN VIÊN (Stylist)  - collection `staffs`
# =====================================================================
class StaffIn(BaseModel):
    name: str
    specialty: str = ""
    exp_years: int = 0
    avatar: str = ""
    work_start: str = "08:00"
    work_end: str = "18:00"
    is_active: bool = True


def _has_upcoming(field: str, value: str) -> bool:
    today = _today()
    for d in db.collection('bookings').where(field, '==', value).stream():
        b = d.to_dict()
        if b.get('status') in ACTIVE_BOOKING and (b.get('date') or '') >= today:
            return True
    return False


def _staff_data(req: StaffIn) -> dict:
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập tên nhân viên")
    if not (HHMM.match(req.work_start) and HHMM.match(req.work_end) and req.work_start < req.work_end):
        raise HTTPException(status_code=400, detail="Giờ làm việc không hợp lệ (HH:MM, giờ bắt đầu < giờ kết thúc)")
    _check_image(req.avatar)
    return {"name": req.name.strip(), "specialty": req.specialty.strip(), "exp_years": max(0, req.exp_years),
            "avatar": req.avatar, "work_start": req.work_start, "work_end": req.work_end, "is_active": req.is_active}


@router.get("/staffs")
def staffs_all(_: str = Depends(staff_uid)):
    out = [{"id": d.id, **d.to_dict()} for d in db.collection('staffs').stream()]
    return sorted(out, key=lambda s: s['id'])


@router.post("/staffs")
def staffs_create(req: StaffIn, _: str = Depends(owner_uid)):
    sid = "staff_" + uuid.uuid4().hex[:6]
    db.collection('staffs').document(sid).set({"id": sid, **_staff_data(req)})
    return {"status": "success", "id": sid}


@router.put("/staffs/{sid}")
def staffs_update(sid: str, req: StaffIn, _: str = Depends(owner_uid)):
    ref = db.collection('staffs').document(sid)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên")
    data = _staff_data(req)
    if not data["is_active"] and _has_upcoming('staff_id', sid):
        raise HTTPException(status_code=409, detail="Nhân viên còn lịch hẹn sắp tới, hãy huỷ/chuyển lịch trước khi ngừng hoạt động")
    ref.update(data)
    return {"status": "success"}


@router.delete("/staffs/{sid}")
def staffs_delete(sid: str, _: str = Depends(owner_uid)):
    if _has_upcoming('staff_id', sid):
        raise HTTPException(status_code=409, detail="Nhân viên còn lịch hẹn sắp tới, không thể xoá. Hãy huỷ lịch hoặc chỉ ngừng hoạt động")
    db.collection('staffs').document(sid).delete()
    return {"status": "success"}


# =====================================================================
# TÀI KHOẢN NGƯỜI DÙNG  - collection `users`
# =====================================================================
class UserIn(BaseModel):
    full_name: str
    phone: str
    email: str
    role: str = "customer"                      # customer | staff | owner
    password: Optional[str] = None
    points: Optional[int] = None


def _public_user(d):
    u = d.to_dict()
    u.pop('password_hash', None)
    u.pop('password', None)
    return {"id": d.id, **u}


def _dupe(field: str, value: str, exclude_uid: Optional[str] = None):
    for d in db.collection('users').where(field, '==', value).stream():
        if d.id != exclude_uid:
            return True
    return False


def _user_fields(req: UserIn, exclude_uid: Optional[str] = None) -> dict:
    name, phone, email = req.full_name.strip(), normalize_phone(req.phone), req.email.strip().lower()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Vui lòng nhập họ tên")
    if not is_valid_phone(phone):
        raise HTTPException(status_code=400, detail="Số điện thoại không hợp lệ (10 số, bắt đầu bằng 0)")
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="Email không hợp lệ")
    if req.role not in ("customer", "staff", "owner"):
        raise HTTPException(status_code=400, detail="Vai trò không hợp lệ")
    if _dupe('phone', phone, exclude_uid):
        raise HTTPException(status_code=409, detail="Số điện thoại đã được sử dụng")
    if _dupe('email', email, exclude_uid):
        raise HTTPException(status_code=409, detail="Email đã được sử dụng")
    return {"full_name": name, "phone": phone, "email": email, "role": req.role}


@router.get("/users")
def users_list(role: Optional[str] = None, q: Optional[str] = None, _: str = Depends(owner_uid)):
    out = []
    for d in db.collection('users').stream():
        u = _public_user(d)
        if role and u.get('role') != role:
            continue
        if q and q.lower() not in f"{u.get('full_name', '')} {u.get('phone', '')} {u.get('email', '')}".lower():
            continue
        out.append(u)
    out.sort(key=lambda u: str(u.get('created_at', '')), reverse=True)
    return out[:500]


@router.post("/users")
def users_create(req: UserIn, _: str = Depends(owner_uid)):
    data = _user_fields(req)
    if not req.password or len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Mật khẩu tối thiểu 6 ký tự")
    uid = {"staff": "staff_", "owner": "owner_"}.get(req.role, "user_") + uuid.uuid4().hex[:8]
    db.collection('users').document(uid).set({
        "uid": uid, **data, "password_hash": hash_password(req.password), "total_spent": 0,
        "points": max(0, req.points or 0), "avatar_url": "", "created_at": _now()})
    return {"status": "success", "uid": uid}


@router.put("/users/{uid}")
def users_update(uid: str, req: UserIn, me: str = Depends(owner_uid)):
    ref = db.collection('users').document(uid)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
    data = _user_fields(req, uid)
    if uid == me and data["role"] != "owner":
        raise HTTPException(status_code=400, detail="Không thể tự hạ quyền tài khoản quản trị của chính bạn")
    if snap.to_dict().get('role') == 'owner' and data["role"] != 'owner':
        if sum(1 for _o in db.collection('users').where('role', '==', 'owner').stream()) <= 1:
            raise HTTPException(status_code=400, detail="Hệ thống phải còn ít nhất 1 tài khoản quản trị")
    if req.password:
        if len(req.password) < 6:
            raise HTTPException(status_code=400, detail="Mật khẩu tối thiểu 6 ký tự")
        data["password_hash"] = hash_password(req.password)
        data["password"] = gcf.DELETE_FIELD
    if req.points is not None:
        data["points"] = max(0, req.points)
    ref.update(data)
    return {"status": "success"}


@router.delete("/users/{uid}")
def users_delete(uid: str, me: str = Depends(owner_uid)):
    if uid == me:
        raise HTTPException(status_code=400, detail="Không thể xoá chính tài khoản đang đăng nhập")
    ref = db.collection('users').document(uid)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
    if snap.to_dict().get('role') == 'owner' and sum(1 for _o in db.collection('users').where('role', '==', 'owner').stream()) <= 1:
        raise HTTPException(status_code=400, detail="Không thể xoá tài khoản quản trị cuối cùng")
    ref.delete()   # đơn hàng / booking cũ vẫn giữ nguyên để đối soát doanh thu
    return {"status": "success"}


# =====================================================================
# SẢN PHẨM  - collection `products`
# =====================================================================
class ProductIn(BaseModel):
    name: str
    type: str
    brand: str
    volume: str = ""
    price: int
    stock: int = 0
    origin: str = ""
    desc: str = ""
    usage: str = ""
    img: str = ""
    images: List[str] = []
    is_active: bool = True


def _product_data(req: ProductIn) -> dict:
    if not req.name.strip() or not req.type.strip() or not req.brand.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập tên, loại và thương hiệu")
    if req.price <= 0 or req.stock < 0:
        raise HTTPException(status_code=400, detail="Giá phải > 0 và tồn kho không âm")
    for u in [req.img, *req.images]:
        _check_image(u)
    imgs = [u for u in req.images if u] or ([req.img] if req.img else [])
    return {"name": req.name.strip(), "type": req.type.strip(), "brand": req.brand.strip(), "volume": req.volume.strip(),
            "price": req.price, "stock": req.stock, "origin": req.origin.strip(), "desc": req.desc.strip(),
            "usage": req.usage.strip(), "img": req.img or (imgs[0] if imgs else ""), "images": imgs,
            "is_active": req.is_active}


@router.get("/products")
def products_all(_: str = Depends(owner_uid)):
    out = [{"id": d.id, **d.to_dict()} for d in db.collection('products').stream()]
    return sorted(out, key=lambda p: (p.get('type', ''), p.get('name', '')))


@router.post("/products")
def products_create(req: ProductIn, _: str = Depends(owner_uid)):
    pid = "prod_" + uuid.uuid4().hex[:8]
    db.collection('products').document(pid).set({
        "id": pid, **_product_data(req), "sold_count": 0, "rating_sum": 0, "rating_count": 0, "rating_avg": 0,
        "created_at": _now()})
    return {"status": "success", "id": pid}


@router.put("/products/{pid}")
def products_update(pid: str, req: ProductIn, _: str = Depends(owner_uid)):
    ref = db.collection('products').document(pid)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    ref.update(_product_data(req))      # giữ nguyên sold_count / rating
    return {"status": "success"}


@router.delete("/products/{pid}")
def products_delete(pid: str, _: str = Depends(owner_uid)):
    ref = db.collection('products').document(pid)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    ref.delete()                         # đơn hàng cũ đã lưu sẵn tên/giá nên không ảnh hưởng
    return {"status": "success"}


# =====================================================================
# DỊCH VỤ  - collection `services` (mỗi dịch vụ có 3 gói giá)
# =====================================================================
class TierIn(BaseModel):
    tier_id: str
    tier_name: str
    product_line: str = ""
    price: int
    pros: str = ""
    cons: str = ""


class ServiceIn(BaseModel):
    name: str
    category: str
    price: int
    duration_minutes: int
    desc: str = ""
    img_url: str = ""
    tiers: List[TierIn] = []
    is_active: bool = True


DEFAULT_TIERS = [("basic", "Gói Tiêu Chuẩn", 1.0), ("premium", "Gói Cao Cấp", 1.4), ("luxury", "Gói Thượng Hạng", 1.9)]


def _service_data(req: ServiceIn) -> dict:
    if not req.name.strip() or not req.category.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập tên và nhóm dịch vụ")
    if req.price <= 0 or req.duration_minutes < 10 or req.duration_minutes > 600:
        raise HTTPException(status_code=400, detail="Giá phải > 0 và thời lượng từ 10 đến 600 phút")
    _check_image(req.img_url)
    tiers = [t.dict() for t in req.tiers if t.tier_name.strip()]
    if not tiers:
        tiers = [{"tier_id": i, "tier_name": n, "product_line": "", "price": int(req.price * m), "pros": "", "cons": ""}
                 for i, n, m in DEFAULT_TIERS]
    ids = [t["tier_id"] for t in tiers]
    if len(set(ids)) != len(ids) or any(t["price"] <= 0 for t in tiers):
        raise HTTPException(status_code=400, detail="Các gói phải có mã khác nhau và giá > 0")
    return {"name": req.name.strip(), "category": req.category.strip(), "price": req.price,
            "duration_minutes": req.duration_minutes, "desc": req.desc.strip(), "img_url": req.img_url,
            "tiers": tiers, "is_active": req.is_active}


@router.get("/services")
def services_all(_: str = Depends(owner_uid)):
    out = [{"id": d.id, **d.to_dict()} for d in db.collection('services').stream()]
    return sorted(out, key=lambda s: (s.get('category', ''), s.get('name', '')))


@router.post("/services")
def services_create(req: ServiceIn, _: str = Depends(owner_uid)):
    sid = "svc_" + uuid.uuid4().hex[:8]
    db.collection('services').document(sid).set({"id": sid, **_service_data(req)})
    return {"status": "success", "id": sid}


@router.put("/services/{sid}")
def services_update(sid: str, req: ServiceIn, _: str = Depends(owner_uid)):
    ref = db.collection('services').document(sid)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy dịch vụ")
    data = _service_data(req)
    if not data["is_active"] and _has_upcoming('service_id', sid):
        raise HTTPException(status_code=409, detail="Dịch vụ còn lịch hẹn sắp tới, chưa thể ngừng cung cấp")
    ref.update(data)
    return {"status": "success"}


@router.delete("/services/{sid}")
def services_delete(sid: str, _: str = Depends(owner_uid)):
    if _has_upcoming('service_id', sid):
        raise HTTPException(status_code=409, detail="Dịch vụ còn lịch hẹn sắp tới, không thể xoá")
    db.collection('services').document(sid).delete()
    return {"status": "success"}