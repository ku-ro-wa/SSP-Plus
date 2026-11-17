// Accounting page (accounting.html): range filter, chart and tables.
// The first render's data, from a JSON block the CSP doesn't execute.
const initialSources = JSON.parse(document.getElementById("initial-sources").textContent);
let sourceChart;

function renderRows(sources) {
    const tbody = document.getElementById("summary-body");
    tbody.innerHTML = "";
    sources.forEach((row) => {
        const tr = document.createElement("tr");

        const sourceCell = document.createElement("td");
        sourceCell.className = "source";
        sourceCell.textContent = row.source;

        const revenueCell = document.createElement("td");
        revenueCell.className = "numeric";
        revenueCell.textContent = "₱" + row.revenue.toFixed(2);

        const countCell = document.createElement("td");
        countCell.className = "numeric";
        countCell.textContent = row.transaction_count;

        tr.append(sourceCell, revenueCell, countCell);
        tbody.appendChild(tr);
    });
}

function renderVouchers(vouchers) {
    const peso = (value) => "₱" + value.toFixed(2);
    document.getElementById("change-dispensed").textContent = peso(vouchers.change_dispensed);
    document.getElementById("voucher-issued").textContent = peso(vouchers.voucher_issued);
    document.getElementById("voucher-applied").textContent = peso(vouchers.voucher_applied);
    document.getElementById("voucher-liability").textContent = peso(vouchers.liability);
    document.getElementById("interrupted-owed").textContent = peso(vouchers.interrupted_owed);
}

function renderChart(sources) {
    const labels = sources.map((row) => row.source);
    const revenue = sources.map((row) => row.revenue);
    const counts = sources.map((row) => row.transaction_count);

    if (sourceChart) {
        sourceChart.data.labels = labels;
        sourceChart.data.datasets[0].data = revenue;
        sourceChart.data.datasets[1].data = counts;
        sourceChart.update();
        return;
    }

    sourceChart = new Chart(document.getElementById("source-chart"), {
        type: "bar",
        data: {
            labels,
            datasets: [
                { label: "Revenue (₱)", data: revenue, backgroundColor: "#000", yAxisID: "y" },
                { label: "Transactions", data: counts, backgroundColor: "#999", yAxisID: "y1" },
            ],
        },
        options: {
            responsive: true,
            scales: {
                y: { beginAtZero: true, position: "left" },
                y1: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false } },
            },
        },
    });
}

async function loadRange(range) {
    const response = await fetch(`/accounting/data?range=${range}`);
    // Session timed out while the page was open — send them back to sign in.
    if (response.status === 401) {
        window.location.href = "/login";
        return;
    }
    if (!response.ok) return;
    const data = await response.json();
    renderRows(data.sources);
    renderChart(data.sources);
    renderVouchers(data.vouchers);

    document.querySelectorAll(".filter-btn").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.range === range);
    });
}

document.querySelectorAll(".filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => loadRange(btn.dataset.range));
});

renderChart(initialSources);
