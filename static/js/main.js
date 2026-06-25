/* ================================================================
   单细胞 ANN 检索系统 — 前端主脚本
   成员5：交互可视化与项目交付
   ================================================================ */

// ===== State =====
const state = {
    indexStatus: null,
    datasets: [],
    activeDatasetId: null,
    cellTypeChart: null,
    pcaData: null,
    umapData: null,
    plotlyChart: null,
    currentVizView: 'pca',
    selectedPoint: null,
    authToken: null,
    currentUser: null,
    // Chart instances for performance evaluation
    buildTimeChart: null,
    queryTimeChart: null,
    recallChart: null,
    memoryChart: null,
};

const $ = (id) => document.getElementById(id);

// DOM refs — search
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

// ===== Init =====
document.addEventListener("DOMContentLoaded", async () => {
    setupNavigation();
    setupIndexSwitch();
    setupDatasetControls();
    setupAuthUI();
    setupVizControls();
    setupRAG();
    await refreshAll();
    await checkAuth();
});

async function refreshAll() {
    await loadDatasets();
    await loadIndexStatus();
    await loadCellTypes();
    await loadVisualizationData();
    await loadDynamicPerformanceEvaluation();
}

// ===== Navigation =====
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

// ===== API Helpers =====
async function apiGet(url) {
    const resp = await fetch(url, { headers: authHeaders() });
    if (!resp.ok) throw await readApiError(resp);
    return resp.json();
}

async function apiPost(url, data) {
    const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(data),
    });
    if (!resp.ok) throw await readApiError(resp);
    return resp.json();
}

async function apiDelete(url) {
    const resp = await fetch(url, { method: "DELETE", headers: authHeaders() });
    if (!resp.ok) throw await readApiError(resp);
    return resp.json();
}

function authHeaders() {
    const headers = {};
    if (state.authToken) {
        headers["Authorization"] = `Bearer ${state.authToken}`;
    }
    return headers;
}

async function readApiError(resp) {
    const data = await resp.json().catch(() => ({}));
    return new Error(data.message || data.error || `HTTP ${resp.status}`);
}

// ===== Auth =====
function setupAuthUI() {
    $("login-btn").addEventListener("click", (e) => { e.preventDefault(); openModal("login-modal"); });
    $("register-btn").addEventListener("click", (e) => { e.preventDefault(); openModal("register-modal"); });
    $("logout-btn").addEventListener("click", (e) => { e.preventDefault(); logout(); });

    $("login-form").addEventListener("submit", handleLogin);
    $("register-form").addEventListener("submit", handleRegister);

    document.querySelectorAll(".modal-close").forEach((btn) => {
        btn.addEventListener("click", () => closeModal(btn.dataset.modal));
    });
    document.querySelectorAll(".modal-backdrop").forEach((el) => {
        el.addEventListener("click", () => {
            const modal = el.closest(".modal");
            if (modal) closeModal(modal.id);
        });
    });
}

function openModal(id) {
    document.getElementById(id).style.display = "flex";
}

function closeModal(id) {
    document.getElementById(id).style.display = "none";
}

async function checkAuth() {
    const token = localStorage.getItem("auth_token");
    if (!token) { updateAuthUI(null); return; }
    state.authToken = token;
    try {
        const data = await apiGet("/api/auth/me");
        state.currentUser = data.user;
        updateAuthUI(data.user);
    } catch {
        state.authToken = null;
        localStorage.removeItem("auth_token");
        updateAuthUI(null);
    }
}

function updateAuthUI(user) {
    if (user) {
        $("user-display").style.display = "inline-flex";
        $("user-name").textContent = user.username + (user.role === "admin" ? " (管理员)" : "");
        $("login-btn").style.display = "none";
        $("register-btn").style.display = "none";
    } else {
        $("user-display").style.display = "none";
        $("login-btn").style.display = "inline";
        $("register-btn").style.display = "inline";
    }
}

async function handleLogin(e) {
    e.preventDefault();
    const username = $("login-username").value.trim();
    const password = $("login-password").value;
    const errEl = $("login-error");
    errEl.style.display = "none";

    try {
        const data = await apiPost("/api/auth/login", { username, password });
        state.authToken = data.token;
        state.currentUser = data.user;
        localStorage.setItem("auth_token", data.token);
        updateAuthUI(data.user);
        closeModal("login-modal");
        $("login-form").reset();
        await refreshAll();
    } catch (err) {
        errEl.textContent = err.message;
        errEl.style.display = "flex";
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const username = $("register-username").value.trim();
    const password = $("register-password").value;
    const email = $("register-email").value.trim();
    const errEl = $("register-error");
    const successEl = $("register-success");
    errEl.style.display = "none";
    successEl.style.display = "none";

    try {
        await apiPost("/api/auth/register", { username, password, email });
        successEl.textContent = "注册成功，请登录。";
        successEl.style.display = "flex";
        $("register-form").reset();
        setTimeout(() => { closeModal("register-modal"); }, 1500);
    } catch (err) {
        errEl.textContent = err.message;
        errEl.style.display = "flex";
    }
}

async function logout() {
    try {
        await apiPost("/api/auth/logout", {});
    } catch {}
    state.authToken = null;
    state.currentUser = null;
    localStorage.removeItem("auth_token");
    updateAuthUI(null);
}

// ===== Dynamic Performance Evaluation =====
async function loadDynamicPerformanceEvaluation() {
    const tableBody = $("evaluation-table-body");
    const loadingIndicator = $("evaluation-loading");
    const contentContainer = $("evaluation-content");

    if (tableBody) tableBody.innerHTML = "";
    if (loadingIndicator) loadingIndicator.style.display = "block";
    if (contentContainer) contentContainer.style.display = "none"; // Hide content while loading

    try {
        const data = await apiGet("/api/performance-evaluation");
        renderPerformanceEvaluationTable(data.evaluation_results, data.dataset_id);
        if (contentContainer) contentContainer.style.display = "block"; // Show content after loading
        renderPerformanceCharts(data.evaluation_results, data.dataset_id);
    } catch (err) {
        console.error("Failed to load dynamic performance evaluation:", err);
        if (tableBody) tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#f44336;">加载性能评测失败: ${escapeHtml(err.message)}</td></tr>`;
    } finally {
        if (loadingIndicator) loadingIndicator.style.display = "none";
    }
}

function renderPerformanceEvaluationTable(results, datasetId) {
    const tableBody = $("evaluation-table-body");
    if (!tableBody) return;

    tableBody.innerHTML = "";

    if (Object.keys(results).length === 0) {
        tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#999; padding:32px;">暂无性能评测数据</td></tr>`;
        return;
    }

    for (const methodKey in results) {
        const metrics = results[methodKey];
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td><strong>${escapeHtml(datasetId)}</strong></td>
            <td>${escapeHtml(metrics.method || methodKey)}</td>
            <td>${metrics.build_time.toFixed(4)}</td>
            <td>${metrics.search_time.toFixed(4)}</td>
            <td>${metrics.memory_mb.toFixed(2)}</td>
            <td>${metrics.recall.toFixed(4)}</td>
            <td>${metrics.precision.toFixed(4)}</td>
        `;
        tableBody.appendChild(tr);
        }
}

function renderPerformanceCharts(results, datasetId) {
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
    const methods = Object.keys(results);

    // Helper to destroy existing chart if it exists
    const destroyChart = (chart) => { if (chart) chart.destroy(); return null; };

    // Build Time Chart
    state.buildTimeChart = destroyChart(state.buildTimeChart);
    state.buildTimeChart = new Chart($("build-time-chart").getContext("2d"), {
        type: "bar",
        data: {
            labels: methods.map(m => methodDisplayNames[m] || m),
            datasets: [{
                label: `构建时间 (${escapeHtml(datasetId)})`,
                data: methods.map(m => results[m]?.build_time || 0),
                backgroundColor: methods.map(m => methodColors[m] || '#9e9e9e'),
                borderRadius: 4,
            }],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { title: { display: true, text: "构建时间 (s)" }, beginAtZero: true } },
            layout: { padding: { right: 16 } },
        },
    });

    // Query Time Chart
    state.queryTimeChart = destroyChart(state.queryTimeChart);
    state.queryTimeChart = new Chart($("query-time-chart").getContext("2d"), {
        type: "bar",
        data: {
            labels: methods.map(m => methodDisplayNames[m] || m),
            datasets: [{
                label: `查询时间 (${escapeHtml(datasetId)})`,
                data: methods.map(m => results[m]?.search_time || 0),
                backgroundColor: methods.map(m => methodColors[m] || '#9e9e9e'),
                borderRadius: 4,
            }],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { title: { display: true, text: "查询时间 (s)" }, beginAtZero: true } },
            layout: { padding: { right: 16 } },
        },
    });

    // Recall Chart
    state.recallChart = destroyChart(state.recallChart);
    state.recallChart = new Chart($("recall-chart").getContext("2d"), {
        type: "bar",
        data: {
            labels: methods.map(m => methodDisplayNames[m] || m),
            datasets: [{
                label: `召回率 (${escapeHtml(datasetId)})`,
                data: methods.map(m => results[m]?.recall || 0),
                backgroundColor: methods.map(m => methodColors[m] || '#9e9e9e'),
                borderRadius: 4,
            }],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { title: { display: true, text: "召回率" }, min: 0, max: 1 } },
            layout: { padding: { right: 16 } },
        },
    });

    // Memory Chart
    state.memoryChart = destroyChart(state.memoryChart);
    state.memoryChart = new Chart($("memory-chart").getContext("2d"), {
        type: "bar",
        data: {
            labels: methods.map(m => methodDisplayNames[m] || m),
            datasets: [{
                label: `内存占用 (${escapeHtml(datasetId)})`,
                data: methods.map(m => results[m]?.memory_mb || 0),
                backgroundColor: methods.map(m => methodColors[m] || '#9e9e9e'),
                borderRadius: 4,
            }],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { title: { display: true, text: "内存 (MB)" }, beginAtZero: true } },
            layout: { padding: { right: 16 } },
        },
    });
}

// ===== Index Status =====
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

// ===== Dataset Management =====
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
        const resp = await fetch("/api/datasets/upload", {
            method: "POST",
            body: formData,
            headers: authHeaders(),
        });
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

// ===== Cell Type / Disease Filters =====
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

// ===== Search =====
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
    if (!state.plotlyChart) return;
    const rowIdx = data.query?.row_index;
    const points = state.currentVizView === 'umap' ? state.umapData : state.pcaData;
    if (!points || !Number.isInteger(rowIdx) || rowIdx >= points.length) return;
    const pt = points[rowIdx];

    Plotly.addTraces('plotly-scatter', {
        x: [pt.x],
        y: [pt.y],
        mode: 'markers',
        type: 'scattergl',
        name: '查询细胞',
        marker: { size: 16, color: '#f44336', symbol: 'star', line: { color: '#fff', width: 2 } },
        hoverinfo: 'skip',
    });
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

// ===== Interactive Visualization (Plotly) =====
function setupVizControls() {
    // PCA/UMAP tab switching
    document.querySelectorAll(".viz-tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            const view = tab.dataset.view;
            if (view === 'umap' && state.umapData.length === 0) {
                // Show message but stay on PCA
                const plotDiv = $("plotly-scatter");
                plotDiv.innerHTML = '<div style="text-align:center;padding:100px 20px;color:#999;">' +
                    '<i class="fas fa-info-circle" style="font-size:2rem;display:block;margin-bottom:12px;"></i>' +
                    '<p>当前数据集没有 UMAP 降维数据。</p>' +
                    '<p style="font-size:0.85rem;margin-top:8px;">请先运行 <code>python scripts/dataset_analysis.py generate-viz --all</code> 生成降维数据。</p>' +
                    '</div>';
                return;
            }
            document.querySelectorAll(".viz-tab").forEach((t) => t.classList.remove("active"));
            tab.classList.add("active");
            state.currentVizView = view;
            renderPlotlyChart();
        });
    });

    // Color mode change
    $("viz-color-mode").addEventListener("change", () => renderPlotlyChart());

    // Cell type filter
    $("cell-type-filter-viz").addEventListener("change", () => renderPlotlyChart());

    // Reset view
    $("viz-reset-btn").addEventListener("click", () => {
        if (state.plotlyChart) {
            Plotly.relayout('plotly-scatter', {
                'xaxis.autorange': true,
                'yaxis.autorange': true,
            });
        }
    });

    // Search selected cell
    $("search-selected-btn").addEventListener("click", () => {
        if (state.selectedPoint) {
            cellIdInput.value = state.selectedPoint.customdata ||
                state.selectedPoint.cell_id || "";
            document.querySelector('a[href="#search"]')?.click();
            searchForm.dispatchEvent(new Event("submit"));
        }
    });
}

async function loadVisualizationData() {
    try {
        const data = await apiGet("/api/visualization-data");
        state.pcaData = data.pca_points || [];
        state.umapData = data.umap_points || [];

        // Populate viz cell type filter
        const typeSet = new Set();
        state.pcaData.forEach((p) => { if (p.cell_type) typeSet.add(p.cell_type); });
        const typeSelect = $("cell-type-filter-viz");
        typeSelect.innerHTML = `<option value="">全部类型</option>`;
        [...typeSet].sort().forEach((ct) => {
            const opt = document.createElement("option");
            opt.value = ct;
            opt.textContent = ct;
            typeSelect.appendChild(opt);
        });

        // Render Plotly chart
        renderPlotlyChart();

        // Render charts & liver stats
        renderCellTypeChart(data);
        renderLiverStats(data);

    } catch (err) {
        console.warn("Failed to load visualization data:", err);
    }
}

function getCurrentVizPoints() {
    return state.currentVizView === 'umap' && state.umapData.length > 0
        ? state.umapData
        : state.pcaData;
}

function getCurrentVizLabel() {
    if (state.currentVizView === 'umap' && state.umapData.length > 0) return 'UMAP';
    return 'PC';
}

function renderPlotlyChart() {
    const points = getCurrentVizPoints();
    if (!points || points.length === 0) {
        $("plotly-scatter").innerHTML = '<p style="text-align:center;padding:80px;color:#999;">暂无数据</p>';
        return;
    }

    const colorMode = $("viz-color-mode").value;
    const typeFilter = $("cell-type-filter-viz").value;
    
    // Filter points
    let filtered = points;
    if (typeFilter) {
        filtered = points.filter((p) => p.cell_type === typeFilter);
    }
    if (filtered.length === 0) {
        $("plotly-scatter").innerHTML = '<p style="text-align:center;padding:80px;color:#999;">所选类型无数据</p>';
        return;
    }
    
    // 语义一致的颜色映射表 - 确保相同语义的类别在不同着色模式下颜色一致
    const semanticColorMap = {
        // 正常/健康相关
        'normal': '#2e7d32',
        'Normal': '#2e7d32',
        'healthy': '#2e7d32',
        'control': '#2e7d32',
        
        // 疾病相关 - 红色系
        'cirrhosis': '#c62828',
        'Cirrhosis': '#c62828',
        'fibrosis': '#e65100',
        'Fibrosis': '#e65100',
        'hepatitis': '#ad1457',
        'Hepatitis': '#ad1457',
        'hcc': '#c2185b',
        'HCC': '#c2185b',
        'carcinoma': '#c2185b',
        
        // 数据分组
        'regular': '#1565c0',
        'Regular': '#1565c0',
        'liver_disease': '#c62828',
        'Liver Disease': '#c62828',
        'joint': '#6a1b9a',
        'Joint': '#6a1b9a',
        
        // 常见细胞类型
        'hepatocyte': '#1565c0',
        'Hepatocyte': '#1565c0',
        'kupffer cell': '#2e7d32',
        'Kupffer Cell': '#2e7d32',
        't cell': '#e65100',
        'T Cell': '#e65100',
        'b cell': '#6a1b9a',
        'B Cell': '#6a1b9a',
        'nk cell': '#00838f',
        'NK Cell': '#00838f',
        'natural killer cell': '#00838f',
        'cholangiocyte': '#558b2f',
        'Cholangiocyte': '#558b2f',
        'macrophage': '#283593',
        'Macrophage': '#283593',
        'neutrophil': '#00695c',
        'Neutrophil': '#00695c',
        'dendritic cell': '#f57f17',
        'Dendritic Cell': '#f57f17',
        'plasma cell': '#455a64',
        'Plasma Cell': '#455a64',
        'hematopoietic stem cell': '#5d4037',
        'Hematopoietic Stem Cell': '#5d4037',
        
        // 未知/其他
        'unknown': '#9e9e9e',
        '未知': '#9e9e9e',
    };
    
    // 默认调色板（用于语义映射表中没有的类别）
    const defaultPalette = [
        '#1565c0', '#2e7d32', '#e65100', '#6a1b9a', '#00838f',
        '#c62828', '#558b2f', '#283593', '#ad1457', '#00695c',
        '#f57f17', '#455a64', '#5d4037', '#00796b', '#c2185b',
        '#689f38', '#4527a0', '#ef6c00', '#4e342e', '#546e7a',
    ];
    
    const colorKey = colorMode;
    const categories = [...new Set(filtered.map((p) => p[colorKey] || "未知"))].sort();
    
    // 为当前着色模式的所有类别分配颜色
    const categoryColors = {};
    let defaultColorIndex = 0;
    for (const cat of categories) {
        // 先尝试精确匹配
        if (semanticColorMap[cat]) {
            categoryColors[cat] = semanticColorMap[cat];
        } else {
            // 尝试不区分大小写匹配
            const lowerCat = cat.toLowerCase();
            const matchedKey = Object.keys(semanticColorMap).find(
                key => key.toLowerCase() === lowerCat
            );
            if (matchedKey) {
                categoryColors[cat] = semanticColorMap[matchedKey];
            } else {
                // 使用默认调色板
                categoryColors[cat] = defaultPalette[defaultColorIndex % defaultPalette.length];
                defaultColorIndex++;
            }
        }
    }
    
    const traces = [];
    let i = 0;
    for (const cat of categories) {
        const catPoints = filtered.filter((p) => (p[colorKey] || "未知") === cat);
        const isLiver = cat === 'liver_disease' || cat === 'Liver Disease';
        traces.push({
            x: catPoints.map((p) => p.x),
            y: catPoints.map((p) => p.y),
            mode: 'markers',
            type: 'scattergl',
            name: cat,
            marker: {
                size: isLiver ? 5 : 3,
                color: categoryColors[cat],
                opacity: 0.7,
                line: isLiver ? { color: '#ff1744', width: 1 } : undefined,
            },
            text: catPoints.map((p) =>
                `细胞: ${p.cell_id || '-'}<br>` +
                `类型: ${p.cell_type || '-'}<br>` +
                `疾病: ${p.disease || '-'}<br>` +
                `分组: ${p.dataset_group || '-'}<br>` +
                `数据集: ${p.dataset_name || '-'}`
            ),
            hoverinfo: 'text',
            customdata: catPoints.map((p) => p.cell_id || ''),
            ids: catPoints.map((_, idx) => `pt-${i}-${idx}`),
            selectedpoints: [],
        });
        i++;
    }

    const layout = {
        dragmode: 'lasso',
        hovermode: 'closest',
        margin: { l: 40, r: 40, t: 20, b: 40 },
        showlegend: true,
        legend: {
            x: 1.02,
            y: 1,
            xanchor: 'left',
            font: { size: 9 },
            itemsizing: 'constant',
        },
        xaxis: {
            title: getCurrentVizLabel() + '1',
            gridcolor: '#f0f0f0',
            zeroline: false,
        },
        yaxis: {
            title: getCurrentVizLabel() + '2',
            gridcolor: '#f0f0f0',
            zeroline: false,
        },
        paper_bgcolor: '#fafafa',
        plot_bgcolor: '#fafafa',
        clickmode: 'event+select',
    };

    const config = {
        responsive: true,
        displayModeBar: true,
        modeBarButtonsToRemove: ['sendDataToCloud', 'toImage'],
        modeBarButtonsToAdd: [{
            name: '框选检索',
            icon: Plotly.Icons.selection,
            click: function(gd) {
                const selected = gd.selectedData || [];
                if (selected.length === 0) return;
                // Pick the first selected point
                const pt = selected[0];
                if (pt && pt.customdata) {
                    cellIdInput.value = pt.customdata;
                    showSelectedPointInfo(pt);
                }
            }
        }],
        displaylogo: false,
        scrollZoom: true,
    };

    const plotDiv = $("plotly-scatter");
    Plotly.newPlot(plotDiv, traces, layout, config).then(() => {
        state.plotlyChart = plotDiv;

        // Click handler: select cell
        plotDiv.on('plotly_click', (data) => {
            if (data.points && data.points.length > 0) {
                const pt = data.points[0];
                if (pt.customdata) {
                    cellIdInput.value = pt.customdata;
                    showSelectedPointInfo(pt);
                }
            }
        });

        // Lasso/box select handler
        plotDiv.on('plotly_selected', (data) => {
            const points = data.points || [];
            if (points.length === 0) {
                $("selected-point-info").style.display = "none";
                return;
            }
            // Show info for first selected point
            const pt = points[0];
            if (pt && pt.customdata) {
                cellIdInput.value = pt.customdata;
                showSelectedPointInfo(pt);
            }
        });
    });
}

function showSelectedPointInfo(pt) {
    state.selectedPoint = pt;
    $("selected-cell-id").textContent = pt.customdata || "-";
    $("selected-cell-type").textContent = pt.data?.name || (pt.text || "").split("<br>")[1]?.replace("类型: ", "") || "-";
    const textLines = (pt.text || "").split("<br>");
    $("selected-disease").textContent = textLines[2]?.replace("疾病: ", "") || "-";
    $("selected-dataset").textContent = textLines[4]?.replace("数据集: ", "") || "-";
    $("selected-point-info").style.display = "flex";
}

// ===== Cell Type Distribution Chart =====
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

// ===== Liver Disease Stats =====
function renderLiverStats(data) {
    const container = $("liver-stats-container");
    const points = data.pca_points || [];

    // Count by disease
    const diseaseCounts = {};
    const groupCounts = {};
    points.forEach((p) => {
        const d = p.disease || "未知";
        diseaseCounts[d] = (diseaseCounts[d] || 0) + 1;
        const g = p.dataset_group || "未知";
        groupCounts[g] = (groupCounts[g] || 0) + 1;
    });

    const diseaseTotal = Object.entries(diseaseCounts)
        .filter(([k]) => k !== "未知" && k !== "normal" && k !== "")
        .reduce((sum, [, v]) => sum + v, 0);

    const normalCount = diseaseCounts["normal"] || diseaseCounts["Normal"] || 0;
    const liverGroupCount = groupCounts["liver_disease"] || 0;
    const total = points.length;

    container.innerHTML = "";

    const cards = [
        { icon: 'fa-dna', iconClass: 'total', label: '总细胞数', value: formatNumber(total) },
        { icon: 'fa-heart', iconClass: 'normal', label: '正常细胞', value: formatNumber(normalCount) },
        { icon: 'fa-exclamation-triangle', iconClass: 'liver', label: '肝病相关细胞', value: formatNumber(diseaseTotal) },
        { icon: 'fa-database', iconClass: 'liver', label: '肝病数据集细胞', value: formatNumber(liverGroupCount) },
    ];

    if (diseaseTotal > 0) {
        cards.push({
            icon: 'fa-percentage',
            iconClass: 'liver',
            label: '肝病细胞占比',
            value: ((diseaseTotal / Math.max(total, 1)) * 100).toFixed(1) + '%',
        });
    }

    cards.forEach((c) => {
        const card = document.createElement("div");
        card.className = "liver-stat-card";
        card.innerHTML = `
            <div class="liver-stat-icon ${c.iconClass}"><i class="fas ${c.icon}"></i></div>
            <div class="liver-stat-info">
                <div class="liver-stat-value">${c.value}</div>
                <div class="liver-stat-label">${c.label}</div>
            </div>
        `;
        container.appendChild(card);
    });
}

// ===== RAG Query =====
function setupRAG() {
    $("rag-form").addEventListener("submit", handleRAGQuery);

    // Click example queries
    document.querySelectorAll(".rag-examples code").forEach((el) => {
        el.addEventListener("click", () => {
            $("rag-query").value = el.textContent;
        });
    });
}

async function handleRAGQuery(e) {
    e.preventDefault();
    const question = $("rag-query").value.trim();
    if (!question) {
        showRAGError("请输入查询语句");
        return;
    }

    const k = parseInt($("rag-k").value, 10) || 5;
    const provider = $("rag-provider").value;
    const apiKey = $("rag-api-key").value.trim();

    $("rag-result").style.display = "none";
    $("rag-error").style.display = "none";
    $("rag-loading").style.display = "block";
    $("rag-btn").disabled = true;

    try {
        const payload = { question, k };
        if (provider && apiKey) {
            payload.provider = provider;
            payload.provider_api_key = apiKey;
        }
        const data = await apiPost("/api/rag/query", payload);
        $("rag-loading").style.display = "none";

        // Show parsed result
        const parsed = data.parsed_filters || {};
        $("rag-original-query").textContent = question;
        $("rag-mode").textContent = data.mode || "rag_placeholder";
        $("rag-parsed-cell-type").textContent = parsed.cell_type || "—";
        $("rag-parsed-disease").textContent = parsed.disease || "—";
        $("rag-parsed-group").textContent = parsed.dataset_group || "—";

        const rec = data.recommended_search_request || {};
        $("rag-search-mode").textContent = rec.search_mode || "—";

        $("rag-result").style.display = "block";

        // Show AI answer
        const answerBox = $("rag-answer-box");
        if (data.answer) {
            $("rag-answer-text").textContent = data.answer;
            answerBox.style.display = "block";
        } else {
            answerBox.style.display = "none";
        }

        // Show summary
        const summaryBox = $("rag-summary-box");
        if (data.summary) {
            const s = data.summary;
            const grid = $("rag-summary-grid");
            grid.innerHTML = `
                <div class="rag-summary-item">
                    <span class="rag-summary-label">主要细胞类型</span>
                    <span class="rag-summary-value">${escapeHtml(s.top_cell_type || "-")}</span>
                </div>
                <div class="rag-summary-item">
                    <span class="rag-summary-label">类型分布</span>
                    <span class="rag-summary-value">${escapeHtml(s.cell_type_distribution || "-")}</span>
                </div>
                <div class="rag-summary-item">
                    <span class="rag-summary-label">疾病分布</span>
                    <span class="rag-summary-value">${escapeHtml(s.disease_distribution || "-")}</span>
                </div>
                <div class="rag-summary-item">
                    <span class="rag-summary-label">最优细胞</span>
                    <span class="rag-summary-value">${escapeHtml(s.top_result_id || "-")}</span>
                </div>
            `;
            summaryBox.style.display = "block";
        } else {
            summaryBox.style.display = "none";
        }

        // Show search results
        const searchRes = data.search_result;
        if (searchRes && searchRes.results && searchRes.results.length > 0) {
            renderRAGResults(searchRes.results);
            $("rag-results-container").style.display = "block";
            $("rag-result-info").textContent =
                `查询耗时: ${searchRes.elapsed_ms || 0}ms | 结果数: ${searchRes.result_count || 0}`;
        } else {
            $("rag-results-container").style.display = "none";
        }

        // Show LLM note
        const msgEl = $("rag-message");
        if (data.llm_note) {
            msgEl.innerHTML = `<i class="fas fa-info-circle"></i> ${escapeHtml(data.llm_note)}`;
            msgEl.style.display = "block";
        } else {
            msgEl.style.display = "none";
        }

    } catch (err) {
        $("rag-loading").style.display = "none";
        showRAGError(err.message);
    } finally {
        $("rag-btn").disabled = false;
    }
}

function renderRAGResults(results) {
    const body = $("rag-results-body");
    body.innerHTML = "";
    results.forEach((r, idx) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td class="rank-cell">${idx + 1}</td>
            <td>${escapeHtml(r.dataset_name || r.metadata?.dataset_name || "-")}</td>
            <td><code>${escapeHtml(r.cell_id || "-")}</code></td>
            <td><span class="cell-type-tag">${escapeHtml(r.cell_type || "-")}</span></td>
            <td>${formatDistance(r.distance)}</td>
            <td>${escapeHtml(r.disease || "-")}</td>
        `;
        body.appendChild(tr);
    });
}

function showRAGError(msg) {
    $("rag-error-text").textContent = msg;
    $("rag-error").style.display = "flex";
}

// ===== Evaluation =====
let buildTimeChart = null;
let queryTimeChart = null;
let recallChart = null;
let memoryChart = null;



// ===== Utility =====
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
