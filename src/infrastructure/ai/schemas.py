"""
AI 响应 JSON Schema 模块。

定义用于 AI API 调用的响应格式 Schema。
"""

from typing import Any, Dict

# 标题解析响应格式
TITLE_PARSE_RESPONSE_FORMAT: Dict[str, Any] = {
    'type': 'json_schema',
    'json_schema': {
        'name': 'title_parse_result',
        'strict': True,
        'schema': {
            'type': 'object',
            'properties': {
                'original_title': {
                    'type': 'string',
                    'description': '原始输入标题'
                },
                'anime_clean_title': {
                    'type': 'string',
                    'description': '干净的动漫短标题（中文优先）'
                },
                'anime_full_title': {
                    'type': ['string', 'null'],
                    'description': '完整的动漫标题（多语言版本）'
                },
                'subtitle_group_name': {
                    'type': 'string',
                    'description': '字幕组名称'
                },
                'season': {
                    'type': 'integer',
                    'description': '季度数字（默认 1，电影/OVA 为 0）'
                },
                'episode': {
                    'type': ['integer', 'null'],
                    'description': '集数（合集为 null）'
                },
                'category': {
                    'type': 'string',
                    'enum': ['tv', 'movie'],
                    'description': '分类'
                },
                'quality': {
                    'type': 'string',
                    'description': '视频质量'
                },
                'codec': {
                    'type': 'string',
                    'description': '编码格式'
                },
                'source': {
                    'type': 'string',
                    'description': '来源'
                }
            },
            'required': [
                'original_title',
                'anime_clean_title',
                'anime_full_title',
                'subtitle_group_name',
                'season',
                'episode',
                'category',
                'quality',
                'codec',
                'source'
            ],
            'additionalProperties': False
        }
    }
}


# 文件重命名响应格式
FILE_RENAME_RESPONSE_FORMAT: Dict[str, Any] = {
    'type': 'json_schema',
    'json_schema': {
        'name': 'file_rename_result',
        'strict': True,
        'schema': {
            'type': 'object',
            'properties': {
                'files': {
                    'type': 'object',
                    'description': '原文件名到新文件名的映射',
                    'additionalProperties': {
                        'type': 'string'
                    }
                },
                'skipped': {
                    'type': 'array',
                    'description': '跳过的文件列表',
                    'items': {
                        'type': 'string'
                    }
                },
                'seasons': {
                    'type': 'object',
                    'description': '季度信息',
                    'additionalProperties': {
                        'type': 'object',
                        'properties': {
                            'count': {'type': 'integer'},
                            'start': {'type': 'integer'},
                            'end': {'type': 'integer'}
                        }
                    }
                },
                'patterns': {
                    'type': 'object',
                    'description': '检测到的模式信息',
                    'properties': {
                        'detected': {'type': 'string'},
                        'method': {
                            'type': 'string',
                            'enum': ['regex', 'ai', 'manual']
                        }
                    },
                    'required': ['detected', 'method'],
                    'additionalProperties': False
                }
            },
            'required': ['files', 'skipped', 'seasons', 'patterns'],
            'additionalProperties': False
        }
    }
}


# 简单 JSON 响应格式（用于不需要严格 schema 的场景）
SIMPLE_JSON_RESPONSE_FORMAT: Dict[str, Any] = {
    'type': 'json_object'
}
