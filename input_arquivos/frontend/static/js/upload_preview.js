function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function renderPreviewTable(preview) {
  document.getElementById("preview-filename").textContent = preview.filename;
  document.getElementById("preview-context").textContent = `Contexto: ${preview.context_name}`;

  if (preview.truncated) {
    const note = document.getElementById("preview-truncated-note");
    note.textContent = `Mostrando as primeiras ${preview.rows.length} de ${preview.total_row_count} linhas.`;
    note.classList.remove("hidden");
  }

  const head = document.getElementById("preview-table-head");
  head.innerHTML = preview.columns.map((column) => `<th class="px-4 py-2">${escapeHtml(column)}</th>`).join("");

  const body = document.getElementById("preview-table-body");
  body.innerHTML = preview.rows
    .map(
      (row) => `
      <tr class="border-b border-black/5 dark:border-white/10 last:border-0">
        ${row.map((value) => `<td class="px-4 py-2">${value === null || value === undefined ? "" : escapeHtml(value)}</td>`).join("")}
      </tr>`
    )
    .join("");
}

function showPreviewEmptyState(message) {
  document.getElementById("preview-table-card").classList.add("hidden");
  document.getElementById("preview-filename").textContent = "Sem tabela para visualizar";
  const emptyState = document.getElementById("preview-empty-state");
  document.getElementById("preview-empty-message").textContent = message;
  emptyState.classList.remove("hidden");
}

async function loadPreview() {
  const uploadId = document.getElementById("preview-root").dataset.uploadId;
  try {
    const preview = await apiFetch(`/api/uploads/${uploadId}/preview`);
    renderPreviewTable(preview);
  } catch (error) {
    if (error.status === 409) {
      showPreviewEmptyState(error.message);
    } else if (error.status === 404) {
      showPreviewEmptyState("Este upload não foi encontrado.");
    } else {
      showToast(`Falha ao carregar a tabela: ${error.message}`, "negative");
      showPreviewEmptyState("Não foi possível carregar esta tabela.");
    }
  }
}

document.addEventListener("DOMContentLoaded", loadPreview);
