import numpy as np
import math
import random
import time
import sys
from typing import List, Tuple, Optional
from heapq import heappush, heappop


def print_flush(msg):
    print(msg)
    sys.stdout.flush()


class HNSWIndex:
    """
    优化版HNSW索引实现 - 使用NumPy向量化加速

    核心改进：
    1. 使用NumPy数组存储向量，提高访问效率
    2. 向量化距离计算
    3. 多样化邻居选择（非简单top-M）
    4. 图保存/加载使用紧凑2D数组格式，避免NPZ逐键浪费
    5. visited使用布尔数组替代Python set
    """

    def __init__(self, M: int = 16, M0: int = None,
                 efConstruction: int = 200, ef: int = 200,
                 ml: float = None):
        self.M = M
        self.M0 = M0 if M0 is not None else 2 * M
        self.efConstruction = efConstruction
        self.ef = ef
        self.ml = ml if ml is not None else 1.0 / math.log(max(M, 2))

        self.vectors = None
        self.graph = []       # graph[layer][node_id] = list_of_neighbor_ids
        self.enter_point = 0
        self.max_layer = -1

    @staticmethod
    def _l2_distance(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.sum((a - b) ** 2))

    @staticmethod
    def _l2_distances(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return np.sum((b - a) ** 2, axis=1)

    def _random_level(self) -> int:
        """随机生成节点层数 - 指数衰减分布（使用numpy以保持一致）"""
        return int(-math.log(random.random()) * self.ml)

    def _search_layer(self, q: np.ndarray, ep: int, layer: int, ef: int,
                      visited: np.ndarray = None) -> List[int]:
        """
        在指定层执行搜索

        使用布尔数组替代set标记已访问节点，大幅提升大ef下的性能。
        """
        if self.vectors is None or len(self.vectors) == 0:
            return []

        n_vectors = len(self.vectors)
        if visited is None:
            visited = np.zeros(n_vectors, dtype=bool)
        else:
            visited[:] = False

        candidates = []   # 最小堆: (dist, node)
        results = []      # 最大堆: (-dist, node)

        visited[ep] = True
        dist = self._l2_distance(q, self.vectors[ep])
        heappush(candidates, (dist, ep))
        heappush(results, (-dist, ep))

        while candidates:
            dist_c, current = heappop(candidates)

            farthest_dist = -results[0][0]
            if dist_c > farthest_dist:
                break

            if layer < len(self.graph) and current < len(self.graph[layer]):
                for neighbor in self.graph[layer][current]:
                    if visited[neighbor]:
                        continue
                    visited[neighbor] = True

                    nd = self._l2_distance(q, self.vectors[neighbor])
                    heappush(candidates, (nd, neighbor))

                    if len(results) < ef:
                        heappush(results, (-nd, neighbor))
                    elif nd < -results[0][0]:
                        heappop(results)
                        heappush(results, (-nd, neighbor))

        return [n for _, n in sorted([(-d, n) for d, n in results])]

    def _select_neighbors(self, q_vector: np.ndarray,
                           candidates: List[int], layer: int) -> List[int]:
        """选择最近的 M 个邻居（简单版）"""
        M = self.M0 if layer == 0 else self.M

        if not candidates:
            return []
        if len(candidates) <= M:
            return list(candidates)

        cand_arr = np.array(candidates, dtype=np.int32)
        cand_vecs = self.vectors[cand_arr]
        dists = self._l2_distances(q_vector, cand_vecs)
        sorted_idx = np.argsort(dists)[:M]
        return [candidates[i] for i in sorted_idx]

    def _select_neighbors_diverse(self, q_vector: np.ndarray,
                                   candidates: List[int], layer: int) -> List[int]:
        """
        多样化邻居选择（HNSW论文Algorithm 4启发式）

        核心思想：
        1. 按距离查询点排序候选节点
        2. 最接近的节点总是加入
        3. 后续节点只有在"到查询的距离 < 到任何已选节点的距离"时才加入
        4. 这样可以避免所有边都指向同一区域，提升图连通性

        如果多样化选择无法凑够M个，fallback到简单top-M选择。
        """
        M = self.M0 if layer == 0 else self.M

        if not candidates:
            return []
        if len(candidates) <= M:
            return list(candidates)

        # 按距离排序候选节点
        cand_arr = np.array(candidates, dtype=np.int32)
        cand_vecs = self.vectors[cand_arr]
        dists = self._l2_distances(q_vector, cand_vecs)
        order = np.argsort(dists)

        selected = [candidates[order[0]]]

        for idx in order[1:]:
            if len(selected) >= M:
                break
            cand_node = candidates[idx]
            cand_vec = self.vectors[cand_node]
            cand_dist = dists[idx]

            # 多样化检查：如果候选项离某已选节点更近，说明它"挤在"该节点附近，
            # 加入它不仅不会增加多样性，还会降低图的质量
            is_diverse = True
            for sel in selected:
                if self._l2_distance(cand_vec, self.vectors[sel]) < cand_dist:
                    is_diverse = False
                    break

            if is_diverse:
                selected.append(cand_node)

        # 如果多样化选择不够M个，fallback到最近的节点补齐
        if len(selected) < M:
            for idx in order:
                node = candidates[idx]
                if node not in selected:
                    selected.append(node)
                    if len(selected) >= M:
                        break

        return selected

    def _insert(self, vector: np.ndarray, node_id: int):
        """插入单个向量"""
        level = self._random_level()

        # 确保图结构有足够的层和节点槽位
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

        # 从最高层快速下降到目标层（使用标准HNSW下降策略）
        for lc in range(self.max_layer, level, -1):
            if lc < len(self.graph):
                candidates = self._search_layer(vector, ep, lc, ef=15)
                if candidates:
                    ep = candidates[0]

        # 在目标层及以下进行精细搜索和双向连接
        for lc in range(min(level, self.max_layer), -1, -1):
            candidates = self._search_layer(vector, ep, lc, self.efConstruction)

            if not candidates:
                continue

            neighbors = self._select_neighbors_diverse(vector, candidates, lc)

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
        print_flush(f"向量数量: {n}, 维度: {d}, M={self.M}, efConstruction={self.efConstruction}")

        start_time = time.time()

        self.vectors = vectors.astype(np.float32)
        self.graph = []
        self.enter_point = 0
        self.max_layer = -1

        progress_interval = max(1000, n // 20)

        for i in range(n):
            vec = self.vectors[i]
            if i % progress_interval == 0 and i > 0:
                elapsed = time.time() - start_time
                progress = (i / n) * 100
                eta = (elapsed / i) * (n - i)
                print_flush(f"[进度] {i}/{n} ({progress:.1f}%)，已用 {elapsed:.1f}s，预计剩余 {eta:.1f}s")

            self._insert(vec, i)

        total_time = time.time() - start_time
        total_edges = sum(len(neighbors)
                          for layer in self.graph for neighbors in layer)
        print_flush(f"HNSW索引构建完成! 总耗时: {total_time:.2f}s")
        print_flush(f"最高层数: {self.max_layer}, 总边数: {total_edges}")

    def search(self, query_vectors: np.ndarray, k: int = 10,
               ef: Optional[int] = None) -> Tuple[np.ndarray, np.ndarray]:
        """执行近似最近邻搜索"""
        if self.vectors is None:
            raise ValueError("索引为空")

        ef_search = ef if ef is not None else self.ef

        n_queries = query_vectors.shape[0]
        n_vectors = len(self.vectors)
        distances = np.full((n_queries, k), float('inf'), dtype=np.float32)
        indices = np.full((n_queries, k), -1, dtype=np.int32)

        # 为visited分配一次布尔数组，被_search_layer复用
        visited = np.zeros(n_vectors, dtype=bool)

        for i, query in enumerate(query_vectors):
            ep = self.enter_point

            # 从最高层快速定位（无硬编码限制）
            for lc in range(self.max_layer, 0, -1):
                if lc < len(self.graph):
                    candidates = self._search_layer(query, ep, lc, ef=15, visited=visited)
                    if candidates:
                        ep = candidates[0]

            # 底层精细搜索
            results = self._search_layer(query, ep, 0, ef=ef_search, visited=visited)

            if len(results) > 0:
                results_arr = np.array(results, dtype=np.int32)
                result_vectors = self.vectors[results_arr]
                dists = self._l2_distances(query, result_vectors)
                sorted_idx = np.argsort(dists)[:k]
                n_results = min(k, len(sorted_idx))
                for j in range(n_results):
                    indices[i, j] = results[sorted_idx[j]]
                    distances[i, j] = dists[sorted_idx[j]]

        return distances, indices

    def save_index(self, file_path: str = "hnsw_index.npz"):
        """
        保存索引到文件（紧凑格式）

        将每一层的邻接表编码为单个2D数组，以-1填充。
        比逐(node,layer)存储NPZ键的方式节省大量空间。
        """
        if self.vectors is None:
            raise ValueError("索引为空")

        save_dict = {
            'vectors': self.vectors,
            'enter_point': self.enter_point,
            'max_layer': self.max_layer,
            'M': self.M,
            'M0': self.M0,
            'efConstruction': self.efConstruction,
            'ef': self.ef,
            'ml': self.ml,
        }

        # 每层存储为一个2D数组 (num_nodes, max_degree)，用-1填充
        for layer_idx, layer in enumerate(self.graph):
            if not layer:
                continue
            max_deg = max((len(nbrs) for nbrs in layer), default=0)
            if max_deg == 0:
                continue
            layer_arr = np.full((len(layer), max_deg), -1, dtype=np.int32)
            for i, nbrs in enumerate(layer):
                if nbrs:
                    layer_arr[i, :len(nbrs)] = nbrs
            save_dict[f'layer_{layer_idx}'] = layer_arr

        np.savez_compressed(file_path, **save_dict)

        file_size = self._get_file_size(file_path)
        print(f"HNSW索引已保存到: {file_path} ({file_size:.1f} MB)")

    @staticmethod
    def _get_file_size(path: str) -> float:
        import os
        return os.path.getsize(path) / (1024 * 1024)

    @staticmethod
    def load_index(file_path: str = "hnsw_index.npz") -> 'HNSWIndex':
        """从文件加载索引（紧凑格式）"""
        data = np.load(file_path, allow_pickle=True)

        index = HNSWIndex(
            M=int(data['M']),
            M0=int(data['M0']),
            efConstruction=int(data['efConstruction']),
            ef=int(data['ef']),
            ml=float(data['ml'])
        )

        index.enter_point = int(data['enter_point'])
        index.max_layer = int(data['max_layer'])
        index.vectors = data['vectors']

        # 从紧凑格式恢复图结构
        index.graph = []
        for layer_idx in range(index.max_layer + 1):
            key = f'layer_{layer_idx}'
            if key in data:
                layer_arr = data[key]
                layer_graph = []
                for row in layer_arr:
                    nbrs = [int(x) for x in row if x != -1]
                    layer_graph.append(nbrs)
                index.graph.append(layer_graph)
            else:
                index.graph.append([])

        file_size = HNSWIndex._get_file_size(file_path)
        print(f"HNSW索引已从 {file_path} 加载 ({file_size:.1f} MB)")
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
    hnsw = HNSWIndex(M=16, efConstruction=200, ef=150)
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

    print("\n[步骤5] 加载索引并验证")
    loaded = HNSWIndex.load_index("hnsw_index.npz")
    d2, i2 = loaded.search(test_queries, k=5)
    match = np.array_equal(indices, i2)
    print(f"保存/加载验证: {'通过' if match else '失败'}")

    print("\n" + "=" * 60)
    print("演示完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
