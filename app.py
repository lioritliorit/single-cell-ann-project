import os
import threading
from typing import Any, Dict

import numpy as np
from flask import Flask, jsonify, render_template, request

from ann_search_service import SearchInputError, SingleCellANNService
from hnsw_search_service import HNSWSearchService


def create_app() -> Flask:
    app = Flask(__name__)

    # Initialize both services for index switching
    faiss_service = SingleCellANNService(
        index_path=os.getenv("ANN_INDEX_PATH", "faiss_index.bin"),
        vectors_path=os.getenv("ANN_VECTORS_PATH", "cleaned_pca_vectors.npy"),
        metadata_path=os.getenv("ANN_METADATA_PATH", "cleaned_cell_metadata.csv"),
    )

    hnsw_service = HNSWSearchService(
        index_path=os.getenv("HNSW_INDEX_PATH", "hnsw_index.npz"),
        vectors_path=os.getenv("ANN_VECTORS_PATH", "cleaned_pca_vectors.npy"),
        metadata_path=os.getenv("ANN_METADATA_PATH", "cleaned_cell_metadata.csv"),
    )

    # Cache for visualization data
    viz_cache: Dict[str, Any] = {}

    # Track current index type with threading lock
    current_index_type: str = "faiss"
    index_lock = threading.Lock()

    def get_search_service():
        """线程安全地获取当前搜索引擎实例"""
        return faiss_service if current_index_type == "faiss" else hnsw_service

    # ===== Frontend =====

    @app.get("/")
    def root():
        return render_template("index.html")

    # ===== Health & Status =====

    @app.get("/api/health")
    def health():
        with index_lock:
            engine = current_index_type
        return jsonify({"status": "ok", "active_index_engine": engine})

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
                "error": str(e),
            })
        status["current_index_type"] = engine
        status["available_index_types"] = ["faiss", "hnsw"]
        return jsonify(status)

    @app.post("/api/index/switch")
    def switch_index():
        nonlocal current_index_type
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        new_type = payload.get("index_type", "").lower()

        if new_type not in ["faiss", "hnsw"]:
            return jsonify({
                "error": "invalid_index_type",
                "message": f"索引类型必须是 faiss 或 hnsw，收到: {new_type}",
            }), 400

        try:
            # 在锁内完成加载和切换，保证原子性
            with index_lock:
                if new_type == "faiss":
                    faiss_service.load()
                else:
                    hnsw_service.load()
                current_index_type = new_type
            return jsonify({"success": True, "index_type": current_index_type})
        except Exception as e:
            return jsonify({"error": "load_failed", "message": str(e)}), 500

    # ===== Cell Info =====

    @app.get("/api/cells/<path:cell_id>")
    def get_cell(cell_id: str):
        with index_lock:
            service = get_search_service()
        return jsonify(service.get_cell(cell_id))

    # ===== Cell Types =====

    @app.get("/api/cell-types")
    def list_cell_types():
        meta_path = os.getenv("ANN_METADATA_PATH", "cleaned_cell_metadata.csv")
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

    # ===== Visualization Data =====

    @app.get("/api/visualization-data")
    def visualization_data():
        nonlocal viz_cache
        if viz_cache:
            return jsonify(viz_cache)

        meta_path = os.getenv("ANN_METADATA_PATH", "cleaned_cell_metadata.csv")
        vec_path = os.getenv("ANN_VECTORS_PATH", "cleaned_pca_vectors.npy")

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
                    ct = row.get("cell_type", "unknown").strip()
                    cell_types_list.append(ct if ct else "unknown")
                    type_counts[ct if ct else "unknown"] = type_counts.get(ct if ct else "unknown", 0) + 1

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

        viz_cache = {"pca_points": pca_points, "cell_type_counts": cell_type_counts}
        return jsonify(viz_cache)

    # ===== Search =====

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
        return jsonify(result)

    # ===== Error Handlers =====

    @app.errorhandler(SearchInputError)
    def handle_search_input_error(error: SearchInputError):
        return jsonify({"error": "bad_request", "message": str(error)}), 400

    @app.errorhandler(FileNotFoundError)
    def handle_missing_file(error: FileNotFoundError):
        return jsonify({"error": "missing_file", "message": str(error)}), 404

    @app.errorhandler(RuntimeError)
    def handle_runtime_error(error: RuntimeError):
        return jsonify({"error": "runtime_error", "message": str(error)}), 500

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
