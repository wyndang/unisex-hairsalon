# backend/routers/admin_service.py - Tổng quan doanh thu cho trang Admin (cửa hàng + dịch vụ + điểm)
import datetime
from fastapi import APIRouter, Depends
from database import db
from auth import staff_uid

router = APIRouter(prefix="/api/admin", tags=["Admin Service"])


@router.get("/dashboard")
def dashboard(admin_uid: str = Depends(staff_uid)):
    """Doanh thu thực thu:
       - Cửa hàng: đơn đã thanh toán (sau giảm giá & điểm), theo ngày thanh toán.
       - Dịch vụ: booking đã trả trước, hoặc đã hoàn thành (thu tại quầy), tính 1 lần, theo ngày hẹn.
       Khi dữ liệu lớn nên chuyển sang bảng thống kê theo ngày thay vì quét toàn bộ."""
    shop = svc = 0
    by_day, top, methods = {}, {}, {}
    n_orders = n_book = 0

    def add(day, key, amount):
        d = by_day.setdefault(day, {"day": day, "shop": 0, "service": 0})
        d[key] += amount

    pending_orders = 0
    for d in db.collection('orders').stream():
        o = d.to_dict()
        if o.get('order_status') == 'pending_confirm':
            pending_orders += 1
        if o.get('payment_status') != 'paid':
            continue
        n_orders += 1
        shop += o['total']
        methods[o['payment_method']] = methods.get(o['payment_method'], 0) + o['total']
        add(str(o.get('paid_at') or o.get('created_at'))[:10], "shop", o['total'])
        for i in o['items']:
            t = top.setdefault(i['product_id'], {"name": i['name'], "quantity": 0, "revenue": 0})
            t['quantity'] += i['quantity']
            t['revenue'] += i['line_total']

    pending_bookings = 0
    for d in db.collection('bookings').stream():
        b = d.to_dict()
        if b.get('status') in ('confirmed', 'paid'):
            pending_bookings += 1
        if b.get('status') == 'cancelled' or not (b.get('paid') or b.get('status') == 'completed'):
            continue
        n_book += 1
        svc += int(b.get('total_price', 0))
        add(b.get('date', '')[:10], "service", int(b.get('total_price', 0)))

    earned = redeemed = 0
    for d in db.collection('point_transactions').stream():
        p = d.to_dict()
        if p.get('type') == 'earn':
            earned += p['points']
        elif p.get('type') == 'redeem':
            redeemed += -p['points']

    return {"total_revenue": shop + svc, "shop_revenue": shop, "service_revenue": svc,
            "paid_orders": n_orders, "counted_bookings": n_book, "revenue_by_method": methods,
            "pending_orders": pending_orders, "upcoming_bookings": pending_bookings,
            "points_issued": earned, "points_redeemed": redeemed,
            "by_day": sorted(by_day.values(), key=lambda x: x['day'])[-30:],
            "top_products": sorted(top.values(), key=lambda x: x['quantity'], reverse=True)[:10]}