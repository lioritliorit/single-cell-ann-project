import numpy as np
import pandas as pd
import time
import os
import sys
from typing import Dict, Any, Tuple
import psutil

def print_flush(msg):
    """带强制刷新的打印函数，确保输出立即显示"""
    print(msg)
    sys.stdout.flush()


class PerformanceEvaluator:
    """
    性能评测模块
    对比自实现HNSW与FAISS的召回率、查询时间、内存占用
    """
    
    def __init__(self, vectors: np.ndarray, queries: np.ndarray = None):
        """
        初始化评测器
        
        Args:
            vectors: 用于构建索引的向量数据
            queries: 用于测试的查询向量（可选）
        """
        self.vectors = vectors
        self.queries = queries if queries is not None else vectors[:100]
        
        # 存储评测结果
        self.results = {}
        
        print(f"评测数据准备完成")
        print(f"索引向量数: {len(vectors)}, 查询向量数: {len(self.queries)}")
        print(f"向量维度: {vectors.shape[1]}")
    
    def _get_memory_usage(self) -> float:
        """获取当前进程的内存使用量（MB）"""
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)
    
    def _compute_recall(self, ann_indices: np.ndarray, ground_truth_indices: np.ndarray) -> float:
        """
        计算召回率
        
        Args:
            ann_indices: ANN搜索结果索引，形状(n_queries, k)
            ground_truth_indices: 精确搜索结果索引，形状(n_queries, k)
            
        Returns:
            召回率（0-1）
        """
        total_correct = 0
        total_expected = 0
        
        for i in range(len(ann_indices)):
            ann_set = set(ann_indices[i])
            gt_set = set(ground_truth_indices[i])
            # 排除-1（无效索引）
            ann_set.discard(-1)
            gt_set.discard(-1)
            
            if len(gt_set) > 0:
                total_correct += len(ann_set & gt_set)
                total_expected += len(gt_set)
        
        return total_correct / total_expected if total_expected > 0 else 0.0
    
    def _compute_precision(self, ann_indices: np.ndarray, ground_truth_indices: np.ndarray) -> float:
        """
        计算精确率
        
        Args:
            ann_indices: ANN搜索结果索引
            ground_truth_indices: 精确搜索结果索引
            
        Returns:
            精确率（0-1）
        """
        total_correct = 0
        total_returned = 0
        
        for i in range(len(ann_indices)):
            ann_set = set(ann_indices[i])
            gt_set = set(ground_truth_indices[i])
            ann_set.discard(-1)
            gt_set.discard(-1)
            
            if len(ann_set) > 0:
                total_correct += len(ann_set & gt_set)
                total_returned += len(ann_set)
        
        return total_correct / total_returned if total_returned > 0 else 0.0
    
    def evaluate_hnsw(self, M: int = 16, efConstruction: int = 100, 
                      ef_search: int = 50, k: int = 10) -> Dict[str, Any]:
        """
        评测自实现HNSW索引
        
        Args:
            M: 每层最大连接数
            efConstruction: 构建时的搜索范围
            ef_search: 查询时的搜索范围
            k: 返回最近邻数量
            
        Returns:
            评测结果字典
        """
        print(f"\n{'='*60}")
        print(f"评测自实现HNSW (M={M}, efConstruction={efConstruction}, ef={ef_search})")
        print(f"{'='*60}")
        
        from hnsw_index import HNSWIndex
        
        result = {
            'method': f'HNSW_self (M={M})',
            'params': {'M': M, 'efConstruction': efConstruction, 'ef': ef_search},
            'build_time': 0.0,
            'search_time': 0.0,
            'memory_mb': 0.0,
            'recall': 0.0,
            'precision': 0.0,
            'indices': None
        }
        
        # 记录构建前内存
        mem_before = self._get_memory_usage()
        
        # 构建索引
        start_time = time.time()
        hnsw = HNSWIndex(M=M, efConstruction=efConstruction, ef=ef_search)
        hnsw.build_index(self.vectors)
        build_time = time.time() - start_time
        
        # 记录构建后内存
        mem_after = self._get_memory_usage()
        
        # 执行搜索
        start_time = time.time()
        distances, indices = hnsw.search(self.queries, k=k)
        search_time = time.time() - start_time
        
        # 计算指标
        result['build_time'] = build_time
        result['search_time'] = search_time
        result['memory_mb'] = mem_after - mem_before
        result['indices'] = indices
        
        print(f"构建时间: {build_time:.4f}s")
        print(f"搜索时间: {search_time:.4f}s")
        print(f"内存占用: {result['memory_mb']:.2f} MB")
        
        self.results['hnsw_self'] = result
        return result
    
    def evaluate_faiss_flat(self, k: int = 10) -> Dict[str, Any]:
        """
        评测FAISS Flat索引（精确搜索，作为baseline）
        
        Args:
            k: 返回最近邻数量
            
        Returns:
            评测结果字典
        """
        print(f"\n{'='*60}")
        print("评测FAISS Flat（精确搜索）")
        print(f"{'='*60}")
        
        try:
            import faiss
        except ImportError:
            print("FAISS未安装，跳过此测试")
            return None
        
        result = {
            'method': 'FAISS_Flat',
            'params': {'type': 'flat'},
            'build_time': 0.0,
            'search_time': 0.0,
            'memory_mb': 0.0,
            'recall': 1.0,  # 精确搜索召回率为1
            'precision': 1.0,
            'indices': None
        }
        
        mem_before = self._get_memory_usage()
        
        vectors_f32 = self.vectors.astype(np.float32)
        d = vectors_f32.shape[1]
        
        # 构建索引
        start_time = time.time()
        index = faiss.IndexFlatL2(d)
        index.add(vectors_f32)
        build_time = time.time() - start_time
        
        mem_after = self._get_memory_usage()
        
        # 执行搜索
        queries_f32 = self.queries.astype(np.float32)
        start_time = time.time()
        distances, indices = index.search(queries_f32, k)
        search_time = time.time() - start_time
        
        result['build_time'] = build_time
        result['search_time'] = search_time
        result['memory_mb'] = mem_after - mem_before
        result['indices'] = indices
        
        print(f"构建时间: {build_time:.4f}s")
        print(f"搜索时间: {search_time:.4f}s")
        print(f"内存占用: {result['memory_mb']:.2f} MB")
        print(f"召回率: 1.0 (精确搜索)")
        
        self.results['faiss_flat'] = result
        return result
    
    def evaluate_faiss_ivfflat(self, nlist: int = 100, nprobe: int = 10, k: int = 10) -> Dict[str, Any]:
        """
        评测FAISS IVFFlat索引
        
        Args:
            nlist: IVF分桶数
            nprobe: 搜索探针数
            k: 返回最近邻数量
            
        Returns:
            评测结果字典
        """
        print(f"\n{'='*60}")
        print(f"评测FAISS IVFFlat (nlist={nlist}, nprobe={nprobe})")
        print(f"{'='*60}")
        
        try:
            import faiss
        except ImportError:
            print("FAISS未安装，跳过此测试")
            return None
        
        result = {
            'method': f'FAISS_IVFFlat (nlist={nlist})',
            'params': {'nlist': nlist, 'nprobe': nprobe},
            'build_time': 0.0,
            'search_time': 0.0,
            'memory_mb': 0.0,
            'recall': 0.0,
            'precision': 0.0,
            'indices': None
        }
        
        mem_before = self._get_memory_usage()
        
        vectors_f32 = self.vectors.astype(np.float32)
        d = vectors_f32.shape[1]
        
        # 构建索引
        start_time = time.time()
        quantizer = faiss.IndexFlatL2(d)
        index = faiss.IndexIVFFlat(quantizer, d, nlist)
        index.train(vectors_f32)
        index.add(vectors_f32)
        build_time = time.time() - start_time
        
        mem_after = self._get_memory_usage()
        
        # 执行搜索
        index.nprobe = nprobe
        queries_f32 = self.queries.astype(np.float32)
        start_time = time.time()
        distances, indices = index.search(queries_f32, k)
        search_time = time.time() - start_time
        
        result['build_time'] = build_time
        result['search_time'] = search_time
        result['memory_mb'] = mem_after - mem_before
        result['indices'] = indices
        
        print(f"构建时间: {build_time:.4f}s")
        print(f"搜索时间: {search_time:.4f}s")
        print(f"内存占用: {result['memory_mb']:.2f} MB")
        
        self.results['faiss_ivfflat'] = result
        return result
    
    def evaluate_faiss_hnsw(self, M: int = 16, ef_search: int = 50, k: int = 10) -> Dict[str, Any]:
        """
        评测FAISS HNSW索引
        
        Args:
            M: 每层最大连接数
            ef_search: 查询时的搜索范围
            k: 返回最近邻数量
            
        Returns:
            评测结果字典
        """
        print(f"\n{'='*60}")
        print(f"评测FAISS HNSW (M={M}, ef={ef_search})")
        print(f"{'='*60}")
        
        try:
            import faiss
        except ImportError:
            print("FAISS未安装，跳过此测试")
            return None
        
        result = {
            'method': f'FAISS_HNSW (M={M})',
            'params': {'M': M, 'ef': ef_search},
            'build_time': 0.0,
            'search_time': 0.0,
            'memory_mb': 0.0,
            'recall': 0.0,
            'precision': 0.0,
            'indices': None
        }
        
        mem_before = self._get_memory_usage()
        
        vectors_f32 = self.vectors.astype(np.float32)
        d = vectors_f32.shape[1]
        
        # 构建索引
        start_time = time.time()
        index = faiss.IndexHNSWFlat(d, M)
        index.hnsw.efConstruction = 200
        index.add(vectors_f32)
        build_time = time.time() - start_time
        
        mem_after = self._get_memory_usage()
        
        # 执行搜索
        index.hnsw.efSearch = ef_search
        queries_f32 = self.queries.astype(np.float32)
        start_time = time.time()
        distances, indices = index.search(queries_f32, k)
        search_time = time.time() - start_time
        
        result['build_time'] = build_time
        result['search_time'] = search_time
        result['memory_mb'] = mem_after - mem_before
        result['indices'] = indices
        
        print(f"构建时间: {build_time:.4f}s")
        print(f"搜索时间: {search_time:.4f}s")
        print(f"内存占用: {result['memory_mb']:.2f} MB")
        
        self.results['faiss_hnsw'] = result
        return result

    def evaluate_faiss_ivfpq(self, nlist: int = 100, m: int = 8, nbits: int = 8, nprobe: int = 10, k: int = 10) -> Dict[str, Any]:
        """
        评测FAISS IVFPQ索引

        Args:
            nlist: IVF分桶数
            m: PQ子向量数量
            nbits: 子向量比特数
            nprobe: 搜索探针数
            k: 返回最近邻数量

        Returns:
            评测结果字典
        """
        print(f"\n{'='*60}")
        print(f"评测FAISS IVFPQ (nlist={nlist}, m={m}, nbits={nbits}, nprobe={nprobe})")
        print(f"{'='*60}")

        try:
            import faiss
        except ImportError:
            print("FAISS未安装，跳过此测试")
            return None

        result = {
            'method': f'FAISS_IVFPQ (nlist={nlist}, m={m}, nbits={nbits})',
            'params': {'nlist': nlist, 'm': m, 'nbits': nbits, 'nprobe': nprobe},
            'build_time': 0.0,
            'search_time': 0.0,
            'memory_mb': 0.0,
            'recall': 0.0,
            'precision': 0.0,
            'indices': None
        }

        mem_before = self._get_memory_usage()
        vectors_f32 = self.vectors.astype(np.float32)
        d = vectors_f32.shape[1]
        valid_m = next((x for x in range(min(m, d), 0, -1) if d % x == 0), 1)
        if valid_m != m:
            print(f"警告：输入的 m={m} 与向量维度 d={d} 不兼容，改为 m={valid_m}。")
            m = valid_m
            result['method'] = f'FAISS_IVFPQ (nlist={nlist}, m={m}, nbits={nbits})'
            result['params']['m'] = m

        start_time = time.time()
        quantizer = faiss.IndexFlatL2(d)
        index = faiss.IndexIVFPQ(quantizer, d, nlist, m, nbits)
        index.train(vectors_f32)
        index.add(vectors_f32)
        build_time = time.time() - start_time

        mem_after = self._get_memory_usage()

        index.nprobe = nprobe
        queries_f32 = self.queries.astype(np.float32)
        start_time = time.time()
        distances, indices = index.search(queries_f32, k)
        search_time = time.time() - start_time

        result['build_time'] = build_time
        result['search_time'] = search_time
        result['memory_mb'] = mem_after - mem_before
        result['indices'] = indices

        print(f"构建时间: {build_time:.4f}s")
        print(f"搜索时间: {search_time:.4f}s")
        print(f"内存占用: {result['memory_mb']:.2f} MB")

        self.results['faiss_ivfpq'] = result
        return result

    def compute_recalls(self, k: int = 10):
        """
        计算所有方法相对于精确搜索的召回率
        
        Args:
            k: 返回最近邻数量
        """
        if 'faiss_flat' not in self.results:
            print("需要先运行FAISS Flat作为baseline")
            self.evaluate_faiss_flat(k=k)
        
        ground_truth = self.results['faiss_flat']['indices']
        
        for method, result in self.results.items():
            if method != 'faiss_flat':
                recall = self._compute_recall(result['indices'], ground_truth)
                precision = self._compute_precision(result['indices'], ground_truth)
                result['recall'] = recall
                result['precision'] = precision
                print(f"\n{result['method']}:")
                print(f"  召回率: {recall:.4f}")
                print(f"  精确率: {precision:.4f}")
    
    def generate_report(self, output_file: str = "performance_report.md"):
        """
        生成性能评测报告
        
        Args:
            output_file: 报告输出路径
        """
        if not self.results:
            print("没有评测数据，无法生成报告")
            return
        
        report = []
        report.append("# HNSW算法性能评测报告")
        report.append("")
        report.append("## 评测概览")
        report.append("")
        report.append(f"- 数据规模: {len(self.vectors)} 个向量")
        report.append(f"- 向量维度: {self.vectors.shape[1]}")
        report.append(f"- 查询数量: {len(self.queries)}")
        report.append("")
        report.append("## 评测结果对比")
        report.append("")
        
        # 生成表格
        report.append("| 方法 | 构建时间(s) | 查询时间(s) | 内存(MB) | 召回率 | 精确率 |")
        report.append("|------|------------|------------|----------|--------|--------|")
        
        for method, result in self.results.items():
            recall = f"{result['recall']:.4f}"
            precision = f"{result['precision']:.4f}"
            report.append(f"| {result['method']} | {result['build_time']:.4f} | {result['search_time']:.4f} | {result['memory_mb']:.2f} | {recall} | {precision} |")
        
        report.append("")
        report.append("## 参数配置")
        report.append("")
        
        for method, result in self.results.items():
            report.append(f"### {result['method']}")
            report.append("")
            report.append("```")
            report.append(str(result['params']))
            report.append("```")
            report.append("")
        
        report.append("## 结论")
        report.append("")
        report.append("### 自实现HNSW vs FAISS对比分析")
        report.append("")
        
        if 'hnsw_self' in self.results and 'faiss_hnsw' in self.results:
            self_impl = self.results['hnsw_self']
            faiss_impl = self.results['faiss_hnsw']
            
            report.append(f"- **构建时间**: 自实现 {self_impl['build_time']:.2f}s vs FAISS {faiss_impl['build_time']:.2f}s")
            report.append(f"- **查询时间**: 自实现 {self_impl['search_time']:.4f}s vs FAISS {faiss_impl['search_time']:.4f}s")
            report.append(f"- **内存占用**: 自实现 {self_impl['memory_mb']:.2f}MB vs FAISS {faiss_impl['memory_mb']:.2f}MB")
            report.append(f"- **召回率**: 自实现 {self_impl['recall']:.4f} vs FAISS {faiss_impl['recall']:.4f}")
            report.append("")
            
            if self_impl['recall'] >= 0.9:
                report.append("✅ 自实现HNSW达到了较高的召回率（>90%）")
            else:
                report.append("⚠️ 自实现HNSW召回率有待提升")
            
            if self_impl['build_time'] < faiss_impl['build_time'] * 2:
                report.append("✅ 自实现HNSW构建效率与FAISS相当")
            else:
                report.append("⚠️ 自实现HNSW构建效率低于FAISS")
        
        report.append("")
        report.append("---")
        report.append(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 写入文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report))
        
        print(f"\n性能评测报告已生成: {output_file}")
        
        # 打印报告内容
        print("\n" + "="*60)
        print("性能评测报告摘要")
        print("="*60)
        for line in report[:20]:
            print(line)
        print("...")
    
    def run_full_evaluation(self, k: int = 10):
        """
        运行完整的性能评测
        
        Args:
            k: 返回最近邻数量
        """
        print("=" * 70)
        print("HNSW算法性能评测 - 完整测试")
        print("=" * 70)
        
        # 1. 精确搜索作为baseline
        self.evaluate_faiss_flat(k=k)
        
        # 2. FAISS IVFFlat
        self.evaluate_faiss_ivfflat(nlist=100, nprobe=10, k=k)
        
        # 3. FAISS HNSW
        self.evaluate_faiss_hnsw(M=16, ef_search=50, k=k)
        
        # 4. 自实现HNSW
        self.evaluate_hnsw(M=16, efConstruction=200, ef_search=100, k=k)
        
        # 5. 计算召回率
        self.compute_recalls(k=k)
        
        # 6. 生成报告
        self.generate_report()


def main():
    """
    主函数：运行性能评测
    """
    print("=" * 70)
    print("性能评测模块 - 入口")
    print("=" * 70)
    
    # 加载数据
    print("\n[步骤1] 加载数据")
    try:
        vectors = np.load("cleaned_pca_vectors.npy")
        print(f"成功加载清洗后的PCA向量: {vectors.shape}")
    except FileNotFoundError:
        print("未找到cleaned_pca_vectors.npy，尝试加载原始PCA向量")
        try:
            vectors = np.load("pca_vectors.npy")
            print(f"成功加载PCA向量: {vectors.shape}")
        except FileNotFoundError:
            print("未找到PCA向量文件，生成模拟数据")
            np.random.seed(42)
            vectors = np.random.randn(10000, 30).astype(np.float32)
    
    # 使用部分数据进行评测（避免耗时过长）
    sample_size = min(10000, len(vectors))
    vectors = vectors[:sample_size]
    queries = vectors[-50:]  # 用最后50个向量作为查询
    
    print(f"\n评测配置:")
    print(f"  索引向量数: {len(vectors)}")
    print(f"  查询向量数: {len(queries)}")
    print(f"  返回邻居数: k=10")
    
    # 创建评测器并运行
    evaluator = PerformanceEvaluator(vectors, queries)
    evaluator.run_full_evaluation(k=10)
    
    print("\n" + "=" * 70)
    print("性能评测完成!")
    print("=" * 70)


if __name__ == "__main__":
    main()