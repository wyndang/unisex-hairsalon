# backend/routers/booking_service.py
import random
import datetime
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from database import db
from google.cloud import firestore as gcf
from auth import current_user, staff_uid, optional_user
from firebase_admin import firestore
from dotenv import load_dotenv
from email_utils import send_email
from routers.admin_manage import notify_staff        # thêm ở đầu file
load_dotenv()
router = APIRouter(prefix="/api/booking", tags=["Booking Service"])



class BookingRequest(BaseModel):
    customer_id: str
    customer_name: str
    customer_email: str
    customer_phone: str
    staff_id: str
    staff_name: str
    service_id: str
    service_name: str
    tier_id: str
    tier_name: str
    date: str
    time: str
    duration: int
    total_price: int
    note: Optional[str] = ""
    payment_method: str # 'pay_later' hoặc 'pay_now'

class OTPVerifyRequest(BaseModel):
    booking_id: str
    otp_code: str

def time_to_minutes(time_str: str) -> int:
    h, m = map(int, time_str.split(':'))
    return h * 60 + m

def minutes_to_time(mins: int) -> str:
    return f"{mins // 60:02d}:{mins % 60:02d}"

@firestore.transactional
def process_booking_and_lock(transaction, schedule_ref, booking_ref, data, start_mins, end_mins):
    snapshot = schedule_ref.get(transaction=transaction)
    booked_slots = snapshot.get("bookings") if snapshot.exists else []

    # Kiểm tra giao nhau: [start_mins, end_mins] với các ca đã đặt
    for slot in booked_slots:
        if start_mins < slot["end"] and end_mins > slot["start"]:
            raise Exception(f"Nhân viên đã bận khung giờ {minutes_to_time(slot['start'])} - {minutes_to_time(slot['end'])}. Vui lòng chọn giờ khác!")
    
    booked_slots.append({
        "start": start_mins,
        "end": end_mins,
        "booking_id": booking_ref.id
    })
    transaction.set(schedule_ref, {"bookings": booked_slots}, merge=True)
    transaction.set(booking_ref, data)

@router.post("/create")
def create_booking(req: BookingRequest, user: Optional[dict] = Depends(optional_user)):
    if user:
        req.customer_id = user['uid']      # danh tính lấy từ token, không tin dữ liệu client
    schedule_id = f"{req.staff_id}_{req.date}"
    schedule_ref = db.collection('daily_schedules').document(schedule_id)
    booking_ref = db.collection('bookings').document()
    
    start_mins = time_to_minutes(req.time)
    end_mins = start_mins + req.duration
    end_time_str = minutes_to_time(end_mins)
    
    data = req.dict()
    data['id'] = booking_ref.id
    data['end_time'] = end_time_str
    data['status'] = "confirmed" if req.payment_method == 'pay_later' else "pending_payment"
    data['created_at'] = datetime.datetime.utcnow().isoformat()
    data['payment_mode'] = 'prepaid' if req.payment_method == 'pay_now' else 'at_counter'
    data['paid'] = False            # true sau khi xác thực OTP thanh toán trước
    data['points_earned'] = 0
    data['points_awarded'] = False
    data['result_note'] = ''
    
    try:
        transaction = db.transaction()
        process_booking_and_lock(transaction, schedule_ref, booking_ref, data, start_mins, end_mins)

        notify_staff("Lịch hẹn mới",
                     f"{req.customer_name} · {req.service_name} · {req.date} {req.time} · Stylist {req.staff_name}",
                     "booking_new", {"booking_id": booking_ref.id})
        
        if req.payment_method == 'pay_later':
            email_html = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                <h2 style="color: #f5a623;">Xác Nhận Đặt Lịch Hẹn - UNISEX Salon</h2>
                <p>Xin chào <strong>{req.customer_name}</strong>,</p>
                <p>Lịch hẹn của bạn đã được hệ thống ghi nhận:</p>
                <ul>
                    <li><strong>Dịch vụ:</strong> {req.service_name}</li>
                    <li><strong>Gói sản phẩm:</strong> {req.tier_name}</li>
                    <li><strong>Stylist phụ trách:</strong> {req.staff_name}</li>
                    <li><strong>Thời gian:</strong> {req.time} - {end_time_str}, ngày {req.date} ({req.duration} phút)</li>
                    <li><strong>Tổng thanh toán:</strong> {req.total_price:,} VNĐ <i>(Thanh toán tại quầy)</i></li>
                </ul>
                <p>Cảm ơn bạn đã tin tưởng UNISEX Salon!</p>
            </div>
            """
            send_email(req.customer_email, "[UNISEX Salon] Xác nhận Lịch hẹn thành công", email_html)
            return {"status": "success", "message": "Đặt lịch thành công! Khung giờ đã được giữ cho bạn.", "booking_id": booking_ref.id, "action": "redirect"}
            
        else:
            otp_code = str(random.randint(100000, 999999))
            expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
            
            db.collection('otp_transactions').document(booking_ref.id).set({
                "booking_id": booking_ref.id,
                "otp_code": otp_code,
                "expires_at": expires_at.isoformat(),
                "is_used": False,
                "email_sent_to": req.customer_email,
                "booking_details": data
            })
            
            otp_html = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #f5a623; border-radius: 8px;">
                <h2 style="color: #f5a623;">Mã OTP Xác Thực Thanh Toán Dịch Vụ</h2>
                <p>Xin chào <strong>{req.customer_name}</strong>,</p>
                <p>Mã OTP để hoàn tất thanh toán của bạn là: <strong style="font-size: 26px; color: #d35400; letter-spacing: 3px;">{otp_code}</strong></p>
                <ul>
                    <li><strong>Dịch vụ:</strong> {req.service_name} ({req.tier_name})</li>
                    <li><strong>Stylist:</strong> {req.staff_name}</li>
                    <li><strong>Khung giờ giữ chỗ:</strong> {req.time} - {end_time_str}, ngày {req.date}</li>
                    <li><strong>Số tiền thanh toán:</strong> {req.total_price:,} VNĐ</li>
                </ul>
                <p><i>Mã có hiệu lực trong vòng 5 phút và chỉ sử dụng 1 lần.</i></p>
            </div>
            """
            send_email(req.customer_email, "[UNISEX Salon] Mã OTP Xác Thực Giao Dịch", otp_html)
            return {"status": "success", "message": "Vui lòng nhập OTP đã gửi qua email", "booking_id": booking_ref.id, "action": "require_otp"}

    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

@firestore.transactional
def process_otp_verification(transaction, otp_ref, booking_ref):
    otp_snap = otp_ref.get(transaction=transaction)
    if not otp_snap.exists:
        raise Exception("Giao dịch OTP không tồn tại.")
    if otp_snap.get("is_used"):
        raise Exception("Giao dịch đã được thanh toán trước đó (Chống thanh toán trùng lặp).")
    
    expires_at = datetime.datetime.fromisoformat(otp_snap.get("expires_at"))
    if datetime.datetime.utcnow() > expires_at:
        raise Exception("Mã OTP đã hết hạn (Quá 5 phút).")
    
    transaction.update(otp_ref, {"is_used": True})
    transaction.update(booking_ref, {"status": "paid", "paid": True, "paid_at": datetime.datetime.utcnow().isoformat()})
    return otp_snap.get("booking_details")

@router.post("/verify-otp")
def verify_otp(req: OTPVerifyRequest):
    otp_ref = db.collection('otp_transactions').document(req.booking_id)
    booking_ref = db.collection('bookings').document(req.booking_id)
    
    otp_doc = otp_ref.get()
    if not otp_doc.exists or otp_doc.get("otp_code") != req.otp_code:
        raise HTTPException(status_code=400, detail="Mã OTP không chính xác.")
    
    try:
        transaction = db.transaction()
        b_data = process_otp_verification(transaction, otp_ref, booking_ref)
        
        receipt_html = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #2ecc71; border-radius: 8px;">
            <h2 style="color: #2ecc71;">Biên Lai Thanh Toán Thành Công</h2>
            <p>Xin chào <strong>{b_data['customer_name']}</strong>,</p>
            <p>Cảm ơn bạn đã hoàn tất thanh toán trực tuyến tại UNISEX Salon:</p>
            <ul>
                <li><strong>Mã giao dịch:</strong> {req.booking_id}</li>
                <li><strong>Dịch vụ:</strong> {b_data['service_name']}</li>
                <li><strong>Dòng sản phẩm sử dụng:</strong> {b_data['tier_name']}</li>
                <li><strong>Stylist:</strong> {b_data['staff_name']}</li>
                <li><strong>Thời gian hẹn:</strong> {b_data['time']} - {b_data['end_time']}, ngày {b_data['date']}</li>
                <li><strong>Số tiền đã thanh toán:</strong> {b_data['total_price']:,} VNĐ</li>
            </ul>
        </div>
        """
        send_email(b_data['customer_email'], "[UNISEX Salon] Biên lai thanh toán điện tử", receipt_html)
        return {"status": "success", "message": "Xác thực và thanh toán thành công!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/available-slots")
def get_available_slots(staff_id: str, date: str):
    schedule_id = f"{staff_id}_{date}"
    doc = db.collection('daily_schedules').document(schedule_id).get()
    return {"booked_slots": doc.get("bookings") if doc.exists else []}


# =====================================================================
# LỊCH SỬ BOOKING, ẢNH KẾT QUẢ, ĐIỂM THƯỞNG
#  - Khách: xem booking + ảnh của mình. Chỉ admin/staff được sửa/upload.
#  - Điểm: 1% giá trị dịch vụ, CHỈ khi booking thanh toán trước (prepaid) và được đánh dấu hoàn thành.
# =====================================================================
IMG_RE = re.compile(r'^data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$')
BOOKING_EARN_RATE = 0.01


class PhotoUpload(BaseModel):
    data_url: str
    caption: str = ""


class NoteUpdate(BaseModel):
    result_note: str = ""


@router.get("/my")
def my_bookings(user: dict = Depends(current_user)):
    docs = db.collection('bookings').where('customer_id', '==', user['uid']).stream()
    rows = [{"id": d.id, **d.to_dict()} for d in docs]
    for r in rows:
        r.pop('customer_email', None)
    rows.sort(key=lambda r: (r.get('date', ''), r.get('time', '')), reverse=True)
    return rows


@router.get("/{booking_id}/photos")
def booking_photos(booking_id: str, user: dict = Depends(current_user)):
    snap = db.collection('bookings').document(booking_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn")
    if snap.to_dict().get('customer_id') != user['uid']:
        u = db.collection('users').document(user['uid']).get()
        if not u.exists or u.to_dict().get('role') not in ('owner', 'staff'):
            raise HTTPException(status_code=403, detail="Bạn không có quyền xem ảnh này")
    docs = db.collection('booking_photos').where('booking_id', '==', booking_id).stream()
    rows = [{"id": d.id, **d.to_dict()} for d in docs]
    rows.sort(key=lambda r: str(r.get('created_at', '')))
    return {"photos": rows, "result_note": snap.to_dict().get('result_note', '')}


@router.get("/admin/all")
def admin_bookings(status: Optional[str] = None, admin_uid: str = Depends(staff_uid)):
    rows = [{"id": d.id, **d.to_dict()} for d in db.collection('bookings').stream()]
    if status:
        rows = [r for r in rows if r.get('status') == status]
    rows.sort(key=lambda r: (r.get('date', ''), r.get('time', '')), reverse=True)
    return rows[:300]


@gcf.transactional
def _complete_tx(tx, ref, now_iso):
    snap = ref.get(transaction=tx)
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn")
    bk = {"id": ref.id, **snap.to_dict()}
    if bk['status'] in ('completed', 'cancelled'):
        raise HTTPException(status_code=400, detail="Lịch hẹn đã kết thúc")
    if bk['status'] == 'pending_payment':
        raise HTTPException(status_code=400, detail="Khách chưa xác thực thanh toán trước")
    cid = bk.get('customer_id')
    user_ref = db.collection('users').document(cid) if cid and cid != 'guest' else None
    user_exists = user_ref.get(transaction=tx).exists if user_ref else False

    upd = {"status": "completed", "completed_at": now_iso}
    if user_exists:
        uu = {"total_spent": gcf.Increment(int(bk['total_price']))}
        if bk.get('payment_mode') == 'prepaid' and bk.get('paid') and not bk.get('points_awarded'):
            earned = int(int(bk['total_price']) * BOOKING_EARN_RATE)
            upd.update({"points_earned": earned, "points_awarded": True})
            if earned > 0:
                uu["points"] = gcf.Increment(earned)
                tx.set(db.collection('point_transactions').document(), {
                    "user_id": cid, "booking_id": ref.id, "order_id": None, "order_code": None,
                    "type": "earn", "points": earned, "note": f"Thưởng 1% dịch vụ {bk['service_name']} (thanh toán trước)",
                    "created_at": datetime.datetime.now(datetime.timezone.utc)})
        tx.update(user_ref, uu)
    tx.update(ref, upd)
    return upd


@router.patch("/admin/{booking_id}/status")
def admin_set_booking_status(booking_id: str, status: str, admin_uid: str = Depends(staff_uid)):
    if status not in ("completed", "cancelled"):
        raise HTTPException(status_code=400, detail="Trạng thái không hợp lệ")
    ref = db.collection('bookings').document(booking_id)
    now_iso = datetime.datetime.utcnow().isoformat()
    if status == "completed":
        upd = _complete_tx(db.transaction(), ref, now_iso)
        return {"status": "success", "points_earned": upd.get("points_earned", 0)}
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn")
    bk = {"id": snap.id, **snap.to_dict()}
    if bk['status'] in ('completed', 'cancelled'):
        raise HTTPException(status_code=400, detail="Lịch hẹn đã kết thúc")
    ref.update({"status": "cancelled", "cancelled_at": now_iso})
    sref = db.collection('daily_schedules').document(f"{bk['staff_id']}_{bk['date']}")   # trả lại khung giờ
    s = sref.get()
    if s.exists:
        sref.set({"bookings": [x for x in (s.to_dict().get('bookings') or []) if x.get('booking_id') != booking_id]}, merge=True)
    return {"status": "success"}


@router.post("/admin/{booking_id}/photos")
def admin_add_photo(booking_id: str, req: PhotoUpload, admin_uid: str = Depends(staff_uid)):
    if not db.collection('bookings').document(booking_id).get().exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn")
    if len(req.data_url) > 700_000 or not IMG_RE.match(req.data_url):
        raise HTTPException(status_code=400, detail="Ảnh không hợp lệ hoặc quá lớn (tối đa ~500KB, jpg/png/webp)")
    ref = db.collection('booking_photos').document()
    ref.set({"booking_id": booking_id, "data_url": req.data_url, "caption": req.caption.strip()[:200],
             "uploaded_by": admin_uid, "created_at": datetime.datetime.now(datetime.timezone.utc)})
    return {"status": "success", "id": ref.id}


@router.delete("/admin/{booking_id}/photos/{photo_id}")
def admin_delete_photo(booking_id: str, photo_id: str, admin_uid: str = Depends(staff_uid)):
    ref = db.collection('booking_photos').document(photo_id)
    snap = ref.get()
    if not snap.exists or snap.to_dict().get('booking_id') != booking_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh")
    ref.delete()
    return {"status": "success"}


@router.patch("/admin/{booking_id}/note")
def admin_set_note(booking_id: str, req: NoteUpdate, admin_uid: str = Depends(staff_uid)):
    ref = db.collection('bookings').document(booking_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn")
    ref.update({"result_note": req.result_note.strip()[:1000]})
    return {"status": "success"}