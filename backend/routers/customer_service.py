# backend/routers/customer_service.py
from fastapi import APIRouter, HTTPException
from database import db

router = APIRouter(prefix="/api/customer", tags=["Customer Service"])

@router.get("/{uid}/bookings/upcoming")
def get_upcoming(uid: str):
    docs = db.collection('bookings').where('customer_id', '==', uid).stream()
    res = []
    for d in docs:
        item = d.to_dict()
        if item.get('status') in ['pending_payment', 'confirmed', 'paid']:
            res.append({"id": d.id, **item})
    return res

@router.get("/{uid}/bookings/history")
def get_history(uid: str):
    docs = db.collection('bookings').where('customer_id', '==', uid).stream()
    res = []
    for d in docs:
        item = d.to_dict()
        if item.get('status') in ['completed', 'cancelled']:
            res.append({"id": d.id, **item})
    return res

@router.get("/{uid}/hair-history")
def get_hair_history(uid: str):
    docs = db.collection('hair_history').where('customer_id', '==', uid).stream()
    return [{"id": d.id, **d.to_dict()} for d in docs]

@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: str):
    b_ref = db.collection('bookings').document(booking_id)
    b_doc = b_ref.get()
    if not b_doc.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn")
    
    b_data = b_doc.to_dict()
    b_ref.update({"status": "cancelled"})
    
    # Giải phóng khung giờ đã đóng băng của nhân viên
    sched_id = f"source venv/bin/activate{b_data.get('staff_id')}_{b_data.get('date')}"
    sched_ref = db.collection('daily_schedules').document(sched_id)
    sched_doc = sched_ref.get()
    if sched_doc.exists:
        slots = [s for s in sched_doc.to_dict().get("bookings", []) if s.get("booking_id") != booking_id]
        sched_ref.set({"bookings": slots}, merge=True)
        
    return {"status": "success", "message": "Đã hủy lịch hẹn và mở khóa giờ cho nhân viên"}