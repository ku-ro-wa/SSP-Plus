// Sign-in form (login.html). POST /login takes JSON (not form-encoded), so
// the form submits via fetch. On success the response sets the session
// cookie and we go to the dashboard.
const form = document.getElementById("login-form");
const errorEl = document.getElementById("login-error");

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button");
    button.disabled = true;
    errorEl.textContent = "";

    try {
        const response = await fetch("/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                username: form.username.value,
                password: form.password.value,
            }),
        });
        if (response.ok) {
            window.location.href = "/accounting";
            return;
        }
        const data = await response.json().catch(() => ({}));
        errorEl.textContent = data.detail || "Sign in failed";
    } catch {
        errorEl.textContent = "Could not reach the dashboard server";
    }
    button.disabled = false;
});
