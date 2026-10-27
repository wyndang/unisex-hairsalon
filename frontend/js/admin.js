/* js/admin.js - Màn hình quản trị UNISEX Salon */
(function () {
    'use strict';
    const A = window.UAuth;
    if (!A || !A.token() || !['owner', 'staff'].includes(A.role())) { location.href = 'login.html?next=admin.html'; return; }
    const OWNER = A.role() === 'owner';
    const $ = id => document.getElementById(id);
    const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const fmt = n => (Number(n) || 0).toLocaleString('vi-VN') + ' đ';
    const num = n => (Number(n) || 0).toLocaleString('vi-VN');
    const dt = x => x ? new Date(x).toLocaleString('vi-VN') : '';
    const api = (path, method, body) => method ? A.api(path, { method, body }) : A.api(path);
    function toast(msg, type) {
        const t = document.createElement('div'); t.className = 'adm-toast ' + (type || ''); t.textContent = msg;
        $('toasts').appendChild(t); setTimeout(() => t.remove(), 3200);
    }
    const fail = e => toast(e.message || 'Có lỗi xảy ra', 'error');
    $('who').textContent = `${localStorage.userName || ''} · ${OWNER ? 'Quản trị viên' : 'Nhân viên'}`;

    const OST = { pending_confirm: 'Chờ xác nhận', preparing: 'Chờ lấy hàng', shipping: 'Chờ giao hàng', completed: 'Hoàn tất', cancelled: 'Đã huỷ' };
    const NEXT = { pending_confirm: ['preparing', 'Xác nhận đơn'], preparing: ['shipping', 'Bàn giao vận chuyển'], shipping: ['completed', 'Đã giao - Hoàn tất'] };
    const PAYS = { pending: 'Chưa thanh toán', paid: 'Đã thanh toán', cancelled: 'Đã huỷ', refunded: 'Đã hoàn tiền' };
    const PAY = { cod: 'COD', card: 'Thẻ', banking: 'Chuyển khoản' };
    const BST = { confirmed: 'Đã xác nhận (trả tại quầy)', pending_payment: 'Chờ thanh toán', paid: 'Đã trả trước', completed: 'Đã thực hiện', cancelled: 'Đã huỷ' };
    const ACTIVE = ['confirmed', 'pending_payment', 'paid'];
    const ROLES = [['customer', 'Khách hàng'], ['staff', 'Nhân viên (staff)'], ['owner', 'Quản trị viên (owner)']];
    const CATS = ['Cắt & Tạo kiểu', 'Gội & Thư giãn', 'Phục hồi', 'Uốn tóc', 'Duỗi tóc', 'Nhuộm tóc'];
    const PTYPES = ['Dầu gội', 'Dầu xả', 'Dầu dưỡng', 'Sáp vuốt tóc', 'Kem ủ & Huyết thanh'];

    const MENU = [
        { k: 'dash', i: 'fa-chart-line', l: 'Tổng quan & Doanh thu', o: 1 },
        { k: 'orders', i: 'fa-box', l: 'Đơn hàng', b: 'pending_orders' },
        { k: 'bookings', i: 'fa-calendar-check', l: 'Booking', b: 'upcoming_bookings' },
        { k: 'services', i: 'fa-scissors', l: 'Dịch vụ', o: 1 },
        { k: 'products', i: 'fa-bottle-droplet', l: 'Sản phẩm', o: 1 },
        { k: 'coupons', i: 'fa-ticket', l: 'Mã giảm giá', o: 1 },
        { k: 'staffs', i: 'fa-user-tie', l: 'Nhân viên (Stylist)', o: 1 },
        { k: 'users', i: 'fa-users', l: 'Tài khoản', o: 1 },
        { k: 'notifs', i: 'fa-bell', l: 'Thông báo', b: 'unread' }
    ].filter(m => OWNER || !m.o);
    let cur = '';

    $('menu').innerHTML = MENU.map(m => `<button data-k="${m.k}"><i class="fas ${m.i}"></i>${m.l}${m.b ? `<span class="nb" id="nb-${m.b}"></span>` : ''}</button>`).join('');
    $('menu').addEventListener('click', e => { const b = e.target.closest('button'); if (b) go(b.dataset.k); });

    function go(k) {
        cur = k; location.hash = k;
        $('side').classList.remove('open');
        document.querySelectorAll('#menu button').forEach(b => b.classList.toggle('on', b.dataset.k === k));
        $('title').textContent = MENU.find(m => m.k === k).l;
        render();
    }
    async function render() {
        const box = $('view'); box.innerHTML = '<p class="muted">Đang tải...</p>';
        try { await VIEWS[cur](box); } catch (e) { box.innerHTML = ''; fail(e); }
    }
    async function loadBadges() {
        try {
            const b = await api('/manage/badges');
            Object.entries(b).forEach(([k, v]) => { const el = $('nb-' + k); if (el) { el.textContent = v; el.classList.toggle('show', v > 0); } });
        } catch (e) { /* bỏ qua */ }
    }
    async function act(path, method, body, ok) {
        try { await api(path, method, body); toast(ok || 'Đã cập nhật', 'success'); loadBadges(); render(); } catch (e) { fail(e); }
    }
    function modal(title, html, cls) {
        const m = document.createElement('div'); m.className = 'modal';
        m.innerHTML = `<div class="modal-box ${cls || ''}"><div class="modal-head"><h3>${title}</h3><button aria-label="Đóng">✕</button></div><div class="mbody">${html}</div></div>`;
        m.addEventListener('mousedown', e => { m._down = e.target === m; });
        m.addEventListener('click', e => { if ((e.target === m && m._down) || e.target.closest('.modal-head button')) m.remove(); });
        document.body.appendChild(m); return m;
    }
    function csv(rows, name) {
        const body = rows.map(r => r.map(c => `"${String(c == null ? '' : c).replace(/"/g, '""')}"`).join(',')).join('\n');
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob(['\ufeff' + body], { type: 'text/csv;charset=utf-8' }));
        a.download = name; a.click();
    }

    /* ======================= TỔNG QUAN ======================= */
    let lastStats = null;
    async function vDash(box) {
        const days = +(sessionStorage.admDays || 30);
        const d = lastStats = await api('/manage/stats?days=' + days);
        const max = Math.max(1, ...d.by_day.map(x => x.shop + x.service));
        const rank = (arr, f) => arr.map(x => `<div class="line"><span>${esc(x.name)}</span><span>${f(x)}</span></div>`).join('') || '<p class="muted">Chưa có dữ liệu.</p>';
        box.innerHTML = `
        <div class="adm-bar"><span class="muted">Biểu đồ:</span>
            <select class="form-control" onchange="AD.days(this.value)">${[7, 30, 90].map(n => `<option value="${n}" ${n === days ? 'selected' : ''}>${n} ngày gần nhất</option>`).join('')}</select>
            <button class="btn-sm" onclick="AD.csvStats()"><i class="fas fa-download"></i> Xuất CSV</button></div>
        <div class="kpis">
            <div class="kpi">Tổng doanh thu<b>${fmt(d.total_revenue)}</b></div>
            <div class="kpi">Doanh thu bán hàng (${d.paid_orders} đơn)<b>${fmt(d.shop_revenue)}</b></div>
            <div class="kpi">Doanh thu dịch vụ (${d.bookings_completed} lượt hoàn tất)<b>${fmt(d.service_revenue)}</b></div>
            <div class="kpi">Booking sắp tới (dự kiến thu)<b>${fmt(d.upcoming_value)}</b><span class="muted">${d.bookings_upcoming} lịch hẹn</span></div>
            <div class="kpi">Số sản phẩm đã bán<b>${num(d.units_sold)}</b></div>
            <div class="kpi">Booking đã huỷ<b>${d.bookings_cancelled}</b></div>
            <div class="kpi">Khách hàng<b>${num(d.customers_total)}</b></div>
            <div class="kpi">Doanh thu ${d.days} ngày<b>${fmt(d.period_total)}</b></div></div>
        <div class="card"><h3>Doanh thu theo ngày <span class="muted">(vàng: bán hàng · xanh: dịch vụ)</span></h3>
            ${d.by_day.filter(x => x.shop + x.service > 0).map(x => `<div class="bar"><span>${esc(x.day)}</span><div style="display:flex"><i style="width:${x.shop / max * 100}%"></i><i class="s" style="width:${x.service / max * 100}%"></i></div><span>${fmt(x.shop + x.service)}</span></div>`).join('') || '<p class="muted">Chưa có doanh thu trong khoảng này.</p>'}</div>
        <div class="split"><div class="card"><h3>Sản phẩm bán chạy</h3>${rank(d.top_products, p => `${p.quantity} · ${fmt(p.revenue)}`)}</div>
            <div class="card"><h3>Dịch vụ được dùng nhiều</h3>${rank(d.top_services, s => `${s.count} lượt · ${fmt(s.revenue)}`)}</div></div>
        <div class="split" style="margin-top:1.4rem"><div class="card"><h3>Hiệu suất Stylist</h3>${rank(d.top_stylists, s => `${s.count} lượt · ${fmt(s.revenue)}`)}</div>
            <div class="card"><h3>⚠ Sắp hết hàng (≤ 5)</h3>${rank(d.low_stock, p => `<b style="color:#e74c3c">còn ${p.stock}</b>`)}</div></div>`;
    }

    /* ======================= ĐƠN HÀNG ======================= */
    let ofilter = '', oq = '';
    async function vOrders(box) {
        const list = await api('/orders/admin/all' + (ofilter ? `?order_status=${ofilter}` : ''));
        const shown = list.filter(o => !oq || `${o.order_code} ${o.customer_name} ${o.customer_phone} ${o.customer_email}`.toLowerCase().includes(oq.toLowerCase()));
        box.innerHTML = `<div class="adm-bar"><input class="form-control grow" placeholder="🔍 Tìm mã đơn, tên, SĐT, email..." value="${esc(oq)}" onchange="AD.oq(this.value)">
            <select class="form-control" onchange="AD.of(this.value)"><option value="">Tất cả trạng thái</option>${Object.entries(OST).map(([k, v]) => `<option value="${k}" ${k === ofilter ? 'selected' : ''}>${v}</option>`).join('')}</select>
            <button class="btn-sm" onclick="AD.csvOrders()"><i class="fas fa-download"></i> Xuất CSV</button></div>
            <div class="card"><h3>Đơn hàng (${shown.length})</h3>${shown.map(o => `<div class="ord"><div class="ord-top"><b>${esc(o.order_code)}</b><span class="st ${o.order_status}">${OST[o.order_status] || o.order_status}</span></div>
            <div class="muted">${dt(o.created_at)} · ${o.is_guest ? 'Khách vãng lai' : 'Tài khoản ' + esc(o.customer_id)}</div>
            <div class="line"><span>${esc(o.customer_name)} · <b>${esc(o.customer_phone)}</b>${o.phone_source === 'custom' && o.account_phone ? ` <span class="muted">(số đăng ký: ${esc(o.account_phone)})</span>` : ''} · ${esc(o.customer_email)}</span></div>
            <div class="muted">Giao tới: ${esc(o.shipping_address)}${o.note ? ' · Ghi chú: ' + esc(o.note) : ''}</div>
            <div class="muted">${o.items.map(i => esc(i.name) + ' ×' + i.quantity).join(', ')}</div>
            <div class="line"><span>${PAY[o.payment_method] || ''} · ${PAYS[o.payment_status] || o.payment_status}${o.payment_info && o.payment_info.card_last4 ? ' · ••••' + o.payment_info.card_last4 : ''}${o.payment_info && o.payment_info.bank_ref ? ' · ' + esc(o.payment_info.bank_ref) : ''}</span>
                <span>${fmt(o.subtotal)}${o.discount ? ` − ${fmt(o.discount)} (${esc(o.coupon_code)})` : ''}${o.points_used ? ` − ${num(o.points_used)} điểm` : ''} = <b style="color:var(--gold)">${fmt(o.total)}</b></span></div>
            <div class="actions">
            ${NEXT[o.order_status] ? `<button class="btn-sm" onclick="AD.act('/orders/${o.id}/status?status=${NEXT[o.order_status][0]}','PATCH',null,'Đã cập nhật - khách sẽ nhận thông báo')">${NEXT[o.order_status][1]}</button>` : ''}
            ${o.payment_status === 'pending' && o.order_status !== 'cancelled' ? `<button class="btn-sm" onclick="AD.act('/orders/${o.id}/confirm-payment','PATCH',null,'Đã ghi nhận thu tiền')">Đã thu tiền</button>` : ''}
            ${['pending_confirm', 'preparing'].includes(o.order_status) ? `<button class="btn-sm danger" onclick="if(confirm('Huỷ đơn ${esc(o.order_code)}?'))AD.act('/orders/${o.id}/cancel','PATCH')">Huỷ đơn</button>` : ''}
            </div></div>`).join('') || '<p class="muted">Không có đơn hàng.</p>'}</div>`;
        window._ordersCache = shown;
    }

    /* ======================= BOOKING ======================= */
    let bf = { status: '', date: '', q: '' };
    async function vBookings(box) {
        const qs = new URLSearchParams(); if (bf.status) qs.set('status', bf.status); if (bf.date) qs.set('date', bf.date);
        const list = (await api('/manage/bookings' + (qs.toString() ? '?' + qs : '')))
            .filter(b => !bf.q || `${b.customer_name} ${b.customer_phone} ${b.service_name} ${b.staff_name}`.toLowerCase().includes(bf.q.toLowerCase()));
        box.innerHTML = `<div class="adm-bar"><input class="form-control grow" placeholder="🔍 Tìm khách, SĐT, dịch vụ, stylist..." value="${esc(bf.q)}" onchange="AD.bf('q',this.value)">
            <select class="form-control" onchange="AD.bf('status',this.value)"><option value="">Tất cả trạng thái</option>${Object.entries(BST).map(([k, v]) => `<option value="${k}" ${k === bf.status ? 'selected' : ''}>${v}</option>`).join('')}</select>
            <input type="date" class="form-control" value="${bf.date}" onchange="AD.bf('date',this.value)">
            <button class="btn-sm" onclick="AD.bf('date','');AD.bf('status','');AD.bf('q','')">Xoá lọc</button></div>
            <div class="card"><h3>Lịch hẹn (${list.length})</h3>
            <p class="muted" style="margin-bottom:1rem">Lịch hẹn chỉ được lưu vào <b>lịch sử tài khoản khách</b> sau khi bạn bấm <b>“Xác nhận đã thực hiện”</b>. Khách không đến → bấm <b>Huỷ</b> để giải phóng lịch cho nhân viên (không lưu lịch sử).</p>
            ${list.map(b => `<div class="ord"><div class="ord-top"><b>${esc(b.service_name)} · ${esc(b.tier_name)}</b><span class="st ${b.status}">${BST[b.status] || b.status}</span></div>
            <div class="line"><span>${esc(b.customer_name)} · <b>${esc(b.customer_phone)}</b> · ${esc(b.customer_email)}</span><b style="color:var(--gold)">${fmt(b.total_price)}</b></div>
            <div class="muted">📅 ${esc(b.date)} · ${esc(b.time)} - ${esc(b.end_time || '')} · Stylist ${esc(b.staff_name)} · ${b.payment_method === 'pay_now' || b.payment_mode === 'prepaid' ? 'Trả trước' : 'Trả tại quầy'}${b.note ? ' · Ghi chú khách: ' + esc(b.note) : ''}</div>
            ${b.status === 'cancelled' && b.cancel_reason ? `<div class="muted">Lý do huỷ: ${esc(b.cancel_reason)}${b.refund_needed ? ' · <b style="color:#e67e22">Cần hoàn tiền</b>' : ''}</div>` : ''}
            <div class="actions">
                ${['confirmed', 'paid'].includes(b.status) ? `<button class="btn-sm" onclick="AD.bk('${b.id}')"><i class="fas fa-check"></i> Xác nhận đã thực hiện</button>` : ''}
                ${b.status === 'completed' ? `<button class="btn-sm" onclick="AD.bk('${b.id}')">Ảnh & ghi chú</button>` : ''}
                ${ACTIVE.includes(b.status) ? `<button class="btn-sm" onclick="AD.bk('${b.id}')">Ảnh trước/sau</button><button class="btn-sm danger" onclick="AD.cancelBk('${b.id}')">Huỷ & giải phóng lịch</button>` : ''}
            </div></div>`).join('') || '<p class="muted">Không có lịch hẹn.</p>'}</div>`;
    }
    async function bookingModal(id) {
        const m = modal('Chi tiết booking', '<div id="bm">Đang tải...</div>', 'wide');
        const draw = async () => {
            const b = await api('/manage/bookings/' + id);
            const done = (b.services_done && b.services_done.length ? b.services_done : [`${b.service_name} (${b.tier_name})`]).join('\n');
            const canDone = ['confirmed', 'paid'].includes(b.status), editable = b.status !== 'cancelled';
            const gal = ph => `<div class="photos">${b.photos.filter(p => (ph === 'before') === (p.phase === 'before')).map(p => `<div class="ph"><img src="${p.data_url}" onclick="window.open(this.src)">${editable ? `<button class="btn-sm danger" data-del="${p.id}">✕</button>` : ''}</div>`).join('') || '<span class="muted">Chưa có ảnh</span>'}</div>`;
            $('bm').innerHTML = `<div class="line"><span><b>${esc(b.customer_name)}</b> · ${esc(b.customer_phone)}</span><span class="st ${b.status}">${BST[b.status] || b.status}</span></div>
                <div class="muted">${esc(b.service_name)} · ${esc(b.tier_name)} · ${esc(b.date)} ${esc(b.time)}-${esc(b.end_time || '')} · Stylist ${esc(b.staff_name)} · ${fmt(b.total_price)}</div>
                ${editable ? `<div class="phase"><h4>📷 Ảnh TRƯỚC khi làm</h4>${gal('before')}<input type="file" accept="image/*" multiple data-up="before" style="margin-top:.5rem"></div>
                <div class="phase"><h4>✨ Ảnh SAU khi làm</h4>${gal('after')}<input type="file" accept="image/*" multiple data-up="after" style="margin-top:.5rem"></div>
                <div class="frm2"><label>Những dịch vụ đã thực hiện (mỗi dòng 1 mục — khách sẽ xem lại)</label><textarea id="bm-done" class="form-control" rows="3">${esc(done)}</textarea>
                <label>Ghi chú của stylist cho khách</label><textarea id="bm-note" class="form-control" rows="2">${esc(b.result_note || '')}</textarea></div>
                <div class="actions" style="margin-top:1rem"><button class="btn-sm" id="bm-save">Lưu ghi chú</button>
                ${canDone ? '<button class="btn-primary" id="bm-ok" style="padding:8px 16px"><i class="fas fa-check"></i> Xác nhận đã thực hiện</button>' : ''}</div>` : '<p class="muted">Lịch hẹn đã huỷ.</p>'}`;
            if (!editable) return;
            const lines = () => $('bm-done').value.split('\n').map(s => s.trim()).filter(Boolean);
            $('bm-save').onclick = () => api('/manage/bookings/' + id + '/note', 'PATCH', { result_note: $('bm-note').value, services_done: lines() }).then(() => toast('Đã lưu', 'success')).catch(fail);
            if (canDone) $('bm-ok').onclick = async () => {
                if (!confirm('Xác nhận khách ĐÃ làm dịch vụ này?\nLịch hẹn sẽ được lưu vào lịch sử tài khoản của khách và gửi email cảm ơn.')) return;
                try { await api('/manage/bookings/' + id + '/status', 'PATCH', { status: 'completed', result_note: $('bm-note').value, services_done: lines() }); m.remove(); toast('Đã xác nhận - đã lưu vào lịch sử khách & gửi thông báo cho staff', 'success'); loadBadges(); render(); } catch (e) { fail(e); }
            };
            $('bm').querySelectorAll('[data-up]').forEach(inp => inp.onchange = async e => {
                try { for (const f of e.target.files) await api('/manage/bookings/' + id + '/photos', 'POST', { data_url: await A.resize(f, 1100, 0.75), phase: inp.dataset.up }); await draw(); } catch (er) { fail(er); }
            });
            $('bm').querySelectorAll('[data-del]').forEach(bt => bt.onclick = () => api(`/manage/bookings/${id}/photos/${bt.dataset.del}`, 'DELETE').then(draw).catch(fail));
        };
        draw().catch(e => { fail(e); m.remove(); });
    }
    function cancelBooking(id) {
        const reason = prompt('Huỷ lịch hẹn này và giải phóng khung giờ cho nhân viên?\nNhập lý do (vd: Khách không đến):', 'Khách không đến');
        if (reason === null) return;
        act('/manage/bookings/' + id + '/status', 'PATCH', { status: 'cancelled', reason }, 'Đã huỷ - khung giờ của nhân viên đã được giải phóng');
    }

    /* ======================= MÃ GIẢM GIÁ (dùng API sẵn có) ======================= */
    async function vCoupons(box) {
        const list = await api('/coupons/admin/all');
        box.innerHTML = `<div class="card"><h3>Tạo / cập nhật mã giảm giá</h3>
            <form class="frm" onsubmit="AD.saveCoupon(event)"><div class="row">
            <div><label>Mã</label><input id="c-code" class="form-control" required pattern="[A-Za-z0-9_-]{3,30}" style="text-transform:uppercase"></div>
            <div><label>Mô tả</label><input id="c-desc" class="form-control"></div>
            <div><label>Loại giảm</label><select id="c-type" class="form-control"><option value="percent">Phần trăm (%)</option><option value="fixed">Số tiền (đ)</option></select></div>
            <div><label>Giá trị (20 = 20% hoặc 50000đ)</label><input id="c-val" type="number" min="1" class="form-control" required></div>
            <div><label>Giảm tối đa (đ, chỉ với %, 0 = không giới hạn)</label><input id="c-max" type="number" min="0" value="0" class="form-control"></div>
            <div><label>Đơn tối thiểu (đ)</label><input id="c-min" type="number" min="0" value="0" class="form-control"></div>
            <div><label>Hiệu lực từ</label><input id="c-from" type="datetime-local" class="form-control"></div>
            <div><label>Hết hạn</label><input id="c-until" type="datetime-local" class="form-control" required></div>
            <div><label>Số lượt dùng tối đa (0 = không giới hạn)</label><input id="c-limit" type="number" min="0" value="100" class="form-control"></div></div>
            <button class="btn-primary" style="margin-top:1rem">Lưu mã</button></form></div>
            <div class="card"><h3>Danh sách mã (${list.length})</h3>${list.map(c => `<div class="ord"><div class="ord-top"><b>${esc(c.code)}</b>
            <span class="st ${c.is_active ? 'completed' : 'cancelled'}">${c.is_active ? 'Đang bật' : 'Đã tắt'}</span></div><div class="muted">${esc(c.description || '')}</div>
            <div class="line"><span>${c.discount_type === 'percent' ? c.discount_value + '%' + (c.max_discount_amount ? ` (tối đa ${fmt(c.max_discount_amount)})` : '') : fmt(c.discount_value)} · đơn từ ${fmt(c.min_order_value)}</span>
            <span>Đã dùng ${c.used_count || 0}/${c.usage_limit || '∞'} · hết hạn ${dt(c.valid_until)}</span></div>
            <div class="actions"><button class="btn-sm" onclick="AD.act('/coupons/admin/${esc(c.code)}/toggle','PATCH')">${c.is_active ? 'Tắt' : 'Bật'}</button></div></div>`).join('')}</div>`;
    }
    function saveCoupon(e) {
        e.preventDefault();
        const v = id => $(id).value, iso = x => x ? new Date(x).toISOString() : null;
        act('/coupons/admin', 'POST', {
            code: v('c-code'), description: v('c-desc'), discount_type: v('c-type'), discount_value: +v('c-val'),
            max_discount_amount: +v('c-max') || 0, min_order_value: +v('c-min') || 0, valid_from: iso(v('c-from')), valid_until: iso(v('c-until')),
            usage_limit: +v('c-limit') || 0, is_active: true
        }, 'Đã lưu mã giảm giá');
    }

    /* ======================= THÔNG BÁO ======================= */
    async function vNotifs(box) {
        const list = await api('/manage/notifications');
        const icon = { booking_completed: 'fa-circle-check', booking_cancelled: 'fa-calendar-xmark', booking_new: 'fa-calendar-plus', new_order: 'fa-box' };
        box.innerHTML = `<div class="adm-bar"><button class="btn-sm" onclick="AD.readAll()">Đánh dấu đã đọc tất cả</button></div>
            ${list.map(n => `<div class="notif ${n.is_read ? '' : 'un'}" onclick="AD.readOne('${n.id}')"><i class="fas ${icon[n.type] || 'fa-bell'}"></i>
            <div><b>${esc(n.title)}</b><div class="muted">${esc(n.message)}</div><div class="muted">${dt(n.created_at)}</div></div></div>`).join('') || '<p class="muted">Chưa có thông báo.</p>'}`;
    }

    /* ======================= CRUD CHUNG: Dịch vụ / Sản phẩm / Nhân viên / Tài khoản ======================= */
    const thumb = u => `<img class="thumb" src="${esc(u || '')}" onerror="this.style.visibility='hidden'" alt="">`;
    const act2 = id => `<div class="acts"><button class="btn-sm" onclick="AD.edit('@K','${id}')">Sửa</button><button class="btn-sm danger" onclick="AD.del('@K','${id}')">Xoá</button></div>`;
    const status = on => `<span class="tag ${on === false ? 'off' : 'ok'}">${on === false ? 'Ẩn' : 'Hoạt động'}</span>`;
    const CRUD = {
        services: {
            title: 'dịch vụ', path: '/manage/services',
            cols: [['', r => thumb(r.img_url)], ['Tên dịch vụ', r => `<b>${esc(r.name)}</b>`], ['Nhóm', r => esc(r.category)], ['Giá từ', r => fmt(r.price)],
            ['Thời lượng', r => r.duration_minutes + ' phút'], ['Gói', r => (r.tiers || []).length], ['Trạng thái', r => status(r.is_active)]],
            fields: [
                { k: 'name', l: 'Tên dịch vụ', r: 1 }, { k: 'category', l: 'Nhóm dịch vụ', t: 'select', o: CATS },
                { k: 'price', l: 'Giá khởi điểm (gói tiêu chuẩn, đ)', t: 'number', r: 1 }, { k: 'duration_minutes', l: 'Thời lượng (phút)', t: 'number', r: 1 },
                { k: 'img_url', l: 'Ảnh dịch vụ', t: 'image', full: 1 }, { k: 'desc', l: 'Mô tả', t: 'textarea', full: 1 },
                { k: 'tiers', l: 'Các gói giá (để trống tên gói để tự tạo 3 gói theo giá khởi điểm)', t: 'tiers', full: 1 },
                { k: 'is_active', l: 'Đang cung cấp', t: 'check', full: 1 }],
            blank: () => ({ category: CATS[0], duration_minutes: 60, is_active: true, tiers: [] })
        },
        products: {
            title: 'sản phẩm', path: '/manage/products',
            cols: [['', r => thumb(r.img)], ['Sản phẩm', r => `<b>${esc(r.name)}</b><div class="muted">${esc(r.brand)} · ${esc(r.type)} · ${esc(r.volume)}</div>`],
            ['Giá', r => fmt(r.price)], ['Tồn kho', r => `<b style="color:${r.stock <= 5 ? '#e74c3c' : 'inherit'}">${r.stock}</b>`], ['Đã bán', r => num(r.sold_count)],
            ['Đánh giá', r => r.rating_count ? `★ ${Number(r.rating_avg).toFixed(1)} (${r.rating_count})` : '—'], ['Trạng thái', r => status(r.is_active)]],
            fields: [
                { k: 'name', l: 'Tên sản phẩm', r: 1, full: 1 }, { k: 'brand', l: 'Thương hiệu', r: 1 }, { k: 'type', l: 'Loại sản phẩm', t: 'select', o: PTYPES },
                { k: 'volume', l: 'Dung tích (vd 250ml)' }, { k: 'origin', l: 'Xuất xứ' },
                { k: 'price', l: 'Giá bán (đ)', t: 'number', r: 1 }, { k: 'stock', l: 'Tồn kho', t: 'number', r: 1 },
                { k: 'img', l: 'Ảnh chính', t: 'image', full: 1 }, { k: 'images', l: 'Ảnh phụ (mỗi dòng 1 link)', t: 'lines', full: 1 },
                { k: 'desc', l: 'Mô tả công dụng', t: 'textarea', full: 1 }, { k: 'usage', l: 'Hướng dẫn sử dụng', t: 'textarea', full: 1 },
                { k: 'is_active', l: 'Đang bán', t: 'check', full: 1 }],
            blank: () => ({ type: PTYPES[0], stock: 0, is_active: true, images: [] })
        },
        staffs: {
            title: 'nhân viên', path: '/manage/staffs',
            cols: [['', r => thumb(r.avatar)], ['Họ tên', r => `<b>${esc(r.name)}</b><div class="muted">${esc(r.id)}</div>`], ['Chuyên môn', r => esc(r.specialty)],
            ['Kinh nghiệm', r => r.exp_years + ' năm'], ['Giờ làm', r => `${esc(r.work_start)} - ${esc(r.work_end)}`], ['Trạng thái', r => status(r.is_active)]],
            fields: [
                { k: 'name', l: 'Họ tên', r: 1 }, { k: 'specialty', l: 'Chuyên môn' }, { k: 'exp_years', l: 'Kinh nghiệm (năm)', t: 'number' },
                { k: 'avatar', l: 'Ảnh đại diện', t: 'image' }, { k: 'work_start', l: 'Giờ bắt đầu', t: 'time', r: 1 }, { k: 'work_end', l: 'Giờ kết thúc', t: 'time', r: 1 },
                { k: 'is_active', l: 'Đang làm việc (nhận lịch hẹn)', t: 'check', full: 1 }],
            blank: () => ({ work_start: '08:00', work_end: '18:00', exp_years: 0, is_active: true })
        },
        users: {
            title: 'tài khoản', path: '/manage/users', id: 'uid',
            cols: [['Họ tên', r => `<b>${esc(r.full_name)}</b><div class="muted">${esc(r.uid)}</div>`], ['SĐT', r => esc(r.phone)], ['Email', r => esc(r.email)],
            ['Vai trò', r => `<span class="tag ${r.role === 'owner' ? 'gold' : r.role === 'staff' ? 'ok' : ''}">${(ROLES.find(x => x[0] === r.role) || [0, r.role])[1]}</span>`],
            ['Điểm', r => num(r.points)], ['Chi tiêu', r => fmt(r.total_spent)], ['Tạo lúc', r => dt(r.created_at)]],
            fields: [
                { k: 'full_name', l: 'Họ tên', r: 1 }, { k: 'role', l: 'Vai trò', t: 'select', o: ROLES },
                { k: 'phone', l: 'Số điện thoại', t: 'tel', r: 1 }, { k: 'email', l: 'Email', t: 'email', r: 1 },
                { k: 'password', l: 'Mật khẩu', t: 'password', hint: 'Tạo mới: bắt buộc (≥ 6 ký tự). Khi sửa: để trống nếu không đổi.' },
                { k: 'points', l: 'Điểm thưởng', t: 'number' }],
            blank: () => ({ role: 'customer', points: 0 })
        }
    };
    const CACHE = {};
    let crudQ = {};
    async function vCrud(box, key) {
        const c = CRUD[key], idf = c.id || 'id';
        const list = CACHE[key] = await api(c.path);
        const q = (crudQ[key] || '').toLowerCase();
        const rows = list.filter(r => !q || JSON.stringify(r).toLowerCase().includes(q));
        box.innerHTML = `<div class="adm-bar"><input class="form-control grow" placeholder="🔍 Tìm ${c.title}..." value="${esc(crudQ[key] || '')}" onchange="AD.q('${key}',this.value)">
            <button class="btn-primary" style="padding:9px 16px" onclick="AD.add('${key}')"><i class="fas fa-plus"></i> Thêm ${c.title}</button></div>
            <div class="card tbl-wrap"><table class="tbl"><thead><tr>${c.cols.map(x => `<th>${x[0]}</th>`).join('')}<th></th></tr></thead><tbody>
            ${rows.map(r => `<tr>${c.cols.map(x => `<td>${x[1](r)}</td>`).join('')}<td>${act2(r[idf]).replace(/@K/g, key)}</td></tr>`).join('') || `<tr><td colspan="${c.cols.length + 1}" class="muted">Chưa có dữ liệu.</td></tr>`}
            </tbody></table><p class="muted" style="margin-top:.6rem">${rows.length} ${c.title}</p></div>`;
    }
    function fieldHTML(f, v) {
        const id = 'f-' + f.k, rq = f.r ? 'required' : '';
        let h;
        if (f.t === 'textarea') h = `<textarea id="${id}" class="form-control" rows="3" ${rq}>${esc(v)}</textarea>`;
        else if (f.t === 'lines') h = `<textarea id="${id}" class="form-control" rows="3">${esc((v || []).join('\n'))}</textarea>`;
        else if (f.t === 'select') h = `<select id="${id}" class="form-control">${f.o.map(o => { const [ov, ol] = Array.isArray(o) ? o : [o, o]; return `<option value="${esc(ov)}" ${ov === v ? 'selected' : ''}>${esc(ol)}</option>`; }).join('')}</select>`;
        else if (f.t === 'check') return `<label class="chk full"><input type="checkbox" id="${id}" ${v ? 'checked' : ''}> ${f.l}</label>`;
        else if (f.t === 'image') h = `<div class="imgf"><img id="${id}-p" src="${esc(v || '')}" onerror="this.style.visibility='hidden'" onload="this.style.visibility='visible'"><input type="text" id="${id}" class="form-control" placeholder="Dán link ảnh hoặc bấm Tải ảnh" value="${esc(v || '')}" oninput="document.getElementById('${id}-p').src=this.value">
            <label class="btn-sm" style="margin:0;cursor:pointer">Tải ảnh<input type="file" accept="image/*" hidden onchange="AD.pick('${id}',this)"></label></div>`;
        else if (f.t === 'tiers') {
            const T = v && v.length ? v : [0, 1, 2].map(i => ({ tier_id: ['basic', 'premium', 'luxury'][i], tier_name: '', product_line: '', price: 0, pros: '', cons: '' }));
            h = T.map((t, i) => `<div class="tierbox" data-tid="${esc(t.tier_id)}"><b>Gói ${i + 1}</b><div class="fgrid"><div><label>Tên gói</label><input class="form-control" id="t${i}-n" value="${esc(t.tier_name)}"></div>
                <div><label>Giá (đ)</label><input type="number" min="0" class="form-control" id="t${i}-p" value="${t.price || ''}"></div>
                <div class="full"><label>Dòng sản phẩm sử dụng</label><input class="form-control" id="t${i}-l" value="${esc(t.product_line)}"></div>
                <div><label>Ưu điểm</label><textarea class="form-control" id="t${i}-pro" rows="2">${esc(t.pros)}</textarea></div>
                <div><label>Nhược điểm / lưu ý</label><textarea class="form-control" id="t${i}-con" rows="2">${esc(t.cons)}</textarea></div></div></div>`).join('');
        } else h = `<input id="${id}" type="${f.t || 'text'}" class="form-control" ${rq} ${f.t === 'number' ? 'min="0"' : ''} value="${esc(v == null ? '' : v)}" ${f.t === 'password' ? 'autocomplete="new-password"' : ''}>`;
        return `<div class="${f.full || f.t === 'tiers' ? 'full' : ''}"><label>${f.l}${f.r ? ' *' : ''}</label>${h}${f.hint ? `<small>${f.hint}</small>` : ''}</div>`;
    }
    function gather(fields) {
        const o = {};
        fields.forEach(f => {
            const el = $('f-' + f.k);
            if (f.t === 'tiers') o[f.k] = [...document.querySelectorAll('.tierbox')].map((b, i) => ({ tier_id: b.dataset.tid, tier_name: $('t' + i + '-n').value.trim(), product_line: $('t' + i + '-l').value.trim(), price: +$('t' + i + '-p').value || 0, pros: $('t' + i + '-pro').value.trim(), cons: $('t' + i + '-con').value.trim() })).filter(t => t.tier_name);
            else if (f.t === 'check') o[f.k] = el.checked;
            else if (f.t === 'number') o[f.k] = el.value === '' ? 0 : +el.value;
            else if (f.t === 'lines') o[f.k] = el.value.split('\n').map(s => s.trim()).filter(Boolean);
            else o[f.k] = el.value.trim();
        });
        return o;
    }
    function openForm(key, row) {
        const c = CRUD[key], isNew = !row, idf = c.id || 'id', data = row || c.blank();
        const m = modal(`${isNew ? 'Thêm' : 'Sửa'} ${c.title}`, `<form id="crud-form" class="fgrid">${c.fields.map(f => fieldHTML(f, data[f.k])).join('')}
            <div class="full actions" style="margin-top:1rem"><button class="btn-primary" style="padding:9px 20px">${isNew ? 'Thêm mới' : 'Lưu thay đổi'}</button></div></form>`, 'wide');
        $('crud-form').onsubmit = async e => {
            e.preventDefault();
            const body = gather(c.fields);
            if (key === 'users' && !body.password) delete body.password;
            try { await api(isNew ? c.path : `${c.path}/${row[idf]}`, isNew ? 'POST' : 'PUT', body); m.remove(); toast(isNew ? 'Đã thêm' : 'Đã lưu thay đổi', 'success'); render(); }
            catch (er) { fail(er); }
        };
    }

    const VIEWS = {
        dash: vDash, orders: vOrders, bookings: vBookings, coupons: vCoupons, notifs: vNotifs,
        services: b => vCrud(b, 'services'), products: b => vCrud(b, 'products'), staffs: b => vCrud(b, 'staffs'), users: b => vCrud(b, 'users')
    };

    window.AD = {
        act, saveCoupon, bk: bookingModal, cancelBk: cancelBooking,
        days: v => { sessionStorage.admDays = v; render(); },
        of: v => { ofilter = v; render(); }, oq: v => { oq = v; render(); },
        bf: (k, v) => { bf[k] = v; render(); },
        q: (k, v) => { crudQ[k] = v; render(); },
        add: k => openForm(k, null),
        edit: (k, id) => openForm(k, CACHE[k].find(r => String(r[CRUD[k].id || 'id']) === String(id))),
        del: async (k, id) => {
            if (!confirm(`Xoá ${CRUD[k].title} này? Thao tác không thể hoàn tác.`)) return;
            try { await api(`${CRUD[k].path}/${id}`, 'DELETE'); toast('Đã xoá', 'success'); render(); } catch (e) { fail(e); }
        },
        pick: async (id, input) => { const f = input.files[0]; if (!f) return; try { const u = await A.resize(f, 700, 0.8); $(id).value = u; $(id + '-p').src = u; } catch (e) { fail(e); } },
        readAll: () => act('/manage/notifications/read-all', 'POST', {}),
        readOne: id => api('/manage/notifications/' + id + '/read', 'PATCH', {}).then(() => { loadBadges(); render(); }).catch(fail),
        csvStats: () => lastStats && csv([['Ngày', 'Bán hàng', 'Dịch vụ', 'Tổng'], ...lastStats.by_day.map(x => [x.day, x.shop, x.service, x.shop + x.service])], 'doanh-thu.csv'),
        csvOrders: () => csv([['Mã đơn', 'Thời gian', 'Khách', 'SĐT', 'Email', 'Địa chỉ', 'Thanh toán', 'TT thanh toán', 'Trạng thái', 'Tạm tính', 'Giảm giá', 'Tổng'],
        ...(window._ordersCache || []).map(o => [o.order_code, dt(o.created_at), o.customer_name, o.customer_phone, o.customer_email, o.shipping_address, PAY[o.payment_method], PAYS[o.payment_status], OST[o.order_status], o.subtotal, o.discount || 0, o.total])], 'don-hang.csv')
    };

    const start = (location.hash || '').slice(1);
    go(MENU.some(m => m.k === start) ? start : MENU[0].k);
    loadBadges(); setInterval(loadBadges, 60000);
})();