# 单细胞 ANN 检索系统

## 项目概述

一个完整的单细胞数据管理、处理、检索与可视化系统。支持多数据集管理、FAISS/HNSW双引擎检索、性能评估、前端可视化和 AI 自然语言查询。

---

## 功能特性

### 核心功能
1. **单细胞数据读取** - 从 h5ad 文件读取表达矩阵和元数据
2. **数据向量化表示** - PCA 降维向量存储与处理
3. **ANN 索引构建** - 支持 FAISS（多种索引类型）和自实现 HNSW
4. **相似细胞检索** - Top-K 相似细胞搜索，返回完整细胞信息
5. **条件检索** - 可限定细胞类型、疾病状态等条件
6. **实验评估** - 详细的响应时间、召回率、内存占用分析
7. **可视化展示** - PCA/UMAP 可视化，支持交互查询
8. **数据集管理** - 数据集增删、动态索引切换

### 高级功能
1. **HNSW 算法改进**
   - 多样化邻居选择，避免图退化
   - numpy 向量化加速
   - 紧凑 2D 数组索引格式（约 20MB）

2. **多数据集联合检索**
   - 支持多个 h5ad 数据集管理
   - 跨数据集细胞搜索
   - 联合索引构建

3. **RAG + AI 自然语言查询**
   - 自然语言描述查询需求
   - AI 辅助细胞分析
   - RAG 增强检索结果

---

## 安装运行

### 环境要求
- Python 3.8+
- pip 包管理器

### 安装依赖
```bash
pip install -r requirements.txt
```

### 完整运行流程

```bash
# 1. 数据处理（可选，已有数据文件）
python data_loader.py          # 读取原始 h5ad
python vector_processor.py     # 向量化与清洗

# 2. 生成可视化数据（可选）
python scripts/dataset_analysis.py generate-viz --all

# 3. 性能评估（可选）
python scripts/dataset_analysis.py evaluate --all

# 4. 启动后端服务
python app.py
```

### 访问服务
- 前端界面：http://127.0.0.1:5000
- API 文档：见 API_USAGE.md

---

## 项目结构

```
single-cell-ann-project/
├── 核心模块
│   ├── data_loader.py            # 数据读取
│   ├── vector_processor.py       # 向量化处理
│   ├── hnsw_index.py             # 自实现 HNSW
│   ├── search_engine.py          # 统一搜索引擎
│   ├── dataset_manager.py        # 数据集管理
│   └── performance_evaluator.py  # 性能评估
│
├── 搜索服务
│   ├── ann_search_service.py     # FAISS 搜索
│   └── hnsw_search_service.py    # HNSW 搜索
│
├── 后端服务
│   ├── app.py                    # Flask API 服务
│   └── auth_manager.py           # 用户认证
│
├── 前端界面
│   ├── templates/index.html      # 主页面
│   ├── static/css/style.css      # 样式
│   └── static/js/main.js         # 交互逻辑
│
├── 工具脚本
│   └── scripts/dataset_analysis.py # 数据集分析与评估
│
└── 配置与文档
    ├── config/                   # 配置文件
    ├── datasets/                 # 数据集存储
    ├── docs/                     # 评测报告
    ├── README.MD                 # 本文件
    └── API_USAGE.md              # API 文档
```

---

## 核心模块说明

### hnsw_index.py - 自实现 HNSW

**参数配置**：
```python
M=16                    # 每层最大连接数
efConstruction=200      # 构建时搜索范围
ef=150                  # 查询时搜索范围
```

**算法改进**：
1. **多样化邻居选择** - 使用 HNSW 论文启发式算法
2. **完整分层搜索** - 从最高层粗粒度导航
3. **紧凑索引格式** - 2D 数组存储，文件体积约 20MB

### performance_evaluator.py - 性能评估

**评测配置**：
- 使用全部向量
- 仅评测 K=10
- 查询优先使用未参与索引构建的数据

**评测对比**：
1. FAISS_Flat - 暴力搜索，100%召回
2. FAISS_IVFFlat - 倒排索引
3. FAISS_IVFPQ - 乘积量化
4. FAISS_HNSW - FAISS 官方实现
5. HNSW_self - 本项目自实现

### 功能测试
```bash
python tests/run_all_tests.py
```
## 前端功能

### 主要界面
1. **数据集管理** - 上传、切换、删除数据集
2. **相似细胞检索** - 输入细胞 ID，查询 Top-K 结果
3. **条件过滤** - 按细胞类型、疾病状态筛选
4. **可视化展示** - PCA/UMAP 散点图，支持交互查询
5. **索引状态** - 查看索引信息，切换引擎（FAISS/HNSW）
6. **AI 查询** - 自然语言描述检索需求

---

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/index/status` | GET | 查看索引状态 |
| `/api/index/switch` | POST | 切换索引引擎 |
| `/api/search` | POST | Top-K 检索（支持条件过滤） |
| `/api/cells/<cell_id>` | GET | 查询单个细胞信息 |
| `/api/cell-types` | GET | 获取所有细胞类型 |
| `/api/visualization-data` | GET | 获取可视化数据 |

完整 API 文档见 API_USAGE.md。

---

## 性能说明

自实现 HNSW 使用纯 Python，构建和查询速度低于 FAISS C++ 实现。这是编程语言层面的差距，非算法问题。纯 Python 实现适合教学演示和小规模实验。生产环境建议使用 FAISS。
