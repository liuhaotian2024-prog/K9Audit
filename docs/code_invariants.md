# Code Invariants — K9 Audit 编程不变量规范

**CIEU Specification 补充文件 v1.0**
*本文件是 CIEU_spec.md 的增补，专门针对 AI 代码生成场景下的 bug 定义。*

---

## 为什么需要编程不变量

CIEU_spec.md 定义了"违反用户约束"为 violation。
本文件定义另一类 violation：**违反编程客观规律**。

用户约束是主观的（你可以不写）。
编程不变量是客观的——不管什么语言、什么项目、什么 AI，违反了就是 bug。

| 类型 | 来源 | 主观/客观 | 示例 |
|------|------|-----------|------|
| 用户约束违规 | Y*_t intent contract | 主观 | 写入了 staging.internal |
| 编程不变量违规 | 本文件定义的规则 | 客观 | 使用了未导入的模块 |

---

## 理论基础：运行时验证 + 契约式设计

K9 不做静态定理证明（Coq/TLA+），不穷举所有状态。
K9 做的是**运行时验证（Runtime Verification）**——在真实执行路径上验证规范是否满足。

这是形式化验证的一个正式分支，加上**契约式设计（Design by Contract）**：

- **postcondition**：函数执行后必须满足的条件
- **invariant**：任何情况下都必须满足的条件

Y*_t 天然是契约容器。用 K9Contract docstring 格式声明，
K9 在 PostToolUse 时自动解析并验证。

覆盖率分析：

| 阶段 | 覆盖率 | 条件 |
|------|--------|------|
| Phase 1 静态规则 | ~30% | 单文件语法+语义 |
| Phase 2 跨文件分析 | ~55% | 集成错误+环境错误 |
| Phase 1 + K9Contract | ~90% | 用户声明后置条件 |
| 永远无法覆盖 | ~10% | 永远不触发的逻辑错误 |

---

## 第一层：语法法则

| 规则 ID | 规则 | 示例违规 |
|---------|------|---------|
| SYN-001 | 括号/引号必须配对 | def foo(: |
| SYN-002 | 字符串必须闭合 | x = "hello |
| SYN-003 | Python 缩进必须一致 | 混用 tab 和 space |
| SYN-004 | 路径分隔符必须符合操作系统 | Windows 下硬编码 / |
| SYN-005 | JSON/YAML 结构必须合法 | 缺少闭合括号的配置文件 |

---

## 第二层：语义法则

| 规则 ID | 规则 | K9 实现状态 |
|---------|------|------------|
| SEM-001 | 使用的模块必须先导入 | ✅ Strategy 3 |
| SEM-002 | 调用的函数必须已定义 | Phase 2 |
| SEM-003 | 变量必须先定义再使用 | Phase 2 |
| SEM-004 | 打开的资源必须关闭 | Phase 2 |
| SEM-005 | 函数签名调用必须匹配 | Phase 2 |
| SEM-006 | 返回值类型必须一致 | Phase 2 |

---

## 第三层：AI 特有高频违规模式

| 规则 ID | 规则 | 说明 |
|---------|------|------|
| AI-001 | 禁止调用幻觉函数 | AI 最常见错误 |
| AI-002 | 禁止 Python 2/3 混用 | AI 训练数据混用 |
| AI-003 | 禁止硬编码环境值 | URL、IP、密钥直接写进代码 |
| AI-004 | 禁止跨文件幽灵引用 | 引用了不存在的类/函数 |
| AI-005 | 禁止静默吞掉异常 | except: pass |
| AI-006 | 禁止无限递归风险 | 递归函数没有终止条件 |

---

## 第四层：K9Contract 运行时契约（Phase 1 已实现）

用户在函数 docstring 里声明后置条件，K9 运行时验证：
```python
def process_payment(account_id: str, amount: float) -> dict:
    """
    K9Contract:
      postcondition: result["status"] in ("success", "failed")
      postcondition: result["balance"] >= 0
      invariant: amount > 0
    """
```

违反记录为 CODE_INVARIANT violation，写入 R_t+1，触发告警和因果追溯。

---

## CIEU 集成格式
```json
{
  "R_t+1": {
    "passed": false,
    "violations": [
      {
        "type": "CODE_INVARIANT",
        "rule_id": "POST-001",
        "field": "postcondition",
        "matched": "result['balance'] >= 0",
        "severity": 0.85,
        "message": "Postcondition violated: result['balance'] >= 0"
      }
    ]
  }
}
```

---

## 实现状态

| 规则层 | 规则数 | 已实现 |
|--------|--------|--------|
| 第一层 语法法则 | 5 | 0 (Phase 2) |
| 第二层 语义法则 | 6 | 1 — SEM-001 via Strategy 3 |
| 第三层 AI 特有 | 6 | 0 (Phase 2) |
| 第四层 K9Contract | ∞ | ✅ 用户自定义，运行时验证 |

---

## 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0 | 2026-03-09 | 初始版本，K9Contract Phase 1 实现 |
