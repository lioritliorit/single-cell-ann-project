"""
测试入口文件
运行所有测试并生成报告
"""

import os
import sys
import argparse
import subprocess
import time
import requests
import io

# Ensure stdout/stderr can handle UTF-8 characters for consistent output across different environments.
# This is particularly important on Windows where default encoding might be different (e.g., GBK).
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_reporter import get_reporter


def run_backend_functional_tests():
    """运行后端功能测试"""
    print("\n" + "="*70)
    print("1. 后端功能测试 (backend_functional_test.py)")
    print("="*70)
    
    try:
        from tests.backend_functional_test import run_backend_functional_tests as _run
        success = _run()
        return success
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def run_search_modes_test():
    """运行检索模式测试"""
    print("\n" + "="*70)
    print("2. 检索模式测试 (test_search_modes.py)")
    print("="*70)
    
    result = subprocess.run(
        [sys.executable, "tests/test_search_modes.py"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
        capture_output=True,
        text=True,
        encoding='utf-8'
    )
    
    # 打印捕获的输出
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    return result.returncode == 0


def run_member4_api_test():
    """运行成员4 API测试"""
    print("\n" + "="*70)
    print("3. 成员4 API测试 (test_member4_api.py)")
    print("="*70)
    
    result = subprocess.run(
        [sys.executable, "tests/test_member4_api.py"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True,
        text=True,
        encoding='utf-8'
    )
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    return result.returncode == 0


def run_test_search_api():
    """运行基础搜索API测试"""
    print("\n" + "="*70)
    print("4. 基础搜索API测试 (test_search_api.py)")
    print("="*70)
    
    result = subprocess.run(
        [sys.executable, "tests/test_search_api.py"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True,
        text=True,
        encoding='utf-8'
    )
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    return result.returncode == 0


def start_flask_server():
    """启动Flask测试服务器"""
    print("\n正在启动Flask后端服务...")
    env = os.environ.copy()
    env["FLASK_ENV"] = "testing"
    
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8'
    )
    
    # 等待服务器启动
    max_wait = 30
    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            response = requests.get("http://127.0.0.1:5000/api/health", timeout=2)
            if response.status_code == 200:
                print("✅ Flask服务启动成功")
                return proc
        except Exception:
            pass
        time.sleep(1)
    
    print("❌ Flask服务启动超时")
    proc.terminate()
    return None


def run_backend_performance_tests():
    """运行后端性能测试"""
    print("\n" + "="*70)
    print("5. 后端性能测试 (backend_performance_test.py)")
    print("="*70)
    
    try:
        from tests.backend_performance_test import run_backend_performance_tests as _run
        return _run()
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def run_frontend_tests():
    """运行前端测试"""
    print("\n" + "="*70)
    print("6. 前端测试 (frontend_test.py)")
    print("="*70)
    
    try:
        from tests.frontend_test import run_frontend_tests as _run
        return _run()
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def run_api_stress_test():
    """运行API并发压测"""
    print("\n" + "="*70)
    print("7. API并发压测 (api_stress_test.py)")
    print("="*70)
    
    result = subprocess.run(
        [sys.executable, "tests/api_stress_test.py", 
         "--url", "http://127.0.0.1:5000",
         "--requests", "50",
         "--workers", "4"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True,
        text=True,
        encoding='utf-8'
    )
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    return result.returncode == 0


def run_all_tests():
    """运行所有测试"""
    parser = argparse.ArgumentParser(description="运行系统测试")
    parser.add_argument(
        "--mode", 
        choices=["all", "functional", "with-server", "performance", "frontend", "member3", "member4", "stress"],
        default="all",
        help="测试模式: all(全部), functional(仅功能测试), with-server(含服务测试), performance(性能), frontend(前端), member3, member4, stress(压测)"
    )
    
    args = parser.parse_args()
    
    print("="*70)
    print("单细胞 ANN 系统测试")
    print("="*70)
    
    # 初始化报告器
    reporter = get_reporter()
    reporter.start_test()
    
    results = {}
    server_proc = None
    
    try:
        if args.mode == "all":
            # 第一阶段：不需要服务的测试
            print("\n" + "="*70)
            print("阶段1: 无服务功能测试")
            print("="*70)
            
            success = run_backend_functional_tests()
            results["backend_functional"] = success
            reporter.add_result("后端功能测试", success)
            
            success = run_search_modes_test()
            results["search_modes"] = success
            reporter.add_result("检索模式测试", success)
            
            success = run_member4_api_test()
            results["member4_api"] = success
            reporter.add_result("成员4 API测试", success)
            
            success = run_test_search_api()
            results["test_search_api"] = success
            reporter.add_result("基础搜索API测试", success)
            
            # 第二阶段：需要服务的测试
            print("\n" + "="*70)
            print("阶段2: 需要后端服务的测试")
            print("="*70)
            print("\n📋 提示：将启动后端服务进行性能和前端测试")
            server_proc = start_flask_server()
            
            if server_proc:
                success = run_backend_performance_tests()
                results["backend_performance"] = success
                reporter.add_result("后端性能测试", success)
                
                success = run_frontend_tests()
                results["frontend"] = success
                reporter.add_result("前端测试", success)
                
                success = run_api_stress_test()
                results["api_stress"] = success
                reporter.add_result("API并发压测", success)
            else:
                print("\n⚠️  跳过需要服务的测试")
                
        elif args.mode == "functional":
            success = run_backend_functional_tests()
            results["backend_functional"] = success
            reporter.add_result("后端功能测试", success)
            
            success = run_search_modes_test()
            results["search_modes"] = success
            reporter.add_result("检索模式测试", success)
            
            success = run_member4_api_test()
            results["member4_api"] = success
            reporter.add_result("成员4 API测试", success)
            
            success = run_test_search_api()
            results["test_search_api"] = success
            reporter.add_result("基础搜索API测试", success)
            
        elif args.mode == "with-server":
            success = run_backend_functional_tests()
            results["backend_functional"] = success
            reporter.add_result("后端功能测试", success)
            
            success = run_search_modes_test()
            results["search_modes"] = success
            reporter.add_result("检索模式测试", success)
            
            success = run_member4_api_test()
            results["member4_api"] = success
            reporter.add_result("成员4 API测试", success)
            
            success = run_test_search_api()
            results["test_search_api"] = success
            reporter.add_result("基础搜索API测试", success)
            
            server_proc = start_flask_server()
            if server_proc:
                success = run_backend_performance_tests()
                results["backend_performance"] = success
                reporter.add_result("后端性能测试", success)
                
                success = run_frontend_tests()
                results["frontend"] = success
                reporter.add_result("前端测试", success)
                
                success = run_api_stress_test()
                results["api_stress"] = success
                reporter.add_result("API并发压测", success)
                
        elif args.mode == "performance":
            server_proc = start_flask_server()
            if server_proc:
                success = run_backend_performance_tests()
                results["backend_performance"] = success
                reporter.add_result("后端性能测试", success)
                
        elif args.mode == "frontend":
            server_proc = start_flask_server()
            if server_proc:
                success = run_frontend_tests()
                results["frontend"] = success
                reporter.add_result("前端测试", success)
                
        elif args.mode == "member3":
            success = run_search_modes_test()
            results["search_modes"] = success
            reporter.add_result("检索模式测试", success)
            
        elif args.mode == "member4":
            success = run_member4_api_test()
            results["member4_api"] = success
            reporter.add_result("成员4 API测试", success)
            
        elif args.mode == "stress":
            server_proc = start_flask_server()
            if server_proc:
                success = run_api_stress_test()
                results["api_stress"] = success
                reporter.add_result("API并发压测", success)
                
    finally:
        if server_proc:
            print("\n正在关闭Flask服务...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except Exception:
                server_proc.kill()
    
    # 结束测试并生成报告
    reporter.end_test()
    
    # 打印总结
    print("\n" + "="*70)
    print("测试总结")
    print("="*70)
    
    for test_name, success in results.items():
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    all_passed = all(results.values()) if results else False
    
    print("\n" + "="*70)
    if all_passed:
        print("🎉 所有测试通过！")
    else:
        print("⚠️  部分测试失败，请检查输出")
    print("="*70)
    
    # 生成报告
    reporter.generate_markdown_report()
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    try:
        exit_code = run_all_tests()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        sys.exit(1)
