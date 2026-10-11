const formatMoney = amount => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);

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
let currentUser = null;
let cart = []; // [{product_id,name,price,quantity}]

function saveCart() {}
function saveUser() { cart = []; updateCartBadge(); resetAssistant(); refreshSession().catch(e => showToast(e.message)); }

function renderAuthArea() {
  const el = document.getElementById('authArea');
  if (currentUser) {
    el.innerHTML = `
      <div class="user-greeting">
        <span>Hello, ${escapeHTML(currentUser.first_name)}</span>
        <button onclick="logout()">Sign out</button>
      </div>`;
  } else {
    el.innerHTML = `<button onclick="openModal()">Register / Sign in</button>`;
  }
}

async function logout() {
  try { await apiRequest('/api/logout', {method:'POST'}); }
  catch (e) { showToast(e.message); return; }
  resetAssistant(); currentUser = null; cart = []; renderAuthArea(); updateCartBadge(); navigatePage('shop');
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

let cartQueue = Promise.resolve();
function addToCart(product_id, name, price) { return changeQty(product_id, 1, name); }
function changeQty(product_id, delta, name) {
  if (!currentUser) { openModal(); switchTab('login'); showToast('Sign in to use your cart'); return; }
  const owner = currentUser.person_id;
  cartQueue = cartQueue.catch(() => {}).then(async () => {
    if (currentUser?.person_id !== owner) return;
    const snapshot = await apiRequest('/api/cart');
    const item = snapshot.items.find(i => i.product_id === product_id);
    const quantity = Math.max(0, (item?.quantity || 0) + delta);
    const updated = await apiRequest('/api/cart', {method:'PATCH', body:{revision:snapshot.revision, items:[{product_id, quantity}]}});
    if (currentUser?.person_id !== owner) return;
    cart = updated.items; updateCartBadge(); renderCart(); showToast(name ? `Added ${name}` : 'Cart updated');
  }).catch(async e => { showToast(e.message); if (currentUser?.person_id === owner) await refreshCart(); });
  return cartQueue;
}
function addKnownProduct(id) { const p = knownProducts.get(id); if (p) addToCart(id, p.name, p.price); }
const knownProducts = new Map();
let visibleProductIds = [];
let selectedProductId = null;

async function showProductDetail(productId) {
  const overlay = document.getElementById('detailOverlay');
  const content = document.getElementById('detailContent');
  content.innerHTML = '<div class="loading" style="width:100%;">Loading...</div>';
  overlay.classList.add('open');
  selectedProductId = productId; updatePageLabel();

  try {
    const res = await fetch(`${API}/api/products/${productId}`);
    if (!res.ok) throw new Error('Product not found');
    const raw = await res.json(); knownProducts.set(raw.product_id, raw);
    const p = Object.fromEntries(Object.entries(raw).map(([k,v]) => [k, typeof v === "string" ? escapeHTML(v) : v]));

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
        ${formatCalories(raw) ? `<div class="detail-nutrition"><strong>${escapeHTML(formatCalories(raw))}</strong><p>${p.calorie_notes || ''}</p></div>` : ''}
        ${p.review ? `
          <div class="detail-review-box">
            <div class="detail-review-label">Product review</div>
            ${p.review}
          </div>` : ''}
        <div class="detail-footer">
          <div class="detail-price">${formatMoney(p.price)}</div>
          <button class="detail-add-btn" onclick="addKnownProduct(${p.product_id}); closeDetail();">
            ${CART_ICON_SVG} Add to cart
          </button>
        </div>
      </div>
    `;
  } catch (err) {
    content.innerHTML = '<div class="loading" style="width:100%;">Unable to load product</div>';
  }
}

function closeDetail() {
  document.getElementById('detailOverlay').classList.remove('open');
  selectedProductId = null; updatePageLabel();
}

function openCart() {
  renderCart();
  navigatePage('cart');
}
function closeCart() {
  navigatePage('shop');
}

function renderCart() {
  const wrap = document.getElementById('cartItemsWrap');
  if (cart.length === 0) {
    wrap.innerHTML = '<div class="cart-empty">Your cart is empty</div>';
    return;
  }
  const total = cart.reduce((sum, i) => sum + i.price * i.quantity, 0);
  wrap.innerHTML = cart.map(i => `
    <div class="cart-item">
      <div class="cart-item-name">${escapeHTML(i.name)}</div>
      <div class="cart-item-qty">
        <button onclick="changeQty(${i.product_id}, -1)">−</button>
        <span>${i.quantity}</span>
        <button onclick="changeQty(${i.product_id}, 1)">+</button>
      </div>
      <div class="cart-item-price">${formatMoney(i.price * i.quantity)}</div>
    </div>
  `).join('') + `
    <div class="cart-total-row"><span>Total</span><span>${formatMoney(total)}</span></div>
    <button class="checkout-btn" onclick="checkout()">Review checkout</button>
  `;
}

async function checkout() {
  if (!currentUser) { openModal(); switchTab('login'); return; }
  try { const quote = await apiRequest('/api/cart/quote', {method:'POST'}); showCheckoutForm(quote); }
  catch (e) { showToast(e.message); }
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
      ? `Search results for "${value}"`
      : (activeCategory ? document.querySelector('.cat-card.active .cat-name')?.textContent : 'All products') || 'All products';
    navigatePage("shop");
    loadProducts(activeCategory, activeSearch);
  }, 350);
});

async function loadCategories() {
  const res = await fetch(`${API}/api/categories`);
  const categories = await res.json();
  const el = document.getElementById('categories');
  el.innerHTML = '';

  const allCard = makeCatCard(null, 'All', '🛒');
  el.appendChild(allCard);

  categories.forEach(c => {
    el.appendChild(makeCatCard(c.category_id, c.name, CATEGORY_EMOJI[c.name] || '🛍️'));
  });
}

function makeCatCard(id, name, emoji) {
  const div = document.createElement('div');
  div.className = 'cat-card' + (activeCategory === id ? ' active' : '');
  const bg = CATEGORY_COLOR[name] || '#1B635522';
  div.innerHTML = `<div class="cat-icon-badge" style="background:${bg}">${emoji}</div><span class="cat-name">${escapeHTML(name)}</span>`;
  div.onclick = () => {
    activeCategory = id;
    document.querySelectorAll('.cat-card').forEach(c => c.classList.remove('active'));
    div.classList.add('active');
    document.getElementById('products-title').textContent = id ? name : 'All products';
    loadProducts(id, activeSearch);
  };
  return div;
}

async function loadProducts(categoryId, search) {
  const el = document.getElementById('products');
  visibleProductIds = [];
  el.innerHTML = '<div class="loading">Loading...</div>';
  const params = new URLSearchParams();
  if (categoryId) params.set('category_id', categoryId);
  if (search) params.set('search', search);
  if (search) {
    params.delete('search');
    params.set('query', search);
  }
  const endpoint = search ? '/api/search' : '/api/products';
  const url = `${API}${endpoint}${params.toString() ? '?' + params.toString() : ''}`;
  let products;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error('Unable to load products');
    const data = await res.json();
    products = search ? data.results.map(result => result.product) : data;
  } catch (err) {
    el.innerHTML = '<div class="loading">Unable to load products. Please try again.</div>';
    return;
  }
  el.innerHTML = '';

  if (products.length === 0) {
    el.innerHTML = '<div class="loading">No results found</div>';
    return;
  }

  visibleProductIds = products.map(p => p.product_id).slice(0, 100);
  products.forEach(raw => {
    knownProducts.set(raw.product_id, raw);
    const p = Object.fromEntries(Object.entries(raw).map(([k,v]) => [k, typeof v === 'string' ? escapeHTML(v) : v]));
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
        ${formatCalories(raw) ? `<div class="prod-nutrition">${escapeHTML(formatCalories(raw))}</div>` : ''}
        <div class="prod-rating">${stars}</div>
        <div class="prod-review">${p.review || ''}</div>
        <div class="prod-footer">
          <div class="prod-price">${formatMoney(p.price)}</div>
          <button class="prod-add" title="Add to cart" onclick="event.stopPropagation(); addKnownProduct(${p.product_id})">${CART_ICON_SVG}</button>
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
    if (!res.ok) throw new Error(data.detail || 'Something went wrong');

    currentUser = { person_id: data.person_id, first_name: data.first_name };
    saveUser();
    renderAuthArea();

    msg.textContent = 'Account created successfully! ✓';
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
    if (!res.ok) throw new Error(data.detail || 'Invalid email or password');

    currentUser = { person_id: data.person_id, first_name: data.first_name };
    saveUser();
    renderAuthArea();

    msg.textContent = `Welcome back, ${data.first_name}! ✓`;
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
loadCategories().catch(e => showToast(e.message));
loadProducts(null);
