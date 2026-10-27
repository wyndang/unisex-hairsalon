# backend/test_email.py  -  chạy:  python test_email.py [email_nhan]
# Chẩn đoán từng bước: DNS -> kết nối TCP -> TLS -> đăng nhập -> gửi thử. In ra nguyên nhân + cách xử lý.
import os
import sys
import ssl
import socket
import smtplib
from email_utils import send_email, ENV_PATH, _ssl_context, _ipv4_only
import email_utils

HOST = "smtp.gmail.com"
user = (os.getenv("SMTP_EMAIL") or "").strip()
pw = (os.getenv("SMTP_PASSWORD") or "").replace(" ", "")
to = sys.argv[1] if len(sys.argv) > 1 else (os.getenv("ADMIN_EMAIL") or user)
print(f".env: {ENV_PATH} | SMTP_EMAIL={user or '(trống)'} | mật khẩu ứng dụng: {len(pw)} ký tự (cần 16)")
print(f"BREVO_API_KEY: {'có' if os.getenv('BREVO_API_KEY') else 'không'}\n")


def step(name, fn):
    try:
        r = fn()
        print(f"[OK]   {name}" + (f" -> {r}" if r else ""))
        return True
    except Exception as ex:
        print(f"[FAIL] {name}: {type(ex).__name__}: {ex}")
        return False


step("DNS smtp.gmail.com (IPv4)", lambda: socket.getaddrinfo(HOST, 587, socket.AF_INET)[0][4][0])
tcp = {}
for port in (587, 465, 443):
    tcp[port] = step(f"Kết nối TCP tới {HOST}:{port}", lambda p=port: socket.create_connection((HOST, p), timeout=10).close())

smtp_ok = False
if tcp[587]:
    def tls():
        with _ipv4_only():
            s = smtplib.SMTP(HOST, 587, timeout=15)
            s.ehlo(); s.starttls(context=_ssl_context()); s.ehlo()
            s.login(user, pw); s.quit()
    smtp_ok = step("EHLO + STARTTLS + đăng nhập (587)", tls)

print("\n--- Gửi thử ---")
sent = send_email(to, "[UNISEX] Email thử", "<h3>Email thử từ UNISEX Salon</h3><p>Nếu bạn đọc được dòng này, gửi email đã hoạt động.</p>")
print("KẾT QUẢ:", "ĐÃ GỬI tới " + to if sent else "KHÔNG GỬI ĐƯỢC -> " + email_utils.LAST_EMAIL_ERROR)

print("\n--- Kết luận ---")
if sent:
    print("Mọi thứ ổn.")
elif not tcp[587] and not tcp[465]:
    print("Mạng đang CHẶN cổng SMTP (587/465). Cách xử lý: tắt VPN / đổi sang wifi khác hoặc hotspot điện thoại,\n"
          "hoặc dùng Brevo qua HTTPS (cổng 443, hướng dẫn trong tin nhắn): đặt BREVO_API_KEY + BREVO_SENDER_EMAIL trong .env.")
elif (tcp[587] or tcp[465]) and not smtp_ok and "từ chối đăng nhập" not in email_utils.LAST_EMAIL_ERROR:
    print("Kết nối được nhưng bị ĐÓNG giữa chừng: thường do phần mềm diệt virus/tường lửa quét SSL (Avast, Kaspersky, ESET, Little Snitch...),\n"
          "VPN, hoặc Google tạm chặn IP sau nhiều lần đăng nhập sai. Hãy tắt quét email/HTTPS của antivirus, tắt VPN, chờ 15-30 phút,\n"
          "hoặc chuyển sang Brevo (HTTPS).")
elif "từ chối đăng nhập" in email_utils.LAST_EMAIL_ERROR:
    print("Sai Mật khẩu ứng dụng: tạo lại tại myaccount.google.com/apppasswords (cần bật xác minh 2 bước) cho ĐÚNG tài khoản SMTP_EMAIL.")