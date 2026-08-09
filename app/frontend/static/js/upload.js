const DESTINATION_ICONS = { minio: "☁️", sqlserver: "🗄️", local: "📁" };

let contextsByName = {};

const contextSelect = document.getElementById("context-select");
const destinationIcon = document.getElementById("destination-icon");
const destinationLabel = document.getElementById("destination-label");
const writeModeField = document.getElementById("write-mode-field");
const fileInput = document.getElementById("file-input");
const uploadForm = document.getElementById("upload-form");

function onFileSelected(input) {
  const file = input.files?.[0];
  const badge = document.getElementById("selected-file-badge");
  const nameEl = document.getElementById("selected-file-name");
  if (file && badge && nameEl) {
    const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
    nameEl.textContent = `📄 ${file.name} (${sizeMb} MB)`;
    badge.classList.remove("hidden");
  }
}

window.onFileSelected = onFileSelected;

function initDragAndDrop() {
  const dropZone = document.getElementById("drop-zone");
  if (!dropZone) return;

  ["dragenter", "dragover"].forEach(evtName => {
    dropZone.addEventListener(evtName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.style.borderColor = "var(--primary)";
      dropZone.style.background = "var(--surface-hover)";
    }, false);
  });

  ["dragleave", "drop"].forEach(evtName => {
    dropZone.addEventListener(evtName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.style.borderColor = "var(--border)";
      dropZone.style.background = "var(--surface-alt)";
    }, false);
  });

  dropZone.addEventListener("drop", (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files && files.length > 0) {
      fileInput.files = files;
      onFileSelected(fileInput);
    }
  });
}

function handleContextChange() {
  const context = contextsByName[contextSelect.value];
  if (!context) {
    destinationIcon.textContent = "📁";
    destinationLabel.textContent = "Destino: Pasta local Parquet";
    writeModeField.classList.add("hidden");
    fileInput.setAttribute("accept", ".xlsx,.xls,.csv,.pdf,.json,.xml,.txt");
    return;
  }

  destinationIcon.textContent = DESTINATION_ICONS[context.destination_type] || "❓";
  if (context.destination_type === "minio") {
    destinationLabel.textContent = `MinIO → bucket "${context.minio_bucket}"`;
    writeModeField.classList.add("hidden");
  } else if (context.destination_type === "local") {
    destinationLabel.textContent = `Pasta local → ${context.local_path || "data/parquet"}`;
    writeModeField.classList.add("hidden");
  } else {
    destinationLabel.textContent = `SQL Server → ${context.db_schema_name || "dbo"}.${context.db_table || "tabela"}`;
    writeModeField.classList.remove("hidden");
    const radio = document.querySelector(`input[name="write_mode"][value="${context.default_write_mode || "append"}"]`);
    if (radio) radio.checked = true;
  }
  if (context.allowed_extensions && context.allowed_extensions.length > 0) {
    fileInput.setAttribute("accept", context.allowed_extensions.join(","));
  }
}

async function loadContexts() {
  try {
    const data = await apiFetch("/api/contexts/me/accessible");
    const noContextsMessage = document.getElementById("no-contexts-message");
    const noContextsText = document.getElementById("no-contexts-text");

    if (!data.contexts || data.contexts.length === 0) {
      if (noContextsMessage && noContextsText) {
        noContextsText.textContent = data.has_any_active_context
          ? "Você ainda não tem contexts liberados. Peça a um admin para liberar acesso em /admin/users."
          : "Nenhum contexto cadastrado. Acesse /admin/contexts para criar um contexto de destino.";
        noContextsMessage.classList.remove("hidden");
        noContextsMessage.classList.add("flex");
      }
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
  } catch (err) {
    console.warn("Utilizando contexto local padrão:", err);
  }

  handleContextChange();
}

function statusBadge(status) {
  const isSuccess = status === "success";
  return `<span class="badge ${isSuccess ? "badge-success" : "badge-danger"}">${isSuccess ? "Sucesso" : "Erro"}</span>`;
}

function formatDate(isoString) {
  if (!isoString) return "–";
  const date = new Date(isoString);
  return date.toLocaleDateString("pt-BR") + " " + date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function viewTableAction(item) {
  if (item.status === "success" && item.artifact_kind === "parquet") {
    return `<a href="/uploads/${item.id}/preview" class="btn btn-ghost btn-sm">Visualizar →</a>`;
  }
  return "—";
}

async function loadHistory() {
  try {
    const history = await apiFetch("/api/uploads/recent?limit=20");
    const rows = document.getElementById("history-rows");
    if (!rows || !history || history.length === 0) return;

    rows.innerHTML = history
      .map(
        (item) => `
        <tr class="border-b border-black/5 dark:border-white/10 last:border-0">
          <td class="px-4 py-2 font-mono font-bold">${item.filename}</td>
          <td class="px-4 py-2">${item.context_name}</td>
          <td class="px-4 py-2">${item.destination_detail || "-"}</td>
          <td class="px-4 py-2 text-center">${statusBadge(item.status)}</td>
          <td class="px-4 py-2">${item.uploaded_by}</td>
          <td class="px-4 py-2">${formatDate(item.created_at)}</td>
          <td class="px-4 py-2 text-right">${viewTableAction(item)}</td>
        </tr>`
      )
      .join("");
  } catch (err) {
    console.warn("Falha ao carregar histórico:", err);
  }
}

async function submitUpload(formData) {
  return apiFetch("/api/uploads", { method: "POST", body: formData });
}

async function handleSubmit(event) {
  event.preventDefault();

  const contextName = contextSelect.value;
  const file = fileInput.files?.[0];
  if (!contextName || !file) {
    showToast("Selecione um contexto e um arquivo antes de enviar.", "warning");
    return;
  }
  const context = contextsByName[contextName];
  const writeMode = (context && context.destination_type === "sqlserver")
    ? (document.querySelector('input[name="write_mode"]:checked')?.value || "append")
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
  const submitButtonLabel = document.getElementById("upload-submit-label");
  if (submitButton) submitButton.disabled = true;
  if (submitButtonLabel) submitButtonLabel.textContent = "Enviando e validando dados...";

  try {
    let result;
    try {
      result = await submitUpload(buildFormData());
    } catch (error) {
      if (error.status === 422 && error.data?.detail?.violations) {
        const violation = error.data.detail;
        const reasonLabels = {
          coluna_ausente: "coluna ausente no arquivo",
          obrigatoria: "célula(s) vazia(s)",
          tipo_invalido: "valor(es) fora do tipo esperado",
        };
        const parts = violation.violations.map((item) => {
          const kind = reasonLabels[item.reason] || item.reason;
          return item.reason === "coluna_ausente" ? `${item.column}: ${kind}` : `${item.column}: ${item.bad_row_count} linha(s) com ${kind}`;
        });
        showToast(`Arquivo rejeitado — dados inválidos: ${parts.join("; ")}.`, "negative");
        fileInput.value = "";
        await loadHistory();
        return;
      }
      if (error.status === 409 && error.data?.detail) {
        const mismatch = error.data.detail;
        const confirmed = await confirmModal({
          title: "Colunas diferentes do último envio",
          body: `
            <p>Este arquivo tem colunas diferentes das do último arquivo aceito para este contexto.</p>
            ${mismatch.extra_columns?.length ? `<p class="mt-2">Novas: ${mismatch.extra_columns.join(", ")}</p>` : ""}
            ${mismatch.missing_columns?.length ? `<p>Faltando: ${mismatch.missing_columns.join(", ")}</p>` : ""}
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

    const viewLastUploadLink = document.getElementById("view-last-upload-link");
    if (result && result.status === "success") {
      showToast(`Arquivo enviado com sucesso para ${result.destination_detail || "destino"}.`, "positive");
      if (result.artifact_kind === "parquet" && viewLastUploadLink) {
        viewLastUploadLink.href = `/uploads/${result.id}/preview`;
        viewLastUploadLink.classList.remove("hidden");
      }
    } else if (result) {
      showToast(`Falha no envio: ${result.error_message || "Erro desconhecido"}`, "negative");
    }
    fileInput.value = "";
    document.getElementById("selected-file-badge")?.classList.add("hidden");
    await loadHistory();
  } catch (error) {
    showToast(`Falha ao processar o arquivo: ${error.message || error}`, "negative");
  } finally {
    if (submitButton) submitButton.disabled = false;
    if (submitButtonLabel) submitButtonLabel.textContent = "⚡ Enviar Arquivo";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  initDragAndDrop();
  await loadContexts();
  await loadHistory();
  contextSelect?.addEventListener("change", handleContextChange);
  uploadForm?.addEventListener("submit", handleSubmit);
});
