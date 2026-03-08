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

Environment variable support
------------------------------
If no identity has been set programmatically, get_agent_identity() will
fall back to environment variables before returning None:

  K9LOG_AGENT_ID    -- agent_id  (default: auto-generated UUID)
  K9LOG_AGENT_NAME  -- agent_name
  K9LOG_AGENT_TYPE  -- agent_type (optional)

Example:
  $env:K9LOG_AGENT_NAME = "my-pipeline"
  $env:K9LOG_AGENT_TYPE = "ci"
  python my_agent.py
"""
import os
import json
import logging
import threading
import uuid
from pathlib import Path

_current_identity = None
_k9_log = logging.getLogger("k9log.identity")
_identity_lock = threading.Lock()

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

    with _identity_lock:
        # Read + write inside same lock -- prevents partial-read from concurrent writer
        if _preset_agent_id:
            agent_id = _preset_agent_id
        elif identity_file.exists():
            try:
                with open(identity_file, 'r') as f:
                    existing = json.load(f)
                agent_id = existing.get('agent_id', f"agent-{uuid.uuid4().hex[:8]}")
            except Exception:
                agent_id = f"agent-{uuid.uuid4().hex[:8]}"
        else:
            agent_id = f"agent-{uuid.uuid4().hex[:8]}"

        identity = {
            'agent_id': agent_id,
            'agent_name': agent_name,
            'agent_type': agent_type,
            'metadata': metadata or {}
        }

        prev_name = (_current_identity or {}).get("agent_name")
        with open(identity_file, 'w') as f:
            json.dump(identity, f, indent=2)
        _current_identity = identity


    if prev_name and prev_name != agent_name:
        _k9_log.info("k9log: agent identity changed: %s -> %s (%s)", prev_name, agent_name, agent_id)
    else:
        _k9_log.info("k9log: agent identity set: %s (%s)", agent_name, agent_id)

    print(f"✅ Agent identity set: {agent_name} ({agent_id})")

def get_agent_identity():
    """Get current agent identity.

    Resolution order:
    1. In-memory (_current_identity set via set_agent_identity)
    2. Persisted file (~/.k9log/agent_identity.json)
    3. Environment variables (K9LOG_AGENT_ID, K9LOG_AGENT_NAME, K9LOG_AGENT_TYPE)
    4. None
    """
    global _current_identity

    if _current_identity is not None:
        return _current_identity

    identity_file = Path.home() / ".k9log" / "agent_identity.json"
    if identity_file.exists():
        try:
            with _identity_lock:
                with open(identity_file, "r") as f:
                    _current_identity = json.load(f)
            return _current_identity
        except Exception:
            pass

    env_name = os.environ.get("K9LOG_AGENT_NAME")
    if env_name:
        env_identity = {
            "agent_id":   os.environ.get("K9LOG_AGENT_ID", f"agent-{uuid.uuid4().hex[:8]}"),
            "agent_name": env_name,
            "agent_type": os.environ.get("K9LOG_AGENT_TYPE"),
            "metadata":   {"source": "env"},
        }
        _k9_log.info("k9log: agent identity loaded from environment: %s (%s)",
                     env_identity["agent_name"], env_identity["agent_id"])
        _current_identity = env_identity
        return _current_identity

    return None

