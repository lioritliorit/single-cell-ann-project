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
  - `save_index(file_path)`：保存索引到文件
  - `load_index(file_path)` [静态]：从文件加载索引

核心参数：
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `M` | 16 | 每层最大连接数 |
| `M0` | 32 | 底层最大连接数（默认2*M） |
| `efConstruction` | 400 | 构建时的搜索范围 |
| `ef` | 300 | 查询时的搜索范围 |

### 2.4 performance_evaluator.py - 性能评测模块
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

### 2.5 ann_search_service.py - ANN搜索服务
Top-K搜索封装服务，调用已构建的FAISS ANN索引。

核心类：
- **`SingleCellANNService`**：单细胞ANN服务类
  - `load()`：加载FAISS索引、PCA向量和元数据
  - `status()`：获取索引状态
  - `get_cell(cell_id)`：获取单个细胞信息
  - `search(cell_id, vector, k, nprobe, include_self, filters)`：搜索Top-K相似细胞

### 2.6 app.py - Flask后端API
提供REST API接口和前端展示页面。

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
hnsw = HNSWIndex(M=16, efConstruction=400, ef=300)
hnsw.build_index(vectors)

# 执行搜索
query = vectors[:5]  # 取前5个向量作为查询
distances, indices = hnsw.search(query, k=10)

# 保存/加载索引
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

### 6.2 查看索引状态

```http
GET /api/index/status
```

返回示例字段：
```json
{
  "loaded": true,
  "cell_count": 69032,
  "index_total": 69032,
  "dimension": 30
}
```

### 6.3 按 cell_id 查询 Top-K

```http
POST /api/search
Content-Type: application/json

{
  "cell_id": "AAACCTGAGCAGGTCA-1_2",
  "k": 5,
  "nprobe": 10
}
```

### 6.4 按查询向量查询 Top-K

```http
POST /api/search
Content-Type: application/json

{
  "vector": [0.12, -1.4, 0.33],
  "k": 5
}
```

`vector` 长度必须与 PCA 维度一致，本项目为 30 维。

### 6.5 带简单条件过滤

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

### 6.6 查询单个细胞信息

```http
GET /api/cells/AAACCTGAGCAGGTCA-1_2
```

### 6.7 获取所有细胞类型列表

```http
GET /api/cell-types
```

### 6.8 获取可视化数据

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
| 细胞类型分布图 | 横向条形图展示各类细胞数量 |
| PCA 二维散点图 | 基于 PCA 前两维的细胞分布可视化，可高亮特定细胞类型 |
| 查询标记 | 在散点图上自动标记查询细胞位置 |
| 索引状态面板 | 显示细胞总数、向量维度、索引状态 |

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
4. 在搜索框输入细胞 ID（默认为 `AAACCTGAGCAGGTCA-1_2`），点击 **检索**
5. 查看 Top-K 相似细胞结果表格
6. 滚动查看细胞类型分布图和 PCA 散点图
7. 可在"细胞类型"下拉框选择类型过滤检索结果

---

## 8. HNSW算法性能评测报告

### 评测概览

- 数据规模: 10000 个向量
- 向量维度: 30
- 查询数量: 50

### 评测结果对比

| 方法 | 构建时间(s) | 查询时间(s) | 内存(MB) | 召回率 | 精确率 |
|------|------------|------------|----------|--------|--------|
| FAISS_Flat | 0.0015 | 0.0474 | 2.32 | 1.0000 | 1.0000 |
| FAISS_IVFFlat (nlist=100) | 0.0543 | 0.0011 | 4.67 | 1.0000 | 1.0000 |
| FAISS_HNSW (M=16) | 0.1293 | 0.0020 | 3.22 | 1.0000 | 1.0000 |
| HNSW_self (M=16) | 229.8325 | 0.5774 | 19.18 | 0.6680 | 0.6680 |

### 参数配置

#### FAISS_Flat
```
{'type': 'flat'}
```

#### FAISS_IVFFlat (nlist=100)
```
{'nlist': 100, 'nprobe': 10}
```

#### FAISS_HNSW (M=16)
```
{'M': 16, 'ef': 50}
```

#### HNSW_self (M=16)
```
{'M': 16, 'efConstruction': 400, 'ef': 300}
```

### 结论

#### 自实现HNSW vs FAISS对比分析

- **构建时间**: 自实现 229.83s vs FAISS 0.13s
- **查询时间**: 自实现 0.5774s vs FAISS 0.0020s
- **内存占用**: 自实现 19.18MB vs FAISS 3.22MB
- **召回率**: 自实现 0.6680 vs FAISS 1.0000

⚠️ 自实现HNSW召回率有待提升
⚠️ 自实现HNSW构建效率低于FAISS

---

## 9. 文件说明

### 需要保留并上传到 GitHub 的文件

| 文件 | 说明 |
|------|------|
| `README.MD` | 项目说明文档 |
| `data_loader.py` | 数据读取模块代码 |
| `vector_processor.py` | 向量化处理模块代码 |
| `hnsw_index.py` | HNSW算法实现代码 |
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
4. **HNSW实现**：自实现HNSW算法（核心要求）
5. **性能评测**：`performance_evaluator.py` 对比不同方案
6. **检索服务**：`ann_search_service.py` + `app.py` 提供 REST API
7. **前端展示**：Web 交互界面，支持检索、可视化、索引状态查看

所有生成的数据文件（CSV、NPY、FAISS索引、HNSW索引）都已包含在项目中，可直接使用。
