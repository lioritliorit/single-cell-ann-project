# Single-Cell ANN 后端 API

该后端完成：调用已构建的 FAISS ANN 索引，实现 Top-K 相似细胞查询，并返回细胞 ID、细胞类型、疾病状态、表达量相关字段和查询耗时。

## 安装依赖

```bash
pip install -r requirements.txt
```

## 启动服务

```bash
python app.py
```

默认地址：

```text
http://127.0.0.1:5000
```

如需指定文件路径，可使用环境变量：

```bash
ANN_INDEX_PATH=faiss_index.bin
ANN_VECTORS_PATH=cleaned_pca_vectors.npy
ANN_METADATA_PATH=cleaned_cell_metadata.csv
```

## 接口

### 健康检查

```http
GET /api/health
```

### 查看索引状态

```http
GET /api/index/status
```

返回示例字段：

```json
{
  "loaded": true,
  "cell_count": 69032,
  "index_total": 69032,
  "dimension": 30
}
```

### 按 cell_id 查询 Top-K

```http
POST /api/search
Content-Type: application/json

{
  "cell_id": "AAACCTGAGCAGGTCA-1_2",
  "k": 5,
  "nprobe": 10
}
```

### 按查询向量查询 Top-K

```http
POST /api/search
Content-Type: application/json

{
  "vector": [0.12, -1.4, 0.33],
  "k": 5
}
```

`vector` 长度必须与 PCA 维度一致，本项目为 30 维。

### 带简单条件过滤

该过滤在 ANN 召回候选后执行，适合前端演示“限定某类细胞”的查询。

```http
POST /api/search
Content-Type: application/json

{
  "cell_id": "AAACCTGAGCAGGTCA-1_2",
  "k": 5,
  "filters": {
    "cell_type": "hepatocyte"
  }
}
```

### 查询单个细胞信息

```http
GET /api/cells/AAACCTGAGCAGGTCA-1_2
```

## 本地测试

```bash
python test_search_api.py
```

该脚本会加载 `faiss_index.bin`、`cleaned_pca_vectors.npy`、`cleaned_cell_metadata.csv`，使用第一条细胞记录执行 `k=5` 查询，并打印返回的 Top-K 结果与耗时。
