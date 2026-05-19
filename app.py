import os
from typing import Any, Dict

from flask import Flask, jsonify, request

from ann_search_service import SearchInputError, SingleCellANNService


def create_app() -> Flask:
    app = Flask(__name__)
    service = SingleCellANNService(
        index_path=os.getenv("ANN_INDEX_PATH", "faiss_index.bin"),
        vectors_path=os.getenv("ANN_VECTORS_PATH", "cleaned_pca_vectors.npy"),
        metadata_path=os.getenv("ANN_METADATA_PATH", "cleaned_cell_metadata.csv"),
    )

    @app.get("/")
    def root():
        return jsonify(
            {
                "name": "single-cell-ann-api",
                "message": "Use /api/search to query Top-K similar cells.",
                "docs": {
                    "health": "GET /api/health",
                    "status": "GET /api/index/status",
                    "search": "POST /api/search",
                    "cell": "GET /api/cells/<cell_id>",
                },
            }
        )

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/index/status")
    def index_status():
        return jsonify(service.status())

    @app.get("/api/cells/<path:cell_id>")
    def get_cell(cell_id: str):
        return jsonify(service.get_cell(cell_id))

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
