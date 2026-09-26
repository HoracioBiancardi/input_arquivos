// Mensagens no card de login (= app_template): erro de acesso, saiu, bloqueio por inatividade.
function loginMsg(texto, tipo = "ok") {
  const box = document.getElementById("login-msg");
  box.replaceChildren();
  if (!texto) return;
  const erro = tipo === "erro";
  const alerta = document.createElement("div");
  alerta.className = `alert ${erro ? "alert-error" : "alert-success"} login-msg`;
  alerta.setAttribute("role", erro ? "alert" : "status");
  const icone = document.createElement("span");
  icone.className = "alert-icon ms";
  icone.textContent = erro ? "error" : "check_circle";
  const corpo = document.createElement("div");
  corpo.textContent = texto;
  alerta.append(icone, corpo);
  box.append(alerta);
}

const MOTIVOS = {
  saiu: "Você saiu.",
  inatividade: "Sessão bloqueada por inatividade. Entre novamente.",
  expirou: "Sessão expirada. Entre novamente.",
};
const motivo = new URLSearchParams(window.location.search).get("motivo");
if (MOTIVOS[motivo]) loginMsg(MOTIVOS[motivo]);
document.getElementById(document.getElementById("username").value ? "password" : "username").focus();

document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  loginMsg("");

  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;

  try {
    await apiFetch("/api/auth/login", { method: "POST", body: { username, password } });
    window.location.href = "/";
  } catch (error) {
    const detail = error.data && error.data.detail;
    loginMsg(typeof detail === "string" ? detail : "Usuário ou senha inválidos.", "erro");
    document.getElementById("password").select();
  }
});
