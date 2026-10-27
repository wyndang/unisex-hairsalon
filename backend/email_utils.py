# backend/email_utils.py
import os
import ssl
import json
import html
import socket
import smtplib
import datetime
import threading
import contextlib
import urllib.error
import urllib.request
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

try:
    import certifi
    CA_FILE = certifi.where()
except ImportError:
    CA_FILE = None

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

PAY_LABEL = {
    "cod": "Thanh toán khi nhận hàng (COD)",
    "card": "Thẻ tín dụng / ghi nợ",
    "banking": "Chuyển khoản ngân hàng",
}
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))
e = html.escape


_SEND_LOCK = threading.Lock()
LAST_EMAIL_ERROR = ""


def _ssl_context() -> ssl.SSLContext:
    """Xác thực chứng chỉ đàng hoàng (certifi). Chỉ tắt khi đặt SMTP_INSECURE_TLS=1 trong .env."""
    if os.getenv("SMTP_INSECURE_TLS") == "1":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context(cafile=CA_FILE) if CA_FILE else ssl.create_default_context()


@contextlib.contextmanager
def _ipv4_only():
    """Ép kết nối IPv4 (tránh lỗi treo/đứt kết nối khi IPv6 trên mạng không dùng được)."""
    orig = socket.getaddrinfo

    def v4(host, port, family=0, type=0, proto=0, flags=0):
        return orig(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = v4
    try:
        yield
    finally:
        socket.getaddrinfo = orig


def _send_brevo(to_email: str, subject: str, html_content: str) -> bool:
    """Gửi qua HTTPS (cổng 443) bằng API Brevo - dùng khi mạng chặn SMTP 587/465."""
    global LAST_EMAIL_ERROR
    key = (os.getenv("BREVO_API_KEY") or "").strip()
    sender = (os.getenv("BREVO_SENDER_EMAIL") or os.getenv("SMTP_EMAIL") or "").strip()
    if not key or not sender:
        return False
    body = json.dumps({
        "sender": {"name": "UNISEX Salon", "email": sender},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email", data=body, method="POST",
        headers={"api-key": key, "content-type": "application/json", "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20, context=_ssl_context()) as r:
            ok = 200 <= r.status < 300
            print(f"[EMAIL SUCCESS] Brevo đã gửi '{subject}' tới {to_email}" if ok else f"[EMAIL ERROR] Brevo HTTP {r.status}")
            return ok
    except urllib.error.HTTPError as he:
        LAST_EMAIL_ERROR = f"Brevo HTTP {he.code}: {he.read().decode('utf-8', 'ignore')[:300]}"
    except Exception as ex:
        LAST_EMAIL_ERROR = f"Brevo: {ex}"
    print("[EMAIL ERROR]", LAST_EMAIL_ERROR)
    return False


def _send_smtp(msg, to_email: str, user: str, password: str) -> bool:
    global LAST_EMAIL_ERROR
    ctx = _ssl_context()
    with _SEND_LOCK, _ipv4_only():
        for port, use_ssl in [(587, False), (465, True)]:
            try:
                if use_ssl:
                    server = smtplib.SMTP_SSL("smtp.gmail.com", port, context=ctx, timeout=20)
                else:
                    server = smtplib.SMTP("smtp.gmail.com", port, timeout=20)
                    server.ehlo()
                    server.starttls(context=ctx)
                server.ehlo()
                server.login(user, password)
                server.send_message(msg)
                server.quit()
                print(f"[EMAIL SUCCESS] Đã gửi '{msg['Subject']}' tới {to_email} (SMTP cổng {port})")
                return True
            except smtplib.SMTPAuthenticationError as ex:
                LAST_EMAIL_ERROR = (f"Gmail từ chối đăng nhập ({ex.smtp_code}). Kiểm tra: đã bật xác minh 2 bước, "
                                    f"SMTP_PASSWORD là 'Mật khẩu ứng dụng' 16 ký tự của đúng tài khoản {user}")
                print("[EMAIL ERROR]", LAST_EMAIL_ERROR)
                return False        # sai mật khẩu thì thử cổng khác cũng vô ích
            except Exception as ex:
                LAST_EMAIL_ERROR = f"SMTP cổng {port}: {type(ex).__name__}: {ex}"
                print("[EMAIL WARN]", LAST_EMAIL_ERROR)
    return False


def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """Thứ tự: Brevo API (nếu có BREVO_API_KEY) -> SMTP Gmail. Trả True nếu gửi được."""
    global LAST_EMAIL_ERROR
    if not to_email:
        return False
    provider = (os.getenv("EMAIL_PROVIDER") or "auto").lower()
    if provider in ("auto", "brevo") and os.getenv("BREVO_API_KEY"):
        if _send_brevo(to_email, subject, html_content):
            return True
        if provider == "brevo":
            return False

    sender_email = (os.getenv("SMTP_EMAIL") or "").strip()
    sender_password = (os.getenv("SMTP_PASSWORD") or "").replace(" ", "").strip()
    if not sender_email or not sender_password:
        LAST_EMAIL_ERROR = "Chưa cấu hình SMTP_EMAIL / SMTP_PASSWORD (hoặc BREVO_API_KEY) trong .env"
        print("[WARNING]", LAST_EMAIL_ERROR)
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = f"UNISEX Salon <{sender_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html_content, "html", "utf-8"))
    ok = _send_smtp(msg, to_email, sender_email, sender_password)
    if not ok:
        print(f"[FALLBACK LOG] Không gửi được email '{subject}' tới {to_email}. Chạy `python test_email.py` để chẩn đoán.")
    return ok


def money(n) -> str:
    return f"{int(n or 0):,}".replace(",", ".") + " VNĐ"


def vn_time(dt) -> str:
    if not dt:
        return ""
    if isinstance(dt, str):
        dt = datetime.datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(VN_TZ).strftime("%H:%M - %d/%m/%Y")


def _payment_detail(o) -> str:
    info = o.get("payment_info") or {}
    if o.get("payment_method") == "card" and info.get("card_last4"):
        return f"Thẻ •••• {e(info['card_last4'])}"
    if o.get("payment_method") == "banking" and info.get("bank_ref"):
        return f"Mã giao dịch: {e(info['bank_ref'])}"
    return ""


def _items_table(o) -> str:
    rows = "".join(
        f"""<tr>
            <td style="padding:8px;border-bottom:1px solid #eee;">{e(i['name'])}<br><small style="color:#888;">{e(i.get('brand') or '')}</small></td>
            <td style="padding:8px;border-bottom:1px solid #eee;text-align:center;">{i['quantity']}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;text-align:right;">{money(i['unit_price'])}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;text-align:right;">{money(i['line_total'])}</td>
        </tr>""" for i in o["items"])
    discount_row = ""
    if o.get("discount"):
        discount_row = f"""<tr><td colspan="3" style="padding:6px 8px;text-align:right;">Mã giảm giá ({e(o.get('coupon_code') or '')}):</td>
            <td style="padding:6px 8px;text-align:right;color:#2ecc71;">- {money(o['discount'])}</td></tr>"""
    points_row = ""
    if o.get("points_used"):
        points_row = f"""<tr><td colspan="3" style="padding:6px 8px;text-align:right;">Dùng điểm thưởng ({int(o['points_used']):,} điểm):</td>
            <td style="padding:6px 8px;text-align:right;color:#2ecc71;">- {money(o['points_used'])}</td></tr>""".replace(",", ".")
    return f"""
    <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr style="background:#faf3e3;">
            <th style="padding:8px;text-align:left;">Sản phẩm</th><th style="padding:8px;">SL</th>
            <th style="padding:8px;text-align:right;">Đơn giá</th><th style="padding:8px;text-align:right;">Thành tiền</th>
        </tr>
        {rows}
        <tr><td colspan="3" style="padding:6px 8px;text-align:right;">Tạm tính:</td><td style="padding:6px 8px;text-align:right;">{money(o['subtotal'])}</td></tr>
        {discount_row}
        {points_row}
        <tr><td colspan="3" style="padding:8px;text-align:right;font-weight:bold;">Tổng thanh toán:</td>
            <td style="padding:8px;text-align:right;font-weight:bold;font-size:17px;color:#d35400;">{money(o['total'])}</td></tr>
    </table>"""


def _info_list(o) -> str:
    detail = _payment_detail(o)
    status = "Đã thanh toán" if o.get("payment_status") == "paid" else "Chưa thanh toán (thu khi nhận hàng)"
    paid_at = f"<li><strong>Thời gian thanh toán:</strong> {vn_time(o.get('paid_at'))}</li>" if o.get("paid_at") else ""
    note = f"<li><strong>Ghi chú:</strong> {e(o['note'])}</li>" if o.get("note") else ""
    return f"""
    <ul style="line-height:1.8;padding-left:18px;">
        <li><strong>Mã đơn hàng:</strong> {e(o['order_code'])}</li>
        <li><strong>Thời gian đặt hàng:</strong> {vn_time(o.get('created_at'))}</li>
        <li><strong>Người nhận:</strong> {e(o['customer_name'])}</li>
        <li><strong>Số điện thoại:</strong> {e(o['customer_phone'])}</li>
        <li><strong>Email:</strong> {e(o['customer_email'])}</li>
        <li><strong>Địa chỉ giao hàng:</strong> {e(o['shipping_address'])}</li>
        {note}
        <li><strong>Hình thức thanh toán:</strong> {PAY_LABEL.get(o['payment_method'], o['payment_method'])}{(' - ' + detail) if detail else ''}</li>
        <li><strong>Trạng thái thanh toán:</strong> {status}</li>
        {paid_at}
    </ul>"""


def order_email_html(o, kind: str) -> str:
    hotline = os.getenv("SALON_HOTLINE", "0901 234 567")
    cfg = {
        "paid": ("Thanh Toán Thành Công", "#2ecc71",
                 "Cảm ơn bạn đã thanh toán. Đơn hàng của bạn đã được ghi nhận và đang được cửa hàng chuẩn bị."),
        "cod_placed": ("Đặt Hàng Thành Công", "#f5a623",
                       "Đơn hàng của bạn đã được ghi nhận. Bạn sẽ thanh toán khi nhận hàng; cửa hàng sẽ liên hệ qua số điện thoại để xác nhận giao hàng."),
        "cod_paid": ("Đã Nhận Thanh Toán", "#2ecc71",
                     "Cửa hàng đã xác nhận nhận được thanh toán cho đơn hàng của bạn. Cảm ơn bạn!"),
        "completed": ("Đơn Hàng Hoàn Tất", "#2ecc71",
                      "Đơn hàng của bạn đã được giao thành công. Cảm ơn bạn đã mua sắm tại UNISEX Salon!"),
    }
    title, color, intro = cfg[kind]
    review_hint = ""
    if o.get("payment_status") == "paid" and not o.get("is_guest"):
        review_hint = "<p>Bạn có thể vào trang sản phẩm đã mua để gửi đánh giá cho chúng tôi.</p>"
    elif o.get("is_guest"):
        review_hint = "<p><i>Bạn mua hàng với tư cách khách nên đơn không lưu vào lịch sử tài khoản. Hãy giữ lại email này làm biên lai.</i></p>"
    if kind == "completed" and o.get("points_earned"):
        review_hint += f"<p>🎁 Bạn vừa nhận được <strong>{int(o['points_earned']):,} điểm thưởng</strong> (1 điểm = 1đ, dùng cho lần mua sau).</p>".replace(",", ".")
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;padding:20px;border:1px solid {color};border-radius:8px;">
        <h2 style="color:{color};margin-top:0;">{title} - UNISEX Salon</h2>
        <p>Xin chào <strong>{e(o['customer_name'])}</strong>,</p>
        <p>{intro}</p>
        {_info_list(o)}
        <h3 style="color:#f5a623;">Chi tiết đơn hàng</h3>
        {_items_table(o)}
        {review_hint}
        <p style="color:#666;font-size:13px;">Cần hỗ trợ? Liên hệ hotline <strong>{e(hotline)}</strong> và cung cấp mã đơn <strong>{e(o['order_code'])}</strong>.</p>
        <p>Cảm ơn bạn đã tin tưởng UNISEX Salon!</p>
    </div>"""


def admin_order_email_html(o) -> str:
    who = "Khách vãng lai (không có tài khoản)" if o.get("is_guest") else f"Tài khoản: {e(o['customer_id'])}"
    phone_note = ""
    if o.get("phone_source") == "custom" and o.get("account_phone") and o["account_phone"] != o["customer_phone"]:
        phone_note = f"<p><i>Khách dùng số khác số đăng ký ({e(o['account_phone'])}).</i></p>"
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;padding:20px;border:1px solid #f5a623;border-radius:8px;">
        <h2 style="color:#f5a623;margin-top:0;">🛒 Đơn hàng mới {e(o['order_code'])}</h2>
        <p><strong>{who}</strong></p>
        {phone_note}
        {_info_list(o)}
        {_items_table(o)}
    </div>"""