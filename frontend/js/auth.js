/* js/auth.js - phiên đăng nhập + gọi API có token. Nạp TRƯỚC cart.js. */
(function () {
    const API = window.UNISEX_API || 'http://localhost:8000/api';
    const KEYS = ['token', 'uid', 'userRole', 'userName', 'userPhone', 'userEmail'];
    const A = {
        API,
        token: () => localStorage.getItem('token') || '',
        role: () => localStorage.getItem('userRole') || '',
        save(d) {   // d = {token, user}
            localStorage.setItem('token', d.token);
            localStorage.setItem('uid', d.user.uid);
            localStorage.setItem('userRole', d.user.role);
            localStorage.setItem('userName', d.user.full_name);
            localStorage.setItem('userPhone', d.user.phone || '');
            localStorage.setItem('userEmail', d.user.email || '');
        },
        clear() { KEYS.forEach(k => localStorage.removeItem(k)); },
        logout() { A.clear(); location.href = 'index.html'; },
        errMsg(d) {
            if (d && typeof d.detail === 'string') return d.detail;
            if (d && Array.isArray(d.detail)) return d.detail.map(x => x.msg).join('; ');
            return 'Có lỗi xảy ra, vui lòng thử lại';
        },
        async api(path, opt) {
            opt = opt || {};
            const h = Object.assign({ 'Content-Type': 'application/json' }, opt.headers || {});
            if (A.token()) h.Authorization = 'Bearer ' + A.token();
            let res;
            try {
                res = await fetch(API + path, {
                    method: opt.method || (opt.body ? 'POST' : 'GET'), headers: h,
                    body: opt.body && typeof opt.body !== 'string' ? JSON.stringify(opt.body) : opt.body
                });
            } catch (e) { throw new Error('Không thể kết nối máy chủ'); }
            let data = null;
            try { data = await res.json(); } catch (e) { }
            if (!res.ok) {
                if (res.status === 401 && A.token() && !opt.noRedirect) {
                    A.clear();
                    location.href = 'login.html?next=' + encodeURIComponent(location.pathname.split('/').pop() || 'index.html');
                }
                throw new Error(A.errMsg(data));
            }
            return data;
        },
        // Đọc ảnh -> thu nhỏ (cạnh dài tối đa `max` px) -> JPEG data URL
        resize(file, max, quality) {
            return new Promise((ok, fail) => {
                const img = new Image(), url = URL.createObjectURL(file);
                img.onload = () => {
                    const k = Math.min(1, max / Math.max(img.width, img.height));
                    const c = document.createElement('canvas');
                    c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
                    c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
                    URL.revokeObjectURL(url);
                    ok(c.toDataURL('image/jpeg', quality || 0.82));
                };
                img.onerror = () => fail(new Error('Không đọc được ảnh'));
                img.src = url;
            });
        }
    };
    window.UAuth = A;
})();