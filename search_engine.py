"""
统一检索引擎 — 支持三种检索模式和索引缓存。

模式：
  NORMAL          — 无过滤的标准 Top-K ANN 检索
  CONDITIONAL     — 检索前按条件预过滤向量，再在子集上执行 Top-K
  CROSS_DATASET   — 跨数据集联合检索，保留来源追踪

IndexCache 为热门数据集提供 LRU 缓存，避免每次切换数据集都重新加载。
"""

import csv
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

import numpy as np


# ---------------------------------------------------------------------------
# 公开类型
# ---------------------------------------------------------------------------

class SearchMode(Enum):
    NORMAL = auto()          # 标准 Top-K，无预过滤
    CONDITIONAL = auto()     # 检索前过滤，在子集上 Top-K
    CROSS_DATASET = auto()   # 跨数据集联合检索


class SearchInputError(ValueError):
    """客户端查询参数无效。"""


class FilterSpec:
    """描述检索前应满足的过滤条件。

    所有字段都是 **精确大小写不敏感相等** 匹配。空字符串表示不过滤。
    """

    __slots__ = ("cell_type", "disease", "dataset_group", "dataset_id", "tissue")

    def __init__(
        self,
        *,
        cell_type: str = "",
        disease: str = "",
        dataset_group: str = "",
        dataset_id: str = "",
        tissue: str = "",
    ) -> None:
        self.cell_type = cell_type.strip()
        self.disease = disease.strip()
        self.dataset_group = dataset_group.strip()
        self.dataset_id = dataset_id.strip()
        self.tissue = tissue.strip()

    @property
    def is_empty(self) -> bool:
        return not any(
            (self.cell_type, self.disease, self.dataset_group, self.dataset_id, self.tissue)
        )

    def to_dict(self) -> Dict[str, str]:
        """返回包含非空条件的扁平字典，与旧 filters dict 兼容。"""
        mapping = {
            "cell_type": self.cell_type,
            "disease": self.disease,
            "dataset_group": self.dataset_group,
            "dataset_id": self.dataset_id,
            "tissue": self.tissue,
        }
        return {k: v for k, v in mapping.items() if v}

    def __repr__(self) -> str:
        parts = [f"{k}={v!r}" for k, v in self.to_dict().items()]
        return f"FilterSpec({', '.join(parts) or 'empty'})"


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------

@dataclass(order=True)
class _CacheEntry:
    last_access: float
    vectors: Any = field(compare=False)
    metadata: List[Dict[str, str]] = field(compare=False)
    index: Any = field(compare=False)
    index_type: str = field(compare=False)  # "faiss" | "hnsw"
    cell_id_map: Dict[str, int] = field(compare=False)


class IndexCache:
    """LRU 缓存，存最近使用的 N 个数据集。

    缓存键 = f"{dataset_id}__{index_type}"，确保 FAISS 和 HNSW 版本互不覆盖。
    """

    def __init__(self, max_entries: int = 3, max_memory_mb: float = 2048.0) -> None:
        self._max_entries = max(1, max_entries)
        self._max_memory_mb = max(64.0, max_memory_mb)
        self._store: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    # ---- public ----

    def key(self, dataset_id: str, index_type: str) -> str:
        return f"{dataset_id}__{index_type}"

    def get(
        self, dataset_id: str, index_type: str
    ) -> Optional[Tuple[Any, List[Dict[str, str]], Any, Dict[str, int]]]:
        with self._lock:
            entry = self._store.get(self.key(dataset_id, index_type))
            if entry is None:
                self.misses += 1
                return None
            entry.last_access = time.monotonic()
            self._store.move_to_end(self.key(dataset_id, index_type))
            self.hits += 1
            return (entry.vectors, entry.metadata, entry.index, entry.cell_id_map)

    def put(
        self,
        dataset_id: str,
        index_type: str,
        vectors: Any,
        metadata: List[Dict[str, str]],
        index: Any,
        cell_id_map: Dict[str, int],
    ) -> None:
        with self._lock:
            cache_key = self.key(dataset_id, index_type)
            if cache_key in self._store:
                self._store.move_to_end(cache_key)
                self._store[cache_key].last_access = time.monotonic()
                return
            self._store[cache_key] = _CacheEntry(
                last_access=time.monotonic(),
                vectors=vectors,
                metadata=metadata,
                index=index,
                index_type=index_type,
                cell_id_map=cell_id_map,
            )
            self._evict_lru()
            self._evict_memory()

    def invalidate(self, dataset_id: Optional[str] = None) -> int:
        """使缓存失效。如果 dataset_id 为 None，清空全部缓存。"""
        with self._lock:
            if dataset_id is None:
                count = len(self._store)
                self._store.clear()
                return count
            removed = 0
            for key in list(self._store.keys()):
                if key.startswith(f"{dataset_id}__"):
                    del self._store[key]
                    removed += 1
            return removed

    @property
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "entries": len(self._store),
                "max_entries": self._max_entries,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": self.hits / max(1, self.hits + self.misses),
                "keys": list(self._store.keys()),
            }

    # ---- internal ----

    def _evict_lru(self) -> None:
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)

    def _evict_memory(self) -> None:
        while self._store:
            total_mb = self._estimate_total_mb()
            if total_mb <= self._max_memory_mb:
                break
            self._store.popitem(last=False)

    def _estimate_total_mb(self) -> float:
        total = 0.0
        for entry in self._store.values():
            if entry.vectors is not None and hasattr(entry.vectors, "nbytes"):
                total += entry.vectors.nbytes / (1024 * 1024)
            if entry.index is not None and hasattr(entry.index, "ntotal"):
                total += 16 * entry.index.ntotal / (1024 * 1024)
        return total


# ---------------------------------------------------------------------------
# 统一检索引擎
# ---------------------------------------------------------------------------

DEFAULT_RESULT_FIELDS = [
    "cell_id",
    "dataset_id",
    "dataset_name",
    "dataset_group",
    "dataset_source",
    "cell_type",
    "author_cell_type",
    "disease",
    "AgeGroup",
    "donor_age",
    "sex",
    "tissue",
    "nCount_RNA",
    "nFeature_RNA",
    "percent.mt",
]


class SearchEngine:
    """封装 FAISS / HNSW + 条件过滤的检索引擎。

    用法::

        engine = SearchEngine(index_cache=IndexCache())
        engine.configure(vectors_path="...", metadata_path="...", faiss_index_path="...")
        engine.load()

        # 标准搜索
        result = engine.search(cell_id="cell_1", k=10)
        # 条件搜索（预过滤）
        result = engine.search(
            cell_id="cell_1", k=10,
            mode=SearchMode.CONDITIONAL,
            filter_spec=FilterSpec(disease="cirrhosis"),
        )
    """

    def __init__(
        self,
        index_cache: Optional[IndexCache] = None,
        result_fields: Optional[Iterable[str]] = None,
    ) -> None:
        self.cache = index_cache or IndexCache()
        self.result_fields = list(result_fields or DEFAULT_RESULT_FIELDS)

        # 路径 (由 configure 设置)
        self._faiss_index_path: str = ""
        self._hnsw_index_path: str = ""
        self._vectors_path: str = ""
        self._metadata_path: str = ""
        self._dataset_id: str = ""

        # 运行时状态
        self.vectors: Optional[np.ndarray] = None
        self.metadata: List[Dict[str, str]] = []
        self.cell_id_to_row: Dict[str, int] = {}
        self.dimension: Optional[int] = None
        self.faiss_index: Any = None
        self.hnsw_index: Any = None
        self._faiss_available = False
        self._hnsw_available = False
        self._loaded = False
        self._load_error: Optional[str] = None

    # ---- 配置 ----

    def configure(
        self,
        *,
        vectors_path: str,
        metadata_path: str,
        faiss_index_path: str = "",
        hnsw_index_path: str = "",
        dataset_id: str = "",
    ) -> None:
        """更新所有文件路径并重置加载状态。"""
        self._faiss_index_path = faiss_index_path
        self._hnsw_index_path = hnsw_index_path
        self._vectors_path = vectors_path
        self._metadata_path = metadata_path
        self._dataset_id = dataset_id
        self._reset()

    def _reset(self) -> None:
        self.vectors = None
        self.metadata = []
        self.cell_id_to_row = {}
        self.dimension = None
        self.faiss_index = None
        self.hnsw_index = None
        self._faiss_available = False
        self._hnsw_available = False
        self._loaded = False
        self._load_error = None

    # ---- 加载 ----

    def load(self, index_type: str = "faiss") -> None:
        """加载向量、元数据和索引。

        优先从 IndexCache 命中；miss 时从磁盘加载并写入缓存。
        """
        cached = self.cache.get(self._dataset_id, index_type)
        if cached is not None:
            self.vectors, self.metadata, index, self.cell_id_to_row = cached
            if index_type == "faiss":
                self.faiss_index = index
                self._faiss_available = True
            else:
                self.hnsw_index = index
                self._hnsw_available = True
            self.dimension = int(self.vectors.shape[1])
            self._loaded = True
            self._load_error = None
            return

        self._assert_file_exists(self._vectors_path, "PCA vector file")
        self._assert_file_exists(self._metadata_path, "metadata file")

        import numpy as np2
        self.vectors = np2.load(self._vectors_path, mmap_mode="r")
        self.metadata = self._load_metadata(self._metadata_path)
        self.cell_id_to_row = {
            row.get("cell_id", ""): idx
            for idx, row in enumerate(self.metadata)
            if row.get("cell_id")
        }

        if len(self.vectors) != len(self.metadata):
            raise RuntimeError(
                f"Vector count and metadata count mismatch: "
                f"{len(self.vectors)} vs {len(self.metadata)}"
            )

        if index_type == "faiss" and self._faiss_index_path:
            self._assert_file_exists(self._faiss_index_path, "FAISS index")
            try:
                import faiss
                self.faiss_index = faiss.read_index(self._faiss_index_path)
                self._faiss_available = True
            except ImportError:
                self._faiss_available = False

            if self.faiss_index is not None and self.faiss_index.ntotal != len(self.metadata):
                raise RuntimeError(
                    f"FAISS index size / metadata mismatch: "
                    f"{self.faiss_index.ntotal} vs {len(self.metadata)}"
                )
            cached_index = self.faiss_index

        elif index_type == "hnsw" and self._hnsw_index_path:
            self._assert_file_exists(self._hnsw_index_path, "HNSW index")
            from hnsw_index import HNSWIndex
            self.hnsw_index = HNSWIndex.load_index(self._hnsw_index_path)
            self._hnsw_available = True
            cached_index = self.hnsw_index
        else:
            cached_index = None

        self.dimension = int(self.vectors.shape[1])
        self._loaded = True
        self._load_error = None

        self.cache.put(
            dataset_id=self._dataset_id,
            index_type=index_type,
            vectors=self.vectors,
            metadata=self.metadata,
            index=cached_index,
            cell_id_map=self.cell_id_to_row,
        )

    # ---- 状态 ----

    def status(self, index_type: str = "faiss") -> Dict[str, Any]:
        self._ensure_loaded()
        base = {
            "loaded": True,
            "vectors_path": self._vectors_path,
            "metadata_path": self._metadata_path,
            "dataset_id": self._dataset_id,
            "cell_count": len(self.metadata),
            "dimension": self.dimension,
            "index_engine": index_type,
            "cache_stats": self.cache.stats,
        }
        if index_type == "faiss":
            base["faiss_available"] = self._faiss_available
            base["index_total"] = (
                int(self.faiss_index.ntotal) if self.faiss_index is not None else len(self.metadata)
            )
            base["faiss_index_path"] = self._faiss_index_path
        else:
            base["index_total"] = (
                len(self.hnsw_index.vectors) if self.hnsw_index is not None and self.hnsw_index.vectors is not None else len(self.metadata)
            )
            base["hnsw_index_path"] = self._hnsw_index_path
            if self.hnsw_index is not None:
                base["M"] = self.hnsw_index.M
                base["ef"] = self.hnsw_index.ef
        return base

    # ---- 获取细胞 ----

    def get_cell(self, cell_id: str) -> Dict[str, Any]:
        self._ensure_loaded()
        idx = self.cell_id_to_row.get(cell_id)
        if idx is None:
            raise SearchInputError(f"Unknown cell_id: {cell_id}")
        return self._format_result(idx, distance=None)

    # ---- 核心搜索 ----

    def search(
        self,
        *,
        cell_id: Optional[str] = None,
        vector: Optional[List[float]] = None,
        k: int = 10,
        mode: SearchMode = SearchMode.NORMAL,
        filter_spec: Optional[FilterSpec] = None,
        index_type: str = "faiss",
        nprobe: Optional[int] = None,
        include_self: bool = False,
    ) -> Dict[str, Any]:
        """统一搜索入口，按模式路由。"""
        self._ensure_loaded()
        k = self._validate_k(k)
        filter_spec = filter_spec or FilterSpec()

        # 构建查询向量
        query_vector, query_cell_id, query_row = self._build_query(cell_id, vector)

        # 设置 nprobe（仅 FAISS IVF 系列有效）
        if nprobe is not None and index_type == "faiss" and self.faiss_index is not None:
            if hasattr(self.faiss_index, "nprobe"):
                self.faiss_index.nprobe = self._validate_nprobe(nprobe)

        started = time.perf_counter()

        if mode == SearchMode.CONDITIONAL and not filter_spec.is_empty:
            result = self._search_conditional(
                query_vector, query_cell_id, query_row, k, filter_spec, index_type, include_self
            )
        elif mode == SearchMode.CROSS_DATASET:
            result = self._search_cross_dataset(
                query_vector, query_cell_id, query_row, k, filter_spec, index_type, include_self
            )
        else:
            result = self._search_normal(
                query_vector, query_cell_id, query_row, k, filter_spec, index_type, include_self
            )

        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)

        return {
            "query": {
                "cell_id": query_cell_id,
                "row_index": query_row,
                "dimension": self.dimension,
                "k": k,
                "mode": mode.name.lower(),
                "include_self": include_self,
                "filter_spec": filter_spec.to_dict(),
                "nprobe": (
                    getattr(self.faiss_index, "nprobe", None)
                    if self.faiss_index is not None else None
                ),
            },
            "elapsed_ms": elapsed_ms,
            "result_count": len(result.get("results", [])),
            "results": result.get("results", []),
            "filter_stats": result.get("filter_stats", {}),
            "warnings": result.get("warnings", []),
        }

    # ---- 内部：三种搜索模式 ----

    def _search_normal(
        self,
        query_vector: np.ndarray,
        query_cell_id: Optional[str],
        query_row: Optional[int],
        k: int,
        filter_spec: FilterSpec,
        index_type: str,
        include_self: bool,
    ) -> Dict[str, Any]:
        """标准 Top-K：FAISS/HNSW ANN + 后置过滤（兼容旧接口）。"""
        candidate_k = self._candidate_count(k, not filter_spec.is_empty, include_self)

        if index_type == "faiss" and self.faiss_index is not None:
            distances, indices = self.faiss_index.search(query_vector, candidate_k)
        elif index_type == "hnsw" and self.hnsw_index is not None:
            distances, indices = self.hnsw_index.search(query_vector, candidate_k)
        else:
            distances, indices = self._numpy_search(query_vector, candidate_k)

        results = self._collect_results(
            distances[0], indices[0], query_row, k, filter_spec, include_self
        )
        return {"results": results, "filter_stats": {"mode": "post_filter"}}

    def _search_conditional(
        self,
        query_vector: np.ndarray,
        query_cell_id: Optional[str],
        query_row: Optional[int],
        k: int,
        filter_spec: FilterSpec,
        index_type: str,
        include_self: bool,
    ) -> Dict[str, Any]:
        """条件检索：先构建布尔掩码，在子集上精确搜索 Top-K。

        流程：
          1. 根据 filter_spec 生成 row mask
          2. 提取子集向量
          3. 构建临时 FAISS 子索引
          4. 在子索引中搜索
          5. 将子索引结果映射回全局行号
        """
        mask = self._build_filter_mask(filter_spec)
        mask_count = int(mask.sum())

        if mask_count == 0:
            return {
                "results": [],
                "filter_stats": {
                    "mode": "pre_filter",
                    "total_cells": len(self.metadata),
                    "filtered_cells": 0,
                    "filter_ratio": 0.0,
                },
                "warnings": ["过滤条件未匹配到任何细胞"],
            }

        # 排除查询细胞自身（如果需要）
        if include_self is False and query_row is not None and mask[query_row]:
            mask[query_row] = False
            mask_count -= 1  # noqa (intentionally reassigned)

        if mask_count == 0:
            return {
                "results": [],
                "filter_stats": {
                    "mode": "pre_filter",
                    "total_cells": len(self.metadata),
                    "filtered_cells": int(np.sum(mask)),
                    "filter_ratio": 0.0,
                },
            }

        # 提取子向量
        subset_indices = np.where(mask)[0].astype(np.int64)
        subset_vectors = self.vectors[subset_indices].astype(np.float32)

        # 构建临时索引并搜索
        try:
            import faiss
            sub_index = faiss.IndexFlatL2(int(subset_vectors.shape[1]))
            sub_index.add(subset_vectors)
            sub_distances, sub_indices = sub_index.search(query_vector, min(k, mask_count))
        except ImportError:
            sub_distances, sub_indices = self._numpy_search_on_subset(
                query_vector, subset_vectors, min(k, mask_count)
            )

        # 映射回全局行号
        results = []
        for dist, sub_idx in zip(sub_distances[0], sub_indices[0]):
            sub_idx = int(sub_idx)
            if sub_idx < 0 or sub_idx >= len(subset_indices):
                continue
            global_idx = int(subset_indices[sub_idx])
            results.append(self._format_result(global_idx, float(dist)))

        return {
            "results": results,
            "filter_stats": {
                "mode": "pre_filter",
                "total_cells": len(self.metadata),
                "filtered_cells": mask_count,
                "filter_ratio": mask_count / max(1, len(self.metadata)),
                "conditions": filter_spec.to_dict(),
            },
        }

    def _search_cross_dataset(
        self,
        query_vector: np.ndarray,
        query_cell_id: Optional[str],
        query_row: Optional[int],
        k: int,
        filter_spec: FilterSpec,
        index_type: str,
        include_self: bool,
    ) -> Dict[str, Any]:
        """跨数据集检索：与标准搜索类似，但在结果中增强来源追踪。

        当 metadata 中存在 dataset_id 列时，返回每行所属来源。
        """
        # 核心逻辑与 _search_conditional 相同（预过滤版）
        if not filter_spec.is_empty:
            result = self._search_conditional(
                query_vector, query_cell_id, query_row, k, filter_spec, index_type, include_self
            )
        else:
            result = self._search_normal(
                query_vector, query_cell_id, query_row, k, filter_spec, index_type, include_self
            )

        # 附加跨数据集统计
        source_counts: Dict[str, int] = {}
        for r in result.get("results", []):
            ds_name = r.get("dataset_name", "unknown") or "unknown"
            source_counts[ds_name] = source_counts.get(ds_name, 0) + 1

        result["filter_stats"]["source_distribution"] = source_counts
        result["filter_stats"]["mode"] = "cross_dataset"
        return result

    # ---- 内部：过滤掩码 ----

    def _build_filter_mask(self, filter_spec: FilterSpec) -> np.ndarray:
        """生成布尔掩码：True = 该行满足所有过滤条件。"""
        n = len(self.metadata)
        mask = np.ones(n, dtype=bool)

        conditions = filter_spec.to_dict()
        if not conditions:
            return mask

        for col, expected in conditions.items():
            expected_lower = expected.lower()
            col_mask = np.zeros(n, dtype=bool)
            for i, row in enumerate(self.metadata):
                if str(row.get(col, "")).lower() == expected_lower:
                    col_mask[i] = True
            mask &= col_mask
            if not mask.any():
                break

        return mask

    # ---- 内部：结果收集 ----

    def _collect_results(
        self,
        distances: np.ndarray,
        indices: np.ndarray,
        query_row: Optional[int],
        k: int,
        filter_spec: FilterSpec,
        include_self: bool,
    ) -> List[Dict[str, Any]]:
        """后置过滤模式下发结果。"""
        results: List[Dict[str, Any]] = []
        for dist, idx in zip(distances, indices):
            idx = int(idx)
            if idx < 0 or idx >= len(self.metadata):
                continue
            if not include_self and query_row is not None and idx == query_row:
                continue
            if not filter_spec.is_empty and not self._row_matches(idx, filter_spec):
                continue
            results.append(self._format_result(idx, float(dist)))
            if len(results) >= k:
                break
        return results

    def _row_matches(self, row_idx: int, filter_spec: FilterSpec) -> bool:
        """检查某行是否满足过滤条件。"""
        row = self.metadata[row_idx]
        for col, expected in filter_spec.to_dict().items():
            if str(row.get(col, "")).lower() != expected.lower():
                return False
        return True

    # ---- 内部：查询向量构建 ----

    def _build_query(
        self, cell_id: Optional[str], vector: Optional[List[float]]
    ) -> Tuple[np.ndarray, Optional[str], Optional[int]]:
        if bool(cell_id) == bool(vector):
            raise SearchInputError("Provide exactly one of cell_id or vector")

        if cell_id:
            row_index = self.cell_id_to_row.get(cell_id)
            if row_index is None:
                raise SearchInputError(f"Unknown cell_id: {cell_id}")
            return (
                self.vectors[row_index].astype(np.float32).reshape(1, -1),
                cell_id,
                row_index,
            )

        arr = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        if arr.shape[1] != self.dimension:
            raise SearchInputError(
                f"Vector dimension must be {self.dimension}, got {arr.shape[1]}"
            )
        return arr, None, None

    # ---- 内部：结果格式化 ----

    def _format_result(self, row_index: int, distance: Optional[float]) -> Dict[str, Any]:
        row = self.metadata[row_index]
        selected_metadata = {
            field: row.get(field, "")
            for field in self.result_fields if field in row
        }
        return {
            "rank_source_index": row_index,
            "distance": distance,
            "cell_id": row.get("cell_id", ""),
            "dataset_id": row.get("dataset_id", ""),
            "dataset_name": row.get("dataset_name", ""),
            "dataset_group": row.get("dataset_group", ""),
            "dataset_source": row.get("dataset_source", ""),
            "cell_type": row.get("cell_type", ""),
            "disease": row.get("disease", ""),
            "expression": {
                "nCount_RNA": self._to_number(row.get("nCount_RNA")),
                "nFeature_RNA": self._to_number(row.get("nFeature_RNA")),
                "percent_mt": self._to_number(row.get("percent.mt")),
            },
            "metadata": selected_metadata,
        }

    # ---- 内部：辅助 ----

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if self._load_error:
            raise RuntimeError(f"Engine load failed: {self._load_error}")
        try:
            self.load()
        except Exception as exc:
            self._load_error = str(exc)
            raise

    @staticmethod
    def _load_metadata(path: str) -> List[Dict[str, str]]:
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    @staticmethod
    def _assert_file_exists(path: str, label: str) -> None:
        if not os.path.exists(path):
            raise FileNotFoundError(f"{label} not found: {path}")

    @staticmethod
    def _validate_k(k: int) -> int:
        try:
            k = int(k)
        except (TypeError, ValueError):
            raise SearchInputError("k must be an integer")
        if k < 1 or k > 100:
            raise SearchInputError("k must be between 1 and 100")
        return k

    @staticmethod
    def _validate_nprobe(nprobe: int) -> int:
        try:
            nprobe = int(nprobe)
        except (TypeError, ValueError):
            raise SearchInputError("nprobe must be an integer")
        if nprobe < 1:
            raise SearchInputError("nprobe must be positive")
        return nprobe

    def _candidate_count(self, k: int, has_filters: bool, include_self: bool) -> int:
        multiplier = 10 if has_filters else 2
        extra = 0 if include_self else 1
        return min(len(self.metadata), max(k + extra, k * multiplier))

    def _numpy_search(
        self, query_vector: np.ndarray, k: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """NumPy 精确 L2 搜索（FAISS 不可用时的降级方案）。"""
        vecs = self.vectors.astype(np.float32)
        diff = vecs - query_vector.astype(np.float32)
        distances = np.sum(diff * diff, axis=1)
        n = min(k, len(distances))
        if n == len(distances):
            order = np.argsort(distances)
        else:
            partial = np.argpartition(distances, n - 1)[:n]
            order = partial[np.argsort(distances[partial])]
        return distances[order].reshape(1, -1), order.astype(np.int64).reshape(1, -1)

    @staticmethod
    def _numpy_search_on_subset(
        query_vector: np.ndarray, subset_vectors: np.ndarray, k: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """在子向量集上精确 L2 搜索。"""
        diff = subset_vectors.astype(np.float32) - query_vector.astype(np.float32)
        distances = np.sum(diff * diff, axis=1)
        n = min(k, len(distances))
        if n == len(distances):
            order = np.argsort(distances)
        else:
            partial = np.argpartition(distances, n - 1)[:n]
            order = partial[np.argsort(distances[partial])]
        return distances[order].reshape(1, -1), order.astype(np.int64).reshape(1, -1)

    @staticmethod
    def _to_number(value: Optional[str]) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------

def auto_nlist(n_vectors: int, min_nlist: int = 4, max_nlist: int = 1024) -> int:
    """根据向量数量自动计算 IVF 聚类数。

    使用经验公式 nlist ≈ 4 * sqrt(N)，结果限定在 [min_nlist, max_nlist]。
    """
    from math import sqrt
    candidate = int(4 * sqrt(max(1, n_vectors)))
    return max(min_nlist, min(max_nlist, candidate))


def build_filter_mask_from_csv(
    metadata_path: str, filter_spec: FilterSpec
) -> Tuple[np.ndarray, int]:
    """不加载全量 metadata 的情况下快速构建过滤掩码（用于大规模数据）。"""
    conditions = filter_spec.to_dict()
    if not conditions:
        return np.array([]), 0

    with open(metadata_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    n = len(rows)
    mask = np.ones(n, dtype=bool)
    for col, expected in conditions.items():
        expected_lower = expected.lower()
        col_mask = np.zeros(n, dtype=bool)
        for i, row in enumerate(rows):
            if str(row.get(col, "")).lower() == expected_lower:
                col_mask[i] = True
        mask &= col_mask
        if not mask.any():
            break

    return mask, n
