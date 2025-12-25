# -*- coding: utf-8 -*-
"""
@Time    : 2025/12/25
@Desc    : Telegram notification service
"""
from typing import List

import httpx
from loguru import logger

from settings import settings


class TelegramNotifier:
    """Telegram notification service for Epic Games collection status"""

    def __init__(self):
        self.bot_token = settings.TG_BOT_TOKEN
        self.chat_id = settings.TG_CHAT_ID
        self.message_thread_id = settings.TG_MESSAGE_THREAD_ID
        self.api_base_url = settings.TG_API_BASE_URL
        self.enabled = bool(self.bot_token and self.chat_id)

    def _send_message(self, text: str) -> bool:
        """
        Send a message to Telegram

        Args:
            text: Message text to send

        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug("Telegram notification is disabled (missing bot_token or chat_id)")
            return False

        try:
            url = f"{self.api_base_url}/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
            }

            # Add message_thread_id if provided (for topic groups)
            if self.message_thread_id:
                payload["message_thread_id"] = self.message_thread_id

            response = httpx.post(url, json=payload, timeout=10)
            response.raise_for_status()

            logger.debug(f"Telegram notification sent successfully")
            return True
        except Exception as err:
            logger.warning(f"Failed to send Telegram notification: {err}")
            return False

    def notify_login_failed(self, email: str, error_msg: str = "") -> bool:
        """
        Notify about login failure

        Args:
            email: Epic Games account email
            error_msg: Error message (optional)

        Returns:
            True if notification sent successfully
        """
        text = f"🚫 <b>Epic Games 登录失败</b>\n\n"
        text += f"账号: <code>{email}</code>\n"
        if error_msg:
            text += f"错误: {error_msg}\n"

        return self._send_message(text)

    def notify_game_claimed(self, game_title: str, success: bool, url: str = "") -> bool:
        """
        Notify about game claim status

        Args:
            game_title: Game title
            success: Whether the claim was successful
            url: Game URL (optional)

        Returns:
            True if notification sent successfully
        """
        if success:
            text = f"🎉 <b>游戏领取成功</b>\n\n"
            text += f"游戏: <b>{game_title}</b>\n"
            text += f"状态: ✅ 成功领取\n"
        else:
            text = f"⚠️ <b>游戏领取失败</b>\n\n"
            text += f"游戏: <b>{game_title}</b>\n"
            text += f"状态: ❌ 领取失败\n"

        if url:
            text += f"链接: {url}\n"

        return self._send_message(text)

    def notify_games_summary(self, claimed_games: List[str], failed_games: List[str]) -> bool:
        """
        Notify about overall game collection summary

        Args:
            claimed_games: List of successfully claimed game titles
            failed_games: List of failed game titles

        Returns:
            True if notification sent successfully
        """
        text = f"📊 <b>Epic Games 领取汇总</b>\n\n"

        if claimed_games:
            text += f"✅ <b>成功领取 ({len(claimed_games)}):</b>\n"
            for game in claimed_games:
                text += f"  • {game}\n"
            text += "\n"

        if failed_games:
            text += f"❌ <b>领取失败 ({len(failed_games)}):</b>\n"
            for game in failed_games:
                text += f"  • {game}\n"
            text += "\n"

        if not claimed_games and not failed_games:
            text += "ℹ️ 本周所有免费游戏已在库中\n"

        return self._send_message(text)


# Global notifier instance
telegram_notifier = TelegramNotifier()
