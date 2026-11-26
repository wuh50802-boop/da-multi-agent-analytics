
import unittest

from src.core.context_manager import (
    select_context_tasks,
    build_task_summaries,
    limit_context_size
)


class TestSelectContextTasks(unittest.TestCase):

    def setUp(self):
        # 模拟按时间从旧到新排列的历史任务
        self.summaries = [
            {
                "task_id": "task_001",
                "question": "Toyota Corolla 的价格是多少？",
                "task_type": "query",
                "status": "success"
            },
            {
                "task_id": "task_002",
                "question": "墨西哥有哪些热门 SUV？",
                "task_type": "query",
                "status": "success"
            }
        ]

    def test_short_follow_up(self):
        """简短追问应关联最近一条历史任务。"""
        result = select_context_tasks(
            "那 Honda 呢？",
            self.summaries
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["task_id"], "task_002")

    def test_unrelated_question(self):
        """无关的新问题不应自动继承历史任务。"""
        result = select_context_tasks(
            "帮我查询今天的汇率",
            self.summaries
        )

        self.assertEqual(result, [])

    def test_keyword_matching(self):
        """有共同关键词的问题应匹配相关历史任务。"""
        result = select_context_tasks(
            "Toyota Corolla 的配置有哪些？",
            self.summaries
        )

        self.assertTrue(len(result) > 0)
        self.assertEqual(result[0]["task_id"], "task_001")

    
    def test_rejected_task_is_selected_for_retry(self):
        """重新尝试时，即使关键词无法匹配，也应保留原 rejected 任务。"""

        summaries = [
            {
                "task_id": "task_rejected",
                "question": "的",
                "resolved_question": "的",
                "task_type": "sql",
                "status": "rejected",
                "error": None,
                "result_count": None
            }
        ]

        result = select_context_tasks(
            "的",
            summaries
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0]["task_id"],
            "task_rejected"
        )
        self.assertEqual(
            result[0]["status"],
            "rejected"
        )

        # 历史摘要不能携带 SQL
        self.assertNotIn("sql", result[0])


    def test_query_result_count(self):
        """应正确读取 query_results 并统计结果数量。"""

        history = [
            {
                "task_id": "task_004",
                "question": "查询 Honda Civic",
                "task_type": "query",
                "status": "success",
                "query_results": [
                    {"model": "Honda Civic"},
                    {"model": "Honda Accord"},
                    {"model": "Honda Fit"}
                ]
            }
        ]

        result = build_task_summaries(history)

        self.assertEqual(result[0]["result_count"], 3)


class TestLimitContextSize(unittest.TestCase):

    def setUp(self):
        self.context = {
            "current_task": {
                "task_id": "task_003",
                "conversation_id": "conversation_001",
                "question": "查询 Honda Civic 的价格",
                "task_type": "query"
            },

            "messages": [
                {
                    "role": "user",
                    "content": "查询 Toyota Corolla 的价格"
                },
                {
                    "role": "assistant",
                    "content": "Toyota Corolla 的价格为..."
                }
            ],

            "task_history": [
                {
                    "task_id": "task_001",
                    "question": "查询 Toyota Corolla 的价格"
                },
                {
                    "task_id": "task_002",
                    "question": "查询墨西哥热门 SUV"
                }
            ],

            "metadata": {
                "total_messages": 2,
                "selected_messages": 2,
                "total_history": 2,
                "selected_tasks": 2
            }
        }

    def test_current_task_is_preserved(self):
        """即使当前任务超过长度限制，也必须保留当前问题。"""

        result = limit_context_size(
            self.context,
            max_chars=1
        )

        self.assertEqual(
            result["current_task"]["question"],
            "查询 Honda Civic 的价格"
        )

        self.assertEqual(result["messages"], [])
        self.assertEqual(result["task_history"], [])

        self.assertTrue(
            result["metadata"]["size_limit_exceeded"]
        )

    def test_max_history_limit(self):
        """历史任务数量不能超过 max_history。"""

        result = limit_context_size(
            self.context,
            max_history=1,
            max_chars=4000
        )

        self.assertLessEqual(
            len(result["task_history"]),
            1
        )

        self.assertEqual(
            result["metadata"]["selected_tasks"],
            len(result["task_history"])
        )

    def test_context_truncation(self):
        """被裁剪的历史任务应正确反映在 metadata 中。"""

        result = limit_context_size(
            self.context,
            max_history=1,
            max_chars=4000
        )

        self.assertTrue(
            result["metadata"]["context_truncated"]
        )

        self.assertEqual(
            result["metadata"]["selected_tasks"],
            1
        )

    def test_messages_preserved(self):
        """长度允许时，应保留原始对话消息。"""

        result = limit_context_size(
            self.context,
            max_chars=4000
        )

        self.assertEqual(
            len(result["messages"]),
            2
        )

        self.assertEqual(
            result["messages"][0]["role"],
            "user"
        )


if __name__ == "__main__":
    unittest.main()
