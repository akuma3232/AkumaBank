/**
 * main.js – AkumaBank client-side utilities
 */

// ── Sidebar toggle ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const toggle  = document.getElementById('sidebarToggle');
  const sidebar = document.getElementById('sidebar');
  const wrapper = document.getElementById('mainWrapper');

  if (toggle && sidebar) {
    toggle.addEventListener('click', () => {
      if (window.innerWidth <= 991) {
        sidebar.classList.toggle('open');
      } else {
        const collapsed = sidebar.classList.toggle('collapsed');
        sidebar.style.transform = collapsed ? 'translateX(-100%)' : '';
        wrapper.style.marginLeft = collapsed ? '0' : '';
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

  // Auto-dismiss alerts after 5 s
  document.querySelectorAll('.alert').forEach(alert => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      if (bsAlert) bsAlert.close();
    }, 5000);
  });

  // Animate KPI values on load
  animateCounters();

  // Add loading overlay to form submissions
  attachFormLoadingOverlay();
});


// ── Confirm delete helper (used in templates) ───────────────────────────────
function confirmDelete(actionUrl, itemName) {
  const modal = document.getElementById('deleteModal');
  if (modal) {
    document.getElementById('deleteItemName').textContent = itemName;
    document.getElementById('deleteForm').action = actionUrl;
    new bootstrap.Modal(modal).show();
  } else {
    if (confirm(`Delete "${itemName}"? This cannot be undone.`)) {
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = actionUrl;
      document.body.appendChild(form);
      form.submit();
    }
  }
}


// ── Animate numeric counters ────────────────────────────────────────────────
function animateCounters() {
  document.querySelectorAll('.kpi-value').forEach(el => {
    const text   = el.textContent.trim();
    const hasMad = text.startsWith('MAD ');
    const raw    = text.replace(/^MAD\s*/, '').replace(/[^\d.-]/g, '');
    const target = parseFloat(raw);

    if (isNaN(target)) return;

    let start = 0;
    const duration = 900;
    const step     = 16;
    const inc      = target / (duration / step);

    const timer = setInterval(() => {
      start += inc;
      if (start >= target) { start = target; clearInterval(timer); }
      const formatted = start >= 1000
        ? (hasMad ? 'MAD ' : '') + Math.round(start).toLocaleString('fr-MA')
        : (hasMad ? 'MAD ' : '') + Math.round(start).toString();
      el.textContent = formatted;
    }, step);
  });
}


// ── Show loading overlay on form submit ─────────────────────────────────────
function attachFormLoadingOverlay() {
  const forms = document.querySelectorAll('form[method="POST"]');
  forms.forEach(form => {
    form.addEventListener('submit', () => {
      // Only show for non-delete forms
      if (form.id === 'deleteForm') return;
      const overlay = document.createElement('div');
      overlay.className = 'page-loading';
      overlay.innerHTML = '<div class="loading-spinner"></div><div style="color:#1e40af;font-weight:600">Processing…</div>';
      document.body.appendChild(overlay);
    });
  });
}


// ── Table search (client-side) ───────────────────────────────────────────────
function filterTable(inputId, tableId) {
  const input = document.getElementById(inputId);
  const table = document.getElementById(tableId);
  if (!input || !table) return;

  input.addEventListener('input', () => {
    const query = input.value.toLowerCase();
    table.querySelectorAll('tbody tr').forEach(row => {
      row.style.display = row.textContent.toLowerCase().includes(query) ? '' : 'none';
    });
  });
}
