from abc import ABC, abstractmethod
from contextlib import suppress
from dataclasses import dataclass, field, replace
from types import CodeType
from typing import (
    Any,
    Callable,
    ClassVar,
    Generic,
    ParamSpec,
    TypeVar,
    Union,
    cast,
    overload,
)
import typing as t
from bolt.utils import internal

from nbtlib import Compound, Path, ListIndex, CompoundMatch, NamedKey  # type: ignore

from .node import Expression, UnrollHelper
from .typing import NbtType, is_compound_type
from .utils import format_type, type_name

from .optimizer import (
    DataTuple,
    IrData,
    IrScore,
    DataTargetType,
    ScoreTuple,
    SourceTuple,
)
from .literals import Literal, convert_node
from .node import Expression, ExpressionNode
from .operations import (
    Add,
    Append,
    BinaryOperation,
    Cast,
    Divide,
    Enable,
    InPlaceMerge,
    Insert,
    Merge,
    Modulus,
    Multiply,
    Operation,
    Prepend,
    Remove,
    Reset,
    ResultType,
    Set,
    Subtract,
    UnaryOperation,
)
from .typing import (
    NbtType,
    Accessor,
    access_type,
    convert_type,
    convert_tag,
    is_array_type,
    is_list_type,
    is_numeric_type,
    is_string_type,
    is_type,
    literal_types,
)


__all__ = [
    "Source",
    "ScoreSource",
    "DataSource",
    "parse_compound",
]

SOLO_COLON = slice(None, None, None)


T = TypeVar("T")
P = ParamSpec("P")


@internal
def resolve(
    expr: Expression,
    value: Any,
    result: Union["Source", None] = None,
    cast: NbtType | None = None,
    lazy: bool = False,
):
    value_node = (
        value if isinstance(value, ExpressionNode) else Literal(value=value, ctx=expr)
    )

    result_type = ResultType.data
    in_place = False

    if isinstance(value_node, Operation):
        result_type = value_node.result
        in_place = value_node.in_place

        if target := value_node.in_place_target:
            if isinstance(target, Source):
                result = target

    if result is None:
        result = create_result(expr, result_type)

    if in_place:
        op = value_node
    elif cast is None:
        op = Set(former=result, latter=value_node, ctx=expr)
    else:
        op = Cast(former=result, latter=value_node, cast_type=cast, ctx=expr)

    expr.resolve(op, lazy=lazy)

    return result


def create_result(expr: Expression, result_type: ResultType) -> "Source":
    if result_type == ResultType.score:
        holder, obj = expr.temp_score()
        return ScoreSource(holder, obj, ctx=expr)

    if result_type == ResultType.data:
        target_type, target, path = expr.temp_data()
        return DataSource(target_type, target, path, ctx=expr)

    raise ValueError(f"Invalid operation result type {result_type}.")


@dataclass
class OperatorMethod(Generic[P, T]):
    func: Callable[P, T]
    lazy: bool = False
    returns: bool = True

    target: Union["Source", None] = None

    @internal
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Any:
        if self.target and not self.lazy:
            self.target.evaluate()

        value = self.func(*args, **kwargs)

        if isinstance(value, (UnaryOperation, BinaryOperation)):
            result = resolve(value.expr, value, lazy=self.lazy)
        else:
            result = value

        if self.returns:
            return result

    def __get__(self, obj: Any, objtype: Any = None):
        if isinstance(obj, OperatorHandler):
            target = obj.target
        elif isinstance(obj, Source):
            target = obj
        elif obj is None:
            target = None
        else:
            raise TypeError(f"Operator method is bound on an invalid object.")

        return replace(self, target=target, func=self.func.__get__(obj, objtype))

    @property
    def __code__(self) -> CodeType:
        return self.func.__code__


@overload
def operator_method(
    *, lazy: bool = False, is_internal: bool = True, returns: bool = True
) -> Callable[[Callable[P, T]], OperatorMethod[P, T]]:
    ...


@overload
def operator_method(func: Callable[P, T]) -> OperatorMethod[P, T]:
    ...


def operator_method(
    func: Callable[..., Any] | None = None,
    *,
    lazy: bool = False,
    is_internal: bool = True,
    returns: bool = True,
) -> Any:
    def decorator(f: Callable[P, T]) -> OperatorMethod[P, T]:
        return OperatorMethod(f, lazy, returns)

    if is_internal:
        internal(decorator)

    if func is not None:
        return decorator(func)

    return decorator


@dataclass(frozen=True)
class OperatorHandler:
    target: "DataSource"

    list_index: ClassVar[bool] = False
    named_key: ClassVar[bool] = False
    compound_match: ClassVar[bool] = False

    def get(self, key: str, default: Any = None) -> OperatorMethod[..., Any] | None:
        if attr := getattr(self, key, None):
            if isinstance(attr, OperatorMethod):
                return cast(OperatorMethod[..., Any], attr)

        return default


UnaryOp = TypeVar("UnaryOp", bound=UnaryOperation)

UnaryOpFunction = Callable[[Union[ExpressionNode, "OperatorHandler"]], T]


def unary_operator(cls: type[UnaryOp]) -> UnaryOpFunction[UnaryOp]:
    def decorator(target: ExpressionNode | OperatorHandler):
        if isinstance(target, OperatorHandler):
            target = target.target

        return cls(target=target, ctx=target.ctx)

    return OperatorMethod(decorator, lazy=True)


BinOp = TypeVar("BinOp", bound=BinaryOperation)

BinaryOpFunction = Callable[[Union[ExpressionNode, "OperatorHandler"], Any], T]

SanitizedBinaryOpFunction = Callable[[ExpressionNode, ExpressionNode], T]


def sanitized(f: SanitizedBinaryOpFunction[T]) -> BinaryOpFunction[T]:
    def decorated(node: Union[ExpressionNode, "OperatorHandler"], value: Any):
        if isinstance(node, OperatorHandler):
            node = node.target

        return f(node, convert_node(value, node.ctx))

    return decorated


@overload
def binary_operator(
    cls: type[BinOp],
) -> BinaryOpFunction[BinOp]:
    ...


@overload
def binary_operator(
    cls: type[BinOp],
    *,
    reverse: t.Literal[True],
) -> tuple[BinaryOpFunction[BinOp], BinaryOpFunction[BinOp]]:
    ...


def binary_operator(
    cls: type[BinOp],
    *,
    reverse: bool = False,
) -> BinaryOpFunction[BinOp] | tuple[BinaryOpFunction[BinOp], BinaryOpFunction[BinOp]]:
    @sanitized
    def decorator(left: ExpressionNode, right: ExpressionNode) -> Any:
        return cls(former=left, latter=right, ctx=left.ctx)

    if not reverse:
        return OperatorMethod(decorator, lazy=True)

    @sanitized
    def reversed(right: ExpressionNode, left: ExpressionNode) -> Any:
        return cls(former=left, latter=right, ctx=right.ctx)

    return (OperatorMethod(decorator, lazy=True), OperatorMethod(reversed, lazy=True))


@dataclass(order=False, kw_only=True)
class Source(ExpressionNode, ABC):
    def is_lazy(self) -> bool:
        return self.to_tuple() in self.expr.lazy_values

    def evaluate(self):
        if self.is_lazy():
            self.expr.evaluate_lazy(self.to_tuple())

        return self

    @abstractmethod
    @operator_method
    def component(self) -> Any:
        ...

    @abstractmethod
    def to_tuple(self) -> SourceTuple:
        ...


@dataclass(unsafe_hash=True, order=False)
class ScoreSource(Source):
    scoreholder: str
    objective: str

    __add__, __radd__ = binary_operator(Add, reverse=True)
    __sub__, __rsub__ = binary_operator(Subtract, reverse=True)
    __mul__, __rmul__ = binary_operator(Multiply, reverse=True)
    __truediv__, __rtruediv__ = binary_operator(Divide, reverse=True)
    __mod__, __rmod__ = binary_operator(Modulus, reverse=True)

    def __rebind__(self, value: Any):
        return resolve(self.expr, value, result=self)

    @operator_method
    def enable(self):
        return Enable(target=self, ctx=self.ctx)

    @operator_method
    def reset(self):
        return Reset(target=self, ctx=self.ctx)

    def __str__(self):
        return f"{self.scoreholder} {self.objective}"

    @operator_method
    def component(self, **tags: Any):
        return {
            "score": {"name": self.scoreholder, "objective": self.objective},
            **tags,
        }

    def to_tuple(self) -> ScoreTuple:
        return ScoreTuple(self.scoreholder, self.objective)

    def unroll(self, helper: UnrollHelper):
        if r := self.expr.unroll_lazy(self.to_tuple(), helper):
            return r[0], r[1]

        result = IrScore(holder=self.scoreholder, obj=self.objective)
        return (), result

    @property
    def holder(self):
        return self.scoreholder

    @property
    def obj(self):
        return self.objective


def parse_compound(value: Union[str, dict, Path, Compound]):
    if isinstance(value, (Path, Compound)):
        return value
    if isinstance(value, dict):
        return convert_tag(value)
    return Path(value)


class GenericOperatorHandler(OperatorHandler):
    list_index: ClassVar[bool] = True
    named_key: ClassVar[bool] = True
    compound_match: ClassVar[bool] = True

    __add__, __radd__ = binary_operator(Add, reverse=True)
    __sub__, __rsub__ = binary_operator(Subtract, reverse=True)
    __mul__, __rmul__ = binary_operator(Multiply, reverse=True)
    __truediv__, __rtruediv__ = binary_operator(Divide, reverse=True)
    __mod__, __rmod__ = binary_operator(Modulus, reverse=True)
    __or__, __ror__ = binary_operator(Merge, reverse=True)

    @operator_method(returns=False)
    def insert(self, index: int, value: Any):
        return Insert(
            former=self.target, latter=value, index=index, ctx=self.target.ctx
        )

    @operator_method(returns=False)
    def append(self, value: Any):
        return Append(former=self.target, latter=value, ctx=self.target.ctx)

    @operator_method(returns=False)
    def prepend(self, value: Any):
        return Prepend(former=self.target, latter=value, ctx=self.target.ctx)

    @operator_method(returns=False)
    def remove(self, sub_path: Any = None):
        target = self.target if sub_path is None else self.target[sub_path]
        return Remove(target=target, ctx=self.target.ctx)

    @operator_method(returns=False)
    def merge(self, value: Any):
        return InPlaceMerge(former=self.target, latter=value, ctx=self.target.ctx)


class NumericOperatorHandler(OperatorHandler):
    __add__, __radd__ = binary_operator(Add, reverse=True)
    __sub__, __rsub__ = binary_operator(Subtract, reverse=True)
    __mul__, __rmul__ = binary_operator(Multiply, reverse=True)
    __truediv__, __rtruediv__ = binary_operator(Divide, reverse=True)
    __mod__, __rmod__ = binary_operator(Modulus, reverse=True)


class StringOperatorHandler(OperatorHandler):
    ...


class SequenceOperatorHandler(OperatorHandler):
    list_index: ClassVar[bool] = True

    @operator_method(returns=False)
    def insert(self, index: int, value: Any):
        return Insert(
            former=self.target, latter=value, index=index, ctx=self.target.ctx
        )

    @operator_method(returns=False)
    def append(self, value: Any):
        return Append(former=self.target, latter=value, ctx=self.target.ctx)

    @operator_method(returns=False)
    def prepend(self, value: Any):
        return Prepend(former=self.target, latter=value, ctx=self.target.ctx)

    @operator_method(returns=False)
    def remove(self, sub_path: Any = None):
        target = self.target if sub_path is None else self.target[sub_path]
        return Remove(target=target, ctx=self.target.ctx)


class CompoundOperatorHandler(OperatorHandler):
    named_key: ClassVar[bool] = True
    compound_match: ClassVar[bool] = True

    __or__, __ror__ = binary_operator(Merge, reverse=True)

    @operator_method(returns=False)
    def merge(self, value: Any):
        return InPlaceMerge(former=self.target, latter=value, ctx=self.target.ctx)


def _not_implemented(*_: Any):
    return NotImplemented


@dataclass
class DataSourceOperator:
    default: Callable[..., Any] | None = None
    handler_name: str = "operator_handler"

    operator: str = field(init=False)

    def __set_name__(self, owner: Any, name: str):
        self.operator = name

    def __get__(self, obj: Any, objtype: Any):
        if obj is None:
            handler = getattr(objtype, self.handler_name, None)
            if handler is None:
                return self

            value = getattr(handler, self.operator, None)
            return value if value is not None else self

        handler = getattr(obj, self.handler_name)

        with suppress(AttributeError):
            return getattr(handler, self.operator)

        if self.default is not None:
            return self.default.__get__(obj, objtype)

        raise AttributeError(
            f"'{type_name(obj)}' object has no attribute '{self.operator}'.",
            name=self.operator,
            obj=obj,
        )


@dataclass(unsafe_hash=True, order=False)
class DataSource(Source):
    _type: DataTargetType
    _target: str
    _path: Path = field(default_factory=Path)
    _scale: float = 1
    writetype: NbtType = Any

    _constructed: bool = field(hash=False, default=False, init=False)

    __add__ = DataSourceOperator(_not_implemented)
    __radd__ = DataSourceOperator(_not_implemented)
    __sub__ = DataSourceOperator(_not_implemented)
    __rsub__ = DataSourceOperator(_not_implemented)
    __mul__ = DataSourceOperator(_not_implemented)
    __rmul__ = DataSourceOperator(_not_implemented)
    __truediv__ = DataSourceOperator(_not_implemented)
    __rtruediv__ = DataSourceOperator(_not_implemented)
    __mod__ = DataSourceOperator(_not_implemented)
    __rmod__ = DataSourceOperator(_not_implemented)
    __or__ = DataSourceOperator(_not_implemented)
    __ror__ = DataSourceOperator(_not_implemented)

    @property
    def operator_handler(self) -> OperatorHandler:
        if is_numeric_type(self.readtype):
            return NumericOperatorHandler(self)

        if is_string_type(self.readtype):
            return StringOperatorHandler(self)

        if is_array_type(self.readtype):
            return SequenceOperatorHandler(self)

        if is_list_type(self.readtype):
            return SequenceOperatorHandler(self)

        if is_compound_type(self.readtype):
            return CompoundOperatorHandler(self)

        return GenericOperatorHandler(self)

    def __post_init__(self):
        super().__post_init__()

        self._constructed = True

    @property
    def readtype(self) -> NbtType:
        return self.writetype

    def to_tuple(self) -> DataTuple:
        return DataTuple(self._type, self._target, self._path)

    def unroll(self, helper: UnrollHelper):
        if r := self.expr.unroll_lazy(self.to_tuple(), helper):
            return r[0], r[1]

        result = IrData(
            type=self._type,
            target=self._target,
            path=self._path,
            nbt_type=self.readtype,
            scale=self._scale,
        )
        return (), result

    @internal
    def __rebind__(self, right: Any):
        return resolve(self.expr, right, result=self, cast=self.writetype)

    @internal
    def __setattr__(self, key: str, value):
        if not self._constructed:
            super().__setattr__(key, value)
        else:
            self.__setitem__(key, value)

    @internal
    def __setitem__(self, key: str, value):
        child = self.__getitem__(key)
        child.__rebind__(value)

    def __getitem__(
        self, key: Union[slice, str, dict[str, Any], int, NbtType, Path]
    ) -> Any:
        if self.is_lazy():
            self.evaluate()
            return self[key]

        if is_type(key, allow_dict=False):
            return replace(self, writetype=convert_type(key) or Any)

        if isinstance(key, str):
            if method := self.operator_handler.get(key):
                return method

        if key is SOLO_COLON:
            sub_path = Path()[:]
        elif (
            isinstance(key, dict)
            or isinstance(key, str)
            and (key[0], key[-1]) == ("{", "}")
        ):
            compound = parse_compound(key)
            sub_path = Path()[:][compound]
        else:
            sub_path = Path()[key]

        return self._access(sub_path)

    __getattr__ = __getitem__

    def _access(self, sub_path: Path) -> "DataSource":
        if not len(sub_path):
            return self

        handler = self.operator_handler

        accessor, *rest = cast(tuple[Accessor, ...], tuple(sub_path))

        if isinstance(accessor, ListIndex) and not handler.list_index:
            raise TypeError(
                f"Data source of type '{format_type(self.readtype)}' object is not indexable"
            )

        if isinstance(accessor, CompoundMatch) and not handler.compound_match:
            raise TypeError(
                f"Data source of type '{format_type(self.readtype)}' does not support compound matching"
            )

        if isinstance(accessor, NamedKey) and not handler.named_key:
            raise TypeError(
                f"Data source of type '{format_type(self.readtype)}' does not have named keys"
            )

        writetype = access_type(self.writetype, accessor, self.expr.ctx) or Any
        path = Path.from_accessors((*self._path, accessor))  # type: ignore

        source = replace(self, _path=path, writetype=writetype)

        if not len(rest):
            return source

        rest_path = Path.from_accessors(tuple(rest))  # type: ignore
        return source._access(rest_path)

    @overload
    def __call__(self, matching: str | Path | Compound, /) -> Any:
        ...

    @overload
    def __call__(
        self,
        /,
        *,
        scale: float | None = None,
        type: str | None = None,
    ) -> Any:
        ...

    def __call__(
        self,
        matching: str | Path | Compound | None = None,
        /,
        *,
        scale: float | None = None,
        type: str | None = None,
    ) -> Any:
        """Create a new DataSource with modified properties."""
        if self.is_lazy():
            self.evaluate()
            return self(matching) if matching else self(scale=scale, type=type)

        if matching is not None:
            sub_path = Path()[parse_compound(matching)]
            return self._access(sub_path)

        writetype = literal_types[type] if type else self.writetype

        return replace(
            self,
            _scale=scale if scale is not None else self._scale,
            writetype=writetype,
        )

    def __str__(self):
        return f"{self._type} {self._target} {self._path}"

    def __repr__(self):
        return f'"{str(self)}"'

    @operator_method
    def component(self, **tags: Any):
        return {"nbt": str(self._path), self._type: self._target, **tags}
