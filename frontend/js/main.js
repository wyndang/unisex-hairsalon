
/* js/main.js - Trang chủ: dịch vụ + sản phẩm bán chạy (kèm sao & lượt mua) */
(function () {
    const U = window.UNISEX;

    document.addEventListener('DOMContentLoaded', () => {
        const role = localStorage.getItem('userRole');
        const fullName = localStorage.getItem('userName') || 'Khách hàng';
        if (role && localStorage.getItem('token')) {
            const targetPage = (role === 'owner' || role === 'staff') ? 'admin.html' : 'customer.html';
            document.getElementById('auth-section').innerHTML = `
                <div onclick="window.location.href='${targetPage}'" style="display: flex; align-items: center; gap: 10px; cursor:pointer;">
                    <img src="https://ui-avatars.com/api/?name=${encodeURIComponent(fullName)}&background=f5a623&color=fff" style="width: 35px; border-radius: 50%;">
                    <span style="color: var(--text-light); font-size: 0.9rem;">${U.esc(fullName)}</span>
                </div>
                <a href="booking.html" class="btn-primary">Book an Appointment</a>
            `;
        }
    });

    function serviceCard(s) {
        const link = `booking.html?service_id=${encodeURIComponent(s.id)}`;
        return `
        <div class="service-card">
            <div class="card-content">
                <div class="card-img-wrap"><img src="${U.esc(s.img_url)}" alt="${U.esc(s.name)}" loading="lazy"></div>
                <div class="pc-meta text-ellipsis-1">${U.esc(s.category)}</div>
                <h3 class="pc-name text-ellipsis-2">${U.esc(s.name)}</h3>
                <p class="pc-desc text-ellipsis-2">${U.esc(s.desc)}</p>
                <div class="svc-meta">
                    <span><i class="far fa-clock"></i> ${s.duration_minutes} phút</span>
                    <span class="pc-price">Từ ${U.fmt(s.price)}</span>
                </div>
            </div>
            <div class="card-footer-actions row">
                <a class="btn-outline" href="services.html?detail=${encodeURIComponent(s.id)}">3 Mức giá</a>
                <a class="btn-primary" href="${link}">Đặt lịch</a>
            </div>
        </div>`;
    }

    async function loadServices() {
        const box = document.getElementById('services-container');
        if (!box) return;
        try {
            const res = await fetch(`${U.API}/catalog/services`);
            const list = await res.json();
            box.innerHTML = list.slice(0, 10).map(serviceCard).join('');
        } catch (e) {
            box.innerHTML = '<p style="color:var(--text-muted)">Không thể tải dịch vụ. Hãy kiểm tra Backend.</p>';
        }
    }

    async function loadProducts() {
        const box = document.getElementById('products-container');
        if (!box) return;
        try {
            const res = await fetch(`${U.API}/catalog/products`);
            const list = await res.json();
            list.sort((a, b) => (b.sold_count || 0) - (a.sold_count || 0));
            box.innerHTML = list.slice(0, 10).map(U.productCard).join('');
        } catch (e) {
            box.innerHTML = '<p style="color:var(--text-muted)">Không thể tải sản phẩm. Hãy kiểm tra Backend.</p>';
        }
    }

    loadServices();
    loadProducts();
    document.addEventListener('unisex:order-placed', loadProducts);
})();