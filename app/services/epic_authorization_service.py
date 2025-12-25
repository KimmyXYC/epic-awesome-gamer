# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/16 22:13
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
import asyncio
import json
import time
from contextlib import suppress

import pyotp
from hcaptcha_challenger.agent import AgentV
from loguru import logger
from playwright.async_api import expect, Page, Response

from services.telegram_service import telegram_notifier
from settings import SCREENSHOTS_DIR, settings

URL_CLAIM = "https://store.epicgames.com/en-US/free-games"


class EpicAuthorization:

    def __init__(self, page: Page):
        self.page = page

        self._is_login_success_signal = asyncio.Queue()
        self._is_refresh_csrf_signal = asyncio.Queue()

    async def _on_response_anything(self, r: Response):
        if r.request.method != "POST" or "talon" in r.url:
            return

        with suppress(Exception):
            result = await r.json()
            result_json = json.dumps(result, indent=2, ensure_ascii=False)

            if "/id/api/login" in r.url and result.get("errorCode"):
                logger.error(f"{r.request.method} {r.url} - {result_json}")
            elif "/id/api/analytics" in r.url and result.get("accountId"):
                self._is_login_success_signal.put_nowait(result)
            elif "/account/v2/refresh-csrf" in r.url and result.get("success", False) is True:
                self._is_refresh_csrf_signal.put_nowait(result)
            # else:
            #     logger.debug(f"{r.request.method} {r.url} - {result_json}")

    async def _handle_right_account_validation(self):
        """
        以下验证仅会在登录成功后出现
        Returns:

        """
        await self.page.goto("https://www.epicgames.com/account/personal", wait_until="networkidle")

        btn_ids = ["#link-success", "#login-reminder-prompt-setup-tfa-skip", "#yes"]

        # == 账号长期不登录需要做的额外验证 == #

        while self._is_refresh_csrf_signal.empty() and btn_ids:
            await self.page.wait_for_timeout(500)
            action_chains = btn_ids.copy()
            for action in action_chains:
                with suppress(Exception):
                    reminder_btn = self.page.locator(action)
                    await expect(reminder_btn).to_be_visible(timeout=1000)
                    await reminder_btn.click(timeout=1000)
                    btn_ids.remove(action)

    async def _login(self) -> bool | None:
        # 尽可能早地初始化机器人
        agent = AgentV(page=self.page, agent_config=settings)

        # {{< SIGN IN PAGE >}}
        logger.debug("Login with Email")

        try:
            point_url = "https://www.epicgames.com/account/personal?lang=en-US&productName=egs&sessionInvalidated=true"
            await self.page.goto(point_url, wait_until="domcontentloaded")

            # 1. 使用电子邮件地址登录
            email_input = self.page.locator("#email")
            await email_input.clear()
            await email_input.type(settings.EPIC_EMAIL)
            logger.debug(f"Email inputted: {settings.EPIC_EMAIL}")

            #等待2秒
            await asyncio.sleep(2)

            # 2. 点击继续按钮
            await self.page.click("#continue")
            logger.debug("Continue button clicked")

            #等待2秒
            await asyncio.sleep(2)

            # 3. 输入密码
            password_input = self.page.locator("#password")
            await password_input.clear()
            await password_input.type(settings.EPIC_PASSWORD.get_secret_value())
            logger.debug("Password inputted")

            #等待2秒
            await asyncio.sleep(2)

            # 4. 点击登录按钮，触发人机挑战值守监听器
            # Active hCaptcha checkbox
            await self.page.click("#sign-in")
            logger.debug("Login button clicked")

            # 5. 处理 2FA OTP（如果启用）
            if settings.EPIC_TOTP_SECRET:
                try:
                    # 等待页面响应和OTP输入框出现
                    await asyncio.sleep(3)
                    
                    # 使用 TOTP 密钥生成验证码
                    totp = pyotp.TOTP(settings.EPIC_TOTP_SECRET)
                    otp_code = totp.now()
                    logger.debug(f"Generated OTP code: {otp_code}")
                    
                    # Epic Games 使用6个独立的输入框，每个输入框只能输入1位数字
                    # 等待第一个输入框出现
                    first_input = self.page.locator('input[name="code-input-0"]')
                    await expect(first_input).to_be_visible(timeout=15000)
                    
                    # 将6位验证码分别输入到6个输入框中
                    for i, digit in enumerate(otp_code):
                        input_locator = self.page.locator(f'input[name="code-input-{i}"]')
                        await input_locator.click()
                        await input_locator.fill(digit)
                        logger.debug(f"OTP digit {i} inputted: {digit}")
                    
                    logger.debug("All OTP digits inputted")
                    
                    # 点击继续按钮
                    await self.page.click("#continue")
                    logger.debug("OTP submitted")
                except Exception as otp_err:
                    logger.warning(f"OTP handling failed or not required: {otp_err}")

            # Active hCaptcha challenge (if present)
            try:
                await agent.wait_for_challenge()
                logger.debug("hCaptcha challenge solved")
            except Exception as captcha_err:
                logger.debug(f"No captcha challenge or captcha handling skipped: {captcha_err}")

            # Wait for the page to redirect
            await asyncio.wait_for(self._is_login_success_signal.get(), timeout=60)
            logger.success("Login success")

            await asyncio.wait_for(self._handle_right_account_validation(), timeout=60)
            logger.success("Right account validation success")
            return True
        except Exception as err:
            logger.warning(f"{err}")
            sr = SCREENSHOTS_DIR.joinpath("authorization")
            sr.mkdir(parents=True, exist_ok=True)
            await self.page.screenshot(path=sr.joinpath(f"login-{int(time.time())}.png"))
            
            # Send Telegram notification for login failure
            telegram_notifier.notify_login_failed(settings.EPIC_EMAIL, str(err))
            
            return None

    async def invoke(self):
        self.page.on("response", self._on_response_anything)

        for _ in range(3):
            await self.page.goto(URL_CLAIM, wait_until="domcontentloaded")

            if "true" == await self.page.locator("//egs-navigation").get_attribute("isloggedin"):
                logger.success("Epic Games is already logged in")
                return True

            if await self._login():
                return
