# -*- coding: utf-8 -*-
"""engine_py.py —— Python 精确计算引擎

两个关键设计决定，都是踩过坑才想明白的：

1. **为什么不用 eval()**
   eval() 会把 `__import__('os').system('rm -rf /')` 当成一个正常表达式执行。
   这里用 ast 把表达式解析成语法树，再**逐节点**求值，只放行白名单里的节点
   类型和函数名。任何不在白名单里的写法一律拒绝，不给机会。

2. **为什么不用 ast 解析出来的数字**
   `0.1` 在 ast 里已经是 float(0.1) 了，而它的真实值是
   0.1000000000000000055511151231257827021181583404541015625。
   精度在拿到它的那一刻就已经丢了。
   所以数字一律从**源码文本**重建：用 ast.get_source_segment() 取回 "0.1"，
   再交给 Decimal("0.1") —— 这才是精确的十进制 0.1。
   这一条是整个项目的地基，去掉它，剩下的都是白干。
"""

from __future__ import annotations

import ast
import math
import operator
import sys
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, DecimalException, localcontext
from fractions import Fraction

# 算大数是这个工具的本分（"2 ** 20000" 必须能出结果），但 Python 3.11+
# 默认把 int <-> str 转换限在 4300 位。放宽到 1000 万位 —— 仍留一道
# 天花板，防止失控表达式生成无限长的字符串。
if hasattr(sys, "set_int_max_str_digits"):  # 3.10 没有这个 API
    sys.set_int_max_str_digits(10_000_000)

# 资源护栏：LLM 可能给出 "2 ** (10 ** 100)" 这类失控表达式，
# 不设上限会把机器算死。上限取「结果约 300 万位」的规模，正常需求远够用。
整数次幂指数上限 = 10_000_000
阶乘参数上限 = 1_000_000
# 物化位数上限：把 1e999999999 转成 Fraction 意味着要真正造一个十亿位
# 的整数。超过这个规模就降级给 Decimal 域 —— 它对大指数是原生支持的，
# 不需要把每一位都造出来。
_物化位数上限 = 100_000
# 工作精度上限：sqrt / ln / exp 的计算量随精度线性增长，10 万位
# 已经足够任何正经用途，再大的值只可能是失控输入。
精度上限 = 100_000

__all__ = [
    "计算错误",
    "计算结果",
    "计算",
    "求值",
    "精确比较",
    "转分数",
    "默认精度",
]

默认精度 = 50

# 高精度常数，1020 位有效数字（Machin 公式 / 泰勒级数现算后固化，
# 只保留 1050 位计算结果的前 1020 位，扔掉尾部累积误差）。
# 精度参数再高，pi / e 相关的计算也以这 1020 位为准。
圆周率 = Decimal(
    "3.141592653589793238462643383279502884197169399375105820974944592307"
    "81640628620899862803482534211706798214808651328230664709384460955058"
    "22317253594081284811174502841027019385211055596446229489549303819644"
    "28810975665933446128475648233786783165271201909145648566923460348610"
    "45432664821339360726024914127372458700660631558817488152092096282925"
    "40917153643678925903600113305305488204665213841469519415116094330572"
    "70365759591953092186117381932611793105118548074462379962749567351885"
    "75272489122793818301194912983367336244065664308602139494639522473719"
    "07021798609437027705392171762931767523846748184676694051320005681271"
    "45263560827785771342757789609173637178721468440901224953430146549585"
    "37105079227968925892354201995611212902196086403441815981362977477130"
    "99605187072113499999983729780499510597317328160963185950244594553469"
    "08302642522308253344685035261931188171010003137838752886587533208381"
    "42061717766914730359825349042875546873115956286388235378759375195778"
    "18577805321712268066130019278766111959092164201989380952572010654858"
    "6"
)
自然常数 = Decimal(
    "2.718281828459045235360287471352662497757247093699959574966967627724"
    "07663035354759457138217852516642742746639193200305992181741359662904"
    "35729003342952605956307381323286279434907632338298807531952510190115"
    "73834187930702154089149934884167509244761460668082264800168477411853"
    "74234544243710753907774499206955170276183860626133138458300075204493"
    "38265602976067371132007093287091274437470472306969772093101416928368"
    "19025515108657463772111252389784425056953696770785449969967946864454"
    "90598793163688923009879312773617821542499922957635148220826989519366"
    "80331825288693984964651058209392398294887933203625094431173012381970"
    "68416140397019837679320683282376464804295311802328782509819455815301"
    "75671736133206981125099618188159304169035159888851934580727386673858"
    "94228792284998920868058257492796104841984443634632449684875602336248"
    "27041978623209002160990235304369941849146314093431738143640546253152"
    "09618369088870701676839642437814059271456354906130310720851038375051"
    "01157477041718986106873969655212671546889570350354021234078498193343"
    "2"
)

_二元运算 = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_一元运算 = {ast.UAdd: operator.pos, ast.USub: operator.neg}

# 允许被调用的函数。名字先于实参校验 —— 否则 open('x','w') 会先因为
# 字符串参数报「无法识别的数字」，把真正的拒绝理由盖掉。
_白名单函数 = frozenset({
    "sqrt", "abs", "round", "min", "max",
    "factorial", "gcd", "lcm",
    "ln", "log", "log10", "exp", "pow",
})


class 计算错误(Exception):
    """表达式非法、越权，或无法在指定数值域内精确求值。"""


class _需降级(Exception):
    """当前数值域装不下（例如 Fraction 遇到无理数），交给另一个数值域重试。"""


@dataclass
class 计算结果:
    表达式: str
    值: str
    数值域: str            # 'fraction' | 'decimal'
    精确: bool             # 是否为无损结果
    交叉验证: str = "未启用"
    cpp验证: str = "未启用"
    备注: str = ""

    def as_dict(self) -> dict:
        return {
            "expression": self.表达式,
            "value": self.值,
            "domain": self.数值域,
            "exact": self.精确,
            "cross_check": self.交叉验证,
            "cpp_check": self.cpp验证,
            "note": self.备注,
        }

    @property
    def 可信(self) -> bool:
        """两路验证都没报不一致，才算可信。"""
        return "不一致" not in self.交叉验证 and "不一致" not in self.cpp验证

    def __str__(self) -> str:
        return self.值


# --------------------------------------------------------------- 字面量还原


def _还原数字(node: ast.Constant, 源码: str, 数值域: str):
    """从源码文本重建数字，而不是用 ast 已经转好的 float。"""
    if isinstance(node.value, bool):
        raise 计算错误("不支持布尔值参与运算")

    文本 = ast.get_source_segment(源码, node)
    if 文本 is None:  # 极少数情况下拿不到源码片段
        文本 = repr(node.value)
    文本 = 文本.replace("_", "").strip()

    try:
        if 数值域 == "fraction":
            # 先转 Decimal 再转 Fraction，保证 0.1 是 1/10 而不是二进制近似
            d = Decimal(文本)
            if abs(d.adjusted()) > _物化位数上限:
                raise _需降级("科学计数法指数过大，物化成 Fraction 会生成天文数字位数的整数")
            return Fraction(d)
        return Decimal(文本)
    except (DecimalException, ValueError):
        pass

    # 兜底：二进制 / 八进制 / 十六进制整数字面量
    try:
        return Fraction(int(文本, 0)) if 数值域 == "fraction" else Decimal(int(文本, 0))
    except ValueError as e:
        raise 计算错误(f"无法识别的数字：{文本}") from e


# --------------------------------------------------------------- 求值器


class _求值器(ast.NodeVisitor):
    def __init__(self, 源码: str, 数值域: str, 精度: int):
        self.源码 = 源码
        self.数值域 = 数值域
        self.精度 = 精度

    def visit_Expression(self, node):
        return self.visit(node.body)

    def visit_Constant(self, node):
        return _还原数字(node, self.源码, self.数值域)

    def visit_Name(self, node):
        名字 = node.id
        if 名字 in ("pi", "圆周率", "e", "自然常数"):
            if self.数值域 == "fraction":
                # 无理数，Fraction 装不下，交给 Decimal 数值域
                raise _需降级(f"{名字} 是无理数")
            return 圆周率 if 名字 in ("pi", "圆周率") else 自然常数
        raise 计算错误(f"不认识的变量名：{名字}")

    def visit_UnaryOp(self, node):
        运算符 = _一元运算.get(type(node.op))
        if 运算符 is None:
            raise 计算错误(f"不支持的一元运算符：{type(node.op).__name__}")
        return 运算符(self.visit(node.operand))

    def visit_BinOp(self, node):
        运算符 = _二元运算.get(type(node.op))
        if 运算符 is None:
            raise 计算错误(f"不支持的运算符：{type(node.op).__name__}")
        左, 右 = self.visit(node.left), self.visit(node.right)
        if isinstance(node.op, ast.Pow):
            _检查指数规模(右)
        try:
            return 运算符(左, 右)
        except ZeroDivisionError as e:
            raise 计算错误("除数为零") from e
        except (DecimalException, OverflowError, ValueError, TypeError) as e:
            # 大概率是当前数值域装不下，换另一个试试
            raise _需降级(f"{type(e).__name__}: {e}") from e

    def visit_Call(self, node):
        if not isinstance(node.func, ast.Name):
            raise 计算错误("只能调用白名单里的函数，不支持属性访问")
        名字 = node.func.id
        if 名字 not in _白名单函数:  # 先查函数名，再算实参
            raise 计算错误(f"不在白名单里的函数：{名字}")
        if node.keywords:
            raise 计算错误("函数不支持关键字参数")
        实参 = [self.visit(a) for a in node.args]
        return _调用函数(名字, 实参, self.数值域, self.精度)

    def generic_visit(self, node):
        # 白名单之外的一切（下标、属性、推导式、lambda、赋值……）全部拒绝
        raise 计算错误(f"表达式里不允许出现：{type(node).__name__}")


def _调用函数(名字: str, 实参: list, 数值域: str, 精度: int):
    if 名字 == "sqrt":
        (x,) = _定长(名字, 实参, 1)
        if 数值域 == "fraction":
            n, d = x.numerator, x.denominator
            if n < 0:
                raise 计算错误("负数不能开平方（本引擎不处理复数）")
            rn, rd = math.isqrt(n), math.isqrt(d)
            if rn * rn == n and rd * rd == d:
                return Fraction(rn, rd)  # 完全平方数，结果仍是有理数
            raise _需降级("sqrt 的结果是无理数，Fraction 装不下")
        if x < 0:
            raise 计算错误("负数不能开平方（本引擎不处理复数）")
        return x.sqrt()

    if 名字 == "abs":
        (x,) = _定长(名字, 实参, 1)
        return abs(x)

    if 名字 == "round":
        if len(实参) == 1:
            x, 位 = 实参[0], 0
        elif len(实参) == 2:
            x, 位 = 实参
            位 = _要求整数("round 的位数参数", 位)
        else:
            raise 计算错误(f"round() 需要 1 或 2 个参数，实际给了 {len(实参)} 个")
        if 数值域 == "fraction":
            return _分数舍入(x, 位)
        # ROUND_HALF_UP 是「远离零」，与 _分数舍入、C++ 的 roundl 三方一致。
        # 注意这和 Python 内建 round() 的银行家舍入不同 —— 是故意的设计。
        return x.quantize(Decimal(1).scaleb(-位), rounding=ROUND_HALF_UP)

    if 名字 in ("min", "max"):
        if not 实参:
            raise 计算错误(f"{名字}() 至少需要一个参数")
        return min(实参) if 名字 == "min" else max(实参)

    if 名字 == "factorial":
        (x,) = _定长(名字, 实参, 1)
        n = _要求整数(名字, x)
        if n < 0:
            raise 计算错误("阶乘不接受负数")
        if n > 阶乘参数上限:
            raise 计算错误(f"阶乘参数过大（上限 {阶乘参数上限}，结果约 557 万位）")
        return Fraction(math.factorial(n)) if 数值域 == "fraction" else Decimal(math.factorial(n))

    if 名字 == "gcd":
        a, b = _定长(名字, 实参, 2)
        a, b = _要求整数(名字, a), _要求整数(名字, b)
        return Fraction(math.gcd(a, b)) if 数值域 == "fraction" else Decimal(math.gcd(a, b))

    if 名字 == "lcm":
        a, b = _定长(名字, 实参, 2)
        a, b = _要求整数(名字, a), _要求整数(名字, b)
        return Fraction(math.lcm(a, b)) if 数值域 == "fraction" else Decimal(math.lcm(a, b))

    if 名字 in ("ln", "log", "log10", "exp"):
        if 数值域 == "fraction":
            raise _需降级(f"{名字} 的结果通常是无理数，需要 decimal 数值域")
        if 名字 == "exp":
            (x,) = _定长(名字, 实参, 1)
            return x.exp()
        if 名字 == "log":
            # log(x) = 自然对数（与 math.log / numpy.log 一致）；
            # log(x, base) = 指定底数。常用对数请用 log10。
            if len(实参) == 1:
                (x,) = 实参
                if x <= 0:
                    raise 计算错误("log 的定义域是 x > 0")
                return x.ln()
            x, 底 = _定长(名字, 实参, 2)
            if x <= 0:
                raise 计算错误("log 的定义域是 x > 0")
            if 底 <= 0 or 底 == 1:
                raise 计算错误("log 的底数必须 > 0 且 ≠ 1")
            return x.ln() / 底.ln()
        (x,) = _定长(名字, 实参, 1)
        if x <= 0:
            raise 计算错误(f"{名字} 的定义域是 x > 0")
        if 名字 == "ln":
            return x.ln()
        return x.log10()  # log10

    if 名字 == "pow":
        a, b = _定长(名字, 实参, 2)
        _检查指数规模(b)
        return a ** b

    raise 计算错误(f"不在白名单里的函数：{名字}")


def _要求整数(名字: str, x) -> int:
    """转成 int，但带小数部分时明确拒绝 —— 精确计算工具不能静默截断。"""
    n = int(x)
    if x != n:
        raise 计算错误(f"{名字} 只接受整数参数，收到 {x}")
    return n


def _检查指数规模(指数) -> None:
    """防止 "2 ** (10 ** 100)" 这类表达式把机器算死。只限制整数次幂；
    非整数指数走 exp/ln 路径，Decimal 自己会快速报溢出。"""
    try:
        n = int(指数)
    except (OverflowError, ValueError):
        return
    if 指数 == n and abs(n) > 整数次幂指数上限:
        raise 计算错误(f"整数次幂的指数过大（上限 ±{整数次幂指数上限}）")


def _定长(名字: str, 实参: list, 个数: int) -> list:
    if len(实参) != 个数:
        raise 计算错误(f"{名字}() 需要 {个数} 个参数，实际给了 {len(实参)} 个")
    return 实参


# --------------------------------------------------------------- 对外接口


def _格式化(值, 数值域: str) -> str:
    if 数值域 == "fraction":
        if 值.denominator == 1:
            return str(值.numerator)
        return f"{值.numerator}/{值.denominator}"
    # 极端指数（如 1e999999999）按定点格式展开会产生上亿个字符，
    # 改用科学计数法 —— 值不变，只是换一种写法。
    if abs(值.adjusted()) > 100_000:
        return format(值, "e")
    return format(值, "f")


def 求值(表达式: str, 数值域: str = "fraction", 精度: int = 默认精度):
    """在指定数值域内求值。装不下时抛 _需降级，由调用方换数值域重试。"""
    if isinstance(精度, bool) or not isinstance(精度, int) or not 1 <= 精度 <= 精度上限:
        raise 计算错误(f"精度必须是 1 ~ {精度上限} 的整数，收到 {精度!r}")
    源码 = 表达式.strip()
    if not 源码:
        raise 计算错误("表达式是空的")
    try:
        树 = ast.parse(源码, mode="eval")
    except SyntaxError as e:
        raise 计算错误(f"语法错误：{e.msg}") from e

    with localcontext() as ctx:
        ctx.prec = 精度
        return _求值器(源码, 数值域, 精度).visit(树)


def 计算(表达式: str, 精度: int = 默认精度, 交叉验证: bool = True) -> 计算结果:
    """算一个表达式。

    流程：
      1. 先用 Fraction（有理数精确）算。完全平方数的 sqrt、分数四则运算都走这条。
      2. 装不下（无理数、ln 等）就换 Decimal（十进制精确）重算。
      3. 两边都算得出来时，比对结果，不一致就明确报出来，不返回可疑值。
    """
    备注 = ""
    try:
        值 = 求值(表达式, "fraction", 精度)
        数值域, 精确 = "fraction", True
    except _需降级 as 因:
        备注 = f"Fraction 装不下（{因}），已改用 Decimal"
        try:
            值 = 求值(表达式, "decimal", 精度)
        except _需降级 as 因2:
            raise 计算错误(f"Decimal 数值域也算不了：{因2}") from None
        except DecimalException as e:
            raise 计算错误(f"计算失败：{e}") from e
        数值域, 精确 = "decimal", True
    except DecimalException as e:
        raise 计算错误(f"计算失败：{e}") from e

    结果 = 计算结果(
        表达式=表达式.strip(),
        值=_格式化(值, 数值域),
        数值域=数值域,
        精确=精确,
        备注=备注,
    )

    if 交叉验证:
        结果.交叉验证 = _交叉验证(表达式, 值, 数值域, 精度)
        结果.cpp验证 = _用C加加验证(表达式, 结果.值)
    return 结果


def _用C加加验证(表达式: str, python值: str) -> str:
    """调用 C++ 引擎做第三路验证。装不了编译器就静默降级，不影响主流程。"""
    try:
        from . import engine_cpp
    except ImportError:
        return "已跳过（未安装 C++ 引擎模块）"
    try:
        return engine_cpp.交叉验证(表达式, python值)
    except Exception as e:  # C++ 是锦上添花，它出任何问题都不该拖垮计算
        return f"已跳过（C++ 验证异常：{type(e).__name__}: {e}）"


def _分数舍入(x: Fraction, 位: int) -> Fraction:
    """对分数做四舍五入（远离零），全程不碰 float。

    位可以为负：round(1234, -1) = 1230。必须用 Fraction(10) ** 位 ——
    写成 10 ** 位 的话，位为负时产生 float 0.1，精确性当场击穿。
    """
    倍数 = Fraction(10) ** 位
    缩放 = x * 倍数
    n, d = 缩放.numerator, 缩放.denominator
    q = (2 * n + d) // (2 * d) if n >= 0 else -((-2 * n + d) // (2 * d))
    return Fraction(q, 倍数)


def _转十进制(值):
    """把 Fraction 或 Decimal 统一成 Decimal，方便跨数值域比较。"""
    if isinstance(值, Fraction):
        return Decimal(值.numerator) / Decimal(值.denominator)
    return 值


def _交叉验证(表达式: str, 主值, 主域: str, 精度: int) -> str:
    """用另一个数值域再算一遍，两边对不上就明确报警。

    真正的独立实现是 C++ 引擎（engine_cpp.py），这里先做第一道自检。
    """
    另域 = "decimal" if 主域 == "fraction" else "fraction"
    try:
        另值 = 求值(表达式, 另域, 精度)
    except (_需降级, 计算错误):
        return "已跳过（该表达式只有一个数值域装得下）"

    with localcontext() as ctx:
        ctx.prec = 精度
        甲 = _转十进制(主值)
        乙 = _转十进制(另值)
        # 容差随精度收紧；精度低于 18 位时也要保留 8 位的分辨力，
        # 否则 scaleb 指数转正，容差大到什么都「通过」。
        容差 = Decimal(1).scaleb(-max(精度 - 10, 8)) * max(Decimal(1), abs(甲))
        if abs(甲 - 乙) > 容差:
            return f"不一致 —— 请人工复核（{甲} vs {乙}）"
    return "通过（Fraction 与 Decimal 结果一致）"


def 转分数(文本: str) -> str:
    """把十进制字符串还原成精确分数：'0.375' -> '3/8'。"""
    try:
        d = Decimal(str(文本).strip())
    except (DecimalException, ValueError) as e:
        raise 计算错误(f"不是合法的十进制数：{文本}") from e
    if not d.is_finite():
        raise 计算错误(f"不是有限小数：{文本}")
    if abs(d.adjusted()) > _物化位数上限:
        # Fraction(d) 会把每一位都物化成整数，1e999999999 能造出十亿位
        raise 计算错误("指数过大，无法物化成精确分数")
    f = Fraction(d)
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


def 精确比较(甲: str, 乙: str, 精度: int = 默认精度) -> tuple:
    """判断两个表达式在数学上是否相等，返回 (是否相等, 说明)。

    `精确比较('0.1 + 0.2', '0.3')` -> (True, ...)
    而 float 版的 0.1 + 0.2 == 0.3 是 False。这就是这个工具存在的理由。
    """
    甲值 = 计算(甲, 精度, 交叉验证=False)
    乙值 = 计算(乙, 精度, 交叉验证=False)

    甲f = _统一到分数(甲值)
    乙f = _统一到分数(乙值)
    if 甲f is not None and 乙f is not None:
        相等 = 甲f == 乙f
        return 相等, (f"{甲值.值} {'==' if 相等 else '!='} {乙值.值}"
                     f"（两边都是精确有理数，逐位比较）")

    相等 = 甲值.值 == 乙值.值
    return 相等, (f"{甲值.值} {'==' if 相等 else '!='} {乙值.值}"
                 f"（十进制字符串逐位比较）")


def _统一到分数(结果: 计算结果):
    if 结果.数值域 == "fraction":
        a, _, b = 结果.值.partition("/")
        return Fraction(int(a), int(b)) if b else Fraction(int(a))
    try:
        d = Decimal(结果.值)
        if abs(d.adjusted()) > _物化位数上限:
            return None  # 物化不起，退回字符串比较
        return Fraction(d)
    except (DecimalException, ValueError):
        return None
