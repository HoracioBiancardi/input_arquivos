// Ícones Material Symbols do destino (o <span> tem a classe .ms).
const DESTINATION_ICONS = { minio: "cloud_upload", local: "folder" };

let contextsByName = {};

// ── Competência (contexto mensal) ──
const MONTH_NAMES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const PERIOD_STATE_TEXT = { missing: "falta", future: "—", not_expected: "—" };
const BR_DAY_MONTH = new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit" });
const periodPanel = document.getElementById("period-panel");
const periodSelectField = document.getElementById("period-select-field");
const periodSelect = document.getElementById("period-select");
let periodYear = new Date().getFullYear();
// Mês já escolhido pelo usuário (no seletor ou clicando na grade): a grade não o troca ao recarregar.
let periodChosen = false;

function periodLabel(period) {
  const [year, month] = period.split("-");
  return `${MONTH_NAMES[Number(month) - 1]}/${year}`;
}

function isMonthly(context) {
  return context?.period_mode === "monthly";
}

function usesPeriodSelector(context) {
  return isMonthly(context) && context.period_source === "selector";
}

// Opções do seletor: 2 anos para trás e 1 para frente; um mês fora disso (clicado na grade) é acrescentado.
function fillPeriodSelect() {
  const today = new Date();
  const options = [];
  for (let offset = -24; offset <= 12; offset += 1) {
    const date = new Date(today.getFullYear(), today.getMonth() + offset, 1);
    options.push(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`);
  }
  periodSelect.replaceChildren(
    ...options.reverse().map((period) => {
      const option = document.createElement("option");
      option.value = period;
      option.textContent = periodLabel(period);
      return option;
    })
  );
  periodSelect.value = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
}

function selectPeriod(period) {
  if (![...periodSelect.options].some((option) => option.value === period)) {
    const option = document.createElement("option");
    option.value = period;
    option.textContent = periodLabel(period);
    periodSelect.prepend(option);
  }
  periodSelect.value = period;
  markSelectedCell();
}

function markSelectedCell() {
  document.querySelectorAll("#period-grid .period-cell").forEach((cell) => {
    cell.classList.toggle("is-selected", usesPeriodSelector(contextsByName[contextSelect.value]) && cell.dataset.period === periodSelect.value);
  });
}

function periodCellTitle(month) {
  if (month.state !== "sent") {
    return `${periodLabel(month.period)}: ${month.state === "missing" ? "ainda não enviado" : "não esperado"}`;
  }
  const lines = month.uploads.map(
    (upload) => `Enviado por ${upload.uploaded_by} em ${formatDateTimeBR(upload.created_at)} (${upload.row_count ?? 0} linha(s), arquivo ${upload.filename})`
  );
  if (month.version_count > month.uploads.length) {
    lines.push(`${month.version_count - month.uploads.length} versão(ões) anterior(es) substituída(s)`);
  }
  return `${periodLabel(month.period)}\n${lines.join("\n")}`;
}

// Células criadas como elementos (nome de usuário e de arquivo são texto de usuário).
function periodCell(month, clickable) {
  const cell = document.createElement(clickable ? "button" : "div");
  if (clickable) cell.type = "button";
  cell.className = `period-cell period-cell--${month.state}`;
  cell.dataset.period = month.period;
  cell.title = periodCellTitle(month);
  const name = document.createElement("strong");
  name.textContent = MONTH_NAMES[Number(month.period.slice(5)) - 1].slice(0, 3);
  const detail = document.createElement("span");
  if (month.state === "sent") {
    const [first] = month.uploads;
    detail.textContent = month.uploads.length > 1
      ? `${month.uploads.length} envios`
      : `${first.uploaded_by} · ${BR_DAY_MONTH.format(new Date(first.created_at))}`;
  } else {
    detail.textContent = PERIOD_STATE_TEXT[month.state] || "";
  }
  cell.append(name, detail);
  if (clickable) {
    cell.addEventListener("click", () => {
      periodChosen = true;
      selectPeriod(month.period);
    });
  }
  return cell;
}

function periodSummary(grid) {
  const missing = grid.months.filter((month) => month.state === "missing").map((month) => month.period);
  const parts = [];
  if (grid.year <= Number(grid.current_period.slice(0, 4))) {
    parts.push(
      missing.length
        ? `Faltam ${missing.length} mês(es) em ${grid.year}: ${missing.map((period) => MONTH_NAMES[Number(period.slice(5)) - 1]).join(", ")}.`
        : `Nenhum mês pendente em ${grid.year}.`
    );
  }
  if (grid.period_source === "column") {
    parts.push(`O mês de cada arquivo sai da coluna "${grid.period_column}".`);
  }
  if (grid.duplicate_policy === "replace") {
    parts.push("Reenviar um mês substitui o anterior, com confirmação.");
  } else if (grid.duplicate_policy === "block") {
    parts.push("Um mês já enviado não aceita outro arquivo.");
  }
  return parts.join(" ");
}

async function loadPeriodGrid() {
  const context = contextsByName[contextSelect.value];
  if (!isMonthly(context)) return;
  const contextName = context.name;
  document.getElementById("period-year").textContent = periodYear;
  try {
    const params = new URLSearchParams({ context_name: contextName, year: periodYear });
    const grid = await apiFetch(`/api/uploads/periods?${params}`);
    if (contextSelect.value !== contextName) return;  // trocou de contexto enquanto carregava
    const clickable = usesPeriodSelector(context);
    document.getElementById("period-grid").replaceChildren(...grid.months.map((month) => periodCell(month, clickable)));
    document.getElementById("period-summary").textContent = periodSummary(grid);
    if (clickable && !periodChosen && grid.year === Number(grid.current_period.slice(0, 4))) {
      const firstMissing = grid.months.find((month) => month.state === "missing");
      selectPeriod(firstMissing ? firstMissing.period : grid.current_period);
    }
    markSelectedCell();
  } catch (err) {
    document.getElementById("period-summary").textContent = `Não foi possível carregar os meses: ${err.message}`;
  }
}

function changePeriodYear(delta) {
  periodYear += delta;
  loadPeriodGrid();
}

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
    nameEl.textContent = `${file.name} (${sizeMb} MB)`;
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
  periodPanel.classList.toggle("hidden", !isMonthly(context));
  periodSelectField.classList.toggle("hidden", !usesPeriodSelector(context));
  periodYear = new Date().getFullYear();
  periodChosen = false;
  if (isMonthly(context)) {
    document.getElementById("period-grid").replaceChildren();
    loadPeriodGrid();
  }
  if (!context) {
    destinationIcon.textContent = "folder_off";
    destinationLabel.textContent = "Escolha um contexto para ver o destino.";
    fileInput.setAttribute("accept", ".xlsx,.xls,.csv,.pdf,.json,.xml,.txt");
    return;
  }

  destinationIcon.textContent = DESTINATION_ICONS[context.destination_type] || "help";
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
      }
      // Sem contexto não há para onde enviar: select vazio e botão desligado.
      contextSelect.innerHTML = '<option value="">Nenhum contexto disponível</option>';
      contextSelect.disabled = true;
      document.getElementById("upload-submit").disabled = true;
      handleContextChange();
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
  return `<span class="status-badge ${isSuccess ? "status-badge--success" : "status-badge--error"}">${isSuccess ? "Sucesso" : "Erro"}</span>`;
}

const LOAD_STATUS_BADGES = {
  pending: ["status-badge--muted", "Banco: pendente"],
  success: ["status-badge--success", "Banco: carregado"],
  error: ["status-badge--error", "Banco: erro"],
  superseded: ["status-badge--muted", "Banco: substituído"],
};

// Envio trocado por outro do mesmo mês: continua no histórico, mas não vale mais.
function supersededBadge(item) {
  return item.superseded_by ? '<span class="status-badge status-badge--muted" title="Outro envio do mesmo mês entrou no lugar deste.">Substituído</span>' : "";
}

function contextCell(item) {
  const period = item.period ? `<div class="text-xs text-muted">${esc(periodLabel(item.period))}</div>` : "";
  return `${esc(item.context_name)}${period}`;
}

// Situação da carga no banco, abaixo do status do envio (só para contextos que carregam no banco).
function loadStatusLine(item) {
  if (!item.load_status) return "";
  const [variant, label] = LOAD_STATUS_BADGES[item.load_status] || ["status-badge--muted", item.load_status];
  const title = item.load_status === "error" ? item.load_error : item.load_detail;
  return `<span class="status-badge ${variant}" title="${esc(title || "")}">${esc(label)}</span>`;
}

// Só o nome do arquivo gravado (a parte mais útil); o caminho completo fica no tooltip.
function destinationCell(detail) {
  if (!detail) return "-";
  const name = detail.split(/[\\/]/).pop();
  return `<span class="font-mono" title="${esc(detail)}">${esc(name)}</span>`;
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
      <p><strong>Contexto:</strong> ${esc(item.context_name)} · <strong>Data:</strong> ${formatDateTimeBR(item.created_at)}</p>
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
        <tr>
          <td data-label="Arquivo" class="px-4 py-2 font-semibold" style="overflow-wrap: anywhere; min-width: 10rem">${esc(item.filename)}</td>
          <td data-label="Contexto" class="px-4 py-2">${contextCell(item)}</td>
          <td data-label="Destino" class="px-4 py-2 hidden lg:table-cell" style="overflow-wrap: anywhere">${destinationCell(item.destination_detail)}</td>
          <td data-label="Status" class="px-4 py-2"><div class="status-stack">${statusBadge(item.status)}${supersededBadge(item)}${loadStatusLine(item)}</div></td>
          <td data-label="Enviado por" class="px-4 py-2 hidden lg:table-cell">${esc(item.uploaded_by)}</td>
          <td data-label="Data" class="px-4 py-2 whitespace-nowrap">${formatDateTimeBR(item.created_at)}</td>
          <td data-label="" class="px-4 py-2 text-right whitespace-nowrap sticky-action">${viewTableAction(item)}</td>
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
  if (usesPeriodSelector(context) && !periodSelect.value) {
    showToast("Escolha o mês de competência do arquivo.", "warning");
    return;
  }
  const buildFormData = (extra) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("context_name", contextName);
    if (usesPeriodSelector(context)) formData.append("period", periodSelect.value);
    Object.entries(extra || {}).forEach(([key, value]) => formData.append(key, value));
    return formData;
  };

  const submitButton = document.getElementById("upload-submit");
  const submitButtonLabel = document.getElementById("upload-submit-label");
  if (submitButton) submitButton.disabled = true;
  if (submitButtonLabel) submitButtonLabel.textContent = "Enviando e validando dados...";

  try {
    // Cada confirmação (colunas diferentes, mês já enviado) reenvia o arquivo com a flag correspondente.
    const flags = {};
    let result;
    while (!result) {
      try {
        result = await submitUpload(buildFormData(flags));
      } catch (error) {
        const detail = error.data?.detail;
        if (error.status === 422 && detail?.violations) {
          showViolationModal(file.name, detail.violations);
          fileInput.value = "";
          await loadHistory();
          return;
        }
        if (error.status === 422 && detail?.kind === "period_error") {
          alertModal({ title: "Mês de competência", body: `<p>${esc(detail.message)}</p>` });
          await loadHistory();
          return;
        }
        if (error.status === 409 && detail?.kind === "period_blocked") {
          alertModal({ title: "Mês já enviado", body: `<p>${esc(detail.message)}</p>` });
          await loadHistory();
          return;
        }
        if (error.status === 409 && detail?.kind === "period_exists") {
          const confirmed = await confirmModal({
            title: `Substituir ${detail.period_label}?`,
            body: `
              <p><strong>${esc(detail.period_label)}</strong> já foi enviado por <strong>${esc(detail.uploaded_by)}</strong>
              em ${formatDateTimeBR(detail.created_at)} (${detail.row_count ?? 0} linha(s)).</p>
              <p class="mt-2">Se continuar, as linhas desse mês serão trocadas pelas deste arquivo. O envio anterior fica no histórico.</p>
            `,
            confirmLabel: "Substituir",
            cancelLabel: "Cancelar",
            variant: "warning",
          });
          if (!confirmed) {
            showToast("Envio cancelado.", "warning");
            return;
          }
          flags.confirm_replace_period = "true";
          continue;
        }
        if (error.status === 409 && detail) {
          const mismatch = detail;
          const confirmed = await confirmModal({
            title: "Colunas diferentes do último envio",
            body: `
              <p>Este arquivo tem colunas diferentes das do último arquivo aceito para este contexto.</p>
              ${mismatch.extra_columns?.length ? `<p class="mt-2">Novas: ${mismatch.extra_columns.map(esc).join(", ")}</p>` : ""}
              ${mismatch.missing_columns?.length ? `<p>Faltando: ${mismatch.missing_columns.map(esc).join(", ")}</p>` : ""}
              <p class="mt-2">Deseja enviar mesmo assim?</p>
            `,
            confirmLabel: "Enviar mesmo assim",
            cancelLabel: "Cancelar",
            variant: "warning",
          });
          if (!confirmed) {
            await submitUpload(buildFormData({ cancelled: "true" }));
            showToast("Envio cancelado.", "warning");
            fileInput.value = "";
            await loadHistory();
            return;
          }
          flags.confirm_mismatch = "true";
          continue;
        }
        throw error;
      }
    }

    const viewLastUploadLink = document.getElementById("view-last-upload-link");
    if (result && result.status === "success") {
      const periodText = result.period ? ` (${periodLabel(result.period)})` : "";
      showToast(`Arquivo enviado com sucesso para ${result.destination_detail || "destino"}${periodText}.`, "positive");
      if (result.artifact_kind === "parquet" && viewLastUploadLink) {
        viewLastUploadLink.href = `/uploads/${result.id}/preview`;
        viewLastUploadLink.classList.remove("hidden");
      }
    } else if (result) {
      showHistoryError(result);
    }
    fileInput.value = "";
    document.getElementById("selected-file-badge")?.classList.add("hidden");
    periodChosen = false;
    await Promise.all([loadHistory(), loadPeriodGrid()]);
  } catch (error) {
    showToast(`Falha ao processar o arquivo: ${error.message || error}`, "negative");
  } finally {
    if (submitButton) submitButton.disabled = false;
    if (submitButtonLabel) submitButtonLabel.textContent = "Enviar arquivo";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  fileInput?.addEventListener("change", () => onFileSelected(fileInput));
  initDragAndDrop();
  fillPeriodSelect();
  periodSelect.addEventListener("change", () => {
    periodChosen = true;
    markSelectedCell();
  });
  document.getElementById("period-prev").addEventListener("click", () => changePeriodYear(-1));
  document.getElementById("period-next").addEventListener("click", () => changePeriodYear(1));
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
