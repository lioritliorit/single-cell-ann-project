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

// ===== Initialize =====
document.addEventListener('DOMContentLoaded', async () => {
    await loadIndexStatus();
    await loadCellTypes();
    await loadVisualizationData();
    setupNavigation();
    loadCellTypeFilterViz();

    // Auto-search on load with default cell ID
    if (cellIdInput.value) {
        searchForm.dispatchEvent(new Event('submit'));
    }
});

// ===== Navigation =====
function setupNavigation() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
            link.classList.add('active');
        });
    });
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

        $('stat-cell-count').textContent = data.cell_count.toLocaleString();
        $('stat-dimension').textContent = data.dimension;
        $('stat-index-total').textContent = data.index_total.toLocaleString();
        $('index-status-loading').style.display = 'none';
        $('index-status-content').style.display = 'block';
    } catch (err) {
        $('badge-cells').innerHTML = `<i class="fas fa-circle" style="color:#f44336;"></i> 加载失败`;
        $('badge-dim').textContent = '无法连接';
        $('badge-status').innerHTML = `<i class="fas fa-exclamation-triangle" style="color:#f44336;"></i> 离线`;
    }
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

    // Sort by count descending, take top 15
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
            maintainAspectRatio: true,
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
    const cellTypeColors = {};
    const colorPalette = [
        '#1565c0', '#2e7d32', '#e65100', '#6a1b9a', '#00838f',
        '#c62828', '#558b2f', '#283593', '#ad1457', '#00695c',
        '#b71c1c', '#f57f17', '#4a148c', '#e91e63', '#00bfa5',
        '#651fff', '#ff6d00', '#00bcd4', '#d500f9', '#76ff03',
    ];

    // Group points by cell type
    const typeGroups = {};
    points.forEach(p => {
        const ct = p.cell_type || 'unknown';
        if (!typeGroups[ct]) {
            typeGroups[ct] = { label: ct, data: [], color: colorPalette[Object.keys(typeGroups).length % colorPalette.length], hidden: false };
            cellTypeColors[ct] = typeGroups[ct].color;
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
            maintainAspectRatio: true,
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

    // Set up cell type filter for scatter
    const select = $('cell-type-filter-viz');
    select.addEventListener('change', () => {
        const selected = select.value;
        state.pcaChart.data.datasets.forEach(ds => {
            if (selected === '') {
                ds.hidden = false;
            } else {
                ds.hidden = ds.label !== selected;
            }
        });
        state.pcaChart.update();
    });
}

function loadCellTypeFilterViz() {
    const select = $('cell-type-filter-viz');
    // Will be populated when pca data loads
    const orig = select.addEventListener;
    const poll = setInterval(() => {
        if (state.pcaData && state.pcaChart) {
            clearInterval(poll);
            const types = [...new Set(state.pcaData.pca_points.map(p => p.cell_type || 'unknown'))].sort();
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = '全部类型';
            select.appendChild(opt);
            types.forEach(t => {
                const o = document.createElement('option');
                o.value = t;
                o.textContent = t;
                select.appendChild(o);
            });
        }
    }, 200);
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

    // Hide previous results
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

        // Show query info
        queryTime.textContent = data.elapsed_ms;
        queryCount.textContent = data.result_count;
        queryCellId.textContent = cellId;
        queryInfo.style.display = 'block';

        // Render results
        renderResults(data.results);
        resultsContainer.style.display = 'block';

        // Highlight searched cell on PCA plot
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

    // Reset all point styles
    state.pcaChart.data.datasets.forEach(ds => {
        ds.pointRadius = 2;
        ds.pointBorderWidth = 0;
    });

    // Highlight query cell if we can find it
    if (data.query && data.query.row_index !== null && data.query.row_index !== undefined) {
        const rowIdx = data.query.row_index;
        const pcaPoint = state.pcaData.pca_points[rowIdx];
        if (pcaPoint) {
            // Add a special highlighted point
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
