"""
AI 响应 JSON Schema 模块。

定义用于 AI API 调用的响应格式 Schema。
"""

from typing import Any, Dict

ResponseFormat = Dict[str, Any]


def _number_or_null(description: str) -> Dict[str, Any]:
    """Helper to describe numeric fields that may be null or fractional."""
    return {
        'description': description,
        'anyOf': [
            {'type': 'integer', 'minimum': 0},
            {'type': 'number', 'minimum': 0},
            {'type': 'null'}
        ]
    }


def _string_field(description: str) -> Dict[str, Any]:
    """Helper to describe common string fields."""
    return {
        'type': 'string',
        'description': description
    }


# 标题解析响应格式
TITLE_PARSE_RESPONSE_FORMAT: ResponseFormat = {
    'type': 'json_schema',
    'json_schema': {
        'name': 'anime_title_parse_result',
        'strict': True,
        'schema': {
            'type': 'object',
            'additionalProperties': False,
            'required': [
                'original_title',
                'anime_full_title',
                'anime_clean_title',
                'subtitle_group_name',
                'episode',
                'season',
                'category'
            ],
            'properties': {
                'original_title': _string_field('Input title to analyze'),
                'anime_full_title': _string_field('Full multi-language anime title'),
                'anime_clean_title': _string_field('Single-language clean anime title'),
                'subtitle_group_name': _string_field(
                    'Fansub or encoder name without brackets'
                ),
                'episode': _number_or_null(
                    'Episode number, movie defaults to 1, null if unknown'
                ),
                'season': {
                    'type': 'integer',
                    'minimum': 0,
                    'description': 'Season number, defaults to 1 when unknown'
                },
                'category': {
                    'type': 'string',
                    'description': 'Content category',
                    'enum': ['tv', 'movie']
                }
            }
        }
    }
}


# 多文件重命名响应格式
MULTI_FILE_RENAME_RESPONSE_FORMAT: ResponseFormat = {
    'type': 'json_schema',
    'json_schema': {
        'name': 'multi_file_rename_response',
        'strict': True,
        'schema': {
            'type': 'object',
            'additionalProperties': False,
            'required': [
                'main_files',
                'skipped_files',
                'seasons_info',
                'anime_full_title',
                'anime_clean_title',
                'subtitle_group_name',
                'subtitle_group_regex',
                'full_title_regex',
                'clean_title_regex',
                'episode_regex',
                'season',
                'category',
                'special_tag_regex',
                'quality_regex',
                'platform_regex',
                'source_regex',
                'codec_regex',
                'subtitle_type_regex',
                'format_regex'
            ],
            'properties': {
                'main_files': {
                    'type': 'object',
                    'description': 'Mappings of file keys (e.g. "1", "2") to new file names',
                    'additionalProperties': _string_field(
                        'Target file path with season prefix when required'
                    )
                },
                'skipped_files': {
                    'type': 'array',
                    'description': 'Keys of non-main content files to skip (e.g. ["3", "5"])',
                    'items': _string_field('File key that should be skipped')
                },
                'seasons_info': {
                    'type': 'object',
                    'description': 'Season metadata keyed by season number',
                    'additionalProperties': {
                        'type': 'object',
                        'additionalProperties': False,
                        'required': ['type', 'count', 'description'],
                        'properties': {
                            'type': _string_field('tv / movie / special'),
                            'count': {
                                'type': 'integer',
                                'minimum': 0,
                                'description': 'Number of episodes identified'
                            },
                            'description': _string_field(
                                'Human-readable description for the season'
                            )
                        }
                    }
                },
                'anime_full_title': _string_field('Full anime title'),
                'anime_clean_title': _string_field('Clean anime title'),
                'subtitle_group_name': _string_field('Primary fansub or encoder name'),
                'subtitle_group_regex': _string_field('Regex to capture subtitle group'),
                'full_title_regex': _string_field('Regex to capture full title block'),
                'clean_title_regex': _string_field('Regex to capture clean title'),
                'episode_regex': _string_field('Regex to capture episode numbers'),
                'season': {
                    'type': 'integer',
                    'minimum': 0,
                    'description': 'Season number primarily represented by this batch'
                },
                'category': {
                    'type': 'string',
                    'description': 'Content category',
                    'enum': ['tv', 'movie']
                },
                'special_tag_regex': _string_field('Regex for tags like V2, END, SP'),
                'quality_regex': _string_field('Regex for quality markers (e.g., 1080p)'),
                'platform_regex': _string_field('Regex for platform/source tags'),
                'source_regex': _string_field('Regex targeting rip/source info'),
                'codec_regex': _string_field('Regex for codec tagging'),
                'subtitle_type_regex': _string_field('Regex for subtitle type tags'),
                'format_regex': _string_field('Regex to capture extension/format')
            }
        }
    }
}


# 简单 JSON 响应格式（用于不需要严格 schema 的场景）
SIMPLE_JSON_RESPONSE_FORMAT: ResponseFormat = {
    'type': 'json_object'
}


# 字幕匹配响应格式
SUBTITLE_MATCH_RESPONSE_FORMAT: ResponseFormat = {
    'type': 'json_schema',
    'json_schema': {
        'name': 'subtitle_match_response',
        'strict': True,
        'schema': {
            'type': 'object',
            'additionalProperties': False,
            'required': ['matches', 'unmatched_subtitles', 'videos_without_subtitle'],
            'properties': {
                'matches': {
                    'type': 'array',
                    'description': 'List of matched video-subtitle pairs using keys',
                    'items': {
                        'type': 'object',
                        'additionalProperties': False,
                        'required': ['video_key', 'subtitle_key', 'language_tag', 'new_name'],
                        'properties': {
                            'video_key': _string_field('Video file key (e.g. "v1", "v2")'),
                            'subtitle_key': _string_field('Subtitle file key (e.g. "s1", "s2")'),
                            'language_tag': _string_field(
                                'Standardized language tag: chs, cht, eng, jpn, kor, etc.'
                            ),
                            'new_name': _string_field(
                                'New subtitle file name (without Season directory prefix)'
                            )
                        }
                    }
                },
                'unmatched_subtitles': {
                    'type': 'array',
                    'items': _string_field('Subtitle file keys that could not be matched'),
                    'description': 'Subtitle file keys without matching video (e.g. ["s3", "s5"])'
                },
                'videos_without_subtitle': {
                    'type': 'array',
                    'items': _string_field('Video file keys without matching subtitle'),
                    'description': 'Video file keys with no subtitle match (e.g. ["v2"])'
                }
            }
        }
    }
}
