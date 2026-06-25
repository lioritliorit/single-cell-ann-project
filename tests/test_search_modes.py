"""
检索模式测试脚本 — 验证成员3实现的三种检索模式。

运行方式:
    python tests/test_search_modes.py

覆盖:
  1. 普通检索 (normal) — 无过滤 Top-K
  2. 条件检索 (conditional) — 预过滤后 Top-K，验证精度
  3. 跨数据集检索 — 来源追踪
  4. 预过滤 vs 后过滤召回率对比
  5. build_filter_mask / build_sub_index 正确性
  6. 边界条件：空过滤、无匹配、空数据集
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

import io
# Ensure stdout can handle UTF-8 characters for consistent output across different environments.
# This is particularly important on Windows where default encoding might be different (e.g., GBK).
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# 测试工具
# ---------------------------------------------------------------------------
TEST_RESULTS: List[Dict[str, Any]] = []


def make_temp_dir() -> str:
    import tempfile

    base = Path(os.getenv("TEST_TMPDIR", ".tmp/single_cell_ann_tests"))
    base.mkdir(parents=True, exist_ok=True)
    return tempfile.mkdtemp(dir=str(base))


def log_test(name: str, passed: bool, detail: str = "") -> None:
    # 用 ASCII 替代 emoji 避免编码问题
    status = "[PASS]" if passed else "[FAIL]"
    msg = f"  {status} | {name}"
    if detail:
        msg += f"  ({detail})"
    try:
        print(msg)
    except UnicodeEncodeError:
        # 如果还是有编码问题，直接打印不包含特殊字符的版本
        print(msg.encode('ascii', errors='ignore').decode())
    TEST_RESULTS.append({"name": name, "passed": passed, "detail": detail})


def summary() -> int:
    passed = sum(1 for r in TEST_RESULTS if r["passed"])
    total = len(TEST_RESULTS)
    print(f"\n{'='*50}")
    print(f"  总计: {passed}/{total} 通过")
    if passed == total:
        print("  🎉 全部通过！")
    else:
        for r in TEST_RESULTS:
            if not r["passed"]:
                print(f"  ❌ {r['name']}")
    print(f"{'='*50}")
    return 0 if passed == total else 1


# ---------------------------------------------------------------------------
# 测试 1: FilterSpec + build_filter_mask
# ---------------------------------------------------------------------------
def test_filter_mask() -> None:
    print("\n--- 测试1: FilterSpec 与过滤掩码 ---")

    try:
        from search_engine import FilterSpec, IndexCache
    except ImportError:
        log_test("导入 search_engine 模块", False, "search_engine.py 未找到")
        return
    log_test("导入 search_engine 模块", True)

    # 测试空 FilterSpec
    fs = FilterSpec()
    log_test("空 FilterSpec.is_empty", fs.is_empty)

    # 测试部分 FilterSpec
    fs2 = FilterSpec(cell_type="hepatocyte", disease="normal")
    log_test("FilterSpec.to_dict 正确", fs2.to_dict() == {"cell_type": "hepatocyte", "disease": "normal"})

    # 模拟 metadata 测试 build_filter_mask
    from ann_search_service import SingleCellANNService
    service = SingleCellANNService()

    # 手动注入 metadata (不从文件加载)
    service.metadata = [
        {"cell_id": "c1", "cell_type": "hepatocyte", "disease": "normal", "dataset_group": "regular"},
        {"cell_id": "c2", "cell_type": "hepatocyte", "disease": "cirrhosis", "dataset_group": "liver_disease"},
        {"cell_id": "c3", "cell_type": "kupffer_cell", "disease": "normal", "dataset_group": "regular"},
        {"cell_id": "c4", "cell_type": "hepatocyte", "disease": "fibrosis", "dataset_group": "liver_disease"},
        {"cell_id": "c5", "cell_type": "t_cell", "disease": "normal", "dataset_group": "regular"},
    ]
    service.vectors = np.random.randn(5, 30).astype(np.float32)
    service.dimension = 30
    service._loaded = True  # 类型提示
    service._faiss_available = True  # 类型提示

    # 按 cell_type 过滤
    mask1 = service.build_filter_mask({"cell_type": "hepatocyte"})
    log_test("过滤 cell_type=hepatocyte (3个)", mask1.sum() == 3)

    # 按 disease 过滤
    mask2 = service.build_filter_mask({"disease": "normal"})
    log_test("过滤 disease=normal (3个)", mask2.sum() == 3)

    # 组合过滤
    mask3 = service.build_filter_mask({"cell_type": "hepatocyte", "disease": "normal"})
    log_test("组合过滤 hepatocyte+normal (1个)", mask3.sum() == 1)

    # 无匹配
    mask4 = service.build_filter_mask({"cell_type": "neuron"})
    log_test("无匹配条件返回全False", mask4.sum() == 0)

    # 空 filters 返回全 True
    mask5 = service.build_filter_mask({})
    log_test("空过滤返回全True", mask5.sum() == 5)


def _release_service(service: Any) -> None:
    """Release mmap handles so temp files can be deleted on Windows."""
    if hasattr(service, "vectors") and service.vectors is not None:
        try:
            service.vectors._mmap.close()
        except Exception:
            pass
        service.vectors = None


# ---------------------------------------------------------------------------
# 测试 2: 条件检索 (预过滤) vs 后过滤
# ---------------------------------------------------------------------------
def test_search_conditional() -> None:
    print("\n--- 测试2: 条件检索验证 ---")

    try:
        from ann_search_service import SingleCellANNService
    except ImportError:
        log_test("导入 SingleCellANNService", False)
        return

    # 生成可控测试数据
    np.random.seed(123)
    n = 2000
    d = 30
    vectors = np.random.randn(n, d).astype(np.float32)

    cell_types = ["hepatocyte"] * 800 + ["kupffer_cell"] * 500 + ["t_cell"] * 400 + ["cholangiocyte"] * 300
    diseases = ["normal"] * 800 + ["cirrhosis"] * 500 + ["normal"] * 300 + ["fibrosis"] * 400

    metadata = []
    for i in range(n):
        metadata.append({
            "cell_id": f"test_cell_{i}",
            "cell_type": cell_types[i],
            "disease": diseases[i],
            "dataset_group": "liver_disease" if diseases[i] != "normal" else "regular",
            "dataset_id": "test",
            "dataset_name": "Test Dataset",
            "dataset_source": "unit_test",
            "nCount_RNA": str(1000 + i),
            "nFeature_RNA": str(500 + i % 200),
            "percent.mt": str(round(i % 15, 2)),
            "donor_age": "30",
            "sex": "male",
            "AgeGroup": "adult",
            "tissue": "liver",
            "author_cell_type": cell_types[i],
        })

    tmpdir = make_temp_dir()
    service = None
    try:
        vectors_path = os.path.join(tmpdir, "vectors.npy")
        metadata_path = os.path.join(tmpdir, "metadata.csv")
        index_path = os.path.join(tmpdir, "index.bin")

        np.save(vectors_path, vectors)

        import csv
        with open(metadata_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(metadata[0].keys()))
            w.writeheader()
            w.writerows(metadata)

        # 构建 FAISS 索引
        try:
            import faiss
            index = faiss.IndexFlatL2(d)
            index.add(vectors)
            faiss.write_index(index, index_path)
            has_faiss = True
        except ImportError:
            has_faiss = False

        # 初始化服务
        service = SingleCellANNService(
            index_path=index_path,
            vectors_path=vectors_path,
            metadata_path=metadata_path,
        )
        service.load()

        log_test("服务加载成功", service._is_loaded())

        # ---- 2a: 普通检索 (无过滤) ----
        result_normal = service.search(cell_id="test_cell_0", k=10)
        log_test("普通检索返回10个结果", result_normal["result_count"] == 10)

        # ---- 2b: 条件检索 (预过滤) hepatocyte ----
        result_cond = service.search_conditional(
            cell_id="test_cell_0",
            k=10,
            filters={"cell_type": "hepatocyte"},
        )
        log_test("条件检索返回10个结果", result_cond["result_count"] == 10)
        log_test("条件检索有 filter_stats", "filter_stats" in result_cond)

        fs = result_cond.get("filter_stats", {})
        log_test(f"预过滤细胞数 ~799 (实际 {fs.get('filtered_cells')})",
                 780 <= fs.get("filtered_cells", 0) <= 800)

        # 验证所有结果都是 hepatocyte
        all_hepatocyte = all(r["cell_type"] == "hepatocyte" for r in result_cond["results"])
        log_test("所有结果均为 hepatocyte", all_hepatocyte)

        # ---- 2c: 组合过滤 hepatocyte + cirrhosis ----
        result_comb = service.search_conditional(
            cell_id="test_cell_1",
            k=10,
            filters={"cell_type": "hepatocyte", "disease": "cirrhosis"},
        )
        all_ok = all(
            r["cell_type"] == "hepatocyte" and r["disease"] == "cirrhosis"
            for r in result_comb["results"]
        )
        log_test("组合过滤 hepatocyte + cirrhosis 正确", all_ok)

        # ---- 2d: 空过滤条件检索 == 普通检索 ----
        result_cond_empty = service.search_conditional(
            cell_id="test_cell_0",
            k=10,
            filters={},
        )
        log_test("空条件检索返回结果", result_cond_empty["result_count"] > 0)

        # ---- 2e: 无匹配条件 ----
        result_none = service.search_conditional(
            cell_id="test_cell_0",
            k=10,
            filters={"cell_type": "neuron"},
        )
        log_test("无匹配条件返回0结果", result_none["result_count"] == 0)

    finally:
        if service is not None:
            _release_service(service)
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 测试 3: 预过滤 vs 后过滤 精确率对比
# ---------------------------------------------------------------------------
def test_pre_vs_post_filter_recall() -> None:
    print("\n--- 测试3: 预过滤 vs 后过滤精确率 ---")

    try:
        from ann_search_service import SingleCellANNService
    except ImportError:
        log_test("导入服务", False)
        return

    np.random.seed(456)
    n = 3000
    d = 30
    vectors = np.random.randn(n, d).astype(np.float32)
    cell_types = ["type_A"] * 1200 + ["type_B"] * 1000 + ["type_C"] * 800

    metadata = []
    for i in range(n):
        metadata.append({
            "cell_id": f"cell_{i}",
            "cell_type": cell_types[i],
            "disease": "normal",
            "dataset_group": "regular",
            "dataset_id": "test",
            "dataset_name": "Test",
            "dataset_source": "unit",
            "nCount_RNA": "1000",
            "nFeature_RNA": "500",
            "percent.mt": "5.0",
            "donor_age": "30",
            "sex": "male",
            "AgeGroup": "adult",
            "tissue": "liver",
            "author_cell_type": cell_types[i],
        })

    import csv
    tmpdir = make_temp_dir()
    service = None
    try:
        vectors_path = os.path.join(tmpdir, "vectors.npy")
        metadata_path = os.path.join(tmpdir, "metadata.csv")
        index_path = os.path.join(tmpdir, "index.bin")

        np.save(vectors_path, vectors)
        with open(metadata_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(metadata[0].keys()))
            w.writeheader()
            w.writerows(metadata)

        try:
            import faiss
            index = faiss.IndexFlatL2(d)
            index.add(vectors)
            faiss.write_index(index, index_path)
        except ImportError:
            pass

        service = SingleCellANNService(index_path, vectors_path, metadata_path)
        service.load()

        # 预过滤：用 type_B 过滤
        result_pre = service.search_conditional(
            cell_id="cell_1500",
            k=10,
            filters={"cell_type": "type_B"},
            include_self=False,
        )

        # 后过滤 (fallback 到普通检索 + filter)
        result_post = service.search(
            cell_id="cell_1500",
            k=10,
            filters={"cell_type": "type_B"},
            include_self=False,
        )

        # 预过滤应该100%都是 type_B
        pre_ok = all(r["cell_type"] == "type_B" for r in result_pre["results"])
        log_test("预过滤: 100%结果为目标类型", pre_ok)

        # 后过滤也应该全部是 type_B (k=10, candidate_k=100 够用)
        post_ok = all(r["cell_type"] == "type_B" for r in result_post["results"])
        log_test("后过滤: 100%结果为目标类型", post_ok)

        # 两种模式结果应一致
        pre_ids = [r["cell_id"] for r in result_pre["results"]]
        post_ids = [r["cell_id"] for r in result_post["results"]]
        overlap = len(set(pre_ids) & set(post_ids))
        log_test(f"预过滤与后过滤结果重叠: {overlap}/10", overlap >= 8)

        if overlap == 10:
            print("    → 预过滤和后过滤结果完全一致 (小数据集精确搜索)")
        elif overlap >= 8:
            print("    → 高重叠度，预过滤更可靠 (不依赖 candidate_k 估计)")

    finally:
        if service is not None:
            _release_service(service)
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 测试 4: IndexCache
# ---------------------------------------------------------------------------
def test_index_cache() -> None:
    print("\n--- 测试4: IndexCache 缓存机制 ---")

    try:
        from search_engine import IndexCache
    except ImportError:
        log_test("导入 IndexCache", False)
        return

    cache = IndexCache(max_entries=3)

    # 模拟数据
    vectors = np.random.randn(100, 30).astype(np.float32)
    metadata = [{"cell_id": f"c{i}"} for i in range(100)]
    fake_index = None
    id_map = {f"c{i}": i for i in range(100)}

    # put 3 entries
    cache.put("ds1", "faiss", vectors, metadata, fake_index, id_map)
    cache.put("ds2", "faiss", vectors, metadata, fake_index, id_map)
    cache.put("ds3", "faiss", vectors, metadata, fake_index, id_map)
    log_test("缓存3个条目", cache.stats["entries"] == 3)

    # get 命中
    hit = cache.get("ds1", "faiss")
    log_test("缓存命中 ds1", hit is not None)

    # get 未命中
    miss = cache.get("ds999", "faiss")
    log_test("缓存未命中 ds999", miss is None)

    # LRU 淘汰
    cache.put("ds4", "faiss", vectors, metadata, fake_index, id_map)
    log_test("LRU淘汰后仍为3条目", cache.stats["entries"] == 3)
    # ds2 是最旧的 (ds1 刚被 get)
    log_test("最旧条目被淘汰", cache.get("ds2", "faiss") is None)
    log_test("ds1 仍存在", cache.get("ds1", "faiss") is not None)

    # invalidate
    cache.invalidate("ds1")
    log_test("invalidate ds1", cache.get("ds1", "faiss") is None)

    cache.invalidate()
    log_test("invalidate 全部清空", cache.stats["entries"] == 0)

    # 命中率统计
    log_test(f"缓存统计正确", cache.stats["hits"] >= 1 and cache.stats["misses"] >= 2)


# ---------------------------------------------------------------------------
# 测试 5: 边界条件
# ---------------------------------------------------------------------------
def test_edge_cases() -> None:
    print("\n--- 测试5: 边界条件 ---")

    from search_engine import FilterSpec, SearchMode

    # 5a: k 值验证
    from ann_search_service import SingleCellANNService, SearchInputError
    service = SingleCellANNService()
    try:
        service._validate_k(0)
        log_test("k=0 抛出异常", False)
    except SearchInputError:
        log_test("k=0 正确抛出 SearchInputError", True)

    try:
        service._validate_k(101)
        log_test("k=101 抛出异常", False)
    except SearchInputError:
        log_test("k=101 正确抛出 SearchInputError", True)

    # 5b: SearchMode 枚举
    log_test("SearchMode.NORMAL 存在", SearchMode.NORMAL is not None)
    log_test("SearchMode.CONDITIONAL 存在", SearchMode.CONDITIONAL is not None)
    log_test("SearchMode.CROSS_DATASET 存在", SearchMode.CROSS_DATASET is not None)

    # 5c: FilterSpec 大小写不敏感
    fs = FilterSpec(cell_type="  Hepatocyte  ")
    log_test("FilterSpec 去除前后空格", fs.cell_type == "Hepatocyte")

    # 5d: 空 metadata 不应该 crash
    service.metadata = []
    service.vectors = np.random.randn(0, 30).astype(np.float32)
    service.dimension = 30
    mask = service.build_filter_mask({"cell_type": "anything"})
    log_test("空metadata的mask长度为0", len(mask) == 0)


# ---------------------------------------------------------------------------
# 测试 6: ann_search_service 的方法存在性检查
# ---------------------------------------------------------------------------
def test_method_existence() -> None:
    print("\n--- 测试6: 新增方法存在性 ---")

    from ann_search_service import SingleCellANNService
    service = SingleCellANNService()

    checks = [
        ("build_filter_mask", hasattr(service, "build_filter_mask")),
        ("build_sub_index", hasattr(service, "build_sub_index")),
        ("search_conditional", hasattr(service, "search_conditional")),
        ("configure_paths", hasattr(service, "configure_paths")),
    ]
    for name, ok in checks:
        log_test(f"方法 {name} 存在", ok)

    from hnsw_search_service import HNSWSearchService
    hnsw = HNSWSearchService()
    hnsw_checks = [
        ("build_filter_mask", hasattr(hnsw, "build_filter_mask")),
        ("search_conditional", hasattr(hnsw, "search_conditional")),
    ]
    for name, ok in hnsw_checks:
        log_test(f"HNSW 方法 {name} 存在", ok)


# ---------------------------------------------------------------------------
# 测试 7: dataset_manager 多索引类型
# ---------------------------------------------------------------------------
def test_multi_index_types() -> None:
    print("\n--- 测试7: 多索引类型构建 ---")

    from dataset_manager import DatasetManager

    # 7a: _auto_nlist
    log_test("auto_nlist(1000)", DatasetManager._auto_nlist(1000) > 0)
    log_test("auto_nlist(0)", DatasetManager._auto_nlist(0) == 4)  # min
    log_test("auto_nlist(1000000)", DatasetManager._auto_nlist(1000000) <= 1024)  # max

    # 7b: _build_faiss_index 支持 index_type 参数
    import inspect
    sig = inspect.signature(DatasetManager._build_faiss_index)
    params = list(sig.parameters.keys())
    log_test("_build_faiss_index 接受 index_type 参数", "index_type" in params)
    log_test("_build_faiss_index 接受 kwargs 或显式参数", "kwargs" in params or "nlist" in params)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    print("=" * 50)
    print(" 成员3 检索核心引擎 — 测试套件")
    print("=" * 50)

    # 切换到项目根目录
    project_root = Path(__file__).resolve().parent.parent
    os.chdir(project_root)

    test_method_existence()
    test_filter_mask()
    test_search_conditional()
    test_pre_vs_post_filter_recall()
    test_index_cache()
    test_edge_cases()
    test_multi_index_types()

    return summary()


if __name__ == "__main__":
    sys.exit(main())
