#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 API Key 冷却和熔断器功能的脚本。

使用方法:
    python scripts/test_circuit_breaker.py [command]

命令:
    status      - 查看当前状态
    cooldown    - 触发 Key 冷却
    disable     - 触发 Key 禁用 (模拟 400/403/404)
    enable      - 启用禁用的 Key
    breaker     - 触发熔断器
    halfopen    - 测试半开状态
    reset       - 重置所有状态
    simulate    - 模拟多次失败触发熔断
    rpm         - 测试 RPM 限制和智能等待
    rpd         - 测试 RPD 限制状态
    errors      - 显示错误类型映射
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
    KeyPool, KeySpec, ErrorType, register_pool, get_pool, get_all_pools
)
from src.infrastructure.ai.circuit_breaker import (
    CircuitBreaker, BreakerState, register_breaker, get_breaker, get_all_breakers
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
        breaker = CircuitBreaker(
            purpose,
            open_duration=60,
            half_open_max_probes=3,
            success_threshold=2
        )
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
        print(f'    禁用: {status["disabled_count"]}')
        print(f'    RPM 限制: {status.get("rpm_blocked_count", 0)}')
        print(f'    RPD 限制: {status.get("rpd_blocked_count", 0)}')
        print(f'    全部不可用: {status["all_in_long_cooling"]}')
        for key in status['keys']:
            cooldown = key['cooldown_remaining_seconds']
            state_emoji = {
                'available': '🟢',
                'cooling': '🟡',
                'long_cooling': '🔴',
                'disabled': '⚫'
            }
            emoji = state_emoji.get(key['state'], '⚪')
            info = f'{emoji} {key["name"]}: {key["state"]}'

            # RPM/RPD 信息
            rpm_str = f'{key["rpm_count"]}/{key["rpm_limit"] or "∞"}'
            rpd_str = f'{key["rpd_count"]}/{key["rpd_limit"] or "∞"}'
            info += f' (RPM: {rpm_str}, RPD: {rpd_str})'

            if key.get('rpm_blocked'):
                info += f' [RPM等待: {key.get("rpm_window_remaining_seconds", 0):.0f}s]'
            if key.get('rpd_blocked'):
                info += ' [RPD已达限]'
            if cooldown > 0:
                info += f' [冷却剩余: {cooldown:.0f}s]'
            if key['disabled']:
                info += f' [禁用原因: {key["disabled_reason"]}]'
            if key['last_error_type']:
                info += f' [错误类型: {key["last_error_type"]}]'
            print(f'    {info}')

    # Circuit Breakers
    breakers = get_all_breakers()
    print(f'\n🔌 熔断器 ({len(breakers)} 个):')
    for purpose, breaker in breakers.items():
        status = breaker.get_status()
        state = status['state']
        state_emoji = {'closed': '🟢', 'open': '🔴', 'half_open': '🟡'}
        emoji = state_emoji.get(state, '⚪')
        print(f'\n  [{purpose}]')
        print(f'    状态: {emoji} {state}')
        if state == 'open':
            print(f'    剩余时间: {status["remaining_seconds"]:.0f}s')
        if state == 'half_open':
            print(f'    探测进度: {status["probe_success_count"]}/{status["success_threshold"]}')
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

        # 报告错误触发冷却（使用 500 服务器错误）
        pool.report_error(
            reservation.key_id,
            error_message='测试错误 - 服务器内部错误',
            status_code=500
        )
        print(f'  ✅ 已触发 {reservation.key_id} 冷却')
    else:
        print('  ❌ 没有可用的 Key')

    show_status()


def trigger_disable():
    """触发 Key 禁用（模拟 400/403/404 错误）"""
    pool, _ = create_test_pool_and_breaker()

    print('\n🚫 触发 Key 禁用...')

    # 预留一个 Key
    reservation = pool.reserve()
    if reservation:
        print(f'  预留 Key: {reservation.key_id}')

        # 报告 403 错误触发禁用
        pool.report_error(
            reservation.key_id,
            error_message='API key not found or has been disabled',
            status_code=403
        )
        print(f'  ✅ Key {reservation.key_id} 已被禁用 (403 权限错误)')
    else:
        print('  ❌ 没有可用的 Key')

    show_status()


def enable_disabled_key():
    """启用禁用的 Key"""
    pool, _ = create_test_pool_and_breaker()

    print('\n✅ 启用禁用的 Key...')

    status = pool.get_status()
    enabled_any = False

    for key in status['keys']:
        if key['disabled']:
            pool.enable_key(key['key_id'])
            print(f'  ✅ Key {key["name"]} 已重新启用')
            enabled_any = True

    if not enabled_any:
        print('  ⚠️ 没有禁用的 Key')

    show_status()


def trigger_breaker():
    """触发熔断器"""
    _, breaker = create_test_pool_and_breaker()

    print('\n🔴 触发熔断器...')
    breaker.trip(duration=60, reason='手动测试触发')
    print('  ✅ 熔断器已触发 (60s)')

    show_status()


def test_half_open():
    """测试半开状态"""
    _, breaker = create_test_pool_and_breaker()

    print('\n🟡 测试半开状态...')

    # 先触发熔断
    breaker.trip(duration=1, reason='测试半开状态')
    print('  1. 触发熔断 (1s)')

    # 等待超时
    import time
    print('  2. 等待 2 秒...')
    time.sleep(2)

    # 检查状态
    if breaker.state == BreakerState.HALF_OPEN:
        print('  3. ✅ 熔断器已进入半开状态')

        # 模拟探测请求
        for i in range(3):
            if breaker.allow_request():
                print(f'  4.{i+1}. 探测请求 {i+1} 被允许')
                breaker.report_success()
            else:
                print(f'  4.{i+1}. 探测请求 {i+1} 被拒绝')

        # 检查是否恢复
        if breaker.state == BreakerState.CLOSED:
            print('  5. ✅ 熔断器已恢复正常')
        else:
            print(f'  5. ⚠️ 熔断器状态: {breaker.state.value}')
    else:
        print(f'  3. ⚠️ 熔断器状态: {breaker.state.value}')

    show_status()


def reset_all():
    """重置所有状态"""
    print('\n🔄 重置所有状态...')

    # 重置 Key Pool
    for purpose, pool in get_all_pools().items():
        status = pool.get_status()
        for key in status['keys']:
            if key['disabled']:
                pool.enable_key(key['key_id'])
                print(f'  ✅ 启用 Key: {purpose}/{key["key_id"]}')
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
                status_code=500  # 使用 500 服务器错误
            )
            print(f'    报告错误 #{i+1}')

    # 检查是否所有 Key 都在长冷却
    status = pool.get_status()
    if status['all_in_long_cooling']:
        print('\n  ⚠️ 所有 Key 都不可用，触发熔断器...')
        breaker.trip(reason='所有 Key 都在长冷却中')
        print('  ✅ 熔断器已触发')

    show_status()


def test_rpm_wait():
    """测试 RPM 限制和智能等待"""
    print('\n⏱️ 测试 RPM 限制和智能等待...')

    purpose = 'rpm_test_pool'

    # 创建一个 RPM 限制很低的测试池
    pool = KeyPool(purpose)
    pool.configure([
        KeySpec(
            key_id='rpm_key_1',
            name='RPM 测试 Key 1',
            api_key='sk-rpm-test-1',
            base_url='https://api.example.com/v1',
            model='gpt-4',
            rpm_limit=3,  # 每分钟只允许 3 次
            rpd_limit=0,  # 无每日限制
            enabled=True
        ),
        KeySpec(
            key_id='rpm_key_2',
            name='RPM 测试 Key 2',
            api_key='sk-rpm-test-2',
            base_url='https://api.example.com/v1',
            model='gpt-4',
            rpm_limit=3,
            rpd_limit=0,
            enabled=True
        )
    ])
    register_pool(pool)

    print(f'  创建测试池: {purpose}')
    print(f'  Key 数量: 2')
    print(f'  RPM 限制: 3/分钟/Key')
    print(f'  总 RPM: 6/分钟\n')

    # 快速消耗所有 RPM 配额
    print('  🔄 快速消耗 RPM 配额...')
    reserved_count = 0
    for i in range(10):
        # 不等待 RPM，只是尝试获取
        result = pool.reserve(wait_for_rpm=False)
        if result:
            pool.report_success(result.key_id)
            reserved_count += 1
            print(f'    #{i+1}: 预留成功 - {result.key_id}')
        else:
            print(f'    #{i+1}: 无可用 Key')
            break

    print(f'\n  📊 成功预留: {reserved_count} 次')

    # 显示当前状态
    status = pool.get_status()
    print(f'  RPM 限制的 Key 数: {status["rpm_blocked_count"]}')

    for key in status['keys']:
        rpm_info = f'{key["rpm_count"]}/{key["rpm_limit"]}'
        blocked = '🔴 已达限' if key['rpm_blocked'] else '🟢 可用'
        remaining = f'({key["rpm_window_remaining_seconds"]:.1f}s)' if key['rpm_blocked'] else ''
        print(f'    {key["name"]}: RPM {rpm_info} {blocked} {remaining}')

    # 测试智能等待
    print('\n  ⏳ 测试智能等待功能...')
    print('    尝试 reserve(wait_for_rpm=True)...')

    import time
    start = time.time()

    # 这应该会自动等待 RPM 窗口重置
    result = pool.reserve(wait_for_rpm=True)

    elapsed = time.time() - start

    if result:
        print(f'    ✅ 成功！等待了 {elapsed:.1f}s 后获得 Key: {result.key_id}')
    else:
        print(f'    ❌ 失败，等待 {elapsed:.1f}s 后仍无可用 Key')

    show_status()


def test_rpd_limit():
    """测试 RPD 限制状态"""
    print('\n📅 测试 RPD 限制状态...')

    purpose = 'rpd_test_pool'

    # 创建一个 RPD 限制很低的测试池
    pool = KeyPool(purpose)
    pool.configure([
        KeySpec(
            key_id='rpd_key_1',
            name='RPD 测试 Key 1',
            api_key='sk-rpd-test-1',
            base_url='https://api.example.com/v1',
            model='gpt-4',
            rpm_limit=0,    # 无 RPM 限制
            rpd_limit=5,    # 每天只允许 5 次
            enabled=True
        )
    ])
    register_pool(pool)

    print(f'  创建测试池: {purpose}')
    print(f'  Key 数量: 1')
    print(f'  RPD 限制: 5/天\n')

    # 快速消耗所有 RPD 配额
    print('  🔄 快速消耗 RPD 配额...')
    reserved_count = 0
    for i in range(10):
        result = pool.reserve(wait_for_rpm=False, wait_for_rpd=False)
        if result:
            pool.report_success(result.key_id)
            reserved_count += 1
            print(f'    #{i+1}: 预留成功 - {result.key_id}')
        else:
            print(f'    #{i+1}: 无可用 Key (RPD 已达限)')
            break

    print(f'\n  📊 成功预留: {reserved_count} 次')

    # 显示当前状态
    status = pool.get_status()
    print(f'  RPD 限制的 Key 数: {status["rpd_blocked_count"]}')

    for key in status['keys']:
        rpd_info = f'{key["rpd_count"]}/{key["rpd_limit"]}'
        blocked = '🔴 已达限 (需等到明天 UTC 0点)' if key['rpd_blocked'] else '🟢 可用'
        print(f'    {key["name"]}: RPD {rpd_info} {blocked}')

    # 测试手动重置
    print('\n  🔄 测试手动重置 RPD...')
    pool.reset_rpd('rpd_key_1')

    status = pool.get_status()
    for key in status['keys']:
        rpd_info = f'{key["rpd_count"]}/{key["rpd_limit"]}'
        blocked = '🔴 已达限' if key['rpd_blocked'] else '🟢 可用'
        print(f'    {key["name"]}: RPD {rpd_info} {blocked}')

    show_status()


def show_error_types():
    """显示所有错误类型"""
    print('\n📋 错误类型映射:')
    print('  ' + '-' * 50)
    print('  状态码 | 错误类型           | 处理方式')
    print('  ' + '-' * 50)
    print('  400    | INVALID_KEY        | 禁用 Key')
    print('  403    | PERMISSION_DENIED  | 禁用 Key')
    print('  404    | NOT_FOUND          | 禁用 Key')
    print('  429    | RATE_LIMITED       | 短冷却 10s')
    print('  500    | SERVER_ERROR       | 普通冷却')
    print('  503    | SERVICE_UNAVAILABLE| 普通冷却')
    print('  504    | TIMEOUT            | 普通冷却')
    print('  其他   | UNKNOWN            | 普通冷却')
    print('  ' + '-' * 50)


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print(__doc__)
        show_error_types()
        return

    command = sys.argv[1].lower()

    if command == 'status':
        create_test_pool_and_breaker()
        show_status()
    elif command == 'cooldown':
        trigger_cooldown()
    elif command == 'disable':
        trigger_disable()
    elif command == 'enable':
        enable_disabled_key()
    elif command == 'breaker':
        trigger_breaker()
    elif command == 'halfopen':
        test_half_open()
    elif command == 'reset':
        reset_all()
    elif command == 'simulate':
        simulate_failures()
    elif command == 'rpm':
        test_rpm_wait()
    elif command == 'rpd':
        test_rpd_limit()
    elif command == 'errors':
        show_error_types()
    else:
        print(f'未知命令: {command}')
        print(__doc__)


if __name__ == '__main__':
    main()
