"""
qBittorrent adapter module.

Contains the QBitAdapter class implementing IDownloadClient interface
for interacting with qBittorrent Web API.
"""

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests

from src.core.config import config
from src.core.exceptions import DownloadError
from src.core.interfaces.adapters import IDownloadClient

logger = logging.getLogger(__name__)


class QBitAdapter(IDownloadClient):
    """qBittorrent 客户端适配器"""

    def __init__(self):
        self.base_url = config.qbittorrent.url.rstrip('/')
        self.username = config.qbittorrent.username
        self.password = config.qbittorrent.password
        self.session = requests.Session()
        self.cookies = None

    def _ensure_login(self) -> bool:
        """确保已登录"""
        if not self.cookies:
            return self.login()
        return True

    def login(self) -> bool:
        """登录qBittorrent"""
        if not self.username or not self.password:
            logger.warning('qBittorrent credentials not configured')
            return False

        try:
            logger.debug(f'🔑 正在登录 qBittorrent: {self.base_url}')
            login_url = urljoin(self.base_url, '/api/v2/auth/login')
            data = {'username': self.username, 'password': self.password}

            response = self.session.post(login_url, data=data)

            if response.status_code == 200 and response.text == 'Ok.':
                self.cookies = self.session.cookies.get_dict()
                logger.info('✅ qBittorrent 登录成功')
                return True
            else:
                logger.error(f'qBittorrent login failed: {response.status_code} - {response.text}')
                return False
        except Exception as e:
            logger.error(f'qBittorrent login exception: {e}')
            return False

    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            'Referer': self.base_url,
            'Origin': self.base_url
        }

    def _retry_on_403(self, method, url, **kwargs):
        """在收到403时重试"""
        headers = kwargs.pop('headers', {})
        headers.update(self._get_headers())
        kwargs['headers'] = headers

        response = method(url, **kwargs)

        if response.status_code == 403:
            logger.warning('Received 403, attempting to re-login and retry...')
            self.cookies = None
            if self.login():
                response = method(url, **kwargs)
            else:
                logger.error('Re-login failed')

        return response

    # ==================== IDownloadClient Interface ====================

    def is_connected(self) -> bool:
        """检查是否已连接到下载客户端"""
        try:
            if not self._ensure_login():
                return False

            version_url = urljoin(self.base_url, '/api/v2/app/version')
            response = self.session.get(version_url)
            return response.status_code == 200
        except Exception as e:
            logger.error(f'Connection check failed: {e}')
            return False

    def add_torrent(
        self,
        torrent_url: str,
        save_path: str,
        hash_id: Optional[str] = None
    ) -> bool:
        """添加种子任务（通过URL）"""
        if not self._ensure_login():
            return False

        try:
            logger.info(f'➕ 正在添加种子到 qBittorrent...')
            logger.debug(f'  种子URL: {torrent_url[:80]}...')
            if save_path:
                logger.debug(f'  保存路径: {save_path}')

            add_url = urljoin(self.base_url, '/api/v2/torrents/add')
            params = {'urls': torrent_url}

            if save_path:
                params['savepath'] = save_path

            category = config.qbittorrent.category
            if category:
                params['category'] = category

            response = self._retry_on_403(self.session.post, add_url, data=params)

            if response.status_code == 200:
                logger.info(f'✅ 种子添加成功到 qBittorrent')
                return True
            else:
                logger.error(f'Add torrent failed: {response.status_code} - {response.text}')
                return False

        except Exception as e:
            logger.error(f'Add torrent exception: {e}')
            return False

    def add_torrent_file(self, file_path: str, save_path: str) -> Optional[str]:
        """添加种子文件"""
        if not self._ensure_login():
            return None

        try:
            add_url = urljoin(self.base_url, '/api/v2/torrents/add')

            with open(file_path, 'rb') as f:
                files = {'torrents': f}
                data = {}

                if save_path:
                    data['savepath'] = save_path

                category = config.qbittorrent.category
                if category:
                    data['category'] = category

                response = self._retry_on_403(
                    self.session.post, add_url, files=files, data=data
                )

            if response.status_code == 200:
                logger.info(f'Torrent file added successfully')
                # 从文件中提取hash
                return get_torrent_hash_from_file(file_path)
            else:
                logger.error(f'Add torrent file failed: {response.status_code} - {response.text}')
                return None

        except Exception as e:
            logger.error(f'Add torrent file exception: {e}')
            return None

    def add_magnet(self, magnet_link: str, save_path: str) -> Optional[str]:
        """添加磁力链接"""
        if not self._ensure_login():
            return None

        try:
            add_url = urljoin(self.base_url, '/api/v2/torrents/add')
            params = {'urls': magnet_link}

            if save_path:
                params['savepath'] = save_path

            category = config.qbittorrent.category
            if category:
                params['category'] = category

            response = self._retry_on_403(self.session.post, add_url, data=params)

            if response.status_code == 200:
                logger.info(f'Magnet link added successfully')
                # 从磁力链接中提取hash
                return get_torrent_hash_from_magnet(magnet_link)
            else:
                logger.error(f'Add magnet failed: {response.status_code} - {response.text}')
                return None

        except Exception as e:
            logger.error(f'Add magnet exception: {e}')
            return None

    def get_torrent_info(self, hash_id: str) -> Optional[Dict[str, Any]]:
        """获取种子信息"""
        if not self._ensure_login():
            return None

        try:
            info_url = urljoin(self.base_url, '/api/v2/torrents/info')
            params = {'hashes': hash_id}

            response = self.session.get(info_url, params=params)

            if response.status_code == 200:
                torrents = response.json()
                if torrents:
                    return torrents[0]
            return None
        except Exception as e:
            logger.error(f'Get torrent info exception: {e}')
            return None

    def get_torrent_files(self, hash_id: str) -> List[Dict[str, Any]]:
        """获取种子文件列表"""
        if not self._ensure_login():
            return []

        try:
            files_url = urljoin(self.base_url, '/api/v2/torrents/files')
            params = {'hash': hash_id}

            response = self.session.get(files_url, params=params)

            if response.status_code == 200:
                return response.json() or []
            return []
        except Exception as e:
            logger.error(f'Get torrent files exception: {e}')
            return []

    def get_torrent_progress(self, hash_id: str) -> float:
        """获取下载进度"""
        torrent_info = self.get_torrent_info(hash_id)
        if torrent_info:
            return torrent_info.get('progress', 0.0)
        return 0.0

    def delete_torrent(self, hash_id: str, delete_files: bool = False) -> bool:
        """删除种子任务"""
        if not self._ensure_login():
            return False

        try:
            delete_url = urljoin(self.base_url, '/api/v2/torrents/delete')
            params = {
                'hashes': hash_id,
                'deleteFiles': 'true' if delete_files else 'false'
            }

            response = self.session.post(delete_url, data=params)

            if response.status_code == 200:
                logger.info(f'Torrent {hash_id} deleted successfully (delete_files={delete_files})')
                return True
            else:
                logger.error(f'Delete torrent failed: {response.status_code} - {response.text}')
                return False

        except Exception as e:
            logger.error(f'Delete torrent exception: {e}')
            return False

    def pause_torrent(self, hash_id: str) -> bool:
        """暂停种子"""
        if not self._ensure_login():
            return False

        try:
            pause_url = urljoin(self.base_url, '/api/v2/torrents/pause')
            params = {'hashes': hash_id}

            response = self.session.post(pause_url, data=params)

            if response.status_code == 200:
                logger.info(f'Torrent {hash_id} paused successfully')
                return True
            else:
                logger.error(f'Pause torrent failed: {response.status_code} - {response.text}')
                return False

        except Exception as e:
            logger.error(f'Pause torrent exception: {e}')
            return False

    def resume_torrent(self, hash_id: str) -> bool:
        """恢复种子"""
        if not self._ensure_login():
            return False

        try:
            resume_url = urljoin(self.base_url, '/api/v2/torrents/resume')
            params = {'hashes': hash_id}

            response = self.session.post(resume_url, data=params)

            if response.status_code == 200:
                logger.info(f'Torrent {hash_id} resumed successfully')
                return True
            else:
                logger.error(f'Resume torrent failed: {response.status_code} - {response.text}')
                return False

        except Exception as e:
            logger.error(f'Resume torrent exception: {e}')
            return False

    # ==================== Additional Methods ====================

    def get_all_torrents(self, filter_type: str = None) -> Optional[List[Dict[str, Any]]]:
        """获取所有种子信息"""
        if not self._ensure_login():
            return None

        try:
            info_url = urljoin(self.base_url, '/api/v2/torrents/info')
            params = {}
            if filter_type:
                params['filter'] = filter_type

            response = self.session.get(info_url, params=params)

            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f'Get all torrents exception: {e}')
            return None

    def get_downloading_torrents(self) -> Optional[List[Dict[str, Any]]]:
        """获取正在下载的种子"""
        return self.get_all_torrents('downloading')

    def get_completed_torrents(self) -> Optional[List[Dict[str, Any]]]:
        """获取已完成的种子"""
        return self.get_all_torrents('completed')

    def get_torrent_folder_structure(self, hash_id: str) -> Optional[str]:
        """获取Torrent的文件夹树形结构（只包含文件夹，不包含文件）"""
        files = self.get_torrent_files(hash_id)
        if not files:
            logger.warning(f'⚠️ 未获取到torrent文件列表: {hash_id[:8]}...')
            return None

        try:
            folders = set()
            for file_info in files:
                file_path = file_info.get('name', '')
                if not file_path:
                    continue

                path_parts = file_path.replace('\\', '/').split('/')
                for i in range(1, len(path_parts)):
                    folder_path = '/'.join(path_parts[:i])
                    if folder_path:
                        folders.add(folder_path)

            if not folders:
                logger.debug(f'📁 Torrent没有子文件夹结构')
                return '（无子文件夹）'

            folder_tree = self._build_folder_tree(sorted(folders))

            logger.debug(f'📁 获取到 {len(folders)} 个文件夹')
            return folder_tree

        except Exception as e:
            logger.error(f'❌ 构建文件夹结构失败: {e}')
            return None

    def _build_folder_tree(self, folders: List[str]) -> str:
        """将文件夹路径列表转换为树形结构字符串"""
        if not folders:
            return ''

        tree_dict = {}
        for folder in folders:
            parts = folder.split('/')
            current = tree_dict
            for part in parts:
                if part not in current:
                    current[part] = {}
                current = current[part]

        lines = []
        self._format_tree(tree_dict, lines, prefix='', is_last=True)
        return '\n'.join(lines)

    def _format_tree(
        self,
        node: Dict,
        lines: List[str],
        prefix: str = '',
        is_last: bool = True
    ):
        """递归格式化树形结构"""
        items = list(node.items())
        for i, (name, children) in enumerate(items):
            is_last_item = (i == len(items) - 1)

            if is_last_item:
                current_prefix = '└── '
                child_prefix = '    '
            else:
                current_prefix = '├── '
                child_prefix = '│   '

            lines.append(f'{prefix}{current_prefix}{name}/')

            if children:
                self._format_tree(children, lines, prefix + child_prefix, is_last_item)


def get_torrent_hash_from_magnet(magnet_link: str) -> Optional[str]:
    """从磁力链接提取hash"""
    match = re.search(r'urn:btih:([a-fA-F0-9]{40})', magnet_link)
    if match:
        return match.group(1).lower()
    return None


def get_torrent_hash_from_file(torrent_file_path: str) -> Optional[str]:
    """从种子文件提取hash"""
    try:
        import bencodepy

        with open(torrent_file_path, 'rb') as f:
            torrent_data = bencodepy.decode(f.read())

        info = torrent_data[b'info']
        info_encoded = bencodepy.encode(info)
        hash_obj = hashlib.sha1(info_encoded)
        return hash_obj.hexdigest()
    except Exception as e:
        logger.error(f'Extract hash from torrent file failed: {e}')
        return None
