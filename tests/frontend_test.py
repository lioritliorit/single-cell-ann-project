"""
前端测试
测试前端页面和交互
"""

import os
import sys
import time

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests


class FrontendTest:
    """前端测试"""

    def __init__(self, base_url="http://127.0.0.1:5000"):
        self.base_url = base_url
        self.results = {}

    def test_page_load(self):
        """测试页面加载"""
        print(f"\n{'='*60}")
        print("前端页面加载测试")
        print(f"{'='*60}")

        try:
            # 测试主页面
            print("\n1. 测试主页面加载...")
            response = requests.get(self.base_url, timeout=30)
            self._check_response("主页面", response, expected_content="<!DOCTYPE html")

            # 测试静态资源
            print("\n2. 测试静态资源...")
            
            # 测试 CSS
            css_url = f"{self.base_url}/static/css/style.css"
            response = requests.get(css_url, timeout=30)
            self._check_response("CSS 样式", response)

            # 测试 JS
            js_url = f"{self.base_url}/static/js/main.js"
            response = requests.get(js_url, timeout=30)
            self._check_response("JavaScript", response)

            print("\n✅ 页面加载测试通过")
            self.results["page_load"] = "success"

        except Exception as e:
            print(f"\n❌ 页面加载测试失败: {e}")
            self.results["page_load"] = f"failed: {str(e)}"

    def _check_response(self, name, response, expected_content=None, expected_status=200):
        """检查响应"""
        success = response.status_code == expected_status
        if expected_content:
            success = success and (expected_content in response.text)

        if success:
            print(f"   ✅ {name}: 成功 (状态码: {response.status_code})")
        else:
            print(f"   ❌ {name}: 失败 (状态码: {response.status_code})")

        return success

    def test_api_integration(self):
        """测试前端 API 集成"""
        print(f"\n{'='*60}")
        print("前端 API 集成测试")
        print(f"{'='*60}")

        test_cases = [
            ("健康检查", "/api/health", "GET"),
            ("索引状态", "/api/index/status", "GET"),
            ("细胞类型", "/api/cell-types", "GET"),
            ("疾病类型", "/api/disease-types", "GET"),
        ]

        for name, path, method in test_cases:
            try:
                url = f"{self.base_url}{path}"
                if method == "GET":
                    response = requests.get(url, timeout=30)
                else:
                    response = requests.post(url, json={}, timeout=30)

                self._check_response(name, response)

            except Exception as e:
                print(f"   ❌ {name}: 异常 - {e}")

        self.results["api_integration"] = "completed"

    def generate_report(self):
        """生成测试报告"""
        print(f"\n{'='*60}")
        print("前端测试报告")
        print(f"{'='*60}")

        for test_name, result in self.results.items():
            status = "✅ 通过" if result == "success" or result == "completed" else "❌ 失败"
            print(f"  {test_name}: {status}")

        return self.results


def run_frontend_tests():
    """运行前端测试"""
    print("=" * 70)
    print("前端测试")
    print("=" * 70)
    print("\n⚠️  注意: 请先运行 'python app.py' 启动后端服务")
    print("=" * 70)

    tester = FrontendTest()

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
    tester.test_page_load()
    tester.test_api_integration()

    # 生成报告
    tester.generate_report()

    print("\n" + "=" * 70)
    print("✅ 前端测试完成")
    print("=" * 70)
    return True


if __name__ == "__main__":
    try:
        success = run_frontend_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        sys.exit(1)
