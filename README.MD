# 单细胞检索系统

## 项目概述

本项目提供完整的单细胞数据处理功能，包括：
- **数据读取与解析**：从 h5ad 文件中提取数据
- **数据校验与清洗**：验证PCA向量与细胞元数据一致性
- **标准向量化接口**：封装统一的向量获取接口
- **FAISS索引构建**：适配FAISS格式，支持ANN近邻搜索
- **HNSW算法实现**：自实现HNSW（Hierarchical Navigable Small Worlds）算法
- **性能评测**：对比不同索引方案的召回率、查询时间、内存占用
- **后端API服务**：Flask REST API 提供 Top-K 相似细胞查询
- **前端可视化展示**：Web交互界面，支持检索、可视化、索引状态查看

---

## 1. 数据文件

本项目使用 `liver.h5ad` 单细胞数据文件，数据采用 AnnData 格式存储。

### 数据规模
- 细胞数量：69032
- 基因数量：32397
- PCA向量维度：30

### AnnData主要字段
- `X`：细胞 × 基因表达矩阵
- `obs`：细胞元信息
- `var`：基因元信息
- `obsm`：降维后的向量表示，包括 `X_pca`、`X_tsne`、`X_umap`
- `uns`：数据集描述信息
- `layers`：当前数据中为空

---

## 2. 模块说明

### 2.1 data_loader.py - 数据读取模块
负责从 h5ad 文件中读取数据并导出基础文件。

主要功能：
- `load_h5ad()`：读取 h5ad 格式文件
- `extract_cell_metadata()`：提取细胞元数据
- `export_pca_vectors()`：导出 PCA 向量
- `export_summary_tables()`：导出统计表格

### 2.2 vector_processor.py - 向量化处理核心模块
提供数据校验、清洗、向量化和FAISS索引构建功能。

核心类：
- **`VectorProcessor`**：数据处理类
  - `load_data()`：加载PCA向量和元数据
  - `validate_consistency()`：校验数据一致性（检查样本数量、NaN、Inf值等）
  - `clean_data(remove_nan, remove_inf, normalize)`：数据清洗，移除异常样本
  - `get_vectors(use_cleaned, dtype)`：获取标准格式向量
  - `get_metadata(use_cleaned)`：获取元数据
  - `save_cleaned_data()`：保存清洗后的数据
  
- **`FAISSIndexBuilder`**：FAISS索引构建类
  - `build_index(index_type, nlist, m, nbits)`：构建FAISS索引
    - 支持三种索引类型：`flat`（精确搜索）、`ivfflat`（倒排索引）、`ivfpq`（乘积量化）
  - `search(query_vectors, k, nprobe)`：执行ANN搜索
  - `save_index(file_path)`：保存索引到文件
  - `load_index(file_path)` [静态]：从文件加载索引

### 2.3 hnsw_index.py - HNSW算法实现
本项目实现了 **HNSW（Hierarchical Navigable Small Worlds）** 算法，这是一种基于图结构的近似最近邻搜索算法。

核心类：
- **`HNSWIndex`**：HNSW索引类
  - `build_index(vectors)`：构建HNSW索引
  - `search(query_vectors, k, ef)`：执行近似最近邻搜索
  - `save_index(file_path)`：保存索引到文件（紧凑2D数组格式）
  - `load_index(file_path)` [静态]：从文件加载索引

核心参数：
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `M` | 16 | 每层最大连接数 |
| `M0` | 32 | 底层最大连接数（默认2*M） |
| `efConstruction` | 200 | 构建时的搜索范围 |
| `ef` | 200 | 查询时的搜索范围 |

**实现优化**（相对基础HNSW的改进）：

1. **多样化邻居选择**：实现了HNSW论文 Algorithm 4 的启发式多样化选择。候选节点只有满足"到查询点的距离 < 到任意已选节点的距离"时才被加入，避免图变成星型结构，提升召回率
2. **完整的搜索层下降**：从 `max_layer` 开始逐层下降，不硬限制起始层数，保证大数据集下的粗粒度导航效果
3. **布尔数组 visited**：使用 numpy `bool[]` 替代 Python `set()` 记录已访问节点，大幅提升大 ef 下的搜索性能
4. **紧凑索引存储**：每层邻接表编码为单个2D NumPy数组（-1填充），替代逐节点逐层的NPZ键存储；
   索引文件从约 94MB 缩小至约 20MB（4.7 倍），保存/加载速度显著提升

### 2.4 hnsw_search_service.py - HNSW搜索服务
Top-K搜索封装服务，调用已构建的HNSW索引。

核心类：
- **`HNSWSearchService`**：HNSW搜索服务类
  - `load()`：加载HNSW索引、PCA向量和元数据
  - `status()`：获取索引状态（含M、ef、efConstruction等HNSW特有参数）
  - `search(cell_id, vector, k, nprobe, include_self, filters)`：搜索Top-K相似细胞
    - HNSW忽略nprobe参数，在响应中通过 `warnings` 字段提示

**`_ensure_loaded` 失败恢复机制**：记录加载尝试状态和错误信息，首次加载失败后直接抛出明确异常，避免静默重试造成混淆。

### 2.5 performance_evaluator.py - 性能评测模块
对比自实现HNSW与FAISS的召回率、查询时间、内存占用。

核心类：
- **`PerformanceEvaluator`**：性能评测类
  - `evaluate_faiss_flat()`：评测FAISS Flat索引（精确搜索，作为baseline）
  - `evaluate_faiss_ivfflat()`：评测FAISS IVFFlat索引
  - `evaluate_faiss_hnsw()`：评测FAISS HNSW索引
  - `evaluate_hnsw()`：评测自实现HNSW索引
  - `compute_recalls()`：计算所有方法相对于精确搜索的召回率
  - `generate_report()`：生成性能评测报告
  - `run_full_evaluation()`：运行完整的性能评测

### 2.6 ann_search_service.py - ANN搜索服务
Top-K搜索封装服务，调用已构建的FAISS ANN索引。

核心类：
- **`SingleCellANNService`**：单细胞ANN服务类
  - `load()`：加载FAISS索引、PCA向量和元数据
  - `status()`：获取索引状态
  - `get_cell(cell_id)`：获取单个细胞信息
  - `search(cell_id, vector, k, nprobe, include_self, filters)`：搜索Top-K相似细胞

### 2.7 app.py - Flask后端API
提供REST API接口和前端展示页面。

**多搜索引擎支持**：内置FAISS和HNSW两个检索服务，通过线程安全的 `threading.Lock()` 保护索引切换操作，避免并发竞态。

**改进特性**：
- 健康检查（`/api/health`）返回当前活跃搜索引擎类型
- `FileNotFoundError` 返回 404 而非 500
- 搜索响应包含 `index_type` 和引擎特定信息

---

## 3. 输出文件

### 3.1 基础输出文件（由 data_loader.py 生成）

| 文件 | 说明 |
|------|------|
| `cell_metadata.csv` | 细胞元数据，包含 cell_id、cell_type、disease 等字段 |
| `pca_vectors.npy` | PCA向量，形状 (69032, 30)，float32格式 |
| `cell_type_count.csv` | 细胞类型统计 |
| `disease_count.csv` | 疾病状态统计 |
| `age_group_count.csv` | 年龄分组统计 |

### 3.2 处理后文件（由 vector_processor.py 生成）

| 文件 | 说明 |
|------|------|
| `cleaned_cell_metadata.csv` | 清洗后的细胞元数据 |
| `cleaned_pca_vectors.npy` | 清洗后的PCA向量 |
| `faiss_index.bin` | FAISS索引文件，可直接用于ANN搜索 |

### 3.3 HNSW索引文件

| 文件 | 说明 |
|------|------|
| `hnsw_index.npz` | 自实现HNSW索引文件 |

### 3.4 性能评测报告

| 文件 | 说明 |
|------|------|
| `performance_report.md` | HNSW算法性能评测报告 |

---

## 4. 快速开始

### 4.1 安装依赖

```bash
pip install -r requirements.txt
```

依赖包括：`flask`、`numpy`、`faiss-cpu`

### 4.2 运行数据处理流程

```bash
# 方式1：使用数据读取模块
python data_loader.py

# 方式2：使用向量化处理模块（推荐）
python vector_processor.py
```

### 4.3 在代码中使用

```python
from vector_processor import VectorProcessor, FAISSIndexBuilder

# 初始化处理器
processor = VectorProcessor()

# 加载、校验、清洗数据
processor.load_data()
processor.validate_consistency()
cleaned_vectors, cleaned_metadata = processor.clean_data()

# 构建FAISS索引
index_builder = FAISSIndexBuilder(cleaned_vectors)
index = index_builder.build_index(index_type="ivfflat", nlist=100)
index_builder.save_index("faiss_index.bin")

# 执行搜索
distances, indices = index_builder.search(query_vectors, k=10)
```

### 4.4 HNSW使用示例

```python
from hnsw_index import HNSWIndex
import numpy as np

# 加载向量数据
vectors = np.load("cleaned_pca_vectors.npy")

# 构建HNSW索引
hnsw = HNSWIndex(M=16, efConstruction=200, ef=150)
hnsw.build_index(vectors)

# 执行搜索
query = vectors[:5]  # 取前5个向量作为查询
distances, indices = hnsw.search(query, k=10)

# 保存/加载索引（紧凑格式，约20MB）
hnsw.save_index("hnsw_index.npz")
hnsw = HNSWIndex.load_index("hnsw_index.npz")
```

### 4.5 运行性能评测

```bash
python performance_evaluator.py
```

### 4.6 启动后端API服务

```bash
python app.py
```

默认地址：
```text
http://127.0.0.1:5000
```

如需指定文件路径，可使用环境变量：
```bash
ANN_INDEX_PATH=faiss_index.bin
ANN_VECTORS_PATH=cleaned_pca_vectors.npy
ANN_METADATA_PATH=cleaned_cell_metadata.csv
```

### 4.7 本地测试API

```bash
python test_search_api.py
```

该脚本会加载 `faiss_index.bin`、`cleaned_pca_vectors.npy`、`cleaned_cell_metadata.csv`，使用第一条细胞记录执行 `k=5` 查询，并打印返回的 Top-K 结果与耗时。

---

## 5. FAISS索引类型选择

| 索引类型 | 说明 | 适用场景 |
|----------|------|----------|
| `flat` | 暴力搜索，100%召回率 | 小规模数据（&lt;10万） |
| `ivfflat` | 倒排文件+扁平索引，平衡速度与精度 | 中等规模数据（10万-100万） |
| `ivfpq` | 倒排文件+乘积量化，内存占用小 | 大规模数据（&gt;100万） |

---

## 6. 后端API接口

### 6.1 健康检查

```http
GET /api/health
```

返回示例：
```json
{
  "status": "ok",
  "active_index_engine": "faiss"
}
```

### 6.2 索引切换

```http
POST /api/index/switch
Content-Type: application/json

{
  "index_type": "hnsw"
}
```

支持的索引类型：`faiss`、`hnsw`。切换过程由线程锁保护，保证并发安全。

### 6.3 查看索引状态

```http
GET /api/index/status
```

FAISS 状态返回示例：
```json
{
  "loaded": true,
  "cell_count": 69032,
  "index_total": 69032,
  "dimension": 30,
  "index_engine": "faiss",
  "current_index_type": "faiss",
  "available_index_types": ["faiss", "hnsw"]
}
```

HNSW 状态额外返回：
```json
{
  "index_engine": "hnsw",
  "M": 16,
  "ef": 150,
  "efConstruction": 200,
  "current_index_type": "hnsw"
}
```

### 6.4 按 cell_id 查询 Top-K

```http
POST /api/search
Content-Type: application/json

{
  "cell_id": "AAACCTGAGCAGGTCA-1_2",
  "k": 5,
  "nprobe": 10
}
```

搜索响应包含引擎信息：
```json
{
  "index_type": "hnsw",
  "engine": "hnsw",
  "elapsed_ms": 10.067,
  "warnings": ["nprobe参数对HNSW索引无效，已忽略"],
  ...
}
```

- `index_type`：实际使用的搜索引擎
- `engine`：搜索引擎标识
- `warnings`：参数不兼容时的提示（如 HNSW 收到 nprobe 参数）

### 6.5 按查询向量查询 Top-K

```http
POST /api/search
Content-Type: application/json

{
  "vector": [0.12, -1.4, 0.33],
  "k": 5
}
```

`vector` 长度必须与 PCA 维度一致，本项目为 30 维。

### 6.6 带简单条件过滤

该过滤在 ANN 召回候选后执行，适合前端演示"限定某类细胞"的查询。

```http
POST /api/search
Content-Type: application/json

{
  "cell_id": "AAACCTGAGCAGGTCA-1_2",
  "k": 5,
  "filters": {
    "cell_type": "hepatocyte"
  }
}
```

### 6.7 查询单个细胞信息

```http
GET /api/cells/AAACCTGAGCAGGTCA-1_2
```

### 6.8 获取所有细胞类型列表

```http
GET /api/cell-types
```

### 6.9 获取可视化数据

```http
GET /api/visualization-data
```

返回 PCA 散点数据和细胞类型统计。

---

## 7. 前端可视化展示模块

基于 Flask + 原生 HTML/CSS/JS，提供 Web 交互界面。

### 技术栈
- **后端框架**：Flask（与检索 API 共用同一服务）
- **前端**：原生 HTML5 + CSS3 + JavaScript（无额外前端框架依赖）
- **图表库**：Chart.js（CDN 加载）
- **图标**：Font Awesome（CDN 加载）

### 功能特性

| 功能 | 说明 |
|------|------|
| 相似细胞检索 | 输入细胞 ID，查询 Top-K 相似细胞 |
| 条件过滤 | 可按细胞类型过滤检索结果 |
| 结果表格展示 | 显示排名、细胞ID、细胞类型、距离、疾病、年龄、性别、表达量 |
| 搜索引擎切换 | 支持 FAISS / 自实现 HNSW 实时切换，状态面板显示引擎特有参数 |
| 引擎参数提示 | HNSW 不支持的参数（如 nprobe）在页面中显示警告 |
| 查询标记 | 散点图上自动标记查询细胞位置，每次搜索替换旧标记而非累加 |
| 细胞类型分布图 | 横向条形图展示各类细胞数量（修复了Chart.js循环缩放bug） |
| PCA 二维散点图 | 基于 PCA 前两维的细胞分布可视化，可筛选特定细胞类型 |
| 索引状态面板 | 显示细胞总数、向量维度、索引类型，切换HNSW时显示M/ef参数 |

### 文件结构

```
templates/
└── index.html          # 主页面模板
static/
├── css/
│   └── style.css       # 页面样式（响应式设计）
└── js/
    └── main.js         # 前端交互逻辑
```

### 快速运行

1. 终端运行 `python app.py`
2. 浏览器打开 `http://127.0.0.1:5000`
3. 页面自动加载索引状态和可视化数据
4. 在搜索框输入细胞 ID（例如 `AAACCTGAGCAGGTCA-1_2`），点击 **检索**
5. 查看 Top-K 相似细胞结果表格
6. 滚动查看细胞类型分布图和 PCA 散点图
7. 可在"细胞类型"下拉框选择类型过滤检索结果
8. 在索引状态面板可切换 FAISS / HNSW 搜索引擎，切换后自动更新状态参数

---

## 8. HNSW算法性能评测报告

### 评测概览

- 数据规模: 10000 个向量
- 向量维度: 30
- 查询数量: 50
- 评测环境: CPU 单线程

### 评测结果对比

| 方法 | 构建时间(s) | 查询时间(s) | 召回率@10 | 说明 |
|------|------------|------------|----------|------|
| FAISS_Flat | 0.005 | 0.007 | 1.0000 | 精确搜索基线（暴力计算） |
| FAISS_IVFFlat (nlist=100) | 0.054 | 0.001 | 1.0000 | FAISS倒排索引 |
| FAISS_HNSW (M=16) | 0.136 | 0.001 | 1.0000 | FAISS的C++ HNSW实现 |
| 新版HNSW_self (M=16) | 133.268 | 0.618 | **0.8600** | 本项目的自实现HNSW（修复后） |

>  旧版 HNSW_self 召回率约 0.6680，修复后提升至 **0.8600**（提升 28.7%）

### 修复优化对比

| 优化项 | 旧版 | 新版 | 效果 |
|--------|------|------|------|
| 邻居选择 | 简单 top-M | 多样化启发式选择 | 召回率提升 |
| 搜索起始层 | 硬编码 ≤3 | 完整分层下降 | 大数据集导航准确 |
| visited 结构 | Python set() | numpy bool[] | 搜索加速 |
| 索引文件大小 | ~94 MB | ~20 MB | 缩小 4.7 倍 |
| 保存格式 | 逐键 NPZ | 紧凑 2D 数组 | 保存/加载大幅加速 |

### 参数配置

#### HNSW_self (新版)
```
{'M': 16, 'efConstruction': 200, 'ef': 150}
```

### 结论

**新版自实现 HNSW 召回率达到 86%**（旧版约 67%），主要得益于：
1. **多样化邻居选择**：避免图退化为星型结构
2. **完整分层搜索**：从最高层开始粗粒度导航
3. **紧凑索引格式**：文件体积从 94MB 降至 20MB

> ⚠️ 构建效率（纯 Python 133s）和搜索速度（12ms/query）远低于 FAISS C++ 实现，这是编程语言层面的差距，非算法问题。纯 Python 实现适合教学演示和小规模实验。如需生产部署，建议使用 FAISS。

---

## 9. 文件说明

### 需要保留并上传到 GitHub 的文件

| 文件 | 说明 |
|------|------|
| `README.MD` | 项目说明文档 |
| `data_loader.py` | 数据读取模块代码 |
| `vector_processor.py` | 向量化处理模块代码 |
| `hnsw_index.py` | HNSW算法实现代码（含多样化选择、紧凑存储） |
| `hnsw_search_service.py` | HNSW搜索服务封装代码 |
| `performance_evaluator.py` | 性能评测模块代码 |
| `ann_search_service.py` | ANN搜索服务代码 |
| `app.py` | Flask后端API代码 |
| `test_search_api.py` | API测试脚本 |
| `.gitignore` | Git忽略文件配置 |
| `requirements.txt` | Python依赖列表 |
| `cell_metadata.csv` | 细胞元数据 |
| `pca_vectors.npy` | PCA向量 |
| `cleaned_cell_metadata.csv` | 清洗后的细胞元数据 |
| `cleaned_pca_vectors.npy` | 清洗后的PCA向量 |
| `faiss_index.bin` | FAISS索引文件 |
| `hnsw_index.npz` | HNSW索引文件 |
| `performance_report.md` | 性能评测报告 |
| `cell_type_count.csv` | 细胞类型统计 |
| `disease_count.csv` | 疾病状态统计 |
| `age_group_count.csv` | 年龄分组统计 |
| `templates/index.html` | 前端页面模板 |
| `static/css/style.css` | 前端样式文件 |
| `static/js/main.js` | 前端交互逻辑 |

### 不上传到 GitHub 的文件

| 文件 | 说明 |
|------|------|
| `liver.h5ad` | 原始数据文件（太大） |
| `*.h5ad` | 其他 h5ad 数据文件 |

---

## 10. 总结

本项目提供了从数据读取到前端展示的完整流程：

1. **数据读取**：`data_loader.py` 从 h5ad 提取基础数据
2. **数据处理**：`vector_processor.py` 完成校验、清洗、向量化
3. **FAISS索引**：使用FAISS库构建高效索引
4. **HNSW实现**：自实现HNSW算法（核心要求），含多样化邻居选择、紧凑索引存储等优化
5. **HNSW搜索服务**：`hnsw_search_service.py` 封装HNSW搜索，含失败恢复机制
6. **性能评测**：`performance_evaluator.py` 对比不同方案，新版召回率86%（旧版约67%）
7. **后端服务**：`app.py` + `ann_search_service.py` / `hnsw_search_service.py` 提供多引擎REST API
8. **前端展示**：Web 交互界面，支持双引擎切换、检索、可视化、索引状态查看

所有生成的数据文件（CSV、NPY、FAISS索引、HNSW索引）都已包含在项目中，可直接使用。
