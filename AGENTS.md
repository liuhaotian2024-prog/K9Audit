# K9 Audit — Claude Code Agent Instructions

## K9Contract 契约规范

每次写 Python 函数时，必须在 docstring 里声明 K9Contract。
K9 Audit 会在运行时验证这些契约，违反立即告警并写入因果链。

### 格式
```python
def process_payment(account_id: str, amount: float) -> dict:
    """
    处理支付请求。

    K9Contract:
      postcondition: result["status"] in ("success", "failed")
      postcondition: result["balance"] >= 0
      invariant: amount > 0
    """
    ...
```

### 规则

**postcondition** — 函数执行完成后必须满足的条件
- 可用变量：`result`（返回值）、`params`（入参dict）、所有参数名直接展开
- 例：`postcondition: result is not None`
- 例：`postcondition: len(result) > 0`
- 例：`postcondition: result["status"] == "success" or result["error"] is not None`

**invariant** — 任何情况下都必须满足的条件（通常针对输入参数）
- 例：`invariant: amount > 0`
- 例：`invariant: len(user_id) > 0`
- 例：`invariant: balance >= 0`

### 什么时候必须写契约

- 任何有返回值的函数
- 任何修改文件、数据库、外部状态的函数
- 任何涉及金融、安全、配置的函数

### 什么时候可以省略

- 纯工具函数（格式转换、字符串处理）
- 无副作用的常量函数

### 示例：文件写入
```python
def write_config(path: str, content: dict) -> bool:
    """
    写入配置文件。

    K9Contract:
      postcondition: result == True
      invariant: len(path) > 0
      invariant: isinstance(content, dict)
    """
    ...
```

### 示例：数据查询
```python
def query_database(table: str, limit: int) -> list:
    """
    查询数据库记录。

    K9Contract:
      postcondition: isinstance(result, list)
      postcondition: len(result) <= limit
      invariant: limit > 0
      invariant: len(table) > 0
    """
    ...
```

---

## 其他规范

- 每个新文件顶部必须有 `import` 语句（不要依赖隐式导入）
- 路径分隔符使用 `pathlib.Path`，不要硬编码 `/` 或 `\`
- 不要硬编码 URL、IP、密钥——使用配置文件或环境变量
- 异常必须处理，不要裸 `except: pass`
