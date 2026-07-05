import json
import logging
import os
import random
import threading
import time
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import numpy as np
import requests
from flask import Flask, jsonify, render_template, request
from datetime import datetime

from ann_search_service import SearchInputError, SingleCellANNService
from auth_manager import AuthError, AuthManager
from dataset_manager import DatasetError, DatasetManager
from hnsw_search_service import HNSWSearchService
from performance_evaluator import PerformanceEvaluator

# ---- 检索调试日志 ----
_search_logger = logging.getLogger("search_debug")
_search_logger.setLevel(logging.DEBUG)
# 使用线程安全的FileHandler
_search_log_handler = logging.FileHandler(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "search_debug.log"),
    encoding="utf-8",
)
_search_log_handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
))
_search_logger.addHandler(_search_log_handler)
_search_logger.propagate = False
# 日志锁，防止并发写入问题
_log_lock = threading.Lock()


def _log_search(mode: str, dataset_id: str, engine: str, elapsed: float,
                k: int, result_count: int, filters: Dict[str, str],
                filter_stats: Dict[str, Any]) -> None:
    """记录每次检索请求的关键参数，作为跨库检索调试日志。"""
    try:
        with _log_lock:
            _search_logger.debug(
                json.dumps({
                    "mode": mode,
                    "dataset_id": dataset_id,
                    "engine": engine,
                    "elapsed_ms": elapsed,
                    "k": k,
                    "result_count": result_count,
                    "filters": filters,
                    "filter_stats": filter_stats,
                }, ensure_ascii=False)
            )
    except Exception:
        # 日志写入失败不影响主流程
        pass


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_H5AD_UPLOAD_MB", "2048")) * 1024 * 1024

    auth_manager = AuthManager(os.getenv("AUTH_DB_PATH", "auth.db"))
    auth_manager.ensure_admin(
        os.getenv("ADMIN_USERNAME", "admin"),
        os.getenv("ADMIN_PASSWORD", "admin123"),
        email=os.getenv("ADMIN_EMAIL", ""),
    )

    dataset_manager = DatasetManager(
        default_vectors_path=os.getenv("ANN_VECTORS_PATH", "cleaned_pca_vectors.npy"),
        default_metadata_path=os.getenv("ANN_METADATA_PATH", "cleaned_cell_metadata.csv"),
        default_faiss_index_path=os.getenv("ANN_INDEX_PATH", "faiss_index.bin"),
        default_hnsw_index_path=os.getenv("HNSW_INDEX_PATH", "hnsw_index.npz"),
    )
    active_dataset = dataset_manager.get_active_dataset()
    active_paths = dataset_manager.dataset_paths(active_dataset)

    faiss_service = SingleCellANNService(
        index_path=active_paths.faiss_index_path,
        vectors_path=active_paths.vectors_path,
        metadata_path=active_paths.metadata_path,
    )
    hnsw_service = HNSWSearchService(
        index_path=active_paths.hnsw_index_path or "__missing_hnsw_index__.npz",
        vectors_path=active_paths.vectors_path,
        metadata_path=active_paths.metadata_path,
    )

    viz_cache: Dict[str, Any] = {}
    current_index_type = "faiss"
    index_lock = threading.Lock()

    def extract_token() -> str:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            return auth_header.split(" ", 1)[1].strip()
        return request.headers.get("X-Auth-Token", "").strip() or request.cookies.get("auth_token", "")

    def current_user() -> Optional[Dict[str, Any]]:
        return auth_manager.user_from_token(extract_token())

    def require_user(handler: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(handler)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            user = current_user()
            if not user:
                raise AuthError("authentication required", 401)
            request.current_user = user  # type: ignore[attr-defined]
            return handler(*args, **kwargs)
        return wrapper

    def require_admin(handler: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(handler)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            user = current_user()
            if not user:
                raise AuthError("authentication required", 401)
            if user.get("role") != "admin":
                raise AuthError("admin role required", 403)
            request.current_user = user  # type: ignore[attr-defined]
            return handler(*args, **kwargs)
        return wrapper

    def active_dataset_for_request() -> Dict[str, Any]:
        dataset = dataset_manager.get_active_dataset()
        user = current_user()
        if not auth_manager.can_view_dataset(user, dataset):
            raise AuthError("current user cannot access active dataset", 403)
        return dataset

    def dataset_with_policy(dataset: Dict[str, Any]) -> Dict[str, Any]:
        item = dict(dataset)
        item["permission"] = auth_manager.get_dataset_policy(dataset["id"], dataset)
        return item

    def visible_datasets(user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = dataset_manager.list_datasets()
        datasets = [
            dataset_with_policy(dataset)
            for dataset in payload.get("datasets", [])
            if auth_manager.can_view_dataset(user, dataset)
        ]
        return {
            "active_dataset_id": payload.get("active_dataset_id"),
            "datasets": datasets,
            "current_user": user,
        }

    def parse_natural_language_query(text: str) -> Dict[str, str]:
        lowered = (text or "").lower()
        filters: Dict[str, str] = {}
        cell_type_aliases = {
            "hepatocyte": ["hepatocyte", "肝细胞"],
            "kupffer cell": ["kupffer", "库普弗", "kupffer细胞"],
            "t cell": ["t cell", "t-cell", "t细胞", "t淋巴细胞"],
            "b cell": ["b cell", "b-cell", "b细胞", "b淋巴细胞"],
            "natural killer cell": ["natural killer", "nk cell", "nk细胞", "自然杀伤"],
            "cholangiocyte": ["cholangiocyte", "胆管"],
            "macrophage": ["macrophage", "巨噬"],
            "neutrophil": ["neutrophil", "中性粒"],
            "dendritic cell": ["dendritic", "树突"],
            "plasma cell": ["plasma cell", "浆细胞"],
            "hematopoietic stem cell": ["stem cell", "干细胞", "造血"],
        }
        disease_aliases = {
            "normal": ["normal", "healthy", "正常", "健康"],
            "cirrhosis": ["cirrhosis", "肝硬化"],
            "fibrosis": ["fibrosis", "纤维化"],
            "hepatitis": ["hepatitis", "肝炎"],
            "hcc": ["hcc", "carcinoma", "肝癌", "肿瘤"],
        }
        for value, aliases in cell_type_aliases.items():
            if any(alias in lowered or alias in text for alias in aliases):
                filters["cell_type"] = value
                break
        for value, aliases in disease_aliases.items():
            if any(alias in lowered or alias in text for alias in aliases):
                filters["disease"] = value
                break
        return filters

    def get_search_service():
        return faiss_service if current_index_type == "faiss" else hnsw_service

    def configure_services_for_dataset(dataset: Dict[str, Any]) -> None:
        nonlocal current_index_type
        paths = dataset_manager.dataset_paths(dataset)
        faiss_service.configure_paths(
            index_path=paths.faiss_index_path,
            vectors_path=paths.vectors_path,
            metadata_path=paths.metadata_path,
        )
        hnsw_service.configure_paths(
            index_path=paths.hnsw_index_path or "__missing_hnsw_index__.npz",
            vectors_path=paths.vectors_path,
            metadata_path=paths.metadata_path,
        )
        if current_index_type == "hnsw" and not paths.hnsw_index_path:
            current_index_type = "faiss"

    @app.get("/")
    def root():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        with index_lock:
            engine = current_index_type
        return jsonify({
            "status": "ok",
            "active_index_engine": engine,
            "active_dataset_id": dataset_manager.get_active_dataset()["id"],
            "auth": {
                "enabled": True,
                "current_user": current_user(),
            },
        })

    @app.post("/api/auth/register")
    def register_user():
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        user = auth_manager.create_user(
            payload.get("username", ""),
            payload.get("password", ""),
            email=payload.get("email", ""),
        )
        return jsonify({"success": True, "user": user}), 201

    @app.post("/api/auth/login")
    def login_user():
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        auth = auth_manager.authenticate(
            payload.get("username", ""),
            payload.get("password", ""),
            ttl_seconds=int(payload.get("ttl_seconds") or 86400),
        )
        return jsonify({"success": True, **auth})

    @app.post("/api/auth/logout")
    @require_user
    def logout_user():
        auth_manager.logout(extract_token())
        return jsonify({"success": True})

    @app.get("/api/auth/me")
    def auth_me():
        return jsonify({"user": current_user()})

    @app.get("/api/admin/users")
    @require_admin
    def admin_list_users():
        return jsonify({"users": auth_manager.list_users()})

    @app.patch("/api/admin/users/<int:user_id>")
    @require_admin
    def admin_update_user(user_id: int):
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        user = auth_manager.update_user(user_id, payload)
        return jsonify({"success": True, "user": user})

    @app.delete("/api/admin/users/<int:user_id>")
    @require_admin
    def admin_delete_user(user_id: int):
        current = request.current_user  # type: ignore[attr-defined]
        if current["id"] == user_id:
            raise AuthError("admin cannot delete the current session user", 400)
        auth_manager.delete_user(user_id)
        return jsonify({"success": True, "deleted": user_id})

    @app.get("/api/admin/dataset-policies")
    @require_admin
    def admin_dataset_policies():
        datasets = dataset_manager.list_datasets().get("datasets", [])
        return jsonify({"policies": auth_manager.list_dataset_policies(datasets)})

    @app.put("/api/admin/dataset-policies/<dataset_id>")
    @require_admin
    def admin_update_dataset_policy(dataset_id: str):
        dataset_manager.get_dataset(dataset_id)
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        policy = auth_manager.set_dataset_policy(
            dataset_id,
            visibility=payload.get("visibility", "public"),
            owner_user_id=payload.get("owner_user_id"),
        )
        return jsonify({"success": True, "policy": policy})

    @app.get("/api/index/status")
    def index_status():
        active_dataset_for_request()
        with index_lock:
            engine = current_index_type
        service = faiss_service if engine == "faiss" else hnsw_service
        try:
            status = service.status()
        except Exception as e:
            return jsonify({
                "loaded": False,
                "current_index_type": engine,
                "available_index_types": ["faiss", "hnsw"],
                "active_dataset": dataset_manager.get_active_dataset(),
                "error": str(e),
            })
        dataset = dataset_manager.get_active_dataset()
        status["current_index_type"] = engine
        status["available_index_types"] = ["faiss", "hnsw"]
        status["active_dataset"] = dataset
        status["active_dataset_id"] = dataset["id"]
        return jsonify(status)

    @app.post("/api/index/switch")
    @require_user
    def switch_index():
        nonlocal current_index_type
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        new_type = payload.get("index_type", "").lower()
        if new_type not in ["faiss", "hnsw"]:
            return jsonify({
                "error": "invalid_index_type",
                "message": f"index_type must be faiss or hnsw, got {new_type}",
            }), 400

        try:
            with index_lock:
                active = dataset_manager.get_active_dataset()
                if new_type == "hnsw" and not active.get("hnsw_index_path"):
                    return jsonify({
                        "error": "missing_hnsw_index",
                        "message": "当前数据集没有 HNSW 索引，请使用 FAISS 检索。",
                    }), 400
                if new_type == "faiss":
                    faiss_service.load()
                else:
                    hnsw_service.load()
                current_index_type = new_type
            return jsonify({"success": True, "index_type": current_index_type})
        except Exception as e:
            return jsonify({"error": "load_failed", "message": str(e)}), 500

    @app.get("/api/datasets")
    def list_datasets():
        return jsonify(visible_datasets(current_user()))

    @app.post("/api/datasets/upload")
    @require_user
    def upload_dataset():
        nonlocal viz_cache
        user = request.current_user  # type: ignore[attr-defined]
        upload = request.files.get("file")
        if upload is None:
            return jsonify({"error": "missing_file", "message": "请上传 file 字段中的 .h5ad 文件"}), 400
        tags = [
            value.strip()
            for value in (request.form.get("tags", "") or "").split(",")
            if value.strip()
        ]
        try:
            dataset = dataset_manager.import_h5ad(
                upload,
                name=request.form.get("name") or None,
                source=request.form.get("source", ""),
                group=request.form.get("group", "regular"),
                description=request.form.get("description", ""),
                tags=tags,
            )
            with index_lock:
                configure_services_for_dataset(dataset)
                faiss_service.load()
            visibility = request.form.get("visibility") or auth_manager.default_visibility(dataset)
            auth_manager.set_dataset_policy(
                dataset["id"],
                visibility=visibility,
                owner_user_id=user["id"],
            )
            viz_cache = {}
            return jsonify({"success": True, "dataset": dataset_with_policy(dataset)})
        except DatasetError as e:
            return jsonify({"error": "dataset_error", "message": str(e)}), 400

    @app.delete("/api/datasets/<dataset_id>")
    @require_user
    def delete_dataset(dataset_id: str):
        nonlocal viz_cache
        try:
            dataset = dataset_manager.get_dataset(dataset_id)
            if not auth_manager.can_manage_dataset(request.current_user, dataset):  # type: ignore[attr-defined]
                raise AuthError("current user cannot delete this dataset", 403)
            result = dataset_manager.delete_dataset(dataset_id)
            dataset = dataset_manager.get_active_dataset()
            with index_lock:
                configure_services_for_dataset(dataset)
            viz_cache = {}
            return jsonify({"success": True, **result})
        except DatasetError as e:
            return jsonify({"error": "dataset_error", "message": str(e)}), 400

    @app.post("/api/datasets/switch")
    @require_user
    def switch_dataset():
        nonlocal viz_cache
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        dataset_id = payload.get("dataset_id", "")
        try:
            requested_dataset = dataset_manager.get_dataset(dataset_id)
            if not auth_manager.can_view_dataset(request.current_user, requested_dataset):  # type: ignore[attr-defined]
                raise AuthError("current user cannot access this dataset", 403)
            dataset = dataset_manager.set_active_dataset(dataset_id)
            with index_lock:
                configure_services_for_dataset(dataset)
                faiss_service.load()
            viz_cache = {}
            return jsonify({"success": True, "dataset": dataset_with_policy(dataset), "index_type": current_index_type})
        except DatasetError as e:
            return jsonify({"error": "dataset_error", "message": str(e)}), 400

    @app.post("/api/datasets/joint-index")
    @require_user
    def build_joint_dataset_index():
        nonlocal viz_cache
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        try:
            dataset_ids = list(payload.get("dataset_ids") or [])
            for dataset_id in dataset_ids:
                dataset = dataset_manager.get_dataset(dataset_id)
                if not auth_manager.can_view_dataset(request.current_user, dataset):  # type: ignore[attr-defined]
                    raise AuthError(f"current user cannot access dataset {dataset_id}", 403)
            dataset = dataset_manager.build_joint_index(
                dataset_ids,
                name=payload.get("name") or "Joint dataset",
                group=payload.get("group") or "joint",
                description=payload.get("description") or "",
            )
            with index_lock:
                configure_services_for_dataset(dataset)
                faiss_service.load()
            auth_manager.set_dataset_policy(
                dataset["id"],
                visibility=payload.get("visibility") or "public",
                owner_user_id=request.current_user["id"],  # type: ignore[attr-defined]
            )
            viz_cache = {}
            return jsonify({"success": True, "dataset": dataset_with_policy(dataset)})
        except DatasetError as e:
            return jsonify({"error": "dataset_error", "message": str(e)}), 400

    @app.get("/api/cells/<path:cell_id>")
    def get_cell(cell_id: str):
        active_dataset_for_request()
        with index_lock:
            service = get_search_service()
        return jsonify(service.get_cell(cell_id))

    @app.get("/api/cell-types")
    def list_cell_types():
        meta_path = active_dataset_for_request()["metadata_path"]
        if not os.path.exists(meta_path):
            return jsonify({"cell_types": []})
        import csv
        types = set()
        with open(meta_path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                ct = row.get("cell_type", "").strip()
                if ct:
                    types.add(ct)
        return jsonify({"cell_types": sorted(types)})

    @app.get("/api/disease-types")
    def list_disease_types():
        """返回当前数据集中所有疾病/状态标签。"""
        meta_path = active_dataset_for_request()["metadata_path"]
        if not os.path.exists(meta_path):
            return jsonify({"disease_types": []})
        import csv
        types = set()
        with open(meta_path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                disease = row.get("disease", "").strip()
                if disease:
                    types.add(disease)
        return jsonify({"disease_types": sorted(types)})

    def _parse_viz_csv(csv_path: Path) -> tuple:
        """Parse a visualization CSV (pca_coords.csv or umap_coords.csv) and return points + type counts."""
        import csv
        points = []
        type_counts: Dict[str, int] = {}
        disease_counts: Dict[str, int] = {}
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                x_str = row.get("pc1", row.get("umap1", "")) or ""
                y_str = row.get("pc2", row.get("umap2", "")) or ""
                try:
                    x_val = float(x_str) if x_str.strip() else 0.0
                    y_val = float(y_str) if y_str.strip() else 0.0
                except ValueError:
                    continue  # skip malformed rows
                points.append({
                    "x": x_val,
                    "y": y_val,
                    "cell_id": row.get("cell_id", ""),
                    "cell_type": row.get("cell_type", "unknown") or "unknown",
                    "disease": row.get("disease", "") or "",
                    "dataset_id": row.get("dataset_id", ""),
                    "dataset_name": row.get("dataset_name", ""),
                    "dataset_group": row.get("dataset_group", ""),
                    "dataset_source": row.get("dataset_source", ""),
                })
                ct = row.get("cell_type", "unknown").strip() or "unknown"
                type_counts[ct] = type_counts.get(ct, 0) + 1
                disease = row.get("disease", "").strip()
                if disease:
                    disease_counts[disease] = disease_counts.get(disease, 0) + 1
        return points, type_counts, disease_counts

    @app.get("/api/visualization-data")
    def visualization_data():
        nonlocal viz_cache
        dataset = active_dataset_for_request()
        cache_key = dataset["id"]
        if viz_cache.get("dataset_id") == cache_key:
            return jsonify(viz_cache["data"])

        # Use manifest paths for PCA/UMAP CSVs; fall back to vectors_path parent
        pca_path_str = dataset.get("pca_coords_path") or ""
        umap_path_str = dataset.get("umap_coords_path") or ""
        pca_file = Path(pca_path_str) if pca_path_str else Path(dataset["vectors_path"]).parent / "pca_coords.csv"
        umap_file = Path(umap_path_str) if umap_path_str else Path(dataset["vectors_path"]).parent / "umap_coords.csv"

        pca_points, pca_type_counts, pca_disease_counts = [], {}, {}
        umap_points, umap_type_counts, umap_disease_counts = [], {}, {}

        if pca_file.exists():
            pca_points, pca_type_counts, pca_disease_counts = _parse_viz_csv(pca_file)

        if umap_file.exists():
            umap_points, umap_type_counts, umap_disease_counts = _parse_viz_csv(umap_file)

        # Fill in empty dataset fields with active dataset info
        ds_name = dataset.get("name", "")
        ds_id = dataset.get("id", "")
        ds_group = dataset.get("group", "")
        for pt in pca_points + umap_points:
            if not pt.get("dataset_name"):
                pt["dataset_name"] = ds_name
            if not pt.get("dataset_id"):
                pt["dataset_id"] = ds_id
            if not pt.get("dataset_group"):
                pt["dataset_group"] = ds_group

        # If CSV files exist, return structured data
        if pca_file.exists() or umap_file.exists():
            # Filter out UMAP points where both coords are 0 (NaN placeholder rows)
            if umap_points:
                umap_points = [p for p in umap_points if p["x"] != 0.0 or p["y"] != 0.0]

            data = {
                "pca_points": pca_points,
                "umap_points": umap_points,
                "cell_type_counts": [
                    {"cell_type": k, "count": v}
                    for k, v in sorted(pca_type_counts.items(), key=lambda x: -x[1])
                ],
                "disease_counts": [
                    {"disease": k, "count": v}
                    for k, v in sorted(pca_disease_counts.items(), key=lambda x: -x[1])
                ],
            }
            viz_cache = {"dataset_id": cache_key, "data": data}
            return jsonify(data)

        # Fallback: generate PCA from raw vectors (original behavior)
        meta_path = dataset["metadata_path"]
        vec_path = dataset["vectors_path"]

        try:
            vectors = np.load(vec_path)
        except Exception:
            return jsonify({"pca_points": [], "umap_points": [], "cell_type_counts": []})

        type_counts_fb: Dict[str, int] = {}
        cell_types_fb: list[str] = []
        diseases_fb: list[str] = []
        cell_ids_fb: list[str] = []
        if os.path.exists(meta_path):
            import csv
            with open(meta_path, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    ct = row.get("cell_type", "unknown").strip() or "unknown"
                    cell_types_fb.append(ct)
                    type_counts_fb[ct] = type_counts_fb.get(ct, 0) + 1
                    diseases_fb.append(row.get("disease", ""))
                    cell_ids_fb.append(row.get("cell_id", ""))

        n = vectors.shape[0]
        if n > 5000:
            rng = np.random.default_rng(42)
            sample_idx = rng.choice(n, 5000, replace=False)
            vectors = vectors[sample_idx]
            if cell_types_fb:
                cell_types_fb = [cell_types_fb[i] for i in sample_idx]
                diseases_fb = [diseases_fb[i] for i in sample_idx]
                cell_ids_fb = [cell_ids_fb[i] for i in sample_idx]

        pca_points_fb = []
        for i in range(vectors.shape[0]):
            ct = cell_types_fb[i] if cell_types_fb else "unknown"
            pca_points_fb.append({
                "x": float(vectors[i, 0]),
                "y": float(vectors[i, 1]),
                "cell_id": cell_ids_fb[i] if cell_ids_fb else "",
                "cell_type": ct,
                "disease": diseases_fb[i] if diseases_fb else "",
                "dataset_id": "",
                "dataset_name": "",
                "dataset_group": "",
                "dataset_source": "",
            })

        data = {
            "pca_points": pca_points_fb,
            "umap_points": [],
            "cell_type_counts": [{"cell_type": k, "count": v} for k, v in type_counts_fb.items()],
            "disease_counts": [],
        }
        viz_cache = {"dataset_id": cache_key, "data": data}
        return jsonify(data)

    @app.post("/api/search")
    def search():
        active_dataset_for_request()
        payload: Dict[str, Any] = request.get_json(silent=True) or {}

        search_mode = (payload.get("search_mode") or "normal").lower()
        filters: Dict[str, str] = payload.get("filters") or {}

        # 也支持顶层 disease 字段（等效 filters.disease）
        if payload.get("disease") and "disease" not in filters:
            filters["disease"] = payload["disease"]
        # cell_type 简写
        if payload.get("cell_type") and "cell_type" not in filters:
            filters["cell_type"] = payload["cell_type"]

        with index_lock:
            service = get_search_service()
            engine = current_index_type

        # 条件检索 / 跨库检索模式
        if search_mode in ("conditional", "cross_dataset") and filters:
            result = service.search_conditional(
                cell_id=payload.get("cell_id"),
                vector=payload.get("vector"),
                k=payload.get("k", 10),
                filters=filters,
                include_self=bool(payload.get("include_self", False)),
            )
        else:
            result = service.search(
                cell_id=payload.get("cell_id"),
                vector=payload.get("vector"),
                k=payload.get("k", 10),
                nprobe=payload.get("nprobe"),
                include_self=bool(payload.get("include_self", False)),
                filters=filters,
            )

        if search_mode == "cross_dataset":
            source_counts: Dict[str, int] = {}
            for r in result.get("results", []):
                ds = r.get("dataset_name", "unknown") or "unknown"
                source_counts[ds] = source_counts.get(ds, 0) + 1
            result.setdefault("filter_stats", {})
            result["filter_stats"]["source_distribution"] = source_counts
            result["filter_stats"]["mode"] = "cross_dataset"

        result["index_type"] = engine
        result["search_mode"] = search_mode
        result["dataset"] = dataset_manager.get_active_dataset()

        # 写入跨库检索调试日志
        try:
            os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs"), exist_ok=True)
            _log_search(
                mode=search_mode,
                dataset_id=dataset_manager.get_active_dataset().get("id", "?"),
                engine=engine,
                elapsed=result.get("elapsed_ms", 0),
                k=payload.get("k", 10),
                result_count=result.get("result_count", 0),
                filters=filters,
                filter_stats=result.get("filter_stats", {}),
            )
        except Exception:
            # 日志写入失败不影响主流程
            pass

        return jsonify(result)

    @app.get("/api/evaluation-data")
    def evaluation_data():
        active_dataset_for_request()
        eval_file = Path("docs/performance_evaluation_summary.json")
        if eval_file.exists():
            import json
            with open(eval_file, encoding="utf-8") as f:
                return jsonify(json.load(f))
        return jsonify({"datasets": []})

    @app.get("/api/performance-evaluation")
    def get_performance_evaluation():
        dataset = active_dataset_for_request()
        force_recompute = request.args.get("force", "false").lower() == "true"
        
        # 1. Try to load from cache
        if not force_recompute:
            cached_data = dataset_manager.load_performance_metrics(dataset["id"])
            if cached_data:
                return jsonify({
                    "dataset_id": dataset["id"],
                    "dataset_name": dataset["name"],
                    "group": dataset["group"],
                    "cell_count": dataset["cell_count"],
                    "dimension": dataset["dimension"],
                    "evaluation_results": cached_data["metrics"],
                    "evaluated_at": cached_data.get("evaluated_at"),
                    "source": "cache"
                })

        # 2. If not cached or forced, recompute and save
        try:
            vectors = np.load(dataset["vectors_path"])
            sample_size = len(vectors)
            query_size = 50 # Default query size

            if len(vectors) > sample_size:
                rng = np.random.default_rng(42)
                indices = rng.choice(len(vectors), size=sample_size, replace=False)
                index_vectors = vectors[indices]
            else:
                index_vectors = vectors

            if len(vectors) > sample_size + query_size:
                queries = vectors[sample_size:sample_size+query_size]
            else:
                rng = np.random.default_rng(42)
                query_indices = rng.choice(len(index_vectors), size=min(query_size, len(index_vectors)), replace=False)
                queries = index_vectors[query_indices]
            
            evaluator = PerformanceEvaluator(index_vectors, queries)
            evaluator.run_full_evaluation(k=10) # Using default K=10 as per user request
            
            # Clean up indices from results before saving
            cleaned_results = {}
            for method, result in evaluator.results.items():
                cleaned_result = dict(result)
                cleaned_result.pop('indices', None)
                cleaned_results[method] = cleaned_result

            # Save to cache
            dataset_manager.save_performance_metrics(dataset["id"], cleaned_results)

            return jsonify({
                "dataset_id": dataset["id"],
                "dataset_name": dataset["name"],
                "group": dataset["group"],
                "cell_count": dataset["cell_count"],
                "dimension": dataset["dimension"],
                "evaluation_results": cleaned_results,
                "evaluated_at": datetime.utcnow().isoformat() + "Z",
                "source": "recomputed"
            })
        except FileNotFoundError:
            return jsonify({"error": "dat-not_found", "message": "当前数据集的向量或元数据文件未找到，无法进行性能评估。"}), 404
        except Exception as e:
            return jsonify({"error": "performance_evaluation_failed", "message": str(e)}), 500

    @staticmethod
    def _call_llm(provider: str, api_key: str, question: str,
                  results: list, filters: dict) -> str:
        """Call external LLM API to generate a narrative answer."""
        if not results:
            return "未检索到相关细胞数据，无法生成 AI 分析。"
        result_lines = []
        for i, r in enumerate(results[:10]):
            ct = r.get("cell_type", "unknown")
            ds = r.get("disease", "normal")
            did = r.get("dataset_name", "") or r.get("dataset_id", "")
            result_lines.append(
                f"{i + 1}. cell_id={r.get('cell_id','')}, "
                f"type={ct}, disease={ds}, distance={r.get('distance',0):.4f}"
                f"{', dataset=' + did if did else ''}"
            )
        context = "\n".join(result_lines)
        filter_desc = "; ".join(f"{k}={v}" for k, v in filters.items()) if filters else "无"
        system_prompt = (
            "你是一个单细胞数据分析助手。以下是基于用户查询从单细胞数据库中检索到的相似细胞结果。"
            "请根据这些结果回答用户的问题，总结检索到的细胞类型、疾病分布和关键特征。"
        )
        user_prompt = (
            f"用户查询：{question}\n\n"
            f"过滤条件：{filter_desc}\n\n"
            f"检索结果（Top-{len(results)}）：\n{context}\n\n"
            "请根据以上检索结果给出分析。"
        )

        if provider in ("openai", "deepseek"):
            base_url = "https://api.openai.com/v1" if provider == "openai" else "https://api.deepseek.com/v1"
            model = "gpt-4o-mini" if provider == "openai" else "deepseek-chat"
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ], "temperature": 0.3, "max_tokens": 1024},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        elif provider == "claude":
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                         "Content-Type": "application/json"},
                json={"model": "claude-3-haiku-20240307", "max_tokens": 1024,
                       "system": system_prompt,
                       "messages": [{"role": "user", "content": user_prompt}]},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["content"][0]["text"]

        raise ValueError(f"Unsupported provider: {provider}")

    @app.post("/api/rag/query")
    def rag_query():
        """RAG endpoint: parse natural language → search → generate summary.

        Supports optional external LLM via `provider_api_key` and `provider`
        (openai / claude). Without a key, uses template-based summarization.
        """
        active_dataset_for_request()
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        question = payload.get("question") or payload.get("query") or ""
        filters = payload.get("filters") or parse_natural_language_query(question)
        k = int(payload.get("k") or 10)
        provider = payload.get("provider", "").lower()
        api_key = payload.get("provider_api_key", "")

        response: Dict[str, Any] = {
            "success": True,
            "mode": "rag-enhanced",
            "question": question,
            "parsed_filters": filters,
            "recommended_search_request": {
                "search_mode": "conditional" if filters else "normal",
                "k": k,
                "filters": filters,
            },
            "dataset": dataset_with_policy(dataset_manager.get_active_dataset()),
        }

        # 1. Execute search with parsed filters
        with index_lock:
            service = get_search_service()
        # If no cell_id or vector is provided, pick a random cell that matches
        # the parsed filters as the query seed (so filtered RAG queries work).
        rag_cell_id = payload.get("cell_id")
        rag_vector = payload.get("vector")
        if not rag_cell_id and not rag_vector:
            import numpy as np
            service._ensure_loaded()
            if filters:
                matching_indices = [
                    i for i, row in enumerate(service.metadata)
                    if all(str(row.get(k, "")).lower() == str(v).lower() for k, v in filters.items())
                ]
                if matching_indices:
                    seed_idx = random.choice(matching_indices)
                else:
                    seed_idx = random.randint(0, len(service.metadata) - 1)
            else:
                seed_idx = random.randint(0, len(service.metadata) - 1)
            rag_cell_id = service.metadata[seed_idx].get("cell_id", "")
        search_result = service.search(
            cell_id=rag_cell_id,
            vector=rag_vector,
            k=k,
            filters=filters,
            include_self=bool(payload.get("include_self", False)),
        )
        response["search_result"] = {
            "elapsed_ms": search_result.get("elapsed_ms", 0),
            "result_count": search_result.get("result_count", 0),
            "results": search_result.get("results", []),
        }

        # 2. Build context summary from retrieved cells
        results = search_result.get("results", [])
        if results:
            cell_types = {}
            diseases = {}
            for r in results:
                ct = r.get("cell_type", "unknown")
                cell_types[ct] = cell_types.get(ct, 0) + 1
                ds = r.get("disease", "unknown")
                if ds:
                    diseases[ds] = diseases.get(ds, 0) + 1
            top_type = max(cell_types, key=cell_types.get) if cell_types else "unknown"
            type_detail = ", ".join(f"{k}({v})" for k, v in sorted(cell_types.items(), key=lambda x: -x[1])[:5])
            disease_detail = ", ".join(f"{k}({v})" for k, v in sorted(diseases.items(), key=lambda x: -x[1])[:3])
            top_result = results[0]
            response["summary"] = {
                "top_cell_type": top_type,
                "cell_type_distribution": type_detail,
                "disease_distribution": disease_detail,
                "top_result_id": top_result.get("cell_id", ""),
                "top_result_distance": top_result.get("distance", 0),
            }
            response["answer"] = (
                f"找到 {len(results)} 个与查询「{question}」相关的细胞。"
                f"主要细胞类型为 {top_type}"
                f"（{type_detail}）。"
                + (f"疾病分布：{disease_detail}。" if disease_detail else "")
                + f"最相似细胞的距离为 {top_result.get('distance', 0):.4f}。"
            )
        else:
            response["answer"] = "未找到匹配的细胞结果，建议放宽筛选条件。"

        # 3. External LLM integration (optional)
        llm_answer = None
        if api_key and provider in ("openai", "deepseek", "claude"):
            response["llm_provider"] = provider
            response["llm_status"] = "api_key_provided"
            try:
                llm_answer = _call_llm(provider, api_key, question, results, filters)
                response["llm_answer"] = llm_answer
                response["llm_status"] = "success"
            except Exception as exc:
                response["llm_status"] = f"error: {exc}"
                response["llm_note"] = f"调用 {provider} API 失败: {exc}"
        else:
            response["llm_provider"] = None
            response["llm_note"] = (
                "模板摘要已生成。如需 AI 生成式回答，传入 provider_api_key "
                "（支持 openai / deepseek / claude）。"
            )

        return jsonify(response)

    @app.errorhandler(AuthError)
    def handle_auth_error(error: AuthError):
        return jsonify({"error": "auth_error", "message": str(error)}), error.status_code

    @app.errorhandler(SearchInputError)
    def handle_search_input_error(error: SearchInputError):
        return jsonify({"error": "bad_request", "message": str(error)}), 400

    @app.errorhandler(FileNotFoundError)
    def handle_missing_file(error: FileNotFoundError):
        return jsonify({"error": "missing_file", "message": str(error)}), 404

    @app.errorhandler(DatasetError)
    def handle_dataset_error(error: DatasetError):
        return jsonify({"error": "dataset_error", "message": str(error)}), 400

    @app.errorhandler(RuntimeError)
    def handle_runtime_error(error: RuntimeError):
        return jsonify({"error": "runtime_error", "message": str(error)}), 500

    @app.errorhandler(Exception)
    def handle_unhandled_error(error: Exception):
        import traceback
        traceback.print_exc()
        return jsonify({"error": "internal_error", "message": str(error)}), 500

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
