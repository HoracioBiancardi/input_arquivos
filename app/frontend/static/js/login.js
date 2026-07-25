document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const errorLabel = document.getElementById("error-label");
  errorLabel.textContent = "";

  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;

  try {
    await apiFetch("/api/auth/login", { method: "POST", body: { username, password } });
    window.location.href = "/";
  } catch (error) {
    const detail = error.data && error.data.detail;
    errorLabel.textContent = typeof detail === "string" ? detail : "Usuário ou senha inválidos.";
  }
});
