# Changelog

本文件记录项目的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.1.0] - 2026-09-29

首个公开版本。

### Added

- **MCP 服务器**（`exact_calc_mcp.server`），暴露 5 个工具：
  - `calculate(expression, precision=50)` —— 精确计算，返回结果与两路验证说明
  - `verify(expression, precision=50)` —— 同上，先给「可信 / 不可信」判定
  - `are_equal(left, right, precision=50)` —— 判断两个表达式是否数学相等
  - `to_fraction(decimal_string)` —— 小数还原成精确分数
  - `engine_status()` —— 报告两个引擎的状态
- **命令行入口** `exact-calc`，支持 `--json` / `--compare` / `--fraction` /
  `--doctor` / `--serve` / `--precision` / `--version`
- **双数值域引擎**（`engine_py`）：`Fraction` 精确有理数 + `Decimal` 精确十进制，
  装不下时自动降级并注明原因
- **独立 C++ 引擎**（`cpp/calc.cpp`）：手写递归下降解析器，`long double`，
  作为第二意见参与交叉验证；找不到编译器时静默跳过
- **数字字面量从源码文本重建**：用 `ast.get_source_segment()` 取回源码字符串再交给
  `Decimal()`，避免 `0.1` 在进入 `ast` 时就退化成二进制近似
- **安全求值**：`ast` 白名单逐节点求值，不使用 `eval()`；
  `Attribute` / `Subscript` / `Lambda` / `IfExp` / `Comprehension` 全部拒绝
- **资源护栏**：整数次幂指数上限 ±10,000,000、`factorial` 参数上限 1,000,000、
  整数转字符串上限 1,000 万位、工作精度 1~100,000 位
- 38 个单元测试，覆盖精确性、安全性与交叉验证三块
- **6 个 MCP 协议测试**（`tests/test_mcp_protocol.py`）：真的起子进程走一遍
  stdio 上的 JSON-RPC 握手，验证 `serverInfo`、`tools/list`、`tools/call`
  与注入拒绝
- **MCP Registry 清单** `server.json`（`io.github.flacales/exact-calc-mcp`）
- **GitHub Actions**：`ci.yml`（3 平台 × 4 个 Python 版本的测试矩阵）、
  `publish-pypi.yml`（Trusted Publishing）、
  `publish-mcp-registry.yml`（发布到 MCP Registry）
- 社区健康文件：`CONTRIBUTING.md`、`SECURITY.md`、`CODE_OF_CONDUCT.md`、
  issue 模板

### Fixed

- MCP 客户端 `initialize` 时收到的 `serverInfo.version` 是 mcp SDK 的版本号
  而不是本项目版本 —— `FastMCP` 的构造签名没有 `version` 参数，
  底层 `Server` 会回落到 `pkg_version("mcp")`。现显式设置。

[Unreleased]: https://github.com/flacales/exact-calc-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/flacales/exact-calc-mcp/releases/tag/v0.1.0
