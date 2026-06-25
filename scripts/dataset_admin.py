import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dataset_manager import DatasetManager
from performance_evaluator import PerformanceEvaluator
import numpy as np
from scripts.dataset_analysis import DatasetAnalysis


class LocalUpload:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.filename = path.name

    def save(self, target: str) -> None:
        shutil.copy2(self.path, target)


def print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage single-cell h5ad datasets and FAISS indexes.")
    sub = parser.add_subparsers(dest="command", required=True)

def _run_and_cache_performance_evaluation(dataset_id: str, manager: DatasetManager, default_k: int = 10) -> None:
    print(f"-> 正在为数据集 {dataset_id} 运行性能评测并缓存结果...")
    try:
        dataset = manager.get_dataset(dataset_id)
        vectors = np.load(dataset["vectors_path"])
        
        # Using a fixed sample size for queries, consistent with app.py's API
        sample_size = len(vectors)
        query_size = 50
        
        if len(vectors) > sample_size: # This condition will only be true if sample_size is less than len(vectors)
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
        evaluator.run_full_evaluation(k=default_k)

        # Cache the results
        # Clean up indices from results before saving to file
        cleaned_results = {}
        for method, result in evaluator.results.items():
            cleaned_result = dict(result)
            cleaned_result.pop('indices', None)
            cleaned_results[method] = cleaned_result
        
        manager.save_performance_metrics(dataset_id, cleaned_results)
        print(f"-> 数据集 {dataset_id} 的性能评测结果已缓存。")
    except Exception as e:
        print(f"-> 警告: 无法为数据集 {dataset_id} 缓存性能评测结果: {e}")

    sub.add_parser("list", help="List registered datasets.")

    import_cmd = sub.add_parser("import", help="Import an h5ad file and build its FAISS index.")
    import_cmd.add_argument("h5ad_path")
    import_cmd.add_argument("--name", default=None)
    import_cmd.add_argument("--source", default="")
    import_cmd.add_argument("--group", default="regular")
    import_cmd.add_argument("--description", default="")
    import_cmd.add_argument("--tags", default="")

    switch_cmd = sub.add_parser("switch", help="Switch the active dataset.")
    switch_cmd.add_argument("dataset_id")

    delete_cmd = sub.add_parser("delete", help="Delete a dataset and its generated files.")
    delete_cmd.add_argument("dataset_id")

    joint_cmd = sub.add_parser("joint", help="Build a joint FAISS index from multiple datasets.")
    joint_cmd.add_argument("dataset_ids", nargs="+")
    joint_cmd.add_argument("--name", default="Joint dataset")
    joint_cmd.add_argument("--group", default="joint")
    joint_cmd.add_argument("--description", default="")

    args = parser.parse_args()
    manager = DatasetManager()

    if args.command == "list":
        print_json(manager.list_datasets())
    elif args.command == "import":
        tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
        dataset = manager.import_h5ad(
            LocalUpload(Path(args.h5ad_path)),
            name=args.name,
            source=args.source,
            group=args.group,
            description=args.description,
            tags=tags,
        )
        print_json(dataset)
        _run_and_cache_performance_evaluation(dataset["id"], manager)
    elif args.command == "switch":
        print_json(manager.set_active_dataset(args.dataset_id))
    elif args.command == "delete":
        print_json(manager.delete_dataset(args.dataset_id))
    elif args.command == "joint":
        dataset = manager.build_joint_index(
            args.dataset_ids,
            name=args.name,
            group=args.group,
            description=args.description,
        )
        print_json(dataset)
        _run_and_cache_performance_evaluation(dataset["id"], manager)


if __name__ == "__main__":
    main()
