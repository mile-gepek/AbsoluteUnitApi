import sys
sys.tracebacklimit = 1

from pint import UnitRegistry

ureg = UnitRegistry(None)

ureg.define('foo = 2 * bar')
foo_quantity = ureg.Quantity('foo')
bar_quantity = foo_quantity.to('bar')
print(bar_quantity)
