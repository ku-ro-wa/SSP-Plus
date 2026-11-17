// Settings page (settings.html), admin role only: save, with per-field errors.
document.getElementById("settings-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const values = {};
    for (const input of e.target.querySelectorAll("input")) values[input.name] = input.value;
    for (const el of e.target.querySelectorAll(".err")) el.hidden = true;
    for (const el of e.target.querySelectorAll("input")) el.classList.remove("invalid");
    const msg = document.getElementById("msg");
    const response = await fetch("/settings", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({values}),
    });
    if (response.ok) { msg.className = "ok"; msg.textContent = "Saved."; return; }
    msg.className = "bad";
    if (response.status === 422) {
        const {errors} = await response.json();
        for (const [key, text] of Object.entries(errors)) {
            const row = document.querySelector(`.field[data-key="${key}"]`);
            if (!row) continue;
            row.querySelector("input").classList.add("invalid");
            const err = row.querySelector(".err"); err.textContent = text; err.hidden = false;
        }
        msg.textContent = "Nothing was saved. Fix the marked fields.";
    } else {
        msg.textContent = "Could not save (" + response.status + ").";
    }
});
