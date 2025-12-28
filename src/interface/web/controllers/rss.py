"""
RSS 处理控制器

处理 RSS feed 解析、过滤和处理等功能
"""
import re

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, render_template, request

from src.container import Container
from src.core.config import config
from src.infrastructure.repositories.download_repository import DownloadRepository
from src.infrastructure.repositories.history_repository import HistoryRepository
from src.interface.web.utils import (
    APIResponse,
    RequestValidator,
    ValidationRule,
    WebLogger,
    handle_api_errors,
    validate_json,
)
from src.services.download_manager import DownloadManager
from src.services.queue.rss_queue import RSSPayload, RSSQueueWorker, get_rss_queue
from src.services.rss_service import RSSService

rss_bp = Blueprint('rss', __name__)
logger = WebLogger(__name__)


def _ensure_rss_queue() -> RSSQueueWorker:
    """确保 RSS 队列已初始化"""
    return get_rss_queue()


@rss_bp.route('/rss')
def rss_page():
    """RSS处理页面"""
    template_config = {
        'fixed_rss_urls': config.rss.get_feeds()
    }
    return render_template('rss.html', config=template_config)


@rss_bp.route('/process_unified_rss', methods=['POST'])
@inject
@handle_api_errors
@validate_json('rss_url')
def process_unified_rss(
    download_manager: DownloadManager = Provide[Container.download_manager],
    history_repo: HistoryRepository = Provide[Container.history_repo]
):
    """统一的RSS处理接口"""
    data = request.get_json()
    rss_url = data.get('rss_url', '').strip()
    blocked_keywords = data.get('blocked_keywords', '').strip()
    blocked_regex = data.get('blocked_regex', '').strip()
    is_manual_mode = data.get('is_manual_mode', False)

    if not rss_url:
        return APIResponse.bad_request('RSS链接不能为空')

    logger.api_request(f"处理RSS - URL:{rss_url}, 手动模式:{is_manual_mode}")

    # 确保队列已初始化
    worker = _ensure_rss_queue()

    # 如果是手动模式，需要检查额外的参数
    if is_manual_mode:
        short_title = data.get('short_title', '').strip()
        subtitle_group = data.get('subtitle_group', '').strip()
        season = data.get('season', 1)
        category = data.get('category', 'tv')
        media_type = data.get('media_type', 'anime')

        if not short_title:
            return APIResponse.bad_request('手动模式下，动漫短标题不能为空')

        # 验证参数
        validation_rules = {
            'season': ValidationRule(required=True, min_value=1, max_value=100),
            'category': ValidationRule(required=True, choices=['tv', 'movie']),
            'media_type': ValidationRule(required=True, choices=['anime', 'live_action'])
        }

        error = RequestValidator.validate(data, validation_rules)
        if error:
            return APIResponse.bad_request(error)

        # 先创建历史记录，状态为 queued
        history_id = history_repo.insert_rss_history(
            rss_url=rss_url,
            triggered_by='手动添加',
            status='queued'
        )

        # 加入队列处理
        payload = RSSPayload(
            rss_url=rss_url,
            trigger_type='手动添加',
            extra_data={
                'mode': 'manual_mode',
                'short_title': short_title,
                'subtitle_group': subtitle_group,
                'season': season,
                'category': category,
                'media_type': media_type,
                'blocked_keywords': blocked_keywords,
                'blocked_regex': blocked_regex,
                'history_id': history_id,
            }
        )
        queue_size = worker.enqueue_event(
            event_type=RSSQueueWorker.EVENT_MANUAL_CHECK,
            payload=payload
        )

        logger.api_success('/process_unified_rss', '手动模式RSS处理已加入队列')
        return APIResponse.success(
            message='手动模式RSS处理已加入队列',
            queue_len=queue_size
        )

    else:
        # 先创建历史记录，状态为 queued
        history_id = history_repo.insert_rss_history(
            rss_url=rss_url,
            triggered_by='手动添加',
            status='queued'
        )

        # AI模式，加入队列处理
        payload = RSSPayload(
            rss_url=rss_url,
            trigger_type='手动添加',
            extra_data={
                'mode': 'ai_mode',
                'blocked_keywords': blocked_keywords,
                'blocked_regex': blocked_regex,
                'history_id': history_id,
            }
        )
        queue_size = worker.enqueue_event(
            event_type=RSSQueueWorker.EVENT_MANUAL_CHECK,
            payload=payload
        )

        logger.api_success('/process_unified_rss', 'AI模式RSS处理已加入队列')
        return APIResponse.success(
            message='AI模式RSS处理已加入队列',
            queue_len=queue_size
        )


@rss_bp.route('/api/rss_history')
@inject
@handle_api_errors
def get_rss_history_api(
    history_repo: HistoryRepository = Provide[Container.history_repo]
):
    """API: 获取RSS处理历史"""
    try:
        limit = int(request.args.get('limit', 10))
    except ValueError:
        return APIResponse.bad_request("limit必须是整数")

    if limit < 1 or limit > 100:
        return APIResponse.bad_request("limit必须在1-100之间")

    logger.api_request(f"获取RSS历史 - limit:{limit}")

    # 在 session 内部处理数据转换
    from src.infrastructure.database.models import RssProcessingHistory
    from src.infrastructure.database.session import db_manager

    with db_manager.session() as session:
        history_objects = session.query(RssProcessingHistory).order_by(
            RssProcessingHistory.created_at.desc()
        ).limit(limit).all()

        # 转换为前端期望的数组格式
        history_data = []
        for h in history_objects:
            history_data.append([
                h.id,
                h.rss_url,
                h.triggered_by,
                h.items_found,
                h.items_attempted,
                h.items_processed,
                h.created_at.isoformat() + 'Z' if h.created_at else None,
                h.status,
                h.completed_at.isoformat() + 'Z' if h.completed_at else None
            ])

    logger.api_success('/api/rss_history', f"返回 {len(history_data)} 条记录")
    return APIResponse.success(history=history_data)


@rss_bp.route('/api/rss_history/<int:history_id>')
@inject
@handle_api_errors
def get_rss_history_detail_api(
    history_id: int,
    history_repo: HistoryRepository = Provide[Container.history_repo]
):
    """API: 获取RSS处理历史详情"""
    if history_id < 1:
        return APIResponse.bad_request("历史记录ID必须大于0")

    logger.api_request(f"获取RSS历史详情 - ID:{history_id}")

    from src.infrastructure.database.models import RssProcessingDetail, RssProcessingHistory
    from src.infrastructure.database.session import db_manager

    with db_manager.session() as session:
        history = session.query(RssProcessingHistory).filter_by(id=history_id).first()

        if not history:
            logger.api_error_msg(f'/api/rss_history/{history_id}', '历史记录不存在')
            return APIResponse.not_found('历史记录不存在')

        details = session.query(RssProcessingDetail).filter_by(history_id=history_id).all()

        # 转换为前端期望的数组格式
        history_array = [
            history.id,
            history.rss_url,
            history.triggered_by,
            history.items_found,
            history.items_attempted,
            history.items_processed,
            history.created_at.isoformat() + 'Z' if history.created_at else None,
            history.status,
            history.completed_at.isoformat() + 'Z' if history.completed_at else None
        ]

        # 定义状态排序优先级: 成功 > 已存在 > 被中断 > 其他
        status_priority = {
            'success': 0,
            'exists': 1,
            'interrupted': 2,
            'filtered': 3,
            'failed': 4,
            'error': 5
        }

        # 转换详情为数组格式
        details_list = []
        for d in details:
            details_list.append([
                d.id,
                d.item_title,
                d.item_status,
                d.failure_reason
            ])

        # 按状态优先级排序
        details_list.sort(key=lambda x: status_priority.get(x[2], 99))

    logger.api_success(f'/api/rss_history/{history_id}', f"返回 {len(details_list)} 条详情")
    return APIResponse.success(
        history=history_array,
        details=details_list
    )


@rss_bp.route('/api/rss_history/<int:history_id>/delete', methods=['POST'])
@inject
@handle_api_errors
def delete_rss_history_api(
    history_id: int,
    history_repo: HistoryRepository = Provide[Container.history_repo]
):
    """API: 删除RSS处理历史记录"""
    if history_id < 1:
        return APIResponse.bad_request("历史记录ID必须大于0")

    logger.api_request(f"删除RSS历史 - ID:{history_id}")

    success = history_repo.delete_rss_processing_history(history_id)

    if success:
        logger.api_success(f'/api/rss_history/{history_id}/delete')
        return APIResponse.success(message='历史记录已删除')
    else:
        return APIResponse.not_found('历史记录不存在')


@rss_bp.route('/api/refresh_all_rss', methods=['POST'])
@inject
@handle_api_errors
def refresh_all_rss_api(
    download_manager: DownloadManager = Provide[Container.download_manager]
):
    """API: 立即刷新所有配置的RSS"""
    # 获取配置中的所有RSS Feeds
    rss_feeds = config.rss.get_feeds()

    if not rss_feeds:
        return APIResponse.bad_request('没有配置RSS链接')

    logger.api_request(f"刷新所有RSS配置 - {len(rss_feeds)} 个链接")

    # 确保队列已初始化
    worker = _ensure_rss_queue()

    # 将每个 RSS feed 单独加入队列，这样可以看到每个的处理进度
    for feed in rss_feeds:
        feed_data = {
            "url": feed.url,
            "blocked_keywords": feed.blocked_keywords,
            "blocked_regex": feed.blocked_regex,
            "media_type": feed.media_type,
        }
        payload = RSSPayload(
            rss_url=feed.url,
            trigger_type='立即刷新',
            extra_data={"feed_data": feed_data, "triggered_by": "WebUI刷新全部"}
        )
        worker.enqueue_event(
            event_type="single_feed",
            payload=payload
        )

    logger.api_success('/api/refresh_all_rss', f"已加入队列 {len(rss_feeds)} 个RSS")
    return APIResponse.success(
        message=f'已将 {len(rss_feeds)} 个RSS链接加入处理队列',
        queue_len=worker.get_queue_size()
    )


@rss_bp.route('/api/preview_filters', methods=['POST'])
@inject
@handle_api_errors
@validate_json('rss_url')
def preview_filters_api(
    rss_service: RSSService = Provide[Container.rss_service],
    download_repo: DownloadRepository = Provide[Container.download_repo]
):
    """API: 预览RSS过滤器效果"""
    data = request.get_json()
    rss_url = data.get('rss_url', '').strip()
    blocked_keywords = data.get('blocked_keywords', '').strip()
    blocked_regex = data.get('blocked_regex', '').strip()

    if not rss_url:
        return APIResponse.bad_request('请输入RSS链接')

    logger.api_request(f"预览过滤器 - RSS:{rss_url}")

    # 解析屏蔽词和正则表达式
    keyword_filters = []
    if blocked_keywords.strip():
        keyword_filters = [kw.strip() for kw in blocked_keywords.split('\n') if kw.strip()]

    regex_filters = []
    if blocked_regex.strip():
        for pattern in blocked_regex.split('\n'):
            pattern = pattern.strip()
            if pattern:
                try:
                    regex_filters.append(re.compile(pattern))
                except re.error as e:
                    return APIResponse.bad_request(f'无效的正则表达式: {pattern} - {e}')

    # 解析RSS feed
    logger.db_query("解析RSS", rss_url)
    rss_items = rss_service.parse_feed(rss_url)

    if not rss_items:
        return APIResponse.bad_request('无法解析RSS feed或feed为空')

    # 批量提取缺失的 hash (并行 + 缓存)
    url_to_hash = rss_service.batch_extract_hashes(
        rss_items,
        skip_slow_fetch=False  # 预览时也获取需要下载的 hash
    )

    # 应用过滤器
    results = []
    stats = {
        'total': len(rss_items),
        'passed': 0,
        'filtered': 0,
        'new': 0
    }

    for item in rss_items:
        title = item.title
        hash_id = item.hash

        # 如果 hash 为空，从批量提取结果中获取
        if not hash_id:
            effective_url = item.torrent_url or item.link
            if effective_url:
                hash_id = url_to_hash.get(effective_url, '')

        # 检查是否已在数据库中
        exists_in_db = False
        if hash_id:
            existing = download_repo.get_download_status_by_hash(hash_id)
            exists_in_db = existing is not None

        # 检查是否被过滤
        should_skip = False
        skip_reason = ""

        # 检查关键词过滤
        for keyword in keyword_filters:
            if keyword.lower() in title.lower():
                should_skip = True
                skip_reason = f"匹配屏蔽词: {keyword}"
                break

        # 检查正则表达式过滤
        if not should_skip:
            for regex in regex_filters:
                if regex.search(title):
                    should_skip = True
                    skip_reason = f"匹配正则表达式: {regex.pattern}"
                    break

        # 确定最终状态
        if should_skip:
            status = 'filtered'
            stats['filtered'] += 1
        elif exists_in_db:
            status = 'exists'
            stats['new'] += 1
        else:
            status = 'passed'
            stats['passed'] += 1
            stats['new'] += 1

        results.append({
            'title': title,
            'status': status,
            'reason': skip_reason
        })

    logger.api_success(
        '/api/preview_filters',
        f"总数:{stats['total']}, 通过:{stats['passed']}, 过滤:{stats['filtered']}"
    )

    return APIResponse.success(
        results=results,
        stats=stats
    )


@rss_bp.route('/api/fetch_all_bangumi_rss', methods=['POST'])
@inject
@handle_api_errors
def fetch_all_bangumi_rss_api(
    rss_service: RSSService = Provide[Container.rss_service],
    download_manager: DownloadManager = Provide[Container.download_manager],
    history_repo: HistoryRepository = Provide[Container.history_repo],
    rss_notifier = Provide[Container.discord_notifier]
):
    """API: 从配置的RSS链接中提取所有番组RSS (仅支持Mikan)"""
    import requests
    from bs4 import BeautifulSoup

    from src.core.config import RSSFeed
    from src.core.interfaces.notifications import RSSNotification

    # 获取配置中的所有RSS Feeds
    rss_feeds = config.rss.get_feeds()

    if not rss_feeds:
        return APIResponse.bad_request('没有配置RSS链接')

    # Filter to only include Mikan RSS feeds
    mikan_feeds = []
    skipped_feeds = []
    for feed in rss_feeds:
        if 'mikanani.me' in feed.url or 'mikan.me' in feed.url:
            mikan_feeds.append(feed)
        else:
            skipped_feeds.append(feed.url)

    if skipped_feeds:
        logger.info(f'⚠️ 跳过非Mikan RSS链接: {len(skipped_feeds)} 个')
        for url in skipped_feeds:
            logger.debug(f'  - 跳过: {url}')

    if not mikan_feeds:
        return APIResponse.bad_request(
            '没有配置Mikan RSS链接。"获取所有"功能仅支持 mikanani.me 的RSS链接。'
        )

    logger.api_request(f"提取番组RSS - {len(mikan_feeds)} 个Mikan源 (跳过 {len(skipped_feeds)} 个非Mikan源)")
    logger.processing_start(f"从 {len(mikan_feeds)} 个Mikan RSS链接中提取番组信息")

    # 立即创建历史记录，让用户知道命令已被执行
    batch_history_id = history_repo.insert_rss_history(
        rss_url='batch://获取所有番组 (处理中...)',
        triggered_by='获取所有'
    )

    # 存储所有提取的番组RSS链接
    bangumi_feed_mapping = {}  # {parent_feed_index: {feed, episode_links, bangumi_rss}}
    episode_links = []

    # 1. 从所有Mikan RSS链接中提取Episode链接
    for feed_idx, feed in enumerate(mikan_feeds):
        try:
            rss_url = feed.url
            logger.db_query("解析RSS", rss_url)
            rss_items = rss_service.parse_feed(rss_url)

            feed_episode_links = []
            for item in rss_items:
                link = item.link if hasattr(item, 'link') else item.get('link', '')
                # 检查是否是Episode链接格式
                if link and '/Home/Episode/' in link:
                    feed_episode_links.append(link)

            # 记录该feed对应的episode链接
            if feed_episode_links:
                bangumi_feed_mapping[feed_idx] = {
                    'feed': feed,
                    'episode_links': feed_episode_links,
                    'bangumi_rss': []
                }
                episode_links.extend(feed_episode_links)
        except Exception as e:
            logger.processing_error(f"解析RSS {feed.url}", e)
            continue

    logger.processing_success(f"共找到 {len(episode_links)} 个Episode链接")

    if not episode_links:
        # 更新历史记录为失败
        history_repo.update_rss_history_stats(
            batch_history_id,
            items_found=0,
            items_attempted=0,
            status='completed'
        )
        history_repo.update_rss_history_url(
            batch_history_id,
            'batch://获取所有番组 (0 个 - 无Episode链接)'
        )
        return APIResponse.bad_request('未找到任何Episode链接')

    # 2. 访问每个Episode页面提取番组ID和字幕组ID
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    # 为每个episode链接找到其对应的父feed
    for feed_idx, mapping in bangumi_feed_mapping.items():
        for episode_url in mapping['episode_links']:
            try:
                response = session.get(episode_url, timeout=10)

                if response.status_code != 200:
                    continue

                # 使用BeautifulSoup解析HTML
                soup = BeautifulSoup(response.text, 'html.parser')

                # 查找包含番组信息的div元素
                poster_div = soup.find('div', class_='bangumi-poster')

                if not poster_div:
                    continue

                onclick_attr = poster_div.get('onclick', '')

                # 从onclick属性中提取番组ID和字幕组ID
                match = re.search(r'/Home/Bangumi/(\d+)#(\d+)', onclick_attr)

                if match:
                    bangumi_id = match.group(1)
                    subgroup_id = match.group(2)

                    # 生成标准RSS链接
                    bangumi_rss_url = (
                        f"https://mikanani.me/RSS/Bangumi?"
                        f"bangumiId={bangumi_id}&subgroupid={subgroup_id}"
                    )

                    # 添加到对应的父feed的bangumi_rss列表中
                    if bangumi_rss_url not in mapping['bangumi_rss']:
                        mapping['bangumi_rss'].append(bangumi_rss_url)

            except Exception as e:
                logger.processing_error(f"处理Episode页面 {episode_url}", e)
                continue

    # 3. 创建带有继承过滤规则的RSSFeed对象列表
    bangumi_rss_feeds = []
    for feed_idx, mapping in bangumi_feed_mapping.items():
        parent_feed = mapping['feed']
        for bangumi_url in mapping['bangumi_rss']:
            # 创建新的RSSFeed对象，继承父feed的过滤规则和media_type
            bangumi_feed = RSSFeed(
                url=bangumi_url,
                blocked_keywords=parent_feed.blocked_keywords,
                blocked_regex=parent_feed.blocked_regex,
                media_type=parent_feed.media_type
            )
            bangumi_rss_feeds.append(bangumi_feed)

    logger.processing_success(
        f"共生成 {len(bangumi_rss_feeds)} 个番组RSS链接（已继承过滤规则）"
    )

    if not bangumi_rss_feeds:
        # 更新历史记录为完成（无结果）
        history_repo.update_rss_history_stats(
            batch_history_id,
            items_found=0,
            items_attempted=0,
            status='completed'
        )
        history_repo.update_rss_history_url(
            batch_history_id,
            'batch://获取所有番组 (0 个 - 无番组RSS)'
        )
        return APIResponse.bad_request('未能生成任何番组RSS链接')

    # 4. 更新历史记录URL为实际数量
    history_repo.update_rss_history_url(
        batch_history_id,
        f'batch://获取所有番组 ({len(bangumi_rss_feeds)} 个)'
    )

    # 5. 发送批处理开始通知
    try:
        rss_notifier.notify_processing_start(
            RSSNotification(
                trigger_type='获取所有',
                rss_url=f'批量处理 {len(bangumi_rss_feeds)} 个番组RSS'
            )
        )
    except Exception as e:
        logger.warning(f'⚠️ 发送RSS开始通知失败: {e}')

    # 6. 确保队列已初始化，将每个番组RSS加入队列
    worker = _ensure_rss_queue()

    for idx, feed in enumerate(bangumi_rss_feeds):
        feed_data = {
            "url": feed.url,
            "blocked_keywords": feed.blocked_keywords,
            "blocked_regex": feed.blocked_regex,
            "media_type": feed.media_type,
        }
        payload = RSSPayload(
            rss_url=feed.url,
            trigger_type='manual',
            extra_data={
                "feed_data": feed_data,
                "triggered_by": "获取所有番组",
                "batch_history_id": batch_history_id,
                "batch_total": len(bangumi_rss_feeds),
                "batch_index": idx
            }
        )
        worker.enqueue_event(
            event_type="single_feed",
            payload=payload
        )

    logger.api_success(
        '/api/fetch_all_bangumi_rss',
        f"已加入队列 {len(bangumi_rss_feeds)} 个番组RSS"
    )

    # Build response message
    message = f'已将 {len(bangumi_rss_feeds)} 个番组RSS链接加入处理队列（已应用过滤规则）'
    if skipped_feeds:
        message += f'，跳过了 {len(skipped_feeds)} 个非Mikan源'

    return APIResponse.success(
        message=message,
        rss_links=[feed.url for feed in bangumi_rss_feeds],
        skipped_count=len(skipped_feeds),
        queue_len=worker.get_queue_size()
    )
