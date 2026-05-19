import numpy as np
import pandas as pd
import os
from typing import Tuple, Optional, Dict, Any
import warnings


class DataValidationError(Exception):
    """数据校验异常"""
    pass


class VectorProcessor:
    """
    单细胞数据向量化处理类
    提供数据校验、清洗、向量化和FAISS索引构建功能
    """
    
    def __init__(self, pca_path: str = "pca_vectors.npy", metadata_path: str = "cell_metadata.csv"):
        """
        初始化 VectorProcessor
        
        Args:
            pca_path: PCA向量文件路径
            metadata_path: 细胞元数据文件路径
        """
        self.pca_path = pca_path
        self.metadata_path = metadata_path
        self.pca_vectors = None
        self.metadata = None
        self.cleaned_vectors = None
        self.cleaned_metadata = None
    
    def load_data(self) -> Tuple[np.ndarray, pd.DataFrame]:
        """
        加载PCA向量和细胞元数据
        
        Returns:
            (pca_vectors, metadata) 元组
        """
        if not os.path.exists(self.pca_path):
            raise FileNotFoundError(f"PCA向量文件不存在: {self.pca_path}")
        
        if not os.path.exists(self.metadata_path):
            raise FileNotFoundError(f"元数据文件不存在: {self.metadata_path}")
        
        try:
            self.pca_vectors = np.load(self.pca_path)
            print(f"成功加载PCA向量: 形状={self.pca_vectors.shape}, 数据类型={self.pca_vectors.dtype}")
        except Exception as e:
            raise DataValidationError(f"加载PCA向量失败: {str(e)}")
        
        try:
            self.metadata = pd.read_csv(self.metadata_path, encoding="utf-8-sig", low_memory=False)
            print(f"成功加载元数据: {self.metadata.shape[0]} 个细胞")
        except Exception as e:
            raise DataValidationError(f"加载元数据失败: {str(e)}")
        
        return self.pca_vectors, self.metadata
    
    def validate_consistency(self) -> Dict[str, Any]:
        """
        校验PCA向量与细胞元数据一致性
        
        Returns:
            校验结果字典
        """
        if self.pca_vectors is None or self.metadata is None:
            self.load_data()
        
        results = {
            "valid": True,
            "messages": [],
            "pca_shape": self.pca_vectors.shape,
            "metadata_count": len(self.metadata)
        }
        
        if self.pca_vectors.shape[0] != len(self.metadata):
            results["valid"] = False
            results["messages"].append(
                f"PCA向量数量({self.pca_vectors.shape[0]})与细胞元数据数量({len(self.metadata)})不一致"
            )
        
        if np.isnan(self.pca_vectors).any():
            results["valid"] = False
            nan_count = np.isnan(self.pca_vectors).sum()
            results["messages"].append(f"PCA向量中存在 {nan_count} 个NaN值")
        
        if np.isinf(self.pca_vectors).any():
            results["valid"] = False
            inf_count = np.isinf(self.pca_vectors).sum()
            results["messages"].append(f"PCA向量中存在 {inf_count} 个Inf值")
        
        if self.pca_vectors.dtype != np.float32:
            results["messages"].append(f"警告: PCA向量数据类型为{self.pca_vectors.dtype}，建议使用float32")
        
        if results["valid"]:
            results["messages"].append("数据一致性校验通过")
        
        for msg in results["messages"]:
            print(f"[校验] {msg}")
        
        return results
    
    def clean_data(self, remove_nan: bool = True, remove_inf: bool = True, 
                   normalize: bool = False) -> Tuple[np.ndarray, pd.DataFrame]:
        """
        数据清洗
        
        Args:
            remove_nan: 是否移除含有NaN的样本
            remove_inf: 是否移除含有Inf的样本
            normalize: 是否对向量进行L2归一化
            
        Returns:
            (cleaned_vectors, cleaned_metadata) 元组
        """
        if self.pca_vectors is None or self.metadata is None:
            self.load_data()
        
        vectors = self.pca_vectors.copy()
        metadata = self.metadata.copy()
        
        print("\n开始数据清洗...")
        
        mask = np.ones(len(vectors), dtype=bool)
        
        if remove_nan:
            nan_mask = ~np.isnan(vectors).any(axis=1)
            removed_nan = (~nan_mask).sum()
            if removed_nan > 0:
                print(f"移除 {removed_nan} 个含有NaN的样本")
            mask = mask & nan_mask
        
        if remove_inf:
            inf_mask = ~np.isinf(vectors).any(axis=1)
            removed_inf = (~inf_mask).sum()
            if removed_inf > 0:
                print(f"移除 {removed_inf} 个含有Inf的样本")
            mask = mask & inf_mask
        
        cleaned_vectors = vectors[mask]
        cleaned_metadata = metadata.iloc[mask].reset_index(drop=True)
        
        if normalize:
            norms = np.linalg.norm(cleaned_vectors, axis=1, keepdims=True)
            norms[norms == 0] = 1
            cleaned_vectors = cleaned_vectors / norms
            print("已对向量进行L2归一化")
        
        print(f"清洗完成: 保留 {len(cleaned_vectors)} 个样本")
        
        self.cleaned_vectors = cleaned_vectors
        self.cleaned_metadata = cleaned_metadata
        
        return cleaned_vectors, cleaned_metadata
    
    def get_vectors(self, use_cleaned: bool = True, dtype: np.dtype = np.float32) -> np.ndarray:
        """
        获取标准格式的向量化数据
        
        Args:
            use_cleaned: 是否使用清洗后的数据
            dtype: 目标数据类型
            
        Returns:
            向量化数据数组
        """
        if use_cleaned:
            if self.cleaned_vectors is None:
                self.clean_data()
            vectors = self.cleaned_vectors
        else:
            if self.pca_vectors is None:
                self.load_data()
            vectors = self.pca_vectors
        
        if vectors.dtype != dtype:
            vectors = vectors.astype(dtype)
        
        return vectors
    
    def get_metadata(self, use_cleaned: bool = True) -> pd.DataFrame:
        """
        获取元数据
        
        Args:
            use_cleaned: 是否使用清洗后的元数据
            
        Returns:
            元数据DataFrame
        """
        if use_cleaned:
            if self.cleaned_metadata is None:
                self.clean_data()
            return self.cleaned_metadata
        else:
            if self.metadata is None:
                self.load_data()
            return self.metadata
    
    def save_cleaned_data(self, vectors_path: str = "cleaned_pca_vectors.npy", 
                          metadata_path: str = "cleaned_cell_metadata.csv"):
        """
        保存清洗后的数据
        
        Args:
            vectors_path: 清洗后PCA向量保存路径
            metadata_path: 清洗后元数据保存路径
        """
        if self.cleaned_vectors is None or self.cleaned_metadata is None:
            self.clean_data()
        
        np.save(vectors_path, self.cleaned_vectors.astype(np.float32))
        self.cleaned_metadata.to_csv(metadata_path, index=False, encoding="utf-8-sig")
        
        print(f"\n清洗后数据已保存:")
        print(f"  PCA向量: {vectors_path}, 形状={self.cleaned_vectors.shape}")
        print(f"  元数据: {metadata_path}")


class FAISSIndexBuilder:
    """
    FAISS索引构建器
    """
    
    def __init__(self, vectors: Optional[np.ndarray] = None):
        """
        初始化FAISS索引构建器
        
        Args:
            vectors: 用于构建索引的向量数据
        """
        self.vectors = vectors
        self.index = None
        self.index_type = None
    
    def set_vectors(self, vectors: np.ndarray):
        """
        设置向量数据
        
        Args:
            vectors: 向量数据数组，形状为(n_samples, n_dimensions)
        """
        if vectors.dtype != np.float32:
            vectors = vectors.astype(np.float32)
        self.vectors = vectors
    
    def build_index(self, index_type: str = "ivfflat", nlist: int = 100, 
                    m: int = 8, nbits: int = 8) -> Any:
        """
        构建FAISS索引
        
        Args:
            index_type: 索引类型 ('flat', 'ivfflat', 'ivfpq')
            nlist: IVF索引的分桶数量（仅IVF类型）
            m: PQ编码的子向量数量（仅IVFPQ类型）
            nbits: PQ编码每个子向量的比特数（仅IVFPQ类型）
            
        Returns:
            FAISS索引对象
        """
        if self.vectors is None:
            raise ValueError("请先设置向量数据")
        
        try:
            import faiss
        except ImportError:
            raise ImportError("请先安装faiss: pip install faiss-cpu 或 faiss-gpu")
        
        n, d = self.vectors.shape
        self.index_type = index_type
        
        print(f"\n开始构建FAISS索引...")
        print(f"向量数量: {n}, 维度: {d}")
        print(f"索引类型: {index_type}")
        
        if index_type == "flat":
            self.index = faiss.IndexFlatL2(d)
            self.index.add(self.vectors)
        
        elif index_type == "ivfflat":
            quantizer = faiss.IndexFlatL2(d)
            self.index = faiss.IndexIVFFlat(quantizer, d, nlist)
            self.index.train(self.vectors)
            self.index.add(self.vectors)
            print(f"IVF分桶数: {nlist}")
        
        elif index_type == "ivfpq":
            quantizer = faiss.IndexFlatL2(d)
            self.index = faiss.IndexIVFPQ(quantizer, d, nlist, m, nbits)
            self.index.train(self.vectors)
            self.index.add(self.vectors)
            print(f"IVF分桶数: {nlist}, PQ子向量数: {m}, 比特数: {nbits}")
        
        else:
            raise ValueError(f"不支持的索引类型: {index_type}")
        
        print(f"索引构建完成!")
        
        return self.index
    
    def search(self, query_vectors: np.ndarray, k: int = 10, 
               nprobe: Optional[int] = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        使用构建好的索引进行搜索
        
        Args:
            query_vectors: 查询向量，形状为(n_queries, n_dimensions)
            k: 返回最近邻的数量
            nprobe: IVF索引的搜索探针数量（仅IVF类型）
            
        Returns:
            (distances, indices) 元组
            - distances: 距离数组，形状为(n_queries, k)
            - indices: 索引数组，形状为(n_queries, k)
        """
        if self.index is None:
            raise ValueError("请先构建索引")
        
        if query_vectors.dtype != np.float32:
            query_vectors = query_vectors.astype(np.float32)
        
        if nprobe is not None and hasattr(self.index, 'nprobe'):
            self.index.nprobe = nprobe
            print(f"设置搜索探针数: {nprobe}")
        
        distances, indices = self.index.search(query_vectors, k)
        
        return distances, indices
    
    def save_index(self, file_path: str = "faiss_index.bin"):
        """
        保存FAISS索引到文件
        
        Args:
            file_path: 索引文件保存路径
        """
        if self.index is None:
            raise ValueError("请先构建索引")
        
        try:
            import faiss
        except ImportError:
            raise ImportError("请先安装faiss: pip install faiss-cpu 或 faiss-gpu")
        
        faiss.write_index(self.index, file_path)
        print(f"\nFAISS索引已保存到: {file_path}")
    
    @staticmethod
    def load_index(file_path: str = "faiss_index.bin") -> Any:
        """
        从文件加载FAISS索引
        
        Args:
            file_path: 索引文件路径
            
        Returns:
            FAISS索引对象
        """
        try:
            import faiss
        except ImportError:
            raise ImportError("请先安装faiss: pip install faiss-cpu 或 faiss-gpu")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"索引文件不存在: {file_path}")
        
        index = faiss.read_index(file_path)
        print(f"FAISS索引已从 {file_path} 加载")
        
        return index


def main():
    """
    主函数：演示完整流程
    """
    print("=" * 60)
    print("单细胞数据向量化处理与FAISS索引构建")
    print("=" * 60)
    
    processor = VectorProcessor()
    
    print("\n[步骤1] 加载数据")
    processor.load_data()
    
    print("\n[步骤2] 数据一致性校验")
    validation_result = processor.validate_consistency()
    
    print("\n[步骤3] 数据清洗")
    cleaned_vectors, cleaned_metadata = processor.clean_data(normalize=False)
    
    print("\n[步骤4] 保存清洗后数据")
    processor.save_cleaned_data()
    
    print("\n[步骤5] 构建FAISS索引")
    try:
        index_builder = FAISSIndexBuilder(cleaned_vectors)
        
        index = index_builder.build_index(index_type="ivfflat", nlist=100)
        index_builder.save_index("faiss_index.bin")
        
        print("\n[步骤6] 测试搜索（使用前5个向量作为查询）")
        test_queries = cleaned_vectors[:5]
        distances, indices = index_builder.search(test_queries, k=5, nprobe=10)
        
        print("\n搜索结果示例 (前3个查询):")
        for i in range(min(3, len(test_queries))):
            print(f"\n查询 {i+1}:")
            print(f"  最近邻索引: {indices[i]}")
            print(f"  对应距离: {distances[i]}")
    
    except ImportError as e:
        print(f"\n警告: {e}")
        print("跳过FAISS索引构建步骤。如需使用，请安装faiss。")
    
    print("\n" + "=" * 60)
    print("处理完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
