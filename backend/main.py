from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from arango import ArangoClient
import redis
import json
from typing import Optional

# ========== 配置 ==========
ARANGO_HOST = "http://127.0.0.1:8529"
ARANGO_USER = "root"
ARANGO_PASSWORD = "12345678"
DB_NAME = "hotpot_qa"
REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6379
CACHE_EXPIRE = 3600  # 缓存过期时间 1小时

# ========== 初始化 ==========
app = FastAPI(title="HotpotQA 多跳查询系统")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据库连接
arango_client = ArangoClient(hosts=ARANGO_HOST)
db = arango_client.db(DB_NAME, username=ARANGO_USER, password=ARANGO_PASSWORD)

# Redis连接
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# ========== 工具函数 ==========
def get_cache(key: str):
    data = r.get(key)
    return json.loads(data) if data else None

def set_cache(key: str, value):
    r.setex(key, CACHE_EXPIRE, json.dumps(value, ensure_ascii=False))

# ========== 接口1：多跳查询 ==========
@app.get("/api/multi-hop")
def multi_hop_query(
    entity_name: str = Query(..., description="起始实体名称"),
    max_depth: int = Query(2, ge=1, le=5, description="最大跳数")
):
    cache_key = f"multihop:{entity_name}:{max_depth}"
    cached = get_cache(cache_key)
    if cached:
        return {"code": 0, "data": cached, "from_cache": True}

    # 先查找实体
    entity_cursor = db.aql.execute(
        """
        FOR doc IN entities
            FILTER doc.name == @name
            RETURN doc
        """,
        bind_vars={"name": entity_name}
    )
    entity_list = list(entity_cursor)
    if not entity_list:
        return {"code": 404, "msg": "未找到该实体"}

    start_entity = entity_list[0]
    start_id = f"entities/{start_entity['_key']}"

    # 图遍历：边投影改用子查询遍历，避免语法歧义
    paths_cursor = db.aql.execute(
        """
        FOR v, e, p IN 1..@max_depth ANY @start_id GRAPH 'qa_knowledge_graph'
            OPTIONS { bfs: true }
            RETURN {
                vertices: p.vertices[*].name,
                edges: (
                    FOR edge IN p.edges
                        RETURN {
                            relation: edge.relation_type,
                            question: edge.question_text,
                            answer: edge.answer
                        }
                )
            }
        """,
        bind_vars={"max_depth": max_depth, "start_id": start_id}
    )
    paths = list(paths_cursor)

    # 提取所有节点用于可视化
    node_set = set()
    edges = []
    for path in paths:
        nodes = path["vertices"]
        for i in range(len(nodes)-1):
            node_set.add(nodes[i])
            node_set.add(nodes[i+1])
            edges.append({
                "source": nodes[i],
                "target": nodes[i+1],
                "relation": path["edges"][i]["relation"],
                "question": path["edges"][i]["question"],
                "answer": path["edges"][i]["answer"]
            })
    node_set.add(start_entity["name"])

    nodes = [{"name": name, "category": "entity"} for name in node_set]
    result = {
        "start_entity": start_entity,
        "nodes": nodes,
        "edges": edges,
        "paths": paths,
        "total_paths": len(paths)
    }

    set_cache(cache_key, result)
    return {"code": 0, "data": result, "from_cache": False}
# ========== 接口2：全文检索 ==========
@app.get("/api/search")
def fulltext_search(
    keyword: str = Query(..., description="搜索关键词"),
    search_type: str = Query("all", description="类型: all/question/document/entity"),
    page: int = 1,
    page_size: int = 20
):
    cache_key = f"search:{keyword}:{search_type}:{page}:{page_size}"
    cached = get_cache(cache_key)
    if cached:
        return {"code": 0, "data": cached, "from_cache": True}

    results = {"questions": [], "documents": [], "entities": []}
    offset = (page - 1) * page_size

    if search_type in ["all", "question"]:
        cursor = db.aql.execute(
            """
            FOR doc IN FULLTEXT(questions, 'question', @keyword)
                LIMIT @offset, @page_size
                RETURN {id: doc._key, question: doc.question, answer: doc.answer, type: doc.type, level: doc.level}
            """,
            bind_vars={"keyword": keyword, "offset": offset, "page_size": page_size}
        )
        results["questions"] = list(cursor)

    if search_type in ["all", "document"]:
        cursor = db.aql.execute(
            """
            LET by_title = (
                FOR doc IN FULLTEXT(documents, 'title', @keyword)
                    RETURN doc
            )
            LET by_sentences = (
                FOR doc IN FULLTEXT(documents, 'sentences', @keyword)
                    RETURN doc
            )
            FOR doc IN UNION_DISTINCT(by_title, by_sentences)
                LIMIT @offset, @page_size
                RETURN {id: doc._key, title: doc.title, preview: IS_ARRAY(doc.sentences) ? doc.sentences[0] : LEFT(doc.sentences, 100)}
            """,
            bind_vars={"keyword": keyword, "offset": offset, "page_size": page_size}
        )
        results["documents"] = list(cursor)

    if search_type in ["all", "entity"]:
        cursor = db.aql.execute(
            """
            FOR doc IN FULLTEXT(entities, 'name', @keyword)
                LIMIT @offset, @page_size
                RETURN {id: doc._key, name: doc.name, description: doc.description}
            """,
            bind_vars={"keyword": keyword, "offset": offset, "page_size": page_size}
        )
        results["entities"] = list(cursor)

    set_cache(cache_key, results)
    return {"code": 0, "data": results, "from_cache": False}

# ========== 接口3：聚类统计 ==========
@app.get("/api/cluster")
def cluster_stats():
    cache_key = "cluster:stats"
    cached = get_cache(cache_key)
    if cached:
        return {"code": 0, "data": cached, "from_cache": True}

    # 问题类型分布
    type_cursor = db.aql.execute("""
        FOR doc IN questions
            COLLECT type = doc.type WITH COUNT INTO count
            RETURN {type, count}
    """)
    type_dist = list(type_cursor)

    # 难度分布
    level_cursor = db.aql.execute("""
        FOR doc IN questions
            COLLECT level = doc.level WITH COUNT INTO count
            RETURN {level, count}
    """)
    level_dist = list(level_cursor)

    # 关系类型分布
    rel_cursor = db.aql.execute("""
        FOR doc IN relations
            COLLECT rel_type = doc.relation_type WITH COUNT INTO count
            RETURN {type: rel_type, count}
    """)
    relation_dist = list(rel_cursor)

    stats = {
        "total_questions": db["questions"].count(),
        "total_documents": db["documents"].count(),
        "total_entities": db["entities"].count(),
        "total_relations": db["relations"].count(),
        "type_distribution": type_dist,
        "level_distribution": level_dist,
        "relation_distribution": relation_dist
    }

    set_cache(cache_key, stats)
    return {"code": 0, "data": stats, "from_cache": False}
