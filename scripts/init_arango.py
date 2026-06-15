from arango import ArangoClient
import os


ARANGO_HOST = "http://127.0.0.1:8529"
ARANGO_USER = "root"
ARANGO_PASSWORD = "12345678"
DB_NAME = "hotpot_qa"

def init_database():
    client = ArangoClient(hosts=ARANGO_HOST)
    sys_db = client.db("_system", username=ARANGO_USER, password=ARANGO_PASSWORD)

    # 创建数据库（若不存在）
    if not sys_db.has_database(DB_NAME):
        sys_db.create_database(DB_NAME)
        print(f" 数据库 {DB_NAME} 创建成功")
    else:
        print(f"  数据库 {DB_NAME} 已存在")

    db = client.db(DB_NAME, username=ARANGO_USER, password=ARANGO_PASSWORD)

    # 1. 创建文档集合
    collections = ["questions", "documents", "entities", "test_questions"]
    for col_name in collections:
        if not db.has_collection(col_name):
            db.create_collection(col_name)
            print(f" 集合 {col_name} 创建成功")
        else:
            print(f"  集合 {col_name} 已存在")

    # 2. 创建边集合
    if not db.has_collection("relations"):
        db.create_collection("relations", edge=True)
        print(" 边集合 relations 创建成功")
    else:
        print("  边集合 relations 已存在")

    # 3. 创建知识图谱（适配 python-arango 8.x 字段规范）
    graph_name = "qa_knowledge_graph"
    if not db.has_graph(graph_name):
        graph = db.create_graph(
            graph_name,
            edge_definitions=[{
                "edge_collection": "relations",
                "from_vertex_collections": ["entities"],
                "to_vertex_collections": ["entities"]
            }]
        )
        print(f" 知识图谱 {graph_name} 创建成功")
    else:
        print(f"  知识图谱 {graph_name} 已存在")

    # 4. 创建索引（使用 add_index 替代旧版 ensure_index）
    # 全文索引
    db["questions"].add_index({"type": "fulltext", "fields": ["question"], "minLength": 2})
    db["documents"].add_index({"type": "fulltext", "fields": ["title"], "minLength": 2})
    db["documents"].add_index({"type": "fulltext", "fields": ["sentences"], "minLength": 2})
    db["entities"].add_index({"type": "fulltext", "fields": ["name"], "minLength": 2})
    print(" 全文索引创建完成")

    # 持久化索引（加速过滤与聚合）
    db["questions"].add_index({"type": "persistent", "fields": ["type"]})
    db["questions"].add_index({"type": "persistent", "fields": ["level"]})
    db["entities"].add_index({"type": "persistent", "fields": ["type"]})
    print(" 聚合索引创建完成")

    print("\n ArangoDB 初始化全部完成")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    init_database()
