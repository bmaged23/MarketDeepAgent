function chatProducts(result) {
  const products = new Map();
  for (const section of result.results?.retrieval?.sections || []) {
    for (const chunk of section.chunks || []) {
      if (chunk.approval === 1 && chunk.product) products.set(chunk.product.product_id, chunk.product);
    }
  }
  // Server-supplied cards are hydrated from current SQL, including context-only choices.
  for (const product of result.products || []) products.set(product.product_id, product);
  return [...products.values()];
}
let currentPage = 'shop';
let conversationId = null;
let recentProductIds = [];
let chatBusy = false;
let sessionGeneration = 0;
const pageTitles = {shop:'Shop',product:'Product details',cart:'Shopping cart',orders:'Your orders',profile:'Your profile',settings:'Assistant settings'};
const panel = document.getElementById('assistantPanel');
const messages = document.getElementById('chatMessages');
function updatePageLabel() { document.getElementById('assistantPageLabel').textContent = pageTitles[selectedProductId ? 'product' : currentPage]; }
function resetAssistant() {
  if (currentUser) sessionStorage.removeItem('market_conversation_'+currentUser.person_id);
  sessionGeneration++; conversationId = null; recentProductIds = [];
  for (const id of ['ordersContent','profileContent','settingsContent','cartItemsWrap']) document.getElementById(id).replaceChildren();
  messages.replaceChildren(); chatMessage('assistant','How can I help with your shopping today?');
  document.getElementById('chatStatus').textContent = '';
  document.getElementById('chatInput').value = '';
}
async function refreshSession() {
  const generation = sessionGeneration;
  try {
    const user = await apiRequest('/api/me');
    if (generation !== sessionGeneration) return;
    if (currentUser?.person_id !== user.person_id) resetAssistant();
    currentUser = user; renderAuthArea(); await refreshCart();
    const remembered = sessionStorage.getItem('market_conversation_'+user.person_id);
    if (remembered && !conversationId) {
      try {
        const history = await apiRequest('/api/conversations/'+encodeURIComponent(remembered));
        if (currentUser?.person_id !== user.person_id) return;
        conversationId = remembered; messages.replaceChildren();
        for (const message of history) chatMessage(message.role,message.content);
      } catch (e) { sessionStorage.removeItem('market_conversation_'+user.person_id); }
    }
  } catch (e) { currentUser = null; cart = []; renderAuthArea(); updateCartBadge(); }
}
async function refreshCart() {
  if (!currentUser) return;
  const owner = currentUser.person_id;
  const snapshot = await apiRequest('/api/cart');
  if (currentUser?.person_id !== owner) return;
  cart = snapshot.items; updateCartBadge(); renderCart();
}
function navigatePage(page) {
  if (!['shop','cart','orders','profile','settings'].includes(page)) return;
  if (page !== 'shop' && !currentUser) { openModal(); switchTab('login'); return; }
  closeDetail(); currentPage = page;
  for (const id of ['shop','cart','orders','profile','settings']) document.getElementById(id+'Page').hidden = id !== page;
  updatePageLabel();
  const loaders = {cart:refreshCart,orders:loadOrders,profile:loadProfile,settings:loadSettings};
  if (loaders[page]) loaders[page]().catch(e => showToast(e.message));
}
function toggleAssistant(open) {
  panel.hidden = !open; document.body.classList.toggle('assistant-open',open);
  document.getElementById('assistantTab').setAttribute('aria-expanded',String(open));
  if (open) document.getElementById('chatInput').focus(); else document.getElementById('assistantTab').focus();
}
document.getElementById('assistantTab').onclick = () => toggleAssistant(panel.hidden);
document.getElementById('closeAssistant').onclick = () => toggleAssistant(false);
document.getElementById('newChat').onclick = () => { if (!chatBusy) resetAssistant(); };
function chatMessage(role,text) {
  const el = document.createElement('div'); el.className = 'chat-message '+role;
  if (role === 'assistant') renderChatMarkdown(el,text); else el.textContent = text;
  messages.append(el);
  if (role === 'assistant') focusChatAnswer(messages,el); else messages.scrollTop = messages.scrollHeight;
  return el;
}
function actionButton(container,label,callback) {
  const button = document.createElement('button'); button.type = 'button'; button.textContent = label;
  button.onclick = () => Promise.resolve(callback()).catch(e => showToast(e.message)); container.append(button); return button;
}
function actionTargetsCurrentView(action) {
  if (action.action === 'navigate') return !selectedProductId && currentPage === action.page;
  if (action.action === 'open_product') return selectedProductId === action.product_id;
  if (action.action === 'apply_search') return !selectedProductId && currentPage === 'shop' && activeSearch === (action.query || '') && activeCategory === (action.category_id || null);
  return false;
}
async function executeAction(action) {
  if (action.action === 'navigate') navigatePage(action.page);
  else if (action.action === 'open_product' && Number.isInteger(action.product_id) && action.product_id > 0) await showProductDetail(action.product_id);
  else if (action.action === 'apply_search') {
    activeSearch = String(action.query || '').slice(0,200); activeCategory = action.category_id || null;
    document.getElementById('searchInput').value = activeSearch; navigatePage('shop'); await loadProducts(activeCategory,activeSearch);
  } else if (action.action === 'refresh_cart') await refreshCart();
}
function findQuotes(value,found=[]) {
  if (!value || typeof value !== 'object') return found;
  if (value.ready === true && typeof value.confirmation_token === 'string' && value.cart) found.push(value);
  else for (const item of Object.values(value)) findQuotes(item,found);
  return found;
}
document.getElementById('chatInput').onkeydown = event => {
  // Preserve multiline entry and input-method composition (for example IME).
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  if (!chatBusy && !event.repeat) document.getElementById('chatForm').requestSubmit();
};
document.getElementById('chatForm').onsubmit = async event => {
  event.preventDefault(); if (chatBusy) return;
  if (!currentUser) { openModal(); switchTab('login'); return; }
  const input = document.getElementById('chatInput'), query = input.value.trim(); if (!query) return;
  const owner = currentUser.person_id, generation = sessionGeneration;
  const page = selectedProductId ? 'product' : currentPage;
  const startingView = {productId:selectedProductId,categoryId:activeCategory,search:activeSearch};
  chatMessage('user',query); input.value = ''; chatBusy = true;
  document.getElementById('chatSend').disabled = true; document.getElementById('newChat').disabled = true;
  document.getElementById('chatStatus').textContent = 'Working on your request…';
  try {
    const result = await apiRequest('/api/chat', {method:'POST', body:{query,conversation_id:conversationId,page_context:{page,product_id:selectedProductId,category_id:activeCategory,search:activeSearch.slice(0,200),visible_product_ids:page === 'shop' ? visibleProductIds : [],referenced_product_ids:recentProductIds}}});
    if (generation !== sessionGeneration || currentUser?.person_id !== owner) return;
    conversationId = result.conversation_id;
    sessionStorage.setItem('market_conversation_'+owner,conversationId);
    const reply = chatMessage('assistant',result.answer);
    // Apply requested navigation immediately, independently of cart synchronization.
    const sameView = (selectedProductId ? 'product' : currentPage) === page && selectedProductId === startingView.productId && activeCategory === startingView.categoryId && activeSearch === startingView.search;
    const completedActions = new Set();
    if (sameView) {
      for (const action of result.actions || []) {
        if (action.trigger === 'on_click' || action.action === 'refresh_cart' || actionTargetsCurrentView(action)) continue;
        if (generation !== sessionGeneration || currentUser?.person_id !== owner) return;
        await executeAction(action);
        if (generation !== sessionGeneration || currentUser?.person_id !== owner) return;
        completedActions.add(action);
      }
    }
    const responseProducts = chatProducts(result);
    const cardProductIds = new Set(responseProducts.map(product => product.product_id));
    for (const action of result.actions || []) {
      if (action.action === 'refresh_cart' || actionTargetsCurrentView(action) || (action.action === 'open_product' && cardProductIds.has(action.product_id))) continue;
      const label = action.action === 'open_product'
        ? (completedActions.has(action) ? 'View product again' : 'View product')
        : action.action === 'navigate' ? (action.page === 'cart' ? 'View cart' : `Open ${pageTitles[action.page] || 'page'}`) : action.action.replaceAll('_',' ');
      actionButton(reply,label, () => executeAction(action));
    }
    const shown = new Set();
    for (const product of responseProducts) {
        if (shown.has(product.product_id)) continue;
        shown.add(product.product_id); knownProducts.set(product.product_id,product);
        const card = document.createElement('div'); card.className = 'assistant-product';
        const title = document.createElement('strong'); title.textContent = product.name; card.append(title);
        const price = document.createElement('p'); price.textContent = formatMoney(product.price); card.append(price);
        const calories = formatCalories(product);
        if (calories) { const nutrition = document.createElement('p'); nutrition.textContent = calories; card.append(nutrition); }
        const opened = [...completedActions].some(action => action.action === 'open_product' && action.product_id === product.product_id);
        if (selectedProductId !== product.product_id) actionButton(card,opened ? 'View product again' : 'View product',() => showProductDetail(product.product_id));
        actionButton(card,'Add to cart',() => addToCart(product.product_id,product.name,product.price));
        reply.append(card);
    }
    if (shown.size) recentProductIds = [...shown].slice(0,10);
    for (const action of result.actions || []) if (action.action === 'open_product') recentProductIds = [action.product_id, ...recentProductIds.filter(id => id !== action.product_id)].slice(0,10);
    for (const quote of findQuotes(result.results)) actionButton(reply,'Review and confirm checkout',() => showCheckoutForm(quote));
    focusChatAnswer(messages,reply);
    try { await refreshCart(); } catch (e) { showToast('Reply ready; cart refresh failed. '+e.message); }
    if (generation !== sessionGeneration || currentUser?.person_id !== owner) return;
    const status = result.memory_status;
    document.getElementById('chatStatus').textContent = !sameView && result.actions?.some(a => a.trigger !== 'on_click' && a.action !== 'refresh_cart') ? 'You changed the view while I was working. Use the button above to open the result.' : status?.sync?.failed || status?.recall_degraded ? 'Reply ready. Memory sync is unavailable; updates will be retried.' : status?.saved ? 'Preference saved. Manage it in Settings.' : '';
  } catch (e) { if (generation === sessionGeneration) { chatMessage('assistant',e.message); document.getElementById('chatStatus').textContent = ''; } }
  finally { chatBusy = false; document.getElementById('chatSend').disabled = false; document.getElementById('newChat').disabled = false; }
};
function showCheckoutForm(quote) {
  const owner = currentUser?.person_id; if (!owner) return;
  closeDetail(); currentPage = 'cart';
  for (const id of ['shop','cart','orders','profile','settings']) document.getElementById(id+'Page').hidden = id !== 'cart';
  updatePageLabel();
  if (!quote.ready) { showToast('Resolve cart issues before checkout'); return; }
  const wrap = document.getElementById('cartItemsWrap');
  // navigatePage refreshes asynchronously; mount the form after that refresh.
  refreshCart().then(() => {
    if (currentUser?.person_id !== owner) return;
    const form = document.createElement('form'); form.className = 'checkout-confirmation';
    form.innerHTML = `<h3>Confirm your order</h3><p>${escapeHTML(quote.cart.items.map(i => `${i.quantity} × ${i.name}`).join(', '))}</p><p>Total: <strong>${formatMoney(quote.cart.total)}</strong></p><p>Cash on delivery. Payment is collected on delivery.</p><label>Delivery address<textarea name="address" required maxlength="1000"></textarea></label><label><input name="confirmed" type="checkbox" required> I confirm this order and total.</label><button type="submit" class="checkout-btn">Confirm order</button><div role="status"></div>`;
    form.elements.address.value = currentUser?.address || '';
    form.onsubmit = async e => {
      e.preventDefault(); const button = form.querySelector('button'), status = form.querySelector('[role=status]'); button.disabled = true;
      try {
        const result = await apiRequest('/api/cart/checkout',{method:'POST',body:{token:quote.confirmation_token,confirmed:form.elements.confirmed.checked,delivery_address:form.elements.address.value,payment_method:'cash_on_delivery'}});
        if (currentUser?.person_id !== owner) return;
        await refreshCart(); showToast(`Order #${result.order.order_id} confirmed`); navigatePage('orders'); loadProducts(activeCategory,activeSearch);
      } catch (err) { status.textContent = err.message; button.disabled = false; }
    };
    wrap.append(form);
  }).catch(e => showToast(e.message));
}
async function loadOrders() {
  const owner = currentUser?.person_id, orders = await apiRequest('/api/orders');
  if (currentUser?.person_id !== owner || currentPage !== 'orders') return;
  const container = document.getElementById('ordersContent'); container.replaceChildren();
  if (!orders.length) { container.textContent = 'You have no orders yet.'; return; }
  for (const order of orders) {
    const card = document.createElement('article'); card.className = 'order-card';
    const title = document.createElement('h3'); title.textContent = `Order #${order.order_id} · ${order.status}`; card.append(title);
    const info = document.createElement('p'); info.textContent = `${formatMoney(order.total_amount)} · Shipping: ${order.shipping_status} · Payment: ${order.payment_status}`; card.append(info);
    for (const item of order.items || []) {
      const row = document.createElement('p'); row.textContent = `${item.quantity} × ${item.name || item.product_name || 'Product #'+item.product_id}`; card.append(row);
      if (order.review_eligible) actionButton(row,'Rate or comment',() => reviewForm(row,order.order_id,item.product_id));
    }
    container.append(card);
  }
}
function reviewForm(container,order_id,product_id) {
  if (container.querySelector('form')) return;
  const form = document.createElement('form'); form.innerHTML = '<label>Rating<select name="rating"><option value="">No rating</option><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select></label><label>Comment<textarea name="comment" maxlength="2000"></textarea></label><button>Save review</button><span role="status"></span>';
  form.onsubmit = async e => { e.preventDefault(); try { await apiRequest('/api/reviews',{method:'POST',body:{order_id,product_id,rating:form.elements.rating.value ? Number(form.elements.rating.value) : null,comment:form.elements.comment.value || ''}}); form.querySelector('[role=status]').textContent='Review saved'; } catch (err) { form.querySelector('[role=status]').textContent=err.message; } }; container.append(form);
}
async function loadProfile() {
  const owner = currentUser?.person_id, profile = await apiRequest('/api/me');
  if (currentUser?.person_id !== owner || currentPage !== 'profile') return;
  const container = document.getElementById('profileContent'); container.replaceChildren();
  const form = document.createElement('form'); form.className = 'settings-form';
  for (const [name,label] of [['first_name','First name'],['last_name','Last name'],['phone','Phone'],['address','Address']]) {
    const field = document.createElement('label'); field.textContent = label; const input = document.createElement('input'); input.name=name; input.value=profile[name] || ''; input.required=name.includes('name'); input.maxLength=name==='address'?1000:name==='phone'?40:100; field.append(input); form.append(field);
  }
  const email = document.createElement('p'); email.textContent=profile.email; form.append(email);
  const button=document.createElement('button'); button.textContent='Save profile'; form.append(button);
  form.onsubmit=async e=>{ e.preventDefault(); try { const payload=Object.fromEntries(new FormData(form)); await apiRequest('/api/profile',{method:'PATCH',body:payload}); await refreshSession(); showToast('Profile saved'); } catch(err) { showToast(err.message); } }; container.append(form);
}
async function loadSettings() {
  const owner = currentUser?.person_id;
  const [preferences,memories]=await Promise.all([apiRequest('/api/preferences'),apiRequest('/api/memories')]);
  if (currentUser?.person_id !== owner || currentPage !== 'settings') return;
  const container=document.getElementById('settingsContent'); container.replaceChildren();
  const label=document.createElement('label'), toggle=document.createElement('input'); toggle.type='checkbox'; toggle.checked=preferences.memory_enabled;
  label.append(toggle,document.createTextNode(' Remember my preferences across conversations')); container.append(label);
  const explanation=document.createElement('p'); explanation.textContent='Turning memory off stops saving and recalling preferences. Existing memories remain until you delete them. Chat history is separate.'; container.append(explanation);
  toggle.onchange=async()=>{ try { await apiRequest('/api/preferences',{method:'PATCH',body:{memory_enabled:toggle.checked}}); } catch(e){toggle.checked=!toggle.checked;showToast(e.message);} };
  const heading=document.createElement('h3'); heading.textContent='What the assistant remembers'; container.append(heading);
  for (const memory of memories) {
    const row=document.createElement('form'); row.className='memory-card'; const input=document.createElement('textarea'); input.value=memory.text; input.required=true; input.maxLength=500; input.setAttribute('aria-label','Memory'); row.append(input);
    const save=document.createElement('button'); save.textContent='Save changes'; row.append(save);
    row.onsubmit=async e=>{e.preventDefault();try{await apiRequest('/api/memories/'+memory.memory_id,{method:'PATCH',body:{text:input.value}});showToast('Memory updated');}catch(err){showToast(err.message);}};
    actionButton(row,'Delete',async()=>{await apiRequest('/api/memories/'+memory.memory_id,{method:'DELETE'});await loadSettings();});container.append(row);
  }
  if (!memories.length) { const empty=document.createElement('p');empty.textContent='No preferences saved yet.';container.append(empty); }
  actionButton(container,'Delete all memories',async()=>{if (!confirm('Delete all saved preferences?')) return;await apiRequest('/api/memories',{method:'DELETE'});await loadSettings();});
  actionButton(container,'Delete chat history',async()=>{if (!confirm('Delete your conversations? Saved preferences are managed separately.')) return;await apiRequest('/api/conversations',{method:'DELETE'});resetAssistant();showToast('Chat history deleted');});
}
const resize=document.getElementById('assistantResize');
function setPanelWidth(width) { document.documentElement.style.setProperty('--assistant-width',Math.max(280,Math.min(600,width))+'px'); }
resize.onpointerdown=e=>{resize.setPointerCapture(e.pointerId);resize.onpointermove=move=>setPanelWidth(innerWidth-move.clientX);};
resize.onpointerup=()=>{resize.onpointermove=null;}; resize.onpointercancel=resize.onpointerup;
resize.onkeydown=e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();setPanelWidth(panel.getBoundingClientRect().width+(e.key==='ArrowLeft'?20:-20));}};
refreshSession(); updatePageLabel();
