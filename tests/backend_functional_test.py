"""
后端功能测试
测试所有 API 接口的功能正确性
"""

import os
import sys
import tempfile
import json

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app


def run_backend_functional_tests():
    """运行后端功能测试"""
    print("=" * 70)
    print("后端功能测试")
    print("=" * 70)
    
    temp_dir = tempfile.TemporaryDirectory()
    os.environ["AUTH_DB_PATH"] = os.path.join(temp_dir.name, "auth.db")
    os.environ["ADMIN_USERNAME"] = "admin"
    os.environ["ADMIN_PASSWORD"] = "admin123"
    
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    
    passed = 0
    total = 0
    
    try:
        # 测试1: 健康检查
        total +=1
        print("\n=== 测试 1: 健康检查接口 ===")
        try:
            response = client.get("/api/health")
            if response.status_code == 200:
                data = json.loads(response.data)
                print(f"✅ 健康检查通过: {data}")
                passed +=1
            else:
                print(f"❌ 健康检查失败: {response.status_code}")
        except Exception as e:
            print(f"❌ 健康检查异常: {e}")
        
        # 测试2: 索引状态
        total +=1
        print("\n=== 测试 2: 索引状态接口 ===")
        try:
            response = client.get("/api/index/status")
            if response.status_code == 200:
                data = json.loads(response.data)
                print(f"✅ 索引状态检查通过: cell_count={data.get('cell_count')}")
                passed +=1
            else:
                print(f"❌ 索引状态失败: {response.status_code}")
        except Exception as e:
            print(f"❌ 索引状态异常: {e}")
        
        # 测试3: 细胞类型
        total +=1
        print("\n=== 测试 3: 获取细胞类型接口 ===")
        try:
            response = client.get("/api/cell-types")
            if response.status_code == 200:
                data = json.loads(response.data)
                print(f"✅ 获取细胞类型通过: 共 {len(data)} 种")
                passed +=1
            else:
                print(f"❌ 细胞类型失败: {response.status_code}")
        except Exception as e:
            print(f"❌ 细胞类型异常: {e}")
        
        # 测试4: 疾病类型
        total +=1
        print("\n=== 测试 4: 获取疾病类型接口 ===")
        try:
            response = client.get("/api/disease-types")
            if response.status_code == 200:
                data = json.loads(response.data)
                print(f"✅ 获取疾病类型通过: 共 {len(data)} 种")
                passed +=1
            else:
                print(f"❌ 疾病类型失败: {response.status_code}")
        except Exception as e:
            print(f"❌ 疾病类型异常: {e}")
        
        # 测试5: 普通搜索
        total +=1
        print("\n=== 测试 5: 普通搜索 ===")
        try:
            search_response = client.post("/api/search", json={
                "cell_id": "AAACCTGAGCAGGTCA-1_2",
                "k": 5
            })
            
            if search_response.status_code == 200:
                data = json.loads(search_response.data)
                print(f"✅ 普通搜索通过: 返回 {len(data['results'])} 个结果")
                passed +=1
            else:
                print(f"⚠️  普通搜索返回状态: {search_response.status_code}")
        except Exception as e:
            print(f"❌ 普通搜索异常: {e}")
        
        # 测试6: 条件搜索
        total +=1
        print("\n=== 测试 6: 条件搜索 ===")
        try:
            response = client.post("/api/search", json={
                "cell_id": "AAACCTGAGCAGGTCA-1_2",
                "k": 5,
                "search_mode": "conditional",
                "filters": {
                    "cell_type": "hepatocyte"
                }
            })
            
            if response.status_code == 200:
                data = json.loads(response.data)
                print(f"✅ 条件搜索通过: 返回 {len(data['results'])} 个结果")
                passed +=1
            else:
                print(f"⚠️  条件搜索返回状态: {response.status_code}")
        except Exception as e:
            print(f"❌ 条件搜索异常: {e}")
        
        # 测试7: 可视化数据
        total +=1
        print("\n=== 测试 7: 可视化数据 ===")
        try:
            response = client.get("/api/visualization-data")
            if response.status_code == 200:
                print("✅ 可视化数据通过")
                passed +=1
            else:
                print(f"❌ 可视化数据失败: {response.status_code}")
        except Exception as e:
            print(f"❌ 可视化数据异常: {e}")
        
        # 测试8: 数据集列表
        total +=1
        print("\n=== 测试 8: 数据集列表 ===")
        try:
            response = client.get("/api/datasets")
            if response.status_code == 200:
                data = json.loads(response.data)
                print(f"✅ 数据集列表通过: 共 {len(data['datasets'])} 个")
                passed +=1
            else:
                print(f"❌ 数据集列表失败: {response.status_code}")
        except Exception as e:
            print(f"❌ 数据集列表异常: {e}")
        
    finally:
        # 清理临时目录
        try:
            temp_dir.cleanup()
        except Exception:
            import shutil
            try:
                shutil.rmtree(temp_dir.name, ignore_errors=True)
            except Exception:
                pass
    
    print("\n" + "=" * 70)
    print(f"测试结果: 通过 {passed}/{total}")
    print("=" * 70)
    
    return passed == total


if __name__ == "__main__":
    success = run_backend_functional_tests()
    sys.exit(0 if success else 1)
