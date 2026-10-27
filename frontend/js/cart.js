/* ==========================================================
   js/cart.js - Giỏ hàng dùng chung cho TẤT CẢ trang
   - Tự chèn nút giỏ hàng ở góc phải trên cùng header (.navbar)
   - Drawer giỏ hàng: thêm / sửa số lượng / xoá / thanh toán
   - Helper dùng chung: window.UNISEX (card sản phẩm, sao, toast...)
   Nạp file này TRƯỚC main.js / products.js / detail.js
   ========================================================== */
(function () {
    'use strict';

    const API = window.UNISEX_API || 'http://localhost:8000/api';
    const KEY = 'unisex_cart_v1';
    const reg = {}; // id -> product (để nút "Thêm" ở card tìm lại dữ liệu)

    /* ---------------- Helpers ---------------- */
    const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
    const fmt = n => (Number(n) || 0).toLocaleString('vi-VN') + ' đ';
    const errMsg = d => {
        if (!d) return 'Có lỗi xảy ra, vui lòng thử lại';
        if (typeof d.detail === 'string') return d.detail;
        if (Array.isArray(d.detail)) return d.detail.map(x => x.msg).join('; ');
        return 'Có lỗi xảy ra, vui lòng thử lại';
    };

    function starsHTML(avg) {
        const a = Number(avg) || 0;
        const w = Math.max(0, Math.min(100, a / 5 * 100));
        return `<span class="stars" title="${a.toFixed(1)}/5"><span class="stars-fill" style="width:${w}%">★★★★★</span></span>`;
    }

    // Dòng: ★★★★☆ 4.8 (120) • Đã bán 350
    function ratingRow(p, big) {
        const cnt = Number(p.rating_count) || 0;
        const avg = Number(p.rating_avg) || 0;
        const sold = Number(p.sold_count) || 0;
        const left = cnt > 0
            ? `${starsHTML(avg)} <b>${avg.toFixed(1)}</b> <span>(${cnt}${big ? ' đánh giá' : ''})</span>`
            : `${starsHTML(0)} <span>Chưa có đánh giá</span>`;
        return `<div class="rating-row${big ? ' big' : ''}">${left}<span class="dot">•</span><span>Đã bán ${sold.toLocaleString('vi-VN')}</span></div>`;
    }

    function productCard(p) {
        reg[p.id] = p;
        const out = (Number(p.stock) || 0) <= 0;
        const link = `product-detail.html?id=${encodeURIComponent(p.id)}`;
        return `
        <div class="product-card" data-uc="1">
            <div class="card-content">
                <a class="card-img-wrap" href="${link}"><img src="${esc(p.img)}" alt="${esc(p.name)}" loading="lazy"></a>
                <div class="pc-meta text-ellipsis-1">${esc(p.brand)} · ${esc(p.type)}</div>
                <h3 class="pc-name text-ellipsis-2"><a href="${link}">${esc(p.name)}</a></h3>
                ${ratingRow(p)}
                <div class="pc-price">${fmt(p.price)} ${out ? '<span class="out-tag">Hết hàng</span>' : ''}</div>
            </div>
            <div class="card-footer-actions row">
                <a class="btn-outline" href="${link}">Chi tiết</a>
                <button type="button" class="btn-primary${out ? ' is-out' : ''}" ${out ? 'disabled' : ''}
                    onclick="UNISEX.addToCart('${esc(p.id)}', this)"><i class="fas fa-cart-plus"></i> Thêm vào giỏ</button>
            </div>
        </div>`;
    }

    /* ---------------- Toast ---------------- */
    let toastWrap;
    function toast(msg, type) {
        if (!toastWrap) {
            toastWrap = document.createElement('div');
            toastWrap.className = 'u-toast-wrap';
            document.body.appendChild(toastWrap);
        }
        const t = document.createElement('div');
        t.className = 'u-toast ' + (type || '');
        t.textContent = msg;
        toastWrap.appendChild(t);
        setTimeout(() => { t.classList.add('hide'); setTimeout(() => t.remove(), 300); }, 2600);
    }

    /* ---------------- Cart data ---------------- */
    const Cart = {
        items() {
            try { const a = JSON.parse(localStorage.getItem(KEY)); return Array.isArray(a) ? a : []; }
            catch (e) { return []; }
        },
        _save(a) {
            try { localStorage.setItem(KEY, JSON.stringify(a)); } catch (e) { }
            refresh();
        },
        count() { return this.items().reduce((s, i) => s + i.qty, 0); },
        subtotal() { return this.items().reduce((s, i) => s + i.price * i.qty, 0); },
        add(p, qty) {
            qty = Math.max(1, parseInt(qty) || 1);
            const stock = Number(p.stock) || 0;
            if (stock <= 0) { toast('Sản phẩm đã hết hàng', 'error'); return false; }
            const a = this.items();
            const ex = a.find(i => i.id === p.id);
            const cur = ex ? ex.qty : 0;
            const next = Math.min(cur + qty, stock);
            if (next === cur) { toast(`Chỉ còn ${stock} sản phẩm trong kho`, 'error'); return false; }
            if (ex) { ex.qty = next; ex.stock = stock; ex.price = p.price; }
            else a.push({
                id: p.id, name: p.name, brand: p.brand, type: p.type,
                img: p.img || (p.images || [])[0] || '', price: p.price, stock, qty: next
            });
            this._save(a);
            bump();
            toast(next < cur + qty ? `Đã thêm (tối đa ${stock} sản phẩm trong kho)` : 'Đã thêm vào giỏ hàng ✓', 'success');
            return true;
        },
        setQty(id, q) {
            let a = this.items();
            const it = a.find(i => i.id === id);
            if (!it) return;
            q = parseInt(q) || 0;
            if (q <= 0) a = a.filter(i => i.id !== id);
            else {
                if (q > it.stock) { toast(`Chỉ còn ${it.stock} sản phẩm trong kho`, 'error'); q = it.stock; }
                it.qty = q;
            }
            this._save(a);
        },
        remove(id) { this._save(this.items().filter(i => i.id !== id)); },
        clear() { this._save([]); }
    };

    /* ---------------- UI ---------------- */
    let btn, badge, overlay, drawer;
    let view = 'cart';      // cart | checkout | success
    let payMethod = 'cod';          // cod | card | banking
    const co = { coupon: '', points: 0, phoneSrc: 'account', pv: null, me: null, coupons: [] };
    const tok = () => localStorage.getItem('token') || '';
    const num = n => (Number(n) || 0).toLocaleString('vi-VN');
    async function req(path, opt) {
        opt = opt || {};
        const h = { 'Content-Type': 'application/json' };
        if (tok()) h.Authorization = 'Bearer ' + tok();
        let res;
        try {
            res = await fetch(API + path, {
                method: opt.method || (opt.body ? 'POST' : 'GET'), headers: h,
                body: opt.body ? JSON.stringify(opt.body) : undefined
            });
        } catch (e) { throw new Error('Không thể kết nối máy chủ'); }
        let d = null; try { d = await res.json(); } catch (e) { }
        if (!res.ok) {
            if (res.status === 401 && tok()) {
                ['token', 'uid', 'userRole', 'userName', 'userPhone', 'userEmail'].forEach(k => localStorage.removeItem(k));
                throw new Error('Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại');
            }
            throw new Error(errMsg(d));
        }
        return d;
    }
    let lastOrder = null;
    let busy = false;
    const isOpen = () => drawer && drawer.classList.contains('open');

    function ensureFontAwesome() {
        if (!document.querySelector('link[href*="font-awesome"]')) {
            const l = document.createElement('link');
            l.rel = 'stylesheet';
            l.href = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css';
            document.head.appendChild(l);
        }
    }

    function build() {
        ensureFontAwesome();
        btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'cart-btn';
        btn.setAttribute('aria-label', 'Giỏ hàng');
        btn.innerHTML = '<i class="fas fa-shopping-cart"></i><span class="cart-badge hidden">0</span>';
        badge = btn.querySelector('.cart-badge');
        btn.addEventListener('click', () => open('cart'));

        // Đặt cạnh .nav-actions (không nằm trong đó để các script ghi đè innerHTML không làm mất nút)
        const navbar = document.querySelector('.navbar');
        const na = navbar && navbar.querySelector('.nav-actions');
        if (na) {
            const wrap = document.createElement('div');
            wrap.className = 'nav-right';
            na.parentNode.insertBefore(wrap, na);
            wrap.appendChild(na);
            wrap.appendChild(btn);
        } else if (navbar) {
            navbar.appendChild(btn);
        } else {
            btn.style.cssText = 'position:fixed;top:14px;right:14px;z-index:200';
            document.body.appendChild(btn);
        }

        overlay = document.createElement('div');
        overlay.className = 'cart-overlay';
        overlay.addEventListener('click', close);
        drawer = document.createElement('aside');
        drawer.className = 'cart-drawer';
        document.body.appendChild(overlay);
        document.body.appendChild(drawer);

        drawer.addEventListener('click', onDrawerClick);
        drawer.addEventListener('submit', e => { if (e.target.id === 'co-form') submitOrder(e); });
        drawer.addEventListener('change', e => {
            const n = e.target.name;
            if (n === 'pay') {
                payMethod = e.target.value;
                drawer.querySelectorAll('.pay-opt[data-g="pay"]').forEach(l =>
                    l.classList.toggle('sel', l.querySelector('input').value === payMethod));
                ['card', 'banking'].forEach(k => {
                    const p = document.getElementById('pp-' + k);
                    if (p) p.classList.toggle('hidden', payMethod !== k);
                });
            } else if (n === 'phsrc') {
                co.phoneSrc = e.target.value;
                drawer.querySelectorAll('.pay-opt[data-g="ph"]').forEach(l =>
                    l.classList.toggle('sel', l.querySelector('input').value === co.phoneSrc));
                const p2 = document.getElementById('co-phone2');
                if (p2) { p2.disabled = co.phoneSrc !== 'custom'; if (!p2.disabled) p2.focus(); }
            } else if (e.target.id === 'co-points') {
                co.points = Math.max(0, parseInt(e.target.value) || 0);
                runPreview();
            }
        });
        drawer.addEventListener('keydown', e => {   // Enter ở ô mã/điểm không được gửi đơn hàng
            if (e.key !== 'Enter') return;
            if (e.target.id === 'co-coupon') { e.preventDefault(); applyCoupon(e.target.value); }
            else if (e.target.id === 'co-points') { e.preventDefault(); e.target.blur(); }
        });
        document.addEventListener('keydown', e => { if (e.key === 'Escape' && isOpen()) close(); });
        window.addEventListener('storage', e => { if (e.key === KEY) refresh(); });
        updateBadge();
    }

    function updateBadge() {
        const n = Cart.count();
        badge.textContent = n > 99 ? '99+' : n;
        badge.classList.toggle('hidden', n === 0);
    }

    function bump() {
        if (!btn) return;
        btn.classList.remove('bump');
        void btn.offsetWidth;
        btn.classList.add('bump');
    }

    function refresh() {
        if (!btn) return;
        updateBadge();
        if (isOpen() && view === 'cart') render();
    }

    function open(v) {
        view = v || 'cart';
        render();
        overlay.classList.add('open');
        drawer.classList.add('open');
        document.body.style.overflow = 'hidden';
    }

    function close() {
        overlay.classList.remove('open');
        drawer.classList.remove('open');
        document.body.style.overflow = '';
    }

    const head = (title, back) => `
        <div class="cd-head">
            ${back ? '<button type="button" class="cd-icon" data-act="back" aria-label="Quay lại"><i class="fas fa-arrow-left"></i></button>' : ''}
            <h3>${title}</h3>
            <button type="button" class="cd-icon" data-act="close" aria-label="Đóng"><i class="fas fa-times"></i></button>
        </div>`;

    function render() {
        if (view === 'checkout') return renderCheckout();
        if (view === 'success') return renderSuccess();
        renderCart();
    }

    function itemHTML(i) {
        const link = `product-detail.html?id=${encodeURIComponent(i.id)}`;
        return `
        <div class="ci">
            <a href="${link}"><img src="${esc(i.img)}" alt=""></a>
            <div class="ci-info">
                <div class="ci-name"><a href="${link}">${esc(i.name)}</a></div>
                <div class="ci-brand">${esc(i.brand)} · ${esc(i.type)}</div>
                <div class="ci-unit">${fmt(i.price)}</div>
                <div class="qty-stepper">
                    <button type="button" data-act="dec" data-id="${esc(i.id)}" aria-label="Giảm">−</button>
                    <span>${i.qty}</span>
                    <button type="button" data-act="inc" data-id="${esc(i.id)}" aria-label="Tăng">+</button>
                </div>
            </div>
            <div class="ci-side">
                <button type="button" class="ci-del" data-act="del" data-id="${esc(i.id)}" title="Xoá khỏi giỏ"><i class="fas fa-trash-alt"></i></button>
                <div class="ci-line">${fmt(i.price * i.qty)}</div>
            </div>
        </div>`;
    }

    function renderCart() {
        const items = Cart.items();
        if (!items.length) {
            drawer.innerHTML = head('Giỏ hàng') + `
                <div class="cd-body"><div class="cd-empty">
                    <i class="fas fa-shopping-basket"></i>
                    <p>Giỏ hàng của bạn đang trống</p>
                </div></div>
                <div class="cd-foot"><a href="products.html" class="btn-primary cd-full">Khám phá sản phẩm</a></div>`;
            return;
        }
        drawer.innerHTML = head(`Giỏ hàng (${Cart.count()})`) + `
            <div class="cd-body">${items.map(itemHTML).join('')}</div>
            <div class="cd-foot">
                <div class="cd-row"><span>Tạm tính (${Cart.count()} sản phẩm)</span><span>${fmt(Cart.subtotal())}</span></div>
                <div class="cd-row total"><span>Tổng cộng</span><strong>${fmt(Cart.subtotal())}</strong></div>
                <button type="button" class="btn-primary cd-full" data-act="checkout">Tiến hành thanh toán</button>
                <button type="button" class="cd-link" data-act="clear">Xoá toàn bộ giỏ hàng</button>
            </div>`;
    }

    async function initCheckout() {
        co.pv = null;
        const jobs = [req('/coupons/public').then(l => { co.coupons = l; }).catch(() => { })];
        if (tok()) jobs.push(req('/auth/me').then(m => { co.me = m; }).catch(e => toast(e.message, 'error')));
        await Promise.all(jobs);
        if (view === 'checkout') { renderCheckout(); runPreview(); }
    }

    function renderCheckout() {
        const logged = !!tok(), me = co.me || {};
        const items = Cart.items();
        const sel = (c, x) => (c === x ? 'sel' : '');
        const contact = logged ? `
            <div class="co-summary"><div><span>Email nhận thông báo</span><span>${esc(me.email || localStorage.getItem('userEmail') || '')}</span></div></div>
            <label class="co-label">Số điện thoại liên hệ *</label>
            <label class="pay-opt ${sel(co.phoneSrc, 'account')}" data-g="ph">
                <input type="radio" name="phsrc" value="account" ${co.phoneSrc === 'account' ? 'checked' : ''}>
                <div><b>${esc(me.phone || localStorage.getItem('userPhone') || '')}</b><small>Số đã đăng ký trong tài khoản</small></div></label>
            <label class="pay-opt ${sel(co.phoneSrc, 'custom')}" data-g="ph">
                <input type="radio" name="phsrc" value="custom" ${co.phoneSrc === 'custom' ? 'checked' : ''}>
                <div style="flex:1"><b>Dùng số khác</b>
                <input type="tel" id="co-phone2" class="form-control" placeholder="090xxxxxxx" style="margin-top:6px" ${co.phoneSrc === 'custom' ? '' : 'disabled'}></div></label>
            <div style="height:.8rem"></div>` : `
            <div class="guest-note"><i class="fas fa-info-circle"></i> Bạn đang mua với tư cách <b>khách</b>: hãy nhập đúng email và số điện thoại để cửa hàng liên hệ, xác nhận đơn và gửi biên lai. Đơn <b>không lưu vào lịch sử</b>, không tích điểm và không thể đánh giá. <a href="login.html?next=products.html">Đăng nhập</a></div>
            <label class="co-label">Số điện thoại *</label>
            <div class="input-with-icon"><i class="fas fa-phone"></i>
                <input type="tel" id="co-phone" class="form-control" required placeholder="090xxxxxxx"></div>
            <label class="co-label">Email *</label>
            <div class="input-with-icon"><i class="fas fa-envelope"></i>
                <input type="email" id="co-email" class="form-control" required placeholder="ban@email.com"></div>`;
        const chips = co.coupons.length ? `<div class="co-chips">${co.coupons.map(c =>
            `<button type="button" data-act="usecoupon" data-code="${esc(c.code)}" title="${esc(c.description)}">${esc(c.code)}</button>`).join('')}</div>` : '';
        const points = logged ? `
            <label class="co-label">Điểm thưởng (hiện có <b id="co-pbal">${num(me.points)}</b> điểm · 1 điểm = 1đ)</label>
            <div class="co-inline"><input type="number" id="co-points" class="form-control" min="0" step="1" placeholder="0" value="${co.points || ''}">
                <button type="button" class="btn-outline" data-act="maxpoints">Dùng tối đa</button></div>
            <div style="height:.8rem"></div>` : '';
        drawer.innerHTML = head('Thanh toán', true) + `
        <form class="cd-form" id="co-form">
            <div class="cd-body">
                <div class="co-summary">
                    ${items.map(i => `<div><span>${esc(i.name)} × ${i.qty}</span><span>${fmt(i.price * i.qty)}</span></div>`).join('')}
                </div>
                <label class="co-label">Họ và tên người nhận *</label>
                <div class="input-with-icon"><i class="fas fa-user"></i>
                    <input type="text" id="co-name" class="form-control" required placeholder="Nguyễn Văn A" value="${esc(me.full_name || localStorage.getItem('userName') || '')}"></div>
                ${contact}
                <label class="co-label">Địa chỉ nhận hàng *</label>
                <div class="input-with-icon"><i class="fas fa-location-dot"></i>
                    <input type="text" id="co-address" class="form-control" required placeholder="Số nhà, đường, phường, quận..."></div>
                <label class="co-label">Ghi chú</label>
                <textarea id="co-note" class="form-control" rows="2" style="margin-bottom:1.2rem" placeholder="Ví dụ: Giao giờ hành chính"></textarea>

                <label class="co-label">Mã giảm giá</label>
                ${chips}
                <div class="co-inline"><input type="text" id="co-coupon" class="form-control" placeholder="Nhập mã" value="${esc(co.coupon)}" style="text-transform:uppercase">
                    <button type="button" class="btn-outline" data-act="applycoupon">Áp dụng</button></div>
                <div class="co-msg" id="co-cmsg"></div>
                ${points}

                <label class="co-label">Hình thức thanh toán *</label>
                <label class="pay-opt ${sel(payMethod, 'cod')}" data-g="pay"><input type="radio" name="pay" value="cod" ${payMethod === 'cod' ? 'checked' : ''}>
                    <div><b>Thanh toán khi nhận hàng (COD)</b><small>Thanh toán tiền mặt cho nhân viên giao hàng</small></div></label>
                <label class="pay-opt ${sel(payMethod, 'card')}" data-g="pay"><input type="radio" name="pay" value="card" ${payMethod === 'card' ? 'checked' : ''}>
                    <div><b>Thẻ tín dụng / ghi nợ</b><small>Giả lập — nhập số bất kỳ, hệ thống không lưu số thẻ</small></div></label>
                <div class="co-sub ${payMethod === 'card' ? '' : 'hidden'}" id="pp-card">
                    <input type="text" id="cc-num" class="form-control" inputmode="numeric" maxlength="23" placeholder="Số thẻ (VD: 4242 4242 4242 4242)">
                    <input type="text" id="cc-name" class="form-control" placeholder="Tên chủ thẻ">
                    <div class="r2"><input type="text" id="cc-exp" class="form-control" maxlength="5" placeholder="MM/YY"><input type="password" id="cc-cvv" class="form-control" maxlength="4" placeholder="CVV"></div>
                </div>
                <label class="pay-opt ${sel(payMethod, 'banking')}" data-g="pay"><input type="radio" name="pay" value="banking" ${payMethod === 'banking' ? 'checked' : ''}>
                    <div><b>Chuyển khoản ngân hàng</b><small>Giả lập — nhập mã giao dịch bất kỳ (hoặc để trống)</small></div></label>
                <div class="co-sub ${payMethod === 'banking' ? '' : 'hidden'}" id="pp-banking">
                    <div class="guest-note" style="margin-bottom:.5rem">Ngân hàng: <b>UNISEX DEMO BANK</b> · STK <b>0123456789</b> · Nội dung: <b>tên + SĐT</b></div>
                    <input type="text" id="bk-ref" class="form-control" placeholder="Mã giao dịch (tuỳ chọn)">
                </div>
            </div>
            <div class="cd-foot">
                <div id="co-totals"></div>
                <button type="submit" class="btn-primary cd-full" id="co-submit">Xác nhận đặt hàng</button>
            </div>
        </form>`;
        renderTotals();
    }

    function renderTotals() {
        const el = document.getElementById('co-totals');
        if (!el) return;
        const sub = Cart.subtotal(), pv = co.pv;
        const disc = pv ? pv.discount : 0, pts = pv ? pv.points_used : 0, total = pv ? pv.total : sub;
        el.innerHTML = `<div class="cd-row"><span>Tạm tính</span><span>${fmt(sub)}</span></div>`
            + (disc ? `<div class="cd-row save"><span>Mã ${esc(pv.coupon_code)}</span><span>− ${fmt(disc)}</span></div>` : '')
            + (pts ? `<div class="cd-row save"><span>Dùng ${num(pts)} điểm</span><span>− ${fmt(pts)}</span></div>` : '')
            + `<div class="cd-row total"><span>Tổng thanh toán</span><strong>${fmt(total)}</strong></div>`
            + (tok() && pv && pv.points_to_earn ? `<div class="cd-row earn"><span>Điểm thưởng dự kiến khi đơn hoàn tất</span><span>+${num(pv.points_to_earn)}</span></div>` : '');
    }

    async function runPreview() {
        const items = Cart.items();
        if (!items.length) return;
        try {
            const d = await req('/orders/preview', { body: { items: items.map(i => ({ product_id: i.id, quantity: i.qty })), coupon_code: co.coupon, points_to_use: co.points } });
            co.pv = d;
            const m = document.getElementById('co-cmsg');
            if (d.coupon_error) { co.coupon = ''; if (m) { m.className = 'co-msg err'; m.textContent = d.coupon_error; } }
            else if (m) { m.className = 'co-msg ok'; m.textContent = d.coupon_code ? `Đã áp dụng mã ${d.coupon_code}: giảm ${fmt(d.discount)}` : ''; }
            if (co.points !== d.points_used) {
                co.points = d.points_used;
                const pi = document.getElementById('co-points'); if (pi) pi.value = d.points_used || '';
            }
            const pb = document.getElementById('co-pbal'); if (pb) pb.textContent = num(d.points_balance);
            renderTotals();
        } catch (e) { toast(e.message, 'error'); }
    }

    function applyCoupon(code) {
        co.coupon = String(code || '').trim().toUpperCase();
        const ci = document.getElementById('co-coupon'); if (ci) ci.value = co.coupon;
        runPreview();
    }

    function renderSuccess() {
        const o = lastOrder || {};
        const paid = o.payment_status === 'paid';
        const guest = !o.customer_id || o.customer_id === 'guest';
        const mail = o.customer_email ? `Thông tin đơn hàng đã được gửi tới <b>${esc(o.customer_email)}</b>. ` : '';
        drawer.innerHTML = head('Đặt hàng thành công') + `
            <div class="cd-body"><div class="cd-center">
                <div class="big-icon"><i class="fas fa-check-circle"></i></div>
                <h3>Cảm ơn bạn đã mua hàng!</h3>
                <div class="order-code">${esc(o.order_code || '')}</div>
                <p style="color:var(--text-muted)">Tổng thanh toán: <strong style="color:var(--gold)">${fmt(o.total)}</strong>
                    ${o.discount ? `<br><small>Đã giảm ${fmt(o.discount)} (mã ${esc(o.coupon_code || '')})</small>` : ''}
                    ${o.points_used ? `<br><small>Đã dùng ${num(o.points_used)} điểm</small>` : ''}</p>
                <p style="color:var(--text-muted);margin-top:.8rem">${mail}${paid
                ? 'Thanh toán thành công — cửa hàng sẽ xác nhận và chuẩn bị đơn hàng.'
                : 'Bạn sẽ thanh toán khi nhận hàng; cửa hàng sẽ liên hệ qua số điện thoại để xác nhận.'}
                ${guest ? '<br>Bạn mua với tư cách khách nên đơn không lưu vào lịch sử cá nhân — hãy ghi lại mã đơn.' : '<br>Theo dõi tiến trình đơn tại Trang cá nhân. Điểm thưởng (1%) được cộng khi đơn hoàn tất.'}</p>
            </div></div>
            <div class="cd-foot">
                ${guest ? '' : '<a href="customer.html" class="btn-outline cd-full" style="margin-bottom:.6rem">Theo dõi đơn hàng</a>'}
                <button type="button" class="btn-primary cd-full" data-act="close">Tiếp tục mua sắm</button>
            </div>`;
    }

    function onDrawerClick(e) {
        const t = e.target.closest('[data-act]');
        if (!t) return;
        const act = t.dataset.act, id = t.dataset.id;
        const it = id ? Cart.items().find(i => i.id === id) : null;
        if (act === 'close') close();
        else if (act === 'back') { view = 'cart'; render(); }
        else if (act === 'inc' && it) Cart.setQty(id, it.qty + 1);
        else if (act === 'dec' && it) Cart.setQty(id, it.qty - 1);
        else if (act === 'del') Cart.remove(id);
        else if (act === 'clear') { if (confirm('Xoá toàn bộ sản phẩm trong giỏ hàng?')) Cart.clear(); }
        else if (act === 'checkout') {
            view = 'checkout';
            drawer.innerHTML = head('Thanh toán', true) + '<div class="cd-body"><div class="cd-empty"><p>Đang tải...</p></div></div>';
            initCheckout();
        }
        else if (act === 'applycoupon') applyCoupon(document.getElementById('co-coupon').value);
        else if (act === 'usecoupon') applyCoupon(t.dataset.code);
        else if (act === 'maxpoints') {
            co.points = (co.pv && co.pv.points_balance) || (co.me && co.me.points) || 0;
            const pi = document.getElementById('co-points'); if (pi) pi.value = co.points || '';
            runPreview();
        }
    }

    async function submitOrder(e) {
        e.preventDefault();
        if (busy) return;
        const items = Cart.items();
        if (!items.length) return;
        const v = id => { const el = document.getElementById(id); return el ? el.value.trim() : ''; };
        const logged = !!tok();
        const payload = {
            customer_name: v('co-name'),
            shipping_address: v('co-address'),
            note: v('co-note'),
            payment_method: payMethod,
            coupon_code: co.coupon,
            points_to_use: logged ? co.points : 0,
            phone_source: logged ? co.phoneSrc : 'custom',
            customer_phone: logged ? (co.phoneSrc === 'custom' ? v('co-phone2') : '') : v('co-phone'),
            customer_email: logged ? '' : v('co-email'),
            items: items.map(i => ({ product_id: i.id, quantity: i.qty }))
        };
        if (logged && co.phoneSrc === 'custom' && !payload.customer_phone) return toast('Vui lòng nhập số điện thoại khác', 'error');
        if (payMethod === 'card') {
            payload.card = { number: v('cc-num'), holder: v('cc-name'), expiry: v('cc-exp'), cvv: v('cc-cvv') };
            if (!payload.card.number || !payload.card.holder || !payload.card.expiry || !payload.card.cvv)
                return toast('Vui lòng nhập đủ thông tin thẻ', 'error');
        }
        if (payMethod === 'banking') payload.bank_ref = v('bk-ref');

        const submit = document.getElementById('co-submit');
        busy = true;
        submit.disabled = true;
        submit.textContent = 'Đang xử lý...';
        try {
            const data = await req('/orders/checkout', { body: payload });
            lastOrder = data.order;
            Cart.clear();
            co.coupon = ''; co.points = 0; co.pv = null;
            view = 'success';
            render();
            document.dispatchEvent(new CustomEvent('unisex:order-placed', { detail: data.order }));
        } catch (err) {
            toast(err.message || 'Không thể kết nối máy chủ', 'error');
            submit.disabled = false;
            submit.textContent = 'Xác nhận đặt hàng';
        } finally {
            busy = false;
        }
    }

    // Đổi link "Đăng nhập" thành "Trang cá nhân" khi đã đăng nhập
    function refreshAuthLink() {
        if (!localStorage.getItem('uid')) return;
        document.querySelectorAll('a.account-link[href="login.html"]').forEach(a => {
            a.href = 'customer.html';
            a.innerHTML = '👤 Trang cá nhân';
            a.style.color = 'var(--gold)';
        });
    }


    /* ---------------- Tự bổ sung sao / lượt mua / nút thêm giỏ cho mọi .product-card ----------------
       (phòng khi trang vẫn đang render card bằng JS cũ) */
    let statsPromise = null;
    function loadStats() {
        if (!statsPromise) {
            statsPromise = fetch(`${API}/catalog/products`).then(r => r.json())
                .then(list => { list.forEach(p => { reg[p.id] = Object.assign(reg[p.id] || {}, p); }); return reg; })
                .catch(() => { statsPromise = null; return reg; });
        }
        return statsPromise;
    }

    async function enhanceCards() {
        const old = [...document.querySelectorAll('.product-card')].filter(c => !c.dataset.uc);
        if (!old.length) return;
        await loadStats();
        const list = Object.values(reg).filter(p => p && p.id && p.name);
        old.forEach(c => {
            if (!c.isConnected) return;
            let p = null;
            const html = c.innerHTML;
            const m = html.match(/product-detail\.html\?id=([^"'&\s]+)/) || html.match(/(prod_\d+)/);
            if (m) p = reg[decodeURIComponent(m[1])];
            if (!p) {   // dự phòng: khớp theo tên sản phẩm
                const h = c.querySelector('h1,h2,h3,h4');
                const name = h && h.textContent.trim();
                p = list.find(x => x.name === name);
            }
            if (!p || !p.price) return;
            const tmp = document.createElement('div');
            tmp.innerHTML = productCard(p).trim();
            c.replaceWith(tmp.firstElementChild);
        });
    }

    let enhTimer;
    function watchCards() {
        const run = () => { clearTimeout(enhTimer); enhTimer = setTimeout(enhanceCards, 120); };
        new MutationObserver(run).observe(document.body, { childList: true, subtree: true });
        run();
    }

    window.UNISEX = {
        API, reg, esc, fmt, errMsg, toast, starsHTML, ratingRow, productCard, Cart,
        openCart: open,
        addToCart(id, el) {
            const p = reg[id];
            if (!p) return;
            if (Cart.add(p, 1) && el && el.tagName === 'BUTTON') {
                const old = el.innerHTML;
                el.innerHTML = '<i class="fas fa-check"></i> Đã thêm';
                el.disabled = true;
                setTimeout(() => { el.innerHTML = old; el.disabled = false; }, 1100);
            }
        }
    };

    function init() { build(); refreshAuthLink(); watchCards(); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();