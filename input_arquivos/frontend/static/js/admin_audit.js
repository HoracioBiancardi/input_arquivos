function statusBadge(status) {
  const isSuccess = status === "success";
  return `<span class="status-badge ${isSuccess ? "status-badge--success" : "status-badge--error"}">${isSuccess ? "Sucesso" : "Erro"}</span>`;
}

function formatDate(isoString) {
  const date = new Date(isoString);
  return date.toLocaleDateString("pt-BR") + " " + date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
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
        <td class="px-4 py-2">${esc(item.filename)}</td>
        <td class="px-4 py-2">${esc(item.context_name)}</td>
        <td class="px-4 py-2">${esc(item.destination_detail) || "-"}</td>
        <td class="px-4 py-2 text-center">${statusBadge(item.status)}</td>
        <td class="px-4 py-2 text-right">${item.row_count ?? "-"}</td>
        <td class="px-4 py-2">${esc(item.uploaded_by)}</td>
        <td class="px-4 py-2">${formatDate(item.created_at)}</td>
        <td class="px-4 py-2">${esc(item.error_message) || "-"}</td>
      </tr>`
    )
    .join("");
}

document.addEventListener("DOMContentLoaded", async () => {
  await loadContextOptions();
  await applyFilters();
  document.getElementById("filter-button").addEventListener("click", applyFilters);
});
