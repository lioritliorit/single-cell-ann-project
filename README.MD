# 单细胞数据处理与ANN索引构建项目

## 项目概述

本项目提供完整的单细胞数据处理功能，包括：
- **数据读取与解析**：从 h5ad 文件中提取数据
- **数据校验与清洗**：验证PCA向量与细胞元数据一致性
- **标准向量化接口**：封装统一的向量获取接口
- **FAISS索引构建**：适配FAISS格式，支持ANN近邻搜索

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

### 2.2 vector_processor.py - 向量化处理核心模块（新增）
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

---

## 4. 快速开始

### 4.1 安装依赖

```bash
pip install numpy pandas scanpy

# FAISS（二选一）
pip install faiss-cpu    # CPU版本
# 或
pip install faiss-gpu    # GPU版本（需要CUDA支持）
```

### 4.2 运行完整流程

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

### 4.4 FAISS索引类型选择

| 索引类型 | 说明 | 适用场景 |
|----------|------|----------|
| `flat` | 暴力搜索，100%召回率 | 小规模数据（<10万） |
| `ivfflat` | 倒排文件+扁平索引，平衡速度与精度 | 中等规模数据（10万-100万） |
| `ivfpq` | 倒排文件+乘积量化，内存占用小 | 大规模数据（>100万） |

---

## 5. 文件说明

### 需要保留并上传到 GitHub 的文件

| 文件 | 说明 |
|------|------|
| `README.MD` | 项目说明文档 |
| `data_loader.py` | 数据读取模块代码 |
| `vector_processor.py` | 向量化处理模块代码 |
| `.gitignore` | Git忽略文件配置 |
| `cell_metadata.csv` | 细胞元数据 |
| `pca_vectors.npy` | PCA向量 |
| `cleaned_cell_metadata.csv` | 清洗后的细胞元数据 |
| `cleaned_pca_vectors.npy` | 清洗后的PCA向量 |
| `faiss_index.bin` | FAISS索引文件 |
| `cell_type_count.csv` | 细胞类型统计 |
| `disease_count.csv` | 疾病状态统计 |
| `age_group_count.csv` | 年龄分组统计 |

### 不上传到 GitHub 的文件

| 文件 | 说明 |
|------|------|
| `liver.h5ad` | 原始数据文件（太大） |
| `*.h5ad` | 其他 h5ad 数据文件 |

---

## 5. 文件说明

### 需要保留并上传到 GitHub 的文件

| 文件 | 说明 |
|------|------|
| `README.MD` | 项目说明文档 |
| `data_loader.py` | 数据读取模块代码 |
| `vector_processor.py` | 向量化处理模块代码 |
| `hnsw_index.py` | HNSW算法实现代码 |
| `performance_evaluator.py` | 性能评测模块代码 |
| `.gitignore` | Git忽略文件配置 |
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

### 不上传到 GitHub 的文件

| 文件 | 说明 |
|------|------|
| `liver.h5ad` | 原始数据文件（太大） |
| `*.h5ad` | 其他 h5ad 数据文件 |

---

## 6. HNSW算法实现

### 6.1 算法概述

本项目实现了 **HNSW（Hierarchical Navigable Small Worlds）** 算法，这是一种基于图结构的近似最近邻搜索算法。

### 6.2 核心参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `M` | 16 | 每层最大连接数 |
| `M0` | 32 | 底层最大连接数（默认2*M） |
| `efConstruction` | 400 | 构建时的搜索范围 |
| `ef` | 300 | 查询时的搜索范围 |

### 6.3 使用示例

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

### 6.4 性能评测

运行性能评测模块对比不同索引方案：

```bash
python performance_evaluator.py
```

评测结果示例：

| 方法 | 构建时间(s) | 查询时间(s) | 内存(MB) | 召回率 |
|------|------------|------------|----------|--------|
| FAISS_Flat | 0.001 | 0.007 | 2.32 | 1.0000 |
| FAISS_IVFFlat | 0.037 | 0.001 | 4.88 | 1.0000 |
| FAISS_HNSW | 0.124 | 0.001 | 4.25 | 1.0000 |
| HNSW_self | 320.24 | 1.30 | 19.25 | 0.8620 |

---

## 7. 总结

本项目提供了从数据读取到ANN索引构建的完整流程：

1. **数据读取**：`data_loader.py` 从 h5ad 提取基础数据
2. **数据处理**：`vector_processor.py` 完成校验、清洗、向量化
3. **FAISS索引**：使用FAISS库构建高效索引
4. **HNSW实现**：自实现HNSW算法（任务3核心要求）
5. **性能评测**：`performance_evaluator.py` 对比不同方案

所有生成的数据文件（CSV、NPY、FAISS索引、HNSW索引）都已包含在项目中，可直接使用。

---

## 8. 前端可视化展示模块

由成员5完成，基于 Flask + 原生 HTML/CSS/JS，提供 Web 交互界面。

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

### API 接口（前端相关）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 前端主页面 |
| `/api/cell-types` | GET | 获取所有细胞类型列表 |
| `/api/visualization-data` | GET | 获取 PCA 散点数据和细胞类型统计 |

---

## 9. 快速运行

### 9.1 安装依赖

```bash
pip install -r requirements.txt
```

依赖包括：`flask`、`numpy`、`faiss-cpu`

### 9.2 启动服务

```bash
python app.py
```

默认地址：

```text
http://127.0.0.1:5000
```

### 9.3 查看效果

1. 终端运行 `python app.py`
2. 浏览器打开 `http://127.0.0.1:5000`
3. 页面自动加载索引状态和可视化数据
4. 在搜索框输入细胞 ID（默认为 `AAACCTGAGCAGGTCA-1_2`），点击 **检索**
5. 查看 Top-K 相似细胞结果表格
6. 滚动查看细胞类型分布图和 PCA 散点图
7. 可在"细胞类型"下拉框选择类型过滤检索结果

---

## 10. 总结

本项目提供了从数据读取到前端展示的完整流程：

1. **数据读取**：`data_loader.py` 从 h5ad 提取基础数据
2. **数据处理**：`vector_processor.py` 完成校验、清洗、向量化
3. **FAISS索引**：使用FAISS库构建高效索引
4. **HNSW实现**：自实现HNSW算法（任务3核心要求）
5. **性能评测**：`performance_evaluator.py` 对比不同方案
6. **检索服务**：`ann_search_service.py` + `app.py` 提供 REST API
7. **前端展示**：Web 交互界面，支持检索、可视化、索引状态查看
