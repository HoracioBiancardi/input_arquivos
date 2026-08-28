const FILE_TYPE_LABELS = {
  excel: "Excel",
  csv: "CSV",
  pdf: "PDF",
  image: "Imagem",
  json: "JSON",
  xml: "XML",
  txt: "TXT",
  yaml: "YAML",
  ods: "ODS",
  html: "HTML",
};

const COLUMN_RULE_TYPES = [
  { value: "text", label: "Texto" },
  { value: "integer", label: "Número inteiro" },
  { value: "decimal", label: "Número decimal" },
  { value: "date", label: "Data" },
  { value: "boolean", label: "Sim/Não" },
];

function ruleRowHtml() {
  const options = COLUMN_RULE_TYPES.map((t) => `<option value="${t.value}">${t.label}</option>`).join("");
  return `<tr class="context-rule-row">
    <td class="pr-2 py-1"><input type="text" list="rules-column-options" class="context-rule-column w-full rounded border border-slate-300 dark:border-slate-600 bg-transparent px-2 py-1"></td>
    <td class="pr-2 py-1"><select class="context-rule-type w-full rounded border border-slate-300 dark:border-slate-600 bg-transparent px-2 py-1">${options}</select></td>
    <td class="pr-2 py-1 text-center"><input type="checkbox" class="context-rule-required"></td>
    <td class="py-1"><button type="button" class="context-rule-remove text-red-600">Remover</button></td>
  </tr>`;
}

function populateColumnDatalist(expectedColumns) {
  const datalist = document.getElementById("rules-column-options");
  const columns = (expectedColumns || "")
    .split(",")
    .map((name) => name.trim())
    .filter(Boolean);
  datalist.innerHTML = columns.map((name) => `<option value="${name}"></option>`).join("");
}

function addRuleRow(rule) {
  const rowsEl = document.getElementById("context-rules-rows");
  rowsEl.insertAdjacentHTML("beforeend", ruleRowHtml());
  const row = rowsEl.lastElementChild;
  if (rule) {
    row.querySelector(".context-rule-column").value = rule.column;
    row.querySelector(".context-rule-type").value = rule.type;
    row.querySelector(".context-rule-required").checked = !!rule.required;
  }
  row.querySelector(".context-rule-remove").addEventListener("click", () => row.remove());
}

function clearRuleRows() {
  document.getElementById("context-rules-rows").innerHTML = "";
}

function collectColumnRules() {
  return Array.from(document.querySelectorAll(".context-rule-row"))
    .map((row) => ({
      column: row.querySelector(".context-rule-column").value.trim(),
      type: row.querySelector(".context-rule-type").value,
      required: row.querySelector(".context-rule-required").checked,
    }))
    .filter((rule) => rule.column);
}

const PDF_MODE_LABELS = {
  extract_tables: "Extrair tabelas",
  metadata_only: "Somente metadados",
  raw_archive: "Arquivar original",
  ocr_stock_lots: "OCR: estoque com lotes",
};

const IMAGE_MODE_LABELS = {
  raw_archive: "Arquivar original",
  table_grid: "Tabela com grade",
  table_borderless: "Tabela sem grade",
};

const PDF_MODE_HELP = {
  extract_tables: "Tenta extrair tabelas estruturadas do PDF (funciona melhor em PDFs com tabelas bem definidas).",
  metadata_only: "Gera uma linha com nome do arquivo, quantidade de páginas e o texto extraído, sem tentar estruturar tabelas.",
  raw_archive: "Não converte para Parquet: arquiva o PDF original diretamente no bucket MinIO ou na pasta local do contexto.",
  ocr_stock_lots: "Modo específico para relatórios \"Relação de Estoque\" (produto + lotes) cujo texto foi vetorizado pelo gerador do PDF: rasteriza a página e usa OCR local em posições de coluna fixas, calibradas para esse layout — não funciona para outros formatos de PDF.",
};

const IMAGE_MODE_HELP = {
  raw_archive: "Não converte para Parquet: arquiva a imagem original no bucket MinIO ou na pasta local do contexto (modo seguro enquanto o tipo de imagem de entrada ainda não foi validado).",
  table_grid: "Extrai tabela via OCR local assumindo grade/linhas visíveis (ex.: foto de planilha impressa, print de sistema com bordas).",
  table_borderless: "Extrai tabela via OCR local usando heurística de posição/espaçamento, para imagens sem grade visível (ex.: texto tabular solto).",
};

const modal = document.getElementById("context-modal");
const form = document.getElementById("context-form");
const destinationSelect = document.getElementById("context-destination");
const pdfModeSelect = document.getElementById("context-pdf-mode");
const imageModeSelect = document.getElementById("context-image-mode");

// `column_rules` não é editado neste modal (ver rules-modal), mas o PUT de
// context é um replace completo — guardamos o valor buscado do servidor
// para reenviá-lo sem alteração e não apagar as regras já configuradas.
let currentEditContext = null;

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
      <tr class="border-b border-slate-700/30 last:border-0 cursor-pointer" data-id="${context.id}">
        <td class="px-4 py-2 font-medium">${esc(context.name)}</td>
        <td class="px-4 py-2">${esc(context.destination_summary)}</td>
        <td class="px-4 py-2">${context.allowed_file_types.split(",").map((t) => FILE_TYPE_LABELS[t] || t).join(", ")}</td>
        <td class="px-4 py-2">${PDF_MODE_LABELS[context.pdf_mode] || context.pdf_mode}</td>
        <td class="px-4 py-2">${IMAGE_MODE_LABELS[context.image_mode] || context.image_mode}</td>
        <td class="px-4 py-2 text-center">${statusBadge(context.active)}</td>
        <td class="px-4 py-2 text-right">
          <button type="button" class="context-rules-button text-xs px-2 py-1 rounded-lg border border-slate-300 dark:border-slate-600" data-id="${context.id}">Regras${context.column_rules.length ? ` (${context.column_rules.length})` : ""}</button>
        </td>
      </tr>`
    )
    .join("");
  rows.querySelectorAll("tr[data-id]").forEach((row) => {
    row.addEventListener("click", () => openEditModal(Number(row.dataset.id)));
  });
  rows.querySelectorAll(".context-rules-button").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openRulesModal(Number(button.dataset.id));
    });
  });
}

function toggleDestinationFields() {
  const selected = destinationSelect.value;
  document.getElementById("minio-fields").classList.toggle("hidden", selected !== "minio");
  document.getElementById("local-fields").classList.toggle("hidden", selected !== "local");
}

function updatePdfHelp() {
  document.getElementById("pdf-mode-help").textContent = PDF_MODE_HELP[pdfModeSelect.value] || "";
}

function updateImageHelp() {
  document.getElementById("image-mode-help").textContent = IMAGE_MODE_HELP[imageModeSelect.value] || "";
}

function clearTestResults() {
  ["minio-test-result", "local-test-result"].forEach((id) => {
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
  document.getElementById("context-active").checked = true;
  currentEditContext = null;
  clearTestResults();
  clearFieldErrors("context");
  toggleDestinationFields();
  updatePdfHelp();
  updateImageHelp();
}

function openCreateModal() {
  resetForm();
  document.getElementById("context-modal-title").textContent = "Novo Contexto";
  modal.classList.remove("hidden");
  modal.classList.add("open", "flex");
}

async function openEditModal(contextId) {
  const context = await apiFetch(`/api/contexts/${contextId}`);
  resetForm();
  currentEditContext = context;
  document.getElementById("context-modal-title").textContent = "Editar Contexto";
  document.getElementById("context-id").value = context.id;
  document.getElementById("context-name").value = context.name;
  context.allowed_file_types.split(",").forEach((type) => {
    const checkbox = document.querySelector(`.context-file-type[value="${type}"]`);
    if (checkbox) checkbox.checked = true;
  });
  destinationSelect.value = context.destination_type;
  document.getElementById("context-minio-bucket").value = context.minio_bucket || "";
  document.getElementById("context-local-path").value = context.local_path || "";
  pdfModeSelect.value = context.pdf_mode;
  imageModeSelect.value = context.image_mode;
  document.getElementById("context-active").checked = context.active;
  toggleDestinationFields();
  updatePdfHelp();
  updateImageHelp();
  modal.classList.remove("hidden");
  modal.classList.add("open", "flex");
}

function closeModal() {
  modal.classList.remove("open", "flex");
  modal.classList.add("hidden");
}
window.closeModal = closeModal;

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
    pdf_mode: pdfModeSelect.value,
    image_mode: imageModeSelect.value,
    minio_bucket: document.getElementById("context-minio-bucket").value || null,
    local_path: document.getElementById("context-local-path").value || null,
    allowed_file_types: fileTypes.join(","),
    column_rules: currentEditContext ? currentEditContext.column_rules : [],
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

const rulesModal = document.getElementById("rules-modal");
let currentRulesContext = null;

async function openRulesModal(contextId) {
  const context = await apiFetch(`/api/contexts/${contextId}`);
  currentRulesContext = context;
  document.getElementById("rules-context-id").value = context.id;
  document.getElementById("rules-modal-context-name").textContent = context.name;
  populateColumnDatalist(context.expected_columns);
  clearRuleRows();
  (context.column_rules || []).forEach(addRuleRow);
  rulesModal.classList.remove("hidden");
  rulesModal.classList.add("open", "flex");
}

function closeRulesModal() {
  rulesModal.classList.remove("open", "flex");
  rulesModal.classList.add("hidden");
  currentRulesContext = null;
}
window.closeRulesModal = closeRulesModal;

async function saveRules() {
  if (!currentRulesContext) return;
  const context = currentRulesContext;
  const payload = {
    name: context.name,
    destination_type: context.destination_type,
    pdf_mode: context.pdf_mode,
    image_mode: context.image_mode,
    minio_bucket: context.minio_bucket,
    local_path: context.local_path,
    allowed_file_types: context.allowed_file_types,
    column_rules: collectColumnRules(),
    active: context.active,
  };
  try {
    await apiFetch(`/api/contexts/${context.id}`, { method: "PUT", body: payload });
    closeRulesModal();
    await loadContexts();
    showToast("Regras salvas com sucesso.", "positive");
  } catch (error) {
    showToast(`Falha ao salvar regras: ${error.message}`, "negative");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadContexts();
  document.getElementById("new-context-button").addEventListener("click", openCreateModal);
  document.getElementById("context-cancel-button").addEventListener("click", closeModal);
  destinationSelect.addEventListener("change", toggleDestinationFields);
  pdfModeSelect.addEventListener("change", updatePdfHelp);
  imageModeSelect.addEventListener("change", updateImageHelp);
  document.getElementById("context-add-rule-button").addEventListener("click", () => addRuleRow());
  document.getElementById("rules-cancel-button").addEventListener("click", closeRulesModal);
  document.getElementById("rules-save-button").addEventListener("click", saveRules);
  form.addEventListener("submit", saveContext);

  document.getElementById("test-minio-button").addEventListener("click", async () => {
    const bucket = document.getElementById("context-minio-bucket").value;
    const result = await apiFetch("/api/contexts/test-minio", { method: "POST", body: { bucket } });
    setTestResult("minio-test-result", result);
  });
  document.getElementById("test-local-button").addEventListener("click", async () => {
    const path = document.getElementById("context-local-path").value;
    const result = await apiFetch("/api/contexts/test-local", { method: "POST", body: { path } });
    setTestResult("local-test-result", result);
  });

  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });
  rulesModal.addEventListener("click", (event) => {
    if (event.target === rulesModal) closeRulesModal();
  });
});
