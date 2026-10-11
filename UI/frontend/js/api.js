// Shared safe rendering and cookie-authenticated requests.
function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
async function apiRequest(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body !== undefined) headers.set('Content-Type','application/json');
  if (!['GET','HEAD'].includes((options.method || 'GET').toUpperCase())) {
    const cookie = document.cookie.split('; ').find(c => c.startsWith('market_csrf='));
    if (cookie) headers.set('X-CSRF-Token', decodeURIComponent(cookie.slice('market_csrf='.length)));
  }
  const response = await fetch(path, {...options, headers, credentials:'same-origin', body:options.body === undefined ? undefined : JSON.stringify(options.body)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Please check the submitted information.');
  return data;
}
function formatCalories(product) {
  const value = product.calories_per_100;
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '';
  const unit = product.calorie_basis === 'per_100ml' ? '100 ml' : '100 g';
  const label = product.calorie_status === 'label_verified' ? 'Calories' : 'Estimated calories';
  return `${label}: ${new Intl.NumberFormat('en-US',{maximumFractionDigits:1}).format(value)} kcal per ${unit}`;
}
