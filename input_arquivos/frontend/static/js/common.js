// Utilitários compartilhados por todas as páginas: fetch autenticado, toasts, modal de confirmação e Auto-Lock.
// Visual único: o design system Blau (body.theme-blau-claro, fixo no base.html) — sem troca de tema.

const AUTOLOCK_KEY = 'app-autolock-minutes';

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
    if (window.location.pathname !== '/login') logout('inatividade');
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
    window.location.href = "/login?motivo=expirou";
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

// Toast do app_template: empilha no canto, faixa colorida por tipo, some sozinho.
const TOAST_CLASSE = {
  success: "", positive: "",
  error: "toast--erro", negative: "toast--erro",
  warn: "toast--aviso", warning: "toast--aviso",
  info: "toast--info",
};

function showToast(message, variant = "info") {
  const root = document.getElementById("toasts") || document.body;
  const toast = document.createElement("div");
  toast.className = `toast ${TOAST_CLASSE[variant] ?? "toast--info"}`.trim();
  toast.setAttribute("role", "status");
  toast.textContent = message;
  root.appendChild(toast);
  setTimeout(() => toast.remove(), 4500);
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

// Sair (botão ou bloqueio por inatividade): a tela de login mostra o motivo no card.
async function logout(motivo = "saiu") {
  try {
    await apiFetch("/api/auth/logout", { method: "POST" });
  } catch (e) {
    // Ignora erro se sessão já foi invalidada
  }
  window.location.href = `/login?motivo=${encodeURIComponent(motivo)}`;
}

// ── Lateral (= app_template): recolher, filtrar e arrastar a largura ─────────
const LATERAL_KEY = "ia-lateral";
const LARGURA_KEY = "ia-sidebar-width";
const LARGURA = { padrao: 240, min: 160, max: 550 };

function aplicarLargura(px) {
  const v = Math.min(LARGURA.max, Math.max(LARGURA.min, Math.round(px)));
  document.documentElement.style.setProperty("--sidebar-w", `${v}px`);
  return v;
}

function toggleSidebar(forceState) {
  const panel = document.getElementById("sidebar-panel");
  const handle = document.getElementById("sidebar-resize-handle");
  if (!panel) return;
  const aberta = typeof forceState === "boolean" ? forceState : panel.classList.contains("collapsed");
  panel.classList.toggle("collapsed", !aberta);
  if (handle) handle.classList.toggle("collapsed", !aberta);
  try { localStorage.setItem(LATERAL_KEY, aberta ? "1" : "0"); } catch { /* sem storage: só nesta página */ }
}

function filterSidebarItems(query) {
  const q = (query || "").toLowerCase();
  document.querySelectorAll(".sidebar-tree .tree-item").forEach((item) => {
    item.style.display = item.textContent.toLowerCase().includes(q) ? "" : "none";
  });
}

function initSidebar() {
  const panel = document.getElementById("sidebar-panel");
  const handle = document.getElementById("sidebar-resize-handle");
  if (!panel || !handle) return;
  try {
    aplicarLargura(Number(localStorage.getItem(LARGURA_KEY)) || LARGURA.padrao);
    if (localStorage.getItem(LATERAL_KEY) === "0") {
      panel.classList.add("resizing");  // sem animação ao abrir a página já recolhida
      toggleSidebar(false);
      requestAnimationFrame(() => panel.classList.remove("resizing"));
    }
  } catch { /* sem storage */ }
  let arrastando = false;
  const mover = (x) => {
    if (!arrastando) return;
    const v = aplicarLargura(x - panel.getBoundingClientRect().left);
    try { localStorage.setItem(LARGURA_KEY, String(v)); } catch { /* sem storage */ }
  };
  const fim = () => {
    if (!arrastando) return;
    arrastando = false;
    panel.classList.remove("resizing"); handle.classList.remove("dragging");
    document.body.style.cursor = ""; document.body.style.userSelect = "";
  };
  const inicio = (e) => {
    if (panel.classList.contains("collapsed")) return;
    arrastando = true;
    panel.classList.add("resizing"); handle.classList.add("dragging");
    document.body.style.cursor = "col-resize"; document.body.style.userSelect = "none";
    e.preventDefault();
  };
  handle.addEventListener("mousedown", inicio);
  handle.addEventListener("touchstart", inicio, { passive: false });
  document.addEventListener("mousemove", (e) => mover(e.clientX));
  document.addEventListener("touchmove", (e) => { if (arrastando) { mover(e.touches[0].clientX); e.preventDefault(); } }, { passive: false });
  document.addEventListener("mouseup", fim);
  document.addEventListener("touchend", fim);
  handle.addEventListener("dblclick", () => {
    try { localStorage.setItem(LARGURA_KEY, String(aplicarLargura(LARGURA.padrao))); } catch { /* sem storage */ }
  });
}

// SHOW/HIDE em todo campo de senha que ainda não tem o botão (= app_template).
function ligarMostrarSenha() {
  document.querySelectorAll('input[type="password"]').forEach((input) => {
    if (input.parentElement.querySelector(".pw-toggle")) return;
    let caixa = input.parentElement;
    if (!caixa.classList.contains("pw-wrap")) {
      caixa = document.createElement("div");
      caixa.className = "pw-wrap";
      input.replaceWith(caixa);
      caixa.append(input);
    }
    const botao = document.createElement("button");
    botao.type = "button";
    botao.className = "pw-toggle";
    botao.title = "Mostrar/ocultar";
    botao.textContent = "SHOW";
    botao.addEventListener("click", () => {
      const mostrar = input.type === "password";
      input.type = mostrar ? "text" : "password";
      botao.textContent = mostrar ? "HIDE" : "SHOW";
    });
    caixa.append(botao);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  applyPrefsOnBoot();
  initAutoLockListener();
  initSidebar();
  ligarMostrarSenha();

  const logoutButton = document.getElementById("logout-button");
  if (logoutButton) {
    logoutButton.addEventListener("click", () => logout());
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
