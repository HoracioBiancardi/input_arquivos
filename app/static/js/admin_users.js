const createModal = document.getElementById("create-user-modal");
const manageModal = document.getElementById("manage-user-modal");
const manageRoleSelect = document.getElementById("manage-role");

function statusBadge(active) {
  return active
    ? '<span class="status-badge status-badge--success">Sim</span>'
    : '<span class="status-badge status-badge--muted">Não</span>';
}

async function loadUsers() {
  const users = await apiFetch("/api/users");
  const rows = document.getElementById("user-rows");
  rows.innerHTML = users
    .map(
      (user) => `
      <tr class="border-b border-black/5 dark:border-white/10 last:border-0 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800" data-id="${user.id}">
        <td class="px-4 py-2 font-medium">${user.username}</td>
        <td class="px-4 py-2">${user.role}</td>
        <td class="px-4 py-2 text-center">${statusBadge(user.active)}</td>
      </tr>`
    )
    .join("");
  rows.querySelectorAll("tr[data-id]").forEach((row) => {
    row.addEventListener("click", () => openManageModal(Number(row.dataset.id)));
  });
}

function openCreateModal() {
  document.getElementById("create-user-form").reset();
  clearFieldErrors("create");
  createModal.classList.remove("hidden");
  createModal.classList.add("flex");
}

function closeCreateModal() {
  createModal.classList.add("hidden");
  createModal.classList.remove("flex");
}

async function saveNewUser(event) {
  event.preventDefault();
  clearFieldErrors("create");
  const username = document.getElementById("create-username").value;
  const password = document.getElementById("create-password").value;
  if (!username || !password) {
    showToast("Usuário e senha são obrigatórios.", "warning");
    return;
  }
  const role = document.getElementById("create-role").value;
  try {
    await apiFetch("/api/users", { method: "POST", body: { username, password, role } });
    closeCreateModal();
    await loadUsers();
    showToast("Usuário criado com sucesso.", "positive");
  } catch (error) {
    const fieldErrors = extractFieldErrors(error.data);
    if (applyFieldErrors("create", fieldErrors) === 0) {
      showToast(`Falha ao criar usuário: ${error.message}`, "negative");
    }
  }
}

function toggleManageContextsField() {
  document.getElementById("manage-contexts-field").classList.toggle("hidden", manageRoleSelect.value !== "user");
}

async function openManageModal(userId) {
  const [user, activeContexts] = await Promise.all([
    apiFetch(`/api/users/${userId}`),
    apiFetch("/api/contexts?active_only=true"),
  ]);

  document.getElementById("manage-user-title").textContent = `Gerenciar ${user.username}`;
  document.getElementById("manage-user-id").value = user.id;
  manageRoleSelect.value = user.role;
  document.getElementById("manage-active").checked = user.active;
  document.getElementById("manage-new_password").value = "";
  clearFieldErrors("manage");

  const assignedIds = new Set(user.context_ids);
  const checkboxesContainer = document.getElementById("manage-contexts-checkboxes");
  checkboxesContainer.innerHTML = activeContexts
    .map(
      (context) => `
      <label class="flex items-center gap-2">
        <input type="checkbox" class="manage-context-checkbox" value="${context.id}" ${assignedIds.has(context.id) ? "checked" : ""}>
        ${context.name}
      </label>`
    )
    .join("");

  toggleManageContextsField();
  manageModal.classList.remove("hidden");
  manageModal.classList.add("flex");
}

function closeManageModal() {
  manageModal.classList.add("hidden");
  manageModal.classList.remove("flex");
}

async function saveManagedUser(event) {
  event.preventDefault();
  clearFieldErrors("manage");
  const userId = document.getElementById("manage-user-id").value;
  const newPassword = document.getElementById("manage-new_password").value;
  const contextIds = Array.from(document.querySelectorAll(".manage-context-checkbox:checked")).map((cb) => Number(cb.value));

  try {
    await Promise.all([
      apiFetch(`/api/users/${userId}`, {
        method: "PATCH",
        body: {
          role: manageRoleSelect.value,
          active: document.getElementById("manage-active").checked,
          new_password: newPassword || null,
        },
      }),
      apiFetch(`/api/users/${userId}/contexts`, { method: "PUT", body: { context_ids: contextIds } }),
    ]);
    closeManageModal();
    await loadUsers();
    showToast("Usuário atualizado com sucesso.", "positive");
  } catch (error) {
    const fieldErrors = extractFieldErrors(error.data);
    if (applyFieldErrors("manage", fieldErrors) === 0) {
      showToast(`Falha ao salvar: ${error.message}`, "negative");
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadUsers();
  document.getElementById("new-user-button").addEventListener("click", openCreateModal);
  document.getElementById("create-user-cancel").addEventListener("click", closeCreateModal);
  document.getElementById("create-user-form").addEventListener("submit", saveNewUser);

  document.getElementById("manage-user-cancel").addEventListener("click", closeManageModal);
  document.getElementById("manage-user-form").addEventListener("submit", saveManagedUser);
  manageRoleSelect.addEventListener("change", toggleManageContextsField);
});
