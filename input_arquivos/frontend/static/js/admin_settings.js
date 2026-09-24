const minioForm = document.getElementById("minio-settings-form");
const secretInput = document.getElementById("minio-secret-key");
const secretHint = document.getElementById("minio-secret-hint");
const sourceBadge = document.getElementById("minio-source-badge");

function applySourceBadge(source) {
  const isAdmin = source === "admin";
  sourceBadge.textContent = isAdmin ? "Configurado via admin" : "Usando .env (padrão)";
  sourceBadge.className = "status-badge " + (isAdmin ? "status-badge--success" : "status-badge--muted");
}

async function loadMinioConfig() {
  try {
    const config = await apiFetch("/api/settings/minio");
    document.getElementById("minio-endpoint").value = config.endpoint || "";
    document.getElementById("minio-access-key").value = config.access_key || "";
    document.getElementById("minio-secure").checked = !!config.secure;
    secretInput.value = "";
    secretHint.textContent = config.secret_key_configured
      ? "Já configurada — deixe em branco para manter a atual."
      : "Obrigatória na primeira configuração.";
    applySourceBadge(config.source);
  } catch (err) {
    showToast(`Falha ao carregar configuração: ${err.message}`, "negative");
  }
}

function currentFormValues() {
  return {
    endpoint: document.getElementById("minio-endpoint").value.trim(),
    access_key: document.getElementById("minio-access-key").value.trim(),
    secret_key: secretInput.value,
    secure: document.getElementById("minio-secure").checked,
  };
}

async function testMinioConfig() {
  const values = currentFormValues();
  if (!values.secret_key) {
    showToast("Informe a chave secreta para testar (o teste não usa a chave já salva).", "warning");
    return;
  }
  const resultEl = document.getElementById("minio-test-result");
  resultEl.textContent = "Testando...";
  resultEl.className = "text-xs";
  try {
    const result = await apiFetch("/api/settings/minio/test", { method: "POST", body: values });
    resultEl.textContent = result.message;
    resultEl.className = "text-xs " + (result.success ? "text-green-600" : "text-red-600");
  } catch (err) {
    resultEl.textContent = err.message;
    resultEl.className = "text-xs text-red-600";
  }
}

async function saveMinioConfig(event) {
  event.preventDefault();
  clearFieldErrors("minio");
  const values = currentFormValues();
  try {
    await apiFetch("/api/settings/minio", { method: "PUT", body: values });
    showToast("Configuração do MinIO salva com sucesso.", "positive");
    setTimeout(() => {
      window.location.href = "/admin";
    }, 800);
  } catch (err) {
    const fieldErrors = extractFieldErrors(err.data);
    if (applyFieldErrors("minio", fieldErrors) === 0) {
      showToast(`Falha ao salvar: ${err.message}`, "negative");
    }
  }
}

async function clearMinioConfig() {
  const confirmed = await confirmModal({
    title: "Voltar a usar o .env?",
    body: "<p>A configuração salva pelo admin será removida e a aplicação volta a usar as variáveis do arquivo .env do servidor.</p>",
    confirmLabel: "Remover configuração",
    cancelLabel: "Cancelar",
    variant: "warning",
  });
  if (!confirmed) return;
  try {
    await apiFetch("/api/settings/minio", { method: "DELETE" });
    showToast("Configuração removida — usando .env novamente.", "positive");
    await loadMinioConfig();
  } catch (err) {
    showToast(`Falha ao remover: ${err.message}`, "negative");
  }
}

const databaseForm = document.getElementById("database-settings-form");
const databasePasswordInput = document.getElementById("database-password");

async function loadDatabaseConfig() {
  try {
    const config = await apiFetch("/api/settings/database");
    const badge = document.getElementById("database-status-badge");
    badge.textContent = config.configured ? "Configurado" : "Não configurado";
    badge.className = "status-badge " + (config.configured ? "status-badge--success" : "status-badge--muted");
    document.getElementById("database-host").value = config.host || "";
    document.getElementById("database-port").value = config.port || 1433;
    document.getElementById("database-database").value = config.database || "";
    document.getElementById("database-username").value = config.username || "";
    databasePasswordInput.value = "";
    document.getElementById("database-password-hint").textContent = config.password_configured
      ? "Já configurada — deixe em branco para manter a atual."
      : "Obrigatória na primeira configuração.";
  } catch (err) {
    showToast(`Falha ao carregar conexão do banco: ${err.message}`, "negative");
  }
}

function currentDatabaseValues() {
  return {
    host: document.getElementById("database-host").value.trim(),
    port: Number(document.getElementById("database-port").value) || 1433,
    database: document.getElementById("database-database").value.trim(),
    username: document.getElementById("database-username").value.trim(),
    password: databasePasswordInput.value || null,
  };
}

function toggleDatabasePasswordVis(event) {
  const showing = databasePasswordInput.type === "text";
  databasePasswordInput.type = showing ? "password" : "text";
  event.currentTarget.textContent = showing ? "SHOW" : "HIDE";
}

async function testDatabaseConfig() {
  clearFieldErrors("database");
  const resultEl = document.getElementById("database-test-result");
  resultEl.textContent = "Testando...";
  resultEl.className = "text-xs";
  try {
    const result = await apiFetch("/api/settings/database/test", { method: "POST", body: currentDatabaseValues() });
    resultEl.textContent = result.message;
    resultEl.className = "text-xs " + (result.success ? "text-green-600" : "text-red-600");
  } catch (err) {
    resultEl.textContent = "";
    if (applyFieldErrors("database", extractFieldErrors(err.data)) === 0) {
      resultEl.textContent = err.message;
      resultEl.className = "text-xs text-red-600";
    }
  }
}

async function saveDatabaseConfig(event) {
  event.preventDefault();
  clearFieldErrors("database");
  try {
    await apiFetch("/api/settings/database", { method: "PUT", body: currentDatabaseValues() });
    showToast("Conexão do banco salva com sucesso.", "positive");
    await loadDatabaseConfig();
  } catch (err) {
    if (applyFieldErrors("database", extractFieldErrors(err.data)) === 0) {
      showToast(`Falha ao salvar: ${err.message}`, "negative");
    }
  }
}

async function clearDatabaseConfig() {
  const confirmed = await confirmModal({
    title: "Remover conexão do banco?",
    body: "<p>Os contextos com carga no banco continuam gravando no MinIO, mas a carga das tabelas passa a falhar até uma nova conexão ser configurada.</p>",
    confirmLabel: "Remover conexão",
    cancelLabel: "Cancelar",
    variant: "warning",
  });
  if (!confirmed) return;
  try {
    await apiFetch("/api/settings/database", { method: "DELETE" });
    showToast("Conexão do banco removida.", "positive");
    await loadDatabaseConfig();
  } catch (err) {
    showToast(`Falha ao remover: ${err.message}`, "negative");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadMinioConfig();
  loadDatabaseConfig();
  document.getElementById("database-test-button").addEventListener("click", testDatabaseConfig);
  document.getElementById("database-clear-button").addEventListener("click", clearDatabaseConfig);
  document.getElementById("database-password-toggle").addEventListener("click", toggleDatabasePasswordVis);
  databaseForm.addEventListener("submit", saveDatabaseConfig);
  document.getElementById("minio-test-button").addEventListener("click", testMinioConfig);
  document.getElementById("minio-clear-button").addEventListener("click", clearMinioConfig);
  minioForm.addEventListener("submit", saveMinioConfig);
});
