# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
"""
K9log - Engineering-grade Causal Audit for AI Agent Ecosystems

Usage:
    from k9log import k9, set_agent_identity
    
    set_agent_identity(agent_name='MyAgent')
    
    @k9
    def my_skill(param1, param2):
        return result
"""

__version__ = '0.2.0'

# ── 依赖检查 ─────────────────────────────────────────────────────────────────
# 注意：这里只定义函数，不在顶层调用。
# 原因：k9log.governance.* 模块是纯计算层，不依赖 rich/click/requests。
# 如果在顶层调用，任何 `from k9log.governance.X import Y` 都会触发检查，
# 导致 hook.py 的宪法层在 rich 未安装时静默失效（except Exception 吞掉错误）。
# 正确做法：只在真正需要 rich 的入口（logger / CLI）处调用。
def _check_dependencies():
    missing = []
    try:
        import rich          # noqa
    except ImportError:
        missing.append("rich>=13.0")
    try:
        import click         # noqa
    except ImportError:
        missing.append("click>=8.0")
    try:
        import cryptography  # noqa
    except ImportError:
        missing.append("cryptography>=41.0")
    try:
        import requests      # noqa
    except ImportError:
        missing.append("requests>=2.28")
    if missing:
        pkgs = "  ".join(missing)
        raise ImportError(
            f"\n\n[K9log] 缺少必要依赖，请先安装：\n\n"
            f"    pip install {pkgs}\n\n"
            f"或者一次性安装所有依赖：\n\n"
            f"    pip install -r requirements.txt\n"
        )
# ─────────────────────────────────────────────────────────────────────────────


def k9(*args, **kwargs):
    _check_dependencies()
    from k9log.core import k9 as _k9
    return _k9(*args, **kwargs)


def set_agent_identity(*args, **kwargs):
    _check_dependencies()
    from k9log.identity import set_agent_identity as _f
    return _f(*args, **kwargs)


def get_agent_identity(*args, **kwargs):
    _check_dependencies()
    from k9log.identity import get_agent_identity as _f
    return _f(*args, **kwargs)


def get_logger(*args, **kwargs):
    _check_dependencies()
    from k9log.logger import get_logger as _f
    return _f(*args, **kwargs)


__all__ = [
    'k9',
    'set_agent_identity',
    'get_agent_identity',
    'get_logger',
]

__all__ = [
    'k9',
    'set_agent_identity',
    'get_agent_identity',
    'get_logger',
]

