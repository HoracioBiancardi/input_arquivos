function statusBadge(status) {
  const isSuccess = status === "success";
  return `<span class="status-badge ${isSuccess ? "status-badge--success" : "status-badge--error"}">${isSuccess ? "Sucesso" : "Erro"}</span>`;
}

const LOAD_STATUS_BADGES = {
  pending: ["status-badge--muted", "Pendente"],
  success: ["status-badge--success", "Carregado"],
  error: ["status-badge--error", "Erro"],
};

// Carga no banco: badge + tabela/erro + botão de recarga (só para envios que têm carga).
function loadCell(item) {
  if (!item.load_status) return "-";
  const [variant, label] = LOAD_STATUS_BADGES[item.load_status] || ["status-badge--muted", item.load_status];
  const detail = item.load_status === "error" ? item.load_error : item.load_detail;
  return `<div class="load-cell">
    <span class="status-badge ${variant}">${label}</span>
    ${detail ? `<div style="color: var(--text-muted); overflow-wrap: anywhere; max-width: 18rem">${esc(detail)}</div>` : ""}
    <button type="button" class="btn btn-ghost btn-sm" data-reload-id="${item.id}">Recarregar</button>
  </div>`;
}

async function reloadToDatabase(button) {
  button.disabled = true;
  button.textContent = "Carregando...";
  try {
    const item = await apiFetch(`/api/audit/${button.dataset.reloadId}/load`, { method: "POST" });
    showToast(
      item.load_status === "success" ? `Carregado em ${item.load_detail}.` : `Falha na carga: ${item.load_error}`,
      item.load_status === "success" ? "positive" : "negative"
    );
  } catch (err) {
    showToast(`Falha ao recarregar: ${err.message}`, "negative");
  }
  await applyFilters();
}

async function loadContextOptions() {
  const select = document.getElementById("filter-context");
  const contexts = await apiFetch("/api/contexts");
  select.innerHTML =
    '<option value="">Todos</option>' +
    contexts.map((context) => `<option value="${esc(context.name)}">${esc(context.name)}</option>`).join("");
}

async function applyFilters() {
  const params = new URLSearchParams();
  const contextName = document.getElementById("filter-context").value;
  const status = document.getElementById("filter-status").value;
  const startDate = document.getElementById("filter-start-date").value;
  const endDate = document.getElementById("filter-end-date").value;
  if (contextName) params.set("context_name", contextName);
  if (status) params.set("status", status);
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);

  const history = await apiFetch(`/api/audit?${params.toString()}`);
  const rows = document.getElementById("audit-rows");
  rows.innerHTML = history
    .map(
      (item) => `
      <tr class="border-b border-black/5 dark:border-white/10 last:border-0">
        <td data-label="Arquivo" class="px-4 py-2" style="overflow-wrap: anywhere">${esc(item.filename)}</td>
        <td data-label="Contexto" class="px-4 py-2">${esc(item.context_name)}</td>
        <td data-label="Destino" class="px-4 py-2" style="overflow-wrap: anywhere">${esc(item.destination_detail) || "-"}</td>
        <td data-label="Status" class="px-4 py-2 text-center">${statusBadge(item.status)}</td>
        <td data-label="Linhas" class="px-4 py-2 text-right">${item.row_count ?? "-"}</td>
        <td data-label="Banco" class="px-4 py-2">${loadCell(item)}</td>
        <td data-label="Enviado por" class="px-4 py-2">${esc(item.uploaded_by)}</td>
        <td data-label="Data" class="px-4 py-2 whitespace-nowrap">${formatDateTimeBR(item.created_at)}</td>
        <td data-label="Erro" class="px-4 py-2" style="overflow-wrap: anywhere">${esc(item.error_message) || "-"}</td>
      </tr>`
    )
    .join("");
  rows.querySelectorAll("[data-reload-id]").forEach((button) => {
    button.addEventListener("click", () => reloadToDatabase(button));
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  await loadContextOptions();
  await applyFilters();
  document.getElementById("filter-button").addEventListener("click", applyFilters);
});
