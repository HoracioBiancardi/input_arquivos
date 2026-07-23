// Utilitários compartilhados por todas as páginas: fetch autenticado, toasts, modal de confirmação e dark mode.

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
    // Formato padrão de 422 do Pydantic/FastAPI: [{loc: [...], msg: "..."}, ...]
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

function showToast(message, variant = "positive") {
  const root = document.getElementById("toast-root");
  if (!root) return;
  const toast = document.createElement("div");
  toast.className = `toast toast--${variant}`;
  toast.textContent = message;
  root.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity .2s ease";
    setTimeout(() => toast.remove(), 200);
  }, 4000);
}

function confirmModal({ title, body, confirmLabel = "Confirmar", cancelLabel = "Cancelar", variant = "primary" }) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4";

    const confirmClasses =
      variant === "warning"
        ? "bg-amber-600 hover:bg-amber-700"
        : "bg-primary hover:opacity-90";

    overlay.innerHTML = `
      <div class="w-full max-w-md rounded-2xl bg-white dark:bg-slate-800 p-6 shadow-lg">
        <h3 class="text-lg font-semibold mb-2 text-slate-900 dark:text-slate-100">${title}</h3>
        <div class="text-sm text-muted mb-4">${body}</div>
        <div class="flex justify-end gap-2">
          <button type="button" data-action="cancel" class="px-4 py-1.5 rounded-lg text-sm font-medium border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700">${cancelLabel}</button>
          <button type="button" data-action="confirm" class="px-4 py-1.5 rounded-lg text-sm font-medium text-white ${confirmClasses}">${confirmLabel}</button>
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

function initDarkMode() {
  const isDark = localStorage.getItem("dark_mode") === "true";
  document.documentElement.classList.toggle("dark", isDark);
  const toggle = document.getElementById("dark-mode-toggle");
  if (!toggle) return;
  updateDarkModeIcon(toggle, isDark);
  toggle.addEventListener("click", () => {
    const nowDark = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", nowDark);
    localStorage.setItem("dark_mode", String(nowDark));
    updateDarkModeIcon(toggle, nowDark);
  });
}

function updateDarkModeIcon(toggle, isDark) {
  toggle.textContent = isDark ? "☀️" : "🌙";
}

async function logout() {
  await apiFetch("/api/auth/logout", { method: "POST" });
  window.location.href = "/login";
}

document.addEventListener("DOMContentLoaded", () => {
  initDarkMode();
  const logoutButton = document.getElementById("logout-button");
  if (logoutButton) {
    logoutButton.addEventListener("click", logout);
  }
});
