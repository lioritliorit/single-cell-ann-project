import csv
import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np


class DatasetError(RuntimeError):
    """Raised when dataset import, indexing, or cleanup fails."""


@dataclass(frozen=True)
class DatasetPaths:
    h5ad_path: Optional[str]
    vectors_path: str
    metadata_path: str
    faiss_index_path: str
    hnsw_index_path: Optional[str] = None


class DatasetManager:
    """Persistent dataset registry and FAISS index builder for h5ad imports."""

    def __init__(
        self,
        base_dir: str = "datasets",
        default_vectors_path: str = "cleaned_pca_vectors.npy",
        default_metadata_path: str = "cleaned_cell_metadata.csv",
        default_faiss_index_path: str = "faiss_index.bin",
        default_hnsw_index_path: str = "hnsw_index.npz",
    ) -> None:
        self.base_dir = Path(base_dir)
        self.upload_dir = self.base_dir / "uploads"
        self.processed_dir = self.base_dir / "processed"
        self.joint_dir = self.base_dir / "joint"
        self.manifest_path = self.base_dir / "manifest.json"
        self.default_vectors_path = default_vectors_path
        self.default_metadata_path = default_metadata_path
        self.default_faiss_index_path = default_faiss_index_path
        self.default_hnsw_index_path = default_hnsw_index_path
        self._ensure_layout()
        self._ensure_default_dataset()

    def _ensure_layout(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.joint_dir.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self._write_manifest({
                "active_dataset_id": "default",
                "datasets": {},
                "updated_at": self._now(),
            })

    def _ensure_default_dataset(self) -> None:
        manifest = self._read_manifest()
        datasets = manifest.setdefault("datasets", {})
        if "default" in datasets:
            return
        if not (
            Path(self.default_vectors_path).exists()
            and Path(self.default_metadata_path).exists()
            and Path(self.default_faiss_index_path).exists()
        ):
            return

        summary = self._summarize_metadata(self.default_metadata_path)
        datasets["default"] = {
            "id": "default",
            "name": "Default single-cell dataset",
            "kind": "single",
            "group": "regular",
            "source": "project bundled files",
            "description": "Initial dataset from cleaned_cell_metadata.csv and cleaned_pca_vectors.npy.",
            "created_at": self._now(),
            "updated_at": self._now(),
            "h5ad_path": None,
            "vectors_path": self.default_vectors_path,
            "metadata_path": self.default_metadata_path,
            "faiss_index_path": self.default_faiss_index_path,
            "hnsw_index_path": self.default_hnsw_index_path if Path(self.default_hnsw_index_path).exists() else None,
            "cell_count": summary["cell_count"],
            "dimension": self._vector_dimension(self.default_vectors_path),
            "cell_types": summary["cell_types"],
            "diseases": summary["diseases"],
            "tissues": summary["tissues"],
            "tags": ["regular"],
            "component_dataset_ids": ["default"],
        }
        manifest["active_dataset_id"] = manifest.get("active_dataset_id") or "default"
        manifest["updated_at"] = self._now()
        self._write_manifest(manifest)

    def list_datasets(self) -> Dict[str, Any]:
        manifest = self._read_manifest()
        datasets = sorted(
            manifest.get("datasets", {}).values(),
            key=lambda item: (item.get("kind") != "single", item.get("created_at", "")),
        )
        return {
            "active_dataset_id": manifest.get("active_dataset_id"),
            "datasets": datasets,
        }

    def get_active_dataset(self) -> Dict[str, Any]:
        manifest = self._read_manifest()
        dataset_id = manifest.get("active_dataset_id", "default")
        return self.get_dataset(dataset_id)

    def get_dataset(self, dataset_id: str) -> Dict[str, Any]:
        datasets = self._read_manifest().get("datasets", {})
        if dataset_id not in datasets:
            raise DatasetError(f"Unknown dataset_id: {dataset_id}")
        return datasets[dataset_id]

    def set_active_dataset(self, dataset_id: str) -> Dict[str, Any]:
        manifest = self._read_manifest()
        if dataset_id not in manifest.get("datasets", {}):
            raise DatasetError(f"Unknown dataset_id: {dataset_id}")
        manifest["active_dataset_id"] = dataset_id
        manifest["updated_at"] = self._now()
        self._write_manifest(manifest)
        return manifest["datasets"][dataset_id]

    def dataset_paths(self, dataset: Dict[str, Any]) -> DatasetPaths:
        return DatasetPaths(
            h5ad_path=dataset.get("h5ad_path"),
            vectors_path=dataset["vectors_path"],
            metadata_path=dataset["metadata_path"],
            faiss_index_path=dataset["faiss_index_path"],
            hnsw_index_path=dataset.get("hnsw_index_path"),
        )

    def import_h5ad(
        self,
        file_storage: Any,
        *,
        name: Optional[str] = None,
        source: str = "",
        group: str = "regular",
        description: str = "",
        tags: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        original_name = getattr(file_storage, "filename", "") or "dataset.h5ad"
        if not original_name.lower().endswith(".h5ad"):
            raise DatasetError("Only .h5ad files are supported")

        dataset_id = self._unique_dataset_id(name or Path(original_name).stem)
        upload_path = self.upload_dir / f"{dataset_id}.h5ad"
        file_storage.save(str(upload_path))

        try:
            dataset = self._process_h5ad(
                dataset_id=dataset_id,
                h5ad_path=upload_path,
                name=name or Path(original_name).stem,
                source=source,
                group=group,
                description=description,
                tags=list(tags or []),
            )
            manifest = self._read_manifest()
            manifest.setdefault("datasets", {})[dataset_id] = dataset
            manifest["active_dataset_id"] = dataset_id
            manifest["updated_at"] = self._now()
            self._write_manifest(manifest)
            return dataset
        except Exception:
            self._safe_remove(upload_path)
            self._safe_remove(self.processed_dir / dataset_id)
            raise

    def delete_dataset(self, dataset_id: str) -> Dict[str, Any]:
        if dataset_id == "default":
            raise DatasetError("The bundled default dataset cannot be deleted")
        manifest = self._read_manifest()
        datasets = manifest.get("datasets", {})
        if dataset_id not in datasets:
            raise DatasetError(f"Unknown dataset_id: {dataset_id}")

        dataset = datasets.pop(dataset_id)
        for key in ("h5ad_path", "vectors_path", "metadata_path", "faiss_index_path", "hnsw_index_path"):
            path = dataset.get(key)
            if path:
                self._safe_remove(Path(path))
        self._safe_remove(self.processed_dir / dataset_id)
        self._safe_remove(self.joint_dir / dataset_id)

        for item in datasets.values():
            components = item.get("component_dataset_ids") or []
            if dataset_id in components:
                item["stale"] = True
                item["stale_reason"] = f"Component dataset {dataset_id} was deleted"

        if manifest.get("active_dataset_id") == dataset_id:
            manifest["active_dataset_id"] = "default" if "default" in datasets else next(iter(datasets), None)
        manifest["updated_at"] = self._now()
        self._write_manifest(manifest)
        return {"deleted": dataset_id, "active_dataset_id": manifest.get("active_dataset_id")}

    def build_joint_index(
        self,
        dataset_ids: List[str],
        *,
        name: str = "Joint dataset",
        group: str = "joint",
        description: str = "",
    ) -> Dict[str, Any]:
        if len(dataset_ids) < 2:
            raise DatasetError("Joint index requires at least two datasets")

        datasets = [self.get_dataset(dataset_id) for dataset_id in dataset_ids]
        dimensions = {int(item.get("dimension") or 0) for item in datasets}
        if len(dimensions) != 1:
            raise DatasetError(f"Vector dimensions do not match: {sorted(dimensions)}")

        joint_id = self._unique_dataset_id(name, prefix="joint")
        out_dir = self.joint_dir / joint_id
        out_dir.mkdir(parents=True, exist_ok=True)

        vectors = []
        rows: List[Dict[str, str]] = []
        fieldnames = set()
        for dataset in datasets:
            current_vectors = np.load(dataset["vectors_path"]).astype(np.float32)
            vectors.append(current_vectors)
            with open(dataset["metadata_path"], encoding="utf-8-sig", newline="") as file_obj:
                for row in csv.DictReader(file_obj):
                    row = dict(row)
                    row["dataset_id"] = dataset["id"]
                    row["dataset_name"] = dataset["name"]
                    row["dataset_group"] = dataset.get("group", "")
                    row["dataset_source"] = dataset.get("source", "")
                    rows.append(row)
                    fieldnames.update(row.keys())

        merged_vectors = np.vstack(vectors).astype(np.float32)
        metadata_path = out_dir / "metadata.csv"
        vectors_path = out_dir / "vectors.npy"
        index_path = out_dir / "faiss_index.bin"
        np.save(vectors_path, merged_vectors)
        self._write_metadata(metadata_path, rows, fieldnames)
        self._build_faiss_index(merged_vectors, index_path)

        summary = self._summarize_metadata(str(metadata_path))
        dataset = {
            "id": joint_id,
            "name": name,
            "kind": "joint",
            "group": group,
            "source": " + ".join(item.get("source") or item["name"] for item in datasets),
            "description": description or "Joint FAISS index over selected datasets.",
            "created_at": self._now(),
            "updated_at": self._now(),
            "h5ad_path": None,
            "vectors_path": str(vectors_path),
            "metadata_path": str(metadata_path),
            "faiss_index_path": str(index_path),
            "hnsw_index_path": None,
            "cell_count": int(merged_vectors.shape[0]),
            "dimension": int(merged_vectors.shape[1]),
            "cell_types": summary["cell_types"],
            "diseases": summary["diseases"],
            "tissues": summary["tissues"],
            "tags": ["joint", group],
            "component_dataset_ids": dataset_ids,
        }

        manifest = self._read_manifest()
        manifest.setdefault("datasets", {})[joint_id] = dataset
        manifest["active_dataset_id"] = joint_id
        manifest["updated_at"] = self._now()
        self._write_manifest(manifest)
        return dataset

    def _process_h5ad(
        self,
        *,
        dataset_id: str,
        h5ad_path: Path,
        name: str,
        source: str,
        group: str,
        description: str,
        tags: List[str],
    ) -> Dict[str, Any]:
        adata = self._read_h5ad(str(h5ad_path))
        if "X_pca" not in adata.obsm:
            raise DatasetError("Uploaded h5ad must contain adata.obsm['X_pca']")

        vectors = np.asarray(adata.obsm["X_pca"], dtype=np.float32)
        metadata = adata.obs.copy()
        metadata.insert(0, "cell_id", metadata.index.astype(str))
        metadata["dataset_id"] = dataset_id
        metadata["dataset_name"] = name
        metadata["dataset_group"] = group
        metadata["dataset_source"] = source

        valid_mask = ~(np.isnan(vectors).any(axis=1) | np.isinf(vectors).any(axis=1))
        vectors = vectors[valid_mask]
        metadata = metadata.iloc[valid_mask].reset_index(drop=True)

        out_dir = self.processed_dir / dataset_id
        out_dir.mkdir(parents=True, exist_ok=True)
        vectors_path = out_dir / "vectors.npy"
        metadata_path = out_dir / "metadata.csv"
        index_path = out_dir / "faiss_index.bin"
        np.save(vectors_path, vectors.astype(np.float32))
        metadata.to_csv(metadata_path, index=False, encoding="utf-8-sig")
        self._build_faiss_index(vectors, index_path)

        summary = self._summarize_metadata(str(metadata_path))
        disease_tags = [f"liver:{d}" for d in summary["diseases"] if "liver" in d.lower() or "hep" in d.lower()]
        combined_tags = sorted(set([tag for tag in tags if tag] + disease_tags + [group]))

        return {
            "id": dataset_id,
            "name": name,
            "kind": "single",
            "group": group,
            "source": source,
            "description": description,
            "created_at": self._now(),
            "updated_at": self._now(),
            "h5ad_path": str(h5ad_path),
            "vectors_path": str(vectors_path),
            "metadata_path": str(metadata_path),
            "faiss_index_path": str(index_path),
            "hnsw_index_path": None,
            "cell_count": int(vectors.shape[0]),
            "dimension": int(vectors.shape[1]),
            "cell_types": summary["cell_types"],
            "diseases": summary["diseases"],
            "tissues": summary["tissues"],
            "tags": combined_tags,
            "component_dataset_ids": [dataset_id],
        }

    @staticmethod
    def _read_h5ad(path: str) -> Any:
        try:
            import scanpy as sc
            return sc.read_h5ad(path)
        except ImportError:
            try:
                import anndata as ad
                return ad.read_h5ad(path)
            except ImportError as exc:
                raise DatasetError("Install scanpy or anndata to import .h5ad files") from exc

    @staticmethod
    def _build_faiss_index(vectors: np.ndarray, index_path: Path) -> None:
        try:
            import faiss
        except ImportError as exc:
            raise DatasetError("Install faiss-cpu before building indexes") from exc
        if vectors.ndim != 2 or vectors.shape[0] == 0:
            raise DatasetError("Cannot build an index for an empty vector matrix")
        index = faiss.IndexFlatL2(int(vectors.shape[1]))
        index.add(vectors.astype(np.float32))
        faiss.write_index(index, str(index_path))

    @staticmethod
    def _summarize_metadata(metadata_path: str) -> Dict[str, Any]:
        cell_types, diseases, tissues = set(), set(), set()
        count = 0
        with open(metadata_path, encoding="utf-8-sig", newline="") as file_obj:
            for row in csv.DictReader(file_obj):
                count += 1
                for key, target in (("cell_type", cell_types), ("disease", diseases), ("tissue", tissues)):
                    value = (row.get(key) or "").strip()
                    if value:
                        target.add(value)
        return {
            "cell_count": count,
            "cell_types": sorted(cell_types),
            "diseases": sorted(diseases),
            "tissues": sorted(tissues),
        }

    @staticmethod
    def _write_metadata(path: Path, rows: List[Dict[str, str]], fieldnames: Iterable[str]) -> None:
        ordered = ["cell_id", "dataset_id", "dataset_name", "dataset_group", "dataset_source"]
        ordered.extend(sorted(key for key in fieldnames if key not in ordered))
        with open(path, "w", encoding="utf-8-sig", newline="") as file_obj:
            writer = csv.DictWriter(file_obj, fieldnames=ordered, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _vector_dimension(vectors_path: str) -> Optional[int]:
        try:
            vectors = np.load(vectors_path, mmap_mode="r")
            return int(vectors.shape[1])
        except Exception:
            return None

    def _unique_dataset_id(self, value: str, prefix: str = "ds") -> str:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
        slug = slug[:48] or prefix
        candidate = slug if slug.startswith(prefix) else f"{prefix}-{slug}"
        datasets = self._read_manifest().get("datasets", {})
        if candidate not in datasets:
            return candidate
        return f"{candidate}-{int(time.time())}"

    def _read_manifest(self) -> Dict[str, Any]:
        with open(self.manifest_path, encoding="utf-8") as file_obj:
            return json.load(file_obj)

    def _write_manifest(self, manifest: Dict[str, Any]) -> None:
        tmp_path = self.manifest_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as file_obj:
            json.dump(manifest, file_obj, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.manifest_path)

    @staticmethod
    def _safe_remove(path: Path) -> None:
        if not path.exists():
            return
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
