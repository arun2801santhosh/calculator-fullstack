
const API = "http://127.0.0.1:8000";

let project = {};
let budget = [];
let expenses = [];
let forecasts = [];
let costChart = null;
let categoryChart = null;

const $ = id => document.getElementById(id);

function money(value) {
    return Number(value || 0).toLocaleString("en-AE", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function monthLabel(value) {
    if (!value) return "";
    const [year, month] = value.split("-").map(Number);
    return new Date(year, month - 1, 1).toLocaleDateString("en", {
        month: "long",
        year: "numeric"
    });
}

function numberValue(id) {
    return Number($(id).value);
}

async function api(url, options = {}) {
    const response = await fetch(API + url, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {})
        }
    });

    if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Request failed: ${response.status}`);
    }

    if (response.status === 204) return null;
    return response.json();
}

function getMonths() {
    const start = $("startMonth").value;
    const duration = numberValue("duration");

    if (!start || !Number.isInteger(duration) || duration < 1) {
        return [];
    }

    const [year, month] = start.split("-").map(Number);

    return Array.from({ length: duration }, (_, index) => {
        const date = new Date(year, month - 1 + index, 1);
        return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
    });
}

function fillMonthDropdowns() {
    const months = getMonths();
    const dropdowns = [
        $("reportMonth"),
        $("entryMonth"),
        $("forecastMonth")
    ];

    dropdowns.forEach(select => {
        const previousValue = select.value;
        select.innerHTML = "";

        months.forEach(month => {
            const option = document.createElement("option");
            option.value = month;
            option.textContent = monthLabel(month);
            select.appendChild(option);
        });

        if (months.includes(previousValue)) {
            select.value = previousValue;
        }
    });
}

function getSelectedMonth() {
    return $("reportMonth").value;
}

function sumExpenses(categoryId, monthCondition) {
    return expenses
        .filter(item =>
            String(item.category_id) === String(categoryId) &&
            monthCondition(item.month)
        )
        .reduce((total, item) => total + Number(item.amount || 0), 0);
}

function sumForecasts(categoryId, monthCondition) {
    return forecasts
        .filter(item =>
            String(item.category_id) === String(categoryId) &&
            monthCondition(item.month)
        )
        .reduce((total, item) => total + Number(item.amount || 0), 0);
}

function calculateRows() {
    const reportMonth = getSelectedMonth();

    return budget.map((item, index) => {
        const previous = sumExpenses(
            item.id,
            month => month < reportMonth
        );

        const current = sumExpenses(
            item.id,
            month => month === reportMonth
        );

        const remaining = sumForecasts(
            item.id,
            month => month > reportMonth
        );

        const total = previous + current + remaining;
        const difference = total - Number(item.committed_cost);

        return {
            ...item,
            sr: index + 1,
            previous,
            current,
            remaining,
            total,
            difference
        };
    });
}

function renderReport() {
    const rows = calculateRows();
    const body = $("reportBody");
    const foot = $("reportFoot");

    body.innerHTML = "";

    rows.forEach(row => {
        const tr = document.createElement("tr");

        const values = [
            row.sr,
            row.description,
            money(row.tender_budget),
            money(row.initial_finalized),
            money(row.committed_cost),
            money(row.previous),
            money(row.current),
            money(row.remaining),
            money(row.total),
            money(row.difference)
        ];

        values.forEach((value, index) => {
            const td = document.createElement("td");
            td.textContent = value;

            if (index === 9) {
                td.style.color = row.difference > 0 ? "#dc2626" :
                    row.difference < 0 ? "#0f9d75" : "#1e293b";
            }

            tr.appendChild(td);
        });

        const action = document.createElement("td");
        action.textContent = "Fixed";
        action.style.color = "#64748b";
        tr.appendChild(action);

        body.appendChild(tr);
    });

    const totals = rows.reduce((result, row) => {
        [
            "tender_budget",
            "initial_finalized",
            "committed_cost",
            "previous",
            "current",
            "remaining",
            "total",
            "difference"
        ].forEach(key => {
            result[key] += Number(row[key] || 0);
        });

        return result;
    }, {
        tender_budget: 0,
        initial_finalized: 0,
        committed_cost: 0,
        previous: 0,
        current: 0,
        remaining: 0,
        total: 0,
        difference: 0
    });

    foot.innerHTML = `
        <tr>
            <td colspan="2">TOTAL</td>
            <td>${money(totals.tender_budget)}</td>
            <td>${money(totals.initial_finalized)}</td>
            <td>${money(totals.committed_cost)}</td>
            <td>${money(totals.previous)}</td>
            <td>${money(totals.current)}</td>
            <td>${money(totals.remaining)}</td>
            <td>${money(totals.total)}</td>
            <td>${money(totals.difference)}</td>
            <td></td>
        </tr>
    `;

    $("tenderTotal").textContent = "AED " + money(totals.tender_budget);
    $("finalTotal").textContent = "AED " + money(totals.initial_finalized);
    $("committedTotal").textContent = "AED " + money(totals.committed_cost);
    $("forecastTotal").textContent = "AED " + money(totals.total);

    renderCharts(rows, totals);
}

function renderExpenseRecords() {
    const body = $("expenseBody");
    body.innerHTML = "";

    expenses.forEach(item => {
        const category = budget.find(
            row => String(row.id) === String(item.category_id)
        );

        const tr = document.createElement("tr");

        tr.innerHTML = `
            <td>${monthLabel(item.month)}</td>
            <td>${category ? category.description : "Unknown"}</td>
            <td>${money(item.amount)}</td>
        `;

        const action = document.createElement("td");

        const editButton = document.createElement("button");
        editButton.textContent = "Edit";
        editButton.onclick = () => editExpense(item);

        const deleteButton = document.createElement("button");
        deleteButton.textContent = "Delete";
        deleteButton.style.background = "#dc2626";
        deleteButton.style.marginLeft = "6px";
        deleteButton.onclick = () => deleteExpense(item);

        action.append(editButton, deleteButton);
        tr.appendChild(action);
        body.appendChild(tr);
    });
}

function renderForecastRecords() {
    let section = $("forecastRecords");

    if (!section) {
        section = document.createElement("div");
        section.id = "forecastRecords";
        section.innerHTML = `
            <h3>Saved Monthly Forecasts</h3>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Month</th>
                            <th>Description</th>
                            <th>Forecast Amount (AED)</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody id="forecastBody"></tbody>
                </table>
            </div>
        `;
        $("saveForecastBtn").insertAdjacentElement("afterend", section);
    }

    const body = $("forecastBody");
    body.innerHTML = "";

    forecasts.forEach(item => {
        const category = budget.find(
            row => String(row.id) === String(item.category_id)
        );

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${monthLabel(item.month)}</td>
            <td>${category ? category.description : "Unknown"}</td>
            <td>${money(item.amount)}</td>
        `;

        const action = document.createElement("td");

        const editButton = document.createElement("button");
        editButton.textContent = "Edit";
        editButton.onclick = () => editForecast(item);

        const deleteButton = document.createElement("button");
        deleteButton.textContent = "Delete";
        deleteButton.style.background = "#dc2626";
        deleteButton.style.marginLeft = "6px";
        deleteButton.onclick = () => deleteForecast(item);

        action.append(editButton, deleteButton);
        tr.appendChild(action);
        body.appendChild(tr);
    });
}

function fillCategoryDropdowns() {
    ["entryCategory", "forecastCategory"].forEach(id => {
        const select = $(id);
        select.innerHTML = "";

        budget.forEach(item => {
            const option = document.createElement("option");
            option.value = item.id;
            option.textContent = item.description;
            select.appendChild(option);
        });
    });
}

function renderCharts(rows, totals) {
    if (typeof Chart === "undefined") return;

    if (costChart) costChart.destroy();

    costChart = new Chart($("costChart"), {
        type: "bar",
        data: {
            labels: ["Tender Budget", "Finalized", "Committed", "Forecast"],
            datasets: [{
                label: "Amount (AED)",
                data: [
                    totals.tender_budget,
                    totals.initial_finalized,
                    totals.committed_cost,
                    totals.total
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    });

    if (categoryChart) categoryChart.destroy();

    categoryChart = new Chart($("categoryChart"), {
        type: "bar",
        data: {
            labels: rows.map(row => row.description),
            datasets: [{
                label: "Total Forecast (AED)",
                data: rows.map(row => row.total)
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    });
}

async function loadData() {
    try {
        const data = await api("/project");

        project = data.project;
        budget = data.budget;
        expenses = data.expenses || [];
        forecasts = data.forecasts || [];

        $("projectName").value = project.name || "";
        $("projectCode").value = project.code || "";
        $("contractor").value = project.contractor || "";
        $("startMonth").value = project.start_month || "2026-12";
        $("duration").value = project.duration || 20;

        fillMonthDropdowns();

        const reportMonth = project.report_month;
        if (reportMonth && getMonths().includes(reportMonth)) {
            $("reportMonth").value = reportMonth;
        }

        renderAll();

    } catch (error) {
        console.error(error);
        alert("Cannot load project data. Please check that the Python backend is running.");
    }
}

function renderAll() {
    fillCategoryDropdowns();
    renderReport();
    renderExpenseRecords();
    renderForecastRecords();
}

async function saveProject() {
    const payload = {
        name: $("projectName").value.trim(),
        code: $("projectCode").value.trim(),
        contractor: $("contractor").value.trim(),
        start_month: $("startMonth").value,
        duration: numberValue("duration"),
        report_month: getSelectedMonth()
    };

    if (!payload.name || !payload.start_month ||
        !Number.isInteger(payload.duration) || payload.duration < 1) {
        alert("Please enter a project name, start month and valid duration.");
        return;
    }

    try {
        const data = await api("/project", {
            method: "PUT",
            body: JSON.stringify(payload)
        });

        project = data.project;
        budget = data.budget;
        expenses = data.expenses || expenses;
        forecasts = data.forecasts || forecasts;

        fillMonthDropdowns();
        renderAll();
        alert("Project information saved successfully.");

    } catch (error) {
        alert("Could not save project: " + error.message);
    }
}

async function addExpense() {
    const month = $("entryMonth").value;
    const categoryId = $("entryCategory").value;
    const amount = numberValue("actualAmount");

    if (!month || !categoryId || !Number.isFinite(amount) || amount < 0) {
        alert("Please enter a valid month, description and amount.");
        return;
    }

    try {
        await api("/expenses", {
            method: "POST",
            body: JSON.stringify({
                month,
                category_id: Number(categoryId),
                amount
            })
        });

        $("actualAmount").value = "";
        await loadData();
        alert("Monthly actual cost saved.");

    } catch (error) {
        alert("Could not save monthly cost: " + error.message);
    }
}

async function editExpense(item) {
    const answer = prompt("Enter the corrected actual cost (AED):", item.amount);
    if (answer === null) return;

    const amount = Number(answer);

    if (!Number.isFinite(amount) || amount < 0) {
        alert("Please enter a valid amount.");
        return;
    }

    try {
        await api(`/expenses/${item.id}`, {
            method: "PUT",
            body: JSON.stringify({ amount })
        });
        await loadData();
    } catch (error) {
        alert("Could not update cost: " + error.message);
    }
}

async function deleteExpense(item) {
    if (!confirm("Delete this monthly actual cost record?")) return;

    try {
        await api(`/expenses/${item.id}`, { method: "DELETE" });
        await loadData();
    } catch (error) {
        alert("Could not delete cost: " + error.message);
    }
}

async function saveForecast() {
    const month = $("forecastMonth").value;
    const categoryId = $("forecastCategory").value;
    const amount = numberValue("forecastAmount");

    if (!month || !categoryId || !Number.isFinite(amount) || amount < 0) {
        alert("Please enter a valid forecast month, description and amount.");
        return;
    }

    try {
        await api("/forecasts", {
            method: "POST",
            body: JSON.stringify({
                month,
                category_id: Number(categoryId),
                amount
            })
        });

        $("forecastAmount").value = "";
        await loadData();
        alert("Monthly forecast saved.");

    } catch (error) {
        alert("Could not save forecast: " + error.message);
    }
}

async function editForecast(item) {
    const answer = prompt("Enter the corrected forecast amount (AED):", item.amount);
    if (answer === null) return;

    const amount = Number(answer);

    if (!Number.isFinite(amount) || amount < 0) {
        alert("Please enter a valid amount.");
        return;
    }

    try {
        await api(`/forecasts/${item.id}`, {
            method: "PUT",
            body: JSON.stringify({ amount })
        });
        await loadData();
    } catch (error) {
        alert("Could not update forecast: " + error.message);
    }
}

async function deleteForecast(item) {
    if (!confirm("Delete this monthly forecast?")) return;

    try {
        await api(`/forecasts/${item.id}`, { method: "DELETE" });
        await loadData();
    } catch (error) {
        alert("Could not delete forecast: " + error.message);
    }
}

function exportPdf() {
    const month = getSelectedMonth();

    if (!month) {
        alert("Please select a report month first.");
        return;
    }

    window.open(
        `${API}/export-pdf?month=${encodeURIComponent(month)}`,
        "_blank"
    );
}

$("saveProjectBtn").addEventListener("click", saveProject);
$("addCostBtn").addEventListener("click", addExpense);
$("saveForecastBtn").addEventListener("click", saveForecast);
$("exportPdfBtn").addEventListener("click", exportPdf);

$("reportMonth").addEventListener("change", async () => {
    try {
        await api("/project", {
            method: "PUT",
            body: JSON.stringify({
                ...project,
                report_month: getSelectedMonth()
            })
        });
        renderReport();
    } catch (error) {
        console.error("Could not save report month:", error);
        renderReport();
    }
});

$("startMonth").addEventListener("change", fillMonthDropdowns);
$("duration").addEventListener("change", fillMonthDropdowns);

loadData();
