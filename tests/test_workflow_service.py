import copy
import unittest

from app_config import DEFAULT_CONFIG
from workflow_service import BotWorkflowService, WorkflowResult


class ActivationClassificationTests(unittest.TestCase):
    """验证激活流程终态文案分类逻辑。AI by zb"""

    def setUp(self) -> None:
        """初始化测试所需的工作流服务实例。AI by zb"""
        self._service = BotWorkflowService(
            telegram_service=None,
            config=copy.deepcopy(DEFAULT_CONFIG),
        )

    def test_activation_failure_message_with_not_success_is_failed(self) -> None:
        """确保包含“未成功”的失败终态不会被误判为成功。AI by zb"""
        result = self._service._classify_activation_message(
            action="activate_team",
            raw_message="多次尝试后仍未成功，额度已退回。 | 任务 T-8aad2e40",
        )

        self.assertIsInstance(result, WorkflowResult)
        self.assertFalse(result.success)
        self.assertEqual(result.status, "invalid_access_token")

    def test_activation_success_message_still_returns_success(self) -> None:
        """确保正常成功文案仍然返回成功终态。AI by zb"""
        result = self._service._classify_activation_message(
            action="activate_team",
            raw_message="升级成功，额度已扣除。",
        )

        self.assertIsInstance(result, WorkflowResult)
        self.assertTrue(result.success)
        self.assertEqual(result.status, "success")

    def test_activation_success_message_with_task_summary_is_success(self) -> None:
        """确保带任务编号与剩余额度的激活成功文案仍会判定为成功。AI by zb"""
        result = self._service._classify_activation_message(
            action="activate_team",
            raw_message=(
                "✅ 激活成功\n"
                "任务 T-1f7cfd16 · 耗时 31.6s\n"
                "这是第 28764 次成功\n"
                "剩余 6 点额度"
            ),
        )

        self.assertIsInstance(result, WorkflowResult)
        self.assertTrue(result.success)
        self.assertEqual(result.status, "success")
