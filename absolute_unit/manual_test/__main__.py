from result import Err
from rich.pretty import pprint
from absolute_unit.conversion import try_convert_expression

if __name__ == "__main__":
    while inp := input().rstrip():
        result = try_convert_expression(inp)
        if isinstance(result, Err):
            print(result.err())
        else:
            expr, converted = result.ok()
            print("-------------")
            pprint(expr)
            print(expr, "=", converted, sep="\n")
