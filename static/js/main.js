// ===== State =====
const state = {
    indexStatus: null,
    cellTypes: [],
    pcaData: null,
    cellTypeChart: null,
    pcaChart: null,
};

// ===== DOM refs =====
const $ = (id) => document.getElementById(id);
const searchForm = $('search-form');
const cellIdInput = $('cell-id-input');
const kInput = $('k-input');
const filterCellType = $('filter-cell-type');
const searchBtn = $('search-btn');
const loading = $('loading');
const queryInfo = $('query-info');
const queryTime = $('query-time');
const queryCount = $('query-count');
const queryCellId = $('query-cell-id');
const resultsContainer = $('results-container');
const resultsBody = $('results-body');
const errorMsg = $('error-msg');
const errorText = $('error-text');
const engineBadge = document.getElementById('badge-engine');

// ===== Initialize =====
document.addEventListener('DOMContentLoaded', async () => {
    await loadIndexStatus();
    await loadCellTypes();
    await loadVisualizationData();
    setupNavigation();
    setupIndexSwitch();

    // Auto-search on load with default cell ID
    if (cellIdInput.value) {
        searchForm.dispatchEvent(new Event('submit'));
    }
});

// ===== Navigation =====
function setupNavigation() {
    const sections = document.querySelectorAll("section[id]");
    const navLinks = document.querySelectorAll(".nav-link");

    function setActive(id) {
        navLinks.forEach(l => l.classList.toggle("active", l.getAttribute("href") === "#" + id));
    }

    // 点击导航跳转时立即切换高亮
    navLinks.forEach(link => {
        link.addEventListener("click", () => {
            const id = link.getAttribute("href")?.replace("#", "");
            if (id) setActive(id);
        });
    });

    // 滚动时根据可见区域自动切换
    const observer = new IntersectionObserver(entries => {
        for (const entry of entries) {
            if (entry.isIntersecting) {
                setActive(entry.target.id);
                break;
            }
        }
    }, { rootMargin: "-20% 0px -60% 0px" });

    sections.forEach(s => observer.observe(s));
}

// ===== API Calls =====
async function apiGet(url) {
    const resp = await fetch(url);
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.message || err.error || `HTTP ${resp.status}`);
    }
    return resp.json();
}

async function apiPost(url, data) {
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.message || err.error || `HTTP ${resp.status}`);
    }
    return resp.json();
}

// ===== Load Index Status =====
async function loadIndexStatus() {
    try {
        const data = await apiGet('/api/index/status');
        state.indexStatus = data;
        $('badge-cells').innerHTML = `<i class="fas fa-hashtag"></i> ${data.cell_count.toLocaleString()} 细胞`;
        $('badge-dim').innerHTML = `<i class="fas fa-vector-square"></i> ${data.dimension} 维`;
        $('badge-status').innerHTML = `<i class="fas fa-circle" style="color:#4caf50;"></i> 已就绪`;

        if (engineBadge) {
            engineBadge.innerHTML = `<i class="fas fa-microchip"></i> ${(data.current_index_type || 'faiss').toUpperCase()}`;
        }

        $('stat-cell-count').textContent = data.cell_count.toLocaleString();
        $('stat-dimension').textContent = data.dimension;
        $('stat-index-total').textContent = data.index_total.toLocaleString();
        $('stat-index-type').textContent = (data.current_index_type || 'faiss').toUpperCase();
        $('index-status-loading').style.display = 'none';
        $('index-status-content').style.display = 'block';

        // 显示索引引擎特定参数
        const extraParams = $('stat-extra-params');
        const extraValue = $('stat-extra-value');
        const extraLabel = $('stat-extra-label');
        if (data.current_index_type === 'hnsw' && data.M) {
            extraParams.style.display = 'block';
            extraValue.textContent = `M=${data.M}, ef=${data.ef}`;
            extraLabel.textContent = 'HNSW 参数';
        } else {
            extraParams.style.display = 'none';
        }

        updateSwitchBtnText(data.current_index_type);
    } catch (err) {
        $('badge-cells').innerHTML = `<i class="fas fa-circle" style="color:#f44336;"></i> 加载失败`;
        $('badge-dim').textContent = '无法连接';
        $('badge-status').innerHTML = `<i class="fas fa-exclamation-triangle" style="color:#f44336;"></i> 离线`;
        if (engineBadge) {
            engineBadge.innerHTML = `<i class="fas fa-microchip"></i> ?`;
        }
    }
}

function updateSwitchBtnText(currentType) {
    const btnText = $('switch-btn-text');
    btnText.textContent = currentType === 'faiss' ? '切换到 HNSW' : '切换到 FAISS';
}

// ===== Index Switching =====
function setupIndexSwitch() {
    $('switch-index-btn').addEventListener('click', switchIndex);
}

async function switchIndex() {
    const btn = $('switch-index-btn');
    const statusEl = $('switch-status');
    const previousType = state.indexStatus?.current_index_type || 'faiss';
    btn.disabled = true;
    statusEl.textContent = '切换中...';
    statusEl.style.color = '#666';

    const targetType = previousType === 'faiss' ? 'hnsw' : 'faiss';

    try {
        const data = await apiPost('/api/index/switch', { index_type: targetType });
        statusEl.textContent = `已切换到 ${targetType.toUpperCase()}`;
        statusEl.style.color = '#2e7d32';
        updateSwitchBtnText(targetType);

        await loadIndexStatus();
    } catch (err) {
        // 切换失败，回滚状态
        statusEl.textContent = `切换失败: ${err.message}`;
        statusEl.style.color = '#c62828';
        // 回滚按钮文本
        updateSwitchBtnText(previousType);
    }

    btn.disabled = false;

    setTimeout(() => {
        statusEl.textContent = '';
    }, 4000);
}

// ===== Load Cell Types =====
async function loadCellTypes() {
    try {
        const data = await apiGet('/api/cell-types');
        state.cellTypes = data.cell_types || [];
        const select = filterCellType;
        state.cellTypes.forEach(ct => {
            const opt = document.createElement('option');
            opt.value = ct;
            opt.textContent = ct;
            select.appendChild(opt);
        });
    } catch (err) {
        console.warn('Failed to load cell types:', err);
    }
}

// ===== Load Visualization Data =====
async function loadVisualizationData() {
    try {
        const data = await apiGet('/api/visualization-data');
        state.pcaData = data;
        renderCellTypeChart(data);
        renderPCAScatter(data);
    } catch (err) {
        console.warn('Failed to load visualization data:', err);
    }
}

// ===== Cell Type Distribution Chart =====
function renderCellTypeChart(data) {
    const ctx = $('cell-type-chart').getContext('2d');

    const items = data.cell_type_counts
        .sort((a, b) => b.count - a.count)
        .slice(0, 15);

    const colors = [
        '#1565c0', '#2e7d32', '#e65100', '#6a1b9a', '#00838f',
        '#c62828', '#558b2f', '#283593', '#ad1457', '#00695c',
        '#b71c1c', '#1b5e20', '#4a148c', '#e65100', '#01579b'
    ];

    if (state.cellTypeChart) {
        state.cellTypeChart.destroy();
    }

    state.cellTypeChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: items.map(d => d.cell_type),
            datasets: [{
                label: '细胞数量',
                data: items.map(d => d.count),
                backgroundColor: colors.slice(0, items.length),
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            responsiveAnimationDuration: 0,
            indexAxis: 'y',
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.parsed.x.toLocaleString()} 个细胞`
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: {
                        callback: (val) => val >= 1000 ? (val/1000).toFixed(1) + 'k' : val
                    }
                },
                y: {
                    grid: { display: false },
                    ticks: { font: { size: 10 } }
                }
            }
        }
    });
}

// ===== PCA Scatter Plot =====
function renderPCAScatter(data) {
    const ctx = $('pca-scatter').getContext('2d');

    const points = data.pca_points || [];
    const colorPalette = [
        '#1565c0', '#2e7d32', '#e65100', '#6a1b9a', '#00838f',
        '#c62828', '#558b2f', '#283593', '#ad1457', '#00695c',
        '#b71c1c', '#f57f17', '#4a148c', '#e91e63', '#00bfa5',
        '#651fff', '#ff6d00', '#00bcd4', '#d500f9', '#76ff03',
    ];

    const typeGroups = {};
    points.forEach(p => {
        const ct = p.cell_type || 'unknown';
        if (!typeGroups[ct]) {
            typeGroups[ct] = { label: ct, data: [], color: colorPalette[Object.keys(typeGroups).length % colorPalette.length], hidden: false };
        }
        typeGroups[ct].data.push({ x: p.pc1, y: p.pc2 });
    });

    const datasets = Object.values(typeGroups);

    if (state.pcaChart) {
        state.pcaChart.destroy();
    }

    state.pcaChart = new Chart(ctx, {
        type: 'scatter',
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            responsiveAnimationDuration: 0,
            animation: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'right',
                    labels: {
                        boxWidth: 12,
                        padding: 8,
                        font: { size: 9 },
                        filter: (item) => item.datasetIndex < 20
                    }
                },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.dataset.label}: (${ctx.parsed.x.toFixed(1)}, ${ctx.parsed.y.toFixed(1)})`
                    }
                }
            },
            scales: {
                x: {
                    title: { display: true, text: 'PC1', font: { size: 11 } },
                    grid: { display: false }
                },
                y: {
                    title: { display: true, text: 'PC2', font: { size: 11 } },
                    grid: { display: false }
                }
            },
            elements: {
                point: {
                    radius: 2,
                    hoverRadius: 4,
                }
            }
        }
    });

    // 图表就绪后初始化筛选器（不再使用轮询）
    initCellTypeFilterViz(data);
}

function initCellTypeFilterViz(data) {
    const select = $('cell-type-filter-viz');
    if (!select) return;

    // 清除旧选项
    select.innerHTML = '';

    const types = [...new Set(data.pca_points.map(p => p.cell_type || 'unknown'))].sort();

    const allOpt = document.createElement('option');
    allOpt.value = '';
    allOpt.textContent = '全部类型';
    select.appendChild(allOpt);

    types.forEach(t => {
        const o = document.createElement('option');
        o.value = t;
        o.textContent = t;
        select.appendChild(o);
    });

    // 移除旧的监听器并添加新监听器
    const newSelect = select.cloneNode(true);
    select.parentNode.replaceChild(newSelect, select);

    newSelect.addEventListener('change', () => {
        const selected = newSelect.value;
        state.pcaChart.data.datasets.forEach(ds => {
            ds.hidden = selected !== '' && ds.label !== selected;
        });
        state.pcaChart.update();
    });
}

// ===== Search =====
searchForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const cellId = cellIdInput.value.trim();
    const k = parseInt(kInput.value) || 10;
    const filter = filterCellType.value;

    if (!cellId) {
        showError('请输入细胞 ID');
        return;
    }

    hideError();
    resultsContainer.style.display = 'none';
    queryInfo.style.display = 'none';
    loading.style.display = 'block';
    searchBtn.disabled = true;

    try {
        const payload = { cell_id: cellId, k };
        if (filter) {
            payload.filters = { cell_type: filter };
        }

        const data = await apiPost('/api/search', payload);

        loading.style.display = 'none';
        searchBtn.disabled = false;

        queryTime.textContent = data.elapsed_ms;
        queryCount.textContent = data.result_count;
        queryCellId.textContent = cellId;
        queryInfo.style.display = 'block';

        // 显示搜索引擎信息
        const engineInfo = document.getElementById('engine-info');
        if (engineInfo) {
            engineInfo.textContent = `引擎: ${(data.index_type || '?').toUpperCase()}`;
        }

        // 显示警告信息
        if (data.warnings && data.warnings.length > 0) {
            const warningEl = document.getElementById('search-warnings');
            if (warningEl) {
                warningEl.innerHTML = data.warnings.map(w =>
                    `<div class="alert alert-warning"><i class="fas fa-exclamation-circle"></i> ${w}</div>`
                ).join('');
                warningEl.style.display = 'block';
            }
        } else {
            const warningEl = document.getElementById('search-warnings');
            if (warningEl) {
                warningEl.style.display = 'none';
            }
        }

        renderResults(data.results);
        resultsContainer.style.display = 'block';

        highlightQueryCell(data);

    } catch (err) {
        loading.style.display = 'none';
        searchBtn.disabled = false;
        showError(err.message);
    }
});

function renderResults(results) {
    resultsBody.innerHTML = '';

    if (!results || results.length === 0) {
        resultsBody.innerHTML = `<tr><td colspan="10" style="text-align:center; color:#999; padding:32px;">
            <i class="fas fa-inbox"></i> 未找到结果
        </td></tr>`;
        return;
    }

    results.forEach((r, i) => {
        const tr = document.createElement('tr');

        const dist = r.distance !== null && r.distance !== undefined
            ? r.distance.toFixed(4)
            : '-';

        const nCount = r.expression?.nCount_RNA !== null && r.expression?.nCount_RNA !== undefined
            ? Number(r.expression.nCount_RNA).toFixed(1)
            : '-';

        const nFeature = r.expression?.nFeature_RNA !== null && r.expression?.nFeature_RNA !== undefined
            ? Number(r.expression.nFeature_RNA).toFixed(1)
            : '-';

        const pctMt = r.expression?.percent_mt !== null && r.expression?.percent_mt !== undefined
            ? Number(r.expression.percent_mt).toFixed(2) + '%'
            : '-';

        tr.innerHTML = `
            <td class="rank-cell">${i + 1}</td>
            <td><code>${r.cell_id || '-'}</code></td>
            <td><span class="cell-type-tag">${r.cell_type || '-'}</span></td>
            <td>${dist}</td>
            <td>${r.disease || '-'}</td>
            <td>${r.metadata?.donor_age || '-'}</td>
            <td>${r.metadata?.sex || '-'}</td>
            <td>${nCount}</td>
            <td>${nFeature}</td>
            <td>${pctMt}</td>
        `;
        resultsBody.appendChild(tr);
    });
}

function highlightQueryCell(data) {
    if (!state.pcaChart || !state.pcaData) return;

    // 清除旧的"查询细胞"高亮（移除之前添加的dataset）
    state.pcaChart.data.datasets = state.pcaChart.data.datasets.filter(
        ds => ds.label !== '查询细胞'
    );

    if (data.query && data.query.row_index !== null && data.query.row_index !== undefined) {
        const rowIdx = data.query.row_index;
        const pcaPoint = state.pcaData.pca_points[rowIdx];
        if (pcaPoint) {
            const highlightDs = {
                label: '查询细胞',
                data: [{ x: pcaPoint.pc1, y: pcaPoint.pc2 }],
                backgroundColor: '#f44336',
                pointRadius: 8,
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
                order: -1,
            };
            state.pcaChart.data.datasets.push(highlightDs);
            state.pcaChart.update();
        }
    }
}

// ===== Error handling =====
function showError(msg) {
    errorText.textContent = msg;
    errorMsg.style.display = 'flex';
}

function hideError() {
    errorMsg.style.display = 'none';
}
