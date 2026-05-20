import csv
import os
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from hnsw_index import HNSWIndex


DEFAULT_FIELDS = [
    "cell_id",
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


class HNSWSearchService:
    """Top-K search wrapper for the prebuilt HNSW index."""

    def __init__(
        self,
        index_path: str = "hnsw_index.npz",
        vectors_path: str = "cleaned_pca_vectors.npy",
        metadata_path: str = "cleaned_cell_metadata.csv",
        result_fields: Optional[Iterable[str]] = None,
    ) -> None:
        self.index_path = index_path
        self.vectors_path = vectors_path
        self.metadata_path = metadata_path
        self.result_fields = list(result_fields or DEFAULT_FIELDS)

        self.index: Optional[HNSWIndex] = None
        self.vectors = None
        self.metadata: List[Dict[str, str]] = []
        self.cell_id_to_row: Dict[str, int] = {}
        self.dimension: Optional[int] = None
        self._load_attempted = False
        self._load_error: Optional[str] = None

    def load(self) -> None:
        """Load the HNSW index, PCA vectors and metadata into the service."""
        self._assert_file_exists(self.index_path, "HNSW index")
        self._assert_file_exists(self.vectors_path, "PCA vector file")
        self._assert_file_exists(self.metadata_path, "metadata file")

        self.index = HNSWIndex.load_index(self.index_path)
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

        if self.index.vectors is not None and len(self.index.vectors) != len(self.metadata):
            raise RuntimeError(
                "HNSW index size and metadata count do not match: "
                f"{len(self.index.vectors)} indexed vectors vs {len(self.metadata)} metadata rows"
            )

        self.dimension = int(self.vectors.shape[1])
        self._load_attempted = False  # Reset so future _ensure_loaded calls don't short-circuit
        self._load_error = None

    def status(self) -> Dict[str, Any]:
        self._ensure_loaded()
        if not self._is_loaded():
            return {
                "loaded": False,
                "error": self._load_error or "Service not loaded",
            }
        return {
            "loaded": True,
            "index_path": self.index_path,
            "vectors_path": self.vectors_path,
            "metadata_path": self.metadata_path,
            "cell_count": len(self.metadata),
            "index_total": len(self.index.vectors) if self.index and self.index.vectors is not None else 0,
            "dimension": self.dimension,
            "index_engine": "hnsw",
            "M": self.index.M if self.index else None,
            "ef": self.index.ef if self.index else None,
            "efConstruction": self.index.efConstruction if self.index else None,
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
        nprobe: Optional[int] = None,  # Not used for HNSW
        include_self: bool = False,
        filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Search top-k similar cells by cell_id or raw PCA vector."""
        self._ensure_loaded()
        filters = filters or {}
        k = self._validate_k(k)
        query_vector, query_cell_id, query_row = self._build_query(cell_id, vector)

        started = time.perf_counter()
        candidate_k = self._candidate_count(k, bool(filters), include_self)
        distances, indices = self.index.search(query_vector, candidate_k)
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
                "include_self": include_self,
                "filters": filters,
            },
            "elapsed_ms": elapsed_ms,
            "result_count": len(results),
            "results": results,
            "engine": "hnsw",
            "warnings": ["nprobe参数对HNSW索引无效，已忽略"] if nprobe is not None else [],
        }

    def _is_loaded(self) -> bool:
        return self.index is not None and self.vectors is not None and bool(self.metadata)

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

    @staticmethod
    def _to_number(value: Optional[str]) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except ValueError:
            return None
