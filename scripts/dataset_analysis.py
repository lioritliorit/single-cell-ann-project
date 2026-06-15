import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from dataset_manager import DatasetError, DatasetManager
from performance_evaluator import PerformanceEvaluator

DOCS_DIR = PROJECT_ROOT / "docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)


class DatasetAnalysis:
    def __init__(self, manager: DatasetManager) -> None:
        self.manager = manager

    def generate_visualization(self, dataset_ids: Optional[List[str]] = None, all_datasets: bool = False) -> Dict[str, Any]:
        if all_datasets or not dataset_ids:
            dataset_ids = [item["id"] for item in self.manager.list_datasets()["datasets"]]

        result = {}
        for dataset_id in dataset_ids:
            try:
                manifest = self.manager.get_dataset(dataset_id)
                generated = self.manager.generate_visualization_data(dataset_id)
                result[dataset_id] = {
                    "status": "ok",
                    "paths": generated,
                    "dataset_name": manifest.get("name"),
                    "group": manifest.get("group"),
                }
            except Exception as exc:
                result[dataset_id] = {"status": "error", "message": str(exc)}
        return result

    def _select_datasets(self, dataset_ids: Optional[List[str]], groups: Optional[List[str]]) -> List[Dict[str, Any]]:
        all_datasets = self.manager.list_datasets()["datasets"]
        if dataset_ids:
            selected = [self.manager.get_dataset(ds) for ds in dataset_ids]
        elif groups:
            selected = [ds for ds in all_datasets if ds.get("group") in groups]
        else:
            selected = []
            for group in ["regular", "liver_disease", "joint"]:
                found = [ds for ds in all_datasets if ds.get("group") == group]
                if found:
                    selected.append(found[0])
        return selected

    def evaluate_dataset(self, dataset_id: str, sample_size: int = None, query_size: int = 50, k_values: Optional[List[int]] = None) -> Dict[str, Any]:
        if k_values is None:
            k_values = [10]  # 只评测 k=10，避免重复构建
        dataset = self.manager.get_dataset(dataset_id)
        vectors = np.load(dataset["vectors_path"])
        
        # 如果不指定 sample_size，使用全部数据
        if sample_size is None:
            sample_size = len(vectors)
        
        if len(vectors) > sample_size:
            rng = np.random.default_rng(42)
            indices = rng.choice(len(vectors), size=sample_size, replace=False)
            index_vectors = vectors[indices]
        else:
            index_vectors = vectors
        
        # 改进查询采样：优先使用未参与索引的向量作为查询
        if len(vectors) > sample_size + query_size:
            # 如果有剩余数据，使用未参与索引的向量
            queries = vectors[sample_size:sample_size+query_size]
        else:
            # 否则使用随机采样，避免位置偏差
            rng = np.random.default_rng(42)
            query_indices = rng.choice(len(index_vectors), size=min(query_size, len(index_vectors)), replace=False)
            queries = index_vectors[query_indices]

        k_evaluations: Dict[int, Dict[str, Any]] = {}
        
        # 只评测默认 k 值（避免重复构建）
        default_k = k_values[1] if len(k_values) > 1 else k_values[0]
        evaluator = PerformanceEvaluator(index_vectors, queries)
        evaluator.evaluate_faiss_flat(k=default_k)
        evaluator.evaluate_faiss_ivfflat(nlist=min(100, max(1, len(vectors) // 10)), nprobe=10, k=default_k)
        evaluator.evaluate_faiss_ivfpq(nlist=min(100, max(1, len(vectors) // 10)), m=8, nbits=8, nprobe=10, k=default_k)
        evaluator.evaluate_faiss_hnsw(M=16, ef_search=50, k=default_k)
        evaluator.evaluate_hnsw(M=16, efConstruction=200, ef_search=100, k=default_k)
        evaluator.compute_recalls(k=default_k)
        
        # 保存结果
        k_evaluations[default_k] = {
            name: self._clean_metrics(result)
            for name, result in evaluator.results.items()
        }

        dataset_result = {
            "dataset_id": dataset_id,
            "dataset_name": dataset.get("name"),
            "group": dataset.get("group"),
            "cell_count": dataset.get("cell_count"),
            "dimension": dataset.get("dimension"),
            "k_evaluations": k_evaluations,
            "default_k": k_values[1] if len(k_values) > 1 else k_values[0],
            "metrics": k_evaluations[k_values[1] if len(k_values) > 1 else k_values[0]],
            "distribution": self._analyze_distribution(dataset),
        }
        return dataset_result

    def evaluate(self, dataset_ids: Optional[List[str]] = None, groups: Optional[List[str]] = None, all_datasets: bool = False, k_values: Optional[List[int]] = None) -> Dict[str, Any]:
        if all_datasets:
            selected = self.manager.list_datasets()["datasets"]
        else:
            selected = self._select_datasets(dataset_ids, groups)

        if not selected:
            raise DatasetError("No datasets selected for evaluation")

        results = []
        for dataset in selected:
            try:
                results.append(self.evaluate_dataset(dataset["id"], k_values=k_values))
            except Exception as exc:
                results.append({"dataset_id": dataset["id"], "error": str(exc)})

        summary_path = DOCS_DIR / "performance_evaluation_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump({"evaluations": results, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")}, f, ensure_ascii=False, indent=2)

        self._write_markdown_summary(results)
        return {"summary_path": str(summary_path), "count": len(results)}

    def _write_markdown_summary(self, evaluations: List[Dict[str, Any]]) -> None:
        lines: List[str] = ["# 性能评测报告", "", f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
        lines.extend(self._write_global_comparison(evaluations))
        lines.extend(self._write_joint_comparison(evaluations))
        lines.extend(self._write_distribution_analysis(evaluations))
        for evaluation in evaluations:
            if evaluation.get("error"):
                lines.extend([f"## 数据集 {evaluation.get('dataset_id')}", "", f"- 错误：{evaluation.get('error')}", ""])
                continue
            lines.extend([
                f"## 数据集 {evaluation['dataset_id']} ({evaluation['dataset_name']})",
                "",
                f"- 分组: {evaluation['group']}",
                f"- 细胞数: {evaluation['cell_count']}",
                f"- 向量维度: {evaluation['dimension']}",
                "",
            ])
            if evaluation.get("distribution"):
                dist = evaluation["distribution"]
                lines.extend([
                    "### 肝病 / 正常细胞分布分析",
                    "",
                    f"- 正常细胞: {dist.get('normal_count', 0)}",
                    f"- 病例细胞: {dist.get('disease_count', 0)}",
                    f"- 正常比例: {dist.get('normal_ratio', 0.0):.4f}",
                    f"- 主要疾病标签: {', '.join(dist.get('top_diseases', []))}",
                    "",
                ])
            lines.extend([
                "### 默认 K 值评测结果",
                "",
                "| 方法 | 构建时间(s) | 查询时间(s) | 内存(MB) | 召回率 | 精确率 |",
                "|------|------------|------------|----------|--------|--------|",
            ])
            for name, metrics in evaluation["metrics"].items():
                if not metrics:
                    continue
                lines.append(
                    f"| {metrics.get('method', name)} | {metrics.get('build_time', 0.0):.6f} | {metrics.get('search_time', 0.0):.6f} | {metrics.get('memory_mb', 0.0):.2f} | {metrics.get('recall', 0.0):.4f} | {metrics.get('precision', 0.0):.4f} |"
                )
            lines.append("")
            lines.extend([
                "### 不同 K 值召回率对比",
                "",
                "| K | 方法 | 召回率 | 精确率 |",
                "|---|------|--------|--------|",
            ])
            for k, methods in evaluation.get("k_evaluations", {}).items():
                for method_name, metrics in methods.items():
                    if not metrics:
                        continue
                    lines.append(
                        f"| {k} | {metrics.get('method', method_name)} | {metrics.get('recall', 0.0):.4f} | {metrics.get('precision', 0.0):.4f} |"
                    )
            lines.append("")
        report_path = DOCS_DIR / "performance_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _write_global_comparison(self, evaluations: List[Dict[str, Any]]) -> List[str]:
        lines: List[str] = ["## 跨数据集性能对比", "", "以下表格展示各数据集中默认 K 值下的主要索引方法性能。", "", "| 数据集 | 组别 | 细胞数 | 方法 | 构建时间(s) | 查询时间(s) | 召回率 | 精确率 |", "|---|---|---|---|---|---|---|---|"]
        for evaluation in evaluations:
            if evaluation.get("error"):
                continue
            for method_name, metrics in evaluation.get("metrics", {}).items():
                if not metrics:
                    continue
                lines.append(
                    f"| {evaluation['dataset_id']} | {evaluation['group']} | {evaluation['cell_count']} | {metrics.get('method', method_name)} | {metrics.get('build_time', 0.0):.6f} | {metrics.get('search_time', 0.0):.6f} | {metrics.get('recall', 0.0):.4f} | {metrics.get('precision', 0.0):.4f} |"
                )
        lines.append("")
        return lines

    def _write_joint_comparison(self, evaluations: List[Dict[str, Any]]) -> List[str]:
        joint_evals = [e for e in evaluations if e.get("group") == "joint" and not e.get("error")]
        single_evals = [e for e in evaluations if e.get("group") != "joint" and not e.get("error")]
        if not joint_evals or not single_evals:
            return []

        lines: List[str] = ["## 联合数据集对比分析", "", "下面的对比展示了联合数据集与单数据集在默认 K 值下的检索性能差异。", ""]
        joint = joint_evals[0]
        comparison_methods = ["FAISS_HNSW (M=16)", "HNSW_self (M=16)", "FAISS_IVFFlat (nlist=100)"]
        lines.extend(["| 方法 | 数据集 | 召回率 | 精确率 | 查询时间(s) |", "|---|---|---|---|---|"])

        def find_metrics(metrics: Dict[str, Any], method_name: str) -> Optional[Dict[str, Any]]:
            for item in metrics.values():
                if item.get("method") == method_name:
                    return item
            return None

        for method in comparison_methods:
            joint_metrics = find_metrics(joint["metrics"], method)
            if joint_metrics:
                lines.append(f"| {method} | {joint['dataset_id']} | {joint_metrics.get('recall', 0.0):.4f} | {joint_metrics.get('precision', 0.0):.4f} | {joint_metrics.get('search_time', 0.0):.4f} |")
            for single in single_evals:
                single_metrics = find_metrics(single["metrics"], method)
                if single_metrics:
                    lines.append(f"| {method} | {single['dataset_id']} | {single_metrics.get('recall', 0.0):.4f} | {single_metrics.get('precision', 0.0):.4f} | {single_metrics.get('search_time', 0.0):.4f} |")
        lines.append("")
        return lines

    def _write_distribution_analysis(self, evaluations: List[Dict[str, Any]]) -> List[str]:
        dataset_with_dist = [e for e in evaluations if e.get("distribution") and not e.get("error")]
        if not dataset_with_dist:
            return []

        lines: List[str] = ["## 元数据分布差异分析", "", "以下内容用于比较不同数据集中的正常/病例比例及主要疾病标签。", "", "| 数据集 | 正常细胞数 | 病例细胞数 | 正常比例 | 主要疾病标签 |", "|---|---|---|---|---|"]
        for evaluation in dataset_with_dist:
            dist = evaluation["distribution"]
            lines.append(
                f"| {evaluation['dataset_id']} | {dist.get('normal_count', 0)} | {dist.get('disease_count', 0)} | {dist.get('normal_ratio', 0.0):.4f} | {', '.join(dist.get('top_diseases', []))} |"
            )
        lines.append("")
        return lines

    @staticmethod
    def _clean_metrics(metrics: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not metrics:
            return {}
        cleaned = {k: v for k, v in metrics.items() if k != "indices"}
        return cleaned

    def _analyze_distribution(self, dataset: Dict[str, Any]) -> Dict[str, Any]:
        if not dataset.get("metadata_path"):
            return {}
        df = pd.read_csv(dataset["metadata_path"], encoding="utf-8-sig", low_memory=False)
        if "disease" not in df.columns:
            return {}
        diseases = df["disease"].astype(str).fillna("").str.lower()
        normal_mask = diseases.str.contains("normal|healthy|control|ctrl", na=False)
        normal_count = int(normal_mask.sum())
        disease_count = int(len(diseases) - normal_count)
        disease_freq = diseases[~normal_mask].value_counts().head(5).to_dict()
        top_diseases = [k for k in disease_freq.keys() if k]
        normal_ratio = normal_count / len(diseases) if len(diseases) > 0 else 0.0
        return {
            "normal_count": normal_count,
            "disease_count": disease_count,
            "normal_ratio": normal_ratio,
            "top_diseases": top_diseases,
        }

    def dynamic_check(self) -> Dict[str, Any]:
        results = []
        dataset_ids = [item["id"] for item in self.manager.list_datasets()["datasets"]]
        for dataset_id in dataset_ids:
            try:
                dataset = self.manager.set_active_dataset(dataset_id)
                paths = [dataset["vectors_path"], dataset["metadata_path"], dataset["faiss_index_path"]]
                for path in paths:
                    if not path or not Path(path).exists():
                        raise DatasetError(f"缺少文件: {path}")
                results.append({"dataset_id": dataset_id, "status": "ok"})
            except Exception as exc:
                results.append({"dataset_id": dataset_id, "status": "error", "message": str(exc)})
        return {"dynamic_check": results}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dataset visualization and evaluation utilities.")
    sub = parser.add_subparsers(dest="command", required=True)

    viz = sub.add_parser("generate-viz", help="Generate PCA/UMAP visualization files for datasets.")
    viz.add_argument("dataset_ids", nargs="*", help="Dataset IDs to generate visualization for.")
    viz.add_argument("--all", action="store_true", help="Generate visualization for all datasets.")

    eval_cmd = sub.add_parser("evaluate", help="Evaluate dataset performance.")
    eval_cmd.add_argument("dataset_ids", nargs="*", help="Dataset IDs to evaluate.")
    eval_cmd.add_argument("--group", nargs="*", help="Dataset groups to evaluate.")
    eval_cmd.add_argument("--all", action="store_true", help="Evaluate all registered datasets.")
    eval_cmd.add_argument("--k-values", default="5,10,20", help="Comma-separated K values for recall comparison, e.g. 5,10,20.")

    sub.add_parser("dynamic-check", help="Validate dataset switch and file consistency for active dataset workflow.")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manager = DatasetManager()
    analysis = DatasetAnalysis(manager)

    if args.command == "generate-viz":
        result = analysis.generate_visualization(args.dataset_ids, all_datasets=args.all)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "evaluate":
        k_values = [int(value) for value in (args.k_values or "").split(",") if value.strip().isdigit()]
        if not k_values:
            k_values = [5, 10, 20]
        result = analysis.evaluate(args.dataset_ids, groups=args.group, all_datasets=args.all, k_values=k_values)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "dynamic-check":
        result = analysis.dynamic_check()
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
