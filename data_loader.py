import scanpy as sc
import numpy as np
import pandas as pd


def load_h5ad(file_path):
    """
    读取 h5ad 格式的单细胞数据文件
    """
    adata = sc.read_h5ad(file_path)
    return adata


def inspect_adata(adata):
    """
    查看 AnnData 对象的基本结构
    """
    print("===== AnnData 基本信息 =====")
    print(adata)

    print("\n===== 数据规模 =====")
    print("细胞数量:", adata.n_obs)
    print("基因数量:", adata.n_vars)

    print("\n===== obs 字段 =====")
    print(adata.obs.columns.tolist())

    print("\n===== var 字段 =====")
    print(adata.var.columns.tolist())

    print("\n===== obsm 字段 =====")
    print(list(adata.obsm.keys()))

    print("\n===== layers 字段 =====")
    print(list(adata.layers.keys()))


def extract_cell_metadata(adata, output_path="cell_metadata.csv"):
    """
    提取细胞元信息，供后续检索结果展示使用
    """
    metadata = adata.obs.copy()
    metadata.insert(0, "cell_id", metadata.index)

    metadata.to_csv(output_path, index=False, encoding="utf-8-sig")

    print("\n细胞元信息已保存到:", output_path)
    print(metadata.head())

    return metadata


def export_pca_vectors(adata, output_path="pca_vectors.npy"):
    """
    提取 PCA 向量，供 ANN 索引构建模块使用
    """
    if "X_pca" not in adata.obsm:
        raise ValueError("当前 h5ad 文件中没有 X_pca，无法直接导出 PCA 向量")

    vectors = adata.obsm["X_pca"].astype("float32")
    np.save(output_path, vectors)

    print("\nPCA 向量已保存到:", output_path)
    print("PCA 向量形状:", vectors.shape)

    return vectors


def export_summary_tables(adata):
    """
    输出细胞类型、疾病状态、年龄分组等统计结果
    """
    if "cell_type" in adata.obs.columns:
        cell_type_count = adata.obs["cell_type"].value_counts()
        cell_type_count.to_csv("cell_type_count.csv", encoding="utf-8-sig")
        print("\n细胞类型统计:")
        print(cell_type_count)

    if "disease" in adata.obs.columns:
        disease_count = adata.obs["disease"].value_counts()
        disease_count.to_csv("disease_count.csv", encoding="utf-8-sig")
        print("\n疾病状态统计:")
        print(disease_count)

    if "AgeGroup" in adata.obs.columns:
        age_group_count = adata.obs["AgeGroup"].value_counts()
        age_group_count.to_csv("age_group_count.csv", encoding="utf-8-sig")
        print("\n年龄分组统计:")
        print(age_group_count)


def main():
    file_path = "liver.h5ad"

    adata = load_h5ad(file_path)

    inspect_adata(adata)

    extract_cell_metadata(adata)

    export_pca_vectors(adata)

    export_summary_tables(adata)

    print("\n数据导入与解析任务完成。")


if __name__ == "__main__":
    main()