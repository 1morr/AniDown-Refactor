"""
数据库查看控制器

处理数据库表查看、SQL 执行等功能
"""
from flask import Blueprint, render_template, request
from dependency_injector.wiring import inject, Provide
import time
from datetime import datetime, timezone
from sqlalchemy import text, inspect

from src.container import Container
from src.infrastructure.database.session import DatabaseSessionManager
from src.infrastructure.database.models import SqlQueryHistory
from src.interface.web.utils import (
    APIResponse,
    handle_api_errors,
    validate_json,
    WebLogger
)

database_bp = Blueprint('database', __name__)
logger = WebLogger(__name__)


@database_bp.route('/database')
@inject
def database_page(
    db_manager: DatabaseSessionManager = Provide[Container.db_manager]
):
    """数据库查看页面"""
    return render_template('database.html')


@database_bp.route('/api/table_data')
@inject
@handle_api_errors
def get_table_data_api(
    db_manager: DatabaseSessionManager = Provide[Container.db_manager]
):
    """API: 获取表格数据（支持分页、搜索、排序）或表格计数"""
    table_name = request.args.get('table', 'anime_info')

    # 如果请求的是计数信息
    if table_name == 'counts':
        logger.api_request("获取所有表计数")
        counts = _get_all_table_counts(db_manager)
        logger.api_success('/api/table_data', f"返回 {len(counts)} 个表的计数")
        return APIResponse.success(counts=counts)

    # 验证分页参数
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
    except ValueError:
        return APIResponse.bad_request("页码和每页数量必须是整数")

    if page < 1 or per_page < 1:
        return APIResponse.bad_request("页码和每页数量必须大于0")
    if per_page > 100:
        return APIResponse.bad_request("每页最多100条记录")

    search = request.args.get('search', '').strip()
    sort_column = request.args.get('sort_column', '')
    sort_order = request.args.get('sort_order', 'desc')

    if sort_order not in ['asc', 'desc']:
        sort_order = 'desc'

    logger.api_request(f"获取表数据 - 表:{table_name}, 页码:{page}")

    result = _get_table_data_paginated(
        db_manager,
        table_name=table_name,
        page=page,
        per_page=per_page,
        search=search,
        sort_column=sort_column,
        sort_order=sort_order
    )

    if 'error' in result:
        logger.api_error_msg('/api/table_data', result['error'])
        return APIResponse.internal_error(result['error'])

    logger.api_success('/api/table_data', f"返回 {len(result['data'])} 条记录")
    # 解包result字典，避免双重嵌套data
    return APIResponse.success(**result)


@database_bp.route('/api/execute_sql', methods=['POST'])
@inject
@handle_api_errors
@validate_json('query')
def execute_sql_api(
    db_manager: DatabaseSessionManager = Provide[Container.db_manager]
):
    """API: 执行SQL查询"""
    data = request.get_json()
    sql_query = data.get('query', '').strip()

    if not sql_query:
        return APIResponse.bad_request('请输入SQL执行语句')

    logger.api_request(f"执行SQL - 类型:{_detect_query_type(sql_query)}")

    # 记录开始时间
    start_time = time.time()

    # 检查是否为SELECT查询（只读查询）
    is_select = sql_query.strip().upper().startswith('SELECT')

    try:
        with db_manager.engine.connect() as conn:
            result = conn.execute(text(sql_query))
            execution_time = time.time() - start_time

            if is_select:
                columns = list(result.keys())
                rows = [list(row) for row in result.fetchall()]
                row_count = len(rows)

                # 识别时间列并转换为 datetime 对象
                time_column_indices = [
                    i for i, col in enumerate(columns)
                    if col.lower().endswith('_at') or 'time' in col.lower()
                ]

                for row in rows:
                    for idx in time_column_indices:
                        if row[idx] is not None and row[idx] != '':
                            try:
                                dt_str = str(row[idx])
                                if '.' in dt_str:
                                    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S.%f")
                                else:
                                    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                                dt = dt.replace(tzinfo=timezone.utc)
                                row[idx] = dt
                            except (ValueError, TypeError):
                                pass

                # 保存到历史记录
                _save_sql_history(
                    db_manager, sql_query, 'select', execution_time, row_count, True, None
                )

                logger.api_success(
                    '/api/execute_sql',
                    f"SELECT查询成功 - {row_count}行, {execution_time:.3f}秒"
                )

                return APIResponse.success(
                    type='select',
                    columns=columns,
                    data=rows,
                    row_count=row_count,
                    execution_time=execution_time
                )
            else:
                # 非SELECT查询需要提交
                conn.commit()
                row_count = result.rowcount

                # 保存到历史记录
                query_type = _detect_query_type(sql_query)
                _save_sql_history(
                    db_manager, sql_query, query_type, execution_time, row_count, True, None
                )

                logger.api_success(
                    '/api/execute_sql',
                    f"{query_type.upper()}查询成功 - {row_count}行, {execution_time:.3f}秒"
                )

                return APIResponse.success(
                    type='modification',
                    message=f'SQL执行成功，受影响行数: {row_count}',
                    row_count=row_count,
                    execution_time=execution_time
                )
    except Exception as e:
        execution_time = time.time() - start_time
        query_type = _detect_query_type(sql_query)
        _save_sql_history(
            db_manager, sql_query, query_type, execution_time, 0, False, str(e)
        )
        logger.api_error_msg('/api/execute_sql', f'SQL执行错误: {str(e)}')
        return APIResponse.bad_request(f'SQL执行错误: {str(e)}')


@database_bp.route('/api/sql_history', methods=['GET'])
@inject
@handle_api_errors
def get_sql_history_api(
    db_manager: DatabaseSessionManager = Provide[Container.db_manager]
):
    """API: 获取SQL查询历史（最近10条，排除重复）"""
    logger.api_request("获取SQL历史")

    with db_manager.session() as session:
        # 获取最近10条不重复的SQL查询
        histories = session.query(SqlQueryHistory)\
            .distinct(SqlQueryHistory.query)\
            .order_by(SqlQueryHistory.created_at.desc())\
            .limit(10)\
            .all()

        result = []
        seen_queries = set()
        for history in histories:
            if history.query not in seen_queries:
                result.append({
                    'id': history.id,
                    'query': history.query,
                    'query_type': history.query_type,
                    'execution_time': history.execution_time,
                    'rows_affected': history.rows_affected,
                    'success': history.success,
                    'created_at': history.created_at
                })
                seen_queries.add(history.query)
                if len(result) >= 10:
                    break

    logger.api_success('/api/sql_history', f"返回 {len(result)} 条历史记录")
    return APIResponse.success(history=result)


@database_bp.route('/api/save_sql_history', methods=['POST'])
@inject
@handle_api_errors
@validate_json('query')
def save_sql_history_api(
    db_manager: DatabaseSessionManager = Provide[Container.db_manager]
):
    """API: 保存SQL查询历史"""
    data = request.get_json()

    query = data.get('query', '').strip()
    success = data.get('success', 1)
    rows_affected = data.get('rows_affected', 0)
    execution_time = data.get('execution_time', 0)

    if not query:
        return APIResponse.bad_request('查询语句不能为空')

    query_type = _detect_query_type(query)
    _save_sql_history(
        db_manager, query, query_type, execution_time, rows_affected, success == 1, None
    )

    logger.api_success('/api/save_sql_history', '保存成功')
    return APIResponse.success(message='保存成功')


def _get_all_table_counts(db_manager):
    """获取所有数据库表的记录数"""
    counts = {}
    try:
        with db_manager.engine.connect() as conn:
            tables = [
                'anime_info', 'anime_patterns', 'download_status',
                'hardlinks', 'torrent_files', 'rss_processing_history',
                'manual_upload_history', 'sql_query_history'
            ]

            for table_name in tables:
                try:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                    counts[table_name] = result.fetchone()[0]
                except Exception:
                    counts[table_name] = 0
        return counts
    except Exception as e:
        logger.db_error("获取表计数", e)
        return {}


def _get_table_data_paginated(
    db_manager, table_name, page=1, per_page=20,
    search='', sort_column='', sort_order='desc'
):
    """获取指定表的分页数据"""
    try:
        with db_manager.engine.connect() as conn:
            offset = (page - 1) * per_page

            # 获取表的列信息
            try:
                inspector = inspect(db_manager.engine)
                columns = [col['name'] for col in inspector.get_columns(table_name)]
            except Exception:
                # 如果无法获取列信息，使用通用查询
                result = conn.execute(text(f"SELECT * FROM {table_name} LIMIT 1"))
                columns = list(result.keys()) if result.keys() else []

            # 识别时间列
            time_columns = [
                col for col in columns
                if '_at' in col.lower() or 'time' in col.lower()
            ]
            time_column_indices = [columns.index(col) for col in time_columns]

            # 构建基础查询
            if search and columns:
                # 搜索逻辑：在所有文本列中搜索
                search_conditions = []
                for col in columns:
                    search_conditions.append(f"CAST({col} AS TEXT) LIKE '%{search}%'")
                where_clause = (
                    f" WHERE {' OR '.join(search_conditions)}"
                    if search_conditions else ""
                )
            else:
                where_clause = ""

            # 排序
            order_clause = (
                f" ORDER BY {sort_column} {sort_order}"
                if sort_column and sort_column in columns
                else " ORDER BY id DESC"
            )

            # 查询总数
            count_query = f"SELECT COUNT(*) FROM {table_name}{where_clause}"
            total_count = conn.execute(text(count_query)).fetchone()[0]

            # 查询数据
            data_query = (
                f"SELECT * FROM {table_name}{where_clause}{order_clause} "
                f"LIMIT {per_page} OFFSET {offset}"
            )
            result = conn.execute(text(data_query))
            data = [list(row) for row in result.fetchall()]

            # 转换时间字符串为 datetime 对象
            for row in data:
                for idx in time_column_indices:
                    if row[idx] is not None and row[idx] != '':
                        try:
                            dt_str = str(row[idx])
                            if '.' in dt_str:
                                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S.%f")
                            else:
                                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                            dt = dt.replace(tzinfo=timezone.utc)
                            row[idx] = dt
                        except (ValueError, TypeError):
                            pass

            return {
                'data': data,
                'columns': columns,
                'total_count': total_count,
                'total_pages': (total_count + per_page - 1) // per_page,
                'current_page': page,
                'per_page': per_page
            }
    except Exception as e:
        logger.db_error(f"获取表数据 - {table_name}", e)
        return {'error': str(e)}


def _detect_query_type(query):
    """检测SQL查询类型"""
    query_upper = query.strip().upper()
    if query_upper.startswith('SELECT'):
        return 'select'
    elif query_upper.startswith('INSERT'):
        return 'insert'
    elif query_upper.startswith('UPDATE'):
        return 'update'
    elif query_upper.startswith('DELETE'):
        return 'delete'
    elif query_upper.startswith('CREATE'):
        return 'create'
    elif query_upper.startswith('DROP'):
        return 'drop'
    elif query_upper.startswith('ALTER'):
        return 'alter'
    else:
        return 'other'


def _save_sql_history(
    db_manager, query, query_type, execution_time, rows_affected, success, error_message
):
    """保存SQL查询历史"""
    try:
        with db_manager.session() as session:
            history = SqlQueryHistory(
                query=query,
                query_type=query_type,
                execution_time=execution_time,
                rows_affected=rows_affected,
                success=1 if success else 0,
                error_message=error_message
            )
            session.add(history)
            session.commit()
    except Exception as e:
        # 如果保存历史失败，不影响主要功能
        logger.db_error("保存SQL历史", e)
