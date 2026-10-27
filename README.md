# 💇‍♀️ UNISEX Hair Salon - Fullstack Web Application

Hệ thống quản lý đặt lịch hẹn dịch vụ, mua sắm sản phẩm chăm sóc tóc và quản trị salon.
Xây dựng bằng **FastAPI + Firebase Firestore + HTML/CSS/JS thuần**.

---

## ✨ Chức năng chính

- **Khách hàng:** đăng ký (OTP) / đăng nhập bằng SĐT hoặc email, đặt lịch dịch vụ, xem lịch sử booking kèm ảnh trước/sau, mua sắm sản phẩm, giỏ hàng, mã giảm giá, đánh giá sản phẩm đã mua.
- **Thanh toán:** COD, thẻ, chuyển khoản (mô phỏng), gửi email hóa đơn.
- **Quản trị:** thống kê doanh thu, quản lý đơn hàng, booking, dịch vụ, sản phẩm, nhân viên, tài khoản, mã giảm giá, thông báo.

---

## 🗂️ Cấu trúc dự án

```text
unisex-hairsalon/
├── backend/     # FastAPI + Firebase Firestore
│   ├── main.py
│   ├── routers/
│   ├── requirements.txt
│   └── .env.example
└── frontend/    # HTML / CSS / JS thuần
    ├── index.html
    ├── css/
    └── js/
```

---

## 🚀 Hướng dẫn cài đặt & khởi chạy

> **Yêu cầu:** Python 3.11 trở lên, Git.

### 1. Clone dự án

```bash
git clone https://github.com/wyndang/unisex-hairsalon.git
cd unisex-hairsalon
```

Lần sau muốn lấy code mới nhất:

```bash
git pull origin main
```

### 2. Chạy Backend (terminal 1)

```bash
cd backend

# Tạo và kích hoạt môi trường ảo
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# Cài đặt thư viện
pip install -r requirements.txt

# Tạo file cấu hình
cp .env.example .env              # Windows: copy .env.example .env
```

Mở file `.env` và điền giá trị:

| Biến | Ý nghĩa |
|---|---|
| `FIREBASE_CREDENTIALS_PATH` | Đường dẫn file key Firebase (mặc định `firebase-service-account.json`) |
| `AUTH_SECRET` | Chuỗi ngẫu nhiên dài, mỗi người tự tạo: `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `SMTP_EMAIL`, `SMTP_PASSWORD` | Gmail + Mật khẩu ứng dụng 16 ký tự (để trống nếu không cần gửi email) |
| `ADMIN_EMAIL` | Email nhận thông báo đơn hàng mới |
| `OTP_DEV_ECHO` | `1` = hiện mã OTP trên màn hình khi test đăng ký |

Đặt file `firebase-service-account.json` (xin chủ dự án qua kênh riêng) vào thư mục `backend/`, sau đó chạy:

```bash
uvicorn main:app --reload --port 8000
```

- API: http://localhost:8000
- Tài liệu API: http://localhost:8000/docs

### 3. Chạy Frontend (terminal 2)

```bash
cd frontend
python3 -m http.server 5500
```

Mở trình duyệt: **http://localhost:5500**

> Frontend gọi API tại `http://localhost:8000/api`, vì vậy cần bật backend trước.

---

## 🌱 Dữ liệu mẫu (chỉ chạy 1 lần, bởi 1 người)

> ⚠️ Cả nhóm dùng chung 1 Firestore, `seed_db.py` sẽ **xóa và tạo lại** dữ liệu. Chỉ một người chạy.

```bash
cd backend
source venv/bin/activate
python seed_db.py            # dịch vụ, sản phẩm, nhân viên, mã giảm giá
python create_accounts.py    # tài khoản admin + staff
```

---

## 🔐 Tài khoản dùng thử (môi trường phát triển)

Đăng nhập bằng **email hoặc số điện thoại** + mật khẩu.

| Vai trò | Email đăng nhập | Số điện thoại | Mật khẩu |
|---|---|---|---|
| Admin | nguyendangnhuquynh9a66@gmail.com | 0988888888 | Admin@2026 |
| Staff 1 (Nguyễn Văn A) | stylist.a@unisex.com | 0977000001 | Staff@2026 |
| Staff 2 (Trần Thị B) | stylist.b@unisex.com | 0977000002 | Staff@2026 |
| Staff 3 (Lê Hoàng C) | stylist.c@unisex.com | 0977000003 | Staff@2026 |
| Staff 4 (Phạm Minh D) | stylist.d@unisex.com | 0977000004 | Staff@2026 |
| Staff 5 (Thảo Vy) | thaovy@unisex.com | 0977000005 | Staff@2026 |

> Admin và staff sau khi đăng nhập sẽ tự động vào trang quản trị (`admin.html`).
> Hãy **đổi mật khẩu** trước khi đưa lên môi trường thật.

---

## 🤝 Quy ước làm việc nhóm

```bash
git pull origin main                      # lấy code mới nhất
git checkout -b feature/ten-chuc-nang     # mỗi chức năng một nhánh
git add .
git commit -m "Mô tả ngắn thay đổi"
git push -u origin feature/ten-chuc-nang  # sau đó tạo Pull Request trên GitHub
```

- Không commit trực tiếp vào `main`.
- Thêm thư viện mới: chạy `pip freeze > requirements.txt` rồi commit; cả nhóm chạy lại `pip install -r requirements.txt`.
- **Tuyệt đối không commit** `.env` và `firebase-service-account.json`.
