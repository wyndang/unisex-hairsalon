// js/products.js
const API_BASE = "http://localhost:8000/api";
let allProducts = [];

document.addEventListener('DOMContentLoaded', async () => {
    const role = localStorage.getItem('userRole');
    const fullName = localStorage.getItem('userName') || 'Như Quỳnh';
    if (role) {
        document.getElementById('auth-section').innerHTML = `
            <div onclick="window.location.href='customer.html'" style="display: flex; align-items: center; gap: 10px; cursor:pointer;">
                <img src="https://ui-avatars.com/api/?name=${encodeURIComponent(fullName)}&background=f5a623&color=fff" style="width: 35px; border-radius: 50%;">
                <span style="color: var(--text-light); font-size: 0.9rem;">${fullName}</span>
            </div>
            <a href="booking.html" class="btn-primary">Book an Appointment</a>
        `;
    }

    try {
        const res = await fetch(`${API_BASE}/catalog/products`);
        allProducts = await res.json();
        renderProducts(allProducts);
    } catch (e) {
        document.getElementById('product-count').innerText = "Không thể kết nối Backend FastAPI.";
    }
});

function renderProducts(productsArray) {
    const container = document.getElementById('main-products-container');
    const countLabel = document.getElementById('product-count');

    container.innerHTML = '';
    countLabel.innerText = `Hiển thị ${productsArray.length} sản phẩm`;

    if (productsArray.length === 0) {
        container.innerHTML = `<div class="no-result"><h3>Không tìm thấy sản phẩm phù hợp.</h3></div>`;
        return;
    }

    productsArray.forEach(prod => {
        const imgUrl = prod.img || (prod.images && prod.images[0]);
        container.innerHTML += `
            <div class="product-card">
                <div class="card-content">
                    <div class="card-img-wrap">
                        <img src="${imgUrl}" alt="${prod.name}">
                    </div>
                    <span class="text-ellipsis-1" style="font-size:0.75rem; color:var(--gold);" title="${prod.brand} • ${prod.type} • ${prod.volume}">${prod.brand} • ${prod.type} • ${prod.volume}</span>
                    <h3 class="text-ellipsis-2" style="font-size:1.05rem; margin:0.3rem 0; color:#fff;" title="${prod.name}">${prod.name}</h3>
                    <div style="color:var(--gold); font-weight:bold; font-size:1.15rem; margin-top:auto; padding-top:0.5rem;">${prod.price.toLocaleString('vi-VN')} đ</div>
                </div>
                <div class="card-footer-actions">
                    <button class="btn-outline" style="width:100%; padding:9px;" onclick="window.location.href='product-detail.html?id=${prod.id}'">Xem chi tiết</button>
                </div>
            </div>
        `;
    });
}

function applyFilters() {
    let filtered = [...allProducts];

    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
    if (searchTerm) {
        filtered = filtered.filter(p => p.name.toLowerCase().includes(searchTerm) || p.brand.toLowerCase().includes(searchTerm));
    }

    const checkedTypes = Array.from(document.querySelectorAll('.type-filter:checked')).map(cb => cb.value);
    if (checkedTypes.length > 0) filtered = filtered.filter(p => checkedTypes.includes(p.type));

    const checkedBrands = Array.from(document.querySelectorAll('.brand-filter:checked')).map(cb => cb.value);
    if (checkedBrands.length > 0) filtered = filtered.filter(p => checkedBrands.includes(p.brand));

    const sortVal = document.getElementById('sortSelect').value;
    if (sortVal === 'price-asc') filtered.sort((a, b) => a.price - b.price);
    else if (sortVal === 'price-desc') filtered.sort((a, b) => b.price - a.price);
    else if (sortVal === 'name-asc') filtered.sort((a, b) => a.name.localeCompare(b.name));

    renderProducts(filtered);
}
/* js/products.js - Trang tất cả sản phẩm: lọc, tìm kiếm, sắp xếp (kèm sao & lượt mua) */
(function () {
    const U = window.UNISEX;
    let all = [];

    // Bỏ dấu tiếng Việt để tìm kiếm dễ hơn
    const norm = s => String(s || '').toLowerCase().normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd');

    async function load() {
        const countEl = document.getElementById('product-count');
        try {
            const res = await fetch(`${U.API}/catalog/products`);
            all = await res.json();
            applyFilters();
        } catch (e) {
            countEl.textContent = 'Không thể tải sản phẩm. Hãy chắc chắn Backend đang chạy.';
        }
    }

    function applyFilters() {
        const kw = norm(document.getElementById('searchInput').value.trim());
        const types = [...document.querySelectorAll('.type-filter:checked')].map(c => c.value);
        const brands = [...document.querySelectorAll('.brand-filter:checked')].map(c => c.value);
        const sort = document.getElementById('sortSelect').value;

        let list = all.filter(p =>
            (!kw || norm(`${p.name} ${p.brand} ${p.type}`).includes(kw)) &&
            (!types.length || types.includes(p.type)) &&
            (!brands.length || brands.includes(p.brand)));

        const by = {
            'price-asc': (a, b) => a.price - b.price,
            'price-desc': (a, b) => b.price - a.price,
            'name-asc': (a, b) => a.name.localeCompare(b.name, 'vi'),
            'sold-desc': (a, b) => (b.sold_count || 0) - (a.sold_count || 0),
            'rating-desc': (a, b) => (b.rating_avg || 0) - (a.rating_avg || 0) || (b.rating_count || 0) - (a.rating_count || 0)
        }[sort];
        if (by) list.sort(by);

        document.getElementById('product-count').textContent = `Hiển thị ${list.length} / ${all.length} sản phẩm`;
        document.getElementById('main-products-container').innerHTML = list.length
            ? list.map(U.productCard).join('')
            : '<p style="color:var(--text-muted);grid-column:1/-1;text-align:center;padding:3rem 0">Không tìm thấy sản phẩm phù hợp.</p>';
    }

    window.applyFilters = applyFilters;
    document.addEventListener('unisex:order-placed', load);
    load();
})();