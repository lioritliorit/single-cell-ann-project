# 性能评测报告

生成时间：2026-06-10 17:45:55

## 跨数据集性能对比

以下表格展示各数据集中默认 K 值下的主要索引方法性能。

| 数据集 | 组别 | 细胞数 | 方法 | 构建时间(s) | 查询时间(s) | 召回率 | 精确率 |
|---|---|---|---|---|---|---|---|
| default | regular | 69032 | FAISS_Flat | 0.0000 | 0.0010 | 1.0000 | 1.0000 |
| default | regular | 69032 | FAISS_IVFFlat (nlist=100) | 0.0187 | 0.0000 | 1.0000 | 1.0000 |
| default | regular | 69032 | FAISS_IVFPQ (nlist=100, m=6, nbits=8) | 0.0690 | 0.0010 | 0.8160 | 0.8160 |
| default | regular | 69032 | FAISS_HNSW (M=16) | 0.0501 | 0.0000 | 1.0000 | 1.0000 |
| default | regular | 69032 | HNSW_self (M=16) | 97.1045 | 1.1626 | 1.0000 | 1.0000 |
| ds-liver | liver_disease | 69032 | FAISS_Flat | 0.0015 | 0.0036 | 1.0000 | 1.0000 |
| ds-liver | liver_disease | 69032 | FAISS_IVFFlat (nlist=100) | 0.0345 | 0.0010 | 1.0000 | 1.0000 |
| ds-liver | liver_disease | 69032 | FAISS_IVFPQ (nlist=100, m=6, nbits=8) | 0.1552 | 0.0000 | 0.8160 | 0.8160 |
| ds-liver | liver_disease | 69032 | FAISS_HNSW (M=16) | 0.0897 | 0.0015 | 1.0000 | 1.0000 |
| ds-liver | liver_disease | 69032 | HNSW_self (M=16) | 85.8208 | 0.1736 | 0.9660 | 0.9660 |
| joint-default-ds-liver | joint | 138064 | FAISS_Flat | 0.0000 | 0.0032 | 1.0000 | 1.0000 |
| joint-default-ds-liver | joint | 138064 | FAISS_IVFFlat (nlist=100) | 0.0439 | 0.0005 | 0.9960 | 0.9960 |
| joint-default-ds-liver | joint | 138064 | FAISS_IVFPQ (nlist=100, m=6, nbits=8) | 0.1423 | 0.0016 | 0.8060 | 0.8060 |
| joint-default-ds-liver | joint | 138064 | FAISS_HNSW (M=16) | 0.0854 | 0.0015 | 0.9980 | 0.9980 |
| joint-default-ds-liver | joint | 138064 | HNSW_self (M=16) | 109.8707 | 0.2099 | 0.8660 | 0.8660 |

## 联合数据集对比分析

下面的对比展示了联合数据集与单数据集在默认 K 值下的检索性能差异。

| 方法 | 数据集 | 召回率 | 精确率 | 查询时间(s) |
|---|---|---|---|---|
| FAISS_HNSW (M=16) | joint-default-ds-liver | 0.9980 | 0.9980 | 0.0015 |
| FAISS_HNSW (M=16) | default | 1.0000 | 1.0000 | 0.0000 |
| FAISS_HNSW (M=16) | ds-liver | 1.0000 | 1.0000 | 0.0015 |
| HNSW_self (M=16) | joint-default-ds-liver | 0.8660 | 0.8660 | 0.2099 |
| HNSW_self (M=16) | default | 1.0000 | 1.0000 | 1.1626 |
| HNSW_self (M=16) | ds-liver | 0.9660 | 0.9660 | 0.1736 |
| FAISS_IVFFlat (nlist=100) | joint-default-ds-liver | 0.9960 | 0.9960 | 0.0005 |
| FAISS_IVFFlat (nlist=100) | default | 1.0000 | 1.0000 | 0.0000 |
| FAISS_IVFFlat (nlist=100) | ds-liver | 1.0000 | 1.0000 | 0.0010 |

## 元数据分布差异分析

以下内容用于比较不同数据集中的正常/病例比例及主要疾病标签。

| 数据集 | 正常细胞数 | 病例细胞数 | 正常比例 | 主要疾病标签 |
|---|---|---|---|---|
| default | 69032 | 0 | 1.0000 |  |
| ds-liver | 20682 | 48350 | 0.2996 | cirrhosis, hepatitis, fibrosis, hcc |
| joint-default-ds-liver | 89714 | 48350 | 0.6498 | cirrhosis, hepatitis, fibrosis, hcc |

## 数据集 default (Default single-cell dataset)

- 分组: regular
- 细胞数: 69032
- 向量维度: 30

### 肝病 / 正常细胞分布分析

- 正常细胞: 69032
- 病例细胞: 0
- 正常比例: 1.0000
- 主要疾病标签: 

### 默认 K 值评测结果

| 方法 | 构建时间(s) | 查询时间(s) | 内存(MB) | 召回率 | 精确率 |
|------|------------|------------|----------|--------|--------|
| FAISS_Flat | 0.0000 | 0.0010 | 1.14 | 1.0000 | 1.0000 |
| FAISS_IVFFlat (nlist=100) | 0.0187 | 0.0000 | 1.31 | 1.0000 | 1.0000 |
| FAISS_IVFPQ (nlist=100, m=6, nbits=8) | 0.0690 | 0.0010 | 0.66 | 0.8160 | 0.8160 |
| FAISS_HNSW (M=16) | 0.0501 | 0.0000 | 1.23 | 1.0000 | 1.0000 |
| HNSW_self (M=16) | 97.1045 | 1.1626 | 1.10 | 1.0000 | 1.0000 |

### 不同 K 值召回率对比

| K | 方法 | 召回率 | 精确率 |
|---|------|--------|--------|
| 5 | FAISS_Flat | 1.0000 | 1.0000 |
| 5 | FAISS_IVFFlat (nlist=100) | 1.0000 | 1.0000 |
| 5 | FAISS_IVFPQ (nlist=100, m=6, nbits=8) | 0.7760 | 0.7760 |
| 5 | FAISS_HNSW (M=16) | 1.0000 | 1.0000 |
| 5 | HNSW_self (M=16) | 0.8480 | 0.8480 |
| 10 | FAISS_Flat | 1.0000 | 1.0000 |
| 10 | FAISS_IVFFlat (nlist=100) | 1.0000 | 1.0000 |
| 10 | FAISS_IVFPQ (nlist=100, m=6, nbits=8) | 0.8160 | 0.8160 |
| 10 | FAISS_HNSW (M=16) | 1.0000 | 1.0000 |
| 10 | HNSW_self (M=16) | 1.0000 | 1.0000 |
| 20 | FAISS_Flat | 1.0000 | 1.0000 |
| 20 | FAISS_IVFFlat (nlist=100) | 1.0000 | 1.0000 |
| 20 | FAISS_IVFPQ (nlist=100, m=6, nbits=8) | 0.8620 | 0.8620 |
| 20 | FAISS_HNSW (M=16) | 1.0000 | 1.0000 |
| 20 | HNSW_self (M=16) | 0.3090 | 0.3090 |

## 数据集 ds-liver (liver)

- 分组: liver_disease
- 细胞数: 69032
- 向量维度: 30

### 肝病 / 正常细胞分布分析

- 正常细胞: 20682
- 病例细胞: 48350
- 正常比例: 0.2996
- 主要疾病标签: cirrhosis, hepatitis, fibrosis, hcc

### 默认 K 值评测结果

| 方法 | 构建时间(s) | 查询时间(s) | 内存(MB) | 召回率 | 精确率 |
|------|------------|------------|----------|--------|--------|
| FAISS_Flat | 0.0015 | 0.0036 | 1.14 | 1.0000 | 1.0000 |
| FAISS_IVFFlat (nlist=100) | 0.0345 | 0.0010 | 0.39 | 1.0000 | 1.0000 |
| FAISS_IVFPQ (nlist=100, m=6, nbits=8) | 0.1552 | 0.0000 | 0.80 | 0.8160 | 0.8160 |
| FAISS_HNSW (M=16) | 0.0897 | 0.0015 | 0.76 | 1.0000 | 1.0000 |
| HNSW_self (M=16) | 85.8208 | 0.1736 | 0.66 | 0.9660 | 0.9660 |

### 不同 K 值召回率对比

| K | 方法 | 召回率 | 精确率 |
|---|------|--------|--------|
| 5 | FAISS_Flat | 1.0000 | 1.0000 |
| 5 | FAISS_IVFFlat (nlist=100) | 1.0000 | 1.0000 |
| 5 | FAISS_IVFPQ (nlist=100, m=6, nbits=8) | 0.7760 | 0.7760 |
| 5 | FAISS_HNSW (M=16) | 1.0000 | 1.0000 |
| 5 | HNSW_self (M=16) | 0.9040 | 0.9040 |
| 10 | FAISS_Flat | 1.0000 | 1.0000 |
| 10 | FAISS_IVFFlat (nlist=100) | 1.0000 | 1.0000 |
| 10 | FAISS_IVFPQ (nlist=100, m=6, nbits=8) | 0.8160 | 0.8160 |
| 10 | FAISS_HNSW (M=16) | 1.0000 | 1.0000 |
| 10 | HNSW_self (M=16) | 0.9660 | 0.9660 |
| 20 | FAISS_Flat | 1.0000 | 1.0000 |
| 20 | FAISS_IVFFlat (nlist=100) | 1.0000 | 1.0000 |
| 20 | FAISS_IVFPQ (nlist=100, m=6, nbits=8) | 0.8620 | 0.8620 |
| 20 | FAISS_HNSW (M=16) | 1.0000 | 1.0000 |
| 20 | HNSW_self (M=16) | 0.8660 | 0.8660 |

## 数据集 joint-default-ds-liver (Joint default + ds-liver)

- 分组: joint
- 细胞数: 138064
- 向量维度: 30

### 肝病 / 正常细胞分布分析

- 正常细胞: 89714
- 病例细胞: 48350
- 正常比例: 0.6498
- 主要疾病标签: cirrhosis, hepatitis, fibrosis, hcc

### 默认 K 值评测结果

| 方法 | 构建时间(s) | 查询时间(s) | 内存(MB) | 召回率 | 精确率 |
|------|------------|------------|----------|--------|--------|
| FAISS_Flat | 0.0000 | 0.0032 | 1.14 | 1.0000 | 1.0000 |
| FAISS_IVFFlat (nlist=100) | 0.0439 | 0.0005 | 0.19 | 0.9960 | 0.9960 |
| FAISS_IVFPQ (nlist=100, m=6, nbits=8) | 0.1423 | 0.0016 | 0.77 | 0.8060 | 0.8060 |
| FAISS_HNSW (M=16) | 0.0854 | 0.0015 | 0.66 | 0.9980 | 0.9980 |
| HNSW_self (M=16) | 109.8707 | 0.2099 | 1.20 | 0.8660 | 0.8660 |

### 不同 K 值召回率对比

| K | 方法 | 召回率 | 精确率 |
|---|------|--------|--------|
| 5 | FAISS_Flat | 1.0000 | 1.0000 |
| 5 | FAISS_IVFFlat (nlist=100) | 1.0000 | 1.0000 |
| 5 | FAISS_IVFPQ (nlist=100, m=6, nbits=8) | 0.7840 | 0.7840 |
| 5 | FAISS_HNSW (M=16) | 1.0000 | 1.0000 |
| 5 | HNSW_self (M=16) | 0.8840 | 0.8840 |
| 10 | FAISS_Flat | 1.0000 | 1.0000 |
| 10 | FAISS_IVFFlat (nlist=100) | 0.9960 | 0.9960 |
| 10 | FAISS_IVFPQ (nlist=100, m=6, nbits=8) | 0.8060 | 0.8060 |
| 10 | FAISS_HNSW (M=16) | 0.9980 | 0.9980 |
| 10 | HNSW_self (M=16) | 0.8660 | 0.8660 |
| 20 | FAISS_Flat | 1.0000 | 1.0000 |
| 20 | FAISS_IVFFlat (nlist=100) | 0.9920 | 0.9920 |
| 20 | FAISS_IVFPQ (nlist=100, m=6, nbits=8) | 0.8270 | 0.8270 |
| 20 | FAISS_HNSW (M=16) | 1.0000 | 1.0000 |
| 20 | HNSW_self (M=16) | 0.8610 | 0.8610 |
