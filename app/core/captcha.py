"""
CAPTCHA Service - Simple math-based CAPTCHA for login protection.

This provides a server-side CAPTCHA without external dependencies.
For production, consider integrating reCAPTCHA or hCaptcha.

Features:
- Math-based challenge (e.g., "5 + 3 = ?")
- Session-based verification
- Configurable complexity
- Rate-limited generation
"""
import random
import secrets
from typing import Tuple, Optional
from app.core.redis_pubsub import get_redis
import logging

logger = logging.getLogger(__name__)

# Configuration
CAPTCHA_EXPIRY_SECONDS = 300  # 5 minutes
CAPTCHA_KEY_PREFIX = "captcha:"


class CaptchaService:
    """
    Simple math CAPTCHA service.

    Usage:
        captcha = CaptchaService()

        # Generate challenge
        challenge_id, question = await captcha.generate(session_id)
        # Returns: ("abc123", "Berapa hasil 7 + 4?")

        # Verify answer
        is_valid = await captcha.verify(session_id, challenge_id, user_answer)
    """

    async def generate(self, session_id: str = None) -> Tuple[str, str, str]:
        """
        Generate a new CAPTCHA challenge.

        Args:
            session_id: Optional session identifier

        Returns:
            (challenge_id, question_text, expected_answer)
        """
        redis = await get_redis()

        # Generate math problem
        operation = random.choice(['+', '-', 'x'])

        if operation == '+':
            a = random.randint(1, 20)
            b = random.randint(1, 20)
            answer = a + b
            question = f"Berapa hasil {a} + {b}?"
        elif operation == '-':
            a = random.randint(10, 30)
            b = random.randint(1, a)  # Ensure positive result
            answer = a - b
            question = f"Berapa hasil {a} - {b}?"
        else:  # multiplication
            a = random.randint(2, 10)
            b = random.randint(2, 10)
            answer = a * b
            question = f"Berapa hasil {a} x {b}?"

        # Generate challenge ID
        challenge_id = secrets.token_urlsafe(16)

        # Store in Redis
        key = f"{CAPTCHA_KEY_PREFIX}{challenge_id}"
        await redis.setex(key, CAPTCHA_EXPIRY_SECONDS, str(answer))

        # Also store session mapping if provided
        if session_id:
            session_key = f"{CAPTCHA_KEY_PREFIX}session:{session_id}"
            await redis.setex(session_key, CAPTCHA_EXPIRY_SECONDS, challenge_id)

        return challenge_id, question, str(answer)

    async def verify(
        self,
        challenge_id: str,
        user_answer: str,
        delete_after_verify: bool = True
    ) -> bool:
        """
        Verify CAPTCHA answer.

        Args:
            challenge_id: The challenge ID from generate()
            user_answer: User's answer
            delete_after_verify: Delete challenge after verification (prevent reuse)

        Returns:
            True if answer is correct
        """
        redis = await get_redis()
        key = f"{CAPTCHA_KEY_PREFIX}{challenge_id}"

        stored_answer = await redis.get(key)

        if not stored_answer:
            return False  # Challenge expired or invalid

        # Handle both bytes and str (Redis may return either)
        if isinstance(stored_answer, bytes):
            stored_answer = stored_answer.decode()

        is_correct = stored_answer.strip() == str(user_answer).strip()

        if delete_after_verify:
            await redis.delete(key)

        return is_correct

    async def get_for_session(self, session_id: str) -> Optional[str]:
        """Get current challenge ID for a session."""
        redis = await get_redis()
        session_key = f"{CAPTCHA_KEY_PREFIX}session:{session_id}"

        challenge_id = await redis.get(session_key)
        return challenge_id.decode() if challenge_id else None

    async def invalidate(self, challenge_id: str):
        """Invalidate a challenge."""
        redis = await get_redis()
        key = f"{CAPTCHA_KEY_PREFIX}{challenge_id}"
        await redis.delete(key)


# For external CAPTCHA services (reCAPTCHA, hCaptcha)
class ExternalCaptchaConfig:
    """
    Configuration for external CAPTCHA providers.

    Supported:
    - Google reCAPTCHA v2/v3
    - hCaptcha
    - Cloudflare Turnstile
    """

    def __init__(
        self,
        provider: str = "none",  # none, recaptcha, hcaptcha, turnstile
        site_key: str = "",
        secret_key: str = "",
        verify_url: str = ""
    ):
        self.provider = provider
        self.site_key = site_key
        self.secret_key = secret_key
        self.verify_url = verify_url or self._default_verify_url()

    def _default_verify_url(self) -> str:
        urls = {
            "recaptcha": "https://www.google.com/recaptcha/api/siteverify",
            "hcaptcha": "https://hcaptcha.com/siteverify",
            "turnstile": "https://challenges.cloudflare.com/turnstile/v0/siteverify"
        }
        return urls.get(self.provider, "")

    @property
    def is_enabled(self) -> bool:
        return self.provider != "none" and self.site_key and self.secret_key


async def verify_external_captcha(
    config: ExternalCaptchaConfig,
    token: str,
    remote_ip: str = None
) -> bool:
    """
    Verify external CAPTCHA token.

    Usage:
        config = ExternalCaptchaConfig(
            provider="recaptcha",
            site_key="...",
            secret_key="..."
        )
        is_valid = await verify_external_captcha(config, user_token)
    """
    if not config.is_enabled:
        return True  # Skip if not configured

    import aiohttp

    data = {
        "secret": config.secret_key,
        "response": token
    }
    if remote_ip:
        data["remoteip"] = remote_ip

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(config.verify_url, data=data) as resp:
                result = await resp.json()
                return result.get("success", False)
    except Exception as e:
        logger.error(f"CAPTCHA verification failed: {e}")
        return False


# Singleton
_captcha_instance = None

def get_captcha() -> CaptchaService:
    """Get singleton CAPTCHA service."""
    global _captcha_instance
    if _captcha_instance is None:
        _captcha_instance = CaptchaService()
    return _captcha_instance
