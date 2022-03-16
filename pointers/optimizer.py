from typing import Any, Dict, Iterable, TypeVar, Callable, List
from functools import wraps
from itertools import chain

from rich import print

from .operations import (
    Operation,
    ScoreSource,
    TempScoreSource,
    ConstantScoreSource,
    Set,
    Add,
    Subtract,
    Multiply,
    Divide,
    Modulus,
)

Rule = Callable[[Iterable[Operation]], None]


class Optimizer:
    rules: List[Rule] = []

    @classmethod
    def rule(cls, f):
        cls.rules.append(f)
        return f

    @classmethod
    def optimize(cls, nodes: Iterable[Operation]):
        for rule in cls.rules:
            nodes = rule(nodes)

        yield from nodes


@Optimizer.rule
def temp_var_collapsing(nodes: Iterable[Operation]):
    map: Dict[TempScoreSource, TempScoreSource] = {}

    def get_replaced(source):
        # get the very last source if they're chained
        replaced = map.get(source)
        return get_replaced(replaced) if replaced else source

    for node in nodes:
        # print("[bold]temp_var_collapsing[/bold]", node)
        if (
            type(node) is Set
            and type(node.former) is TempScoreSource
            and type(node.latter) is TempScoreSource
        ):
            # peek: Operation = next(nodes)  # deletes current node
            replaced_latter = get_replaced(node.latter)
            map[node.former] = replaced_latter
            # yield peek.__class__(node.latter, peek.latter)
        else:
            yield node.__class__(get_replaced(node.former), get_replaced(node.latter))


@Optimizer.rule
def constant_to_literal_replacement(nodes: Iterable[Operation]) -> Iterable[Operation]:
    for node in nodes:
        # print("[bold]constant_to_literal_replacement[/bold]", node)
        if (
            isinstance(node, (Set, Add, Subtract))
            and type(node.latter) is ConstantScoreSource
        ):
            literal = node.latter.scoreholder[1:]
            yield node.__class__(node.former, int(literal))
        else:
            yield node


@Optimizer.rule
def print_empty(nodes: Iterable[Operation]) -> Iterable[Operation]:
    for node in nodes:
        # print()
        yield node
