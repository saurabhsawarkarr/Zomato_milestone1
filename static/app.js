/**
 * Cinder AI — Frontend Application Logic
 * Connects to the Nextleap Zomato FastAPI backend.
 *
 * Endpoints used:
 *   GET  /metadata/locations  → { locations: string[] }
 *   GET  /metadata/cuisines   → { cuisines: string[] }
 *   POST /recommend           → RecommendationResponse
 */

/* ═══════════════════════════════════════════════════════════
   STATE
   ═══════════════════════════════════════════════════════════ */
const state = {
  locations: [],
  cuisines: [],
  selectedLocation: '',
  selectedBudget: 'medium',
  selectedCuisines: new Set(),
  minRating: 4.0,
  isLoading: false,
};

/* ═══════════════════════════════════════════════════════════
   CUISINE → EMOJI MAP
   ═══════════════════════════════════════════════════════════ */
const CUISINE_EMOJIS = {
  'Italian': '🍝',        'Chinese': '🥢',       'Indian': '🍛',
  'North Indian': '🍛',   'South Indian': '🥘',  'Japanese': '🍱',
  'Mexican': '🌮',        'Thai': '🍜',           'Pizza': '🍕',
  'Burger': '🍔',         'Biryani': '🍚',        'Kebab': '🍢',
  'Desserts': '🍰',       'Ice Cream': '🍦',      'Bakery': '🥐',
  'Seafood': '🦞',        'Continental': '🍽️',   'Fast Food': '🍟',
  'Healthy Food': '🥗',   'Mughlai': '🫕',        'Beverages': '☕',
  'Sandwich': '🥪',       'Cafe': '☕',           'Korean': '🫕',
  'Lebanese': '🧆',       'Mediterranean': '🫒',  'Rolls': '🌯',
  'Momos': '🥟',          'Street Food': '🍢',   'Salad': '🥗',
  'Juice & Beverages': '🥤', 'Maharashtrian': '🍱', 'Bengali': '🍚',
  'Chinese': '🥡',        'Andhra': '🌶️',         'Rajasthani': '🫕',
  'Gujarati': '🫙',       'Punjabi': '🫕',        'Chettinad': '🌶️',
};

function getCuisineEmoji(cuisines) {
  if (!cuisines) return '🍽️';
  const list = Array.isArray(cuisines) ? cuisines : [cuisines];
  for (const c of list) {
    if (CUISINE_EMOJIS[c]) return CUISINE_EMOJIS[c];
  }
  return '🍽️';
}

/* ═══════════════════════════════════════════════════════════
   RANK CONFIG
   ═══════════════════════════════════════════════════════════ */
const RANK_CONFIG = [
  { color: '#FFD700', icon: 'workspace_premium', cssClass: 'rank-gold',   gradient: '#3d2e00, #1a1200' },
  { color: '#C0C0C0', icon: 'military_tech',     cssClass: 'rank-silver', gradient: '#2a2d32, #1a1d22' },
  { color: '#CD7F32', icon: 'emoji_events',       cssClass: 'rank-bronze', gradient: '#2d1e0a, #1a0f00' },
  { color: '#a78bfa', icon: '',                  cssClass: '',            gradient: '#1e1a3d, #0d0a22' },
  { color: '#67e8f9', icon: '',                  cssClass: '',            gradient: '#0a2d2a, #051a18' },
];

/* ═══════════════════════════════════════════════════════════
   INIT
   ═══════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', async () => {
  setupBudgetCards();
  setupRatingSlider();
  setupCharCounter();
  setupLocationDropdown();
  setupForm();
  await loadMetadata();
});

/* ═══════════════════════════════════════════════════════════
   METADATA LOADING
   ═══════════════════════════════════════════════════════════ */
async function loadMetadata() {
  try {
    const [locResult, cuisResult] = await Promise.allSettled([
      fetch('/metadata/locations'),
      fetch('/metadata/cuisines'),
    ]);

    // Locations
    if (locResult.status === 'fulfilled' && locResult.value.ok) {
      const data = await locResult.value.json();
      state.locations = (data.locations || []).sort();
      document.getElementById('locationDropdownHint').textContent =
        state.locations.length > 0 ? 'Type to search or browse...' : 'No locations found';
    } else {
      document.getElementById('locationDropdownHint').textContent =
        '⚠ Server not running — start with: uvicorn src.main:app';
      showToast('API server not connected. Start the server to load data.', 'info');
    }

    // Cuisines
    if (cuisResult.status === 'fulfilled' && cuisResult.value.ok) {
      const data = await cuisResult.value.json();
      state.cuisines = data.cuisines || [];
      renderCuisinePills();
    } else {
      renderCuisinePillsOffline();
    }

  } catch (err) {
    console.warn('Metadata load failed:', err.message);
    document.getElementById('locationDropdownHint').textContent =
      '⚠ Cannot reach server. Run: uvicorn src.main:app --reload';
    renderCuisinePillsOffline();
  }
}

/* ═══════════════════════════════════════════════════════════
   LOCATION DROPDOWN
   ═══════════════════════════════════════════════════════════ */
function setupLocationDropdown() {
  const input    = document.getElementById('locationInput');
  const dropdown = document.getElementById('locationDropdown');
  const arrow    = document.getElementById('locationArrow');
  const wrapper  = document.getElementById('locationWrapper');

  // Show all on focus
  input.addEventListener('focus', () => {
    renderLocationOptions(state.locations.slice(0, 80));
    dropdown.classList.remove('hidden');
    arrow.textContent = 'expand_less';
  });

  // Filter on type
  input.addEventListener('input', () => {
    const q = input.value.toLowerCase().trim();
    const filtered = q
      ? state.locations.filter(l => l.toLowerCase().includes(q))
      : state.locations.slice(0, 80);
    renderLocationOptions(filtered);
    dropdown.classList.remove('hidden');

    // If user edited away from selected value, clear it
    if (input.value !== state.selectedLocation) {
      state.selectedLocation = '';
      document.getElementById('locationValue').value = '';
    }
  });

  // Keyboard: Escape closes
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      dropdown.classList.add('hidden');
      arrow.textContent = 'expand_more';
    }
  });

  // Close on outside click
  document.addEventListener('click', (e) => {
    if (!wrapper.contains(e.target)) {
      dropdown.classList.add('hidden');
      arrow.textContent = 'expand_more';
      // If nothing was selected but user typed something, clear the input
      if (!state.selectedLocation && input.value) {
        input.value = '';
      }
    }
  });
}

function renderLocationOptions(locations) {
  const dropdown = document.getElementById('locationDropdown');

  if (!locations.length) {
    dropdown.innerHTML = `
      <div class="px-4 py-3 text-on-surface-variant text-sm italic flex items-center gap-2">
        <span class="material-symbols-outlined text-sm">search_off</span>
        No locations match your search
      </div>`;
    return;
  }

  dropdown.innerHTML = locations.map(loc => `
    <div
      class="location-option px-4 py-2.5 cursor-pointer text-on-surface text-sm flex items-center gap-2 ${loc === state.selectedLocation ? 'selected' : ''}"
      data-value="${loc}"
    >
      <span class="material-symbols-outlined text-xs text-on-surface-variant shrink-0">location_on</span>
      <span>${loc}</span>
    </div>
  `).join('');

  dropdown.querySelectorAll('.location-option').forEach(opt => {
    opt.addEventListener('click', () => {
      const val = opt.dataset.value;
      document.getElementById('locationInput').value  = val;
      document.getElementById('locationValue').value  = val;
      document.getElementById('locationArrow').textContent = 'expand_more';
      state.selectedLocation = val;
      document.getElementById('locationDropdown').classList.add('hidden');

      // Remove validation error
      document.getElementById('locationInput').classList.remove('border-red-500/60', 'ring-1', 'ring-red-500/30');
    });
  });
}

/* ═══════════════════════════════════════════════════════════
   CUISINE PILLS
   ═══════════════════════════════════════════════════════════ */
function renderCuisinePills() {
  const container = document.getElementById('cuisinePillsContainer');

  if (!state.cuisines.length) {
    container.innerHTML = `<span class="text-on-surface-variant text-xs">No cuisines available</span>`;
    return;
  }

  const displayCuisines = state.cuisines.slice(0, 35);

  container.innerHTML = displayCuisines.map(c => `
    <span
      class="cuisine-pill px-3 py-1 rounded-full border border-white/10 bg-surface-variant/30 text-on-surface text-xs cursor-pointer hover:border-white/30 transition-all select-none"
      data-cuisine="${c}"
    >${c}</span>
  `).join('');

  container.querySelectorAll('.cuisine-pill').forEach(pill => {
    pill.addEventListener('click', () => toggleCuisine(pill));
  });
}

function toggleCuisine(pill) {
  const c = pill.dataset.cuisine;
  if (state.selectedCuisines.has(c)) {
    state.selectedCuisines.delete(c);
    pill.classList.remove('border-primary/50', 'bg-primary/10', 'text-primary');
    pill.classList.add('border-white/10', 'bg-surface-variant/30', 'text-on-surface');
  } else {
    state.selectedCuisines.add(c);
    pill.classList.add('border-primary/50', 'bg-primary/10', 'text-primary');
    pill.classList.remove('border-white/10', 'bg-surface-variant/30', 'text-on-surface');
  }
  updateCuisineLabel();
}

function updateCuisineLabel() {
  const label = document.getElementById('cuisineSelectionLabel');
  const count = state.selectedCuisines.size;
  label.textContent = count > 0 ? `${count} selected` : 'Optional';
  label.className   = count > 0
    ? 'text-xs text-primary font-semibold'
    : 'text-xs text-on-surface-variant font-normal';
}

function renderCuisinePillsOffline() {
  document.getElementById('cuisinePillsContainer').innerHTML = `
    <div class="text-on-surface-variant text-xs flex items-center gap-1.5">
      <span class="material-symbols-outlined text-xs">wifi_off</span>
      Start the API server to load cuisines
    </div>`;
}

/* ═══════════════════════════════════════════════════════════
   BUDGET CARDS
   ═══════════════════════════════════════════════════════════ */
function setupBudgetCards() {
  document.querySelectorAll('.budget-option').forEach(el => {
    el.addEventListener('click', () => {
      // Deactivate all
      document.querySelectorAll('.budget-option').forEach(opt => {
        opt.classList.remove('border-primary/50', 'bg-primary/10', 'shadow-[0_0_18px_rgba(255,83,90,0.2)]', 'active');
        const lbl  = opt.querySelector('.budget-label');
        const sub  = opt.querySelector('.budget-sub');
        const icon = opt.querySelector('.material-symbols-outlined');
        lbl.classList.replace('text-primary', 'text-on-surface');
        sub.classList.replace('text-primary', 'text-on-surface-variant');
        if (icon) { icon.classList.replace('text-primary', 'text-on-surface-variant'); }
      });

      // Activate selected
      el.classList.add('border-primary/50', 'bg-primary/10', 'shadow-[0_0_18px_rgba(255,83,90,0.2)]', 'active');
      const lbl  = el.querySelector('.budget-label');
      const sub  = el.querySelector('.budget-sub');
      const icon = el.querySelector('.material-symbols-outlined');
      lbl.classList.replace('text-on-surface', 'text-primary');
      sub.classList.replace('text-on-surface-variant', 'text-primary');
      if (icon) { icon.classList.replace('text-on-surface-variant', 'text-primary'); }

      state.selectedBudget = el.dataset.value;
    });
  });
}

/* ═══════════════════════════════════════════════════════════
   RATING SLIDER
   ═══════════════════════════════════════════════════════════ */
function setupRatingSlider() {
  const slider  = document.getElementById('ratingSlider');
  const display = document.getElementById('ratingValue');

  const update = () => {
    const val = parseFloat(slider.value);
    state.minRating = val;
    display.textContent = val.toFixed(1) + '+';
    const pct = (val / 5) * 100;
    slider.style.setProperty('--range-progress', `${pct}%`);
  };

  slider.addEventListener('input', update);
  update(); // Initialize on load
}

/* ═══════════════════════════════════════════════════════════
   CHARACTER COUNTER
   ═══════════════════════════════════════════════════════════ */
function setupCharCounter() {
  const textarea = document.getElementById('additionalPrefs');
  const counter  = document.getElementById('charCounter');

  textarea.addEventListener('input', () => {
    const len = textarea.value.length;
    counter.textContent = `${len}/500`;
    counter.className   = len > 450
      ? 'text-xs text-error font-semibold'
      : 'text-xs text-on-surface-variant';
  });
}

/* ═══════════════════════════════════════════════════════════
   FORM SUBMIT
   ═══════════════════════════════════════════════════════════ */
function setupForm() {
  document.getElementById('submitBtn').addEventListener('click', handleSubmit);
  // Allow pressing Enter in the location input to confirm selection
  document.getElementById('locationInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      document.getElementById('locationDropdown').classList.add('hidden');
    }
  });
}

async function handleSubmit() {
  if (state.isLoading) return;

  // ── Validate location ──
  if (!state.selectedLocation) {
    const inp = document.getElementById('locationInput');
    inp.classList.add('border-red-500/60', 'ring-1', 'ring-red-500/30');
    showToast('Please select a location from the dropdown.', 'error');
    inp.focus();
    return;
  }

  const additionalPrefs = document.getElementById('additionalPrefs').value.trim();

  const payload = {
    location:                state.selectedLocation,
    budget:                  state.selectedBudget,
    cuisine:                 state.selectedCuisines.size > 0
                               ? [...state.selectedCuisines].join(',')
                               : null,
    min_rating:              state.minRating,
    additional_preferences:  additionalPrefs || null,
  };

  showLoading();

  try {
    const res  = await fetch('/recommend', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });

    const data = await res.json();

    if (!res.ok) {
      const msg = (Array.isArray(data.detail) ? data.detail[0]?.msg : data.detail)
                  || data.message
                  || `Server error (${res.status})`;
      throw new Error(msg);
    }

    renderResults(data);

  } catch (err) {
    console.error('Recommendation error:', err);
    showToast(err.message || 'Failed to connect. Is the server running?', 'error');
  } finally {
    hideLoading();
  }
}

/* ═══════════════════════════════════════════════════════════
   RENDER RESULTS
   ═══════════════════════════════════════════════════════════ */
function renderResults(data) {
  const grid            = document.getElementById('resultsGrid');
  const emptyState      = document.getElementById('emptyState');
  const summaryBanner   = document.getElementById('summaryBanner');
  const relaxationBadge = document.getElementById('relaxationBadge');
  const resultsCount    = document.getElementById('resultsCount');

  const recs = data.recommendations || [];

  if (!recs.length) {
    grid.innerHTML = '';
    emptyState.classList.remove('hidden');
    emptyState.querySelector('h3').textContent = 'No restaurants found';
    emptyState.querySelector('p').textContent  =
      'Try broadening your search — choose a different budget, lower the minimum rating, or remove cuisine filters.';
    summaryBanner.classList.add('hidden');
    relaxationBadge.classList.add('hidden');
    resultsCount.textContent = 'No matches found';
    return;
  }

  emptyState.classList.add('hidden');

  // Count
  resultsCount.textContent = `${recs.length} match${recs.length !== 1 ? 'es' : ''} found`;

  // AI Summary
  if (data.summary) {
    summaryBanner.classList.remove('hidden');
    document.getElementById('summaryText').textContent = data.summary;
  } else {
    summaryBanner.classList.add('hidden');
  }

  // Filter Relaxation
  if (data.filters_relaxed) {
    relaxationBadge.classList.remove('hidden');
  } else {
    relaxationBadge.classList.add('hidden');
  }

  // Render cards
  grid.innerHTML = recs.map((rec, i) => renderCard(rec, i)).join('');

  // Staggered entrance
  grid.querySelectorAll('.result-card').forEach((card, i) => {
    card.style.animationDelay = `${i * 110}ms`;
    card.classList.add('fade-in-up');
  });

  // Smooth scroll to results
  setTimeout(() => {
    document.getElementById('resultsSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 100);
}

/* ═══════════════════════════════════════════════════════════
   RENDER SINGLE CARD
   ═══════════════════════════════════════════════════════════ */
function renderCard(rec, index) {
  const rank         = RANK_CONFIG[index] || RANK_CONFIG[4];
  const emoji        = getCuisineEmoji(rec.cuisines);
  const cuisines     = Array.isArray(rec.cuisines) ? rec.cuisines : (rec.cuisines ? [rec.cuisines] : []);
  const cost         = typeof rec.cost_for_two === 'number' ? Math.round(rec.cost_for_two) : rec.cost_for_two;
  const explanation  = rec.explanation || 'A great match based on your preferences.';
  const cardId       = `card-${index}`;
  const isLong       = explanation.length > 140;
  const shortExp     = isLong ? explanation.slice(0, 140).trimEnd() + '...' : explanation;

  const cuisinePills = cuisines.slice(0, 4).map(c => `
    <span class="px-2 py-0.5 rounded border border-white/10 bg-white/5 text-xs text-on-surface-variant">${c}</span>
  `).join('');

  const rankIconHtml = rank.icon
    ? `<span class="material-symbols-outlined text-[13px]" style="font-variation-settings:'FILL' 1; color:${rank.color}">${rank.icon}</span>`
    : '';

  const readMoreHtml = isLong ? `
    <button
      class="text-xs text-primary hover:text-primary-container transition-colors mt-1 font-semibold"
      onclick="toggleExplanation('${cardId}', this)"
      data-full="${escapeHtml(explanation)}"
      data-short="${escapeHtml(shortExp)}"
    >Read more</button>
  ` : '';

  return `
    <article class="result-card glass-card rounded-xl overflow-hidden group relative flex flex-col" id="${cardId}" style="opacity:0">

      <!-- Rank Badge -->
      <div class="absolute top-3 right-3 z-10 bg-black/60 backdrop-blur-md border border-white/20 rounded-full px-2.5 py-1 flex items-center gap-1.5 shadow-lg">
        <span class="text-sm font-bold font-headline-md" style="color:${rank.color}">#${rec.rank}</span>
        ${rankIconHtml}
      </div>

      <!-- Gradient Header (no food image) -->
      <div class="h-28 relative overflow-hidden" style="background: linear-gradient(135deg, ${rank.gradient})">
        <!-- Giant first-letter watermark -->
        <div class="absolute inset-0 flex items-center justify-center select-none pointer-events-none">
          <span class="text-[100px] font-black leading-none text-white/[0.04] uppercase">${(rec.name || 'R').charAt(0)}</span>
        </div>
        <!-- Bottom info strip -->
        <div class="absolute bottom-0 left-0 right-0 px-4 pb-3 pt-6 flex items-center justify-between"
             style="background: linear-gradient(to top, #0d1117 0%, transparent 100%)">
          <span class="text-2xl leading-none">${emoji}</span>
          <div class="flex items-center gap-1 bg-black/50 backdrop-blur-sm rounded-full px-2.5 py-0.5">
            <span class="material-symbols-outlined text-[#ec6a06] text-sm" style="font-variation-settings:'FILL' 1;">star</span>
            <span class="text-xs text-white font-semibold">${rec.rating}</span>
          </div>
        </div>
      </div>

      <!-- Card Body -->
      <div class="p-md flex flex-col flex-grow gap-2.5">

        <!-- Name + Cost -->
        <div class="flex justify-between items-start gap-2">
          <h3 class="font-headline-md text-[17px] font-semibold text-on-surface leading-snug">${rec.name}</h3>
          <span class="shrink-0 px-2 py-0.5 rounded border border-primary/25 bg-primary/5 text-xs text-primary whitespace-nowrap">₹${cost} for two</span>
        </div>

        <!-- Cuisine Tags -->
        <div class="flex flex-wrap gap-1.5">${cuisinePills}</div>

        <!-- AI Explanation -->
        <div class="mt-auto border-l-2 border-primary-container pl-3 py-1 mt-2">
          <p class="text-sm text-on-surface-variant italic leading-relaxed" id="exp-${cardId}">"${shortExp}"</p>
          ${readMoreHtml}
        </div>

      </div>
    </article>
  `;
}

/* Toggle explanation length */
function toggleExplanation(cardId, btn) {
  const p        = document.getElementById(`exp-${cardId}`);
  const expanded = btn.textContent.trim() === 'Read less';
  if (expanded) {
    p.textContent      = `"${btn.dataset.short}"`;
    btn.textContent    = 'Read more';
  } else {
    p.textContent      = `"${btn.dataset.full}"`;
    btn.textContent    = 'Read less';
  }
}

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

/* ═══════════════════════════════════════════════════════════
   LOADING STATE
   ═══════════════════════════════════════════════════════════ */
function showLoading() {
  state.isLoading = true;

  document.getElementById('loadingState').classList.remove('hidden');
  document.getElementById('submitBtn').disabled = true;
  document.getElementById('submitBtn').innerHTML = `
    <span class="material-symbols-outlined text-sm animate-spin">progress_activity</span>
    Thinking...
  `;

  // Show skeleton cards in the grid
  document.getElementById('resultsGrid').innerHTML = Array.from({ length: 5 }, () => `
    <div class="skeleton-card">
      <div class="h-28 skeleton-shimmer"></div>
      <div class="p-6 flex flex-col gap-3">
        <div class="flex justify-between gap-4">
          <div class="h-5 w-2/3 skeleton-shimmer skeleton-line rounded"></div>
          <div class="h-5 w-1/4 skeleton-shimmer skeleton-line rounded"></div>
        </div>
        <div class="flex gap-2">
          <div class="h-4 w-16 skeleton-shimmer skeleton-line rounded-full"></div>
          <div class="h-4 w-20 skeleton-shimmer skeleton-line rounded-full"></div>
          <div class="h-4 w-14 skeleton-shimmer skeleton-line rounded-full"></div>
        </div>
        <div class="h-3 w-full skeleton-shimmer skeleton-line rounded mt-2"></div>
        <div class="h-3 w-4/5 skeleton-shimmer skeleton-line rounded"></div>
        <div class="h-3 w-3/5 skeleton-shimmer skeleton-line rounded"></div>
      </div>
    </div>
  `).join('');
}

function hideLoading() {
  state.isLoading = false;

  document.getElementById('loadingState').classList.add('hidden');
  const btn = document.getElementById('submitBtn');
  btn.disabled = false;
  btn.innerHTML = `
    <span class="material-symbols-outlined text-sm">auto_awesome</span>
    Get AI Recommendations
  `;
}

/* ═══════════════════════════════════════════════════════════
   TOAST NOTIFICATIONS
   ═══════════════════════════════════════════════════════════ */
const TOAST_CONFIG = {
  error:   { bg: 'bg-error-container border-error/30',                                    text: 'text-on-error-container', icon: 'error'         },
  success: { bg: 'bg-tertiary-container/20 border-tertiary/30 backdrop-blur-md',          text: 'text-tertiary',           icon: 'check_circle'  },
  info:    { bg: 'glass-card border-white/10',                                            text: 'text-on-surface',         icon: 'info'          },
};

function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const id        = `toast-${Date.now()}`;
  const cfg       = TOAST_CONFIG[type] || TOAST_CONFIG.info;

  const el = document.createElement('div');
  el.id        = id;
  el.className = `${cfg.bg} ${cfg.text} border rounded-xl px-4 py-3 flex items-start gap-3 shadow-2xl slide-in-right max-w-sm`;
  el.innerHTML = `
    <span class="material-symbols-outlined text-sm mt-0.5 shrink-0">${cfg.icon}</span>
    <p class="text-sm flex-1 leading-relaxed">${message}</p>
    <button onclick="removeToast('${id}')" class="text-current opacity-50 hover:opacity-100 ml-1 transition-opacity shrink-0">
      <span class="material-symbols-outlined text-sm">close</span>
    </button>
  `;

  container.appendChild(el);
  setTimeout(() => removeToast(id), 6000);
}

function removeToast(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove('slide-in-right');
  el.classList.add('slide-out-right');
  setTimeout(() => el?.remove(), 320);
}
