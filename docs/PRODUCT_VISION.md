# K9Audit — Product Vision & Capability Summary

> 内部参考文档 · 2026-03-08

---

## 一句话定位

**数据主权优先、零 token、非 LLM、可验证的 AI agent 因果证据基础设施。**

不是在观察 agent，而是在给 agent 行为立一份带 hash chain 的可追责因果账本。

> 本地优先，不等于只能本地。核心审计引擎永远在用户机器上运行。
> 数据去哪里、怎么同步，由用户决定——不是我们。

## 部署模式

| 模式 | 适用场景 | 数据位置 |
|------|----------|----------|
| 本地（默认） | 个人开发者、高合规项目 | 仅在你的磁盘上 |
| 加密同步（Phase 2） | 团队共享 dashboard | 加密后同步，密钥归用户 |
| 自托管（Phase 2） | 金融、医疗、政府 | 你自己的基础设施 |

K9 永远不会用你的审计数据训练模型。

---

## 核心思想

别人做 agent 监控的通常路子：收 trace → 再喂给 LLM → LLM 给个总结。

K9Audit 不这样做。它的判断是确定性的，结果不依赖概率：

- 每次 agent 调用，强制记录"它**应该**怎么做"（Y*）和"它**实际**怎么做了"（Y_t+1）
- 两者之差就是偏差（R_t+1）
- 偏差用 SHA256 串起来，任何人任何时候都能重新验算，没法抵赖

这就是"不让嫌疑人给嫌疑人写不在场证明"的工程落地。

---

## 现在真实能干的事（第一阶段已交付）

### 1. CIEU 五元组记录引擎
`@k9` 装饰器把一次 agent 调用拆成五个字段：

| 字段 | 含义 |
|------|------|
| X_t | 上下文：谁在调用、从哪里、带什么环境 |
| U_t | 动作：调用了什么 skill、传了什么参数 |
| Y_star_t | 应然：这个 skill 的 intent contract / 约束规则 |
| Y_t+1 | 结果：实际执行后返回了什么 |
| R_t+1 | 评估：通过 / 违规 / 偏差程度 / 风险等级 |

### 2. 哈希链因果账本
Append-only JSONL ledger，每条记录带 prev_hash / event_hash / seq，Verifier 流式重算验证。不是普通日志，是带完整性证明的因果证据账本。

### 3. 确定性约束层
支持 max/min、regex、blocklist、allowlist、deny_content、allowed_paths、enum、长度约束。判断结果是确定性的，不需要 LLM 再解释一遍。

### 4. Incident Trace
k9log trace --last 终端一条命令还原案发现场，输出完整 X/U/Y*/Y/R + 时间线上下文 + hash 验证状态。

### 5. 双重验证
- verify-log：链完整性、hash、seq 连续性
- verify-ystar：约束覆盖率、uncovered skills 检测

### 6. HTML 证据报告
可分享、可存档、纯 HTML 无依赖。能给老板、客户、审计方、团队复盘用。

### 7. Health 一键体检
k9log health 一屏输出记录数、pass/violation 比例、chain integrity、约束覆盖率、skill 覆盖表、violation 分布、模块可用性。

### 8. Hook 适配器
hook.py 从 stdin 读 tool call payload，映射成 CIEU，做约束检查，写 ledger，发告警，不阻断 Claude Code。

### 9. 配套能力
- Alerting：Telegram / Slack / Discord / webhook，带去重和聚合
- Redaction：自动掩码 token / secret / credentials
- Identity：支持环境变量注入（K9LOG_AGENT_NAME 等），CI/CD 零代码接入

---

## 五个差异化

**1. 不是让 AI 审计 AI**
判断是确定性的，不依赖概率，不需要再调用一次 LLM。

**2. 不是 observability，是 causal evidence**
普通工具只有 timeline 和 span。K9Audit 还有 intent contract、outcome assessment 和 integrity proof。

**3. 本地优先，零 token 成本**
不上云，不按事件计费，不按席位叠价。

**4. 三件事同时成立**
可追溯（trace）、可验证（verify-log / verify-ystar）、可复核（hash chain + deterministic constraints + report）。

**5. Y* 作为第一公民**
绝大多数日志系统只记"发生了什么"，K9Audit 还记"应该发生什么"。两者之差才是真正有价值的信号。

---

## 最现实的市场切口

**眼前**：coding agent 用户——Claude Code、OpenHands、Cline 用户，让 agent 动 repo / shell / config 的开发者。痛点直接：为什么跑偏、为什么表面成功但结果奇怪、为什么要花几小时翻日志。

**更宽**：任何"行为有应然约束"的系统——workflow automation、enterprise agent ops、CI/CD traceability、RPA、autonomous systems incident reconstruction。

**合规方向**：可追责、可追溯、可解释、有 evidence integrity、有 rule coverage、有 report。EU AI Act 合规话语能听懂的东西。

---

## 将来能自然长出的功能

| 方向 | 说明 |
|------|------|
| 通用 ingestion 层 | generic JSON adapter、CI/CD adapter、shell trace adapter |
| 私有行为画像 | 哪些 skill 最危险、哪些 drift 最常见 |
| 反事实重放 | 如果当时换个 policy / 多一个约束会怎样 |
| 联邦失败模式库 | 跨用户沉淀 recurring hard cases 和 Y* 模板建议 |
| 完整治理层 | grants / verdict / constitutional enforcement |
| Operational world model | CIEU 五元组天然是行为世界模型的训练底座 |

---

## 当前边界（第一阶段未交付）

CLI 里已隐藏，调用时提示 not included in Phase 1 public release：
- Taint propagation
- Metalearning / causal rule learning
- Counterfactual replay
- Federated layer
- Full constitutional enforcement
- Full grants / policy runtime

---

## 一句话最终评价

它不是"又一个 trace dashboard"。
它是把过去很难追溯、很难解释、很难定责的 agent 问题，
变成几分钟内可 trace、可 verify、可出 report 的问题的基础设施。

