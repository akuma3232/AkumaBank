/**
 * main.js – AkumaBank Future UI & Cyber Core Engine
 * Complete interactive suite: Dark/Light Mode, Command HUD (Ctrl+K),
 * 3D Holographic Card physics, Casablanca Financial Clock,
 * Web Audio synthetic micro-feedback, and toast notifications.
 */

// ── Web Audio Synthetic Micro-Feedback ──────────────────────────────────────
const SoundFX = {
  ctx: null,
  enabled: true,
  init() {
    if (!this.ctx && (window.AudioContext || window.webkitAudioContext)) {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    }
  },
  play(frequency = 880, type = 'sine', duration = 0.05, gain = 0.03) {
    if (!this.enabled) return;
    try {
      this.init();
      if (!this.ctx) return;
      if (this.ctx.state === 'suspended') {
        this.ctx.resume();
      }
      const osc = this.ctx.createOscillator();
      const vol = this.ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(frequency, this.ctx.currentTime);
      vol.gain.setValueAtTime(gain, this.ctx.currentTime);
      vol.gain.exponentialRampToValueAtTime(0.0001, this.ctx.currentTime + duration);
      osc.connect(vol);
      vol.connect(this.ctx.destination);
      osc.start();
      osc.stop(this.ctx.currentTime + duration);
    } catch (_) {
      // Audio autoplay policy catch
    }
  },
  click() { this.play(720, 'sine', 0.04, 0.02); },
  success() {
    this.play(640, 'triangle', 0.06, 0.03);
    setTimeout(() => this.play(960, 'sine', 0.08, 0.03), 50);
  },
  hud() {
    this.play(520, 'sine', 0.05, 0.03);
    setTimeout(() => this.play(780, 'sine', 0.06, 0.02), 40);
  }
};

// ── Theme Manager (Dark / Light) ─────────────────────────────────────────────
const ThemeManager = {
  init() {
    const current = localStorage.getItem('akuma-theme') || 'dark';
    this.applyTheme(current);

    const toggleBtns = document.querySelectorAll('#themeToggleBtn, .theme-toggle-btn');
    toggleBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        SoundFX.click();
        const active = document.documentElement.getAttribute('data-theme') || 'dark';
        const next = active === 'dark' ? 'light' : 'dark';
        this.applyTheme(next);
      });
    });
  },
  applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('akuma-theme', theme);
    window.dispatchEvent(new Event('themeChanged'));
  }
};

// ── Casablanca Financial Clock ───────────────────────────────────────────────
function initCasablancaClock() {
  const clockEl = document.getElementById('casablancaClockText');
  if (!clockEl) return;

  function update() {
    try {
      const now = new Date();
      const formatted = now.toLocaleTimeString('fr-FR', {
        timeZone: 'Africa/Casablanca',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      });
      clockEl.textContent = formatted;
    } catch (e) {
      const now = new Date();
      clockEl.textContent = now.toTimeString().split(' ')[0];
    }
  }

  update();
  setInterval(update, 1000);
}

// ── 3D Holographic Card Physics & Tilt ───────────────────────────────────────
function initHolographicCards() {
  const cards = document.querySelectorAll('.cyber-card');

  cards.forEach(card => {
    card.addEventListener('mousemove', e => {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      const centerX = rect.width / 2;
      const centerY = rect.height / 2;

      // Calculate tilt angles (-14 to +14 deg)
      const rotateX = ((centerY - y) / centerY) * 12;
      const rotateY = ((x - centerX) / centerX) * 12;

      card.style.transform = `perspective(1000px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) translateZ(8px)`;

      // Dynamic holographic reflection offset
      const xPct = ((x / rect.width) * 100).toFixed(1);
      const yPct = ((y / rect.height) * 100).toFixed(1);
      card.style.setProperty('--sheen-x', `${xPct}%`);
      card.style.setProperty('--sheen-y', `${yPct}%`);
    });

    card.addEventListener('mouseleave', () => {
      card.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) translateZ(0)';
      card.style.setProperty('--sheen-x', '50%');
      card.style.setProperty('--sheen-y', '50%');
    });
  });
}

// ── Card Number Masking / Reveal ────────────────────────────────────────────
function toggleCardNumberDisplay(elementId, btn) {
  SoundFX.click();
  const el = document.getElementById(elementId);
  if (!el) return;

  const raw = el.getAttribute('data-raw-number') || '';
  const isMasked = el.classList.contains('is-revealed');
  const icon = btn ? btn.querySelector('i') : null;

  if (isMasked) {
    // Mask again: 4240 •••• •••• 1234
    const first4 = raw.length >= 4 ? raw.slice(0, 4) : '••••';
    const last4 = raw.length >= 4 ? raw.slice(-4) : raw;
    el.innerHTML = `${first4} &nbsp; •••• &nbsp; •••• &nbsp; ${last4}`;
    el.classList.remove('is-revealed');
    if (icon) {
      icon.classList.remove('bi-eye-slash');
      icon.classList.add('bi-eye');
    }
  } else {
    // Reveal formatted: 4240 1234 5678 9012
    el.textContent = raw.replace(/(.{4})/g, '$1 ').trim();
    el.classList.add('is-revealed');
    if (icon) {
      icon.classList.remove('bi-eye');
      icon.classList.add('bi-eye-slash');
    }
  }
}

// ── CVV Masking / Reveal ────────────────────────────────────────────────────
function toggleCvvDisplay(spanEl, cvvCode) {
  SoundFX.click();
  if (!spanEl) return;
  if (spanEl.getAttribute('data-revealed') === 'true') {
    spanEl.textContent = '•••';
    spanEl.removeAttribute('data-revealed');
    spanEl.classList.remove('text-warning');
  } else {
    spanEl.textContent = cvvCode;
    spanEl.setAttribute('data-revealed', 'true');
    spanEl.classList.add('text-warning');
    setTimeout(() => {
      if (spanEl.getAttribute('data-revealed') === 'true') {
        spanEl.textContent = '•••';
        spanEl.removeAttribute('data-revealed');
        spanEl.classList.remove('text-warning');
      }
    }, 4000);
  }
}

// ── Toast System & Clipboard Copy ───────────────────────────────────────────
function showCyberToast(message, type = 'info', title = 'AkumaBank Sentinel') {
  SoundFX.success();
  let container = document.getElementById('cyberToastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'cyberToastContainer';
    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    container.style.zIndex = '1099';
    document.body.appendChild(container);
  }

  const toastId = 'toast_' + Date.now();
  const iconClass = type === 'success'
    ? 'bi-check-circle-fill text-success'
    : type === 'warning'
    ? 'bi-exclamation-triangle-fill text-warning'
    : 'bi-shield-check text-primary';

  const toastEl = document.createElement('div');
  toastEl.className = 'cyber-toast shadow-lg';
  toastEl.id = toastId;
  toastEl.innerHTML = `
    <div class="cyber-toast-header">
      <i class="bi ${iconClass} me-2 fs-6"></i>
      <strong class="me-auto font-monospace">${title}</strong>
      <button type="button" class="btn-close-toast" onclick="this.closest('.cyber-toast').remove()">&times;</button>
    </div>
    <div class="cyber-toast-body">
      ${message}
    </div>
    <div class="cyber-toast-progress">
      <div class="cyber-toast-progress-bar"></div>
    </div>
  `;

  container.appendChild(toastEl);

  setTimeout(() => {
    toastEl.classList.add('hiding');
    setTimeout(() => toastEl.remove(), 300);
  }, 4000);
}

function copyToClipboard(text, customMessage = 'Copied to clipboard!') {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      showCyberToast(`<strong>${text}</strong><br><small class="text-muted">${customMessage}</small>`, 'success', 'Quantum Clipboard');
    }).catch(() => fallbackCopy(text));
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand('copy');
    showCyberToast(`<strong>${text}</strong> copied!`, 'success', 'Quantum Clipboard');
  } catch (_) {}
  document.body.removeChild(ta);
}

// ── Command HUD (Ctrl + K) ──────────────────────────────────────────────────
const CommandHUD = {
  backdrop: null,
  input: null,
  list: null,
  selectedIndex: 0,
  commands: [
    { title: 'Executive Dashboard', subtitle: 'View banking metrics & volume', icon: 'bi-speedometer2', url: '/dashboard', cat: 'Navigation' },
    { title: 'My Banking Portal', subtitle: 'Personal holographic cards & balances', icon: 'bi-wallet2', url: '/my-banking', cat: 'Navigation' },
    { title: 'Customer Directory', subtitle: 'Search, register & inspect customers', icon: 'bi-people-fill', url: '/customers', cat: 'Management' },
    { title: 'Bank Accounts', subtitle: 'Account management, limits & freeze', icon: 'bi-credit-card-2-front-fill', url: '/accounts', cat: 'Management' },
    { title: 'Transaction Ledger', subtitle: 'Record deposits, withdrawals & transfers', icon: 'bi-arrow-left-right', url: '/transactions', cat: 'Operations' },
    { title: 'Credit & Loans', subtitle: 'Loan underwriting, rates & approvals', icon: 'bi-cash-coin', url: '/loans', cat: 'Operations' },
    { title: 'Morocco Branches', subtitle: 'Casablanca, Rabat, Tangier network', icon: 'bi-building-fill', url: '/branches', cat: 'Organization' },
    { title: 'Financial Reports', subtitle: 'Audited balance sheets & P&L statements', icon: 'bi-bar-chart-line-fill', url: '/reports', cat: 'Analytics' },
    { title: 'Database SQL Console', subtitle: 'Live tables, views, triggers & schema', icon: 'bi-database-fill', url: '/database', cat: 'System' },
    { title: 'Account Settings', subtitle: 'Profile, avatar & credentials', icon: 'bi-person-circle', url: '/account/settings', cat: 'Security' },
    { title: 'Toggle Cyber Dark / Light Theme', subtitle: 'Switch color spectrum mode', icon: 'bi-moon-stars-fill', action: 'toggleTheme', cat: 'System' },
    { title: 'Sign Out Session', subtitle: 'Secure quantum sign out', icon: 'bi-box-arrow-right', url: '/logout', cat: 'Security' }
  ],

  init() {
    this.backdrop = document.getElementById('commandHudBackdrop');
    this.input = document.getElementById('commandHudInput');
    this.list = document.getElementById('commandHudList');

    if (!this.backdrop || !this.input || !this.list) return;

    // Trigger button
    const openBtn = document.getElementById('openCommandPaletteBtn');
    if (openBtn) {
      openBtn.addEventListener('click', () => this.open());
    }

    // Global shortcut Ctrl+K / Cmd+K
    window.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        this.toggle();
      } else if (e.key === 'Escape' && this.isOpen()) {
        this.close();
      }
    });

    // Close on backdrop click
    this.backdrop.addEventListener('click', e => {
      if (e.target === this.backdrop) this.close();
    });

    // Input search
    this.input.addEventListener('input', () => {
      this.selectedIndex = 0;
      this.render();
    });

    // Keyboard navigation in HUD
    this.input.addEventListener('keydown', e => {
      const items = this.getFiltered();
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        SoundFX.click();
        this.selectedIndex = (this.selectedIndex + 1) % (items.length || 1);
        this.render();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        SoundFX.click();
        this.selectedIndex = (this.selectedIndex - 1 + (items.length || 1)) % (items.length || 1);
        this.render();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (items[this.selectedIndex]) {
          this.execute(items[this.selectedIndex]);
        }
      }
    });
  },

  isOpen() {
    return this.backdrop && this.backdrop.style.display !== 'none';
  },

  open() {
    SoundFX.hud();
    this.backdrop.style.display = 'flex';
    this.input.value = '';
    this.selectedIndex = 0;
    this.render();
    setTimeout(() => this.input.focus(), 50);
  },

  close() {
    SoundFX.click();
    this.backdrop.style.display = 'none';
  },

  toggle() {
    if (this.isOpen()) this.close();
    else this.open();
  },

  getFiltered() {
    const q = (this.input.value || '').trim().toLowerCase();
    if (!q) return this.commands;
    return this.commands.filter(cmd =>
      cmd.title.toLowerCase().includes(q) ||
      cmd.subtitle.toLowerCase().includes(q) ||
      cmd.cat.toLowerCase().includes(q)
    );
  },

  render() {
    const items = this.getFiltered();
    if (items.length === 0) {
      this.list.innerHTML = `
        <div class="hud-empty-state text-center py-4 text-muted">
          <i class="bi bi-search fs-3 mb-2 d-block opacity-50"></i>
          <span>No matching system commands found</span>
        </div>
      `;
      return;
    }

    let html = '';
    items.forEach((item, idx) => {
      const isSelected = idx === this.selectedIndex;
      html += `
        <div class="hud-item ${isSelected ? 'active' : ''}" data-index="${idx}">
          <div class="hud-item-icon"><i class="bi ${item.icon}"></i></div>
          <div class="hud-item-content">
            <div class="hud-item-title">${item.title}</div>
            <div class="hud-item-sub">${item.subtitle}</div>
          </div>
          <span class="hud-item-cat">${item.cat}</span>
        </div>
      `;
    });

    this.list.innerHTML = html;

    // Click handler on list items
    this.list.querySelectorAll('.hud-item').forEach(el => {
      el.addEventListener('click', () => {
        const idx = parseInt(el.getAttribute('data-index'), 10);
        if (items[idx]) this.execute(items[idx]);
      });
    });

    // Ensure selected item is scrolled into view
    const activeEl = this.list.querySelector('.hud-item.active');
    if (activeEl) {
      activeEl.scrollIntoView({ block: 'nearest' });
    }
  },

  execute(item) {
    SoundFX.success();
    this.close();
    if (item.action === 'toggleTheme') {
      const active = document.documentElement.getAttribute('data-theme') || 'dark';
      ThemeManager.applyTheme(active === 'dark' ? 'light' : 'dark');
      showCyberToast(`Theme switched to <strong>${active === 'dark' ? 'Crisp Light' : 'Cyber Dark'}</strong> mode.`, 'info');
    } else if (item.url) {
      window.location.href = item.url;
    }
  }
};

// ── Sidebar Toggle & Responsive Handling ────────────────────────────────────
function initSidebar() {
  const toggle  = document.getElementById('sidebarToggle');
  const sidebar = document.getElementById('sidebar');
  const wrapper = document.getElementById('mainWrapper');

  if (toggle && sidebar) {
    toggle.addEventListener('click', () => {
      SoundFX.click();
      if (window.innerWidth <= 991) {
        sidebar.classList.toggle('open');
      } else {
        const collapsed = sidebar.classList.toggle('collapsed');
        sidebar.style.transform = collapsed ? 'translateX(-100%)' : '';
        if (wrapper) wrapper.style.marginLeft = collapsed ? '0' : '';
      }
    });
  }

  // Close sidebar on outside click (mobile)
  document.addEventListener('click', e => {
    if (window.innerWidth <= 991 && sidebar && sidebar.classList.contains('open')) {
      if (!sidebar.contains(e.target) && e.target !== toggle) {
        sidebar.classList.remove('open');
      }
    }
  });
}

// ── Numeric Counters Animation ──────────────────────────────────────────────
function animateCounters() {
  document.querySelectorAll('.kpi-value').forEach(el => {
    const text   = el.textContent.trim();
    const hasMad = text.startsWith('MAD ');
    const raw    = text.replace(/^MAD\s*/, '').replace(/[^\d.-]/g, '');
    const target = parseFloat(raw);

    if (isNaN(target)) return;

    let start = 0;
    const duration = 850;
    const step     = 16;
    const inc      = target / (duration / step);

    const timer = setInterval(() => {
      start += inc;
      if (start >= target) { start = target; clearInterval(timer); }
      const formatted = start >= 1000
        ? (hasMad ? 'MAD ' : '') + Math.round(start).toLocaleString('fr-MA')
        : (hasMad ? 'MAD ' : '') + (Number.isInteger(target) ? Math.round(start).toString() : start.toFixed(2));
      el.textContent = formatted;
    }, step);
  });
}

// ── Card Subscription Selector & Live Preview ──────────────────────────────
window.selectCardTier = function(tierId, tierName, tierBadge, tierCategory, monthlyFee, plafond, accentColor, perks) {
  if (window.SoundFX) SoundFX.click();
  
  // Resolve tier metadata from window.CARD_TIERS_DATA if not provided
  const tierData = (window.CARD_TIERS_DATA && window.CARD_TIERS_DATA[tierId]) || {};
  tierName   = tierName || tierData.name || '';
  tierBadge  = tierBadge || tierData.badge || '';
  monthlyFee = monthlyFee || tierData.monthly_fee || '';
  plafond    = plafond || tierData.plafond || tierData.atm_limit || '';
  perks      = perks || tierData.perks || [];

  const input = document.getElementById('selectedCardTierInput');
  if (input) input.value = tierId;

  document.querySelectorAll('.card-template-item').forEach(item => {
    item.classList.toggle('is-selected', item.getAttribute('data-tier-id') === tierId);
  });

  const previewCard = document.getElementById('modalPreviewCard');
  if (previewCard) {
    previewCard.className = previewCard.className.replace(/cyber-card-tier-[^\s]+/g, '');
    previewCard.classList.add(`cyber-card-tier-${tierId}`);
  }

  const badgeEl = document.getElementById('modalPreviewBadge');
  if (badgeEl && tierBadge) badgeEl.textContent = tierBadge;

  const titleEl = document.getElementById('modalPreviewTitle');
  if (titleEl && tierName) titleEl.textContent = tierName;

  const feeEl = document.getElementById('modalPreviewFee');
  if (feeEl && monthlyFee) feeEl.textContent = monthlyFee;

  const limitEl = document.getElementById('modalPreviewLimit');
  if (limitEl && plafond) limitEl.textContent = plafond;

  const perksListEl = document.getElementById('modalPreviewPerks');
  if (perksListEl && Array.isArray(perks) && perks.length > 0) {
    perksListEl.innerHTML = perks.map(p => `<li><i class="bi bi-check2-circle text-success me-2"></i><span>${p}</span></li>`).join('');
  }
};

window.filterCardTemplates = function(category, btn) {
  if (window.SoundFX) SoundFX.click();
  document.querySelectorAll('.card-filter-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');

  document.querySelectorAll('.card-template-item').forEach(item => {
    const itemCat = item.getAttribute('data-category');
    if (category === 'all' || itemCat === category) {
      item.style.display = 'flex';
    } else {
      item.style.display = 'none';
    }
  });
};

window.updatePreviewCardholder = function(selectEl) {
  const cardholderEl = document.getElementById('modalPreviewCardholder');
  if (cardholderEl && selectEl) {
    const text = selectEl.options[selectEl.selectedIndex]?.text || '';
    cardholderEl.textContent = (text && !text.includes('Select')) ? text.toUpperCase() : 'NOUVEAU CLIENT';
  }
};

function initCardTemplateClicks() {
  document.querySelectorAll('.card-template-item').forEach(item => {
    item.addEventListener('click', (e) => {
      const tierId = item.getAttribute('data-tier-id');
      if (tierId) {
        window.selectCardTier(tierId);
      }
    });
  });
}

// ── DOM Ready Initializer ───────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  ThemeManager.init();
  initSidebar();
  initCasablancaClock();
  initHolographicCards();
  initCardTemplateClicks();
  CommandHUD.init();
  animateCounters();

  // Attach sound feedback to primary action buttons
  document.querySelectorAll('.btn-primary, .btn-success, .btn-danger, .btn-topbar-action, .topbar-btn-hud').forEach(btn => {
    btn.addEventListener('click', () => SoundFX.click());
  });

  // Auto-dismiss Bootstrap alert banners smoothly after 5s
  document.querySelectorAll('.alert').forEach(alert => {
    setTimeout(() => {
      if (window.bootstrap && bootstrap.Alert) {
        const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
        if (bsAlert) bsAlert.close();
      }
    }, 5500);
  });
});
