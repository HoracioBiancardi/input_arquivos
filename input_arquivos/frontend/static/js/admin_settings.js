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
    const config = await apiFetch("/api/settings/minio", { method: "PUT", body: values });
    showToast("Configuração do MinIO salva com sucesso.", "positive");
    secretInput.value = "";
    secretHint.textContent = "Já configurada — deixe em branco para manter a atual.";
    applySourceBadge(config.source);
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

document.addEventListener("DOMContentLoaded", () => {
  loadMinioConfig();
  document.getElementById("minio-test-button").addEventListener("click", testMinioConfig);
  document.getElementById("minio-clear-button").addEventListener("click", clearMinioConfig);
  minioForm.addEventListener("submit", saveMinioConfig);
});
