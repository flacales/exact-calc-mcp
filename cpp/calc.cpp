// calc.cpp -- an independent expression evaluator, written from scratch.
//
// Why this file exists:
//   The Python engine computes with Fraction / Decimal and is exact.
//   This one computes with long double and is NOT exact.
//   That is the point. It is a second, independently written implementation
//   whose only job is to disagree loudly if the Python engine is wrong.
//   A bug would have to appear in two separate codebases, in two languages,
//   using two different numeric types, to slip through.
//
// Deliberate differences from the Python engine:
//   - long double (80-bit extended on x86) instead of arbitrary precision
//   - no factorial / gcd / lcm: those stay Python-only, and this program
//     exits with code 2 so the caller skips cross-checking instead of
//     reporting a false mismatch
//   - ASCII-only source. Non-ASCII identifiers are a portability trap:
//     MSVC, clang and gcc each disagree about what a UTF-8 identifier is.
//
// Build:
//   g++ -O2 -std=c++17 -o calc calc.cpp
//
// Usage:
//   ./calc "0.1 + 0.2"
//   echo "2 ** 100" | ./calc
//
// Exit codes:
//   0  computed successfully
//   2  bad expression, or beyond this engine's scope (caller should skip)

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

[[noreturn]] void fail(const std::string& why) {
    throw std::runtime_error(why);
}

long double constant(const std::string& name) {
    if (name == "pi") return 3.14159265358979323846264338327950288L;
    if (name == "e") return 2.71828182845904523536028747135266250L;
    fail("unknown constant: " + name);
}

// Named call_function, not apply: an unqualified call with a std::vector
// argument drags std::apply in through ADL and it fails to compile.
long double call_function(const std::string& name,
                          const std::vector<long double>& args) {
    auto need = [&](std::size_t n) {
        if (args.size() != n) {
            fail(name + " takes " + std::to_string(n) + " argument(s), got " +
                 std::to_string(args.size()));
        }
    };

    if (name == "sqrt") {
        need(1);
        if (args[0] < 0) fail("sqrt of a negative number");
        return sqrtl(args[0]);
    }
    if (name == "abs")   { need(1); return fabsl(args[0]); }
    if (name == "pow")   { need(2); return powl(args[0], args[1]); }
    if (name == "exp")   { need(1); return expl(args[0]); }
    if (name == "ln")    { need(1); if (args[0] <= 0) fail("ln domain error");    return logl(args[0]); }
    if (name == "log") {
        // Natural log, like Python's math.log; log(x, base) for a custom base.
        if (args.size() == 1) { if (args[0] <= 0) fail("log domain error"); return logl(args[0]); }
        need(2);
        if (args[0] <= 0 || args[1] <= 0 || args[1] == 1) fail("log domain error");
        return logl(args[0]) / logl(args[1]);
    }
    if (name == "log10") { need(1); if (args[0] <= 0) fail("log10 domain error"); return log10l(args[0]); }
    if (name == "round") { need(1); return roundl(args[0]); }
    if (name == "min") {
        if (args.empty()) fail("min needs at least one argument");
        return *std::min_element(args.begin(), args.end());
    }
    if (name == "max") {
        if (args.empty()) fail("max needs at least one argument");
        return *std::max_element(args.begin(), args.end());
    }
    fail("function not supported by the C++ engine: " + name);
}

// Recursive descent parser. Precedence matches Python exactly:
//   expr    := term (('+' | '-') term)*
//   term    := unary (('*' | '/' | '%') unary)*
//   unary   := ('+' | '-') unary | power
//   power   := primary ['**' unary]        <- right associative
//   primary := number | constant | call | '(' expr ')'
//
// Matching Python's precedence matters: -2 ** 2 is -4 in Python, not 4.
class Parser {
public:
    explicit Parser(const char* src) : p_(src) {}

    long double parse() {
        long double v = expr();
        skip();
        if (*p_ != '\0') fail(std::string("trailing input: ") + p_);
        return v;
    }

private:
    const char* p_;

    void skip() {
        while (*p_ == ' ' || *p_ == '\t' || *p_ == '\n' || *p_ == '\r') ++p_;
    }

    bool eat(char c) {
        skip();
        if (*p_ == c) { ++p_; return true; }
        return false;
    }

    long double expr() {
        long double v = term();
        for (;;) {
            if (eat('+'))      v += term();
            else if (eat('-')) v -= term();
            else               return v;
        }
    }

    long double term() {
        long double v = unary();
        for (;;) {
            skip();
            if (*p_ == '*' && *(p_ + 1) == '*') return v;  // '**' belongs to power()
            if (*p_ == '*') {
                ++p_;
                v *= unary();
            } else if (*p_ == '/') {
                ++p_;
                long double d = unary();
                if (d == 0) fail("division by zero");
                v /= d;
            } else if (*p_ == '%') {
                ++p_;
                long double d = unary();
                if (d == 0) fail("modulo by zero");
                v = fmodl(v, d);
            } else {
                return v;
            }
        }
    }

    long double unary() {
        if (eat('+')) return unary();
        if (eat('-')) return -unary();
        return power();
    }

    long double power() {
        long double base = primary();
        skip();
        if ((*p_ == '*' && *(p_ + 1) == '*') || *p_ == '^') {
            p_ += (*p_ == '^') ? 1 : 2;
            return powl(base, unary());  // right associative: 2**3**2 == 2**(3**2)
        }
        return base;
    }

    long double primary() {
        skip();
        if (*p_ == '(') {
            ++p_;
            long double v = expr();
            if (!eat(')')) fail("missing closing parenthesis");
            return v;
        }
        if (std::isalpha(static_cast<unsigned char>(*p_))) return name();
        return number();
    }

    long double name() {
        std::string n;
        while (std::isalnum(static_cast<unsigned char>(*p_)) || *p_ == '_') n += *p_++;
        skip();
        if (*p_ != '(') return constant(n);  // not a call, so it is a constant

        ++p_;
        std::vector<long double> args;
        if (!eat(')')) {
            args.push_back(expr());
            while (eat(',')) args.push_back(expr());
            if (!eat(')')) fail("missing closing parenthesis");
        }
        return call_function(n, args);
    }

    long double number() {
        skip();
        char* end = nullptr;
        long double v = strtold(p_, &end);
        if (end == p_) fail(std::string("expected a number, found: ") + p_);
        p_ = end;
        return v;
    }
};

}  // namespace

int main(int argc, char** argv) {
    std::string src;
    if (argc > 1) {
        src = argv[1];
    } else {
        std::getline(std::cin, src);
    }

    // Drop Python-style digit separators: 1_000 -> 1000
    std::string cleaned;
    cleaned.reserve(src.size());
    for (char c : src) {
        if (c != '_') cleaned += c;
    }

    try {
        Parser parser(cleaned.c_str());
        long double result = parser.parse();
        if (std::isnan(result) || std::isinf(result)) fail("result is NaN or infinite");
        std::printf("%.18Lg\n", result);
        return 0;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "error: %s\n", e.what());
        return 2;
    }
}
