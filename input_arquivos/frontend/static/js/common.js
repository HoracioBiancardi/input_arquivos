// Utilitários compartilhados por todas as páginas: fetch autenticado, toasts, modal de confirmação, temas SwordPower e Auto-Lock.

const THEME_KEY = 'app-theme';
const AUTOLOCK_KEY = 'app-autolock-minutes';
const VALID_THEMES = new Set(['corporate', 'green-neutral', 'cyber-dark']);

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

// ── Datas ─────────────────────────────────────────────────────────────
// A API devolve horários em UTC com fuso explícito (+00:00); a exibição é sempre no
// horário de Brasília, independente do fuso configurado na máquina de quem acessa.
const BR_DATETIME_FORMAT = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function formatDateTimeBR(isoString) {
  if (!isoString) return "–";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "–";
  return BR_DATETIME_FORMAT.format(date).replace(",", "");
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
  // Login e troca de senha devolvem 401 para credencial errada — mostrar o erro, não redirecionar.
  const credentialPaths = ["/api/auth/login", "/api/auth/change-password"];
  if (response.status === 401 && !credentialPaths.includes(path)) {
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

    overlay.querySelectorAll('[data-action="cancel"]').forEach((button) => button.addEventListener("click", () => close(false)));
    overlay.querySelector('[data-action="confirm"]').addEventListener("click", () => close(true));

    document.body.appendChild(overlay);
  });
}

function alertModal({ title, body, closeLabel = "Fechar", maxWidth = "560px" }) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "overlay open";

    overlay.innerHTML = `
      <div class="modal glass" style="max-width: ${maxWidth}; max-height: 90vh; overflow-y: auto">
        <div class="modal-header">
          <h2>${esc(title)}</h2>
          <button class="close-btn" data-action="close">X</button>
        </div>
        <div class="modal-body mb-4">${body}</div>
        <div class="modal-footer">
          <button type="button" data-action="close" class="btn btn-primary">${esc(closeLabel)}</button>
        </div>
      </div>
    `;

    function close() {
      overlay.remove();
      document.removeEventListener("keydown", onKeydown);
      resolve();
    }

    function onKeydown(event) {
      if (event.key === "Escape") close();
    }

    overlay.querySelectorAll('[data-action="close"]').forEach((button) => button.addEventListener("click", close));
    document.addEventListener("keydown", onKeydown);

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

// ── Senhas: mostrar/ocultar, gerar e trocar a própria ────────────────
// Sem caracteres ambíguos (0/O, 1/l/I) para a senha poder ser ditada/digitada sem erro.
const PASSWORD_GROUPS = ["ABCDEFGHJKLMNPQRSTUVWXYZ", "abcdefghijkmnopqrstuvwxyz", "23456789", "!@#$%&*?"];

// Índice aleatório em [0, max) sem viés de módulo (descarta bytes acima do maior múltiplo de max).
// crypto.getRandomValues funciona também em HTTP, diferente de crypto.subtle/clipboard.
function randomIndex(max) {
  const limit = 256 - (256 % max);
  const buffer = new Uint8Array(1);
  do {
    crypto.getRandomValues(buffer);
  } while (buffer[0] >= limit);
  return buffer[0] % max;
}

// Senha com ao menos um caractere de cada grupo, embaralhada (Fisher-Yates).
function generatePassword(length = 16) {
  const all = PASSWORD_GROUPS.join("");
  const chars = PASSWORD_GROUPS.map((group) => group[randomIndex(group.length)]);
  while (chars.length < length) chars.push(all[randomIndex(all.length)]);
  for (let i = chars.length - 1; i > 0; i--) {
    const j = randomIndex(i + 1);
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  return chars.join("");
}

function togglePasswordVisibility(inputId, button) {
  const input = document.getElementById(inputId);
  const showing = input.type === "text";
  input.type = showing ? "password" : "text";
  button.textContent = showing ? "SHOW" : "HIDE";
}

// Preenche os campos com uma senha gerada e deixa visível, para quem gerou conseguir anotar/repassar.
function fillGeneratedPassword(inputIds) {
  const password = generatePassword();
  inputIds.forEach((id) => {
    const input = document.getElementById(id);
    input.value = password;
    input.type = "text";
    const toggle = input.parentElement.querySelector(".pw-toggle");
    if (toggle) toggle.textContent = "HIDE";
  });
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(password).then(
      () => showToast("Senha gerada e copiada.", "positive"),
      () => showToast("Senha gerada — anote antes de salvar.", "info")
    );
  } else {
    showToast("Senha gerada — anote antes de salvar.", "info");
  }
}

function openChangePasswordModal(username) {
  const form = document.getElementById("change-password-form");
  if (!form) return;
  form.reset();
  clearFieldErrors("cp");
  ["cp-current_password", "cp-new_password", "cp-new_password_confirm"].forEach((id) => {
    document.getElementById(id).type = "password";
  });
  form.querySelectorAll(".pw-toggle").forEach((button) => (button.textContent = "SHOW"));
  document.getElementById("cp-username").value = username || "";
  document.getElementById("change-password-overlay").classList.add("open");
  document.getElementById(username ? "cp-current_password" : "cp-username").focus();
}

function closeChangePasswordModal() {
  const overlay = document.getElementById("change-password-overlay");
  if (overlay) overlay.classList.remove("open");
}

async function submitChangePassword(event) {
  event.preventDefault();
  clearFieldErrors("cp");
  const username = document.getElementById("cp-username").value.trim();
  const newPassword = document.getElementById("cp-new_password").value;
  if (newPassword !== document.getElementById("cp-new_password_confirm").value) {
    applyFieldErrors("cp", [{ field: "new_password_confirm", message: "As senhas não conferem." }]);
    return;
  }
  try {
    await apiFetch("/api/auth/change-password", {
      method: "POST",
      body: {
        username,
        current_password: document.getElementById("cp-current_password").value,
        new_password: newPassword,
      },
    });
    closeChangePasswordModal();
    showToast("Senha trocada com sucesso.", "positive");
    const loginUsername = document.getElementById("username");
    if (loginUsername) {
      loginUsername.value = username;
      document.getElementById("password").focus();
    } else {
      setTimeout(() => window.location.reload(), 800);
    }
  } catch (error) {
    if (applyFieldErrors("cp", extractFieldErrors(error.data)) === 0) {
      showToast(error.message, "negative");
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("change-password-form");
  if (form) form.addEventListener("submit", submitChangePassword);
});
