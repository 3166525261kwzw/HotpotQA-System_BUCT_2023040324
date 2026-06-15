import json
import hashlib
import os
from tqdm import tqdm

RAW_DIR = "../data/raw"
PROCESSED_DIR = "../data/processed"

def get_md5_key(text: str) -> str:
    """生成符合ArangoDB规范的唯一_key"""
    return hashlib.md5(text.strip().encode("utf-8")).hexdigest()

def process_dataset(input_file: str, is_train: bool):
    questions_out = []
    documents_map = {}  # 标题去重
    entities_map = {}
    relations_out = []
    test_questions_out = []

    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in tqdm(lines, desc=f"处理 {os.path.basename(input_file)}"):
        item = json.loads(line.strip())
        qid = item["_id"] if "_id" in item else item["id"]
        question = item["question"]
        answer = item["answer"]
        q_type = item["type"]
        level = item["level"]
        supporting_facts = item["supporting_facts"]
        context = item["context"]

        # 1. 处理问题数据
        doc_titles = context["title"]
        doc_ids = [get_md5_key(title) for title in doc_titles]
        question_doc = {
            "_key": qid,
            "question": question,
            "answer": answer,
            "type": q_type,
            "level": level,
            "supporting_facts": supporting_facts,
            "doc_ids": doc_ids
        }
        if is_train:
            questions_out.append(question_doc)
        else:
            test_questions_out.append(question_doc)

        # 2. 处理上下文文档（去重）
        sentences_list = context["sentences"]
        for idx, title in enumerate(doc_titles):
            doc_key = doc_ids[idx]
            if doc_key not in documents_map:
                sentences = ["".join(s) if isinstance(s, list) else s for s in sentences_list[idx]]
                documents_map[doc_key] = {
                    "_key": doc_key,
                    "title": title,
                    "sentences": sentences,
                    "related_question_ids": [qid]
                }
            else:
                if qid not in documents_map[doc_key]["related_question_ids"]:
                    documents_map[doc_key]["related_question_ids"].append(qid)

            # 3. 构建实体节点
            if doc_key not in entities_map:
                entities_map[doc_key] = {
                    "_key": doc_key,
                    "name": title,
                    "type": "wiki_entity",
                    "description": sentences[0] if sentences else ""
                }

        # 4. 构建关系边
        if is_train:
            sup_titles = supporting_facts["title"]
            unique_sup_titles = list(dict.fromkeys(sup_titles))  # 去重保序
            
            # bridge/comparison 问题连接两个支撑实体
            if len(unique_sup_titles) >= 2:
                from_title = unique_sup_titles[0]
                to_title = unique_sup_titles[1]
                from_key = get_md5_key(from_title)
                to_key = get_md5_key(to_title)
                
                edge_key = get_md5_key(f"{from_key}_{to_key}_{qid}")
                relation_doc = {
                    "_key": edge_key,
                    "_from": f"entities/{from_key}",
                    "_to": f"entities/{to_key}",
                    "relation_type": f"{q_type}_link",
                    "question_id": qid,
                    "question_text": question,
                    "answer": answer,
                    "level": level
                }
                relations_out.append(relation_doc)

    # 输出文件
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    
    if is_train:
        # 输出问题集
        with open(f"{PROCESSED_DIR}/questions.jsonl", "w", encoding="utf-8") as f:
            for doc in questions_out:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        
        # 输出文档集
        with open(f"{PROCESSED_DIR}/documents.jsonl", "w", encoding="utf-8") as f:
            for doc in documents_map.values():
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        
        # 输出实体集
        with open(f"{PROCESSED_DIR}/entities.jsonl", "w", encoding="utf-8") as f:
            for doc in entities_map.values():
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        
        # 输出关系集
        with open(f"{PROCESSED_DIR}/relations.jsonl", "w", encoding="utf-8") as f:
            for doc in relations_out:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        print(f"训练集处理完成：问题{len(questions_out)}条，文档{len(documents_map)}篇，实体{len(entities_map)}个，关系{len(relations_out)}条")
    else:
        # 输出测试集
        with open(f"{PROCESSED_DIR}/test_questions.jsonl", "w", encoding="utf-8") as f:
            for doc in test_questions_out:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        print(f"验证集处理完成：测试问题{len(test_questions_out)}条")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    process_dataset(f"{RAW_DIR}/train.jsonl", is_train=True)
    process_dataset(f"{RAW_DIR}/dev.jsonl", is_train=False)
