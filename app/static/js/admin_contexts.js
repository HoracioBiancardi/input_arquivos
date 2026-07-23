const FILE_TYPE_LABELS = { excel: "Excel", csv: "CSV", pdf: "PDF" };

const PDF_MODE_HELP = {
  extract_tables: "Tenta extrair tabelas estruturadas do PDF (funciona melhor em PDFs com tabelas bem definidas).",
  metadata_only: "Gera uma linha com nome do arquivo, quantidade de páginas e o texto extraído, sem tentar estruturar tabelas.",
  raw_archive: "Não converte para Parquet: arquiva o PDF original diretamente no bucket MinIO ou na pasta local do contexto.",
};

const modal = document.getElementById("context-modal");
const form = document.getElementById("context-form");
const destinationSelect = document.getElementById("context-destination");
const pdfModeSelect = document.getElementById("context-pdf-mode");

function statusBadge(active) {
  return active
    ? '<span class="status-badge status-badge--success">Sim</span>'
    : '<span class="status-badge status-badge--muted">Não</span>';
}

async function loadContexts() {
  const contexts = await apiFetch("/api/contexts");
  const rows = document.getElementById("context-rows");
  rows.innerHTML = contexts
    .map(
      (context) => `
      <tr class="border-b border-black/5 dark:border-white/10 last:border-0 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800" data-id="${context.id}">
        <td class="px-4 py-2 font-medium">${context.name}</td>
        <td class="px-4 py-2">${context.destination_summary}</td>
        <td class="px-4 py-2">${context.allowed_file_types.split(",").map((t) => FILE_TYPE_LABELS[t] || t).join(", ")}</td>
        <td class="px-4 py-2">${context.pdf_mode}</td>
        <td class="px-4 py-2 text-center">${statusBadge(context.active)}</td>
      </tr>`
    )
    .join("");
  rows.querySelectorAll("tr[data-id]").forEach((row) => {
    row.addEventListener("click", () => openEditModal(Number(row.dataset.id)));
  });
}

function toggleDestinationFields() {
  const selected = destinationSelect.value;
  document.getElementById("minio-fields").classList.toggle("hidden", selected !== "minio");
  document.getElementById("db-fields").classList.toggle("hidden", selected !== "sqlserver");
  document.getElementById("local-fields").classList.toggle("hidden", selected !== "local");
}

function updatePdfHelp() {
  document.getElementById("pdf-mode-help").textContent = PDF_MODE_HELP[pdfModeSelect.value] || "";
}

function clearTestResults() {
  ["minio-test-result", "db-test-result", "local-test-result"].forEach((id) => {
    const el = document.getElementById(id);
    el.textContent = "";
    el.className = "text-sm";
  });
}

function setTestResult(elementId, result) {
  const el = document.getElementById(elementId);
  el.textContent = result.message;
  el.className = "text-sm " + (result.success ? "text-green-600" : "text-red-600");
}

function resetForm() {
  form.reset();
  document.getElementById("context-id").value = "";
  document.querySelectorAll(".context-file-type").forEach((checkbox) => (checkbox.checked = false));
  document.getElementById("context-db-schema").value = "dbo";
  document.getElementById("context-active").checked = true;
  clearTestResults();
  clearFieldErrors("context");
  toggleDestinationFields();
  updatePdfHelp();
}

function openCreateModal() {
  resetForm();
  document.getElementById("context-modal-title").textContent = "Novo Context";
  modal.classList.remove("hidden");
  modal.classList.add("flex");
}

async function openEditModal(contextId) {
  const context = await apiFetch(`/api/contexts/${contextId}`);
  resetForm();
  document.getElementById("context-modal-title").textContent = "Editar Context";
  document.getElementById("context-id").value = context.id;
  document.getElementById("context-name").value = context.name;
  context.allowed_file_types.split(",").forEach((type) => {
    const checkbox = document.querySelector(`.context-file-type[value="${type}"]`);
    if (checkbox) checkbox.checked = true;
  });
  destinationSelect.value = context.destination_type;
  document.getElementById("context-minio-bucket").value = context.minio_bucket || "";
  document.getElementById("context-db-connection").value = context.db_connection_string || "";
  document.getElementById("context-db-schema").value = context.db_schema_name || "dbo";
  document.getElementById("context-db-table").value = context.db_table || "";
  document.getElementById("context-local-path").value = context.local_path || "";
  document.getElementById("context-required-columns").value = context.required_columns || "";
  document.getElementById("context-write-mode").value = context.default_write_mode;
  pdfModeSelect.value = context.pdf_mode;
  document.getElementById("context-active").checked = context.active;
  toggleDestinationFields();
  updatePdfHelp();
  modal.classList.remove("hidden");
  modal.classList.add("flex");
}

function closeModal() {
  modal.classList.add("hidden");
  modal.classList.remove("flex");
}

async function saveContext(event) {
  event.preventDefault();
  clearFieldErrors("context");
  const fileTypes = Array.from(document.querySelectorAll(".context-file-type:checked")).map((cb) => cb.value);
  if (fileTypes.length === 0) {
    showToast("Selecione ao menos um tipo de arquivo aceito.", "warning");
    return;
  }

  const payload = {
    name: document.getElementById("context-name").value,
    destination_type: destinationSelect.value,
    default_write_mode: document.getElementById("context-write-mode").value,
    pdf_mode: pdfModeSelect.value,
    minio_bucket: document.getElementById("context-minio-bucket").value || null,
    db_connection_string: document.getElementById("context-db-connection").value || null,
    db_schema_name: document.getElementById("context-db-schema").value || "dbo",
    db_table: document.getElementById("context-db-table").value || null,
    local_path: document.getElementById("context-local-path").value || null,
    allowed_file_types: fileTypes.join(","),
    required_columns: document
      .getElementById("context-required-columns")
      .value.split(",")
      .map((name) => name.trim())
      .filter(Boolean)
      .join(","),
    active: document.getElementById("context-active").checked,
  };

  const contextId = document.getElementById("context-id").value;
  try {
    if (contextId) {
      await apiFetch(`/api/contexts/${contextId}`, { method: "PUT", body: payload });
    } else {
      await apiFetch("/api/contexts", { method: "POST", body: payload });
    }
    closeModal();
    await loadContexts();
    showToast("Context salvo com sucesso.", "positive");
  } catch (error) {
    const fieldErrors = extractFieldErrors(error.data);
    if (applyFieldErrors("context", fieldErrors) === 0) {
      showToast(`Falha ao salvar: ${error.message}`, "negative");
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadContexts();
  document.getElementById("new-context-button").addEventListener("click", openCreateModal);
  document.getElementById("context-cancel-button").addEventListener("click", closeModal);
  destinationSelect.addEventListener("change", toggleDestinationFields);
  pdfModeSelect.addEventListener("change", updatePdfHelp);
  form.addEventListener("submit", saveContext);

  document.getElementById("test-minio-button").addEventListener("click", async () => {
    const bucket = document.getElementById("context-minio-bucket").value;
    const result = await apiFetch("/api/contexts/test-minio", { method: "POST", body: { bucket } });
    setTestResult("minio-test-result", result);
  });
  document.getElementById("test-db-button").addEventListener("click", async () => {
    const connectionString = document.getElementById("context-db-connection").value;
    const result = await apiFetch("/api/contexts/test-db", { method: "POST", body: { connection_string: connectionString } });
    setTestResult("db-test-result", result);
  });
  document.getElementById("test-local-button").addEventListener("click", async () => {
    const path = document.getElementById("context-local-path").value;
    const result = await apiFetch("/api/contexts/test-local", { method: "POST", body: { path } });
    setTestResult("local-test-result", result);
  });
});
