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
K9log Identity - Agent identity management
"""
import os
import json
import uuid
from pathlib import Path

_current_identity = None

def set_agent_identity(agent_name, agent_type=None, metadata=None):
    """Set agent identity.

    Accepts two calling styles:
    - set_agent_identity("MyBot", agent_type="coding")       # positional
    - set_agent_identity({"agent_id": "x", "agent_name": "MyBot", ...})  # dict

    The dict form is used internally by connectors that already have a full
    identity object (e.g. hook.py reading from config).
    """
    global _current_identity
    # ── Handle dict shorthand ──────────────────────────────────────────────
    if isinstance(agent_name, dict):
        d = agent_name
        if agent_type is None:
            agent_type = d.get('agent_type')
        if metadata is None:
            metadata = d.get('metadata', {})
        agent_name = d.get('agent_name') or d.get('agent_id') or 'unknown'
        # If the dict already has a stable agent_id, preserve it
        _preset_agent_id = d.get('agent_id') if d.get('agent_id') else None
    else:
        _preset_agent_id = None
    
    identity_dir = Path.home() / '.k9log'
    identity_dir.mkdir(exist_ok=True)
    
    identity_file = identity_dir / 'agent_identity.json'
    
    # Load or generate agent_id
    if _preset_agent_id:
        agent_id = _preset_agent_id
    elif identity_file.exists():
        with open(identity_file, 'r') as f:
            existing = json.load(f)
            agent_id = existing.get('agent_id', f"agent-{uuid.uuid4().hex[:8]}")
    else:
        agent_id = f"agent-{uuid.uuid4().hex[:8]}"
    
    identity = {
        'agent_id': agent_id,
        'agent_name': agent_name,
        'agent_type': agent_type,
        'metadata': metadata or {}
    }
    
    # Save to file
    with open(identity_file, 'w') as f:
        json.dump(identity, f, indent=2)
    
    _current_identity = identity
    
    print(f'✅ Agent identity set: {agent_name} ({agent_id})')

def get_agent_identity():
    """Get current agent identity"""
    global _current_identity
    
    if _current_identity is None:
        # Try to load from file
        identity_file = Path.home() / '.k9log' / 'agent_identity.json'
        if identity_file.exists():
            with open(identity_file, 'r') as f:
                _current_identity = json.load(f)
    
    return _current_identity

