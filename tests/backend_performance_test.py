"""
后端性能测试
测试 API 的性能指标
"""

import os
import sys
import time
import json
import statistics
from pathlib import Path

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests


class BackendPerformanceTest:
    """后端性能测试"""

    def __init__(self, base_url="http://127.0.0.1:5000"):
        self.base_url = base_url
        self.results = {}

    def test_search_performance(self, num_requests=100):
        """测试搜索性能"""
        print(f"\n{'='*60}")
        print(f"搜索性能测试 - {num_requests} 次请求")
        print(f"{'='*60}")

        # 获取测试数据
        test_cell_id = "AAACCTGAGCAGGTCA-1_2"
        url = f"{self.base_url}/api/search"
        payload = {"cell_id": test_cell_id, "k": 10}

        latencies = []
        success_count = 0

        for i in range(num_requests):
            try:
                start = time.perf_counter()
                response = requests.post(url, json=payload, timeout=30)
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)
                if response.status_code == 200:
                    success_count += 1
            except Exception as e:
                print(f"请求 {i+1} 失败: {e}")
                latencies.append(999999)  # 用大值标记失败

            if (i + 1) % 20 == 0:
                print(f"已完成 {i+1}/{num_requests} 次请求")

        self._analyze_results("search", latencies, success_count, num_requests)

    def test_health_check(self, num_requests=100):
        """测试健康检查性能"""
        print(f"\n{'='*60}")
        print(f"健康检查性能测试 - {num_requests} 次请求")
        print(f"{'='*60}")

        url = f"{self.base_url}/api/health"
        latencies = []
        success_count = 0

        for i in range(num_requests):
            try:
                start = time.perf_counter()
                response = requests.get(url, timeout=30)
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)
                if response.status_code == 200:
                    success_count += 1
            except Exception as e:
                print(f"请求 {i+1} 失败: {e}")
                latencies.append(999999)

            if (i + 1) % 20 == 0:
                print(f"已完成 {i+1}/{num_requests} 次请求")

        self._analyze_results("health_check", latencies, success_count, num_requests)

    def test_index_status(self, num_requests=100):
        """测试索引状态性能"""
        print(f"\n{'='*60}")
        print(f"索引状态性能测试 - {num_requests} 次请求")
        print(f"{'='*60}")

        url = f"{self.base_url}/api/index/status"
        latencies = []
        success_count = 0

        for i in range(num_requests):
            try:
                start = time.perf_counter()
                response = requests.get(url, timeout=30)
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)
                if response.status_code == 200:
                    success_count += 1
            except Exception as e:
                print(f"请求 {i+1} 失败: {e}")
                latencies.append(999999)

            if (i + 1) % 20 == 0:
                print(f"已完成 {i+1}/{num_requests} 次请求")

        self._analyze_results("index_status", latencies, success_count, num_requests)

    def _analyze_results(self, test_name, latencies, success_count, total_count):
        """分析测试结果"""
        # 计算统计数据
        valid_latencies = [l for l in latencies if l < 999999]
        
        if valid_latencies:
            avg_latency = statistics.mean(valid_latencies)
            min_latency = min(valid_latencies)
            max_latency = max(valid_latencies)
            p50 = self._percentile(valid_latencies, 50)
            p95 = self._percentile(valid_latencies, 95)
            p99 = self._percentile(valid_latencies, 99)
        else:
            avg_latency = min_latency = max_latency = p50 = p95 = p99 = 0

        success_rate = success_count / total_count

        result = {
            "test_name": test_name,
            "total_requests": total_count,
            "success_count": success_count,
            "success_rate": success_rate,
            "latency_ms": {
                "min": round(min_latency, 3),
                "avg": round(avg_latency, 3),
                "p50": round(p50, 3),
                "p95": round(p95, 3),
                "p99": round(p99, 3),
                "max": round(max_latency, 3)
            }
        }

        self.results[test_name] = result

        # 打印结果
        print(f"\n✅ {test_name} 测试结果:")
        print(f"  成功: {success_count}/{total_count} ({success_rate:.1%})")
        print(f"  延迟 (ms):")
        print(f"    最小: {min_latency:.3f}")
        print(f"    平均: {avg_latency:.3f}")
        print(f"    P50:  {p50:.3f}")
        print(f"    P95:  {p95:.3f}")
        print(f"    P99:  {p99:.3f}")
        print(f"    最大: {max_latency:.3f}")

    def _percentile(self, data, pct):
        """计算百分位"""
        if not data:
            return 0
        ordered = sorted(data)
        idx = min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1))))
        return ordered[idx]

    def generate_report(self, output_file="docs/backend_performance_report.json"):
        """生成测试报告"""
        print(f"\n{'='*60}")
        print("生成性能测试报告")
        print(f"{'='*60}")

        report = {
            "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "base_url": self.base_url,
            "results": self.results
        }

        output_path = Path(__file__).resolve().parent.parent / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"报告已保存到: {output_path}")

        # 打印摘要
        print("\n性能测试摘要:")
        for name, result in self.results.items():
            print(f"  {name}:")
            print(f"    成功率: {result['success_rate']:.1%}")
            print(f"    平均延迟: {result['latency_ms']['avg']:.3f}ms")
            print(f"    P95 延迟: {result['latency_ms']['p95']:.3f}ms")

        return report


def run_backend_performance_tests():
    """运行后端性能测试"""
    print("=" * 70)
    print("后端性能测试")
    print("=" * 70)
    print("\n⚠️  注意: 请先运行 'python app.py' 启动后端服务")
    print("=" * 70)

    tester = BackendPerformanceTest()

    try:
        # 检查服务是否可用
        print("\n正在检查服务连接...")
        response = requests.get(f"{tester.base_url}/api/health", timeout=5)
        if response.status_code != 200:
            print(f"❌ 服务连接失败，状态码: {response.status_code}")
            return False
        print("✅ 服务连接成功")
    except Exception as e:
        print(f"❌ 无法连接到服务: {e}")
        print("请先运行: python app.py")
        return False

    # 运行测试
    tester.test_health_check(num_requests=100)
    tester.test_index_status(num_requests=100)
    tester.test_search_performance(num_requests=100)

    # 生成报告
    tester.generate_report()

    print("\n" + "=" * 70)
    print("✅ 性能测试完成")
    print("=" * 70)
    return True


if __name__ == "__main__":
    try:
        success = run_backend_performance_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        sys.exit(1)
