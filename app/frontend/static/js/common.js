// Utilitários compartilhados por todas as páginas: fetch autenticado, toasts, modal de confirmação, temas SwordPower e Auto-Lock.

const THEME_KEY = 'app-theme';
const AUTOLOCK_KEY = 'app-autolock-minutes';
const VALID_THEMES = new Set(['corporate', 'green-neutral']);

function getTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  return VALID_THEMES.has(saved) ? saved : 'corporate';
}

function setTheme(theme) {
  const valid = VALID_THEMES.has(theme) ? theme : 'corporate';
  localStorage.setItem(THEME_KEY, valid);
  VALID_THEMES.forEach((t) => document.body.classList.remove('theme-' + t));
  document.body.classList.add('theme-' + valid);
  const el = document.getElementById('settings-theme');
  if (el) el.value = valid;
}

function getAutoLockMinutes() {
  const saved = localStorage.getItem(AUTOLOCK_KEY);
  return saved === null ? 5 : Number(saved);
}

function setAutoLockMinutes(minutes) {
  localStorage.setItem(AUTOLOCK_KEY, String(minutes));
  const el = document.getElementById('settings-autolock');
  if (el) el.value = String(minutes);
  resetAutoLockTimer();
}

function applyPrefsOnBoot() {
  setTheme(getTheme());
  setAutoLockMinutes(getAutoLockMinutes());
}

function openSettingsModal() {
  const overlay = document.getElementById('settings-overlay');
  if (overlay) overlay.classList.add('open');
}

function closeSettingsModal() {
  const overlay = document.getElementById('settings-overlay');
  if (overlay) overlay.classList.remove('open');
}

function changeTheme(theme) {
  setTheme(theme);
}

function changeAutoLock(minutes) {
  setAutoLockMinutes(Number(minutes));
}

// ── Auto-Lock por Inatividade ──────────────────────────────────────────
let _autolockTimer = null;

function resetAutoLockTimer() {
  if (_autolockTimer) clearTimeout(_autolockTimer);
  const minutes = getAutoLockMinutes();
  if (minutes <= 0) return; // Desativado

  _autolockTimer = setTimeout(() => {
    // Redireciona/desloga por inatividade se houver sessão ativa
    if (window.location.pathname !== '/login') {
      showToast('Sessão bloqueada por inatividade.', 'warning');
      setTimeout(() => logout(), 1000);
    }
  }, minutes * 60 * 1000);
}

function initAutoLockListener() {
  ['mousemove', 'keydown', 'click', 'touchstart', 'scroll'].forEach((evt) => {
    window.addEventListener(evt, resetAutoLockTimer, { passive: true });
  });
  resetAutoLockTimer();
}

// ── Sanitização XSS ───────────────────────────────────────────────────
function esc(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ── Fetch Autenticado ──────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const init = { credentials: "same-origin", ...options, headers: { ...(options.headers || {}) } };
  if (init.body && !(init.body instanceof FormData) && typeof init.body !== "string") {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(init.body);
  }
  const response = await fetch(path, init);
  if (response.status === 401 && path !== "/api/auth/login") {
    window.location.href = "/login";
    throw new Error("Sessão expirada.");
  }
  if (response.status === 204) {
    return null;
  }
  const isJson = (response.headers.get("content-type") || "").includes("application/json");
  const data = isJson ? await response.json() : null;
  if (!response.ok) {
    const detail = (data && (data.detail || data.message)) || `Erro ${response.status}`;
    const error = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

function extractFieldErrors(errorData) {
  const detail = errorData && errorData.detail;
  if (Array.isArray(detail)) {
    return detail
      .filter((item) => item && item.loc)
      .map((item) => ({ field: item.loc[item.loc.length - 1], message: item.msg }));
  }
  if (detail && typeof detail === "object" && detail.field) {
    return [{ field: detail.field, message: detail.message }];
  }
  return [];
}

function clearFieldErrors(prefix) {
  document.querySelectorAll(`[data-field-error-for^="${prefix}-"]`).forEach((el) => el.remove());
}

function applyFieldErrors(prefix, errors) {
  clearFieldErrors(prefix);
  let applied = 0;
  errors.forEach(({ field, message }) => {
    const input = document.getElementById(`${prefix}-${field}`);
    if (!input) return;
    const errorEl = document.createElement("p");
    errorEl.className = "field-error text-negative text-xs mt-1";
    errorEl.dataset.fieldErrorFor = `${prefix}-${field}`;
    errorEl.textContent = message;
    input.insertAdjacentElement("afterend", errorEl);
    applied += 1;
  });
  return applied;
}

function showToast(message, variant = "info") {
  const root = document.getElementById("toast-root") || document.body;
  const toast = document.createElement("div");
  
  // Mapeamento de variantes para compatibilidade
  let typeClass = variant;
  if (variant === "positive") typeClass = "success";
  if (variant === "negative") typeClass = "error";
  if (variant === "warning") typeClass = "warn";

  toast.className = `toast ${typeClass}`;
  toast.textContent = message;
  root.appendChild(toast);
  
  requestAnimationFrame(() => toast.classList.add("visible"));

  setTimeout(() => {
    toast.classList.remove("visible");
    setTimeout(() => toast.remove(), 250);
  }, 4000);
}

function confirmModal({ title, body, confirmLabel = "Confirmar", cancelLabel = "Cancelar", variant = "primary" }) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "overlay open";

    overlay.innerHTML = `
      <div class="modal glass" style="max-width: 440px">
        <div class="modal-header">
          <h2>${esc(title)}</h2>
          <button class="close-btn" data-action="cancel">X</button>
        </div>
        <div class="modal-body mb-4">${body}</div>
        <div class="modal-footer">
          <button type="button" data-action="cancel" class="btn btn-ghost">${esc(cancelLabel)}</button>
          <button type="button" data-action="confirm" class="btn btn-primary">${esc(confirmLabel)}</button>
        </div>
      </div>
    `;

    function close(result) {
      overlay.remove();
      resolve(result);
    }

    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) close(false);
    });
    overlay.querySelector('[data-action="cancel"]').addEventListener("click", () => close(false));
    overlay.querySelector('[data-action="confirm"]').addEventListener("click", () => close(true));

    document.body.appendChild(overlay);
  });
}

async function logout() {
  try {
    await apiFetch("/api/auth/logout", { method: "POST" });
  } catch (e) {
    // Ignora erro se sessão já foi invalidada
  }
  window.location.href = "/login";
}

document.addEventListener("DOMContentLoaded", () => {
  applyPrefsOnBoot();
  initAutoLockListener();

  const logoutButton = document.getElementById("logout-button");
  if (logoutButton) {
    logoutButton.addEventListener("click", logout);
  }
});
