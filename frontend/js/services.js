// js/services.js
const API_BASE = "http://localhost:8000/api";
let allServices = [];
let currentModalService = null;
let selectedTierId = "basic";

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
        const res = await fetch(`${API_BASE}/catalog/services`);
        allServices = await res.json();
        renderServices(allServices);

        // Nếu trên URL có ?detail=svc_1 thì mở sẵn Modal
        const params = new URLSearchParams(window.location.search);
        const detailId = params.get('detail');
        if (detailId) openServiceModal(detailId, 'basic');
    } catch (e) {
        document.getElementById('service-count').innerText = "Lỗi kết nối máy chủ FastAPI";
    }
});

function renderServices(list) {
    const container = document.getElementById('main-services-container');
    document.getElementById('service-count').innerText = `Hiển thị ${list.length} dịch vụ`;
    container.innerHTML = '';

    list.forEach(svc => {
        const tiersHTML = (svc.tiers || []).map(t => `
            <button class="btn-outline" style="padding:5px 8px; font-size:0.75rem; width:100%; margin-bottom:4px; text-align:left; display:flex; justify-content:space-between;"
                onclick="openServiceModal('${svc.id}', '${t.tier_id}')">
                <span class="text-ellipsis-1">${t.tier_name.split(' (')[0]}</span>
                <strong style="color:var(--gold);">${t.price.toLocaleString('vi-VN')}đ</strong>
            </button>
        `).join('');

        container.innerHTML += `
            <div class="service-card">
                <div class="card-content">
                    <div class="card-img-wrap">
                        <img src="${svc.img_url}" alt="${svc.name}">
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:var(--gold);">
                        <span class="text-ellipsis-1">${svc.category}</span>
                        <span>⏱ ${svc.duration_minutes} phút</span>
                    </div>
                    <h3 class="text-ellipsis-2" style="font-size:1.05rem; margin:0.3rem 0; color:#fff;" title="${svc.name}">${svc.name}</h3>
                    <p class="text-ellipsis-2" style="color:var(--text-muted); font-size:0.8rem; margin-bottom:0.5rem;" title="${svc.desc}">${svc.desc}</p>
                    <div style="margin-top:auto;">
                        <small style="color:#aaa; display:block; margin-bottom:3px; font-size:0.72rem;">Chọn mức giá xem Ưu/Nhược điểm:</small>
                        ${tiersHTML}
                    </div>
                </div>
                <div class="card-footer-actions">
                    <button class="btn-primary" style="width:100%; padding:9px;" onclick="window.location.href='booking.html?service_id=${svc.id}'">Book an appointment</button>
                </div>
            </div>
        `;
    });
}

function openServiceModal(serviceId, defaultTierId = 'basic') {
    currentModalService = allServices.find(s => s.id === serviceId);
    if (!currentModalService) return;

    document.getElementById('m-category').innerText = `${currentModalService.category} • ⏱ ${currentModalService.duration_minutes} phút`;
    document.getElementById('m-title').innerText = currentModalService.name;
    document.getElementById('m-desc').innerText = currentModalService.desc;

    selectModalTier(defaultTierId);
    document.getElementById('service-detail-modal').style.display = 'flex';
}

function selectModalTier(tierId) {
    selectedTierId = tierId;
    const tiers = currentModalService.tiers || [];
    const tabsContainer = document.getElementById('m-tier-tabs');
    tabsContainer.innerHTML = '';

    tiers.forEach(t => {
        const isActive = t.tier_id === tierId ? 'active' : '';
        tabsContainer.innerHTML += `
            <div class="tier-btn ${isActive}" onclick="selectModalTier('${t.tier_id}')">
                <div style="font-weight:bold; margin-bottom:5px;">${t.tier_name.split(' (')[0]}</div>
                <div style="color:var(--gold); font-size:1.2rem; font-weight:bold;">${t.price.toLocaleString('vi-VN')} đ</div>
                <small style="color:#aaa;">${t.product_line}</small>
            </div>
        `;
    });

    const activeTier = tiers.find(t => t.tier_id === tierId) || tiers[0];
    document.getElementById('t-name').innerText = activeTier.tier_name;
    document.getElementById('t-line').innerText = activeTier.product_line;
    document.getElementById('t-pros').innerText = activeTier.pros;
    document.getElementById('t-cons').innerText = activeTier.cons;
    document.getElementById('m-selected-price').innerText = activeTier.price.toLocaleString('vi-VN') + ' đ';

    document.getElementById('m-book-btn').onclick = () => {
        window.location.href = `booking.html?service_id=${currentModalService.id}&tier_id=${activeTier.tier_id}`;
    };
}

function closeServiceModal() {
    document.getElementById('service-detail-modal').style.display = 'none';
}

function applyServiceFilters() {
    let filtered = [...allServices];
    const q = document.getElementById('serviceSearch').value.toLowerCase();
    if (q) filtered = filtered.filter(s => s.name.toLowerCase().includes(q) || s.desc.toLowerCase().includes(q));

    const cats = Array.from(document.querySelectorAll('.svc-cat-filter:checked')).map(cb => cb.value);
    if (cats.length > 0) filtered = filtered.filter(s => cats.includes(s.category));

    const sortVal = document.getElementById('serviceSort').value;
    if (sortVal === 'price-asc') filtered.sort((a, b) => a.price - b.price);
    else if (sortVal === 'price-desc') filtered.sort((a, b) => b.price - a.price);
    else if (sortVal === 'dur-asc') filtered.sort((a, b) => a.duration_minutes - b.duration_minutes);

    renderServices(filtered);
}