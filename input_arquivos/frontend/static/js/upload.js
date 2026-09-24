const DESTINATION_ICONS = { minio: "☁️", local: "📁" };

let contextsByName = {};

const contextSelect = document.getElementById("context-select");
const destinationIcon = document.getElementById("destination-icon");
const destinationLabel = document.getElementById("destination-label");
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
    fileInput.setAttribute("accept", ".xlsx,.xls,.csv,.pdf,.json,.xml,.txt");
    return;
  }

  destinationIcon.textContent = DESTINATION_ICONS[context.destination_type] || "❓";
  if (context.destination_type === "minio") {
    destinationLabel.textContent = `MinIO → bucket "${context.minio_bucket}"`;
  } else {
    destinationLabel.textContent = `Pasta local → ${context.local_path || "data/parquet"}`;
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

    contextSelect.innerHTML = data.contexts.map((context) => `<option value="${esc(context.name)}">${esc(context.name)}</option>`).join("");
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

const LOAD_STATUS_LABELS = { pending: "Banco: pendente", success: "Banco: carregado", error: "Banco: erro" };

// Situação da carga no banco, abaixo do status do envio (só para contextos que carregam no banco).
function loadStatusLine(item) {
  if (!item.load_status) return "";
  const title = item.load_status === "error" ? item.load_error : item.load_detail;
  return `<div class="text-xs mt-1" style="color: var(--text-muted)" title="${esc(title || "")}">${LOAD_STATUS_LABELS[item.load_status] || esc(item.load_status)}</div>`;
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
  if (item.status !== "success") {
    return `<button type="button" class="btn btn-ghost btn-sm" data-error-id="${item.id}">Ver erro</button>`;
  }
  return "—";
}

const DATA_VIOLATION_PREFIX = "Dados inválidos: ";
const violationReasonLabels = {
  coluna_ausente: "coluna ausente no arquivo",
  obrigatoria: "célula(s) vazia(s)",
  tipo_invalido: "valor(es) fora do tipo esperado",
};
const ruleTypeLabels = { text: "Texto", integer: "Inteiro", decimal: "Decimal", date: "Data", boolean: "Boolean" };

// Mensagem gravada no histórico: "Dados inválidos: col (motivo, N linha(s)); col2 (...)" vira uma lista;
// qualquer outra mensagem (erro de leitura, MinIO, cancelamento) é exibida como texto corrido.
function errorMessageHtml(message) {
  if (!message) return "<p>Nenhum detalhe foi registrado para este erro.</p>";
  if (message.startsWith(DATA_VIOLATION_PREFIX)) {
    const items = message.slice(DATA_VIOLATION_PREFIX.length).split("; ");
    return `
      <p>O arquivo foi rejeitado porque alguns dados não respeitam as regras de coluna do contexto:</p>
      <ul class="mt-2" style="list-style: disc; padding-left: 1.25rem">${items.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`;
  }
  return `<p style="white-space: pre-wrap; word-break: break-word">${esc(message)}</p>`;
}

function showHistoryError(item) {
  alertModal({
    title: "Detalhes do erro",
    body: `
      <p><strong>Arquivo:</strong> ${esc(item.filename)}</p>
      <p><strong>Contexto:</strong> ${esc(item.context_name)} · <strong>Data:</strong> ${formatDate(item.created_at)}</p>
      <div class="mt-3">${errorMessageHtml(item.error_message)}</div>`,
  });
}

// Resposta 422 da API (antes de gravar no histórico) traz as amostras de linhas com problema,
// que a mensagem do histórico não guarda — por isso esse modal é mais detalhado que o do "Ver erro".
function showViolationModal(filename, violations) {
  const blocks = violations
    .map((item) => {
      const reason = violationReasonLabels[item.reason] || item.reason;
      const type = ruleTypeLabels[item.rule_type] || item.rule_type;
      const header = `<p class="mt-3"><strong>${esc(item.column)}</strong> (${esc(type)}): ${
        item.reason === "coluna_ausente" ? esc(reason) : `${item.bad_row_count} linha(s) com ${esc(reason)}`
      }</p>`;
      if (!item.sample?.length) return header;
      const rows = item.sample
        .map((sample) => `<tr><td class="px-2 py-1">${sample.row}</td><td class="px-2 py-1 font-mono">${esc(sample.value) || "<em>(vazio)</em>"}</td></tr>`)
        .join("");
      const more = item.bad_row_count > item.sample.length ? `<p class="text-xs">… e mais ${item.bad_row_count - item.sample.length} linha(s).</p>` : "";
      return `${header}
        <table class="text-sm mt-1"><thead><tr><th class="px-2 py-1 text-left">Linha</th><th class="px-2 py-1 text-left">Valor</th></tr></thead><tbody>${rows}</tbody></table>${more}`;
    })
    .join("");
  alertModal({
    title: "Arquivo rejeitado — dados inválidos",
    body: `<p><strong>Arquivo:</strong> ${esc(filename)}</p>${blocks}`,
  });
}

let historyById = {};

async function loadHistory() {
  try {
    const history = await apiFetch("/api/uploads/recent?limit=20");
    const rows = document.getElementById("history-rows");
    if (!rows || !history || history.length === 0) return;
    historyById = Object.fromEntries(history.map((item) => [item.id, item]));

    rows.innerHTML = history
      .map(
        (item) => `
        <tr class="border-b border-black/5 dark:border-white/10 last:border-0">
          <td class="px-4 py-2 font-mono font-bold" style="overflow-wrap: anywhere; min-width: 10rem">${esc(item.filename)}</td>
          <td class="px-4 py-2">${esc(item.context_name)}</td>
          <td class="px-4 py-2 hidden lg:table-cell" style="overflow-wrap: anywhere; min-width: 12rem">${esc(item.destination_detail) || "-"}</td>
          <td class="px-4 py-2 text-center">${statusBadge(item.status)}${loadStatusLine(item)}</td>
          <td class="px-4 py-2 hidden md:table-cell">${esc(item.uploaded_by)}</td>
          <td class="px-4 py-2 whitespace-nowrap">${formatDate(item.created_at)}</td>
          <td class="px-4 py-2 text-right whitespace-nowrap sticky-action">${viewTableAction(item)}</td>
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
  const buildFormData = (extra) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("context_name", contextName);
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
        showViolationModal(file.name, error.data.detail.violations);
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
      showHistoryError(result);
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
  document.getElementById("history-rows")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-error-id]");
    const item = button && historyById[button.dataset.errorId];
    if (item) showHistoryError(item);
  });
});
