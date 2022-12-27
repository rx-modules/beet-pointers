import re
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Callable, Iterable, List

from beet.core.utils import required_field
from mecha import AstCommand, AstNode, AstObjective, AstPlayerName, Reducer, rule

from .sources import ConstantScoreSource, DataSource, ScoreSource, Source


@dataclass
class ConstantScoreChecker(Reducer):
    objective: str = required_field()
    callback: Callable = required_field()
    pattern: re.Pattern[str] = re.compile(r"^\$([-+]?\d+)\b")

    @cached_property
    def objective_node(self):
        return AstObjective(value=self.objective)

    @rule(AstCommand)
    def command(self, node: AstCommand):
        if self.objective_node not in node.arguments:
            return

        i = node.arguments.index(self.objective_node)
        name = node.arguments[i - 1]

        if not isinstance(name, AstPlayerName):
            return

        match = self.pattern.match(name.value)

        if not match:
            return

        value = int(match.group(1))
        source = ConstantScoreSource.create(value)

        self.callback(source)


@dataclass
class ObjectiveChecker(Reducer):
    whitelist: Iterable[str] = required_field()
    callback: Callable = required_field()

    @rule(AstObjective)
    def objective(self, node: AstObjective):
        value = node.value

        if value not in self.whitelist:
            return

        self.callback(value)


@dataclass
class SourceJsonConverter:
    converter: Callable[[Any, AstNode], AstNode]

    def convert(self, obj: Any):
        if isinstance(obj, Source):
            return obj.component()
        if isinstance(obj, list):
            return [self.convert(value) for value in obj]
        if isinstance(obj, dict):
            return {key: self.convert(value) for key, value in obj.items()}

        return obj

    def __call__(self, obj: Any, node: AstNode):
        obj = self.convert(obj)

        return self.converter(obj, node)
