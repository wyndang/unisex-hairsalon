// js/detail.js
const API_BASE = "http://localhost:8000/api";
const urlParams = new URLSearchParams(window.location.search);
const productId = urlParams.get('id') || 'prod_1';

let currentProduct = null;
let currentSlide = 0;

document.addEventListener('DOMContentLoaded', async () => {
    await loadProductDetail();
});

async function loadProductDetail() {
    try {
        const res = await fetch(`${API_BASE}/catalog/products/${productId}`);
        if (!res.ok) throw new Error("Không tìm thấy sản phẩm");
        currentProduct = await res.json();
        renderSlider();
        renderData();
    } catch (err) {
        document.getElementById('p-name').innerText = "Không tìm thấy sản phẩm";
    }
}

function renderSlider() {
    const track = document.getElementById('slider-track');
    track.innerHTML = '';
    const imgs = currentProduct.images && currentProduct.images.length > 0 ? currentProduct.images : [currentProduct.img];
    imgs.forEach(imgUrl => {
        const img = document.createElement('img');
        img.src = imgUrl;
        track.appendChild(img);
    });
}

function moveSlide(dir) {
    const imgs = currentProduct.images && currentProduct.images.length > 0 ? currentProduct.images : [currentProduct.img];
    const total = imgs.length;
    currentSlide = (currentSlide + dir + total) % total;
    document.getElementById('slider-track').style.transform = `translateX(-${currentSlide * 100}%)`;
}

function renderData() {
    document.getElementById('p-name').innerText = currentProduct.name;
    document.getElementById('p-meta').innerText = `${currentProduct.brand} • ${currentProduct.type} • ${currentProduct.volume}`;
    document.getElementById('p-price').innerText = currentProduct.price.toLocaleString('vi-VN') + ' đ';
    document.getElementById('p-desc').innerText = currentProduct.desc;
    document.getElementById('p-origin').innerText = currentProduct.origin || 'Chính hãng';
    document.getElementById('p-usage').innerText = currentProduct.usage || 'Thoa đều lên tóc.';

    const reviews = currentProduct.reviews || [];
    document.getElementById('total-reviews').innerText = `${reviews.length} đánh giá`;
    if (reviews.length > 0) {
        const avg = (reviews.reduce((s, r) => s + r.stars, 0) / reviews.length).toFixed(1);
        document.getElementById('avg-rating').innerText = avg;
    }

    const list = document.getElementById('reviews-list');
    list.innerHTML = reviews.length === 0 ? `<p style="color:var(--text-muted);">Chưa có đánh giá nào.</p>` : '';
    reviews.forEach(r => {
        list.innerHTML += `
            <div class="review-card">
                <div style="display:flex; justify-content:space-between; margin-bottom:0.3rem;">
                    <strong>${r.customer_name}</strong>
                    <span style="color:var(--gold);">${'★'.repeat(r.stars)}</span>
                </div>
                <p style="color:var(--text-light);">${r.comment}</p>
            </div>
        `;
    });
}

async function submitReview(e) {
    e.preventDefault();
    const uid = localStorage.getItem('uid') || 'guest';
    const userName = localStorage.getItem('userName') || 'Khách hàng';
    const stars = parseInt(document.getElementById('review-stars').value);
    const comment = document.getElementById('review-text').value;

    const res = await fetch(`${API_BASE}/catalog/products/${productId}/reviews`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ customer_id: uid, customer_name: userName, stars, comment })
    });
    if (res.ok) {
        document.getElementById('review-text').value = '';
        await loadProductDetail();
        alert("Cảm ơn bạn đã đánh giá sản phẩm!");
    }
}

function addToCartCurrent() {
    if (!currentProduct) return;
    let cart = JSON.parse(localStorage.getItem('salonCart') || '[]');
    const existing = cart.find(i => i.product_id === currentProduct.id);
    if (existing) existing.quantity += 1;
    else cart.push({
        product_id: currentProduct.id,
        name: currentProduct.name,
        price: currentProduct.price,
        img: currentProduct.img || currentProduct.images[0],
        quantity: 1
    });
    localStorage.setItem('salonCart', JSON.stringify(cart));
    alert(`Đã thêm "${currentProduct.name}" vào giỏ hàng!`);
}
/* js/detail.js - Chi tiết sản phẩm: slider, thêm giỏ hàng, đánh giá (chỉ người đã mua) */
(function () {
    const U = window.UNISEX;
    const $ = id => document.getElementById(id);
    const pid = new URLSearchParams(location.search).get('id');
    let product = null, idx = 0, total = 1;

    async function load() {
        if (!pid) { $('p-name').textContent = 'Không tìm thấy sản phẩm'; return; }
        try {
            const res = await fetch(`${U.API}/catalog/products/${encodeURIComponent(pid)}`);
            if (!res.ok) throw new Error();
            product = await res.json();
            U.reg[product.id] = product;
            renderProduct();
            renderReviews();
            await setupReviewForm();
        } catch (e) {
            $('p-name').textContent = 'Không tải được sản phẩm';
        }
    }

    function renderProduct() {
        const p = product;
        document.title = `${p.name} - UNISEX Salon`;
        const imgs = (p.images && p.images.length) ? p.images : [p.img];
        total = imgs.length;
        idx = 0;
        $('slider-track').innerHTML = imgs.map(u => `<img src="${U.esc(u)}" alt="${U.esc(p.name)}">`).join('');
        document.querySelectorAll('.slider-btn').forEach(b => b.style.display = total > 1 ? '' : 'none');
        moveSlide(0);

        $('p-meta').textContent = `${p.brand} · ${p.type} · ${p.volume}`;
        $('p-name').textContent = p.name;
        $('p-price').textContent = U.fmt(p.price);
        $('p-stats').innerHTML = U.ratingRow(p, true);
        $('p-desc').textContent = p.desc || '';
        $('p-origin').textContent = p.origin || '';
        $('p-usage').textContent = p.usage || '';

        const stock = Number(p.stock) || 0;
        $('p-stock').innerHTML = stock > 0 ? `Còn ${stock} sản phẩm` : '<span class="out-tag">Hết hàng</span>';
        $('d-qty').max = stock;
        $('d-qty').value = stock > 0 ? 1 : 0;
    }

    function moveSlide(d) {
        idx = (idx + d + total) % total;
        $('slider-track').style.transform = `translateX(-${idx * 100}%)`;
    }

    function changeQty(d) {
        const stock = Number(product && product.stock) || 0;
        const el = $('d-qty');
        let v = (parseInt(el.value) || 1) + d;
        v = Math.max(1, Math.min(v, Math.max(stock, 1)));
        el.value = v;
    }

    function addToCartCurrent() {
        if (!product) return;
        U.Cart.add(product, parseInt($('d-qty').value) || 1);
    }

    function renderReviews() {
        const p = product;
        const cnt = Number(p.rating_count) || 0;
        $('avg-rating').textContent = cnt ? Number(p.rating_avg).toFixed(1) : '—';
        $('total-reviews').textContent = `${cnt} đánh giá`;
        const list = p.reviews || [];
        $('reviews-list').innerHTML = list.length ? list.map(r => `
            <div class="review-item">
                <div class="rv-head">
                    <strong>${U.esc(r.customer_name)}</strong>
                    ${U.starsHTML(r.stars)}
                    <span class="verified-badge"><i class="fas fa-check-circle"></i> Đã mua hàng</span>
                    <span class="rv-date">${r.created_at ? new Date(r.created_at).toLocaleDateString('vi-VN') : ''}</span>
                </div>
                <p style="color:var(--text-light)">${U.esc(r.comment)}</p>
            </div>`).join('')
            : '<p style="color:var(--text-muted)">Chưa có đánh giá nào cho sản phẩm này.</p>';
    }

    // Chỉ hiện form khi khách đã mua & thanh toán thành công (server kiểm tra lại khi gửi)
    async function setupReviewForm() {
        const uid = localStorage.getItem('uid'), token = localStorage.getItem('token');
        const notice = $('review-notice'), form = $('review-form');
        form.style.display = 'none';
        notice.style.display = 'block';
        if (!uid || !token) {
            notice.innerHTML = '🔒 Vui lòng <a href="login.html">đăng nhập</a> để gửi đánh giá. Chỉ khách hàng đã mua và thanh toán thành công sản phẩm này mới được đánh giá.';
            return;
        }
        try {
            const res = await fetch(`${U.API}/catalog/products/${encodeURIComponent(pid)}/can-review`, { headers: { Authorization: 'Bearer ' + token } });
            if (res.status === 401) { notice.innerHTML = 'Phiên đăng nhập đã hết hạn. Vui lòng <a href="login.html">đăng nhập lại</a>.'; return; }
            const r = await res.json();
            if (r.can_review) {
                notice.style.display = 'none';
                form.style.display = 'block';
            } else if (r.reason === 'already_reviewed') {
                notice.textContent = '✅ Bạn đã đánh giá sản phẩm này. Cảm ơn bạn!';
            } else {
                notice.textContent = '🛍️ Chỉ khách hàng đã mua và thanh toán thành công sản phẩm này mới có thể gửi đánh giá.';
            }
        } catch (e) {
            notice.textContent = 'Không thể kiểm tra quyền đánh giá lúc này.';
        }
    }

    async function submitReview(e) {
        e.preventDefault();
        const token = localStorage.getItem('token');
        if (!token) return;
        const payload = {
            stars: parseInt($('review-stars').value),
            comment: $('review-text').value.trim()
        };
        try {
            const res = await fetch(`${U.API}/catalog/products/${encodeURIComponent(pid)}/reviews`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (!res.ok) throw new Error(U.errMsg(data));
            U.toast('Cảm ơn bạn đã đánh giá!', 'success');
            $('review-text').value = '';
            load();
        } catch (err) {
            U.toast(err.message || 'Không thể gửi đánh giá', 'error');
        }
    }

    window.moveSlide = moveSlide;
    window.changeQty = changeQty;
    window.addToCartCurrent = addToCartCurrent;
    window.submitReview = submitReview;
    document.addEventListener('unisex:order-placed', load);
    load();
})();