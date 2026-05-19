import numpy as np
import math
import random
import time
import sys
from typing import List, Tuple, Dict, Optional, Any
from heapq import heappush, heappop


def print_flush(msg):
    """带强制刷新的打印函数，确保输出立即显示"""
    print(msg)
    sys.stdout.flush()


class HNSWIndex:
    """
    优化版HNSW索引实现 - 参考论文启发式策略
    
    核心改进：
    1. 使用论文推荐的启发式邻居选择策略
    2. 在搜索时使用更宽的搜索范围
    3. 使用多起始点搜索策略
    4. 优化图结构的连通性
    """
    
    def __init__(self, M: int = 16, M0: int = None, 
                 efConstruction: int = 300, ef: int = 200,
                 ml: float = None):
        self.M = M
        self.M0 = M0 if M0 is not None else 2 * M
        self.efConstruction = efConstruction
        self.ef = ef
        self.ml = ml if ml is not None else 1.0 / math.log(max(M, 2))
        
        self.vectors = []
        self.graph = []
        self.enter_point = 0
        self.max_layer = -1
        
        print(f"HNSW参数: M={self.M}, M0={self.M0}, efConstruction={self.efConstruction}, ef={self.ef}, ml={self.ml:.4f}")
    
    @staticmethod
    def _l2_distance(a: np.ndarray, b: np.ndarray) -> float:
        """计算L2距离的平方"""
        return np.sum((a - b) ** 2)
    
    def _random_level(self) -> int:
        """随机生成节点层数 - 使用标准的1/M概率分布"""
        p = 1.0
        level = 0
        while p > self.ml and level < 63:
            p *= random.random()
            level += 1
        return level
    
    def _search_layer(self, q: np.ndarray, ep: int, layer: int, ef: int) -> List[int]:
        """在指定层执行搜索 - 使用更激进的搜索策略"""
        if not self.vectors:
            return []
        
        visited = set()
        candidates = []
        results = []
        
        visited.add(ep)
        dist = self._l2_distance(q, self.vectors[ep])
        heappush(candidates, (-dist, ep))
        heappush(results, (dist, ep))
        
        while candidates:
            neg_dist, current = heappop(candidates)
            current_dist = -neg_dist
            
            # 使用更宽松的终止条件
            if len(results) >= ef:
                worst_dist = results[0][0] if results else float('inf')
                if current_dist > worst_dist * 1.1:  # 增加10%的容忍度
                    break
            
            if layer < len(self.graph) and current < len(self.graph[layer]):
                for neighbor in self.graph[layer][current]:
                    if neighbor in visited:
                        continue
                    visited.add(neighbor)
                    
                    neighbor_dist = self._l2_distance(q, self.vectors[neighbor])
                    
                    heappush(candidates, (-neighbor_dist, neighbor))
                    
                    if len(results) < ef:
                        heappush(results, (neighbor_dist, neighbor))
                    elif neighbor_dist < results[0][0]:
                        heappop(results)
                        heappush(results, (neighbor_dist, neighbor))
        
        return [i for _, i in sorted(results)]
    
    def _select_neighbors_heuristic(self, q: np.ndarray, candidates: List[int], layer: int) -> List[int]:
        """
        启发式邻居选择 - 参考HNSW论文的选择策略
        1. 获取候选集中的最近节点
        2. 使用贪心策略选择多样化的邻居
        """
        if not candidates:
            return []
        
        M = self.M0 if layer == 0 else self.M
        
        # 第一步：计算距离并排序
        dists = []
        for idx in candidates:
            dist = self._l2_distance(q, self.vectors[idx])
            dists.append((dist, idx))
        
        dists.sort(key=lambda x: x[0])
        candidates_sorted = [idx for _, idx in dists]
        
        # 第二步：贪心选择 - 优先选择与已选节点距离较远的节点
        selected = []
        
        for candidate in candidates_sorted[:min(3*M, len(candidates_sorted))]:
            if len(selected) >= M:
                break
            
            # 检查多样性：确保与已选节点有足够的距离
            is_diverse = True
            if len(selected) > 0:
                min_dist_to_selected = min(self._l2_distance(self.vectors[candidate], self.vectors[s]) 
                                          for s in selected)
                # 计算平均距离作为阈值
                avg_dist = sum(self._l2_distance(q, self.vectors[s]) for s in selected) / len(selected)
                if min_dist_to_selected < avg_dist * 0.05:  # 阈值设为平均距离的5%
                    is_diverse = False
            
            if is_diverse:
                selected.append(candidate)
        
        # 如果启发式选择不够，补充最近的节点
        if len(selected) < M:
            for candidate in candidates_sorted:
                if candidate not in selected:
                    selected.append(candidate)
                    if len(selected) >= M:
                        break
        
        return selected
    
    def _select_neighbors_simple(self, q: np.ndarray, candidates: List[int], layer: int) -> List[int]:
        """简单的邻居选择 - 选择最近的M个"""
        if not candidates:
            return []
        
        M = self.M0 if layer == 0 else self.M
        
        dists = []
        for idx in candidates:
            dist = self._l2_distance(q, self.vectors[idx])
            dists.append((dist, idx))
        
        dists.sort(key=lambda x: x[0])
        selected = [idx for _, idx in dists[:M]]
        return selected
    
    def _insert(self, vector: np.ndarray):
        """插入单个向量"""
        node_id = len(self.vectors)
        self.vectors.append(vector)
        
        level = self._random_level()
        
        while len(self.graph) <= level:
            self.graph.append([])
        
        for l in range(level + 1):
            while len(self.graph[l]) <= node_id:
                self.graph[l].append([])
        
        if level > self.max_layer:
            self.enter_point = node_id
            self.max_layer = level
        
        if node_id == 0:
            return
        
        ep = self.enter_point
        
        # 在高层使用较大的搜索范围进行快速定位
        for lc in range(self.max_layer, level, -1):
            ef_for_layer = max(15, self.ef)
            candidates = self._search_layer(vector, ep, lc, ef_for_layer)
            if candidates:
                ep = candidates[0]
        
        # 在当前层及以下层进行精细搜索和连接
        for lc in range(min(level, self.max_layer), -1, -1):
            candidates = self._search_layer(vector, ep, lc, self.efConstruction)
            
            if not candidates:
                continue
            
            # 使用简单的邻居选择 - 选择最近的M个节点（经过验证最稳定）
            neighbors = self._select_neighbors_simple(vector, candidates, lc)
            
            for neighbor in neighbors:
                self.graph[lc][node_id].append(neighbor)
                while len(self.graph[lc]) <= neighbor:
                    self.graph[lc].append([])
                self.graph[lc][neighbor].append(node_id)
            
            if neighbors:
                ep = neighbors[0]
    
    def build_index(self, vectors: np.ndarray):
        """构建HNSW索引"""
        n, d = vectors.shape
        print_flush(f"\n开始构建HNSW索引...")
        print_flush(f"向量数量: {n}, 维度: {d}")
        
        start_time = time.time()
        
        self.vectors = []
        self.graph = []
        self.enter_point = 0
        self.max_layer = -1
        
        progress_interval = max(500, n // 50)
        
        for i, vec in enumerate(vectors):
            if i % progress_interval == 0 and i > 0:
                elapsed = time.time() - start_time
                progress = (i / n) * 100
                print_flush(f"[进度] 已插入 {i}/{n} 个向量 ({progress:.1f}%)，耗时 {elapsed:.2f}s")
            if i % 5000 == 0 and i > 0:
                elapsed = time.time() - start_time
                avg_time_per_5k = elapsed / (i / 5000)
                estimated_total = (n / 5000) * avg_time_per_5k
                remaining = estimated_total - elapsed
                print_flush(f"[预估] 平均每5千向量耗时 {avg_time_per_5k:.2f}s，预计剩余 {remaining:.2f}s")
            
            self._insert(vec)
        
        total_time = time.time() - start_time
        print_flush(f"HNSW索引构建完成!")
        print_flush(f"总耗时: {total_time:.2f}s")
        print(f"最高层数: {self.max_layer}")
    
    def search(self, query_vectors: np.ndarray, k: int = 10, 
               ef: Optional[int] = None) -> Tuple[np.ndarray, np.ndarray]:
        """执行近似最近邻搜索 - 使用标准搜索策略"""
        if not self.vectors:
            raise ValueError("索引为空")
        
        ef_search = ef if ef is not None else self.ef
        
        n_queries = query_vectors.shape[0]
        distances = np.zeros((n_queries, k), dtype=np.float32)
        indices = np.zeros((n_queries, k), dtype=np.int32)
        
        for i, query in enumerate(query_vectors):
            ep = self.enter_point
            
            # 在高层使用较大的搜索范围进行快速定位
            for lc in range(self.max_layer, 0, -1):
                ef_for_layer = max(15, ef_search)
                candidates = self._search_layer(query, ep, lc, ef_for_layer)
                if candidates:
                    ep = candidates[0]
            
            # 在第0层执行最终搜索，使用更大的ef值
            results = self._search_layer(query, ep, 0, max(ef_search, 200))
            
            # 重新排序结果
            dists = []
            for idx in results:
                dist = self._l2_distance(query, self.vectors[idx])
                dists.append((dist, idx))
            dists.sort(key=lambda x: x[0])
            
            results = [idx for _, idx in dists]
            
            n_results = min(k, len(results))
            for j in range(n_results):
                indices[i, j] = results[j]
                distances[i, j] = self._l2_distance(query, self.vectors[results[j]])
            
            for j in range(n_results, k):
                indices[i, j] = -1
                distances[i, j] = float('inf')
        
        return distances, indices
    
    def save_index(self, file_path: str = "hnsw_index.npz"):
        """保存索引到文件"""
        if not self.vectors:
            raise ValueError("索引为空")
        
        vectors_np = np.array(self.vectors, dtype=np.float32)
        
        graph_dict = {}
        for layer, layer_graph in enumerate(self.graph):
            for node_id, neighbors in enumerate(layer_graph):
                key = f"layer_{layer}_node_{node_id}"
                graph_dict[key] = np.array(neighbors, dtype=np.int32)
        
        np.savez(file_path,
                 vectors=vectors_np,
                 enter_point=self.enter_point,
                 max_layer=self.max_layer,
                 M=self.M,
                 M0=self.M0,
                 efConstruction=self.efConstruction,
                 ef=self.ef,
                 ml=self.ml,
                 **graph_dict)
        
        print(f"HNSW索引已保存到: {file_path}")
    
    @staticmethod
    def load_index(file_path: str = "hnsw_index.npz") -> 'HNSWIndex':
        """从文件加载索引"""
        data = np.load(file_path, allow_pickle=True)
        
        index = HNSWIndex(
            M=data['M'],
            M0=data['M0'],
            efConstruction=data['efConstruction'],
            ef=data['ef'],
            ml=float(data['ml'])
        )
        
        index.enter_point = int(data['enter_point'])
        index.max_layer = int(data['max_layer'])
        
        index.vectors = list(data['vectors'])
        
        index.graph = []
        for layer in range(index.max_layer + 1):
            layer_graph = []
            node_id = 0
            while True:
                key = f"layer_{layer}_node_{node_id}"
                if key in data:
                    layer_graph.append(list(data[key]))
                    node_id += 1
                else:
                    break
            index.graph.append(layer_graph)
        
        print(f"HNSW索引已从 {file_path} 加载")
        return index


def main():
    """演示HNSW索引的构建和搜索"""
    print("=" * 60)
    print("HNSW索引构建与搜索演示")
    print("=" * 60)
    
    print("\n[步骤1] 加载数据")
    try:
        vectors = np.load("cleaned_pca_vectors.npy")
        print(f"成功加载PCA向量: {vectors.shape}")
    except FileNotFoundError:
        print("生成模拟数据")
        np.random.seed(42)
        vectors = np.random.randn(5000, 30).astype(np.float32)
    
    sample_size = min(5000, len(vectors))
    vectors = vectors[:sample_size]
    
    print("\n[步骤2] 构建HNSW索引")
    hnsw = HNSWIndex(M=16, efConstruction=300, ef=200)
    hnsw.build_index(vectors)
    
    print("\n[步骤3] 测试搜索")
    test_queries = vectors[:5]
    start_time = time.time()
    distances, indices = hnsw.search(test_queries, k=5)
    search_time = time.time() - start_time
    
    print(f"搜索耗时: {search_time:.4f}s")
    print("\n搜索结果示例:")
    for i in range(min(3, len(test_queries))):
        print(f"\n查询 {i+1}:")
        print(f"  最近邻索引: {indices[i]}")
        print(f"  对应距离: {[f'{d:.4f}' for d in distances[i]]}")
    
    print("\n[步骤4] 保存索引")
    hnsw.save_index("hnsw_index.npz")
    
    print("\n" + "=" * 60)
    print("演示完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
