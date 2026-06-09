import os
import threading
from typing import Any, Dict

import numpy as np
from flask import Flask, jsonify, render_template, request

from ann_search_service import SearchInputError, SingleCellANNService
from dataset_manager import DatasetError, DatasetManager
from hnsw_search_service import HNSWSearchService


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_H5AD_UPLOAD_MB", "2048")) * 1024 * 1024

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
        })

    @app.get("/api/index/status")
    def index_status():
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
        return jsonify(dataset_manager.list_datasets())

    @app.post("/api/datasets/upload")
    def upload_dataset():
        nonlocal viz_cache
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
            viz_cache = {}
            return jsonify({"success": True, "dataset": dataset})
        except DatasetError as e:
            return jsonify({"error": "dataset_error", "message": str(e)}), 400

    @app.delete("/api/datasets/<dataset_id>")
    def delete_dataset(dataset_id: str):
        nonlocal viz_cache
        try:
            result = dataset_manager.delete_dataset(dataset_id)
            dataset = dataset_manager.get_active_dataset()
            with index_lock:
                configure_services_for_dataset(dataset)
            viz_cache = {}
            return jsonify({"success": True, **result})
        except DatasetError as e:
            return jsonify({"error": "dataset_error", "message": str(e)}), 400

    @app.post("/api/datasets/switch")
    def switch_dataset():
        nonlocal viz_cache
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        dataset_id = payload.get("dataset_id", "")
        try:
            dataset = dataset_manager.set_active_dataset(dataset_id)
            with index_lock:
                configure_services_for_dataset(dataset)
                faiss_service.load()
            viz_cache = {}
            return jsonify({"success": True, "dataset": dataset, "index_type": current_index_type})
        except DatasetError as e:
            return jsonify({"error": "dataset_error", "message": str(e)}), 400

    @app.post("/api/datasets/joint-index")
    def build_joint_dataset_index():
        nonlocal viz_cache
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        try:
            dataset = dataset_manager.build_joint_index(
                list(payload.get("dataset_ids") or []),
                name=payload.get("name") or "Joint dataset",
                group=payload.get("group") or "joint",
                description=payload.get("description") or "",
            )
            with index_lock:
                configure_services_for_dataset(dataset)
                faiss_service.load()
            viz_cache = {}
            return jsonify({"success": True, "dataset": dataset})
        except DatasetError as e:
            return jsonify({"error": "dataset_error", "message": str(e)}), 400

    @app.get("/api/cells/<path:cell_id>")
    def get_cell(cell_id: str):
        with index_lock:
            service = get_search_service()
        return jsonify(service.get_cell(cell_id))

    @app.get("/api/cell-types")
    def list_cell_types():
        meta_path = dataset_manager.get_active_dataset()["metadata_path"]
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

    @app.get("/api/visualization-data")
    def visualization_data():
        nonlocal viz_cache
        dataset = dataset_manager.get_active_dataset()
        cache_key = dataset["id"]
        if viz_cache.get("dataset_id") == cache_key:
            return jsonify(viz_cache["data"])

        meta_path = dataset["metadata_path"]
        vec_path = dataset["vectors_path"]

        try:
            vectors = np.load(vec_path)
        except Exception:
            return jsonify({"pca_points": [], "cell_type_counts": []})

        type_counts: Dict[str, int] = {}
        cell_types_list: list[str] = []
        if os.path.exists(meta_path):
            import csv
            with open(meta_path, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    ct = row.get("cell_type", "unknown").strip() or "unknown"
                    cell_types_list.append(ct)
                    type_counts[ct] = type_counts.get(ct, 0) + 1

        n = vectors.shape[0]
        if n > 5000:
            rng = np.random.default_rng(42)
            sample_idx = rng.choice(n, 5000, replace=False)
            vectors = vectors[sample_idx]
            if cell_types_list:
                cell_types_list = [cell_types_list[i] for i in sample_idx]

        pca_points = []
        for i in range(vectors.shape[0]):
            ct = cell_types_list[i] if cell_types_list else "unknown"
            pca_points.append({
                "pc1": float(vectors[i, 0]),
                "pc2": float(vectors[i, 1]),
                "cell_type": ct,
            })

        cell_type_counts = [{"cell_type": k, "count": v} for k, v in type_counts.items()]
        data = {"pca_points": pca_points, "cell_type_counts": cell_type_counts}
        viz_cache = {"dataset_id": cache_key, "data": data}
        return jsonify(data)

    @app.post("/api/search")
    def search():
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        with index_lock:
            service = get_search_service()
            engine = current_index_type

        result = service.search(
            cell_id=payload.get("cell_id"),
            vector=payload.get("vector"),
            k=payload.get("k", 10),
            nprobe=payload.get("nprobe"),
            include_self=bool(payload.get("include_self", False)),
            filters=payload.get("filters") or {},
        )
        result["index_type"] = engine
        result["dataset"] = dataset_manager.get_active_dataset()
        return jsonify(result)

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

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
