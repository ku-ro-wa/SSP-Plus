// Logs page (logs.html), admin role only: Mark resolved on the error log.
document.querySelectorAll("[data-resolve]").forEach((button) => {
    button.addEventListener("click", async () => {
        button.disabled = true;
        const response = await fetch(`/errors/${button.dataset.resolve}/resolve`, {method: "POST"});
        if (response.ok) location.reload();
        else { button.disabled = false; button.textContent = "Could not save (" + response.status + ")"; }
    });
});
