#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 API Key 冷却和熔断器功能的脚本。

使用方法:
    python scripts/test_circuit_breaker.py [command]

命令:
    status      - 查看当前状态
    cooldown    - 触发 Key 冷却
    breaker     - 触发熔断器
    reset       - 重置所有状态
    simulate    - 模拟多次失败触发熔断
"""

import sys
import os
import io

# 修复 Windows 控制台 UTF-8 编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.ai.key_pool import (
    KeyPool, KeySpec, register_pool, get_pool, get_all_pools
)
from src.infrastructure.ai.circuit_breaker import (
    CircuitBreaker, register_breaker, get_breaker, get_all_breakers
)


def create_test_pool_and_breaker():
    """创建测试用的 Key Pool 和熔断器"""
    purpose = 'test_pool'

    # 检查是否已存在
    pool = get_pool(purpose)
    breaker = get_breaker(purpose)

    if not pool:
        pool = KeyPool(purpose)
        pool.configure([
            KeySpec(
                key_id='test_key_1',
                name='测试 Key 1',
                api_key='sk-test-key-1',
                base_url='https://api.example.com/v1',
                model='gpt-4',
                rpm_limit=10,
                rpd_limit=100,
                enabled=True
            ),
            KeySpec(
                key_id='test_key_2',
                name='测试 Key 2',
                api_key='sk-test-key-2',
                base_url='https://api.example.com/v1',
                model='gpt-4',
                rpm_limit=10,
                rpd_limit=100,
                enabled=True
            )
        ])
        register_pool(pool)
        print(f'✅ 创建测试 Key Pool: {purpose}')

    if not breaker:
        breaker = CircuitBreaker(purpose)
        register_breaker(breaker)
        print(f'✅ 创建测试熔断器: {purpose}')

    return pool, breaker


def show_status():
    """显示当前状态"""
    print('\n' + '=' * 60)
    print('📊 当前状态')
    print('=' * 60)

    # Key Pools
    pools = get_all_pools()
    print(f'\n🔑 Key Pools ({len(pools)} 个):')
    for purpose, pool in pools.items():
        status = pool.get_status()
        print(f'\n  [{purpose}]')
        print(f'    可用: {status["available_count"]}/{status["total_count"]}')
        print(f'    全部长冷却: {status["all_in_long_cooling"]}')
        for key in status['keys']:
            cooldown = key['cooldown_remaining_seconds']
            state_emoji = {'available': '🟢', 'cooling': '🟡', 'long_cooling': '🔴'}
            emoji = state_emoji.get(key['state'], '⚪')
            print(f'    {emoji} {key["name"]}: {key["state"]}'
                  + (f' (冷却剩余: {cooldown:.0f}s)' if cooldown > 0 else ''))

    # Circuit Breakers
    breakers = get_all_breakers()
    print(f'\n🔌 熔断器 ({len(breakers)} 个):')
    for purpose, breaker in breakers.items():
        status = breaker.get_status()
        is_open = status['is_open']
        emoji = '🔴' if is_open else '🟢'
        print(f'\n  [{purpose}]')
        print(f'    状态: {emoji} {"已触发" if is_open else "正常"}')
        if is_open:
            print(f'    剩余时间: {status["remaining_seconds"]:.0f}s')
        print(f'    触发次数: {status["trip_count"]}')
        if status['last_trip_reason']:
            print(f'    最近原因: {status["last_trip_reason"]}')

    print()


def trigger_cooldown():
    """触发 Key 冷却"""
    pool, _ = create_test_pool_and_breaker()

    print('\n🔄 触发 Key 冷却...')

    # 预留一个 Key
    reservation = pool.reserve()
    if reservation:
        print(f'  预留 Key: {reservation.key_id}')

        # 报告错误触发短冷却
        pool.report_error(
            reservation.key_id,
            error_message='测试错误 - 触发短冷却',
            is_rate_limit=False
        )
        print(f'  ✅ 已触发 {reservation.key_id} 短冷却 (30s)')
    else:
        print('  ❌ 没有可用的 Key')

    show_status()


def trigger_breaker():
    """触发熔断器"""
    _, breaker = create_test_pool_and_breaker()

    print('\n🔴 触发熔断器...')
    breaker.trip(duration=60, reason='手动测试触发')
    print('  ✅ 熔断器已触发 (60s)')

    show_status()


def reset_all():
    """重置所有状态"""
    print('\n🔄 重置所有状态...')

    # 重置 Key Pool
    for purpose, pool in get_all_pools().items():
        status = pool.get_status()
        for key in status['keys']:
            if key['cooldown_remaining_seconds'] > 0:
                pool.reset_cooldown(key['key_id'])
                print(f'  ✅ 重置 Key 冷却: {purpose}/{key["key_id"]}')

    # 重置熔断器
    for purpose, breaker in get_all_breakers().items():
        if breaker.is_open():
            breaker.reset()
            print(f'  ✅ 重置熔断器: {purpose}')

    show_status()


def simulate_failures():
    """模拟多次失败触发熔断"""
    pool, breaker = create_test_pool_and_breaker()

    print('\n🔥 模拟多次失败以触发熔断...')
    print('  (连续 3 次错误触发长冷却，所有 Key 长冷却后触发熔断)')

    # 对每个 Key 模拟多次失败
    status = pool.get_status()
    for key_info in status['keys']:
        key_id = key_info['key_id']
        print(f'\n  处理 Key: {key_id}')

        # 模拟 4 次连续错误 (超过 MAX_CONSECUTIVE_ERRORS=3)
        for i in range(4):
            pool.report_error(
                key_id,
                error_message=f'模拟错误 #{i+1}',
                is_rate_limit=False
            )
            print(f'    报告错误 #{i+1}')

    # 检查是否所有 Key 都在长冷却
    status = pool.get_status()
    if status['all_in_long_cooling']:
        print('\n  ⚠️ 所有 Key 都在长冷却中，触发熔断器...')
        breaker.trip(reason='所有 Key 都在长冷却中')
        print('  ✅ 熔断器已触发')

    show_status()


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1].lower()

    if command == 'status':
        # 确保有测试数据
        create_test_pool_and_breaker()
        show_status()
    elif command == 'cooldown':
        trigger_cooldown()
    elif command == 'breaker':
        trigger_breaker()
    elif command == 'reset':
        reset_all()
    elif command == 'simulate':
        simulate_failures()
    else:
        print(f'未知命令: {command}')
        print(__doc__)


if __name__ == '__main__':
    main()
