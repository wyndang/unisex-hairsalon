# backend/create_accounts.py - tạo / đặt lại tài khoản ADMIN và STAFF  (chạy:  python create_accounts.py)
# An toàn khi chạy nhiều lần: cùng uid thì cập nhật, không tạo trùng. KHÔNG xoá dữ liệu khác.
import datetime
from google.cloud import firestore as gcf
from database import db
from security import hash_password

NOW = datetime.datetime.now(datetime.timezone.utc)
ADMIN_PASSWORD = "Admin@2026"
STAFF_PASSWORD = "Staff@2026"

ADMINS = [
    {"uid": "owner_01", "full_name": "Quản trị viên UNISEX", "email": "nguyendangnhuquynh9a66@gmail.com", "phone": "0988888888"},
]
# uid trùng id trong collection `staffs` -> tài khoản gắn với đúng Stylist
STAFFS = [
    {"uid": "staff_01", "full_name": "Stylist Nguyễn Văn A", "email": "stylist.a@unisex.com", "phone": "0977000001",
     "specialty": "Master Cut & Layer", "exp_years": 6},
    {"uid": "staff_02", "full_name": "Stylist Trần Thị B", "email": "stylist.b@unisex.com", "phone": "0977000002",
     "specialty": "Chuyên gia Uốn & Nhuộm", "exp_years": 5},
    {"uid": "staff_03", "full_name": "Stylist Lê Hoàng C", "email": "stylist.c@unisex.com", "phone": "0977000003",
     "specialty": "Chuyên gia Phục hồi Keratin", "exp_years": 4},
    {"uid": "staff_04", "full_name": "Stylist Phạm Minh D", "email": "stylist.d@unisex.com", "phone": "0977000004",
     "specialty": "Tạo kiểu & Balayage", "exp_years": 7},
    {"uid": "staff_05", "full_name": "Chuyên viên Thảo Vy", "email": "thaovy@unisex.com", "phone": "0977000005",
     "specialty": "Gội đầu dưỡng sinh & Spa", "exp_years": 3},
]


def _conflict(field, value, uid):
    for d in db.collection('users').where(field, '==', value).stream():
        if d.id != uid:
            return d.id
    return None


def upsert(acc, role, password):
    for field in ("phone", "email"):
        other = _conflict(field, acc[field], acc["uid"])
        if other:
            print(f"  ! {field} {acc[field]} đang thuộc tài khoản {other} -> bỏ qua {acc['uid']}. Hãy xoá/đổi tài khoản đó rồi chạy lại.")
            return False
    ref = db.collection('users').document(acc["uid"])
    existed = ref.get().exists
    data = {"uid": acc["uid"], "role": role, "full_name": acc["full_name"], "email": acc["email"].lower(),
            "phone": acc["phone"], "password_hash": hash_password(password), "password": gcf.DELETE_FIELD}
    if not existed:
        data.update({"total_spent": 0, "points": 0, "created_at": NOW})
    ref.set(data, merge=True)
    if role == "staff":   # đảm bảo có hồ sơ Stylist tương ứng (không ghi đè nếu đã có)
        sref = db.collection('staffs').document(acc["uid"])
        if not sref.get().exists:
            sref.set({"id": acc["uid"], "name": acc["full_name"], "specialty": acc["specialty"],
                      "exp_years": acc["exp_years"], "avatar": "", "work_start": "08:00", "work_end": "18:00",
                      "is_active": True})
    print(f"  {'cập nhật' if existed else 'tạo mới '}  {role:5}  {acc['uid']:9}  {acc['phone']}  {acc['email']}")
    return True


if __name__ == "__main__":
    print("== ADMIN ==")
    for a in ADMINS:
        upsert(a, "owner", ADMIN_PASSWORD)
    print("== STAFF ==")
    for s in STAFFS:
        upsert(s, "staff", STAFF_PASSWORD)
    print("\nĐăng nhập bằng SĐT hoặc email + mật khẩu:")
    print(f"  Admin : nguyendangnhuquynh9a66@gmail.com / 0988888888   | mật khẩu: {ADMIN_PASSWORD}")
    print(f"  Staff : stylist.a@unisex.com ... (xem bảng trên) | mật khẩu: {STAFF_PASSWORD}")
    print("HÃY ĐỔI MẬT KHẨU trong màn hình Quản trị > Tài khoản trước khi đưa lên môi trường thật.")