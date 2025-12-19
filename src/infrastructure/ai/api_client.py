"""
OpenAI API 客户端模块。

提供 OpenAI API 的 HTTP 通信功能。
只负责网络请求，不包含业务逻辑。
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class APIResponse:
    """
    API 响应数据类。

    Attributes:
        success: 请求是否成功
        content: 响应内容（成功时）
        error_code: HTTP 错误代码（失败时）
        error_message: 错误消息（失败时）
        response_time_ms: 响应时间（毫秒）
    """
    success: bool
    content: Optional[str] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    response_time_ms: int = 0


class OpenAIClient:
    """
    OpenAI API 客户端。

    只负责 HTTP 通信，不包含重试逻辑、Key 管理等业务逻辑。
    遵循单一职责原则 (SRP)。

    Example:
        >>> client = OpenAIClient(timeout=30)
        >>> response = client.call(
        ...     base_url='https://api.openai.com/v1',
        ...     api_key='sk-xxx',
        ...     model='gpt-4',
        ...     messages=[{'role': 'user', 'content': 'Hello'}]
        ... )
        >>> if response.success:
        ...     print(response.content)
    """

    def __init__(self, timeout: int = 30):
        """
        初始化客户端。

        Args:
            timeout: 请求超时时间（秒），默认 30 秒
        """
        self._timeout = timeout

    def call(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, Any]] = None,
        extra_params: Optional[Dict[str, Any]] = None
    ) -> APIResponse:
        """
        发送 API 请求。

        Args:
            base_url: API 基础 URL（如 https://api.openai.com/v1）
            api_key: API Key
            model: 模型名称（如 gpt-4, gpt-3.5-turbo）
            messages: 消息列表
            response_format: 响应格式设置（如 JSON mode）
            extra_params: 额外的请求参数

        Returns:
            APIResponse: 响应数据
        """
        start_time = time.time()

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        payload: Dict[str, Any] = {
            'model': model,
            'messages': messages,
            'temperature': 0.1
        }

        if response_format:
            payload['response_format'] = response_format

        if extra_params:
            payload.update(extra_params)

        url = f'{base_url}/chat/completions'

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self._timeout
            )

            response_time_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content'].strip()
                logger.debug(
                    f'🤖 API 请求成功: {model}, '
                    f'响应时间: {response_time_ms}ms'
                )
                return APIResponse(
                    success=True,
                    content=content,
                    response_time_ms=response_time_ms
                )
            else:
                error_message = self._extract_error_message(response)
                logger.warning(
                    f'⚠️ API 请求失败: {response.status_code}, '
                    f'{error_message[:100]}'
                )
                return APIResponse(
                    success=False,
                    error_code=response.status_code,
                    error_message=error_message,
                    response_time_ms=response_time_ms
                )

        except requests.Timeout:
            response_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f'❌ API 请求超时: {self._timeout}s')
            return APIResponse(
                success=False,
                error_message=f'Request timeout after {self._timeout}s',
                response_time_ms=response_time_ms
            )

        except requests.ConnectionError as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f'❌ API 连接错误: {e}')
            return APIResponse(
                success=False,
                error_message=f'Connection error: {str(e)}',
                response_time_ms=response_time_ms
            )

        except requests.RequestException as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f'❌ API 请求异常: {e}')
            return APIResponse(
                success=False,
                error_message=f'Request error: {str(e)}',
                response_time_ms=response_time_ms
            )

        except Exception as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            logger.exception(f'❌ API 未预期错误: {e}')
            return APIResponse(
                success=False,
                error_message=f'Unexpected error: {str(e)}',
                response_time_ms=response_time_ms
            )

    def _extract_error_message(self, response: requests.Response) -> str:
        """
        从响应中提取错误消息。

        Args:
            response: HTTP 响应对象

        Returns:
            错误消息字符串
        """
        try:
            error_data = response.json()
            if 'error' in error_data:
                error = error_data['error']
                if isinstance(error, dict):
                    return error.get('message', str(error))
                return str(error)
            return response.text[:500]
        except Exception:
            return response.text[:500] if response.text else f'HTTP {response.status_code}'
