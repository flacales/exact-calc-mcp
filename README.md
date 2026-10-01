# exact-calc-mcp

<!-- mcp-name: io.github.flacales/exact-calc-mcp -->
<!--
  上一行是 MCP Registry 用来验证 PyPI 包归属的标记：Registry 会在包的 README
  （即 PyPI 上的 description）里找 `mcp-name: <server.json 里的 name>`。
  它必须在单独一行、或放在 HTML 注释里，且不能紧跟句号之类的字符，
  否则匹配不到。改 server.json 的 name 时记得同步改这里。
-->

[![CI](https://github.com/flacales/exact-calc-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/flacales/exact-calc-mcp/actions/workflows/ci.yml)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-3776AB.svg?logo=python&logoColor=white)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-server-6E56CF.svg)](https://registry.modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/tests-44%20passing-brightgreen.svg)](tests/)

**让 AI 用代码精确计算，而不是靠猜。**

给 AI agent 用的精确计算工具。通过 MCP 或命令行调用，结果由**两个独立编写的引擎**交叉验证后才返回。

<sub>English: Exact arithmetic for AI agents. LLMs do not compute — they generate plausible-looking tokens. This MCP server outsources arithmetic to two independently written engines (exact Python rational/decimal arithmetic + a separate C++ evaluator) and only returns a result when both agree.</sub>

---

## 问题：LLM 不做算术

这不是"模型不够聪明"，是架构决定的。语言模型是自回归生成器，它输出的是**在统计上最像答案的 token 序列**。它没有算术电路，没有进位链，没有中间寄存器。

所以当你问它 `0.1 + 0.2` 时，它不是在算，是在回忆"这段对话里通常接什么"。绝大多数时候它答 `0.3` —— 因为训练语料里就是这么写的。**这个答案恰好是对的，但不是因为它算对了。**

而在下面这些地方，它会稳定地错：

| 表达式 | 二进制浮点（Python `float`） | 本工具 |
|---|---|---|
| `0.1 + 0.2` | `0.30000000000000004` | `3/10` |
| `0.3 - 0.1` | `0.19999999999999998` | `1/5` |
| `1/3` | `0.3333333333333333` | `1/3` |
| `sqrt(2) ** 2` | `2.0000000000000004` | `1.999…9`（50 位精度内，误差 1e-49） |
| `1e16 + 1` | `1e+16`（+1 被吃掉） | `10000000000000001` |
| `2 ** 100` | `1.2676506002282294e+30` | `1267650600228229401496703205376` |

注意最后两行的区别：`2 ** 100` 在 `float` 里其实**是精确的**（它是 2 的幂），所以它不该被当作浮点误差的例子 —— 真正的例子是 `1e16 + 1`，那个 `+1` 被彻底吃掉了。挑例子也得较真。

**结论：不要让模型算。** 让它理解意图、编排步骤，把确定性计算外包给程序。这就是这个项目在做的事。

---

## 它和别的计算器 MCP 有什么不同

大部分 calculator MCP 就是一层 `eval()` 包装。这个不是。

| | 常见的 `eval()` 版 | 本工具 |
|---|---|---|
| **数值类型** | `float`（二进制，有误差） | `Fraction` / `Decimal`（精确） |
| **`0.1 + 0.2`** | `0.30000000000000004` | `3/10` |
| **安全性** | `eval()`，可被注入 | `ast` 白名单，逐节点求值 |
| **结果可信度** | 单点实现，错了不知道 | **双引擎交叉验证** |
| **字面量处理** | 直接用 `ast` 里的 float | **从源码文本重建** |

最后一条是最容易被忽略、也最关键的，下面单独讲。

---

## 安装

```bash
pip install -e .
```

只依赖官方 `mcp` SDK。C++ 引擎是**可选**的，找不到编译器会自动跳过，不影响使用。

---

## 用法一：接入 MCP 客户端

任何支持 MCP 的客户端都能直接用。下面覆盖了主流的几种。

先记住两条命令，下面所有配置无非是换一种写法：

```bash
# 不用安装（uv 会自动拉到临时环境）
uvx --from git+https://github.com/flacales/exact-calc-mcp exact-calc --serve

# 或本地装好后
pip install -e . && python -m exact_calc_mcp --serve
```

<details open>
<summary><b>Claude Desktop</b></summary>

编辑 `claude_desktop_config.json`（macOS：`~/Library/Application Support/Claude/`；
Windows：`%APPDATA%\Claude\`）：

```json
{
  "mcpServers": {
    "exact-calc": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/flacales/exact-calc-mcp", "exact-calc", "--serve"]
    }
  }
}
```

</details>

<details>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add exact-calc -- uvx --from git+https://github.com/flacales/exact-calc-mcp exact-calc --serve
```

</details>

<details>
<summary><b>Cursor</b></summary>

编辑 `~/.cursor/mcp.json`（全局）或项目里的 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "exact-calc": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/flacales/exact-calc-mcp", "exact-calc", "--serve"]
    }
  }
}
```

</details>

<details>
<summary><b>VS Code</b></summary>

编辑 `.vscode/mcp.json`（工作区）或用户设置里的 `mcp` 段。
注意 VS Code 用的键是 `servers` 而不是 `mcpServers`，并且要显式写 `type`：

```json
{
  "servers": {
    "exact-calc": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/flacales/exact-calc-mcp", "exact-calc", "--serve"]
    }
  }
}
```

</details>

<details>
<summary><b>Codex</b></summary>

编辑 `~/.codex/config.toml`：

```toml
[mcp_servers.exact-calc]
command = "uvx"
args = ["--from", "git+https://github.com/flacales/exact-calc-mcp", "exact-calc", "--serve"]
```

</details>

<details>
<summary><b>Cline / Continue / 其他</b></summary>

配置结构基本一致，都是 `mcpServers` 下加一项：

```json
{
  "mcpServers": {
    "exact-calc": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/flacales/exact-calc-mcp", "exact-calc", "--serve"]
    }
  }
}
```

</details>

> 不想用 `uvx` 也行：把 `command` 换成 `python`、`args` 换成
> `["-m", "exact_calc_mcp", "--serve"]`，前提是那个 Python 环境里装了本项目。

### 提供的工具

| 工具 | 用途 |
|---|---|
| `calculate(expression, precision=50)` | 精确计算，返回结果 + 两路验证说明 |
| `verify(expression, precision=50)` | 同上，但先给一句"可信 / 不可信"的判定 |
| `are_equal(left, right, precision=50)` | 判断两个表达式是否数学相等 |
| `to_fraction(decimal_string)` | 把小数还原成精确分数 |
| `engine_status()` | 报告两个引擎的状态 |

`calculate` 返回的结构：

```json
{
  "expression": "0.1 + 0.2",
  "value": "3/10",
  "domain": "fraction",
  "exact": true,
  "cross_check": "通过（Fraction 与 Decimal 结果一致）",
  "cpp_check": "通过（Python 与 C++ 独立实现结果完全一致：0.3）",
  "note": ""
}
```

---

## 用法二：命令行

不需要 MCP 客户端也能用 —— 任何能执行 shell 的 agent 都可以调。

```bash
# 计算
exact-calc "0.1 + 0.2"
# 0.1 + 0.2 = 3/10
#   数值域    : fraction（无损）
#   Python 自检: 通过（Fraction 与 Decimal 结果一致）
#   C++ 独立复核: 通过（Python 与 C++ 独立实现结果完全一致：0.3）

# 给程序解析用的 JSON
exact-calc --json "1/3 + 1/6"

# 判断两个表达式是否相等（退出码 0 相等 / 1 不等）
exact-calc --compare "0.1 + 0.2" "0.3"

# 小数转精确分数
exact-calc --fraction 0.1        # 1/10

# 检查引擎状态
exact-calc --doctor
```

支持的语法：`+ - * / // % **` 和括号，函数 `sqrt abs round min max factorial gcd lcm ln log log10 exp pow`，常量 `pi`、`e`。运算符优先级与 Python 完全一致（`-2 ** 2` 是 `-4`，`2 ** 3 ** 2` 是 `512`）。两点和 Python 直觉不同：`log(x)` 是**自然对数**（与 `math.log` 一致），`log(x, base)` 指定底数，常用对数用 `log10`；`round` 是**远离零**的四舍五入（`round(2.5) = 3`），不是 Python 内建的银行家舍入。

---

## 架构

```
              ┌──────────────────────────────────────┐
   表达式 ──▶ │  ast 解析 + 白名单校验（不用 eval）    │
              └───────────────┬──────────────────────┘
                              │
              ┌───────────────▼──────────────────────┐
              │  从**源码文本**重建数字字面量          │
              │  "0.1" ──▶ Decimal("0.1")，不经过 float│
              └───────────────┬──────────────────────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        │                                           │
   ┌────▼─────────────┐                    ┌────────▼──────────┐
   │  Python 引擎      │                    │  C++ 引擎          │
   │  Fraction / Decimal│                   │  手写递归下降解析器 │
   │  任意精度，精确    │                    │  long double       │
   └────┬─────────────┘                    └────────┬──────────┘
        │                                           │
        │  Fraction ◀─对比──▶ Decimal               │
        │                                           │
        └───────────────┬───────────────────────────┘
                        │
              ┌─────────▼──────────┐
              │  两路一致才返回     │
              │  不一致就明确报警   │
              └────────────────────┘
```

---

## 四个设计决定

### 1. 不用 `eval()`

`eval()` 会把 `__import__('os').system('rm -rf /')` 当成正常表达式执行。这里用 `ast` 解析成语法树后逐节点求值，只放行白名单里的节点类型和函数名。`Attribute`、`Subscript`、`Lambda`、`IfExp`、`Comprehension` 全部拒绝。

**函数名先于实参校验** —— 否则 `open('x','w')` 会先因为字符串参数报一个"无法识别的数字"，把真正的拒绝理由盖掉。

### 2. 数字从源码文本重建（最关键的一条）

```python
ast.parse("0.1")            # Constant(value=0.1) ← 已经是二进制近似了
```

`0.1` 在 `ast` 里已经变成 `float(0.1)`，而它的真实值是

```
0.1000000000000000055511151231257827021181583404541015625
```

精度在拿到它的那一刻就丢了。所以这里用 `ast.get_source_segment()` 取回**源码里的字符串 `"0.1"`**，再交给 `Decimal("0.1")` —— 这才是精确的十进制 0.1。

去掉这一步，整个项目的精确性主张都是空话。有专门的测试守着这条（`test_数字字面量从源码文本还原`）。

### 3. 双数值域，自动降级

- **`Fraction`** —— 有理数精确。分数运算、完全平方数的开方走这条。
- **`Decimal`** —— 十进制精确。无理数（`sqrt(2)`、`pi`、`ln`）走这条。

先试 `Fraction`，装不下就自动降级到 `Decimal`，并在结果里注明为什么。`sqrt(144)` 仍然是精确的 `12`，因为它能开尽。

### 4. 双引擎交叉验证

**一个实现错了，你不会知道。** 所以这里有两个：

- Python 引擎：`Fraction` / `Decimal`，任意精度，精确
- C++ 引擎：手写的递归下降解析器，`long double`，**故意不精确**

C++ 那边只回答"量级和有效数字对得上吗"，不参与精度判定。两边对不上就明确报警，而不是返回一个可疑的数字。

C++ 引擎明确不支持的函数（`factorial`、`gcd` 等）会返回退出码 2，调用方据此**跳过验证**，而不是误报不一致。

> 关于 C++ 源码：它全部是 ASCII 的。中文标识符在 MSVC、clang、gcc 之间行为不一致，一个要发到 GitHub 上的 C++ 文件不该埋这个雷。

---

## 局限（诚实说明）

- **不支持复数**：`sqrt(-1)` 会报错。
- **三角/双曲函数未实现**：`Decimal` 没有这些函数，需要它们的话得引入 `mpmath`。
- **`%` 对负数取模的行为**：Python 侧用 `operator.mod`（结果为负时向负无穷取整），C++ 侧用 `fmodl`（向零取整）。两者对负操作数的结果不同，这类表达式会被交叉验证判为不一致 —— 这是**已知的行为差异**，不是 bug。
- **C++ 引擎精度有限**：`long double` 约 18~19 位有效十进制。超过这个量级的验证会以"相对误差 1e-18，差异来自精度上限"的形式通过。
- **`0x10` 这类十六进制字面量**：Python 引擎支持，C++ 引擎不支持（`strtold` 要求十六进制浮点必须带 `p` 指数），会走"已跳过"。
- **`round` 是远离零舍入**：`round(2.5) = 3`、`round(-2.5) = -3`。和 Python 内建 `round()` 的银行家舍入（`round(2.5) = 2`）不同 —— 这是故意的，三个引擎（Fraction / Decimal / C++ `roundl`）在这件事上保持一致，比跟随 Python 的内建行为更重要。
- **资源护栏**：整数次幂的指数上限 ±10,000,000（结果约 300 万位）；`factorial` 参数上限 1,000,000；整数转字符串上限 1,000 万位（Python 3.11+ 默认只有 4300 位，本工具已放宽）；指数超过 1e±100000 的结果以科学计数法表示（如 `1e+999999999`）；工作精度限定在 1~100,000 位。超出护栏的表达式会被明确拒绝，而不是把机器算死。
- **`pi`、`e` 预存 1020 位有效数字**：超过这个位数的常数相关计算以预存值为准（`sqrt(2)`、`ln(2)` 这类现场计算的值不受此限，随精度参数走）。
- **它不是符号计算系统**：不做化简、解方程、求导。需要这些请上 `sympy`。

---

## 测试

```bash
python -m unittest discover -s tests -v
```

**44 个用例，全绿**，覆盖四块：

| 文件 | 用例 | 测什么 |
|---|--:|---|
| `tests/test_engine.py` | 38 | 精确性、安全性、交叉验证 |
| `tests/test_mcp_protocol.py` | 6 | MCP 协议层：stdio 上的 JSON-RPC 握手、`tools/list`、`tools/call`、注入拒绝 |

具体地：

- **精确性**：浮点误差被消除、大整数不丢精度、优先级与 Python 一致
- **安全性**：14 个注入/越权表达式全部被拒
- **交叉验证**：两路结果一致；C++ 超范围时正确跳过而非误报
- **协议**：`serverInfo.version` 是项目版本而**不是 mcp SDK 的版本**；
  5 个工具都在且都有描述（描述是给模型读的 prompt，缺了模型就不会调）

---

## 为什么值得做这件事

给 AI 加一个计算器，听起来是个小工具。但它背后的原则很大：

> **模型负责理解与编排，程序负责确定性计算。**

把这条原则推到底，就是 agent 工程的核心 —— 凡是"有唯一正确答案"的事，都不该交给一个概率模型去猜。日期计算、单位换算、财务对账、代码执行，全都一样。

这个项目是那条原则最小的一个实例。

---

## 贡献

欢迎 issue 和 PR。开始之前请读 [CONTRIBUTING.md](CONTRIBUTING.md)。

跑测试只要一条命令，不需要额外依赖：

```bash
python -m unittest discover -s tests -v
```

## 安全

这个工具**不执行任意代码** —— 表达式经 `ast` 白名单逐节点求值，不走 `eval()`，
属性访问、下标、lambda、推导式一律拒绝。相关测试在
`tests/test_engine.py` 的「安全性」一节。

如果你发现了绕过白名单、拒绝服务或资源护栏失效的问题，
请按 [SECURITY.md](SECURITY.md) 的方式**私下报告**，不要开公开 issue。

## 变更记录

见 [CHANGELOG.md](CHANGELOG.md)。

## License

MIT —— 见 [LICENSE](LICENSE)。
