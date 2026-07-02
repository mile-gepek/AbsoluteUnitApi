"""
This module is used for parsing user input from commands
"""

from __future__ import annotations

import abc
import enum
import operator
import re
import string
from collections import deque
from collections.abc import Callable, Generator
from typing import ClassVar, Self, overload, override

import pint
import rich.repr
from pint.facets.plain import PlainQuantity
from pint.util import UnitsContainer
from pydantic import BaseModel, Field, computed_field
from result import Err, Ok, Result

__all__ = [
    "tokenize",
    "Parser",
    "ParserMode",
    "Error",
    "ParsingError",
    "EvaluationError",
    "EOL",
    "_EOL",
]


class _EOL(BaseModel):
    """
    Marker for end-of-line token/expression spans.

    Used when reporting errors such as expecting expressions after an operator.
    When printing out errors, this should be remapped to the length of the input.
    """

    # This is probably a dumb way to do this, but I didn't know how else to.

    @override
    def __repr__(self) -> str:
        return "EOF"


EOL = _EOL()


class CharStream:
    """
    A peekable iterator of characters from the given input string, also with a manual `advance` method.
    """

    def __init__(self, string: str) -> None:
        self._string: str = string
        self._i: int = 0

    @property
    def position(self) -> int:
        return self._i

    def peek(self) -> str | None:
        if self._i >= len(self._string):
            return None
        return self._string[self._i]

    def advance(self) -> None:
        if self._i < len(self._string):
            self._i += 1

    def __next__(self) -> str:
        char = self.peek()
        self.advance()
        if char is None:
            raise StopIteration
        return char

    def __iter__(self) -> Self:
        return self

    def __bool__(self) -> bool:
        return bool(self._string)


class Token(abc.ABC):
    """
    Base class for all Token types.

    Tokenization is implemented via the `consume` method (overriden if certain Tokens want to).
    Tokens are "registered" using the `__init_subclass__` hook, which stores all token types and a total alphabet (used for discovering unknown tokens).
    """

    total_alphabet: ClassVar[str] = ""
    """
    A string containing all possible expression characters.
    When a token is created with `Tokem.from_stream` and the first character from the stream isn't recognized, it returns an UnknownToken.
    """
    token_types: ClassVar[list[type[Self]]] = []

    def __init__(self, token: str, start: int, end: int) -> None:
        self._token: str = token
        self._start: int = start
        self._end: int = end

    @classmethod
    def from_stream(cls, stream: CharStream) -> Token | None:
        """
        Peek into the stream and return a Token depending on the character.
        The token type is decided based on it's `default_alphabet`, or UnknownToken if none of the match.
        """
        char = stream.peek()
        if char is None:
            return None

        # Any unknown character (not "registered" from any of the token subclasses)
        if char not in cls.total_alphabet:
            start = stream.position
            token_str = UnknownToken.consume(stream)
            return UnknownToken(token_str, start, stream.position)

        for token_type in cls.token_types:
            alphabet = token_type.default_alphabet()
            if alphabet is not None and char in alphabet:
                start = stream.position
                token = token_type.consume(stream)
                return token_type(token, start, stream.position)

    @property
    def token(self) -> str:
        return self._token

    @property
    def start(self) -> int:
        """
        The start of this token in the input string.
        """
        # TODO: Tokens (and expressions) currently don't hold a reference to the input string, this should be changed.

        return self._start

    @property
    def end(self) -> int:
        """
        The end of this token in the input string.
        """
        # TODO: Tokens (and expressions) currently don't hold a reference to the input string, this should be changed.

        return self._end

    def span(self) -> tuple[int, int]:
        return (self._start, self._end)

    @staticmethod
    @abc.abstractmethod
    def default_alphabet() -> str | None:
        return None

    @classmethod
    def alphabet(cls, curr_token: str) -> str | None:
        """
        Context-dependant alphabet.
        Certain Tokens, such as `OperatorToken`s want to change their alphabet depending on the characters they've already consumed.

        # Example
        An operator token that has already accepted the character '*', can accept another '*' to make exponentiation.
        """
        return cls.default_alphabet()

    @classmethod
    def consume(cls, stream: CharStream) -> str:
        """
        The standard way of grabbing a token from a stream, used by most Token types.
        Consumes stream characters one by one, stopping when it finds a character which isn't in the Token's `alphabet`.

        Subclasses (concrete token types) can override this method, such as WhitespaceToken or UnknownToken.
        """
        token = ""
        while (char := stream.peek()) is not None:
            alphabet = cls.alphabet(token)
            if alphabet is None or char not in alphabet:
                break
            token += char
            stream.advance()
        return token

    def __init_subclass__(cls) -> None:
        alphabet = cls.default_alphabet()
        if alphabet is None:
            return
        Token.token_types.append(cls)
        Token.total_alphabet += alphabet

    @override
    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self._token}, {self.span()})"

    @override
    def __repr__(self) -> str:
        return str(self)

    @classmethod
    @abc.abstractmethod
    def repr_name(cls) -> str: ...


class FloatToken(Token):
    """
    Accepts numbers with the following forms:
    - '1'
    - '1.'
    - '1.2'
    - '.2'
    """

    @override
    @staticmethod
    def default_alphabet() -> str:
        return string.digits + "."

    @override
    @classmethod
    def alphabet(cls, curr_token: str) -> str:
        """
        Used to check if the float token already contains a dot.
        """
        if "." in curr_token:
            return string.digits
        return cls.default_alphabet()

    def to_float(self) -> float:
        return float(self._token)

    @override
    @classmethod
    def repr_name(cls) -> str:
        return "number"


class UnitToken(Token):
    """
    Units to be used for the pint library.

    NOTE: The units are not checked during tokenization, these represent any ascii string
    """

    @override
    @staticmethod
    def default_alphabet() -> str:
        return string.ascii_letters + "_"

    @override
    @classmethod
    def repr_name(cls) -> str:
        return "unit"


class ParenType(enum.Enum):
    L_PAREN = "("
    R_PAREN = ")"

    L_BRACKET = "["
    R_BRACKET = "]"

    L_BRACE = "{"
    R_BRACE = "}"

    def is_opening(self) -> bool:
        return self in [ParenType.L_PAREN, ParenType.L_BRACKET, ParenType.L_BRACE]

    def paren_name(self) -> str:
        match self:
            case ParenType.L_PAREN:
                return "opening parenthesis"
            case ParenType.R_PAREN:
                return "closing parenthesis"
            case ParenType.L_BRACKET:
                return "opening bracket"
            case ParenType.R_BRACKET:
                return "closing bracket"
            case ParenType.L_BRACE:
                return "opening brace"
            case ParenType.R_BRACE:
                return "closing brace"

    def is_pair(self, other: ParenType) -> bool:
        """
        Return True if `self` and `other` are pairs e.g. "[" forms a pair with "]", but not itself
        """
        match self:
            case ParenType.L_PAREN:
                return ParenType.R_PAREN == other
            case ParenType.R_PAREN:
                return ParenType.L_PAREN == other
            case ParenType.L_BRACKET:
                return ParenType.R_BRACKET == other
            case ParenType.R_BRACKET:
                return ParenType.L_BRACKET == other
            case ParenType.L_BRACE:
                return ParenType.R_BRACE == other
            case ParenType.R_BRACE:
                return ParenType.L_BRACE == other

    def to_pair(self) -> tuple[ParenType, ParenType]:
        """Return a tuple of the paren pairs matching self"""
        match self:
            case ParenType.L_PAREN | ParenType.R_PAREN:
                return (ParenType.L_PAREN, ParenType.R_PAREN)
            case ParenType.L_BRACKET | ParenType.R_BRACKET:
                return (ParenType.L_BRACKET, ParenType.R_BRACKET)
            case ParenType.L_BRACE | ParenType.R_BRACE:
                return (ParenType.L_BRACE, ParenType.R_BRACE)


class ParenToken(Token):
    def __init__(self, token: str, start: int, end: int) -> None:
        super().__init__(token, start, end)
        # This is a bit scuffed because it takes a string, but tokenization depends on that anyway.
        # Maybe refactor to only accept ParenType directly.
        self._paren_type: ParenType = ParenType(token)

    @override
    @staticmethod
    def default_alphabet() -> str:
        return "()[]{}"

    @override
    @classmethod
    def alphabet(cls, curr_token: str) -> str:
        if curr_token:
            return ""
        return cls.default_alphabet()

    @property
    def paren_type(self) -> ParenType:
        return self._paren_type

    @override
    @classmethod
    def repr_name(cls) -> str:
        return "group expression"


class OperatorType(enum.Enum):
    ADD = "+"
    SUB = "-"
    MUL = "*"
    DIV = "/"
    EXP = "**"


_BINARY_OP_MAP: dict[
    OperatorType,
    Callable[
        [PlainQuantity[float] | float, PlainQuantity[float] | float],
        PlainQuantity[float] | float,
    ],
] = {
    OperatorType.ADD: operator.add,
    OperatorType.SUB: operator.sub,
    OperatorType.MUL: operator.mul,
    OperatorType.DIV: operator.truediv,
    OperatorType.EXP: operator.pow,
}

_UNARY_OP_MAP: dict[
    OperatorType, Callable[[PlainQuantity[float] | float], PlainQuantity[float] | float]
] = {
    OperatorType.ADD: lambda x: x,
    OperatorType.SUB: lambda x: -x,
}


class OperatorToken(Token):
    def __init__(self, token: str, start: int, end: int) -> None:
        super().__init__(token, start, end)
        # Just like ParenToken, acceping a string instead of OperatorType directly is scuffed.
        self._op_type: OperatorType = OperatorType(self._token)

    @override
    @staticmethod
    def default_alphabet() -> str:
        return "+-*/"

    @override
    @classmethod
    def alphabet(cls, curr_token: str) -> str:
        if not curr_token:
            return cls.default_alphabet()
        if curr_token == "*":
            return "*"
        return ""

    @property
    def op_type(self) -> OperatorType:
        return self._op_type

    @override
    @classmethod
    def repr_name(cls) -> str:
        return "operator"


class Whitespace(Token):
    """
    Whitespace gets skipped during tokenization.

    Whitespace tokens are always equivalent to the empty string since they're discarded.
    """

    # This should probably be removed and be put into CharStream directly

    @override
    @staticmethod
    def default_alphabet() -> str:
        return string.whitespace

    @override
    @classmethod
    def consume(cls, stream: CharStream) -> str:
        while char := stream.peek():
            if not char.isspace():
                break
            stream.advance()
        return ""

    @override
    @classmethod
    def repr_name(cls) -> str:
        raise NotImplementedError


class UnknownToken(Token):
    """
    Any characters not "registered" by subclassing Token get interpreted as unknown.
    """

    @override
    @staticmethod
    def default_alphabet() -> str | None:
        return None

    @override
    @classmethod
    def consume(cls, stream: CharStream) -> str:
        token = ""
        while char := stream.peek():
            if char in Token.total_alphabet:
                break
            token += char
            stream.advance()
        return token

    @override
    @classmethod
    def repr_name(cls) -> str:
        raise NotImplementedError


def tokenize(s: str) -> Generator[Token, None, None]:
    """
    A lazy iterator to generate tokens from a a given input string.
    """
    stream = CharStream(s)
    while stream:
        token: Token | None = Token.from_stream(stream)
        if token is None:
            break
        if not isinstance(token, Whitespace):
            yield token


class Expression(abc.ABC, BaseModel):
    @abc.abstractmethod
    def start(self) -> int:
        """
        The start of this expression in the input string.
        """
        # TODO: Expressions (and tokens) currently don't hold a reference to the input string, this should be changed.

    @abc.abstractmethod
    def end(self) -> int:
        """
        The end of this expression in the input string.
        """
        # TODO: Expressions (and tokens) currently don't hold a reference to the input string, this should be changed.

    @property
    def span(self) -> tuple[int, int] | _EOL:
        return (self.start(), self.end())

    @abc.abstractmethod
    def dimensionality(self) -> pint.util.UnitsContainer: ...

    @computed_field(alias="dimension")
    def _dimensionality_string(self) -> str:
        return str(self.dimensionality())

    @abc.abstractmethod
    def is_unit(self) -> bool: ...

    @abc.abstractmethod
    def evaluate(
        self,
        ureg: pint.UnitRegistry,
    ) -> Result[PlainQuantity[float] | float, list[EvaluationError]]:
        """
        Evaluate this expression with the global UnitRegistry and context settings.
        """

    @override
    def __eq__(self, other: object) -> bool:
        raise NotImplementedError


class Binary(Expression):
    left: Expression
    right: Expression
    operator: OperatorType

    implicit: bool
    """Whether this operation is implicit e.g. `5km`."""

    @classmethod
    def try_new(
        cls,
        left: Expression,
        op: OperatorType,
        right: Expression,
        implicit: bool = False,
    ) -> Result[Self, DimensionalityError | DivisionByZeroError]:
        """
        Try to create a new Binary expression.

        Returns a DimensionalityError when adding or subtracting expressions with different dimensionalities.
        """
        if (
            op in (OperatorType.ADD, OperatorType.SUB)
            and left.dimensionality() != right.dimensionality()
            or op == OperatorType.EXP
            and right.is_unit()
        ):
            return Err(DimensionalityError(left, op, right))
        elif op == OperatorType.DIV and isinstance(right, Float) and right.value == 0:
            return Err(DivisionByZeroError(right))
        return Ok(cls(left=left, operator=op, right=right, implicit=implicit))

    @override
    def start(self) -> int:
        return self.left.start()

    @override
    def end(self) -> int:
        return self.right.end()

    @override
    def dimensionality(self) -> pint.util.UnitsContainer:
        match self.operator:
            case OperatorType.MUL:
                return self.left.dimensionality() * self.right.dimensionality()
            case OperatorType.DIV:
                return self.left.dimensionality() / self.right.dimensionality()
            case OperatorType.EXP:
                assert isinstance(self.right, Float)
                return self.left.dimensionality() ** self.right.value
            case _:
                return self.left.dimensionality()

    @override
    def is_unit(self) -> bool:
        return bool(self.dimensionality())

    @override
    def evaluate(
        self, ureg: pint.UnitRegistry
    ) -> Result[PlainQuantity[float] | float, list[EvaluationError]]:
        op = _BINARY_OP_MAP[self.operator]
        errors: list[EvaluationError] = []

        left = self.left.evaluate(ureg)
        right = self.right.evaluate(ureg)
        if isinstance(left, Err):
            errors.extend(left.err())
        if isinstance(right, Err):
            errors.extend(right.err())

        elif self.operator == OperatorType.DIV and right.ok() == 0:
            errors.append(DivisionByZeroError(self.right))

        if errors:
            return Err(errors)
        try:
            left = left.unwrap()
            right = right.unwrap()
            return Ok(op(left, right))
        # except OverflowError:
        #     return Err([EvaluationError("Overflow error.", self.span())])
        except pint.errors.PintError as e:
            return Err([EvaluationError(message=str(e), span=self.span)])

    def _as_str(self) -> str:
        """Neatly surrounds the expression with parentheses if it is implicit."""
        s = str(self)
        if self.implicit:
            return f"({s})"
        return s

    @override
    def __str__(self) -> str:
        if isinstance(self.left, Binary) and not self.implicit:
            left = self.left._as_str()
        else:
            left = str(self.left)
        if isinstance(self.right, Binary) and not self.implicit:
            right = self.right._as_str()
        else:
            right = str(self.right)

        if (
            isinstance(self.left, Float)
            and self.right.is_unit()
            and self.operator == OperatorType.MUL
            and self.implicit
        ):
            if isinstance(self.right, Unit):
                s = f"{left}{right}"
            else:
                s = f"{left} {right}"
        elif self.left.is_unit() and self.right.is_unit():
            s = f"{left}{self.operator.value}{right}"
        else:
            s = f"{left} {self.operator.value} {right}"

        return s

    @override
    def __repr__(self) -> str:
        return f"Binary({self.operator.value} ({self.left!r}, {self.right!r}))"

    def __rich_repr__(self) -> rich.repr.Result:
        yield "left", self.left
        yield "op", self.operator.value
        yield "right", self.right
        yield "implicit", self.implicit

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Expression):
            raise TypeError(
                f"Can not compare {self.__class__.__qualname__} and {other.__class__.__qualname__}"
            )
        if not isinstance(other, Binary):
            return False
        return (
            self.left == other.left
            and self.operator == other.operator
            and self.right == other.right
        )


class Unary(Expression):
    value: Expression
    operator: OperatorType
    operator_start: int

    @override
    def start(self) -> int:
        return self.operator_start

    @override
    def end(self) -> int:
        return self.value.end()

    @override
    def dimensionality(self) -> pint.util.UnitsContainer:
        return self.value.dimensionality()

    @override
    def is_unit(self) -> bool:
        return self.value.is_unit()

    @override
    def evaluate(
        self, ureg: pint.UnitRegistry
    ) -> Result[PlainQuantity[float] | float, list[EvaluationError]]:
        value = self.value.evaluate(ureg)
        if isinstance(value, Err):
            return value
        op = _UNARY_OP_MAP[self.operator]
        return Ok(op(value.ok()))

    @override
    def __str__(self) -> str:
        return f"{self.operator.value}{self.value}"

    @override
    def __repr__(self) -> str:
        return f"Unary({self.operator}{self.value!r})"

    def __rich_repr__(self) -> rich.repr.Result:
        yield "op", self.operator.value
        yield "value", self.value

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Expression):
            raise TypeError(
                f"Can not compare {self.__class__.__qualname__} and {other.__class__.__qualname__}"
            )
        if not isinstance(other, Unary):
            return False
        return self.value == other.value and self.operator == other.operator


class Primary(Expression, abc.ABC):
    _token_type: ClassVar[type]

    _start: int
    _end: int

    @classmethod
    @abc.abstractmethod
    def from_token(
        cls, token: Token, ureg: pint.UnitRegistry
    ) -> Result[Self, ParsingError]: ...

    @override
    def start(self) -> int:
        return self._start

    @override
    def end(self) -> int:
        return self._end

    def __neg__(self) -> Primary:
        return -self


class Float(Primary):
    _token_type: ClassVar[type] = FloatToken

    value: float

    @classmethod
    def new(cls, value: float, start: int, end: int) -> Self:
        return cls.model_construct(value=value, _start=start, _end=end)

    @override
    @classmethod
    def from_token(
        cls,
        token: Token,
        ureg: pint.UnitRegistry,
    ) -> Result[Self, ParsingError]:
        start = token.start
        end = token.end
        match token:
            case FloatToken():
                return Ok(
                    cls.model_construct(value=token.to_float(), _start=start, _end=end)
                )
            case _:
                return Err(UnexpectedTokenError(token, expected="number"))

    @override
    def dimensionality(self) -> pint.util.UnitsContainer:
        return UnitsContainer()

    @override
    def is_unit(self) -> bool:
        return False

    @override
    def evaluate(self, ureg: pint.UnitRegistry) -> Result[float, list[EvaluationError]]:
        return Ok(self.value)

    @override
    def __str__(self) -> str:
        if self.value.is_integer():
            return str(int(self.value))
        return str(self.value)

    @override
    def __repr__(self) -> str:
        return f"Float({self.value})"

    def __rich_repr__(self) -> rich.repr.Result:
        yield self.value

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, (Expression, float)):
            raise TypeError(
                f"Can not compare {self.__class__.__qualname__} and {other.__class__.__qualname__}"
            )
        match other:
            case Float():
                return self.value == other.value
            case float():
                return self.value == other
            case _:
                return False


class Unit(Primary):
    _token_type: ClassVar[type] = UnitToken

    _unit: PlainQuantity[float]
    unit_str: str = Field(serialization_alias="unit")

    @classmethod
    def try_new(
        cls, unit_token: UnitToken, ureg: pint.UnitRegistry
    ) -> Result[Self, UndefinedUnitError]:
        try:
            unit = ureg.Quantity(unit_token.token)
        except pint.UndefinedUnitError:
            return Err(UndefinedUnitError(unit_token))
        return Ok(
            cls.model_construct(
                _unit=unit,
                unit_str=unit_token.token,
                _start=unit_token.start,
                _end=unit_token.end,
            )
        )

    @override
    @classmethod
    def from_token(
        cls, token: Token, ureg: pint.UnitRegistry
    ) -> Result[Self, ParsingError]:
        match token:
            case UnitToken():
                return cls.try_new(token, ureg)
            case _:
                return Err(UnexpectedTokenError(token, expected="number"))

    @override
    def dimensionality(self) -> pint.util.UnitsContainer:
        return self._unit.dimensionality

    @override
    def is_unit(self) -> bool:
        return True

    @override
    def evaluate(
        self, ureg: pint.UnitRegistry
    ) -> Result[PlainQuantity[float], list[EvaluationError]]:
        return Ok(self._unit)

    @override
    def __str__(self) -> str:
        return self.unit_str

    @override
    def __repr__(self) -> str:
        return f"Unit({self._unit})"

    def __rich_repr__(self) -> rich.repr.Result:
        yield self.unit_str

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Expression):
            raise TypeError(
                f"Can not compare {self.__class__.__qualname__} and {other.__class__.__qualname__}"
            )
        if not isinstance(other, Unit):
            return False
        return self._unit == other._unit


class Group(Expression):
    paren_type: ParenType = Field(serialization_alias="type")
    expression: Expression
    _start: int
    _end: int

    @classmethod
    def new(
        cls,
        paren_type: ParenType,
        expression: Expression,
        start: int,
        end: int,
    ) -> Self:
        return cls.model_construct(
            paren_type=paren_type,
            expression=expression,
            _start=start,
            _end=end,
        )

    @override
    def start(self) -> int:
        return self._start

    @override
    def end(self) -> int:
        return self._end

    @override
    def dimensionality(self) -> pint.util.UnitsContainer:
        return self.expression.dimensionality()

    @override
    def is_unit(self) -> bool:
        return self.expression.is_unit()

    @override
    def evaluate(
        self, ureg: pint.UnitRegistry
    ) -> Result[PlainQuantity[float] | float, list[EvaluationError]]:
        return self.expression.evaluate(ureg)

    @override
    def __str__(self) -> str:
        opening, closing = self.paren_type.to_pair()
        # if isinstance(self.expr, Binary) and self.expr.implicit:
        #     return str(self.expr)
        return f"{opening.value}{self.expression}{closing.value}"

    @override
    def __repr__(self) -> str:
        opening, closing = self.paren_type.to_pair()
        return f"Group({opening.value}{self.expression!r}{closing.value})"

    def __rich_repr__(self) -> rich.repr.Result:
        yield self.expression

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Expression):
            raise TypeError(
                f"Can not compare {self.__class__.__qualname__} and {other.__class__.__qualname__}"
            )
        if isinstance(other, Group):
            return self.expression == other.expression
        return self.expression == other


class Error(Exception):
    def __init__(self, message: str, span: tuple[int, int] | _EOL = EOL):
        super().__init__(message)
        self.span: tuple[int, int] | _EOL = span


class ParsingError(Error):
    pass


class UnexpectedTokenError(ParsingError):
    def __init__(self, token: Token, *, expected: str) -> None:
        super().__init__(f"Expected {expected}, got '{token.token}'.", token.span())


class UnexpectedEolError(ParsingError):
    def __init__(self, expected: str):
        super().__init__(expected)


def _format_expected(expected_token_types: tuple[type[Token], ...]) -> str:
    *expected, last = expected_token_types
    if not expected:
        return last.repr_name()
    if len(expected) == 1:
        first_str = expected[0].repr_name()
        last_str = last.repr_name()
        return f"{first_str} or {last_str}"
    return ", ".join(exp_class.repr_name() for exp_class in expected_token_types)


class UnmatchedParenError(ParsingError):
    def __init__(self, paren_token: ParenToken):
        name = paren_token.paren_type.paren_name()
        super().__init__(f"Unmatched {name}.", paren_token.span())


class EmptyGroupExpression(ParsingError):
    def __init__(self, span: tuple[int, int]) -> None:
        super().__init__("Empty group expression.", span)


class InvalidUnaryError(ParsingError):
    def __init__(self, operator_token: OperatorToken) -> None:
        super().__init__(
            f"Invalid unary operator: {operator_token.token}.", operator_token.span()
        )


class ExpectedPrimaryError(ParsingError):
    def __init__(
        self,
        *,
        message: str | None = None,
        span: tuple[int, int] | _EOL = EOL,
    ) -> None:
        if message is None:
            message = "Expected expression."
        super().__init__(message, span)


class UnexpectedPrimaryError(ParsingError):
    def __init__(self, token: Token):
        super().__init__(f"Expected expression, got: {token.token}.", token.span())


class UndefinedUnitError(ParsingError):
    def __init__(self, unit_token: UnitToken) -> None:
        super().__init__(f"Invalid unit {unit_token.token}", unit_token.span())


# Dimensionality errors should be caught during parsing
class DimensionalityError(ParsingError):
    def __init__(self, left: Expression, op: OperatorType, right: Expression) -> None:
        start = left.start()
        end = right.end()
        super().__init__(
            f"Invalid operation '{op.value}' for expressions with differing dimensions ({left.dimensionality()} {op.value} {right.dimensionality()}).",
            span=(start, end),
        )


# Evaluation errors


class EvaluationError(Error):
    pass


class DivisionByZeroError(ParsingError, EvaluationError):
    def __init__(self, expression: Expression) -> None:
        super().__init__(
            f"Tried dividing by zero (Expression '{expression}' evaluates to 0).",
            expression.span,
        )


class ParserMode(enum.StrEnum):
    Adaptive = enum.auto()
    Strict = enum.auto()


class Parser:
    def __init__(
        self, ureg: pint.UnitRegistry, mode: ParserMode = ParserMode.Adaptive
    ) -> None:
        self.ureg: pint.UnitRegistry = ureg
        self._mode: ParserMode = mode
        self._token: Token | None = None
        self._previous_token: Token | None = None

    @staticmethod
    def preprocess_input(input: str) -> str:
        input = input.replace('"', "in")
        # '' Should have priority as inch, instead of making it `ft ft`
        input = input.replace("''", "in")
        input = input.replace("'", "ft")

        input = input.replace(" per ", " / ")

        # Swap any substring similar to `6 foot 3` to `6 foot 3 inch`
        input = re.sub(
            r"^(\d+(\.\d+)? *(foot|ft) *\d+(\.\d+)?)$",
            lambda m: m.group(0) + " inch",
            input,
        )

        return input

    def parse(self, input: str) -> Result[Expression, list[ParsingError]]:
        """
        Try to parse the given input expression.

        Errors
        ------
        - List of `ParsingError` for issues when parsing.
        """
        input = self.preprocess_input(input)
        tokens = list(tokenize(input))
        result = self._parse_expr(deque(tokens))
        return result

    def _expect_token[T: Token](
        self, tokens: deque[Token], expected: tuple[type[T], ...]
    ) -> Result[T, UnexpectedTokenError | UnexpectedEolError]:
        if not tokens:
            expected_str = _format_expected(expected)
            return Err(UnexpectedEolError(expected=expected_str))
        token = tokens[0]
        if not isinstance(token, expected):
            expected_str = _format_expected(expected)
            return Err(UnexpectedTokenError(token, expected=expected_str))
        return Ok(token)

    def _eat_token[T: Token](
        self, tokens: deque[Token], expected: tuple[type[T], ...]
    ) -> Result[T, UnexpectedTokenError | UnexpectedEolError]:
        token_res = self._expect_token(tokens, expected)
        if isinstance(token_res, Err):
            return token_res
        _ = tokens.popleft()
        token = token_res.ok()
        self._previous_token = self._token
        self._token = token
        return token_res

    def _expect_two[T1: Token, T2: Token](
        self,
        tokens: deque[Token],
        expect_first: tuple[type[T1], ...],
        expect_second: tuple[type[T2], ...],
    ) -> Result[tuple[T1, T2], UnexpectedTokenError | UnexpectedEolError]:
        first_res = self._expect_token(tokens, expect_first)
        if isinstance(first_res, Err):
            return first_res
        first = first_res.ok()

        self._bump(tokens)
        second_res = self._expect_token(tokens, expect_second)
        tokens.appendleft(first)
        if isinstance(second_res, Err):
            return second_res
        second = second_res.ok()
        return Ok((first, second))

    def _bump(self, tokens: deque[Token]) -> None:
        token = tokens.popleft()
        self._previous_token = self._token
        self._token = token

    def _parse_expr(
        self,
        tokens: deque[Token],
    ) -> Result[Expression, list[ParsingError]]:
        return self._parse_sum(tokens)

    def _parse_binary(
        self,
        tokens: deque[Token],
        ops: tuple[OperatorType, ...],
    ) -> Result[Expression, list[ParsingError]]:
        """
        A generic algorithm for parsing binary operations.

        The expression gets parsed in the following way:
        1. Decide what the term is.
            - If we're parsing a sum, we look for unary operations (see `_parse_unary`).
                - This way `-3 + 4` doesn't turn into `-(3 + 4)`, but we guarantee multiplication and exponentiation have higher precedence.
            - If we're parsing factors, look for smaller exponent expressions.
            - If we're parsing an exponentiation, look for "primary" terms (see `_parse_primary`).
        2. Parse one term (the starting left term).
        3. Repeatedly pop an operator and try to parse the `right` term. Then construct a Binary with the current terms.

        Errors
        ------
        - Any errors propagated from parsing primary terms in `_parse_primary`.

        - Errors get reported for all terms, hopefully this makes it easier to debug and use.
            - e.g. "(1 / 0) + (2 / 0)" will report errors for both parenthesis.
        """

        error_group: list[ParsingError] = []

        match ops[0]:
            case OperatorType.ADD | OperatorType.SUB:
                parse_term = self._parse_unary
            case OperatorType.MUL | OperatorType.DIV:
                parse_term = self._parse_exp
            case OperatorType.EXP:
                match self._mode:
                    case ParserMode.Adaptive:
                        parse_term = self._parse_primary
                    case ParserMode.Strict:
                        parse_term = self._parse_primary_single

        term = parse_term(tokens)
        if isinstance(term, Err):
            error_group.extend(term.err())

        while tokens:
            token_res = self._expect_token(tokens, (Token,))
            if isinstance(token_res, Err):
                error_group.append(token_res.err())
                continue
            token = token_res.ok()

            op_type = None
            if isinstance(token, UnknownToken):
                expected = "operator or group expression"
                error_group.append(UnexpectedTokenError(token, expected=expected))
                self._bump(tokens)
            elif isinstance(token, OperatorToken):
                if token.op_type not in ops:
                    break
                op_type = token.op_type
                self._bump(tokens)
            # Implicit multiplication
            elif (
                OperatorType.MUL in ops
                or OperatorType.EXP in ops
                and self._mode == ParserMode.Adaptive
            ):
                if isinstance(token, FloatToken) and isinstance(
                    self._token, FloatToken
                ):
                    message = "Expected operator or unit between numbers."
                    start = self._token.end
                    end = token.start
                    error_group.append(
                        ExpectedPrimaryError(message=message, span=(start, end))
                    )
                    self._bump(tokens)
                    continue
                op_type = OperatorType.MUL
            else:
                break

            right = parse_term(tokens)
            if isinstance(right, Err):
                error_group.extend(right.err())

            elif op_type is not None:
                right_val = right.ok()
                if (
                    isinstance(right_val, Float)
                    and right_val.value == 0
                    and op_type == OperatorType.DIV
                ):
                    error_group.append(DivisionByZeroError(right_val))
                elif isinstance(term, Ok):
                    match Binary.try_new(term.ok(), op_type, right_val):
                        case Err(err) if isinstance(err, DimensionalityError):
                            error_group.append(err)
                        case res:
                            term = Ok(
                                res.expect(
                                    "Can not be DivisionByZero because we check in the if above"
                                )
                            )

        if error_group:
            return Err(error_group)
        return term

    def _parse_sum(
        self,
        tokens: deque[Token],
    ) -> Result[Expression, list[ParsingError]]:
        return self._parse_binary(tokens, (OperatorType.ADD, OperatorType.SUB))

    def _parse_mul(
        self,
        tokens: deque[Token],
    ) -> Result[Expression, list[ParsingError]]:
        return self._parse_binary(tokens, (OperatorType.MUL, OperatorType.DIV))

    def _parse_exp(
        self,
        tokens: deque[Token],
    ) -> Result[Expression, list[ParsingError]]:
        return self._parse_binary(tokens, (OperatorType.EXP,))

    def _parse_unary(
        self,
        tokens: deque[Token],
    ) -> Result[Expression, list[ParsingError]]:
        """
        Parse a sequence of unary operations, the tree is created from the innermost operation.

        Example
        -------
        - `+-3` turns into `Unary(ADD, Unary(SUB, Float(3)))`.

        Errors
        ------
        - `InvalidUnaryError`
            - Any operator not found in the unary operator map `_UNARY_OP_MAP` is considered invalid.
        - Any errors propagated from parsing higher precedence terms, see `_parse_mul` and `_parse_exp`.
        """
        op_list: list[OperatorToken] = []
        while tokens:
            token_res = self._expect_token(tokens, (Token,))
            if isinstance(token_res, Err):
                return Err([token_res.err()])
            token = token_res.ok()

            if isinstance(token, UnknownToken):
                self._bump(tokens)
                return Err([UnexpectedTokenError(token, expected="expression")])
            if not isinstance(token, OperatorToken):
                value = self._parse_mul(tokens)
                if isinstance(value, Err):
                    return value
                break
            if token.op_type not in _UNARY_OP_MAP:
                return Err([InvalidUnaryError(token)])
            self._bump(tokens)
            op_list.append(token)
        else:
            return Err([ExpectedPrimaryError()])

        if not op_list:
            return value

        value = value.unwrap()
        while op_list:
            op = op_list.pop()
            value = Unary(operator=op.op_type, value=value, operator_start=op.start)
        return Ok(value)

    def _parse_primary(
        self,
        tokens: deque[Token],
    ) -> Result[Expression, list[ParsingError]]:
        """
        Parses a:
        - `Group`: any expression in parenthesis, brackets or braces gets parsed recursively.
        - `Float`: a floating point number.
        - `Unit`: a string/identifier, units.
        - "Primary chain": Series of Floats and Units which get parsed with implicit binary operations.
            - See `_parse_primary_chain` for details.

        Errors
        ------
        - `ExpectedPrimaryError`
            - We reached the end of the token stream, but we're expecting a primary or a group term.
            - Returned from `_parse_primary_chain` in some cases.
        - `UnmatchedParenError`
            - See `_parse_group`.
        - `UnexpectedPrimaryError`, `InvalidUnitError`
            - See `_parse_primary_chain`.
        """
        if not tokens:
            return Err([ExpectedPrimaryError()])

        token_res = self._eat_token(tokens, (ParenToken,))
        if isinstance(token_res, Ok):
            return self._parse_group(tokens, token_res.ok())
        return self._parse_primary_chain(tokens)

    def _parse_primary_single(
        self, tokens: deque[Token]
    ) -> Result[Primary | Group, list[ParsingError]]:
        if not tokens:
            return Err([ExpectedPrimaryError()])
        token_res = self._eat_token(tokens, (ParenToken, FloatToken, UnitToken))
        if isinstance(token_res, Err):
            return Err([token_res.err()])
        token = token_res.ok()

        if isinstance(token, ParenToken):
            return self._parse_group(tokens, token)
        elif isinstance(token, FloatToken):
            return Ok(Float.new(token.to_float(), *token.span()))
        else:
            res = Unit.from_token(token, self.ureg)
            if isinstance(res, Ok):
                return res
            return Err([res.err()])

    def _parse_group(
        self,
        tokens: deque[Token],
        opening_pair: ParenToken,
    ) -> Result[Group, list[ParsingError]]:
        """
        Parses a sequence of tokens surrounded by Paren tokens on the same level, handling nested groups as expected.
        e.g.
        ((5 + 3) + 7)
        Gets turned into one big Group expression, with a smaller one inside.

        Errors
        ------
        - Any error propagated from the inner expression.
        - `UnmatchedParenError`
            - Returned when the first paren is not an opening one, or when the opening paren isn't closed.
        """
        if not opening_pair.paren_type.is_opening():
            return Err([UnmatchedParenError(opening_pair)])

        group_tokens: deque[Token] = deque()
        pairs_open = 1
        while tokens:
            token_res = self._eat_token(tokens, (Token,))
            if isinstance(token_res, Err):
                return Err([token_res.err()])
            token = token_res.ok()

            if isinstance(token, ParenToken):
                if token.paren_type == opening_pair.paren_type:
                    pairs_open += 1
                elif token.paren_type.is_pair(opening_pair.paren_type):
                    pairs_open -= 1
            if pairs_open == 0:
                break
            group_tokens.append(token)
        else:
            return Err([UnmatchedParenError(opening_pair)])

        closing_pair = token
        if not group_tokens:
            start = opening_pair.start
            end = closing_pair.end
            if start == end:
                end += 1
            return Err([EmptyGroupExpression(span=(start, end))])

        # Since groups get parsed without any context of  the outer expression,
        # they can raise errors EOL errors even when it's not actually the end of the expression.
        # e.g.
        # `(9 / ) + (4 * )`
        #      ^        ^ No tokens left after the operators so they report EOL
        # We solve this by changing every EOL to a span between the last token and paren
        last_group_token = group_tokens[-1]
        expr = self._parse_expr(group_tokens)
        if isinstance(expr, Err):
            errors = expr.err()
            start = last_group_token.end
            end = closing_pair.start
            if end == start:
                end += 1
            for err in errors:
                if err.span == EOL:
                    err.span = (start, end)
            return expr

        return Ok(
            Group.new(
                expression=expr.unwrap(),
                paren_type=opening_pair.paren_type,
                start=opening_pair.start,
                end=closing_pair.end,
            )
        )

    def _parse_primary_chain(
        self,
        tokens: deque[Token],
    ) -> Result[Binary | Primary | Group, list[ParsingError]]:
        # TODO: DOCS.
        # TODO: this code is fucking disgusting.

        token_res = self._expect_token(tokens, (FloatToken, UnitToken))
        if isinstance(token_res, Err):
            return Err([token_res.err()])
        token = token_res.ok()

        error_group: list[ParsingError] = []
        previous_number_error = False
        previous_unit_error = False
        # Any series of the same error gets ignored, because too many errors will be a wall of text in discord.

        subexpressions: deque[Binary | Primary | Group] = deque()
        curr_subexpr: Float | Unit | Binary | None = None
        previous_unit: Unit | Binary | None = None

        while tokens:
            token_res = self._expect_token(tokens, (FloatToken, UnitToken))
            if isinstance(token_res, Err):
                break
            token = token_res.ok()

            if isinstance(token, FloatToken):
                number_res = self._parse_primary_expression(Float, tokens)
                if isinstance(number_res, Err):
                    error_group.extend(number_res.err())
                    curr_subexpr = None
                else:
                    if curr_subexpr is not None:
                        subexpressions.append(curr_subexpr)
                    curr_subexpr = number_res.ok()

                if isinstance(self._previous_token, FloatToken):
                    if not previous_number_error:
                        message = "Expected operator or unit between numbers."
                        start = self._previous_token.end
                        end = token.start
                        error_group.append(
                            ExpectedPrimaryError(message=message, span=(start, end))
                        )
                    previous_number_error = True
                    self._previous_token = token
                    continue

            else:
                unit_res = self._parse_primary_expression(Unit, tokens)
                if isinstance(unit_res, Err):
                    error_group.extend(unit_res.err())
                    curr_subexpr = None
                    previous_unit = None
                    continue
                unit = unit_res.ok()

                if (
                    isinstance(self._previous_token, UnitToken)
                    and previous_unit is not None
                    and previous_unit.dimensionality() == unit.dimensionality()
                ):
                    if not previous_unit_error:
                        message = (
                            "Expected a number between units of same dimensionality."
                        )
                        start = previous_unit.end()
                        end = unit.start()
                        error_group.append(
                            ExpectedPrimaryError(message=message, span=(start, end))
                        )
                    previous_unit_error = True
                    previous_unit = unit
                    continue

                if curr_subexpr is None:
                    curr_subexpr = unit
                else:
                    curr_subexpr = Binary(
                        left=curr_subexpr,
                        operator=OperatorType.MUL,
                        right=unit,
                        implicit=True,
                    )

                previous_unit = unit

            previous_number_error = False
            previous_unit_error = False

        if curr_subexpr is not None:
            subexpressions.append(curr_subexpr)

        if error_group:
            return Err(error_group)

        while len(subexpressions) > 1:
            left = subexpressions.popleft()
            right = subexpressions.popleft()
            if left.dimensionality() == right.dimensionality():
                op = OperatorType.ADD
            else:
                op = OperatorType.MUL
            new_expr = Binary.try_new(left, op, right, implicit=True).unwrap()
            subexpressions.appendleft(new_expr)
        return Ok(subexpressions[0])

    @overload
    def _parse_primary_expression(
        self,
        primary: type[Float],
        tokens: deque[Token],
        exp: bool = False,
    ) -> Result[Float | Binary, list[ParsingError]]: ...

    @overload
    def _parse_primary_expression(
        self,
        primary: type[Unit],
        tokens: deque[Token],
        exp: bool = False,
    ) -> Result[Unit | Binary, list[ParsingError]]: ...

    def _parse_primary_expression(
        self,
        primary: type[Float | Unit],
        tokens: deque[Token],
        exp: bool = False,
    ) -> Result[Float | Unit | Binary, list[ParsingError]]:
        """
        Parses simple or complex float or unit expressions, such as "1", "1/2", "N / m**2", or "1 / 4**(2+3)".

        NOTE: implicit multiplication of units is not handled here,
        the input "N m" only returns the Unit "N", but "m" stays in `tokens`.

        Errors
        ------
        - `UndefinedUnitError`
            - All units which aren't defined in the registry are reported.
        - `ExpectedPrimaryError`
            - Returned when we run into a unit as an exponent. This would raise a pint.DimensionalityError when trying to evalute.
        - `DivisionByZeroError`
            - Returned when dividing by 0.
            - NOTE: the right operand must be exactly 0, it can not be e.g. "x / (1-1)."
        """
        error_group: list[ParsingError] = []

        if exp:
            op_res = self._eat_token(tokens, (FloatToken, UnitToken))
        else:
            op_res = self._expect_token(tokens, (FloatToken, UnitToken))
        if isinstance(op_res, Err):
            return Err([op_res.err()])
        op = op_res.ok()

        assert isinstance(op, primary._token_type)
        token_type = type(op)

        if exp:
            ops = (OperatorType.EXP,)
            right_token = primary.from_token(op, self.ureg)
            if isinstance(right_token, Err):
                error_group.append(right_token.err())
                # Type hint to avoid LSP complaints because `list` is invariant
                errors: list[ParsingError] = [right_token.err()]
                term = Err(errors)
            else:
                term = right_token
        else:
            ops = (OperatorType.DIV,)
            term = self._parse_primary_expression(primary, tokens, exp=True)
            if isinstance(term, Err):
                error_group.extend(term.err())

        while len(tokens) > 1:
            op_right_res = self._expect_two(
                tokens, (OperatorToken,), (FloatToken, UnitToken, ParenToken)
            )
            if isinstance(op_right_res, Err):
                break
            op, right_token = op_right_res.ok()
            if op.op_type not in ops:
                break
            if exp:
                self._bump(tokens)
                self._bump(tokens)
                if isinstance(right_token, UnitToken):
                    message = f"Expected a number or dimensionless group as an exponent, got unit '{right_token.token}'."
                    error_group.append(
                        ExpectedPrimaryError(message=message, span=right_token.span())
                    )
                    continue
                elif isinstance(right_token, FloatToken):
                    right = Float.new(right_token.to_float(), *right_token.span())
                else:
                    right_res = self._parse_group(tokens, right_token)
                    if isinstance(right_res, Err):
                        error_group.extend(right_res.err())
                        continue
                    right = right_res.ok()
                    if right.is_unit():
                        message = f"Expected a number as an exponent, got an expression with dimension '{right.dimensionality()}'."
                        error_group.append(
                            ExpectedPrimaryError(
                                message=message, span=right_token.span()
                            )
                        )
            else:
                if not isinstance(right_token, token_type):
                    break
                self._bump(tokens)
                right_res = self._parse_primary_expression(primary, tokens, exp=True)
                if isinstance(right_res, Err):
                    error_group.extend(right_res.err())
                    continue
                right = right_res.ok()
            if (
                isinstance(right, Float)
                and right.value == 0
                and op.op_type == OperatorType.DIV
            ):
                error_group.append(DivisionByZeroError(right))
            elif isinstance(term, Ok):
                term = Ok(
                    Binary.try_new(term.ok(), op.op_type, right).expect(
                        "This could only fail if it was an exponentation with a unit, or division by zero, both of which we check for above"
                    )
                )

        if error_group:
            return Err(error_group)

        # if isinstance(term, Ok):
        #     print(primary, type(term.ok()))
        return term
