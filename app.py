import os
from typing import Any, Dict

import numpy as np
from flask import Flask, jsonify, render_template, request

from ann_search_service import SearchInputError, SingleCellANNService


def create_app() -> Flask:
    app = Flask(__name__)
    service = SingleCellANNService(
        index_path=os.getenv("ANN_INDEX_PATH", "faiss_index.bin"),
        vectors_path=os.getenv("ANN_VECTORS_PATH", "cleaned_pca_vectors.npy"),
        metadata_path=os.getenv("ANN_METADATA_PATH", "cleaned_cell_metadata.csv"),
    )

    # Cache for visualization data
    viz_cache: Dict[str, Any] = {}

    # ===== Frontend =====

    @app.get("/")
    def root():
        return render_template("index.html")

    # ===== Health & Status =====

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/index/status")
    def index_status():
        return jsonify(service.status())

    # ===== Cell Info =====

    @app.get("/api/cells/<path:cell_id>")
    def get_cell(cell_id: str):
        return jsonify(service.get_cell(cell_id))

    # ===== Cell Types =====

    @app.get("/api/cell-types")
    def list_cell_types():
        """Return sorted list of unique cell types for filter dropdown."""
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
        """Return PCA 2D coordinates and cell type counts for charts."""
        nonlocal viz_cache
        if viz_cache:
            return jsonify(viz_cache)

        meta_path = os.getenv("ANN_METADATA_PATH", "cleaned_cell_metadata.csv")
        vec_path = os.getenv("ANN_VECTORS_PATH", "cleaned_pca_vectors.npy")

        try:
            vectors = np.load(vec_path)
        except Exception:
            return jsonify({"pca_points": [], "cell_type_counts": []})

        # Cell type counts
        type_counts: Dict[str, int] = {}
        cell_types_list: list[str] = []
        if os.path.exists(meta_path):
            import csv
            with open(meta_path, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    ct = row.get("cell_type", "unknown").strip()
                    cell_types_list.append(ct if ct else "unknown")
                    type_counts[ct if ct else "unknown"] = type_counts.get(ct if ct else "unknown", 0) + 1

        # Subsample if too many points (max 5000 for scatter performance)
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
        result = service.search(
            cell_id=payload.get("cell_id"),
            vector=payload.get("vector"),
            k=payload.get("k", 10),
            nprobe=payload.get("nprobe"),
            include_self=bool(payload.get("include_self", False)),
            filters=payload.get("filters") or {},
        )
        return jsonify(result)

    # ===== Error Handlers =====

    @app.errorhandler(SearchInputError)
    def handle_search_input_error(error: SearchInputError):
        return jsonify({"error": "bad_request", "message": str(error)}), 400

    @app.errorhandler(FileNotFoundError)
    def handle_missing_file(error: FileNotFoundError):
        return jsonify({"error": "missing_file", "message": str(error)}), 500

    @app.errorhandler(RuntimeError)
    def handle_runtime_error(error: RuntimeError):
        return jsonify({"error": "runtime_error", "message": str(error)}), 500

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
