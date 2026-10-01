# 贡献指南

感谢你愿意参与。这个项目不大，规矩也不多，但下面几条请尽量遵守。

## 环境准备

只需要 Python 3.10+，**不需要额外依赖**（测试用的是标准库 `unittest`）：

```bash
git clone https://github.com/flacales/exact-calc-mcp.git
cd exact-calc-mcp
python -m unittest discover -s tests -v
```

装成可编辑模式后可以用命令行入口：

```bash
pip install -e .
exact-calc "0.1 + 0.2"
```

## 跑测试

```bash
python -m unittest discover -s tests -v
```

当前 38 个用例，应当全绿。**提交前请确保你没让它变红。**

## C++ 引擎

`cpp/calc.cpp` 是可选组件。有 C++ 编译器时会自动编译并参与交叉验证，
没有就静默跳过，不影响主功能。

注意两点：

- **源码必须是纯 ASCII。** 中文标识符在 MSVC / clang / gcc 之间行为不一致，
  一个要发到 GitHub 上的 C++ 文件不该埋这个雷。
- **`cpp/calc.exe`（及 `cpp/calc`）不要提交。** 它是编译产物，已在 `.gitignore` 里。

## 代码风格

- Python 侧用中文标识符是本项目**有意为之**（领域词直接中文更省认知成本），
  请保持一致，不要"顺手改成英文"。
- **工具描述（docstring）用英文，注释用中文。** docstring 是给模型读的，
  相当于一段 prompt，英文的兼容性和触发率更稳；注释是给人读的。
  两者受众不同，不该统一。
- 不引入运行时依赖。目前唯一的依赖是官方 `mcp` SDK。

## 关于"精确性"的硬要求

这是本项目的立身之本，改这块请格外小心：

- **数字字面量必须从源码文本还原**（`ast.get_source_segment()` → `Decimal()`），
  不能直接用 `ast` 里的 `float`。有专门的测试守着这条。
- **不要用 `eval()`。** 求值走 `ast` 白名单，函数名要先于实参校验。
- 改动数值域或交叉验证逻辑时，请**同时更新 README 的「局限」一节**——
  那份清单是给用户的承诺，不能落后于代码。

## 提交 PR

1. Fork 并开一个分支，分支名描述改动内容（`fix/...`、`feat/...`）
2. 确保测试全绿
3. 如果改了用户可见的行为，同步更新 `README.md`，并在 `CHANGELOG.md`
   的 `[Unreleased]` 下加一条
4. PR 描述里说清**为什么**这么改，而不只是改了什么

## 报告问题

- 功能缺陷 / 新想法 → 用 [issue 模板](.github/ISSUE_TEMPLATE)
- 安全漏洞 → **不要开公开 issue**，见 [SECURITY.md](SECURITY.md)

## 许可证

贡献的代码按 [MIT](LICENSE) 授权。
