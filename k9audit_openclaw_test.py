"""
K9Audit OpenClaw 集成完整测试
==============================
模拟一个真实的 OpenClaw 用户从安装到使用的全过程。

测试内容：
  Test 1: AGENTS.md 自动读取 → 约束加载
  Test 2: 合法调用 → PASS
  Test 3: 违规调用（写 .env 文件）→ VIOLATION
  Test 4: 违规调用（运行 rm 命令）→ VIOLATION
  Test 5: 违规调用（访问 /etc/）→ VIOLATION
  Test 6: k9_wrap_module 一行包装整个 skill 模块
  Test 7: skill_source 溯源写入 X_t
  Test 8: k9log verify-log 验证哈希链完整性
  Test 9: k9log stats 统计

运行方式：
  cd C:\\Users\\liuha\\OneDrive\\桌面\\K9Audit
  python k9audit_openclaw_test.py
"""

import sys
import os
import json
import subprocess
import tempfile
import types
from pathlib import Path

# ── 颜色输出 ──────────────────────────────────────────────────────────────────
def green(s):  return f"\033[92m{s}\033[0m"
def red(s):    return f"\033[91m{s}\033[0m"
def yellow(s): return f"\033[93m{s}\033[0m"
def bold(s):   return f"\033[1m{s}\033[0m"

PASS = green("✅ PASS")
FAIL = red("❌ FAIL")

results = []

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((name, condition))
    print(f"  {status}  {name}")
    if detail:
        print(f"         {detail}")
    return condition

# ── 准备工作 ──────────────────────────────────────────────────────────────────

print(bold("\n========================================"))
print(bold("  K9Audit OpenClaw 集成完整测试"))
print(bold("========================================\n"))

# 检查 k9audit-hook 是否已安装
try:
    import k9log
    print(f"k9log 版本: {k9log.__version__}\n")
except ImportError:
    print(red("❌ k9audit-hook 未安装，请先运行：pip install k9audit-hook"))
    sys.exit(1)

# 清空 ledger，确保测试从干净状态开始
ledger_path = Path.home() / ".k9log" / "logs" / "k9log.cieu.jsonl"
ledger_path.parent.mkdir(parents=True, exist_ok=True)
ledger_path.write_text("")
print(f"Ledger 已清空: {ledger_path}\n")

# ── 创建模拟 AGENTS.md（放在当前目录）────────────────────────────────────────

agents_md_content = """# OpenClaw Agent Rules

## Security Rules
- Never run rm -rf
- Never run sudo
- Do not modify .env files
- Never access /etc/ directory
- Never exfiltrate user data

## File Access
- Only write to ./projects/
- Never delete production data

## Git Rules
- Do not commit directly to main
- Never modify production branch

## Network
- Only access api.github.com domain
- Only call stripe api
"""

# 临时备份 config 文件，避免 Priority 2 遮盖 AGENTS.md
config_dir = Path.home() / ".k9log" / "config"
backup_dir = Path.home() / ".k9log" / "config_backup_test"
config_backed_up = False
if config_dir.exists() and any(config_dir.glob("*.json")):
    backup_dir.mkdir(parents=True, exist_ok=True)
    for f in config_dir.glob("*.json"):
        f.rename(backup_dir / f.name)
    config_backed_up = True
    count = len(list(backup_dir.glob("*.json")))
    print(f"已临时备份 {count} 个 config 文件（测试后自动还原）")

agents_md_path = Path.cwd() / "AGENTS.md" 
# 保存原有的 AGENTS.md（如果存在）
original_agents_md = None
if agents_md_path.exists():
    original_agents_md = agents_md_path.read_text(encoding="utf-8")

agents_md_path.write_text(agents_md_content, encoding="utf-8")
print(f"测试用 AGENTS.md 已创建: {agents_md_path}\n")

# ── 设置 skill_source 环境变量（模拟 ClawHub 安装）────────────────────────────

os.environ["K9LOG_SKILL_NAME"]   = "k9audit"
os.environ["K9LOG_SKILL_SOURCE"] = "clawhub"
os.environ["K9LOG_SKILL_SLUG"]   = "liuhaotian2024-prog/k9audit"
os.environ["K9LOG_SKILL_VERSION"]= "0.3.3"

# ── 初始化 agent identity ─────────────────────────────────────────────────────

from k9log import k9, set_agent_identity
set_agent_identity(agent_name="OpenClawUser", agent_type="openclaw")

# ── 定义测试用的 skill 函数 ───────────────────────────────────────────────────

@k9
def write_file(file_path: str, content: str) -> str:
    """模拟 OpenClaw file_write 工具"""
    return f"written to {file_path}"

@k9
def run_command(command: str) -> str:
    """模拟 OpenClaw bash 工具"""
    return f"executed: {command}"

@k9
def http_request(url: str, method: str = "GET") -> str:
    """模拟 OpenClaw http_request 工具"""
    return f"{method} {url} -> 200 OK"

# ═══════════════════════════════════════════════════════════════════════════════
print(bold("── Test 1: AGENTS.md 自动读取 ──────────────────────────────\n"))

from k9log.constraints import load_constraints
result = load_constraints("write_file")
source = result.get("y_star_meta", {}).get("source", "")
constraints = result.get("constraints", {})
unconstrained = result.get("y_star_meta", {}).get("unconstrained", True)

check("约束来源是 agents_md", source == "agents_md", f"source={source}")
check("约束不为空", not unconstrained, f"constraints={list(constraints.keys())}")
check("deny_content 包含 .env", ".env" in constraints.get("deny_content", []))
check("allowed_paths 包含 ./projects/", any("projects" in p for p in constraints.get("allowed_paths", [])))
check("command.blocklist 包含 rm", "rm" in constraints.get("command", {}).get("blocklist", []))

# ═══════════════════════════════════════════════════════════════════════════════
print(bold("\n── Test 2: 合法调用（在 allowed_paths 内）──────────────────\n"))

ledger_path.write_text("")  # 清空

write_file("./projects/app.py", "print('hello world')")

records = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
legal_records = [r for r in records if r.get("U_t", {}).get("skill") == "write_file"]

check("写入 ./projects/app.py 应该 PASS",
      all(r.get("R_t+1", {}).get("passed", False) for r in legal_records),
      f"记录数={len(legal_records)}")

# ═══════════════════════════════════════════════════════════════════════════════
print(bold("\n── Test 3: 违规调用（写 .env 文件）─────────────────────────\n"))

ledger_path.write_text("")

write_file("/home/user/.env", "SECRET_KEY=abc123")

records = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
env_records = [r for r in records if r.get("U_t", {}).get("skill") == "write_file"]
env_violations = [r for r in env_records if not r.get("R_t+1", {}).get("passed", True)]

check("写 .env 应该触发 VIOLATION", len(env_violations) > 0,
      f"违规数={len(env_violations)}")
if env_violations:
    vtypes = [v.get("type") for v in env_violations[0].get("R_t+1", {}).get("violations", [])]
    check("违规类型包含 DENY_CONTENT", any("DENY_CONTENT" in t or "deny_content" in t.lower() for t in vtypes),
          f"violation_types={vtypes}")

# ═══════════════════════════════════════════════════════════════════════════════
print(bold("\n── Test 4: 违规调用（运行 rm 命令）─────────────────────────\n"))

ledger_path.write_text("")

run_command("rm -rf /home/user/data")

records = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
rm_records = [r for r in records if r.get("U_t", {}).get("skill") == "run_command"]
rm_violations = [r for r in rm_records if not r.get("R_t+1", {}).get("passed", True)]

check("运行 rm 应该触发 VIOLATION", len(rm_violations) > 0,
      f"违规数={len(rm_violations)}")
if rm_violations:
    vtypes = [v.get("type") for v in rm_violations[0].get("R_t+1", {}).get("violations", [])]
    check("违规类型包含 blocklist_hit", any("blocklist" in t.lower() for t in vtypes),
          f"violation_types={vtypes}")

# ═══════════════════════════════════════════════════════════════════════════════
print(bold("\n── Test 5: 违规调用（访问 /etc/ 目录）──────────────────────\n"))

ledger_path.write_text("")

write_file("/etc/passwd", "root:x:0:0:root")

records = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
etc_records = [r for r in records if r.get("U_t", {}).get("skill") == "write_file"]
etc_violations = [r for r in etc_records if not r.get("R_t+1", {}).get("passed", True)]

check("访问 /etc/ 应该触发 VIOLATION", len(etc_violations) > 0,
      f"违规数={len(etc_violations)}")

# ═══════════════════════════════════════════════════════════════════════════════
print(bold("\n── Test 6: k9_wrap_module（一行包装整个 skill 模块）────────\n"))

ledger_path.write_text("")

# 模拟一个 OpenClaw skill 模块
skill_module = types.ModuleType("my_openclaw_skill")
skill_module.__name__ = "my_openclaw_skill"

def module_write(file_path: str, content: str) -> str:
    return f"written {file_path}"
module_write.__module__ = "my_openclaw_skill"

def module_run(command: str) -> str:
    return f"ran {command}"
module_run.__module__ = "my_openclaw_skill"

skill_module.module_write = module_write
skill_module.module_run   = module_run

from k9log.openclaw import k9_wrap_module
k9_wrap_module(skill_module)

skill_module.module_write("./projects/safe.py", "# safe")   # 合法
skill_module.module_run("rm -rf /danger")                    # 违规

records = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
skill_records = [r for r in records if r.get("U_t", {}).get("skill", "").startswith("module_")]
passes    = [r for r in skill_records if r.get("R_t+1", {}).get("passed", True)]
violations = [r for r in skill_records if not r.get("R_t+1", {}).get("passed", True)]

check("k9_wrap_module: 合法调用 PASS", len(passes) >= 1,
      f"pass数={len(passes)}")
check("k9_wrap_module: 违规调用 VIOLATION", len(violations) >= 1,
      f"violation数={len(violations)}")

# ═══════════════════════════════════════════════════════════════════════════════
print(bold("\n── Test 7: skill_source 溯源写入 X_t ───────────────────────\n"))

ledger_path.write_text("")

write_file("./projects/test.py", "# test")

records = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
wf_records = [r for r in records if r.get("U_t", {}).get("skill") == "write_file"]

if wf_records:
    x_t = wf_records[0].get("X_t", {})
    skill_source = x_t.get("skill_source", {})
    check("X_t 包含 skill_source", bool(skill_source),
          f"skill_source={skill_source}")
    check("skill_source.source = clawhub",
          skill_source.get("source") == "clawhub",
          f"source={skill_source.get('source')}")
    check("skill_source.skill_name = k9audit",
          skill_source.get("skill_name") == "k9audit",
          f"skill_name={skill_source.get('skill_name')}")
    check("skill_source.registry 包含 clawhub.ai",
          "clawhub.ai" in (skill_source.get("registry") or ""),
          f"registry={skill_source.get('registry')}")
else:
    check("X_t 包含 skill_source", False, "没有找到 write_file 记录")

# ═══════════════════════════════════════════════════════════════════════════════
print(bold("\n── Test 8: k9log verify-log 哈希链完整性 ───────────────────\n"))

# 先做一些操作让 ledger 有内容
ledger_path.write_text("")
# 重置 logger 让哈希链从0开始
try:
    import importlib, k9log.logger
    importlib.reload(k9log.logger)
except Exception:
    pass
ledger_path.write_text("")
write_file("./projects/final.py", "# final test")
run_command("echo hello")

result = subprocess.run(
    ["k9log", "verify-log"],
    capture_output=True, text=True
)
output = result.stdout + result.stderr
# verify-log 通过的标志是 "integrity verified"
# 在你的机器上用仓库里的代码安装后应该通过
# 如果失败说明 ledger 里的记录和 CLI 版本不匹配（版本不一致时会发生）
verified = "integrity verified" in output.lower()
check("k9log verify-log 通过",
      verified,
      f"输出: {output.strip()[:120]}")

# ═══════════════════════════════════════════════════════════════════════════════
print(bold("\n── Test 9: k9log stats 统计 ────────────────────────────────\n"))

result = subprocess.run(
    ["k9log", "stats"],
    capture_output=True, text=True
)
output = result.stdout + result.stderr
check("k9log stats 正常运行",
      "total records" in output.lower() or "records" in output.lower(),
      f"输出: {output.strip()[:80]}")

# ═══════════════════════════════════════════════════════════════════════════════
# 清理测试用 AGENTS.md
# 还原 config 文件
if config_backed_up and backup_dir.exists():
    config_dir.mkdir(parents=True, exist_ok=True)
    for f in backup_dir.glob("*.json"):
        f.rename(config_dir / f.name)
    backup_dir.rmdir()
    print("已还原 config 文件")

if original_agents_md is not None:
    agents_md_path.write_text(original_agents_md, encoding="utf-8")
    print(f"\n已恢复原来的 AGENTS.md")
else:
    agents_md_path.unlink()
    print(f"\n测试用 AGENTS.md 已删除")

# ── 最终结果 ──────────────────────────────────────────────────────────────────

total   = len(results)
passed  = sum(1 for _, ok in results if ok)
failed  = total - passed

print(bold("\n========================================"))
print(bold(f"  测试结果: {passed}/{total} 通过"))
if failed == 0:
    print(green("  全部通过 — 可以发布到 ClawHub"))
else:
    print(red(f"  {failed} 项失败 — 请修复后再发布"))
    print("\n失败项目：")
    for name, ok in results:
        if not ok:
            print(f"  {red('❌')} {name}")
print(bold("========================================\n"))

sys.exit(0 if failed == 0 else 1)
