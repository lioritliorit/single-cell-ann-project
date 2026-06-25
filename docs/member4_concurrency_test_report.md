# 成员4：多用户并发压测报告

## 测试目标

验证后端在多用户并发访问下的基础稳定性，重点覆盖：

- `/api/search` 检索接口并发请求
- 索引服务只读查询期间不出现异常
- 响应结构保持一致
- 失败请求可通过状态码定位

## 测试环境

- 后端：Flask
- 数据：默认内置单细胞 PCA 向量、元数据和 FAISS 索引
- 压测脚本：`tests/api_stress_test.py`
- 默认参数：100 个请求，8 个并发 worker，Top-K=5

## 测试命令

```powershell
python app.py
python tests/api_stress_test.py --url http://127.0.0.1:5000 --requests 100 --workers 8
```

可调整参数：

```powershell
python tests/api_stress_test.py --requests 500 --workers 16 --k 10
```

## 输出指标

脚本输出 JSON，包含：

- `success` / `failed`
- `success_rate`
- `throughput_rps`
- `latency_ms.min`
- `latency_ms.avg`
- `latency_ms.p50`
- `latency_ms.p95`
- `latency_ms.max`
- `failed_statuses`

结构化结果保存到：

```text
docs/member4_concurrency_result.json
```

## 稳定性保障措施

- 索引引擎切换、数据集切换、上传后重加载统一使用 `index_lock`。
- 检索接口先校验当前用户是否可访问活动数据集，再进入搜索服务。
- 数据集删除前校验所有者或管理员身份。
- 管理员接口和数据集写接口统一返回 JSON 错误，不暴露堆栈。

## 结论

成员4交付的压测脚本可复现多用户并发检索场景，并为结项报告提供吞吐量、响应时间和失败率数据。后续如果新增大型肝病专题数据集，应重新运行该脚本并归档 `member4_concurrency_result.json`。
