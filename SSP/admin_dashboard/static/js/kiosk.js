// Kiosk page edits (kiosk.html), loaded only for the admin role: paper,
// coins, ink, Collect cash, mark resolved, owed payments refunded in cash.
async function send(url, body) {
    const response = await fetch(url, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body || {}),
    });
    let data = {};
    try { data = await response.json(); } catch (e) {}
    return {ok: response.ok, status: response.status, data};
}
function say(name, ok, text) {
    const el = document.querySelector(`[data-msg="${name}"]`);
    el.className = "msg " + (ok ? "ok" : "bad");
    el.textContent = text;
}
function failure(result) {
    return result.data.error || ("Could not save (" + result.status + ").");
}
const done = (name) => { say(name, true, "Saved."); setTimeout(() => location.reload(), 700); };

document.querySelectorAll("form[data-edit]").forEach((form) => {
    const name = form.dataset.edit;
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const values = Object.fromEntries(new FormData(form).entries());
        const [url, body] = {
            paper: ["/kiosk/paper", {count: values.count}],
            coins: ["/kiosk/coins", values],
            ink: ["/kiosk/ink", {levels: values}],
        }[name];
        const result = await send(url, body);
        result.ok ? done(name) : say(name, false, failure(result));
    });
    form.querySelectorAll("[data-refill]").forEach((button) => {
        button.addEventListener("click", async () => {
            const result = await send(button.dataset.refill);
            result.ok ? done(name) : say(name, false, failure(result));
        });
    });
});

document.querySelectorAll("[data-resolve]").forEach((button) => {
    button.addEventListener("click", async () => {
        button.disabled = true;
        const result = await send(`/errors/${button.dataset.resolve}/resolve`);
        if (result.ok) location.reload();
        else { button.disabled = false; button.textContent = failure(result); }
    });
});

document.querySelectorAll("[data-owed-cash]").forEach((button) => {
    button.addEventListener("click", async () => {
        if (!confirm("Record that the attendant paid this back in cash?")) return;
        button.disabled = true;
        const result = await send(`/kiosk/owed/${button.dataset.owedCash}/refunded-in-cash`);
        if (result.ok) location.reload();
        else { button.disabled = false; button.textContent = failure(result); }
    });
});

document.getElementById("collect-cash-button").addEventListener("click", async () => {
    const preview = await (await fetch("/kiosk/collect-cash/preview")).json();
    const lines = preview.items.map((i) => `₱${i.denomination} ${i.type === "bill" ? "bills" : "coins"}: ${i.count}`);
    const total = preview.total.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    const text = "Record these counts and set every count to 0?\n\n" + lines.join("\n") +
        `\n\nTotal: ₱${total}\n\nCoin counts are what is in the machine now, including the hoppers' stock. ` +
        "With the coins at 0 the kiosk gives no change until you enter the hopper counts after refilling.";
    if (!confirm(text)) return;
    const result = await send("/kiosk/collect-cash", {expected_total: preview.total});
    if (result.ok) { say("collect", true, "Collection #" + result.data.collection_id + " recorded."); setTimeout(() => location.reload(), 1200); }
    else say("collect", false, failure(result));
});
