from result import Err
from rich.pretty import pprint
from absolute_unit.conversion import try_convert_expression

if __name__ == "__main__":
    while inp := input().rstrip():
        target = input() or None
        result = try_convert_expression(inp, target)
        if isinstance(result, Err):
            print(result.err())
        else:
            expr, converted = result.ok()
            print("-------------")
            pprint(expr)
            print(expr, "=", converted, sep="\n")
