from dataclasses import dataclass, field, replace
from functools import cache
from itertools import count
from typing import Callable, ClassVar, Union

from nbtlib import Compound, Path

from . import operations as op
from .literals import convert_tag
from .node import ExpressionNode

# from rich.pretty import pprint


SOLO_COLON = slice(None, None, None)


class Source(ExpressionNode):
    ...


@dataclass(unsafe_hash=True, order=False)
class ScoreSource(Source):
    scoreholder: str
    objective: str

    def __rebind__(self, other: ExpressionNode):
        self.emit("rebind", other)
        return self

    def __str__(self):
        return f"{self.scoreholder} {self.objective}"

    def __repr__(self):
        return f'"{str(self)}"'

    @property
    def holder(self):
        return self.scoreholder

    @property
    def obj(self):
        return self.objective


@dataclass(unsafe_hash=True, order=False)
class ConstantScoreSource(ScoreSource):
    objective: str = "const"
    value: int = field(hash=False, kw_only=True)

    @classmethod
    def create(cls, value: Union[str, int, float]):
        return super().create(f"${int(value)}", cls.objective, value=value)
    
    @classmethod
    def from_name(cls, name: str):
        value = name[1:]
        return cls.create(value)


class TempScoreSource(ScoreSource):
    objective: str = "temp"
    count: ClassVar[int] = -1

    @classmethod
    def create(cls):
        cls.count += 1
        return super().create(f"$i{cls.count}", cls.objective)


def parse_compound(value: Union[str, dict, Path, Compound]):
    if type(value) in (Path, Compound):
        return value
    if type(value) is dict:
        return convert_tag(value)
    return Path(value)


@dataclass(unsafe_hash=True, order=False)
class DataSource(Source):
    _default_nbt_type: ClassVar[str] = "int"
    _default_floating_point_type: ClassVar[str] = "double"
    _type: str
    _target: str
    _path: Path = field(default_factory=Path)
    _scale: float = 1
    _nbt_type: str = None

    _constructed: bool = field(hash=False, default=False, init=False)

    def __post_init__(self):
        self._constructed = True

    def unroll(self):
        temp_var = TempScoreSource.create()
        yield op.Set.create(temp_var, self)
        yield temp_var

    def __rebind__(self, other):
        self.emit("rebind", other)
        return self

    def __setattr__(self, key: str, value):
        if not self._constructed:
            super().__setattr__(key, value)
        else:
            self.__setitem__(key, value)

    def __setitem__(self, key: str, value):
        child = self.__getitem__(key)
        child.__rebind__(value)

    def __getitem__(self, key: Union[str, int, Path, Compound]) -> "DataSource":
        if key is SOLO_COLON:
            # self[:]
            return self.all()
        if type(key) is str and key[0] == "{" and key[-1] == "}":
            # self[{abc:1b}]
            return self.filtered(key)
        # self[0] or self.foo
        path = self._path[key]
        return replace(self, _path=path)

    def __getattr__(self, key: str):
        try:
            return super().__getattr__(key)
        except AttributeError:
            return self.__getitem__(key)

    def __call__(
        self,
        matching: Union[str, Path, Compound] = None,
        scale: float = None,
        type: str = None,
    ) -> "DataSource":
        """Create a new DataSource with modified properties."""
        if matching is not None:
            path = self._path[parse_compound(matching)]
        else:
            path = self._path
        return replace(
            self,
            _path=path,
            _scale=scale if scale is not None else self._scale,
            _nbt_type=type if type is not None else self._nbt_type,
        )

    def __str__(self):
        return f"{self._type} {self._target} {self._path}"

    def __repr__(self):
        return f'"{str(self)}"'

    def get_type(self):
        return self._nbt_type if self._nbt_type else self._default_nbt_type

    def all(self) -> "DataSource":
        path = self._path + "[]"
        return replace(self, _path=path)

    def filtered(self, value: Union[str, Path, Compound]):
        compound = parse_compound(value)
        path = self._path[:][compound]
        return replace(self, _path=path)
