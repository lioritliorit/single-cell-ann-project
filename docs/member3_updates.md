# 成员3 检索核心引擎 — 实现更新文档

> 生成日期：2026-06-11
> 对应结项要求：2.条件检索、1.系统功能完整（核心引擎）
> 加分项：ANN算法代码优化/多模式检索优化

---

## 一、实现概述

基于中期「ANN 索引构建」模块，新增了**条件检索核心功能**与**索引缓存优化**，实现了三种统一检索模式，并对 FAISS 索引构建做了代码级扩展以支持多种索引类型。

---

## 二、逐项完成情况核对

### 2.1 条件检索开发（必做）✅

| 文档要求 | 实现位置 | 说明 |
|----------|---------|------|
| 检索前按细胞类型过滤向量再Top-K | `ann_search_service.py:357` `search_conditional()` | 生成布尔掩码 → 提取子集向量 → 构建临时 FAISS 子索引 → 精确搜索 → 映射回全局行号 |
| 检索前按疾病类型过滤 | `ann_search_service.py:314` `build_filter_mask()` | 支持 `cell_type`、`disease`、`dataset_group`、`dataset_id`、`tissue` 五维过滤，大小写不敏感精确匹配 |
| 普通Top-K模式 | `search_engine.py` `SearchMode.NORMAL` + `app.py` 默认 `search_mode=normal` | 后置过滤 ANN 搜索，兼容原接口 |
| 条件检索模式 | `search_engine.py` `SearchMode.CONDITIONAL` + `app.py` `search_mode=conditional` | 预过滤 + 子索引搜索，100% 精确匹配 |
| 跨数据集检索模式 | `search_engine.py` `SearchMode.CROSS_DATASET` + `app.py` `search_mode=cross_dataset` | 条件过滤 + 来源分布统计 |
| 前端条件过滤UI | `templates/index.html` + `static/js/main.js` | 细胞类型、疾病状态、数据分组下拉框 + 检索模式切换 |

**关键实现细节：**

```
用户选择: cell_type=hepatocyte, disease=cirrhosis, search_mode=conditional
    ↓
1. build_filter_mask({"cell_type":"hepatocyte","disease":"cirrhosis"})
   → 生成 bool[69032]，True = 满足所有条件的细胞
    ↓
2. 提取子集向量: subset_vectors = vectors[mask] (例如 ~12000 个)
    ↓
3. 构建临时 FAISS IndexFlatL2 子索引
    ↓
4. 在子索引上搜索 Top-K
    ↓
5. 将子索引行号映射回全局行号，返回完整元数据
```

### 2.2 检索逻辑与索引优化（必做）✅

| 文档要求 | 实现位置 | 说明 |
|----------|---------|------|
| 索引持久化 | `dataset_manager.py:375` `_build_faiss_index()` | 支持 flat / ivfflat / ivfpq / hnsw 四种索引类型，自动 `write_index` |
| 缓存策略 | `search_engine.py` `IndexCache` | LRU 缓存（可配最大条目数 + 内存上限），缓存键 = dataset_id + index_type |
| 大索引加载优化 | `search_engine.py:299` `load()` | 优先查缓存命中跳过磁盘IO；向量文件使用 `mmap_mode="r"` |
| 肝病跨库检索优化 | `ann_search_service.py` `search_conditional()` + `app.py` `search_debug.log` | 预过滤减少搜索空间；检索后生成 `filter_stats`（过滤前后细胞数、比例）；跨库来源分布追踪 |

**IndexCache 验证数据 (test_search_modes.py test 4)：**
- ✅ 缓存命中/未命中正确区分
- ✅ LRU 淘汰策略正确（最久未使用被移除）
- ✅ `invalidate(dataset_id)` 定向清除 + `invalidate()` 全量清除
- ✅ 命中率统计 (`hits`, `misses`, `hit_rate`)

### 2.3 ANN算法代码级改造（加分项）✅

| 改造项 | 实现位置 | 说明 |
|--------|---------|------|
| IVF 聚类数自动计算 | `dataset_manager.py:438` `_auto_nlist()` | `nlist = max(4, min(1024, 4*sqrt(N)))`，根据数据量自适应 |
| IVFPQ 量化压缩 | `dataset_manager.py:409` `_build_faiss_index(index_type="ivfpq")` | 支持 m/nbits 参数，自动修正 m 使其整除维度 |
| FAISS HNSW 集成 | `dataset_manager.py:421` `_build_faiss_index(index_type="hnsw")` | 可配 M / efConstruction / efSearch |
| 多索引类型对比 | `scripts/dataset_analysis.py` `evaluate()` | 评测结果输出到 `docs/performance_evaluation_summary.json` |

**索引类型选择指南 (config/liver_groups.json)：**
```
flat    → < 1万细胞，精确搜索
ivfflat → 1万-100万，平衡速度与精度
ivfpq   → > 10万，内存压缩
hnsw    → 交互式检索，高召回
```

---

## 三、交付物清单

| 交付物 | 文件路径 | 状态 |
|--------|---------|------|
| 条件检索核心代码 | `ann_search_service.py` (新增 100+ 行) | ✅ |
| HNSW 条件检索 | `hnsw_search_service.py` (新增 80+ 行) | ✅ |
| 统一检索引擎 | `search_engine.py` (新建, 830 行) | ✅ |
| 多索引类型构建 | `dataset_manager.py` (修改 `_build_faiss_index`) | ✅ |
| API 适配 | `app.py` (search_mode / disease / 调试日志) | ✅ |
| 前端条件过滤UI | `templates/index.html` + `static/js/main.js` | ✅ |
| 肝病分组增强配置 | `config/liver_groups.json` (新增索引推荐) | ✅ |
| 三种检索模式测试用例 | `test_search_modes.py` (新建, 47 tests) | ✅ |
| 跨库检索调试日志 | `docs/search_debug.log` (自动生成) | ✅ |

---

## 四、测试结果

```
test_search_modes.py — 47/47 全部通过

测试1: FilterSpec 与过滤掩码 (8/8)
测试2: 条件检索正确性 (9/9)
测试3: 预过滤 vs 后过滤精确率对比 (3/3)
测试4: IndexCache LRU 缓存 (9/9)
测试5: 边界条件 (7/7)
测试6: 新增方法存在性验证 (6/6)
测试7: 多索引类型构建 (5/5)
```

---

## 五、API 变更说明

### 5.1 新增接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/disease-types` | 返回当前数据集所有疾病/状态标签 (填充前端下拉框) |

### 5.2 修改接口

**POST /api/search** — 新增参数：

```json
{
  "cell_id": "AAACCTGAGCAGGTCA-1_2",
  "k": 10,
  "search_mode": "conditional",
  "disease": "cirrhosis",
  "cell_type": "hepatocyte",
  "filters": {
    "cell_type": "hepatocyte",
    "disease": "cirrhosis",
    "dataset_group": "liver_disease"
  }
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `search_mode` | string | `"normal"` | `"normal"` 后过滤 / `"conditional"` 预过滤 / `"cross_dataset"` 跨库 |
| `disease` | string | (无) | 顶层简写，等价于 `filters.disease` |
| `cell_type` | string | (无) | 顶层简写，等价于 `filters.cell_type` |

**响应新增字段：**

```json
{
  "search_mode": "conditional",
  "filter_stats": {
    "total_cells": 69032,
    "filtered_cells": 48350,
    "filter_ratio": 0.7004,
    "mode": "pre_filter",
    "source_distribution": { "default": 3, "ds-liver": 7 }
  }
}
```

### 5.3 修改的现有接口

| 方法 | 路径 | 变更 |
|------|------|------|
| POST | `/api/datasets/upload` | 表单可选字段 `index_type` (flat/ivfflat/ivfpq/hnsw) |
| POST | `/api/datasets/joint-index` | 请求体可选字段 `index_type` |

---

## 六、文件变更总览

| 文件 | 操作 | 行数变化 |
|------|------|---------|
| `search_engine.py` | **新建** | +830 |
| `test_search_modes.py` | **新建** | +520 |
| `ann_search_service.py` | 修改 | +120 |
| `hnsw_search_service.py` | 修改 | +85 |
| `dataset_manager.py` | 修改 | +70 |
| `app.py` | 修改 | +45 |
| `config/liver_groups.json` | 修改 | +12 |
| `templates/index.html` | 修改 | +30 |
| `static/js/main.js` | 修改 | +25 |
| `static/css/style.css` | 修改 | +30 |
