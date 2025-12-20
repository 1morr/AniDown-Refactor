"""
AI Key usage repository module.

Contains the AIKeyRepository class for managing AI API key usage logging.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError

from src.infrastructure.database.models import AIKeyDailyCount, AIKeyUsageLog
from src.infrastructure.database.session import db_manager

logger = logging.getLogger(__name__)


def _utc_date_str() -> str:
    """获取当前 UTC 日期字符串"""
    return datetime.now(timezone.utc).date().isoformat()


class AIKeyRepository:
    """AI Key 使用记录 Repository"""

    def log_usage(
        self,
        purpose: str,
        key_id: str,
        key_name: str = '',
        model: str = '',
        hash_id: str = '',
        anime_title: str = '',
        context_summary: str = '',
        success: bool = True,
        error_code: Optional[int] = None,
        error_message: str = '',
        response_time_ms: int = 0,
        rpm_at_call: int = 0,
        rpd_at_call: int = 0,
    ) -> Optional[int]:
        """
        记录一次 AI Key 使用

        Args:
            purpose: 用途 (title_parse, multi_file_rename)
            key_id: Key 的哈希 ID
            key_name: Key 名称
            model: 使用的 AI 模型名称
            hash_id: 相关 torrent 的 hash
            anime_title: 关联的动漫标题
            context_summary: 简短上下文描述
            success: 是否成功
            error_code: HTTP 错误码 (429, 403, 404 等)
            error_message: 完整错误信息
            response_time_ms: 响应时间（毫秒）
            rpm_at_call: 调用时的 RPM 计数
            rpd_at_call: 调用时的 RPD 计数

        Returns:
            新记录的 ID，失败返回 None
        """
        today = _utc_date_str()

        try:
            with db_manager.session() as session:
                # 记录使用日志
                log_entry = AIKeyUsageLog(
                    purpose=purpose,
                    key_id=key_id,
                    key_name=key_name or '',
                    model=model or '',
                    hash_id=hash_id or '',
                    anime_title=(anime_title or '')[:500],
                    context_summary=(context_summary or '')[:500],
                    success=1 if success else 0,
                    error_code=error_code,
                    error_message=(error_message or '')[:1000] if not success else '',
                    response_time_ms=response_time_ms,
                    rpm_at_call=rpm_at_call,
                    rpd_at_call=rpd_at_call,
                )
                session.add(log_entry)

                # 同步更新每日计数表（用于启动时恢复）
                daily_record = (
                    session.query(AIKeyDailyCount)
                    .filter(
                        AIKeyDailyCount.purpose == purpose,
                        AIKeyDailyCount.key_id == key_id,
                        AIKeyDailyCount.date_utc == today,
                    )
                    .first()
                )

                if daily_record:
                    daily_record.count = rpd_at_call
                else:
                    daily_record = AIKeyDailyCount(
                        purpose=purpose,
                        key_id=key_id,
                        date_utc=today,
                        count=rpd_at_call,
                    )
                    session.add(daily_record)

                session.flush()
                return log_entry.id
        except SQLAlchemyError as e:
            logger.error(f'Failed to log AI key usage: {e}')
            return None

    def get_usage_history(
        self,
        purpose: str,
        key_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        获取指定 Key 的使用历史

        Returns:
            使用记录列表
        """
        try:
            with db_manager.session() as session:
                query = (
                    session.query(AIKeyUsageLog)
                    .filter(
                        AIKeyUsageLog.purpose == purpose,
                        AIKeyUsageLog.key_id == key_id,
                    )
                    .order_by(desc(AIKeyUsageLog.created_at))
                    .limit(limit)
                    .offset(offset)
                )
                records = query.all()
                return [
                    {
                        'id': r.id,
                        'purpose': r.purpose,
                        'key_id': r.key_id,
                        'key_name': r.key_name,
                        'model': r.model,
                        'hash_id': r.hash_id,
                        'anime_title': r.anime_title,
                        'context_summary': r.context_summary,
                        'success': bool(r.success),
                        'error_code': r.error_code,
                        'error_message': r.error_message,
                        'response_time_ms': r.response_time_ms,
                        'rpm_at_call': r.rpm_at_call,
                        'rpd_at_call': r.rpd_at_call,
                        'created_at_utc': r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in records
                ]
        except SQLAlchemyError as e:
            logger.error(f'Failed to get AI key usage history: {e}')
            return []

    def get_usage_stats(
        self,
        purpose: str,
        key_id: str,
    ) -> Dict[str, Any]:
        """
        获取指定 Key 的使用统计信息

        Args:
            purpose: 用途
            key_id: Key ID

        Returns:
            包含统计信息的字典
        """
        try:
            with db_manager.session() as session:
                from sqlalchemy import func as sql_func, distinct

                # 总调用次数和成功/失败次数
                total_calls = (
                    session.query(sql_func.count(AIKeyUsageLog.id))
                    .filter(
                        AIKeyUsageLog.purpose == purpose,
                        AIKeyUsageLog.key_id == key_id,
                    )
                    .scalar() or 0
                )

                success_calls = (
                    session.query(sql_func.count(AIKeyUsageLog.id))
                    .filter(
                        AIKeyUsageLog.purpose == purpose,
                        AIKeyUsageLog.key_id == key_id,
                        AIKeyUsageLog.success == 1,
                    )
                    .scalar() or 0
                )

                failed_calls = total_calls - success_calls

                # 平均响应时间
                avg_response_time = (
                    session.query(sql_func.avg(AIKeyUsageLog.response_time_ms))
                    .filter(
                        AIKeyUsageLog.purpose == purpose,
                        AIKeyUsageLog.key_id == key_id,
                        AIKeyUsageLog.success == 1,
                    )
                    .scalar() or 0
                )

                # 使用过的动漫项目数量（去重）
                anime_count = (
                    session.query(sql_func.count(distinct(AIKeyUsageLog.anime_title)))
                    .filter(
                        AIKeyUsageLog.purpose == purpose,
                        AIKeyUsageLog.key_id == key_id,
                        AIKeyUsageLog.anime_title.isnot(None),
                        AIKeyUsageLog.anime_title != '',
                    )
                    .scalar() or 0
                )

                # 最近使用的动漫项目列表（去重，最近 10 个）
                recent_animes = (
                    session.query(
                        AIKeyUsageLog.anime_title,
                        sql_func.max(AIKeyUsageLog.created_at).label('last_used')
                    )
                    .filter(
                        AIKeyUsageLog.purpose == purpose,
                        AIKeyUsageLog.key_id == key_id,
                        AIKeyUsageLog.anime_title.isnot(None),
                        AIKeyUsageLog.anime_title != '',
                    )
                    .group_by(AIKeyUsageLog.anime_title)
                    .order_by(desc('last_used'))
                    .limit(10)
                    .all()
                )

                # 今日调用次数
                today = datetime.now(timezone.utc).date().isoformat()
                today_calls = (
                    session.query(sql_func.count(AIKeyUsageLog.id))
                    .filter(
                        AIKeyUsageLog.purpose == purpose,
                        AIKeyUsageLog.key_id == key_id,
                        sql_func.date(AIKeyUsageLog.created_at) == today,
                    )
                    .scalar() or 0
                )

                return {
                    'total_calls': total_calls,
                    'success_calls': success_calls,
                    'failed_calls': failed_calls,
                    'success_rate': round(success_calls / total_calls * 100, 1) if total_calls > 0 else 0,
                    'avg_response_time_ms': round(avg_response_time),
                    'anime_count': anime_count,
                    'today_calls': today_calls,
                    'recent_animes': [
                        {
                            'title': a.anime_title,
                            'last_used_utc': a.last_used.isoformat() if a.last_used else None
                        }
                        for a in recent_animes
                    ],
                }
        except SQLAlchemyError as e:
            logger.error(f'Failed to get AI key usage stats: {e}')
            return {
                'total_calls': 0,
                'success_calls': 0,
                'failed_calls': 0,
                'success_rate': 0,
                'avg_response_time_ms': 0,
                'anime_count': 0,
                'today_calls': 0,
                'recent_animes': [],
            }

    def get_daily_count(self, purpose: str, key_id: str, date_utc: str = None) -> int:
        """
        获取指定 Key 在指定日期的请求计数

        Args:
            purpose: 用途
            key_id: Key ID
            date_utc: UTC 日期字符串，默认为今天

        Returns:
            请求计数
        """
        if date_utc is None:
            date_utc = _utc_date_str()

        try:
            with db_manager.session() as session:
                record = (
                    session.query(AIKeyDailyCount)
                    .filter(
                        AIKeyDailyCount.purpose == purpose,
                        AIKeyDailyCount.key_id == key_id,
                        AIKeyDailyCount.date_utc == date_utc,
                    )
                    .first()
                )
                return record.count if record else 0
        except SQLAlchemyError as e:
            logger.error(f'Failed to get daily count: {e}')
            return 0

    def increment_daily_count(self, purpose: str, key_id: str, date_utc: str = None) -> int:
        """
        增加指定 Key 在指定日期的请求计数

        Args:
            purpose: 用途
            key_id: Key ID
            date_utc: UTC 日期字符串，默认为今天

        Returns:
            更新后的计数
        """
        if date_utc is None:
            date_utc = _utc_date_str()

        try:
            with db_manager.session() as session:
                record = (
                    session.query(AIKeyDailyCount)
                    .filter(
                        AIKeyDailyCount.purpose == purpose,
                        AIKeyDailyCount.key_id == key_id,
                        AIKeyDailyCount.date_utc == date_utc,
                    )
                    .first()
                )

                if record:
                    record.count += 1
                    new_count = record.count
                else:
                    record = AIKeyDailyCount(
                        purpose=purpose,
                        key_id=key_id,
                        date_utc=date_utc,
                        count=1,
                    )
                    session.add(record)
                    new_count = 1

                session.flush()
                return new_count
        except SQLAlchemyError as e:
            logger.error(f'Failed to increment daily count: {e}')
            return 0

    def get_all_daily_counts(self, date_utc: str = None) -> Dict[tuple, int]:
        """
        获取指定日期所有 Key 的请求计数

        Args:
            date_utc: UTC 日期字符串，默认为今天

        Returns:
            {(purpose, key_id): count} 字典
        """
        if date_utc is None:
            date_utc = _utc_date_str()

        try:
            with db_manager.session() as session:
                records = (
                    session.query(AIKeyDailyCount)
                    .filter(AIKeyDailyCount.date_utc == date_utc)
                    .all()
                )
                return {
                    (r.purpose, r.key_id): r.count
                    for r in records
                }
        except SQLAlchemyError as e:
            logger.error(f'Failed to get all daily counts: {e}')
            return {}

    def cleanup_old_logs(self, days_to_keep: int = 30) -> int:
        """
        清理旧的使用日志

        Args:
            days_to_keep: 保留天数

        Returns:
            删除的记录数
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
            with db_manager.session() as session:
                deleted = (
                    session.query(AIKeyUsageLog)
                    .filter(AIKeyUsageLog.created_at < cutoff)
                    .delete(synchronize_session=False)
                )
                logger.info(f'Cleaned up {deleted} old AI key usage logs')
                return deleted
        except SQLAlchemyError as e:
            logger.error(f'Failed to cleanup old logs: {e}')
            return 0

    def cleanup_old_daily_counts(self, days_to_keep: int = 7) -> int:
        """
        清理旧的每日计数记录

        Args:
            days_to_keep: 保留天数

        Returns:
            删除的记录数
        """
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).date().isoformat()
            with db_manager.session() as session:
                deleted = (
                    session.query(AIKeyDailyCount)
                    .filter(AIKeyDailyCount.date_utc < cutoff_date)
                    .delete(synchronize_session=False)
                )
                logger.info(f'Cleaned up {deleted} old AI key daily count records')
                return deleted
        except SQLAlchemyError as e:
            logger.error(f'Failed to cleanup old daily counts: {e}')
            return 0


# 全局实例
ai_key_repository = AIKeyRepository()
