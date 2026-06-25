# 系统测试文档

本文件夹包含完整的系统测试，涵盖**后端功能测试**、**后端性能测试**和**前端测试**。

---

## 📁 测试文件列表

| 文件 | 说明 | 类型 |
|------|------|------|
| `run_all_tests.py` | 测试入口，一键运行所有测试并生成报告 | 入口 |
| `test_reporter.py` | 测试报告生成器（自动生成Markdown报告） | 工具 |
| `backend_functional_test.py` | 后端功能测试（API 接口） | 功能测试 |
| `backend_performance_test.py` | 后端性能测试（响应时间、吞吐量） | 性能测试 |
| `frontend_test.py` | 前端测试（页面加载、API 集成） | 功能测试 |
| `test_member4_api.py` | 成员4 API 测试（认证、权限） | 功能测试 |
| `test_search_modes.py` | 成员3 检索模式测试 | 功能测试 |
| `test_search_api.py` | 基础搜索 API 测试 | 功能测试 |
| `api_stress_test.py` | 并发压测脚本 | 性能测试 |
| `reports/` | 测试报告目录（自动生成Markdown报告） | 报告 |

---

## 🚀 快速开始

### 1. 一键运行所有测试（自动启动服务）
```bash
python tests/run_all_tests.py
```
这个命令会：
- 先运行无需服务的功能测试
- 自动启动 Flask 后端服务
- 运行需要服务的性能和前端测试
- 最后自动关闭服务

### 2. 选择性运行测试
```bash
# 仅运行功能测试（无服务）
python tests/run_all_tests.py --mode functional

# 运行含服务的完整测试（功能+性能+前端）
python tests/run_all_tests.py --mode with-server

# 仅运行性能测试（自动启动服务）
python tests/run_all_tests.py --mode performance

# 仅运行前端测试（自动启动服务）
python tests/run_all_tests.py --mode frontend

# 运行成员3测试
python tests/run_all_tests.py --mode member3

# 运行成员4测试
python tests/run_all_tests.py --mode member4

# 仅运行压测（自动启动服务）
python tests/run_all_tests.py --mode stress
```

### 3. 单独运行某个测试
```bash
# 后端功能测试
python tests/backend_functional_test.py

# 后端性能测试（需要先启动 app.py）
python tests/backend_performance_test.py

# 前端测试（需要先启动 app.py）
python tests/frontend_test.py

# 成员4 API测试
python tests/test_member4_api.py

# 检索模式测试
python tests/test_search_modes.py

# 基础搜索测试
python tests/test_search_api.py

# 并发压测（需要先启动 app.py）
python tests/api_stress_test.py --url http://127.0.0.1:5000 --requests 100 --workers 8
```

---

## 📋 测试分类详解

### 一、功能测试
测试系统功能是否正常工作。

| 测试文件 | 测试内容 |
|---------|---------|
| `backend_functional_test.py` | 健康检查、索引状态、搜索、细胞类型、疾病类型、可视化数据、数据集 |
| `test_member4_api.py` | 用户注册、登录、权限、数据集策略 |
| `test_search_modes.py` | 普通检索、条件检索、预过滤 vs 后过滤、索引缓存、边界条件 |
| `test_search_api.py` | 基础搜索功能 |

### 二、性能测试
测试系统性能指标。

| 测试文件 | 测试内容 |
|---------|---------|
| `backend_performance_test.py` | 搜索响应时间、健康检查响应时间、索引状态响应时间 |
| `api_stress_test.py` | 多用户并发访问、吞吐量、P50/P95 延迟 |

### 三、前端测试
测试前端页面和交互。

| 测试文件 | 测试内容 |
|---------|---------|
| `frontend_test.py` | 页面加载、静态资源、API 集成 |

---

## ⚙️ 测试环境要求

- Python 3.8+
- 依赖库（见根目录 `requirements.txt`）
- `run_all_tests.py` 会自动管理服务启停，无需手动操作

---

## 📊 测试报告

### Markdown 测试报告
运行 `run_all_tests.py` 时会自动在 `tests/reports/` 目录下生成：
- `latest_test_report.md` - 最新测试报告（每次运行都会更新）
- `test_report_YYYYMMDD_HHMMSS.md` - 带时间戳的历史测试报告

### JSON 性能报告
- `docs/backend_performance_report.json` - 后端性能测试详细数据
- `docs/member4_concurrency_result.json` - 并发压测详细结果

---

## 🔧 注意事项

1. 所有测试文件已添加项目根目录到 `sys.path`，可正确导入项目模块
2. 测试运行时会自动切换到项目根目录
3. `run_all_tests.py` 会自动管理 Flask 服务的启动和关闭
