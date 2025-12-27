"""
Database session management module.

Contains the DatabaseSessionManager class for handling database connections
and session management using SQLAlchemy.
"""

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from src.core.exceptions import DatabaseError
from src.infrastructure.database.models import Base

logger = logging.getLogger(__name__)


class DatabaseSessionManager:
    """数据库会话管理器"""

    def __init__(self, db_path: str = None):
        """
        Initialize the database session manager.

        Args:
            db_path: Path to the SQLite database file.
                     If not provided, uses DB_PATH env var or defaults to 'anime_downloader.db'.
        """
        # 优先使用环境变量，然后是传入的路径，最后是默认路径
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = os.getenv('DB_PATH', 'anime_downloader.db')

        # 确保数据库目录存在
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self.engine = create_engine(
            f'sqlite:///{self.db_path}',
            echo=False,
            pool_pre_ping=True,
            connect_args={'check_same_thread': False}
        )
        self.session_factory = sessionmaker(bind=self.engine)
        self.Session = scoped_session(self.session_factory)

    def init_db(self):
        """初始化数据库表结构"""
        try:
            Base.metadata.create_all(self.engine)
            logger.info('✅ 数据库表初始化完成')
        except SQLAlchemyError as e:
            raise DatabaseError(
                f'数据库初始化失败: {str(e)}',
                context={'original_exception': str(e)}
            )

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """获取数据库会话上下文"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except IntegrityError as e:
            session.rollback()
            logger.error(f'数据完整性错误: {e}')
            raise DatabaseError(
                '数据完整性错误',
                context={'original_exception': str(e)}
            )
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f'数据库操作错误: {e}')
            raise DatabaseError(
                '数据库操作错误',
                context={'original_exception': str(e)}
            )
        except Exception as e:
            session.rollback()
            logger.error(f'未知数据库错误: {e}')
            raise DatabaseError(
                '未知数据库错误',
                context={'original_exception': str(e)}
            )
        finally:
            session.close()


# 全局数据库会话管理器实例
db_manager = DatabaseSessionManager()
