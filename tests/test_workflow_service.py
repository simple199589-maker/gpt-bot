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

    def test_activation_queue_join_message_is_progress(self) -> None:
        """确保已加入队列文案会被判定为已入队状态。AI by zb"""
        result = self._service._classify_activation_message(
            action="activate_plus",
            raw_message=(
                "⏳ 你的请求已加入队列。\n"
                "• 排队位置：第 108 位\n"
                "• 预计等待：约 32 分钟\n\n"
                "请不要重复提交，开始处理后会自动通知你。\n"
                "随时点击「💰 查余额/进度」可查看实时排队进度。"
            ),
        )

        self.assertEqual(result, "progress")
        progress_result = self._service._build_progress_result(
            action="activate_plus",
            raw_message=(
                "⏳ 你的请求已加入队列。\n"
                "• 排队位置：第 108 位\n"
                "• 预计等待：约 32 分钟"
            ),
        )
        self.assertEqual(progress_result.status, "queued")

    def test_activation_existing_queue_task_message_is_progress(self) -> None:
        """确保已有排队任务文案会被判定为已存在排队任务状态。AI by zb"""
        result = self._service._classify_activation_message(
            action="activate_plus",
            raw_message=(
                "你已经有一个任务在队列中。\n"
                "• 当前状态：排队中\n"
                "• 排队位置：第 103 位\n\n"
                "请等待完成后再提交新的请求。"
            ),
        )

        self.assertEqual(result, "progress")
        progress_result = self._service._build_progress_result(
            action="activate_plus",
            raw_message="你已经有一个任务在队列中。\n• 当前状态：排队中",
        )
        self.assertEqual(progress_result.status, "already_queued")

    def test_activation_queue_full_message_returns_queue_full_status(self) -> None:
        """确保队列已满文案会被细分为 queue_full。AI by zb"""
        result = self._service._classify_activation_message(
            action="activate_plus",
            raw_message=(
                "⏸️ Plus直充队列已满（67人），暂时无法接受新请求。\n\n"
                "系统会在队列降到 50 人以下时自动恢复。\n"
                "你可以稍后再试，或点击「💰 查余额/进度」查看当前状态。"
            ),
        )

        self.assertIsInstance(result, WorkflowResult)
        self.assertFalse(result.success)
        self.assertEqual(result.status, "queue_full")


class BalanceExtractionTests(unittest.TestCase):
    """验证余额与进度文案中的额度提取逻辑。AI by zb"""

    def setUp(self) -> None:
        """初始化测试所需的工作流服务实例。AI by zb"""
        self._service = BotWorkflowService(
            telegram_service=None,
            config=copy.deepcopy(DEFAULT_CONFIG),
        )

    def test_extract_balance_from_balance_progress_message(self) -> None:
        """确保新“查余额/进度”文案能提取额度余额。AI by zb"""
        raw_message = (
            "💰 额度余额：6 点\n"
            "📊 累计直充成功：29 次\n\n"
            "🎟 每日直充上限\n"
            "• 今日已成功：1/2 次\n"
            "• 额外直充次数：2 次\n\n"
            "📋 你的队列任务\n"
            "• 类型：Plus直充\n"
            "• 当前状态：排队中\n"
            "• 排队位置：第 96 位\n"
            "• 前方还有 95 人\n"
            "• 预计等待：约 29 分钟\n\n"
            "📈 当前队列\n"
            "• Plus 队列：110 人\n"
            "• Pro 队列：0 人"
        )

        balance = self._service._extract_balance(raw_message)

        self.assertEqual(balance, 6)

    def test_extract_balance_from_legacy_balance_message(self) -> None:
        """确保旧格式余额文案仍然可以提取。AI by zb"""
        balance = self._service._extract_balance("余额：12")

        self.assertEqual(balance, 12)
