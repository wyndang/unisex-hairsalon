# backend/seed_db.py
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone, timedelta
from security import hash_password

cred = credentials.Certificate("firebase-service-account.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()

# ==== SƠ ĐỒ COLLECTION MỚI (Firestore tự tạo khi có dữ liệu đầu tiên) ====
# users              : + points, avatar_url, email_verified, phone_verified, password_hash (không còn password thô)
# coupons            : doc id = code; discount_type percent|fixed, discount_value, max_discount_amount,
#                      min_order_value, valid_from, valid_until, usage_limit, used_count, is_active
# orders             : thông tin giao hàng, items, subtotal, coupon_code, discount, points_used, total,
#                      payment_method/info/status, order_status, status_history, points_earned, points_awarded
# purchases          : đơn x sản phẩm (+ can_review)
# point_transactions : nhật ký điểm earn | redeem | refund (cả booking trả trước sau này)
# otp_codes          : doc id = "<purpose>:<email|phone>", code_hash, expires_at, attempts (bước đăng ký OTP)
# bookings           : (booking_service) cần thêm: payment_mode prepaid|at_counter, points_earned,
#                      result_photos[], result_note  -> xem bước sau
# CẢNH BÁO: script này XOÁ SẠCH các collection liệt kê bên dưới (kể cả orders).
# True: tạo số liệu DEMO (lượt bán + sao) để giao diện có dữ liệu hiển thị ngay.
# False: toàn bộ bắt đầu từ 0 (dùng khi chạy thật).
DEMO_STATS = True

def clear_collection(coll_name):
    docs = db.collection(coll_name).stream()
    for doc in docs:
        doc.reference.delete()

def seed_data():
    now = datetime.now(timezone.utc)
    future_date = now + timedelta(days=30)

    print("Đang làm sạch và khởi tạo dữ liệu mới...")
    for c in ['users', 'staffs', 'services', 'products', 'coupons', 'orders', 'purchases', 'reviews', 'point_transactions', 'otp_codes']:
        clear_collection(c)

    # 1. Collection: users
    users_data = [
        {"uid": "owner_01", "role": "owner", "full_name": "Admin Salon", "email": "admin@unisex.com", "phone": "0988888888",
         "password_hash": hash_password("123456"), "total_spent": 0, "points": 0, "avatar_url": "",
         "email_verified": True, "phone_verified": True, "created_at": now},
        {"uid": "staff_01", "role": "staff", "full_name": "Stylist Nguyễn Văn A", "email": "nva@unisex.com", "phone": "0977777777",
         "password_hash": hash_password("123456"), "total_spent": 0, "points": 0, "avatar_url": "",
         "email_verified": True, "phone_verified": True, "created_at": now},
        {"uid": "user_01", "role": "customer", "full_name": "Nguyễn Đặng Như Quỳnh", "email": "dangquynh071007l@gmail.com", "phone": "0901234567",
         "password_hash": hash_password("123456"), "total_spent": 2000000, "points": 50000, "avatar_url": "",
         "email_verified": True, "phone_verified": True, "created_at": now}
    ]
    for u in users_data:
        db.collection('users').document(u['uid']).set(u)

    # 2. Collection: staffs (Quản lý nhân viên riêng biệt)
    staffs_data = [
        {"id": "staff_01", "name": "Stylist Nguyễn Văn A", "specialty": "Master Cut & Layer", "exp_years": 6, "avatar": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=300&q=80", "work_start": "08:00", "work_end": "18:00", "is_active": True},
        {"id": "staff_02", "name": "Stylist Trần Thị B", "specialty": "Chuyên gia Uốn & Nhuộm", "exp_years": 5, "avatar": "https://images.unsplash.com/photo-1580489944761-15a19d654956?auto=format&fit=crop&w=300&q=80", "work_start": "08:00", "work_end": "18:00", "is_active": True},
        {"id": "staff_03", "name": "Stylist Lê Hoàng C", "specialty": "Chuyên gia Phục hồi Keratin", "exp_years": 4, "avatar": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=300&q=80", "work_start": "08:00", "work_end": "18:00", "is_active": True},
        {"id": "staff_04", "name": "Stylist Phạm Minh D", "specialty": "Tạo kiểu & Balayage", "exp_years": 7, "avatar": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=300&q=80", "work_start": "08:00", "work_end": "18:00", "is_active": True},
        {"id": "staff_05", "name": "Chuyên viên Thảo Vy", "specialty": "Gội đầu dưỡng sinh & Spa", "exp_years": 3, "avatar": "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=300&q=80", "work_start": "08:00", "work_end": "18:00", "is_active": True}
    ]
    for st in staffs_data:
        db.collection('staffs').document(st['id']).set(st)

    # 3. Collection: services (15 dịch vụ, mỗi dịch vụ 3 mức giá kèm Ưu/Nhược điểm)
    raw_services = [
        ("svc_1", "Cắt Tạo Kiểu Thiết Kế", "Cắt & Tạo kiểu", 45, 150000, "Thiết kế kiểu tóc cá nhân hóa phù hợp khuôn mặt, bao gồm xả dưỡng cơ bản.", "https://images.unsplash.com/photo-1560066984-138dadb4c035?auto=format&fit=crop&w=600&q=80"),
        ("svc_2", "Gội Đầu Dưỡng Sinh Trung Hoa", "Gội & Thư giãn", 60, 200000, "Gội đầu thảo dược kết hợp massage ấn huyệt cổ vai gáy giảm căng thẳng.", "https://images.unsplash.com/photo-1519823551278-64ac92734fb1?auto=format&fit=crop&w=600&q=80"),
        ("svc_3", "Hấp Dầu Collagen Tươi", "Phục hồi", 60, 350000, "Cung cấp độ ẩm sâu, giúp mái tóc khô xơ trở nên mềm mượt tức thì.", "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?auto=format&fit=crop&w=600&q=80"),
        ("svc_4", "Phục Hồi Tóc Chuyên Sâu Keratin", "Phục hồi", 90, 600000, "Tái tạo cấu trúc tủy tóc bị nát, cháy do hóa chất, trả lại độ đàn hồi.", "https://images.unsplash.com/photo-1580618672591-eb180b1a973f?auto=format&fit=crop&w=600&q=80"),
        ("svc_5", "Uốn Sóng Lơi Hàn Quốc", "Uốn tóc", 120, 700000, "Tạo lọn sóng tự nhiên, bồng bềnh chuẩn phong cách Hàn Quốc.", "https://images.unsplash.com/photo-1595476108010-b4d1f10d5e43?auto=format&fit=crop&w=600&q=80"),
        ("svc_6", "Uốn Phồng Layer Đa Tầng", "Uốn tóc", 120, 650000, "Uốn cúp đuôi kết hợp tỉa layer giúp gương mặt thon gọn, trẻ trung.", "https://images.unsplash.com/photo-1605497788044-5a32c7078486?auto=format&fit=crop&w=600&q=80"),
        ("svc_7", "Duỗi Hơi Nước Tự Nhiên", "Duỗi tóc", 120, 650000, "Công nghệ duỗi hơi nước giúp tóc thẳng mượt tự nhiên, không bị đơ cứng.", "https://images.unsplash.com/photo-1519699047748-de8e457a634e?auto=format&fit=crop&w=600&q=80"),
        ("svc_8", "Duỗi Phủ Lụa Bóng Mượt", "Duỗi tóc", 150, 800000, "Kết hợp ép thẳng và phủ tinh chất lụa giúp tóc bóng khỏe như gương.", "https://images.unsplash.com/photo-1527799820374-dcf8d9d4a388?auto=format&fit=crop&w=600&q=80"),
        ("svc_9", "Bấm Phồng Chân Tóc Vô Hình", "Cắt & Tạo kiểu", 60, 300000, "Kỹ thuật làm phồng chân tóc không lộ vết bấm, giữ độ phồng 3-4 tháng.", "https://images.unsplash.com/photo-1492106087820-71f1a00d2b11?auto=format&fit=crop&w=600&q=80"),
        ("svc_10", "Nhuộm Màu Thời Trang Thuần Chay", "Nhuộm tóc", 120, 600000, "Lên màu chuẩn xác, không cần tẩy, không gây kích ứng da đầu.", "https://images.unsplash.com/photo-1522337660859-02fbefca4702?auto=format&fit=crop&w=600&q=80"),
        ("svc_11", "Nhuộm Balayage / Highlight Nghệ Thuật", "Nhuộm tóc", 180, 1200000, "Kỹ thuật gẩy sợi và chuyển màu loang Tây Âu sành điệu.", "https://images.unsplash.com/photo-1562322140-8baeececf3df?auto=format&fit=crop&w=600&q=80"),
        ("svc_12", "Tẩy Tóc An Toàn Không Rát", "Nhuộm tóc", 90, 500000, "Bóc tách sắc tố tóc kèm tinh chất bảo vệ liên kết disulfide.", "https://images.unsplash.com/photo-1620331311520-246422fd82f9?auto=format&fit=crop&w=600&q=80"),
        ("svc_13", "Detox Thanh Lọc Da Đầu", "Gội & Thư giãn", 45, 250000, "Làm sạch sâu nang tóc, loại bỏ gàu, bã nhờn và cặn silicon tích tụ.", "https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=600&q=80"),
        ("svc_14", "Tết Tóc Nghệ Thuật Cornrow / Box Braids", "Cắt & Tạo kiểu", 90, 400000, "Tết tóc cá tính giữ nếp lâu cho các sự kiện và lễ hội âm nhạc.", "https://images.unsplash.com/photo-1508214751196-bcfd4ca60f91?auto=format&fit=crop&w=600&q=80"),
        ("svc_15", "Trị Liệu Rụng Tóc Huyết Thanh", "Phục hồi", 60, 550000, "Đưa tinh chất kích thích mọc tóc vào sâu nang tóc bằng máy điện di.", "https://images.unsplash.com/photo-1515377905703-c4788e51af15?auto=format&fit=crop&w=600&q=80")
    ]

    for sid, name, cat, dur, base_p, desc, img in raw_services:
        tiers = [
            {
                "tier_id": "basic",
                "tier_name": "Gói Tiêu Chuẩn (Dòng L'Oréal Professionnel)",
                "product_line": "L'Oréal Serie Expert (Pháp)",
                "price": base_p,
                "pros": "Chi phí tiết kiệm nhất, lên phom/màu ổn định, phù hợp với nền tóc khỏe tự nhiên chưa qua nhiều lần tẩy nhuộm.",
                "cons": "Độ bóng và khả năng giữ ẩm ở mức cơ bản (khoảng 2-3 tháng); tóc có thể hơi khô nhẹ ở phần ngọn nếu không dùng thêm dầu dưỡng tại nhà."
            },
            {
                "tier_id": "premium",
                "tier_name": "Gói Cao Cấp (Dòng Moroccanoil & Goldwell)",
                "product_line": "Moroccanoil (Israel) / Goldwell (Đức)",
                "price": int(base_p * 1.4),
                "pros": "Giàu tinh dầu Argan chống oxy hóa, mùi hương sang trọng dễ chịu, không gây xót da đầu, độ bền màu/nếp cao từ 4-6 tháng.",
                "cons": "Chi phí tầm trung; đối với tóc đã tẩy nát cấp độ 3 trở lên vẫn cần kết hợp thêm bước phục hồi chuyên sâu."
            },
            {
                "tier_id": "luxury",
                "tier_name": "Gói Thượng Hạng (Dòng Olaplex & Kérastase)",
                "product_line": "Olaplex (Mỹ) & Kérastase (Pháp)",
                "price": int(base_p * 1.9),
                "pros": "Công nghệ nối liên kết lưu huỳnh độc quyền bảo vệ tóc tuyệt đối 100%, phục hồi tóc hư tổn nặng ngay trong lúc làm, tóc bóng mượt như lụa và giữ nếp trên 6 tháng.",
                "cons": "Giá thành cao nhất trong 3 phân khúc và quy trình ủ tinh chất đòi hỏi kỹ thuật tỉ mỉ."
            }
        ]
        db.collection('services').document(sid).set({
            "id": sid,
            "name": name,
            "category": cat,
            "price": base_p, # Giá khởi điểm từ gói Basic
            "duration_minutes": dur,
            "desc": desc,
            "img_url": img,
            "tiers": tiers,
            "is_active": True
        })

    # 4. Collection: products (30 sản phẩm chia đều 5 loại x 6 sản phẩm)
    categories = ["Dầu gội", "Dầu xả", "Dầu dưỡng", "Sáp vuốt tóc", "Kem ủ & Huyết thanh"]
    brands = ["Moroccanoil", "Olaplex", "Kevin Murphy", "Kérastase", "L'Oréal", "Davines"]
    imgs = [
        "https://images.unsplash.com/photo-1526947425960-945c6e72858f?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1596462502278-27bfdc403348?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1608248543803-ba4f8c70ae0b?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1631729371254-42c2892f0e6e?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1620916566398-39f1143ab7be?auto=format&fit=crop&w=600&q=80",
        "https://images.unsplash.com/photo-1556228578-0d85b1a4d571?auto=format&fit=crop&w=600&q=80"
    ]

    product_names = {
        "Dầu gội": ["Hydrating Shampoo", "No.4 Bond Maintenance", "Balancing Wash", "Bain Satin Riche", "Absolut Repair Gold", "Nounou Shampoo"],
        "Dầu xả": ["Moisture Repair Conditioner", "No.5 Bond Conditioner", "Hydrate-Me Rinse", "Fondant Extentioniste", "Vitamino Color Conditioner", "Momo Conditioner"],
        "Dầu dưỡng": ["Treatment Original Argan", "No.7 Bonding Oil", "Young Again Oil", "Elixir Ultime Oil", "Mythic Oil Huile", "Oi Oil Absolute"],
        "Sáp vuốt tóc": ["Texture Clay Matte", "Rough Rider Clay", "Night Rider Paste", "Free Hold Medium", "Genesis Homme Cire", "Strong Moulding Clay"],
        "Kem ủ & Huyết thanh": ["Intense Hydrating Mask", "No.3 Hair Perfector", "Restore Repair Mask", "Masque Chronologiste", "Pro Longer Mask", "Liquid Spell Reinforcing"]
    }

    prod_idx = 1
    for c_idx, cat in enumerate(categories):
        for b_idx, brand in enumerate(brands):
            pid = f"prod_{prod_idx}"
            pname = f"{brand} {product_names[cat][b_idx]}"
            price = 350000 + (b_idx * 120000) + (c_idx * 50000)
            volume = "100g" if cat == "Sáp vuốt tóc" else ("100ml" if cat == "Dầu dưỡng" else "250ml")
            img_main = imgs[(prod_idx - 1) % len(imgs)]
            img_sub1 = imgs[prod_idx % len(imgs)]
            img_sub2 = imgs[(prod_idx + 1) % len(imgs)]

            # Thống kê bán hàng & đánh giá (rating_sum/rating_count để cập nhật trung bình chính xác)
            if DEMO_STATS:
                sold_count = 30 + (prod_idx * 37) % 400
                rating_count = 8 + (prod_idx * 13) % 90
                rating_sum = round((4.2 + ((prod_idx * 7) % 8) / 10) * rating_count)
            else:
                sold_count = rating_count = rating_sum = 0
            rating_avg = round(rating_sum / rating_count, 2) if rating_count else 0

            db.collection('products').document(pid).set({
                "id": pid,
                "name": pname,
                "type": cat,
                "brand": brand,
                "volume": volume,
                "price": price,
                "stock": 40,
                "origin": "Châu Âu / Mỹ",
                "desc": f"Sản phẩm {cat.lower()} chính hãng từ thương hiệu {brand}, giúp nuôi dưỡng, bảo vệ cấu trúc tóc và mang lại vẻ bóng mượt chuẩn Salon.",
                "usage": "Sử dụng một lượng vừa đủ lên tóc ẩm hoặc khô tùy theo phân loại sản phẩm. Tránh tiếp xúc trực tiếp với mắt.",
                "img": img_main,
                "images": [img_main, img_sub1, img_sub2],
                "sold_count": sold_count,       # số lượt mua (chỉ tăng khi đơn đã thanh toán)
                "rating_sum": rating_sum,       # tổng số sao
                "rating_count": rating_count,   # số lượt đánh giá
                "rating_avg": rating_avg,       # sao trung bình (0-5)
                "created_at": now,
                "is_active": True
            })
            prod_idx += 1

    # 5. Collection: coupons
    db.collection('coupons').document("WELCOME20").set({
        "code": "WELCOME20", "description": "Giảm 20% tối đa 100.000đ cho đơn từ 300.000đ",
        "discount_type": "percent", "discount_value": 20, "max_discount_amount": 100000,
        "min_order_value": 300000, "valid_from": now, "valid_until": future_date,
        "usage_limit": 100, "used_count": 0, "is_active": True
    })
    db.collection('coupons').document("GIAM50K").set({
        "code": "GIAM50K", "description": "Giảm 50.000đ cho đơn từ 500.000đ",
        "discount_type": "fixed", "discount_value": 50000, "max_discount_amount": 0,
        "min_order_value": 500000, "valid_from": now, "valid_until": future_date,
        "usage_limit": 50, "used_count": 0, "is_active": True
    })

    print("Hoàn tất! Đã tạo 15 Dịch vụ (kèm 3 mức giá), 30 Sản phẩm, 5 Nhân viên, 2 Coupon lên Firestore! (mật khẩu demo: 123456)")

if __name__ == "__main__":
    seed_data()