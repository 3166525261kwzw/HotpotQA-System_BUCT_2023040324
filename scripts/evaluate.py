import json
import requests
from tqdm import tqdm
import os

API_BASE = "http://127.0.0.1:8000/api"
TEST_FILE = "../data/processed/test_questions.jsonl"

def evaluate():
    # 读取全部验证集测试用例
    with open(TEST_FILE, "r", encoding="utf-8") as f:
        test_cases = [json.loads(line.strip()) for line in f.readlines()]

    total_count = len(test_cases)
    hit_count = 0
    error_count = 0
    error_sample_list = []
    detail_records = []

    for case in tqdm(test_cases, desc="多跳问答验证评估进度"):
        try:
            # 提取测试用例关键信息
            q_id = case["_key"]
            question_text = case["question"]
            std_answer = case["answer"].strip().lower()
            sup_title_list = case["supporting_facts"]["title"]
            start_entity_name = sup_title_list[0]

            # 请求多跳查询接口，最大3跳覆盖HotpotQA题型
            resp = requests.get(
                url=f"{API_BASE}/multi-hop",
                params={
                    "entity_name": start_entity_name,
                    "max_depth": 3
                },
                timeout=10
            )
            resp_json = resp.json()

            # 接口业务异常判断
            if resp_json["code"] != 0:
                raise Exception(f"业务异常码{resp_json['code']}:{resp_json.get('msg','无详情')}")

            graph_data = resp_json["data"]
            paths = graph_data["paths"]
            all_node_info = graph_data["nodes"]
            match_success = False

            # 构建节点名称-描述映射字典
            node_desc_map = {}
            for node in all_node_info:
                node_name = node["name"].lower()
                desc = node.get("description", "").lower()
                node_desc_map[node_name] = desc

            # 遍历所有推理路径，扩大匹配范围：节点名称 + 节点描述
            for path_item in paths:
                vertex_names = [v.lower() for v in path_item["vertices"]]
                full_text_pool = ""
                # 拼接节点名称
                full_text_pool += " ".join(vertex_names) + " "
                # 拼接每个节点对应的文档描述正文
                for v_name in vertex_names:
                    full_text_pool += node_desc_map.get(v_name, "") + " "
                # 标准答案命中文本池则判定正确
                if std_answer in full_text_pool:
                    match_success = True
                    break

            if match_success:
                hit_count += 1
                detail_records.append({
                    "qid": q_id,
                    "question": question_text,
                    "std_answer": std_answer,
                    "start_entity": start_entity_name,
                    "status": "命中正确"
                })
            else:
                detail_records.append({
                    "qid": q_id,
                    "question": question_text,
                    "std_answer": std_answer,
                    "start_entity": start_entity_name,
                    "status": "未匹配答案"
                })

        except Exception as err:
            error_count += 1
            err_msg = str(err)
            # 只存储前5条异常样例用于调试
            if len(error_sample_list) < 5:
                error_sample_list.append({
                    "qid": case["_key"],
                    "start_entity": case["supporting_facts"]["title"][0],
                    "error_info": err_msg[:220]
                })
            detail_records.append({
                "qid": case["_key"],
                "status": "请求异常",
                "error": err_msg
            })
            continue

    # 计算最终准确率（仅统计成功请求的样本）
    valid_req_num = total_count - error_count
    accuracy = (hit_count / valid_req_num * 100) if valid_req_num > 0 else 0
    overall_accuracy = (hit_count / total_count * 100) if total_count > 0 else 0

    # 控制台打印评估汇总结果
    print("\n==================== 多跳问答评估汇总结果 ====================")
    print(f"总测试用例数量：{total_count}")
    print(f"接口请求异常数量：{error_count}")
    print(f"有效可推理样本数：{valid_req_num}")
    print(f"答案匹配命中数量：{hit_count}")
    print(f"有效样本内准确率：{accuracy:.2f} %")
    print(f"全量样本整体准确率：{overall_accuracy:.2f} %")

    if error_sample_list:
        print("\n---------------- 前5条请求异常样例详情 ----------------")
        for idx, sample in enumerate(error_sample_list, 1):
            print(f"{idx}. QID:{sample['qid']} | 起始实体:{sample['start_entity']}")
            print(f"   异常信息：{sample['error_info']}\n")

    # 写入完整评估报告文件
    report_file = "../data/processed/evaluation_full_report.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("=== HotpotQA 多跳问答系统评估报告 ===\n")
        f.write(f"总用例：{total_count}\n")
        f.write(f"请求失败数：{error_count}\n")
        f.write(f"有效推理样本：{valid_req_num}\n")
        f.write(f"答案命中数：{hit_count}\n")
        f.write(f"有效样本准确率：{accuracy:.2f}%\n")
        f.write(f"全量整体准确率：{overall_accuracy:.2f}%\n\n")
        f.write("===== 逐条详细记录 =====\n")
        for record in detail_records:
            f.write(f"{record}\n")

    print(f"\n完整评估报告已保存至路径：{report_file}")

if __name__ == "__main__":
    # 锁定脚本工作目录
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    evaluate()
