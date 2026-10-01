# -*- coding: utf-8 -*-
"""测试套件

跑法：
    python -m unittest discover -s tests -v
或者：
    python tests/test_engine.py

重点覆盖三类东西：
  1. 精确性 —— 本工具存在的理由，必须有测试守着
  2. 安全性 —— AST 白名单不能被绕过
  3. 交叉验证 —— C++ 引擎对不上时必须报警，而不是默默返回
"""

from __future__ import annotations

import math
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exact_calc_mcp import engine_cpp, engine_py  # noqa: E402


class 测试精确性(unittest.TestCase):
    def test_浮点经典误差被消除(self):
        """0.1 + 0.2 必须是精确的 3/10。"""
        self.assertEqual(engine_py.计算("0.1 + 0.2").值, "3/10")
        self.assertEqual(engine_py.计算("0.3").值, "3/10")
        # 对照：二进制浮点做不到
        self.assertNotEqual(0.1 + 0.2, 0.3)

    def test_减法不产生尾数垃圾(self):
        self.assertEqual(engine_py.计算("0.3 - 0.1").值, "1/5")
        self.assertNotEqual(0.3 - 0.1, 0.2)  # float 会给 0.19999999999999998

    def test_分数运算保持精确(self):
        self.assertEqual(engine_py.计算("1/3 + 1/6").值, "1/2")
        self.assertEqual(engine_py.计算("(1/7) * 7").值, "1")
        self.assertEqual(engine_py.计算("10 / 4").值, "5/2")

    def test_大整数不丢精度(self):
        self.assertEqual(engine_py.计算("2 ** 100").值, "1267650600228229401496703205376")
        self.assertEqual(engine_py.计算("factorial(20)").值, "2432902008176640000")
        # 对照：float 装不下 1e16 + 1
        self.assertEqual(1e16 + 1, 1e16)

    def test_完全平方数的开方仍是精确有理数(self):
        结果 = engine_py.计算("sqrt(144)")
        self.assertEqual(结果.值, "12")
        self.assertEqual(结果.数值域, "fraction")

    def test_无理数自动降级到十进制域(self):
        结果 = engine_py.计算("sqrt(2)")
        self.assertEqual(结果.数值域, "decimal")
        self.assertTrue(结果.值.startswith("1.4142135623730950488016887242"))

    def test_运算符优先级与Python一致(self):
        self.assertEqual(engine_py.计算("-2 ** 2").值, "-4")       # 不是 4
        self.assertEqual(engine_py.计算("2 ** 3 ** 2").值, "512")  # 右结合
        self.assertEqual(engine_py.计算("2 + 3 * 4").值, "14")
        self.assertEqual(engine_py.计算("(2 + 3) * 4").值, "20")

    def test_数字字面量从源码文本还原(self):
        """这是整个项目的地基：0.1 不能被先转成 float 再处理。"""
        self.assertEqual(engine_py.计算("1e3").值, "1000")
        self.assertEqual(engine_py.计算("1_000 + 1").值, "1001")
        self.assertEqual(engine_py.计算("0x10 + 1").值, "17")
        self.assertEqual(engine_py.转分数("0.1"), "1/10")
        # 对照：0.1 的二进制浮点真值是 3602879701896397 / 2**55
        分子, 分母 = (0.1).as_integer_ratio()
        self.assertEqual((分子, 分母), (3602879701896397, 36028797018963968))

    def test_舍入不经过float(self):
        self.assertEqual(engine_py.计算("round(1/3, 4)").值, "3333/10000")

    def test_舍入规则两个数值域一致(self):
        """round(2.5) = 3（远离零）。曾经 Fraction 域给 3、Decimal 域
        按银行家舍入给 2，交叉验证误报不一致。"""
        结果 = engine_py.计算("round(2.5)")
        self.assertEqual(结果.值, "3")
        self.assertNotIn("不一致", 结果.交叉验证)

    def test_舍入支持负数位数(self):
        """round(1234, -1) = 1230。曾经 10 ** -1 = 0.1 是 float，
        直接把精确性击穿（AttributeError）。"""
        self.assertEqual(engine_py.计算("round(1234, -1)").值, "1230")

    def test_log是自然对数且支持指定底数(self):
        """曾经 log 被实现成 log10，和 log10 完全重复，log(e) 得 0.4342。"""
        self.assertTrue(engine_py.计算("log(e)").值.startswith("1.000000"))
        self.assertNotEqual(engine_py.计算("log(100)").值,
                            engine_py.计算("log10(100)").值)

    def test_大数输出不受4300位限制(self):
        """Python 3.11+ 的 int->str 默认上限是 4300 位，本工具必须放宽。"""
        结果 = engine_py.计算("2 ** 20000")
        self.assertEqual(len(结果.值), 6021)

    def test_极端指数结果用科学计数法(self):
        """1e999999999 按定点展开会产生上亿个字符，必须改用科学计数法。"""
        self.assertIn("e+", engine_py.计算("1e999999999").值)

    def test_精确比较(self):
        相等, _ = engine_py.精确比较("0.1 + 0.2", "0.3")
        self.assertTrue(相等)
        相等, _ = engine_py.精确比较("1/3", "0.3333333333333333")
        self.assertFalse(相等)


class 测试安全性(unittest.TestCase):
    """AST 白名单是安全边界，每一条都得有测试盯着。"""

    危险表达式 = [
        "__import__('os').system('echo pwned')",
        "open('/etc/passwd')",
        "(1).__class__",
        "[1,2][0]",
        "lambda: 1",
        "{'a': 1}",
        "x + 1",
        "1 if 2 else 3",
        "[x for x in range(3)]",
        "().__class__.__bases__",
        "globals()",
        "eval('1+1')",
        "exec('x=1')",
        "getattr(1, 'real')",
    ]

    def test_危险表达式全部被拒(self):
        for 表达式 in self.危险表达式:
            with self.subTest(表达式=表达式):
                with self.assertRaises(engine_py.计算错误):
                    engine_py.计算(表达式)

    def test_非白名单函数被拒且报错信息准确(self):
        """open('x','w') 应该因为「函数不在白名单」被拒，
        而不是因为字符串参数报一个让人摸不着头脑的错。"""
        with self.assertRaises(engine_py.计算错误) as 上下文:
            engine_py.计算("open('x','w')")
        self.assertIn("白名单", str(上下文.exception))

    def test_除零有明确提示(self):
        with self.assertRaises(engine_py.计算错误) as 上下文:
            engine_py.计算("1 / 0")
        self.assertIn("除数为零", str(上下文.exception))

    def test_min_max零参数被拒(self):
        for 表达式 in ("min()", "max()"):
            with self.subTest(表达式=表达式):
                with self.assertRaises(engine_py.计算错误):
                    engine_py.计算(表达式)

    def test_非整数参数被拒而不是静默截断(self):
        """factorial(3.5) 曾经被 int() 静默截断成 factorial(3) = 6。"""
        for 表达式 in ("factorial(3.5)", "gcd(4.5, 3)", "lcm(2.5, 2)"):
            with self.subTest(表达式=表达式):
                with self.assertRaises(engine_py.计算错误):
                    engine_py.计算(表达式)

    def test_对数定义域有明确提示(self):
        """ln(-1) 曾经在 Decimal 降级路径上抛原生 InvalidOperation，
        而不是计算错误，MCP 工具会崩出难懂的报错。"""
        for 表达式 in ("ln(-1)", "log(0)", "log10(-2)", "log(100, 1)"):
            with self.subTest(表达式=表达式):
                with self.assertRaises(engine_py.计算错误):
                    engine_py.计算(表达式)

    def test_失控表达式被资源护栏拦下(self):
        """2 ** (10 ** 100) 这类表达式不设上限会把机器算死。"""
        with self.assertRaises(engine_py.计算错误):
            engine_py.计算("2 ** (10 ** 100)")
        with self.assertRaises(engine_py.计算错误):
            engine_py.计算("pow(2, 10 ** 100)")
        with self.assertRaises(engine_py.计算错误):
            engine_py.计算("factorial(10000000)")

    def test_语法错误有明确提示(self):
        with self.assertRaises(engine_py.计算错误):
            engine_py.计算("1 +")

    def test_空表达式被拒(self):
        with self.assertRaises(engine_py.计算错误):
            engine_py.计算("   ")


class 测试交叉验证(unittest.TestCase):
    def test_常规表达式两路验证都通过(self):
        结果 = engine_py.计算("0.1 + 0.2")
        self.assertNotIn("不一致", 结果.交叉验证)
        self.assertTrue(结果.可信)

    def test_结果里带上两路验证的说明(self):
        结果 = engine_py.计算("2 ** 10")
        明细 = 结果.as_dict()
        self.assertEqual(明细["value"], "1024")
        for 键 in ("expression", "value", "domain", "exact", "cross_check", "cpp_check"):
            self.assertIn(键, 明细)

    def test_可信属性会识别出不一致(self):
        结果 = engine_py.计算("1 + 1")
        结果.交叉验证 = "不一致 —— 请人工复核"
        self.assertFalse(结果.可信)


@unittest.skipUnless(engine_cpp.可用(), "本机没有 C++ 编译器，跳过 C++ 引擎测试")
class 测试C加加引擎(unittest.TestCase):
    用例 = ["0.1 + 0.2", "1/3 + 1/6", "(1/7) * 7", "2 + 3 * 4",
            "-2 ** 2", "2 ** 3 ** 2", "sqrt(2)", "pi", "10 % 3",
            "log(100)", "log(100, 10)", "round(2.5)"]

    def test_与Python结果一致(self):
        for 表达式 in self.用例:
            with self.subTest(表达式=表达式):
                python值 = engine_py.计算(表达式, 交叉验证=False).值
                说明 = engine_cpp.交叉验证(表达式, python值)
                self.assertIn("通过", 说明, f"{表达式} 两路结果不一致：{说明}")

    def test_超出能力范围时明确跳过而不是误报(self):
        """factorial 只有 Python 引擎实现，C++ 必须老实说「我不管」，
        而不是返回一个错的数字让验证误判为不一致。"""
        说明 = engine_cpp.交叉验证("factorial(5)", "120")
        self.assertIn("已跳过", 说明)

    def test_非法表达式不会崩(self):
        说明 = engine_cpp.交叉验证("1 +", "0")
        self.assertIn("已跳过", 说明)


class 测试模块接口(unittest.TestCase):
    def test_转分数(self):
        self.assertEqual(engine_py.转分数("0.375"), "3/8")
        self.assertEqual(engine_py.转分数("-2.5"), "-5/2")
        self.assertEqual(engine_py.转分数("3"), "3")

    def test_转分数对非法输入报错(self):
        with self.assertRaises(engine_py.计算错误):
            engine_py.转分数("abc")

    def test_转分数拒绝非有限值和极端指数(self):
        """inf 曾经抛原生 OverflowError；1e999999999 会物化十亿位整数卡死。"""
        for 文本 in ("inf", "-inf", "nan", "1e999999999"):
            with self.subTest(文本=文本):
                with self.assertRaises(engine_py.计算错误):
                    engine_py.转分数(文本)

    def test_精度参数校验(self):
        """精度 0 / 负数 / 浮点曾经抛原生 ValueError / TypeError；
        天文数字精度是 DoS 向量。"""
        for 精度 in (0, -5, 50.5, True, 10 ** 9):
            with self.subTest(精度=精度):
                with self.assertRaises(engine_py.计算错误):
                    engine_py.计算("1+1", 精度=精度)

    def test_常数预存1020位(self):
        """pi / e 预存 1020 位有效数字，高精度计算不再是 100 位封顶。"""
        self.assertGreater(len(engine_py.计算("pi").值), 1000)
        self.assertGreater(len(engine_py.计算("e").值), 1000)
        self.assertTrue(engine_py.计算("pi").值.startswith("3.14159265358979323846"))
        self.assertTrue(engine_py.计算("e").值.startswith("2.71828182845904523536"))

    def test_低精度交叉验证仍有分辨力(self):
        """精度 < 10 时容差曾经大到什么都「通过」。"""
        结果 = engine_py.计算("0.1 + 0.2", 精度=5)
        self.assertNotIn("不一致", 结果.交叉验证)

    def test_环境报告结构完整(self):
        报告 = engine_cpp.环境报告()
        for 键 in ("可用", "编译器", "二进制", "说明"):
            self.assertIn(键, 报告)

    def test_精度可调(self):
        粗 = engine_py.计算("1/3", 精度=10)
        细 = engine_py.计算("sqrt(2)", 精度=200)
        self.assertEqual(粗.值, "1/3")          # 有理数不受精度影响
        self.assertGreater(len(细.值), 150)     # 无理数位数随精度增加


if __name__ == "__main__":
    unittest.main(verbosity=2)
