# HotpotQA 多跳知识查询与可视化系统

基于 ArangoDB + Redis 构建的多跳知识问答可视化系统，以 HotpotQA 数据集为基础，实现知识图谱多跳推理、多维度全文检索、数据聚类统计三大核心功能。

## 技术栈
- **主数据库**：ArangoDB 3.11 — 多模型数据库，同时承载文档存储、图遍历、全文能力
- **缓存层**：Redis 6+ — 接口结果缓存，降低数据库压力，提升查询性能
- **后端框架**：Python 3.12 + FastAPI + Uvicorn
- **前端可视化**：原生 HTML/CSS/JavaScript + ECharts 5.4
- **数据集**：HotpotQA（训练集 + 验证集）

## 项目目录结构

``` plaintext
hotpot-qa-experiment/
├── data/
│   ├── raw/          # 原始数据集：train.jsonl、dev.jsonl
│   └── processed/    # 预处理后的结构化数据文件
├── scripts/
│   ├── preprocess.py # 数据预处理 ETL 脚本
│   ├── init_db.py    # ArangoDB 数据库初始化脚本
│   └── evaluate.py   # 多跳推理效果评估脚本
├── backend/
│   └── main.py       # FastAPI 后端服务主程序
├── frontend/
│   └── index.html    # 前端单页可视化应用
└── README.md         # 项目说明文档
```

## 部署与运行
> 运行环境：Ubuntu 系统，需提前安装 ArangoDB、Redis、Python3

### 1. 环境准备
```bash
# 安装系统依赖
sudo apt install python3-pip python3-venv -y

# 创建并激活 Python 虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装Python依赖包（使用清华镜像源加速下载）
pip install python-arango redis fastapi uvicorn pydantic tqdm -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2. 数据集准备
1. 将 HotpotQA 训练集、验证集文件放入 `data/raw/` 目录
2. 执行数据预处理脚本，生成结构化数据：
```bash
cd scripts
python preprocess.py
```
执行完成后，`data/processed/` 目录会生成实体、关系、文档、问题四类文件。

### 3. 数据库初始化
确保本地 ArangoDB 服务正常启动，执行初始化脚本，创建数据库、集合、索引与知识图谱：
```bash
python init_db.py
```

使用 `arangoimport` 工具批量导入结构化数据：
```bash
# 导入文档集合
arangoimport --server.database hotpot_qa --server.username root --server.password 12345678 \
  --collection documents --type jsonl --file ../data/processed/documents.jsonl --on-duplicate ignore

# 导入实体集合
arangoimport --server.database hotpot_qa --server.username root --server.password 12345678 \
  --collection entities --type jsonl --file ../data/processed/entities.jsonl --on-duplicate ignore

# 导入问题集合
arangoimport --server.database hotpot_qa --server.username root --server.password 12345678 \
  --collection questions --type jsonl --file ../data/processed/questions.jsonl --on-duplicate ignore

# 导入关系边集合
arangoimport --server.database hotpot_qa --server.username root --server.password 12345678 \
  --collection relations --type jsonl --file ../data/processed/relations.jsonl --on-duplicate ignore
```

### 4. 启动后端服务
```bash
cd ../backend
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > app.log 2>&1 &
```

**接口验证说明**：
`http://127.0.0.1:8000/api/cluster` 为**本地内网接口**，仅能在部署服务器/本机访问，外网、GitHub 环境无法连通，属于正常现象。
本地验证命令：
```bash
curl http://127.0.0.1:8000/api/cluster
```

### 5. 启动前端服务
```bash
cd ../frontend
nohup python3 -m http.server 8080 > server.log 2>&1 &
```
本地浏览器访问：`http://localhost:8080` 进入系统首页。

## 核心功能
### 1. 多跳知识推理
- 支持 2/3/4 跳自定义多跳推理深度
- 基于 BFS 广度优先遍历知识图谱，完整返回关联路径
- ECharts 力导向图可视化实体与关系，支持拖拽、缩放交互
- 展示推理路径、关联问题与标准答案

### 2. 多维度全文检索
- 支持问题、文档、实体 三类数据单独/联合检索
- 依托 ArangoDB 全文索引，匹配标题、正文、题干内容
- 分页展示检索结果，附带类型、难度等元数据标签

### 3. 聚类统计可视化
- 展示问题、文档、实体、关系总数量
- 可视化图表：问题类型分布、难度等级分布、关系类型分布
- 图表支持悬浮查看详细数值

## 效果评估
项目内置评估脚本，基于 HotpotQA 验证集测试多跳推理效果：
```bash
cd scripts
python evaluate.py
```

### 基线测试结果
1. 仅匹配实体名称：有效样本准确率 11.7%，整体准确率 7.29%
2. 实体名称 + 文档描述联合匹配：有效样本准确率 19.21%，整体准确率 12.01%

### 性能优化
- 引入 Redis 做热点数据缓存，重复请求响应速度提升 90% 以上
- 依托 ArangoDB 全文索引、持久化索引，保障检索与聚合效率
