const API = ''; // same origin, backend serves this file too

const CATEGORY_EMOJI = {
  'Beverages': '🍵',
  'Dairy': '🧀',
  'Bakery': '🥐',
  'Snacks': '🍫',
  'Grains & Staples': '🌾',
  'Fruits & Vegetables': '🍎',
};
const CATEGORY_COLOR = {
  'Beverages': '#E0A23326',
  'Dairy': '#1B635522',
  'Bakery': '#AE3A2C22',
  'Snacks': '#8B4A2B22',
  'Grains & Staples': '#C9A22730',
  'Fruits & Vegetables': '#4F8F3B26',
};

const CART_ICON_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle>
  <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path>
</svg>`;

// ===== Session (persisted across refresh) =====
let currentUser = JSON.parse(localStorage.getItem('smartcart_user') || 'null');
let cart = JSON.parse(localStorage.getItem('smartcart_cart') || '[]'); // [{product_id,name,price,quantity}]

function saveCart() { localStorage.setItem('smartcart_cart', JSON.stringify(cart)); }
function saveUser() { localStorage.setItem('smartcart_user', JSON.stringify(currentUser)); }

function renderAuthArea() {
  const el = document.getElementById('authArea');
  if (currentUser) {
    el.innerHTML = `
      <div class="user-greeting">
        <span>مرحباً، ${currentUser.first_name}</span>
        <button onclick="logout()">خروج</button>
      </div>`;
  } else {
    el.innerHTML = `<button onclick="openModal()">تسجيل / دخول</button>`;
  }
}

function logout() {
  currentUser = null;
  localStorage.removeItem('smartcart_user');
  renderAuthArea();
}

function updateCartBadge() {
  const totalQty = cart.reduce((sum, i) => sum + i.quantity, 0);
  const badge = document.getElementById('cartBadge');
  if (totalQty > 0) {
    badge.style.display = 'flex';
    badge.textContent = totalQty;
    badge.classList.remove('pop');
    void badge.offsetWidth;
    badge.classList.add('pop');
  } else {
    badge.style.display = 'none';
  }
}

function showToast(text) {
  const toast = document.getElementById('toast');
  toast.textContent = text;
  toast.classList.add('show');
  clearTimeout(window._toastTimer);
  window._toastTimer = setTimeout(() => toast.classList.remove('show'), 2000);
}

function addToCart(product_id, name, price) {
  const existing = cart.find(i => i.product_id === product_id);
  if (existing) {
    existing.quantity++;
  } else {
    cart.push({ product_id, name, price, quantity: 1 });
  }
  saveCart();
  updateCartBadge();
  showToast(`✓ تمت إضافة "${name}" إلى السلة`);
}

function changeQty(product_id, delta) {
  const item = cart.find(i => i.product_id === product_id);
  if (!item) return;
  item.quantity += delta;
  if (item.quantity <= 0) cart = cart.filter(i => i.product_id !== product_id);
  saveCart();
  updateCartBadge();
  renderCart();
}

async function showProductDetail(productId) {
  const overlay = document.getElementById('detailOverlay');
  const content = document.getElementById('detailContent');
  content.innerHTML = '<div class="loading" style="width:100%;">جارِ التحميل...</div>';
  overlay.classList.add('open');

  try {
    const res = await fetch(`${API}/api/products/${productId}`);
    if (!res.ok) throw new Error('Product not found');
    const p = await res.json();

    const filledCount = Math.round(p.avg_rating || 0);
    const stars = `<span class="star-filled">${'★'.repeat(filledCount)}</span><span class="star-empty">${'☆'.repeat(5 - filledCount)}</span>`;

    content.innerHTML = `
      <div class="detail-img-side">
        <img src="${p.image_path || ''}" alt="${p.name}"
             onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
        <span class="detail-img-fallback" style="display:none;">🛍️</span>
      </div>
      <div class="detail-info-side">
        <div class="detail-cat">${p.category}</div>
        <div class="detail-name">${p.name}</div>
        <div class="detail-rating">${stars} <span class="num">${p.avg_rating || 0} / 5</span></div>
        <div class="detail-desc">${p.description || ''}</div>
        ${p.review ? `
          <div class="detail-review-box">
            <div class="detail-review-label">رأي أحد العملاء</div>
            ${p.review}
          </div>` : ''}
        <div class="detail-footer">
          <div class="detail-price">${p.price} ج.م</div>
          <button class="detail-add-btn" onclick="addToCart(${p.product_id}, '${p.name.replace(/'/g, "\\'")}', ${p.price}); closeDetail();">
            ${CART_ICON_SVG} أضف للسلة
          </button>
        </div>
      </div>
    `;
  } catch (err) {
    content.innerHTML = '<div class="loading" style="width:100%;">تعذر تحميل المنتج</div>';
  }
}

function closeDetail() {
  document.getElementById('detailOverlay').classList.remove('open');
}

function openCart() {
  renderCart();
  document.getElementById('cartOverlay').classList.add('open');
}
function closeCart() {
  document.getElementById('cartOverlay').classList.remove('open');
}

function renderCart() {
  const wrap = document.getElementById('cartItemsWrap');
  if (cart.length === 0) {
    wrap.innerHTML = '<div class="cart-empty">السلة فارغة</div>';
    return;
  }
  const total = cart.reduce((sum, i) => sum + i.price * i.quantity, 0);
  wrap.innerHTML = cart.map(i => `
    <div class="cart-item">
      <div class="cart-item-name">${i.name}</div>
      <div class="cart-item-qty">
        <button onclick="changeQty(${i.product_id}, -1)">−</button>
        <span>${i.quantity}</span>
        <button onclick="changeQty(${i.product_id}, 1)">+</button>
      </div>
      <div class="cart-item-price">${(i.price * i.quantity).toFixed(0)} ج.م</div>
    </div>
  `).join('') + `
    <div class="cart-total-row"><span>الإجمالي</span><span>${total.toFixed(0)} ج.م</span></div>
    <button class="checkout-btn" onclick="checkout()">تأكيد الطلب</button>
  `;
}

async function checkout() {
  if (!currentUser) {
    closeCart();
    openModal();
    switchTab('login');
    showToast('سجّل الدخول أولاً لإتمام الطلب');
    return;
  }
  if (cart.length === 0) return;

  try {
    const res = await fetch(`${API}/api/orders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        person_id: currentUser.person_id,
        items: cart.map(i => ({ product_id: i.product_id, quantity: i.quantity })),
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'حدث خطأ في الطلب');

    cart = [];
    saveCart();
    updateCartBadge();
    closeCart();
    showToast(`✓ تم تأكيد الطلب رقم ${data.order_id}`);
    loadProducts(activeCategory, activeSearch); // refresh stock numbers
  } catch (err) {
    showToast('✗ ' + err.message);
  }
}

let activeCategory = null;
let activeSearch = '';
let searchDebounce = null;

document.getElementById('searchInput').addEventListener('input', (e) => {
  clearTimeout(searchDebounce);
  const value = e.target.value.trim();
  searchDebounce = setTimeout(() => {
    activeSearch = value;
    document.getElementById('products-title').textContent = value
      ? `نتائج البحث عن "${value}"`
      : (activeCategory ? document.querySelector('.cat-card.active .cat-name')?.textContent : 'كل المنتجات') || 'كل المنتجات';
    loadProducts(activeCategory, activeSearch);
  }, 350);
});

async function loadCategories() {
  const res = await fetch(`${API}/api/categories`);
  const categories = await res.json();
  const el = document.getElementById('categories');
  el.innerHTML = '';

  const allCard = makeCatCard(null, 'الكل', '🛒');
  el.appendChild(allCard);

  categories.forEach(c => {
    el.appendChild(makeCatCard(c.category_id, c.name, CATEGORY_EMOJI[c.name] || '🛍️'));
  });
}

function makeCatCard(id, name, emoji) {
  const div = document.createElement('div');
  div.className = 'cat-card' + (activeCategory === id ? ' active' : '');
  const bg = CATEGORY_COLOR[name] || '#1B635522';
  div.innerHTML = `<div class="cat-icon-badge" style="background:${bg}">${emoji}</div><span class="cat-name">${name}</span>`;
  div.onclick = () => {
    activeCategory = id;
    document.querySelectorAll('.cat-card').forEach(c => c.classList.remove('active'));
    div.classList.add('active');
    document.getElementById('products-title').textContent = id ? name : 'كل المنتجات';
    loadProducts(id, activeSearch);
  };
  return div;
}

async function loadProducts(categoryId, search) {
  const el = document.getElementById('products');
  el.innerHTML = '<div class="loading">جارِ التحميل...</div>';
  const params = new URLSearchParams();
  if (categoryId) params.set('category_id', categoryId);
  if (search) params.set('search', search);
  const url = `${API}/api/products${params.toString() ? '?' + params.toString() : ''}`;
  const res = await fetch(url);
  const products = await res.json();
  el.innerHTML = '';

  if (products.length === 0) {
    el.innerHTML = '<div class="loading">لا توجد نتائج</div>';
    return;
  }

  products.forEach(p => {
    const card = document.createElement('div');
    card.className = 'prod-card';
    card.style.cursor = 'pointer';
    card.onclick = () => showProductDetail(p.product_id);
    const filledCount = Math.round(p.avg_rating || 0);
    const stars = `<span class="star-filled">${'★'.repeat(filledCount)}</span><span class="star-empty">${'☆'.repeat(5 - filledCount)}</span>`;
    card.innerHTML = `
      <div class="prod-img-wrap">
        <img src="${p.image_path || ''}" alt="${p.name}"
             onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
        <span class="prod-img-fallback" style="display:none;">🛍️</span>
      </div>
      <div class="prod-info">
        <div class="prod-cat">${p.category}</div>
        <div class="prod-name">${p.name}</div>
        <div class="prod-rating">${stars}</div>
        <div class="prod-review">${p.review || ''}</div>
        <div class="prod-footer">
          <div class="prod-price">${p.price} ج.م</div>
          <button class="prod-add" title="أضف للسلة" onclick="event.stopPropagation(); addToCart(${p.product_id}, '${p.name.replace(/'/g, "\\'")}', ${p.price})">${CART_ICON_SVG}</button>
        </div>
      </div>
    `;
    el.appendChild(card);
  });
}

function openModal() {
  document.getElementById('modalOverlay').classList.add('open');
}
function closeModal() {
  document.getElementById('modalOverlay').classList.remove('open');
  document.getElementById('modalMsg').textContent = '';
  document.getElementById('loginMsg').textContent = '';
}

function switchTab(tab) {
  const isRegister = tab === 'register';
  document.getElementById('tabRegister').classList.toggle('active', isRegister);
  document.getElementById('tabLogin').classList.toggle('active', !isRegister);
  document.getElementById('registerForm').style.display = isRegister ? 'block' : 'none';
  document.getElementById('loginForm').style.display = isRegister ? 'none' : 'block';
}

document.getElementById('registerForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = document.getElementById('modalMsg');
  msg.textContent = '';
  msg.className = 'modal-msg';

  const payload = {
    first_name: document.getElementById('first_name').value,
    last_name: document.getElementById('last_name').value,
    email: document.getElementById('email').value,
    password: document.getElementById('password').value,
    phone: document.getElementById('phone').value || null,
    address: document.getElementById('address').value || null,
  };

  try {
    const res = await fetch(`${API}/api/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'حدث خطأ');

    currentUser = { person_id: data.person_id, first_name: data.first_name };
    saveUser();
    renderAuthArea();

    msg.textContent = 'تم إنشاء الحساب بنجاح! ✓';
    msg.className = 'modal-msg success';
    document.getElementById('registerForm').reset();
    setTimeout(closeModal, 1200);
  } catch (err) {
    msg.textContent = err.message;
    msg.className = 'modal-msg error';
  }
});

document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = document.getElementById('loginMsg');
  msg.textContent = '';
  msg.className = 'modal-msg';

  const payload = {
    email: document.getElementById('login_email').value,
    password: document.getElementById('login_password').value,
  };

  try {
    const res = await fetch(`${API}/api/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'بيانات الدخول غير صحيحة');

    currentUser = { person_id: data.person_id, first_name: data.first_name };
    saveUser();
    renderAuthArea();

    msg.textContent = `مرحباً بعودتك، ${data.first_name}! ✓`;
    msg.className = 'modal-msg success';
    document.getElementById('loginForm').reset();
    setTimeout(closeModal, 1000);
  } catch (err) {
    msg.textContent = err.message;
    msg.className = 'modal-msg error';
  }
});

renderAuthArea();
updateCartBadge();
loadCategories();
loadProducts(null);
