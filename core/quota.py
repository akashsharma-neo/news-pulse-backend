import logging
import sys
from datetime import datetime, timezone, timedelta

from django.conf import settings
from django.db.models import F
from django_redis import get_redis_connection
from django_redis.exceptions import ConnectionInterrupted

logger = logging.getLogger(__name__)

_IS_TEST = 'test' in sys.argv or settings.NEWSMINE_ENV == "test"


def _seconds_till_end_of_month() -> int:
    now = datetime.now(timezone.utc)
    next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int((next_month - now).total_seconds())


def _redis():
    try:
        return get_redis_connection("default")
    except Exception:
        return None


class QuotaManager:
    DEFAULT_LIMITS = {"anon": 50, "user": 200}

    @staticmethod
    def try_consume_ai_chat(identity_type: str, identity_id: str, user=None):
        if _IS_TEST:
            return True, _quota_dict(0, 999999, 999999, datetime.now(timezone.utc).strftime("%Y-%m"))

        r = _redis()
        if r is None:
            logger.warning("Redis unavailable — quota check bypassed")
            return True, _quota_dict(0, 999999, 999999, datetime.now(timezone.utc).strftime("%Y-%m"))

        now = datetime.now(timezone.utc)
        month = now.strftime("%Y-%m")
        key = f"quota:{identity_type}:{identity_id}:ai_chat:{month}"

        if identity_type == "user" and user is not None:
            limit = user.monthly_ai_chat_limit if user.monthly_ai_chat_limit > 0 else 0
            if limit == 0:
                return False, _quota_dict(0, 0, 0, month)

            existing = r.get(key)
            if existing is None:
                used = user.monthly_ai_chat_used
                if used > 0:
                    r.setnx(key, used)
                    r.expire(key, _seconds_till_end_of_month())
                used = int(r.get(key) or 0)
            else:
                used = int(existing)

            if used >= limit:
                return False, _quota_dict(used, limit, 0, month)

            new_used = r.incr(key)
            if new_used == 1:
                r.expire(key, _seconds_till_end_of_month())

            if new_used > limit:
                r.decr(key)
                return False, _quota_dict(limit, limit, 0, month)

            UserModel = user.__class__
            UserModel.objects.filter(pk=user.pk).update(
                monthly_ai_chat_used=F("monthly_ai_chat_used") + 1,
                quota_reset_at=now,
            )
            user.refresh_from_db(fields=["monthly_ai_chat_used", "quota_reset_at"])

            return True, _quota_dict(new_used, limit, limit - new_used, month)

        else:
            limit = QuotaManager.DEFAULT_LIMITS["anon"]
            new_used = r.incr(key)
            if new_used == 1:
                r.expire(key, _seconds_till_end_of_month())
            if new_used > limit:
                r.decr(key)
                return False, _quota_dict(limit, limit, 0, month)
            return True, _quota_dict(new_used, limit, limit - new_used, month)

    @staticmethod
    def get_ai_chat_quota(identity_type: str, identity_id: str, user=None):
        if _IS_TEST:
            return _quota_dict(0, 999999, 999999, datetime.now(timezone.utc).strftime("%Y-%m"))

        r = _redis()
        if r is None:
            return _quota_dict(0, 999999, 999999, datetime.now(timezone.utc).strftime("%Y-%m"))

        month = datetime.now(timezone.utc).strftime("%Y-%m")
        key = f"quota:{identity_type}:{identity_id}:ai_chat:{month}"

        if identity_type == "user" and user is not None:
            limit = user.monthly_ai_chat_limit if user.monthly_ai_chat_limit > 0 else 0
            existing = r.get(key)
            if existing is None:
                used = user.monthly_ai_chat_used
            else:
                used = int(existing)
        else:
            limit = QuotaManager.DEFAULT_LIMITS["anon"]
            existing = r.get(key)
            used = int(existing) if existing is not None else 0

        remaining = max(0, limit - used) if limit > 0 else 0
        return _quota_dict(used, limit, remaining, month)


def _quota_dict(used: int, limit: int, remaining: int, month: str):
    year, mon = month.split("-")
    last_day = _days_in_month(int(year), int(mon))
    resets_at = datetime(int(year), int(mon), last_day, 23, 59, 59, tzinfo=timezone.utc).isoformat()
    return {
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "resets_at": resets_at,
    }


def _days_in_month(year: int, month: int) -> int:
    from calendar import monthrange
    return monthrange(year, month)[1]


class RateLimiter:
    @staticmethod
    def check(identity_type: str, identity_id: str, scope: str, limit: int, window_seconds: int) -> bool:
        if _IS_TEST:
            return True

        r = _redis()
        if r is None:
            return True

        now = datetime.now(timezone.utc)
        if window_seconds >= 3600:
            window_key = now.strftime("%Y%m%d%H")
        elif window_seconds >= 60:
            window_key = now.strftime("%Y%m%d%H%M")
        else:
            window_key = now.strftime("%Y%m%d%H%M%S")

        key = f"rl:{identity_type}:{identity_id}:{scope}:{window_key}"
        count = r.incr(key)
        if count == 1:
            r.expire(key, window_seconds)
        return count <= limit

    @staticmethod
    def check_ip(ip: str, scope: str, limit: int, window_seconds: int) -> bool:
        return RateLimiter.check("ip", ip, scope, limit, window_seconds)
