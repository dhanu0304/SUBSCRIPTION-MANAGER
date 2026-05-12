if (window.lucide) {
    window.lucide.createIcons();
}

const sidebar = document.querySelector(".sidebar");
const menuToggle = document.querySelector(".menu-toggle");

if (menuToggle && sidebar) {
    menuToggle.addEventListener("click", () => sidebar.classList.toggle("open"));
}

Chart.defaults.color = "#a9b4c7";
Chart.defaults.borderColor = "rgba(255,255,255,0.08)";
Chart.defaults.font.family = "Inter";

const chartDataElement = document.getElementById("chart-data");
const chartData = chartDataElement ? JSON.parse(chartDataElement.textContent) : {};
const serviceLabels = chartData.service_labels || [];
const serviceValues = chartData.service_values || [];
const categoryLabels = chartData.category_labels || [];
const categoryValues = chartData.category_values || [];
const trendLabels = chartData.trend_labels || ["Jan", "Feb", "Mar", "Apr", "May", "Jun"];
const trendValues = chartData.trend_values || [];
const bankMonthLabels = chartData.bank_month_labels || [];
const bankMonthValues = chartData.bank_month_values || [];
const palette = ["#ff3131", "#22c55e", "#38bdf8", "#a855f7", "#fb7185", "#f59e0b"];

const makeGradient = (ctx, top, bottom) => {
    const gradient = ctx.createLinearGradient(0, 0, 0, 260);
    gradient.addColorStop(0, top);
    gradient.addColorStop(1, bottom);
    return gradient;
};

const spendingChart = document.getElementById("spendingChart");
if (spendingChart) {
    const ctx = spendingChart.getContext("2d");
    new Chart(ctx, {
        type: "line",
        data: {
            labels: trendLabels,
            datasets: [{
                label: "Spending",
                data: trendValues,
                fill: true,
                tension: 0.42,
                borderWidth: 3,
                pointRadius: 4,
                borderColor: "#38bdf8",
                backgroundColor: makeGradient(ctx, "rgba(56,189,248,0.35)", "rgba(168,85,247,0.02)")
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true, ticks: { callback: value => `Rs. ${value}` } } }
        }
    });
}

const barChart = document.getElementById("barChart");
if (barChart) {
    new Chart(barChart, {
        type: "bar",
        data: {
            labels: serviceLabels,
            datasets: [{
                label: "Cost",
                data: serviceValues,
                backgroundColor: palette,
                borderRadius: 12
            }]
        },
        options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
    });
}

const pieChart = document.getElementById("pieChart");
if (pieChart) {
    new Chart(pieChart, {
        type: "doughnut",
        data: {
            labels: categoryLabels,
            datasets: [{
                data: categoryValues,
                backgroundColor: palette,
                borderWidth: 0,
                hoverOffset: 8
            }]
        },
        options: { cutout: "68%", plugins: { legend: { position: "bottom" } } }
    });
}

const trendChart = document.getElementById("trendChart");
if (trendChart) {
    new Chart(trendChart, {
        type: "line",
        data: {
            labels: trendLabels,
            datasets: [{
                label: "Trend",
                data: trendValues,
                borderColor: "#a855f7",
                backgroundColor: "rgba(168,85,247,0.18)",
                fill: true,
                tension: 0.45
            }]
        },
        options: { plugins: { legend: { display: false } } }
    });
}

const bankChart = document.getElementById("bankChart");
if (bankChart) {
    new Chart(bankChart, {
        type: "bar",
        data: {
            labels: bankMonthLabels,
            datasets: [{
                label: "Spent",
                data: bankMonthValues,
                backgroundColor: ["#38bdf8", "#a855f7", "#22c55e", "#fb7185", "#f59e0b"],
                borderRadius: 12
            }]
        },
        options: {
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true, ticks: { callback: value => `Rs. ${value}` } } }
        }
    });
}
