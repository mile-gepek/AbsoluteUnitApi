from result import Err
from rich.pretty import pprint
from absolute_unit import conversion

if __name__ == "__main__":
    while inp := input().rstrip():
        expr_res = conversion.parse_input(inp)
        if isinstance(expr_res, Err):
            print(expr_res.err())
            continue
        expr = expr_res.ok()

        eval_res = conversion.evaluate_expression(expr)
        if isinstance(eval_res, Err):
            print(eval_res.err())
            continue
        eval = eval_res.ok()

        target = input() or None
        if target is None:
            target_unit_res = conversion.infer_target_unit(eval)
        else:
            target_unit_res = conversion.get_target_unit(target)
        if isinstance(target_unit_res, Err):
            print(target_unit_res.err())
            continue
        target_unit = target_unit_res.ok()

        converted_res = conversion.convert(eval, target_unit)
        if isinstance(converted_res, Err):
            print(converted_res.err())
            continue

        converted = converted_res.ok()
        print("-------------")
        pprint(expr)
        print(expr, "=", converted, sep="\n")
