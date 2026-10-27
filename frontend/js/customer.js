// js/customer.js
const API_BASE = "http://localhost:8000/api";
const uid = localStorage.getItem('uid') || 'user_01';

function switchTab(tabId) {
    document.querySelectorAll('.tab-menu li').forEach(li => li.classList.remove('active'));
    event.target.classList.add('active');
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    document.getElementById(`tab-${tabId}`).classList.add('active');
}

async function loadUpcomingBookings() {
    const list = document.getElementById('upcoming-list');
    list.innerHTML = `<p style="color:var(--text-muted);">Đang tải lịch hẹn...</p>`;
    try {
        const res = await fetch(`${API_BASE}/customer/${uid}/bookings/upcoming`);
        const bookings = await res.json();
        list.innerHTML = '';

        if (bookings.length === 0) {
            list.innerHTML = `<p style="color:var(--text-muted);">Bạn chưa có lịch hẹn nào sắp tới. <a href="booking.html" style="color:var(--gold);">Đặt lịch ngay</a></p>`;
            return;
        }

        bookings.forEach(item => {
            const statusText = item.status === 'paid' ? 'Đã thanh toán trước' : 'Thanh toán tại quầy';
            list.innerHTML += `
                <div class="appointment-card">
                    <div>
                        <h3 style="margin-bottom: 0.4rem; color:#fff;">${item.service_name || 'Dịch vụ Salon'}</h3>
                        <p style="color:var(--gold); font-size:0.85rem; margin-bottom:0.4rem;">Gói: ${item.tier_name || 'Tiêu chuẩn'}</p>
                        <p style="color:var(--text-muted); font-size: 0.9rem;">
                            📅 Ngày: <strong>${item.date}</strong> | ⏰ Giờ: <strong>${item.time} - ${item.end_time || ''}</strong> (${item.duration || 60} phút)<br>
                            👤 Stylist: ${item.staff_name || item.staff_id}
                        </p>
                    </div>
                    <div style="text-align: right;">
                        <span class="status-badge status-upcoming">${statusText}</span>
                        <p style="color:var(--gold); font-weight:bold; margin-top:0.5rem;">${(item.total_price || 0).toLocaleString('vi-VN')} đ</p>
                        <button class="btn-outline" onclick="cancelBooking('${item.id}')" style="margin-top: 0.6rem; border-color: #e74c3c; color: #e74c3c; padding: 5px 15px;">Hủy lịch</button>
                    </div>
                </div>
            `;
        });
    } catch (e) {
        list.innerHTML = `<p style="color:#e74c3c;">Lỗi tải dữ liệu từ Backend.</p>`;
    }
}

async function cancelBooking(bookingId) {
    if (!confirm("Bạn có chắc chắn muốn hủy lịch hẹn này không?")) return;
    const res = await fetch(`${API_BASE}/customer/bookings/${bookingId}/cancel`, { method: 'POST' });
    if (res.ok) {
        alert("Đã hủy lịch hẹn và mở khóa giờ cho Stylist!");
        loadUpcomingBookings();
        loadHistoryBookings();
    }
}

async function loadHistoryBookings() {
    const list = document.getElementById('history-list');
    try {
        const res = await fetch(`${API_BASE}/customer/${uid}/bookings/history`);
        const history = await res.json();
        list.innerHTML = history.length === 0 ? `<p style="color:var(--text-muted);">Chưa có lịch sử hóa đơn.</p>` : '';

        history.forEach(item => {
            list.innerHTML += `
                <div class="appointment-card">
                    <div>
                        <h3 style="margin-bottom: 0.4rem; color:#fff;">${item.service_name || 'Dịch vụ Salon'}</h3>
                        <p style="color:var(--text-muted); font-size: 0.9rem;">📅 Ngày: ${item.date} (${item.time})</p>
                    </div>
                    <div style="text-align: right;">
                        <span class="status-badge status-done">${item.status === 'cancelled' ? 'Đã hủy' : 'Hoàn thành'}</span>
                        <p style="color:var(--gold); font-weight: bold; font-size:1.1rem; margin-top: 0.5rem;">${(item.total_price || 0).toLocaleString('vi-VN')} đ</p>
                    </div>
                </div>
            `;
        });
    } catch (e) { }
}

async function loadHairGallery() {
    const list = document.getElementById('hair-list');
    try {
        const res = await fetch(`${API_BASE}/customer/${uid}/hair-history`);
        const hairs = await res.json();
        list.innerHTML = hairs.length === 0 ? `<p style="color:var(--text-muted);">Chưa có ảnh kiểu tóc nào.</p>` : '';

        hairs.forEach(item => {
            list.innerHTML += `
                <div class="hair-card">
                    <img src="${item.img_url}" alt="Kiểu tóc">
                    <p style="color:var(--gold); font-size: 0.85rem; margin-bottom: 0.4rem;">Stylist: ${item.staff_id}</p>
                    <p style="color:var(--text-muted); font-size: 0.85rem;">📝 Ghi chú: ${item.note}</p>
                </div>
            `;
        });
    } catch (e) { }
}

function logout() {
    localStorage.clear();
    window.location.href = 'login.html';
}

document.addEventListener('DOMContentLoaded', () => {
    loadUpcomingBookings();
    loadHistoryBookings();
    loadHairGallery();
});