# backend/routers/catalog_service.py
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from google.cloud import firestore as gcf
from database import db
from auth import current_user
import datetime

router = APIRouter(prefix="/api/catalog", tags=["Catalog Service"])


class ReviewRequest(BaseModel):
    customer_name: str = ""   # bỏ qua: tên lấy từ tài khoản
    stars: int
    comment: str


@router.get("/services")
def get_services():
    docs = db.collection('services').where('is_active', '==', True).stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


@router.get("/services/{service_id}")
def get_service_detail(service_id: str):
    doc = db.collection('services').document(service_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy dịch vụ")
    return {"id": doc.id, **doc.to_dict()}


@router.get("/products")
def get_products():
    # Mỗi sản phẩm đã có sẵn: sold_count, rating_avg, rating_count -> card hiển thị trực tiếp
    docs = db.collection('products').where('is_active', '==', True).stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


@router.get("/products/{product_id}")
def get_product_detail(product_id: str):
    doc = db.collection('products').document(product_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")

    product_data = {"id": doc.id, **doc.to_dict()}
    reviews_ref = db.collection('reviews').where('product_id', '==', product_id).stream()
    reviews = [{"id": r.id, **r.to_dict()} for r in reviews_ref]
    reviews.sort(key=lambda r: r.get('created_at', ''), reverse=True)  # mới nhất lên đầu
    product_data['reviews'] = reviews
    return product_data


# ---------------------------------------------------------------
# ĐÁNH GIÁ: chỉ khách đã MUA & THANH TOÁN THÀNH CÔNG mới được đánh giá
# ---------------------------------------------------------------
def _has_paid_purchase(customer_id: str, product_id: str) -> bool:
    if not customer_id or customer_id == 'guest':   # khách vãng lai không có quyền đánh giá
        return False
    docs = (db.collection('purchases')
            .where('customer_id', '==', customer_id)
            .where('product_id', '==', product_id)
            .where('can_review', '==', True)
            .limit(1).stream())
    return any(True for _ in docs)


def _review_doc_id(product_id: str, customer_id: str) -> str:
    return f"{product_id}_{customer_id}"  # mỗi khách chỉ đánh giá 1 lần / sản phẩm


@router.get("/products/{product_id}/can-review")
def can_review(product_id: str, user: dict = Depends(current_user)):
    customer_id = user['uid']
    if db.collection('reviews').document(_review_doc_id(product_id, customer_id)).get().exists:
        return {"can_review": False, "reason": "already_reviewed"}
    if not _has_paid_purchase(customer_id, product_id):
        return {"can_review": False, "reason": "not_purchased"}
    return {"can_review": True, "reason": "ok"}


@gcf.transactional
def _review_tx(tx, prod_ref, rev_ref, rev_data):
    # Đọc trước - ghi sau (yêu cầu của Firestore transaction)
    if rev_ref.get(transaction=tx).exists:
        raise HTTPException(status_code=409, detail="Bạn đã đánh giá sản phẩm này rồi")
    prod = prod_ref.get(transaction=tx)
    if not prod.exists:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    p = prod.to_dict()
    count = int(p.get('rating_count', 0)) + 1
    total = float(p.get('rating_sum', 0)) + rev_data['stars']
    tx.set(rev_ref, rev_data)
    tx.update(prod_ref, {
        "rating_count": count,
        "rating_sum": total,
        "rating_avg": round(total / count, 2)
    })


@router.post("/products/{product_id}/reviews")
def add_product_review(product_id: str, req: ReviewRequest, user: dict = Depends(current_user)):
    customer_id = user['uid']
    u = db.collection('users').document(customer_id).get()
    customer_name = u.to_dict().get('full_name', 'Khách hàng') if u.exists else 'Khách hàng'
    if not 1 <= req.stars <= 5:
        raise HTTPException(status_code=400, detail="Số sao phải từ 1 đến 5")
    comment = req.comment.strip()
    if not comment or len(comment) > 1000:
        raise HTTPException(status_code=400, detail="Nội dung đánh giá phải từ 1 đến 1000 ký tự")
    if not _has_paid_purchase(customer_id, product_id):
        raise HTTPException(status_code=403,
                            detail="Chỉ khách hàng đã mua và thanh toán thành công sản phẩm này mới được đánh giá")

    rev_ref = db.collection('reviews').document(_review_doc_id(product_id, customer_id))
    prod_ref = db.collection('products').document(product_id)
    rev_data = {
        "id": rev_ref.id,
        "product_id": product_id,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "stars": req.stars,
        "comment": comment,
        "verified_purchase": True,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    _review_tx(db.transaction(), prod_ref, rev_ref, rev_data)
    return {"status": "success", "review": rev_data}


@router.get("/staffs")
def get_staffs():
    docs = db.collection('staffs').where('is_active', '==', True).stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]