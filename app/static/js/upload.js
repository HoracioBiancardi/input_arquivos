const DESTINATION_ICONS = { minio: "☁️", sqlserver: "🗄️", local: "📁" };

let contextsByName = {};

const contextSelect = document.getElementById("context-select");
const destinationIcon = document.getElementById("destination-icon");
const destinationLabel = document.getElementById("destination-label");
const writeModeField = document.getElementById("write-mode-field");
const fileInput = document.getElementById("file-input");
const uploadForm = document.getElementById("upload-form");

function handleContextChange() {
  const context = contextsByName[contextSelect.value];
  if (!context) {
    destinationIcon.textContent = "❓";
    destinationLabel.textContent = "Selecione um contexto";
    writeModeField.classList.add("hidden");
    fileInput.setAttribute("accept", ".xlsx,.xls,.csv,.pdf");
    return;
  }

  destinationIcon.textContent = DESTINATION_ICONS[context.destination_type] || "❓";
  if (context.destination_type === "minio") {
    destinationLabel.textContent = `MinIO → bucket "${context.minio_bucket}"`;
    writeModeField.classList.add("hidden");
  } else if (context.destination_type === "local") {
    destinationLabel.textContent = `Pasta local → ${context.local_path}`;
    writeModeField.classList.add("hidden");
  } else {
    destinationLabel.textContent = `SQL Server → ${context.db_schema_name}.${context.db_table}`;
    writeModeField.classList.remove("hidden");
    const radio = document.querySelector(`input[name="write_mode"][value="${context.default_write_mode}"]`);
    if (radio) radio.checked = true;
  }
  fileInput.setAttribute("accept", context.allowed_extensions.join(","));
}

async function loadContexts() {
  const data = await apiFetch("/api/contexts/me/accessible");
  const noContextsMessage = document.getElementById("no-contexts-message");
  const noContextsText = document.getElementById("no-contexts-text");

  if (data.contexts.length === 0) {
    noContextsText.textContent = data.has_any_active_context
      ? "Você ainda não tem contexts liberados. Peça a um admin para liberar acesso em /admin/users."
      : "Nenhum contexto ativo. Peça a um admin para cadastrar um em /admin/contexts.";
    noContextsMessage.classList.remove("hidden");
    noContextsMessage.classList.add("flex");
    uploadForm.classList.add("hidden");
    return;
  }

  contextsByName = {};
  data.contexts.forEach((context) => {
    contextsByName[context.name] = context;
  });

  contextSelect.innerHTML = data.contexts.map((context) => `<option value="${context.name}">${context.name}</option>`).join("");
  if (data.last_context_name) {
    contextSelect.value = data.last_context_name;
  }

  uploadForm.classList.remove("hidden");
  uploadForm.classList.add("flex");
  handleContextChange();
}

function statusBadge(status) {
  const isSuccess = status === "success";
  return `<span class="status-badge ${isSuccess ? "status-badge--success" : "status-badge--error"}">${isSuccess ? "Sucesso" : "Erro"}</span>`;
}

function formatDate(isoString) {
  const date = new Date(isoString);
  return date.toLocaleDateString("pt-BR") + " " + date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

async function loadHistory() {
  const history = await apiFetch("/api/uploads/recent?limit=20");
  const rows = document.getElementById("history-rows");
  rows.innerHTML = history
    .map(
      (item) => `
      <tr class="border-b border-black/5 dark:border-white/10 last:border-0">
        <td class="px-4 py-2">${item.filename}</td>
        <td class="px-4 py-2">${item.context_name}</td>
        <td class="px-4 py-2">${item.destination_detail || "-"}</td>
        <td class="px-4 py-2 text-center">${statusBadge(item.status)}</td>
        <td class="px-4 py-2">${item.uploaded_by}</td>
        <td class="px-4 py-2">${formatDate(item.created_at)}</td>
      </tr>`
    )
    .join("");
}

async function submitUpload(formData) {
  return apiFetch("/api/uploads", { method: "POST", body: formData });
}

async function handleSubmit(event) {
  event.preventDefault();

  const contextName = contextSelect.value;
  const file = fileInput.files[0];
  if (!contextName || !file) {
    showToast("Selecione um contexto e um arquivo antes de enviar.", "warning");
    return;
  }
  const context = contextsByName[contextName];
  const writeMode = context.destination_type === "sqlserver"
    ? document.querySelector('input[name="write_mode"]:checked').value
    : "";

  const buildFormData = (extra) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("context_name", contextName);
    if (writeMode) formData.append("write_mode", writeMode);
    Object.entries(extra || {}).forEach(([key, value]) => formData.append(key, value));
    return formData;
  };

  const submitButton = document.getElementById("upload-submit");
  submitButton.disabled = true;
  try {
    let result;
    try {
      result = await submitUpload(buildFormData());
    } catch (error) {
      if (error.status === 422) {
        const violation = error.data.detail;
        const parts = [];
        if (violation.missing_columns.length) parts.push(`ausentes: ${violation.missing_columns.join(", ")}`);
        if (violation.empty_columns.length) parts.push(`vazias: ${violation.empty_columns.join(", ")}`);
        showToast(`Arquivo rejeitado — colunas obrigatórias ${parts.join("; ")}.`, "negative");
        fileInput.value = "";
        return;
      }
      if (error.status === 409) {
        const mismatch = error.data.detail;
        const confirmed = await confirmModal({
          title: "Colunas diferentes do último envio",
          body: `
            <p>Este arquivo tem colunas diferentes das do último arquivo aceito para este contexto.</p>
            ${mismatch.extra_columns.length ? `<p class="mt-2">Novas: ${mismatch.extra_columns.join(", ")}</p>` : ""}
            ${mismatch.missing_columns.length ? `<p>Faltando: ${mismatch.missing_columns.join(", ")}</p>` : ""}
            <p class="mt-2">Deseja enviar mesmo assim?</p>
          `,
          confirmLabel: "Enviar mesmo assim",
          cancelLabel: "Cancelar",
          variant: "warning",
        });
        result = await submitUpload(buildFormData(confirmed ? { confirm_mismatch: "true" } : { cancelled: "true" }));
        if (!confirmed) {
          showToast("Envio cancelado.", "warning");
          fileInput.value = "";
          await loadHistory();
          return;
        }
      } else {
        throw error;
      }
    }

    if (result.status === "success") {
      showToast(`Arquivo enviado com sucesso para ${result.destination_detail}.`, "positive");
    } else {
      showToast(`Falha no envio: ${result.error_message}`, "negative");
    }
    fileInput.value = "";
    await loadHistory();
  } catch (error) {
    showToast(`Falha ao processar o arquivo: ${error.message}`, "negative");
  } finally {
    submitButton.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  await loadContexts();
  await loadHistory();
  contextSelect.addEventListener("change", handleContextChange);
  uploadForm.addEventListener("submit", handleSubmit);
});
