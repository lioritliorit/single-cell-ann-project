# 数据集管理与联合检索测试日志

测试日期：2026-06-09

## 环境

- 工作目录：`C:\Users\moyux\Desktop\single-cell-ann-project`
- 后端：Flask
- 索引：FAISS `IndexFlatL2` 用于新导入和联合数据集；默认数据集保留原 FAISS/HNSW 文件

## 已完成测试

1. Python 编译检查

```bash
python -m py_compile app.py ann_search_service.py hnsw_search_service.py vector_processor.py data_loader.py
```

结果：通过。

2. 默认数据集注册

预期：首次启动时生成 `datasets/manifest.json`，注册 `default` 数据集，并指向：

```text
cleaned_pca_vectors.npy
cleaned_cell_metadata.csv
faiss_index.bin
hnsw_index.npz
```

3. Web API 覆盖范围

新增接口：

```text
GET    /api/datasets
POST   /api/datasets/upload
DELETE /api/datasets/<dataset_id>
POST   /api/datasets/switch
POST   /api/datasets/joint-index
```

原有接口已联动当前活动数据集：

```text
GET  /api/index/status
GET  /api/cell-types
GET  /api/visualization-data
POST /api/search
```

## 推荐现场调试流程

1. 启动服务

```bash
python app.py
```

2. 打开页面

```text
http://127.0.0.1:5000
```

3. 上传肝病专题 h5ad

页面参数建议：

```text
group: liver_disease
source: 数据来源或论文名
tags: liver,cirrhosis,hepatitis
```

4. 验证自动索引

上传成功后检查：

```text
datasets/uploads/<dataset_id>.h5ad
datasets/processed/<dataset_id>/vectors.npy
datasets/processed/<dataset_id>/metadata.csv
datasets/processed/<dataset_id>/faiss_index.bin
datasets/manifest.json
```

5. 切换和检索

在数据集表格中切换到上传数据集，输入该数据集内的 `cell_id`，执行 Top-K 检索。

6. 构建联合索引

勾选 `default` 和肝病数据集，点击“构建所选联合索引”。成功后活动数据集变为 `joint-*`，检索结果表格应显示命中的来源数据集。

7. 条件过滤

在联合索引上选择“数据分组 = 肝病”，提交检索。请求中会带：

```json
{"filters": {"dataset_group": "liver_disease"}}
```

8. 删除清理

删除上传数据集后，应同步清理对应 h5ad、向量、元数据、FAISS 索引和处理目录。依赖该数据集的联合索引会在清单中标记为 `stale=true`。

## 当前限制

- 本仓库没有额外提供真实肝病 h5ad 文件，因此本日志记录的是功能流程和可复现实测步骤；实际跨库结果需在导入真实肝病数据后完成。
- 新上传数据集只自动构建 FAISS 索引，不自动构建 HNSW 索引。
