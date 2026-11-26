
import unittest
from unittest.mock import patch

from src.service.task_service import retry_task


class TestRetryTask(unittest.TestCase):

    def setUp(self):
        self.original_state = {
            "task_id": "task_old",
            "question": "统计每个用户发布的帖子数量",
            "conversation_id": "conversation_001",
            "status": "rejected",
            "task_type": "sql",
            "resolved_question": "统计每个用户发布的帖子数量",
            "sql": "SELECT * FROM invalid_table",
            "sql_approved": False,
            "query_results": None,
            "report": None
        }

    @patch("src.service.task_service.load_workflow_state")
    def test_task_not_found(self, mock_load):
        mock_load.return_value = None

        with self.assertRaisesRegex(ValueError, "未找到任务"):
            retry_task("task_missing")

    @patch("src.service.task_service.load_workflow_state")
    def test_only_rejected_task_can_retry(self, mock_load):
        self.original_state["status"] = "failed"
        mock_load.return_value = self.original_state

        with self.assertRaisesRegex(ValueError, "不允许重新尝试"):
            retry_task("task_old")

    @patch("src.service.task_service.load_workflow_state")
    def test_missing_conversation_id(self, mock_load):
        self.original_state["conversation_id"] = None
        mock_load.return_value = self.original_state

        with self.assertRaisesRegex(ValueError, "缺少 conversation_id"):
            retry_task("task_old")

    @patch("src.service.task_service.run_workflow")
    @patch("src.service.task_service.load_workflow_state")
    def test_retry_creates_new_task(self, mock_load, mock_run):
        mock_load.return_value = self.original_state
        mock_run.side_effect = lambda state: state

        result = retry_task("task_old")

        # 新旧任务 ID 不同
        self.assertNotEqual(
            result["task_id"],
            self.original_state["task_id"]
        )

        # 原始问题和对话 ID 保留
        self.assertEqual(
            result["question"],
            self.original_state["question"]
        )
        self.assertEqual(
            result["conversation_id"],
            self.original_state["conversation_id"]
        )

        # 新任务的执行状态必须是干净的
        self.assertIsNone(result["task_type"])
        self.assertIsNone(result["resolved_question"])
        self.assertIsNone(result["sql"])
        self.assertFalse(result["sql_approved"])
        self.assertIsNone(result["query_results"])

        # 新工作流确实被启动
        mock_run.assert_called_once()

        # 原任务内容没有被修改
        self.assertEqual(
            self.original_state["status"],
            "rejected"
        )
        self.assertEqual(
            self.original_state["sql"],
            "SELECT * FROM invalid_table"
        )


if __name__ == "__main__":
    unittest.main()
