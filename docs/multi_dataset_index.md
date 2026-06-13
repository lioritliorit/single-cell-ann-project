# 多数据集联合索引实现说明

## 目标

本项目现在支持 h5ad 数据集上传、删除、切换和跨数据集联合检索。每个数据集会维护独立的向量、元数据和 FAISS 索引；联合索引会把多个数据集的 PCA 向量按行合并，并在元数据中保留来源字段，便于检索结果回溯和条件过滤。

## 存储结构

```text
datasets/
  manifest.json                 # 全量数据集注册表和活动数据集
  uploads/<dataset_id>.h5ad      # 上传的原始 h5ad
  processed/<dataset_id>/
    vectors.npy                  # 清洗后的 X_pca
    metadata.csv                 # obs + dataset_* 来源字段
    faiss_index.bin              # 自动构建的 FAISS FlatL2 索引
  joint/<joint_id>/
    vectors.npy
    metadata.csv
    faiss_index.bin
```

默认项目自带的 `cleaned_pca_vectors.npy`、`cleaned_cell_metadata.csv`、`faiss_index.bin` 会注册为 `default` 数据集。`default` 不会被删除。

## 上传与动态索引

Web 页面入口：`数据集管理 -> 上传并建索引`

后端接口：

```http
POST /api/datasets/upload
Content-Type: multipart/form-data

file=<*.h5ad>
name=liver disease cohort
source=GEO / local / paper
group=liver_disease
description=...
tags=liver,cirrhosis
```

处理流程：

1. 读取 h5ad，要求存在 `adata.obsm["X_pca"]`。
2. 导出 `adata.obs` 为 `metadata.csv`，自动补充 `cell_id`、`dataset_id`、`dataset_name`、`dataset_group`、`dataset_source`。
3. 清理包含 NaN/Inf 的向量行，并同步裁剪元数据。
4. 使用 `faiss.IndexFlatL2` 构建索引并保存。
5. 更新 `datasets/manifest.json`，并自动切换为活动数据集。

命令行等价操作：

```bash
python scripts/dataset_admin.py import liver_disease.h5ad --name liver-disease --source GEO --group liver_disease --tags liver,cirrhosis
```

## 删除、切换与缓存清理

删除接口会同步移除上传文件、处理后的向量、元数据、索引文件和处理目录：

```http
DELETE /api/datasets/<dataset_id>
```

命令行：

```bash
python scripts/dataset_admin.py delete ds-liver-disease
```

切换接口：

```http
POST /api/datasets/switch
Content-Type: application/json

{"dataset_id": "default"}
```

命令行：

```bash
python scripts/dataset_admin.py switch default
```

## 联合索引

Web 页面中勾选至少两个数据集，点击“构建所选联合索引”。后端会校验所有数据集 PCA 维度一致，然后合并向量和元数据。

接口：

```http
POST /api/datasets/joint-index
Content-Type: application/json

{
  "dataset_ids": ["default", "ds-liver-disease"],
  "name": "regular + liver disease",
  "group": "joint",
  "description": "Cross-library retrieval index"
}
```

命令行：

```bash
python scripts/dataset_admin.py joint default ds-liver-disease --name regular-liver-joint --group joint
```

联合索引结果会注册为新的 `kind=joint` 数据集，并自动切换为活动数据集。检索结果保留 `dataset_id`、`dataset_name`、`dataset_group`，可在 Web 检索表格中查看，也可通过过滤器限制：

```json
{
  "cell_id": "AAACCTGAGCAGGTCA-1_2",
  "k": 10,
  "filters": {
    "dataset_group": "liver_disease"
  }
}
```

## 肝病数据分组

分组配置见 `config/liver_groups.json`。

推荐导入肝病专题数据时使用：

```text
group = liver_disease
tags = liver, hepatitis, cirrhosis, fibrosis, hcc 等
```

常规参考库使用：

```text
group = regular
```

联合索引自动使用：

```text
group = joint
```

## 注意事项

- 上传 h5ad 必须包含 `X_pca`，当前实现不在 Web 请求中重新计算 PCA。
- 联合索引要求所有参与数据集向量维度一致。
- 上传数据集默认只构建 FAISS 索引；HNSW 切换仅适用于存在 `hnsw_index_path` 的数据集，例如项目默认数据集。
