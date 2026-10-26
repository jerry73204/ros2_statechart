# Copyright 2026 The ros2_statechart Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
Chart expressions, ns/1: the Python subset of docs/FORMAT.md section 8.

``check(text, role, context)`` parses one expression with ``ast`` and returns
a list of problems (strings). ``role`` is ``'cond'`` (must be boolean),
``'value'`` or ``'location'`` (a datamodel name). ``context`` says which
names exist: datamodel values (with their initial literals), model
attributes, state ids.
"""

import ast
from dataclasses import dataclass, field
import keyword

EVENT_DATA = frozenset({'msg', 'request', 'goal'})
JS_NAMES = {'true': 'True', 'false': 'False', 'null': 'None'}
JS_OPERATORS = (('===', '=='), ('!==', '!='), ('&&', 'and'), ('||', 'or'))
RESERVED_PREFIX = 'sc_ros_'
COMPARISONS = {ast.Eq: '==', ast.NotEq: '!=', ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>',
               ast.GtE: '>='}
ARITHMETIC = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/'}
REFUSED_NODES = {
    ast.Subscript: 'indexing and slicing', ast.ListComp: 'comprehensions',
    ast.SetComp: 'comprehensions', ast.DictComp: 'comprehensions',
    ast.GeneratorExp: 'comprehensions', ast.Lambda: 'lambda', ast.JoinedStr: 'f-strings',
    ast.FormattedValue: 'f-strings', ast.NamedExpr: ':=', ast.IfExp: 'conditional expressions',
    ast.List: 'list displays', ast.Tuple: 'tuple displays', ast.Dict: 'dict displays',
    ast.Set: 'set displays', ast.Starred: 'starred expressions', ast.Await: 'await',
    ast.Yield: 'yield', ast.YieldFrom: 'yield', ast.Slice: 'slicing',
}


@dataclass
class Context:
    """The names an expression may use."""

    data: dict = field(default_factory=dict)       # id -> initial expression text
    model: set = field(default_factory=set)        # public attributes of the model class
    guards: set = field(default_factory=set)       # callable ones among them
    states: set = field(default_factory=set)
    open_event_data: bool = False                  # a data builder may add names


def reserved(name):
    """Whether a name may not be a datamodel or guard name."""
    return name.startswith('_') or name.startswith(RESERVED_PREFIX) or keyword.iskeyword(name)


def bool_data(context, name):
    """Whether a datamodel value is boolean by its initial literal."""
    text = context.data.get(name)
    if text is None:
        return False
    try:
        return isinstance(ast.literal_eval(text.strip()), bool)
    except (ValueError, SyntaxError):
        return False


def check(text, role, context):
    """Return the problems of one expression (empty when it is a chart expression)."""
    stripped = (text or '').strip()
    if role == 'location':
        if not stripped.isidentifier() or keyword.iskeyword(stripped):
            return [f'<assign location="{text}">: the location is a datamodel name only']
        if reserved(stripped):
            return [f'<assign location="{text}">: "{stripped}" is a reserved name']
        if stripped not in context.data:
            return [f'<assign location="{text}">: "{stripped}" is not a datamodel value']
        return []
    try:
        tree = ast.parse(stripped, mode='eval')
    except SyntaxError as exc:
        hints = [f'"{js}" is JavaScript; write "{py}"' for js, py in JS_OPERATORS
                 if js in stripped]
        if not hints and '!' in stripped.replace('!=', ''):
            hints = ['"!" is JavaScript; write "not"']
        return hints or [f'not a Python expression: {exc.msg}']
    walker = _Walker(context)
    walker.visit(tree.body)
    problems = walker.problems
    if role == 'cond' and not problems and not is_boolean(tree.body, context):
        problems.append('a condition must be boolean: a comparison, a boolean datamodel '
                        'value, In(...), a guard, or and/or/not of those')
    return problems


def is_boolean(node, context):
    """Whether an (allowed) expression is boolean-typed."""
    if isinstance(node, ast.Compare):
        return True
    if isinstance(node, ast.BoolOp):
        return all(is_boolean(v, context) for v in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return is_boolean(node.operand, context)
    if isinstance(node, ast.Call):
        return True  # In(...), the only call allowed
    if isinstance(node, ast.Constant):
        return isinstance(node.value, bool)
    if isinstance(node, ast.Name):
        return node.id in context.guards or bool_data(context, node.id)
    return False


class _Walker(ast.NodeVisitor):

    def __init__(self, context):
        self.context = context
        self.problems = []

    def refuse(self, what):
        if what not in self.problems:
            self.problems.append(what)

    def generic_visit(self, node):
        name = REFUSED_NODES.get(type(node))
        if name is not None:
            self.refuse(f'{name} are not allowed' if name.endswith('s')
                        else f'{name} is not allowed')
            return
        self.refuse(f'{type(node).__name__} is not allowed in a chart expression')

    def visit_Constant(self, node):
        if not (node.value is None or isinstance(node.value, (bool, int, float, str))):
            self.refuse(f'the literal {node.value!r} is not allowed')

    def visit_Name(self, node):
        name = node.id
        if name in JS_NAMES:
            self.refuse(f'"{name}" is JavaScript; write "{JS_NAMES[name]}"')
        elif name == 'In':
            self.refuse("In is only allowed as a call: In('STATE')")
        elif name.startswith('_') or name.startswith(RESERVED_PREFIX):
            self.refuse(f'"{name}" is a reserved name')

    def visit_Attribute(self, node):
        if node.attr.startswith('_'):
            self.refuse(f'attribute "{node.attr}" is reserved')
        base = node.value
        if not isinstance(base, (ast.Name, ast.Attribute)):
            self.refuse('attributes are read only from names (msg.data, goal.station)')
            return
        self.visit(base)

    def visit_BoolOp(self, node):
        for value in node.values:
            self.visit(value)

    def visit_UnaryOp(self, node):
        if not isinstance(node.op, (ast.Not, ast.USub)):
            self.refuse(f'the operator {type(node.op).__name__} is not allowed')
            return
        self.visit(node.operand)

    def visit_BinOp(self, node):
        if type(node.op) not in ARITHMETIC:
            op = {ast.Pow: '**', ast.FloorDiv: '//', ast.Mod: '%'}.get(type(node.op))
            self.refuse(f'"{op}" is not allowed' if op else 'bitwise operators are not '
                        'allowed')
            return
        for side in (node.left, node.right):
            if isinstance(side, ast.Constant) and isinstance(side.value, (str, bool)) \
                    or isinstance(side, ast.Constant) and side.value is None:
                self.refuse('arithmetic is on numbers only')
        self.visit(node.left)
        self.visit(node.right)

    def visit_Compare(self, node):
        if len(node.ops) != 1:
            self.refuse('chained comparisons are not allowed: write a < b and b < c')
            return
        op = type(node.ops[0])
        if op not in COMPARISONS:
            name = {ast.Is: 'is', ast.IsNot: 'is not', ast.In: 'in', ast.NotIn: 'not in'}.get(
                op, op.__name__)
            self.refuse(f'"{name}" is not allowed')
            return
        self.visit(node.left)
        self.visit(node.comparators[0])

    def visit_Call(self, node):
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == 'In'):
            self.refuse("calls are not allowed (only In('STATE'); guards are names)")
            return
        if node.keywords or len(node.args) != 1 or not (
                isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
            self.refuse("In takes one literal state id: In('STATE')")
            return
        state = node.args[0].value
        if self.context.states and state not in self.context.states:
            self.refuse(f'In(\'{state}\'): no state "{state}"')


def names(text):
    """Return the root names an expression reads (In excluded)."""
    try:
        tree = ast.parse((text or '').strip(), mode='eval')
    except SyntaxError:
        return set()
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id != 'In':
            found.add(node.id)
    return found
