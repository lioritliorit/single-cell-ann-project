const state = {
    indexStatus: null,
    datasets: [],
    activeDatasetId: null,
    cellTypeChart: null,
    pcaChart: null,
    pcaData: null,
};

const $ = (id) => document.getElementById(id);

const searchForm = $("search-form");
const cellIdInput = $("cell-id-input");
const kInput = $("k-input");
const searchModeSelect = $("search-mode-select");
const filterCellType = $("filter-cell-type");
const filterDisease = $("filter-disease");
const filterDatasetGroup = $("filter-dataset-group");
const searchBtn = $("search-btn");
const loading = $("loading");
const queryInfo = $("query-info");
const queryTime = $("query-time");
const queryCount = $("query-count");
const queryCellId = $("query-cell-id");
const filterStats = $("filter-stats");
const statsTotal = $("stats-total");
const statsFiltered = $("stats-filtered");
const statsRatio = $("stats-ratio");
const statsMode = $("stats-mode");
const resultsContainer = $("results-container");
const resultsBody = $("results-body");
const errorMsg = $("error-msg");
const errorText = $("error-text");

document.addEventListener("DOMContentLoaded", async () => {
    setupNavigation();
    setupIndexSwitch();
    setupDatasetControls();
    await refreshAll();
});

async function refreshAll() {
    await loadDatasets();
    await loadIndexStatus();
    await loadCellTypes();
    await loadVisualizationData();
    await loadEvaluationData();
}

function setupNavigation() {
    const sections = document.querySelectorAll("section[id]");
    const navLinks = document.querySelectorAll(".nav-link");

    function setActive(id) {
        navLinks.forEach((link) => {
            link.classList.toggle("active", link.getAttribute("href") === "#" + id);
        });
    }

    navLinks.forEach((link) => {
        link.addEventListener("click", () => {
            const id = link.getAttribute("href")?.replace("#", "");
            if (id) setActive(id);
        });
    });

    const observer = new IntersectionObserver((entries) => {
        for (const entry of entries) {
            if (entry.isIntersecting) {
                setActive(entry.target.id);
                break;
            }
        }
    }, { rootMargin: "-20% 0px -60% 0px" });

    sections.forEach((section) => observer.observe(section));
}

async function apiGet(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw await readApiError(resp);
    return resp.json();
}

async function apiPost(url, data) {
    const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
    });
    if (!resp.ok) throw await readApiError(resp);
    return resp.json();
}

async function apiDelete(url) {
    const resp = await fetch(url, { method: "DELETE" });
    if (!resp.ok) throw await readApiError(resp);
    return resp.json();
}

async function readApiError(resp) {
    const data = await resp.json().catch(() => ({}));
    return new Error(data.message || data.error || `HTTP ${resp.status}`);
}

async function loadIndexStatus() {
    try {
        const data = await apiGet("/api/index/status");
        state.indexStatus = data;

        $("badge-cells").innerHTML = `<i class="fas fa-hashtag"></i> ${formatNumber(data.cell_count || 0)} 细胞`;
        $("badge-dim").innerHTML = `<i class="fas fa-vector-square"></i> ${data.dimension || "-"} 维`;
        $("badge-status").innerHTML = `<i class="fas fa-circle" style="color:#4caf50;"></i> 已就绪`;
        $("badge-engine").innerHTML = `<i class="fas fa-microchip"></i> ${(data.current_index_type || "faiss").toUpperCase()}`;

        $("stat-cell-count").textContent = formatNumber(data.cell_count || 0);
        $("stat-dimension").textContent = data.dimension || "-";
        $("stat-index-total").textContent = formatNumber(data.index_total || 0);
        $("stat-index-type").textContent = (data.current_index_type || "faiss").toUpperCase();
        $("stat-active-dataset").textContent = data.active_dataset?.name || data.active_dataset_id || "-";
        $("index-status-loading").style.display = "none";
        $("index-status-content").style.display = "block";

        const extraParams = $("stat-extra-params");
        if (data.current_index_type === "hnsw" && data.M) {
            extraParams.style.display = "block";
            $("stat-extra-value").textContent = `M=${data.M}, ef=${data.ef}`;
            $("stat-extra-label").textContent = "HNSW 参数";
        } else {
            extraParams.style.display = "none";
        }

        updateSwitchBtnText(data.current_index_type || "faiss");
    } catch (err) {
        $("badge-cells").innerHTML = `<i class="fas fa-circle" style="color:#f44336;"></i> 加载失败`;
        $("badge-dim").textContent = "无法连接";
        $("badge-status").innerHTML = `<i class="fas fa-exclamation-triangle" style="color:#f44336;"></i> 离线`;
        $("badge-engine").innerHTML = `<i class="fas fa-microchip"></i> ?`;
    }
}

function setupIndexSwitch() {
    $("switch-index-btn").addEventListener("click", switchIndex);
}

async function switchIndex() {
    const btn = $("switch-index-btn");
    const statusEl = $("switch-status");
    const previousType = state.indexStatus?.current_index_type || "faiss";
    const targetType = previousType === "faiss" ? "hnsw" : "faiss";

    btn.disabled = true;
    statusEl.textContent = "切换中...";
    statusEl.style.color = "#666";

    try {
        await apiPost("/api/index/switch", { index_type: targetType });
        statusEl.textContent = `已切换到 ${targetType.toUpperCase()}`;
        statusEl.style.color = "#2e7d32";
        await loadIndexStatus();
    } catch (err) {
        statusEl.textContent = `切换失败: ${err.message}`;
        statusEl.style.color = "#c62828";
        updateSwitchBtnText(previousType);
    } finally {
        btn.disabled = false;
        setTimeout(() => { statusEl.textContent = ""; }, 4000);
    }
}

function updateSwitchBtnText(currentType) {
    $("switch-btn-text").textContent = currentType === "faiss" ? "切换到 HNSW" : "切换到 FAISS";
}

function setupDatasetControls() {
    $("dataset-upload-form").addEventListener("submit", uploadDataset);
    $("build-joint-btn").addEventListener("click", buildJointIndex);
}

async function loadDatasets() {
    const data = await apiGet("/api/datasets");
    state.datasets = data.datasets || [];
    state.activeDatasetId = data.active_dataset_id;
    renderDatasets();
}

function renderDatasets() {
    const body = $("datasets-body");
    body.innerHTML = "";

    if (!state.datasets.length) {
        body.innerHTML = `<tr><td colspan="9" style="text-align:center; color:#999; padding:32px;">暂无数据集</td></tr>`;
        return;
    }

    state.datasets.forEach((ds) => {
        const tr = document.createElement("tr");
        const isActive = ds.id === state.activeDatasetId;
        const canDelete = ds.id !== "default";
        const typeLabels = (ds.cell_types || []).slice(0, 3).join(", ");
        const diseaseLabels = (ds.diseases || []).slice(0, 3).join(", ");
        const activeBadge = isActive ? `<span class="cell-type-tag">活动</span>` : "";
        const stale = ds.stale ? `<span class="dataset-stale">需重建</span>` : "";

        tr.innerHTML = `
            <td><input type="checkbox" class="dataset-check" value="${escapeHtml(ds.id)}" ${isActive ? "checked" : ""}></td>
            <td>${activeBadge} ${stale}</td>
            <td><strong>${escapeHtml(ds.name || ds.id)}</strong><div class="form-text">${escapeHtml(ds.id)}</div></td>
            <td>${escapeHtml(groupLabel(ds.group))}</td>
            <td>${escapeHtml(ds.source || "-")}</td>
            <td>${formatNumber(ds.cell_count || 0)}</td>
            <td title="${escapeHtml((ds.cell_types || []).join(", "))}">${escapeHtml(typeLabels || "-")}</td>
            <td title="${escapeHtml((ds.diseases || []).join(", "))}">${escapeHtml(diseaseLabels || "-")}</td>
            <td>
                <button class="btn btn-outline btn-sm" data-action="switch" data-id="${escapeHtml(ds.id)}" ${isActive ? "disabled" : ""}>
                    <i class="fas fa-toggle-on"></i> 切换
                </button>
                <button class="btn btn-outline btn-sm btn-danger" data-action="delete" data-id="${escapeHtml(ds.id)}" ${canDelete ? "" : "disabled"}>
                    <i class="fas fa-trash"></i> 删除
                </button>
            </td>
        `;
        body.appendChild(tr);
    });

    body.querySelectorAll("button[data-action='switch']").forEach((btn) => {
        btn.addEventListener("click", () => switchDataset(btn.dataset.id));
    });
    body.querySelectorAll("button[data-action='delete']").forEach((btn) => {
        btn.addEventListener("click", () => deleteDataset(btn.dataset.id));
    });
}

async function uploadDataset(event) {
    event.preventDefault();
    const file = $("dataset-file").files[0];
    if (!file) {
        showDatasetMessage("请先选择 .h5ad 文件。", "error");
        return;
    }

    const btn = $("dataset-upload-btn");
    const formData = new FormData();
    formData.append("file", file);
    formData.append("name", $("dataset-name").value.trim());
    formData.append("group", $("dataset-group").value);
    formData.append("source", $("dataset-source").value.trim());
    formData.append("description", $("dataset-description").value.trim());
    formData.append("tags", $("dataset-tags").value.trim());

    btn.disabled = true;
    showDatasetMessage("正在上传、解析 h5ad 并构建 FAISS 索引...", "info");

    try {
        const resp = await fetch("/api/datasets/upload", { method: "POST", body: formData });
        if (!resp.ok) throw await readApiError(resp);
        const data = await resp.json();
        showDatasetMessage(`已导入数据集：${data.dataset.name}`, "success");
        $("dataset-upload-form").reset();
        await refreshAll();
    } catch (err) {
        showDatasetMessage(err.message, "error");
    } finally {
        btn.disabled = false;
    }
}

async function switchDataset(datasetId) {
    showDatasetMessage("正在切换数据集并加载索引...", "info");
    try {
        await apiPost("/api/datasets/switch", { dataset_id: datasetId });
        showDatasetMessage("数据集已切换。", "success");
        clearSearchResults();
        await refreshAll();
    } catch (err) {
        showDatasetMessage(err.message, "error");
    }
}

async function deleteDataset(datasetId) {
    if (!window.confirm(`确认删除数据集 ${datasetId} 及其索引文件？`)) return;
    showDatasetMessage("正在删除数据集和索引缓存...", "info");
    try {
        await apiDelete(`/api/datasets/${encodeURIComponent(datasetId)}`);
        showDatasetMessage("数据集已删除。", "success");
        clearSearchResults();
        await refreshAll();
    } catch (err) {
        showDatasetMessage(err.message, "error");
    }
}

async function buildJointIndex() {
    const selected = Array.from(document.querySelectorAll(".dataset-check:checked")).map((item) => item.value);
    if (selected.length < 2) {
        showDatasetMessage("请至少选择两个数据集。", "error");
        return;
    }

    const name = `Joint ${selected.join(" + ")}`;
    showDatasetMessage("正在合并向量并构建联合 FAISS 索引...", "info");
    try {
        await apiPost("/api/datasets/joint-index", {
            dataset_ids: selected,
            name,
            group: "joint",
            description: "Web UI generated joint index",
        });
        showDatasetMessage("联合索引已构建并切换为活动数据集。", "success");
        clearSearchResults();
        await refreshAll();
    } catch (err) {
        showDatasetMessage(err.message, "error");
    }
}

function showDatasetMessage(message, type) {
    const el = $("dataset-message");
    const className = type === "error" ? "alert alert-error" : type === "success" ? "alert alert-success" : "alert alert-warning";
    el.className = className;
    el.innerHTML = `<i class="fas fa-info-circle"></i> <span>${escapeHtml(message)}</span>`;
    el.style.display = "flex";
}

async function loadCellTypes() {
    try {
        const data = await apiGet("/api/cell-types");
        const types = data.cell_types || [];
        filterCellType.innerHTML = `<option value="">全部类型</option>`;
        types.forEach((ct) => {
            const opt = document.createElement("option");
            opt.value = ct;
            opt.textContent = ct;
            filterCellType.appendChild(opt);
        });
    } catch (err) {
        console.warn("Failed to load cell types:", err);
    }

    // 同时加载疾病类型
    try {
        const data = await apiGet("/api/disease-types");
        const types = data.disease_types || [];
        filterDisease.innerHTML = `<option value="">全部状态</option>`;
        types.forEach((dt) => {
            const opt = document.createElement("option");
            opt.value = dt;
            opt.textContent = dt;
            filterDisease.appendChild(opt);
        });
    } catch (err) {
        console.warn("Failed to load disease types:", err);
    }
}

async function loadVisualizationData() {
    try {
        const data = await apiGet("/api/visualization-data");
        state.pcaData = data;
        renderCellTypeChart(data);
        renderPCAScatter(data);
    } catch (err) {
        console.warn("Failed to load visualization data:", err);
    }
}

function renderCellTypeChart(data) {
    const ctx = $("cell-type-chart").getContext("2d");
    const items = (data.cell_type_counts || []).sort((a, b) => b.count - a.count).slice(0, 15);
    const colors = [
        "#1565c0", "#2e7d32", "#e65100", "#6a1b9a", "#00838f",
        "#c62828", "#558b2f", "#283593", "#ad1457", "#00695c",
        "#b71c1c", "#1b5e20", "#4a148c", "#f57f17", "#455a64",
    ];

    if (state.cellTypeChart) state.cellTypeChart.destroy();
    state.cellTypeChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: items.map((d) => d.cell_type),
            datasets: [{
                label: "细胞数量",
                data: items.map((d) => d.count),
                backgroundColor: colors.slice(0, items.length),
                borderRadius: 4,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            responsiveAnimationDuration: 0,
            indexAxis: "y",
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { display: false } },
                y: { grid: { display: false }, ticks: { font: { size: 10 } } },
            },
        },
    });
}

function renderPCAScatter(data) {
    const ctx = $("pca-scatter").getContext("2d");
    const points = data.pca_points || [];
    const palette = [
        "#1565c0", "#2e7d32", "#e65100", "#6a1b9a", "#00838f",
        "#c62828", "#558b2f", "#283593", "#ad1457", "#00695c",
        "#f57f17", "#455a64", "#5d4037", "#00796b", "#c2185b",
    ];
    const groups = {};

    points.forEach((point) => {
        const ct = point.cell_type || "unknown";
        if (!groups[ct]) {
            groups[ct] = {
                label: ct,
                data: [],
                backgroundColor: palette[Object.keys(groups).length % palette.length],
                hidden: false,
            };
        }
        groups[ct].data.push({ x: point.pc1, y: point.pc2 });
    });

    if (state.pcaChart) state.pcaChart.destroy();
    state.pcaChart = new Chart(ctx, {
        type: "scatter",
        data: { datasets: Object.values(groups) },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            responsiveAnimationDuration: 0,
            animation: false,
            plugins: {
                legend: {
                    display: true,
                    position: "right",
                    labels: { boxWidth: 12, padding: 8, font: { size: 9 }, filter: (item) => item.datasetIndex < 20 },
                },
            },
            scales: {
                x: { title: { display: true, text: "PC1", font: { size: 11 } }, grid: { display: false } },
                y: { title: { display: true, text: "PC2", font: { size: 11 } }, grid: { display: false } },
            },
            elements: { point: { radius: 2, hoverRadius: 4 } },
        },
    });

    initCellTypeFilterViz(points);
}

function initCellTypeFilterViz(points) {
    const select = $("cell-type-filter-viz");
    select.innerHTML = `<option value="">全部类型</option>`;
    [...new Set(points.map((p) => p.cell_type || "unknown"))].sort().forEach((type) => {
        const opt = document.createElement("option");
        opt.value = type;
        opt.textContent = type;
        select.appendChild(opt);
    });
    select.onchange = () => {
        const selected = select.value;
        state.pcaChart.data.datasets.forEach((dataset) => {
            dataset.hidden = selected !== "" && dataset.label !== selected;
        });
        state.pcaChart.update();
    };
}

searchForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const cellId = cellIdInput.value.trim();
    const k = parseInt(kInput.value, 10) || 10;
    if (!cellId) {
        showError("请输入细胞 ID");
        return;
    }

    hideError();
    resultsContainer.style.display = "none";
    queryInfo.style.display = "none";
    filterStats.style.display = "none";
    loading.style.display = "block";
    searchBtn.disabled = true;

    try {
        const filters = {};
        if (filterCellType.value) filters.cell_type = filterCellType.value;
        if (filterDisease.value) filters.disease = filterDisease.value;
        if (filterDatasetGroup.value) filters.dataset_group = filterDatasetGroup.value;

        const searchMode = searchModeSelect.value || "normal";
        const payload = { cell_id: cellId, k, search_mode: searchMode };
        if (Object.keys(filters).length) payload.filters = filters;
        const data = await apiPost("/api/search", payload);

        queryTime.textContent = data.elapsed_ms;
        queryCount.textContent = data.result_count;
        queryCellId.textContent = cellId;
        $("engine-info").textContent = `${(data.index_type || "?").toUpperCase()} / ${data.dataset?.name || ""}`;
        queryInfo.style.display = "block";

        // 显示过滤统计
        if (data.filter_stats) {
            const fs = data.filter_stats;
            statsTotal.textContent = formatNumber(fs.total_cells || 0);
            statsFiltered.textContent = formatNumber(fs.filtered_cells || 0);
            statsRatio.textContent = ((fs.filter_ratio || 0) * 100).toFixed(1) + "%";
            statsMode.textContent = fs.mode || data.search_mode || "-";
            filterStats.style.display = "block";
        }

        renderWarnings(data.warnings || []);
        renderResults(data.results || []);
        resultsContainer.style.display = "block";
        highlightQueryCell(data);
    } catch (err) {
        showError(err.message);
    } finally {
        loading.style.display = "none";
        searchBtn.disabled = false;
    }
});

function renderWarnings(warnings) {
    const warningEl = $("search-warnings");
    if (!warnings.length) {
        warningEl.style.display = "none";
        warningEl.innerHTML = "";
        return;
    }
    warningEl.innerHTML = warnings.map((warning) =>
        `<div class="alert alert-warning"><i class="fas fa-exclamation-circle"></i> ${escapeHtml(warning)}</div>`
    ).join("");
    warningEl.style.display = "block";
}

function renderResults(results) {
    resultsBody.innerHTML = "";
    if (!results.length) {
        resultsBody.innerHTML = `<tr><td colspan="11" style="text-align:center; color:#999; padding:32px;">未找到结果</td></tr>`;
        return;
    }

    results.forEach((result, index) => {
        const tr = document.createElement("tr");
        const expression = result.expression || {};
        tr.innerHTML = `
            <td class="rank-cell">${index + 1}</td>
            <td>${escapeHtml(result.dataset_name || result.metadata?.dataset_name || "-")}</td>
            <td><code>${escapeHtml(result.cell_id || "-")}</code></td>
            <td><span class="cell-type-tag">${escapeHtml(result.cell_type || "-")}</span></td>
            <td>${formatDistance(result.distance)}</td>
            <td>${escapeHtml(result.disease || "-")}</td>
            <td>${escapeHtml(result.metadata?.donor_age || "-")}</td>
            <td>${escapeHtml(result.metadata?.sex || "-")}</td>
            <td>${formatOptionalNumber(expression.nCount_RNA, 1)}</td>
            <td>${formatOptionalNumber(expression.nFeature_RNA, 1)}</td>
            <td>${formatOptionalNumber(expression.percent_mt, 2)}</td>
        `;
        resultsBody.appendChild(tr);
    });
}

function highlightQueryCell(data) {
    if (!state.pcaChart || !state.pcaData) return;
    state.pcaChart.data.datasets = state.pcaChart.data.datasets.filter((ds) => ds.label !== "查询细胞");

    const rowIdx = data.query?.row_index;
    const pcaPoint = Number.isInteger(rowIdx) ? state.pcaData.pca_points[rowIdx] : null;
    if (!pcaPoint) return;

    state.pcaChart.data.datasets.push({
        label: "查询细胞",
        data: [{ x: pcaPoint.pc1, y: pcaPoint.pc2 }],
        backgroundColor: "#f44336",
        pointRadius: 8,
        pointBorderColor: "#fff",
        pointBorderWidth: 2,
        order: -1,
    });
    state.pcaChart.update();
}

function clearSearchResults() {
    queryInfo.style.display = "none";
    filterStats.style.display = "none";
    resultsContainer.style.display = "none";
    hideError();
}

function showError(message) {
    errorText.textContent = message;
    errorMsg.style.display = "flex";
}

function hideError() {
    errorMsg.style.display = "none";
}

function formatNumber(value) {
    return Number(value || 0).toLocaleString();
}

function formatDistance(value) {
    return value === null || value === undefined ? "-" : Number(value).toFixed(4);
}

function formatOptionalNumber(value, digits) {
    return value === null || value === undefined ? "-" : Number(value).toFixed(digits);
}

function groupLabel(value) {
    const labels = { regular: "常规", liver_disease: "肝病", joint: "联合" };
    return labels[value] || value || "-";
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

let buildTimeChart = null;
let queryTimeChart = null;
let recallChart = null;
let memoryChart = null;

async function loadEvaluationData() {
    try {
        const data = await apiGet("/api/evaluation-data");
        renderEvaluationCharts(data);
        renderEvaluationTable(data);
        $("evaluation-loading").style.display = "none";
        $("evaluation-content").style.display = "block";
    } catch (err) {
        console.warn("Failed to load evaluation data:", err);
        $("evaluation-loading").innerHTML = `<p><i class="fas fa-exclamation-triangle"></i> 无法加载评测数据</p>`;
    }
}

function renderEvaluationCharts(data) {
    const evaluations = data.evaluations || [];
    const datasetLabels = evaluations.map(d => d.dataset_name || d.dataset_id);
    const methodColors = {
        "faiss_flat": "#1565c0",
        "faiss_ivfflat": "#2e7d32",
        "faiss_ivfpq": "#e65100",
        "faiss_hnsw": "#6a1b9a",
        "hnsw_self": "#c62828"
    };
    const methodDisplayNames = {
        "faiss_flat": "FAISS_Flat",
        "faiss_ivfflat": "FAISS_IVFFlat",
        "faiss_ivfpq": "FAISS_IVFPQ",
        "faiss_hnsw": "FAISS_HNSW",
        "hnsw_self": "HNSW_self"
    };

    // Build time chart - compare methods across datasets
    const buildCtx = $("build-time-chart").getContext("2d");
    if (buildTimeChart) buildTimeChart.destroy();
    const methods = ["faiss_flat", "faiss_ivfflat", "faiss_ivfpq", "faiss_hnsw", "hnsw_self"];
    buildTimeChart = new Chart(buildCtx, {
        type: "bar",
        data: {
            labels: datasetLabels,
            datasets: methods.map((methodKey) => {
                return {
                    label: methodDisplayNames[methodKey],
                    data: evaluations.map(ds => {
                        const metrics = ds.metrics || {};
                        return (metrics[methodKey]?.build_time) || 0;
                    }),
                    backgroundColor: methodColors[methodKey],
                    borderRadius: 4,
                };
            }),
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: true, position: "right" } },
            scales: {
                y: { title: { display: true, text: "构建时间 (s)" }, beginAtZero: true },
            },
        },
    });

    // Query time chart
    const queryCtx = $("query-time-chart").getContext("2d");
    if (queryTimeChart) queryTimeChart.destroy();
    queryTimeChart = new Chart(queryCtx, {
        type: "bar",
        data: {
            labels: datasetLabels,
            datasets: methods.map((methodKey) => {
                return {
                    label: methodDisplayNames[methodKey],
                    data: evaluations.map(ds => {
                        const metrics = ds.metrics || {};
                        return (metrics[methodKey]?.search_time) || 0;
                    }),
                    backgroundColor: methodColors[methodKey],
                    borderRadius: 4,
                };
            }),
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: true, position: "right" } },
            scales: {
                y: { title: { display: true, text: "查询时间 (s)" }, beginAtZero: true },
            },
        },
    });

    // Recall chart - K=10
    const recallCtx = $("recall-chart").getContext("2d");
    if (recallChart) recallChart.destroy();
    recallChart = new Chart(recallCtx, {
        type: "bar",
        data: {
            labels: datasetLabels,
            datasets: methods.map((methodKey) => {
                return {
                    label: methodDisplayNames[methodKey],
                    data: evaluations.map(ds => {
                        const metrics = ds.metrics || {};
                        return (metrics[methodKey]?.recall) || 0;
                    }),
                    backgroundColor: methodColors[methodKey],
                    borderRadius: 4,
                };
            }),
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: true, position: "right" } },
            scales: {
                y: { title: { display: true, text: "召回率" }, min: 0, max: 1 },
            },
        },
    });

    // Memory chart
    const memoryCtx = $("memory-chart").getContext("2d");
    if (memoryChart) memoryChart.destroy();
    memoryChart = new Chart(memoryCtx, {
        type: "bar",
        data: {
            labels: datasetLabels,
            datasets: methods.map((methodKey) => {
                return {
                    label: methodDisplayNames[methodKey],
                    data: evaluations.map(ds => {
                        const metrics = ds.metrics || {};
                        const mem = (metrics[methodKey]?.memory_mb) || 0;
                        return mem >= 0 ? mem : 0; // 过滤掉负数
                    }),
                    backgroundColor: methodColors[methodKey],
                    borderRadius: 4,
                };
            }),
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: true, position: "right" } },
            scales: {
                y: { title: { display: true, text: "内存 (MB)" }, beginAtZero: true },
            },
        },
    });
}

function renderEvaluationTable(data) {
    const tbody = $("evaluation-table-body");
    tbody.innerHTML = "";
    const evaluations = data.evaluations || [];

    if (!evaluations.length) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#999; padding:32px;">暂无评测数据</td></tr>`;
        return;
    }

    evaluations.forEach((ds) => {
        const metrics = ds.metrics || {};
        const methods = ["faiss_flat", "faiss_ivfflat", "faiss_ivfpq", "faiss_hnsw", "hnsw_self"];
        methods.forEach((methodKey, idx) => {
            const result = metrics[methodKey];
            if (!result) return;
            const tr = document.createElement("tr");
            const mem = (result?.memory_mb) || 0;
            tr.innerHTML = `
                <td>${idx === 0 ? `<strong>${escapeHtml(ds.dataset_name || ds.dataset_id)}</strong>` : ""}</td>
                <td>${escapeHtml(result?.method || "-")}</td>
                <td>${formatOptionalNumber(result?.build_time, 4)}</td>
                <td>${formatOptionalNumber(result?.search_time, 4)}</td>
                <td>${formatOptionalNumber(mem >= 0 ? mem : 0, 2)}</td>
                <td>${formatOptionalNumber(result?.recall, 4)}</td>
                <td>${formatOptionalNumber(result?.precision, 4)}</td>
            `;
            tbody.appendChild(tr);
        });
    });
}
