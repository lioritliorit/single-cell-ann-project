# 成员4：后端全链路与权限管理交付说明

## 1. 后端全链路接口

本模块统一承接数据集管理、条件检索、可视化数据和性能评测数据接口。

核心接口：

| 功能 | 方法 | 路径 | 权限 |
| --- | --- | --- | --- |
| 健康检查 | GET | `/api/health` | 公开 |
| 索引状态 | GET | `/api/index/status` | 当前数据集可见 |
| 数据集列表 | GET | `/api/datasets` | 按用户权限过滤 |
| 上传 h5ad | POST | `/api/datasets/upload` | 登录用户 |
| 切换活动数据集 | POST | `/api/datasets/switch` | 登录用户且有访问权 |
| 删除数据集 | DELETE | `/api/datasets/<dataset_id>` | 管理员或数据集所有者 |
| 联合索引 | POST | `/api/datasets/joint-index` | 登录用户且可访问所有组件数据集 |
| 普通/条件/跨库检索 | POST | `/api/search` | 当前数据集可见 |
| 细胞详情 | GET | `/api/cells/<cell_id>` | 当前数据集可见 |
| 细胞类型 | GET | `/api/cell-types` | 当前数据集可见 |
| 疾病类型 | GET | `/api/disease-types` | 当前数据集可见 |
| 可视化数据 | GET | `/api/visualization-data` | 当前数据集可见 |
| 性能评测数据 | GET | `/api/evaluation-data` | 当前数据集可见 |

检索接口继续兼容成员3的三种模式：

```json
{
  "cell_id": "AAACCTGAGCAGGTCA-1_2",
  "k": 10,
  "search_mode": "conditional",
  "filters": {
    "cell_type": "hepatocyte",
    "disease": "fibrosis",
    "dataset_group": "liver_disease"
  }
}
```

## 2. 用户与权限管理

SQLite 数据库文件默认是 `auth.db`，可通过 `AUTH_DB_PATH` 指定。

首次启动时系统自动创建管理员：

```powershell
$env:ADMIN_USERNAME="admin"
$env:ADMIN_PASSWORD="admin123"
python app.py
```

认证接口：

| 功能 | 方法 | 路径 |
| --- | --- | --- |
| 注册 | POST | `/api/auth/register` |
| 登录 | POST | `/api/auth/login` |
| 退出 | POST | `/api/auth/logout` |
| 当前用户 | GET | `/api/auth/me` |

登录成功后返回 `token`，后续请求使用：

```http
Authorization: Bearer <token>
```

管理员接口：

| 功能 | 方法 | 路径 |
| --- | --- | --- |
| 用户列表 | GET | `/api/admin/users` |
| 修改用户 | PATCH | `/api/admin/users/<user_id>` |
| 删除用户 | DELETE | `/api/admin/users/<user_id>` |
| 数据集策略列表 | GET | `/api/admin/dataset-policies` |
| 修改数据集策略 | PUT | `/api/admin/dataset-policies/<dataset_id>` |

数据集权限策略：

| visibility | 含义 |
| --- | --- |
| `public` | 匿名用户也可访问 |
| `liver_disease` | 登录用户可访问，用于肝病专题区分 |
| `private` | 仅所有者和管理员可访问 |

上传数据集时可传入表单字段 `visibility`，默认规则为：

- `default` 和联合数据集：`public`
- `group=liver_disease`：`liver_disease`
- 其他上传数据集：`private`

## 3. RAG 接口预留

后端预留接口：

```http
POST /api/rag/query
Content-Type: application/json

{
  "question": "Find hepatocyte cells from liver fibrosis",
  "k": 5
}
```

当前实现不会调用外部大模型，而是将自然语言中的关键词解析成结构化过滤条件：

```json
{
  "mode": "rag_placeholder",
  "parsed_filters": {
    "cell_type": "hepatocyte",
    "disease": "fibrosis",
    "dataset_group": "liver_disease"
  },
  "recommended_search_request": {
    "search_mode": "conditional",
    "k": 5,
    "filters": {
      "cell_type": "hepatocyte",
      "disease": "fibrosis",
      "dataset_group": "liver_disease"
    }
  }
}
```

如果请求中同时提供 `cell_id` 或 `vector`，接口会返回 `retrieval_preview`，可作为后续 RAG 回答的检索上下文。

## 4. 稳定性与并发测试

功能测试：

```powershell
python tests/test_member4_api.py
```

并发压测：

```powershell
python app.py
python tests/api_stress_test.py --url http://127.0.0.1:5000 --requests 100 --workers 8
```

压测输出：

- 控制台打印吞吐量、成功率、平均延迟、P50、P95。
- 结构化结果写入 `docs/member4_concurrency_result.json`。

## 5. 接口适配与 bug 修复记录

- 接入 `main` 分支已有数据集管理、动态索引、联合索引、条件检索、可视化数据接口，形成完整后端数据流。
- 为全局活动索引切换、数据集切换和检索服务重绑定增加 `index_lock` 保护，降低并发请求时的状态竞争风险。
- 数据集写操作改为登录用户接口；删除操作限定为管理员或数据集所有者。
- 数据集列表按当前用户权限过滤，避免私有数据集暴露给无权限用户。
- RAG 后端接口以结构化 filters 作为稳定契约，便于后续前端或 LLM 服务接入。
