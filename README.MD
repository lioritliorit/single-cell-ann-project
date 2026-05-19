# 单细胞数据读取模块说明

## 1. 数据文件

本项目使用老师提供的 `liver.h5ad` 单细胞数据文件，数据采用 AnnData 格式存储。

## 2. 数据规模

- 细胞数量：69032
- 基因数量：32397
- PCA向量维度：30

## 3. AnnData主要字段

- `X`：细胞 × 基因表达矩阵
- `obs`：细胞元信息
- `var`：基因元信息
- `obsm`：降维后的向量表示，包括 `X_pca`、`X_tsne`、`X_umap`
- `uns`：数据集描述信息
- `layers`：当前数据中为空

## 4. 输出文件

### cell_metadata.csv

保存每个细胞的元信息，包括：

- cell_id
- cell_type
- disease
- AgeGroup
- sex
- tissue
- development_stage
- nCount_RNA
- nFeature_RNA
- percent.mt

该文件用于 ANN 检索结果展示。

### pca_vectors.npy

保存从 `adata.obsm["X_pca"]` 中提取的 PCA 向量。

形状为：
(69032, 30)
其中每一行对应一个细胞，每一列对应一个 PCA 维度。
该文件可直接用于 ANN 索引构建。

### cell_type_count.csv

保存不同细胞类型的数量统计。

### disease_count.csv

保存疾病状态统计。本数据集中所有细胞均为 normal。

### age_group_count.csv

保存年龄分组统计，包括 Ped 和 Adult。

## 总结
目前输出了以下文件：

1. pca_vectors.npy
   - 形状为 69032 × 30
   - 每一行对应一个细胞的 PCA 向量
   - 可直接用于 ANN 索引构建

2. cell_metadata.csv
   - 保存每个细胞的元信息
   - ANN 检索返回的索引编号可以用 metadata.iloc[indices] 映射成具体细胞信息

3. cell_type_count.csv / disease_count.csv / age_group_count.csv
   - 用于报告和可视化展示