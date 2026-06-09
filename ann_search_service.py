import csv
import os
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_FIELDS = [
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


class SearchInputError(ValueError):
    """Raised when a client query cannot be executed."""


class SingleCellANNService:
    """Top-K search wrapper for the prebuilt single-cell FAISS index."""

    def __init__(
        self,
        index_path: str = "faiss_index.bin",
        vectors_path: str = "cleaned_pca_vectors.npy",
        metadata_path: str = "cleaned_cell_metadata.csv",
        result_fields: Optional[Iterable[str]] = None,
    ) -> None:
        self.index_path = index_path
        self.vectors_path = vectors_path
        self.metadata_path = metadata_path
        self.result_fields = list(result_fields or DEFAULT_FIELDS)

        self.index = None
        self.vectors = None
        self.metadata: List[Dict[str, str]] = []
        self.cell_id_to_row: Dict[str, int] = {}
        self.dimension: Optional[int] = None
        self._load_attempted = False
        self._load_error: Optional[str] = None
        self._faiss_available = True

    def configure_paths(
        self,
        *,
        index_path: str,
        vectors_path: str,
        metadata_path: str,
    ) -> None:
        self.index_path = index_path
        self.vectors_path = vectors_path
        self.metadata_path = metadata_path
        self.index = None
        self.vectors = None
        self.metadata = []
        self.cell_id_to_row = {}
        self.dimension = None
        self._load_attempted = False
        self._load_error = None
        self._faiss_available = True

    def load(self) -> None:
        """Load the FAISS index, PCA vectors and metadata into the service."""
        self._assert_file_exists(self.index_path, "FAISS index")
        self._assert_file_exists(self.vectors_path, "PCA vector file")
        self._assert_file_exists(self.metadata_path, "metadata file")

        try:
            import faiss
            self.index = faiss.read_index(self.index_path)
            self._faiss_available = True
        except ImportError:
            self.index = None
            self._faiss_available = False

        import numpy as np
        self.vectors = np.load(self.vectors_path, mmap_mode="r")
        self.metadata = self._load_metadata(self.metadata_path)
        self.cell_id_to_row = {
            row.get("cell_id", ""): idx
            for idx, row in enumerate(self.metadata)
            if row.get("cell_id")
        }

        if len(self.vectors) != len(self.metadata):
            raise RuntimeError(
                "Vector count and metadata count do not match: "
                f"{len(self.vectors)} vectors vs {len(self.metadata)} metadata rows"
            )

        if self.index is not None and self.index.ntotal != len(self.metadata):
            raise RuntimeError(
                "FAISS index size and metadata count do not match: "
                f"{self.index.ntotal} indexed vectors vs {len(self.metadata)} metadata rows"
            )

        self.dimension = int(self.vectors.shape[1])
        self._load_attempted = False
        self._load_error = None

    def status(self) -> Dict[str, Any]:
        self._ensure_loaded()
        return {
            "loaded": True,
            "index_path": self.index_path,
            "vectors_path": self.vectors_path,
            "metadata_path": self.metadata_path,
            "cell_count": len(self.metadata),
            "index_total": int(self.index.ntotal) if self.index is not None else len(self.metadata),
            "dimension": self.dimension,
            "index_engine": "faiss",
            "faiss_available": self._faiss_available,
            "fallback_engine": None if self._faiss_available else "numpy_l2",
        }

    def get_cell(self, cell_id: str) -> Dict[str, Any]:
        self._ensure_loaded()
        row_index = self.cell_id_to_row.get(cell_id)
        if row_index is None:
            raise SearchInputError(f"Unknown cell_id: {cell_id}")
        return self._format_result(row_index, distance=None)

    def search(
        self,
        *,
        cell_id: Optional[str] = None,
        vector: Optional[List[float]] = None,
        k: int = 10,
        nprobe: Optional[int] = None,
        include_self: bool = False,
        filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Search top-k similar cells by cell_id or raw PCA vector."""
        self._ensure_loaded()
        filters = filters or {}
        k = self._validate_k(k)
        query_vector, query_cell_id, query_row = self._build_query(cell_id, vector)

        if nprobe is not None and self.index is not None and hasattr(self.index, "nprobe"):
            self.index.nprobe = self._validate_nprobe(nprobe)

        started = time.perf_counter()
        candidate_k = self._candidate_count(k, bool(filters), include_self)
        if self.index is not None:
            distances, indices = self.index.search(query_vector, candidate_k)
        else:
            distances, indices = self._numpy_search(query_vector, candidate_k)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)

        results = []
        for distance, row_index in zip(distances[0], indices[0]):
            row_index = int(row_index)
            if row_index < 0:
                continue
            if not include_self and query_row is not None and row_index == query_row:
                continue
            if not self._matches_filters(self.metadata[row_index], filters):
                continue
            results.append(self._format_result(row_index, float(distance)))
            if len(results) >= k:
                break

        return {
            "query": {
                "cell_id": query_cell_id,
                "row_index": query_row,
                "dimension": self.dimension,
                "k": k,
                "nprobe": getattr(self.index, "nprobe", None) if self.index is not None else None,
                "include_self": include_self,
                "filters": filters,
            },
            "elapsed_ms": elapsed_ms,
            "result_count": len(results),
            "results": results,
            "warnings": [] if self._faiss_available else [
                "faiss-cpu 未安装，当前使用 NumPy 精确 L2 检索降级模式。"
            ],
        }

    def _is_loaded(self) -> bool:
        return self.vectors is not None and bool(self.metadata)

    def _ensure_loaded(self) -> None:
        if self._is_loaded():
            return
        if self._load_attempted:
            raise RuntimeError(
                f"之前加载失败: {self._load_error}"
            )
        self._load_attempted = True
        try:
            self.load()
        except Exception as e:
            self._load_error = str(e)
            raise

    def _build_query(
        self, cell_id: Optional[str], vector: Optional[List[float]]
    ) -> Tuple[Any, Optional[str], Optional[int]]:
        if bool(cell_id) == bool(vector):
            raise SearchInputError("Provide exactly one of cell_id or vector")

        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError(
                "Missing runtime dependency. Install with: "
                "pip install -r requirements.txt"
            ) from exc

        if cell_id:
            row_index = self.cell_id_to_row.get(cell_id)
            if row_index is None:
                raise SearchInputError(f"Unknown cell_id: {cell_id}")
            return (
                self.vectors[row_index].astype("float32").reshape(1, -1),
                cell_id,
                row_index,
            )

        query = np.asarray(vector, dtype="float32").reshape(1, -1)
        if query.shape[1] != self.dimension:
            raise SearchInputError(
                f"Vector dimension must be {self.dimension}, got {query.shape[1]}"
            )
        return query, None, None

    def _format_result(
        self, row_index: int, distance: Optional[float]
    ) -> Dict[str, Any]:
        row = self.metadata[row_index]
        selected_metadata = {
            field: row.get(field, "")
            for field in self.result_fields
            if field in row
        }
        return {
            "rank_source_index": row_index,
            "distance": distance,
            "cell_id": row.get("cell_id", ""),
            "dataset_id": row.get("dataset_id", ""),
            "dataset_name": row.get("dataset_name", ""),
            "dataset_group": row.get("dataset_group", ""),
            "cell_type": row.get("cell_type", ""),
            "disease": row.get("disease", ""),
            "expression": {
                "nCount_RNA": self._to_number(row.get("nCount_RNA")),
                "nFeature_RNA": self._to_number(row.get("nFeature_RNA")),
                "percent_mt": self._to_number(row.get("percent.mt")),
            },
            "metadata": selected_metadata,
        }

    @staticmethod
    def _load_metadata(metadata_path: str) -> List[Dict[str, str]]:
        with open(metadata_path, encoding="utf-8-sig", newline="") as file_obj:
            return list(csv.DictReader(file_obj))

    @staticmethod
    def _assert_file_exists(path: str, label: str) -> None:
        if not os.path.exists(path):
            raise FileNotFoundError(f"{label} not found: {path}")

    @staticmethod
    def _validate_k(k: int) -> int:
        try:
            value = int(k)
        except (TypeError, ValueError) as exc:
            raise SearchInputError("k must be an integer") from exc
        if value < 1 or value > 100:
            raise SearchInputError("k must be between 1 and 100")
        return value

    @staticmethod
    def _validate_nprobe(nprobe: int) -> int:
        try:
            value = int(nprobe)
        except (TypeError, ValueError) as exc:
            raise SearchInputError("nprobe must be an integer") from exc
        if value < 1:
            raise SearchInputError("nprobe must be positive")
        return value

    def _candidate_count(self, k: int, has_filters: bool, include_self: bool) -> int:
        multiplier = 10 if has_filters else 2
        extra = 0 if include_self else 1
        return min(len(self.metadata), max(k + extra, k * multiplier))

    @staticmethod
    def _matches_filters(row: Dict[str, str], filters: Dict[str, str]) -> bool:
        for key, expected in filters.items():
            if key not in row:
                return False
            if str(row.get(key, "")).lower() != str(expected).lower():
                return False
        return True

    def _numpy_search(self, query_vector: Any, k: int) -> Tuple[Any, Any]:
        import numpy as np

        diff = self.vectors.astype("float32") - query_vector.astype("float32")
        distances = np.sum(diff * diff, axis=1)
        candidate_count = min(k, len(distances))
        if candidate_count == len(distances):
            order = np.argsort(distances)
        else:
            partial = np.argpartition(distances, candidate_count - 1)[:candidate_count]
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
