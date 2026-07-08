"""Fuzz tests for WorkflowEngine._evaluate_condition AST sandbox (F-01).

Despite the AST whitelist, eval() of untrusted source remains a high-risk
surface. This suite throws a large, diverse payload set at the sandbox and
asserts that none escape: every call returns a plain bool, no exception
propagates, and known-malicious payloads are rejected (return False).
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from vibesop.core.skills.workflow import ExecutionContext, WorkflowEngine


class TestWorkflowEvalFuzz:
    """200+ payload fuzz against _evaluate_condition."""

    # Payloads that must be rejected (return False) by the sandbox.
    MALICIOUS_PAYLOADS: ClassVar[list[str]] = [
        # Dunder / introspection access
        "().__class__",
        "(1).__class__",
        "[].__class__",
        "{}.__class__",
        "''.__class__",
        "().__class__.__base__",
        "[].__class__.__mro__",
        "{}.__class__.__bases__",
        "().__dict__",
        "object.__subclasses__",
        "().__class__.__subclasses__()",
        "[].__class__.__subclasses__()",
        # __import__ / eval / exec
        "__import__('os')",
        "__import__('sys')",
        "eval('1+1')",
        "exec('pass')",
        "compile('1', '', 'eval')",
        "open('/etc/passwd')",
        # getattr chains
        "getattr((), '__class__')",
        "getattr([], '__class__')",
        "getattr('', '__class__')",
        "getattr(1, '__class__')",
        "getattr(getattr((), 'a'), 'b')",
        "getattr(().__class__, '__base__')",
        "getattr([].__class__, '__base__')",
        "hasattr((), '__class__') and getattr((), '__class__')",
        # Subscript / item access to dunder
        "().__class__['__base__']",
        "[].__class__['__mro__']",
        "{}.__class__['__bases__']",
        # Non-whitelisted AST nodes
        "lambda: 1",
        "(lambda: 1)()",
        "x for x in []",  # generator expression (not ListComp)
        "{x for x in []}",  # set comprehension
        "{x: x for x in []}",  # dict comprehension
        "yield 1",
        "await 1",
        "f'{x}'",
        # Dangerous builtins not on allowlist
        "exec('pass')",
        "compile('1', 'a', 'eval')",
        "__build_class__",
        "breakpoint()",
        "input()",
        "print()",
        # Type / class exploitation
        "type(())",
        "type([])",
        "type('X', (), {})()",
        "object.__init__",
        "().__init__",
        # Attribute chains that end in calls
        "''.format()",
        "[].append(1)",
        "[].pop()",
        "{}.clear()",
        "().__str__()",
        # List comprehensions with dangerous elements
        "[x.__class__ for x in [()]]",
        "[().__class__ for _ in [1]]",
        "[getattr(x, '__class__') for x in [()]]",
        "[x for x in [().__class__]]",
        # Nested / obfuscated
        "(().__class__) if True else 1",
        "True and ().__class__",
        "not ().__class__",
        "any([().__class__])",
        "all([().__class__])",
        "len([().__class__])",
        # Variable-name attacks (context injection)
        "__builtins__",
        "__globals__",
        "__loader__",
        "__spec__",
        # Arithmetic that might reach object internals
        "1 + ().__class__",
        "[] * 1000000",
        # Import via __import__ hidden in variable
        "__import__",
        # getattr with computed attribute name
        "getattr((), '_' + '_class_')",
        "getattr((), '__class__'[:8])",
        # String methods that can eval
        "'1+1'.eval()",
        "'__import__(\"os\")'.encode()",
        # Boolean short-circuit attacks
        "False or ().__class__",
        "True and ().__class__",
        # Tuple unpacking / named expressions (Python 3.8+)
        "(x := 1)",
        # f-strings (FormattedValue)
        'f"{x}"',
        # Walrus in comprehension
        "[y := x for x in []]",
        # ast.Subscript through allowed literal
        "[1, 2, 3][0].__class__",
        "{'a': 1}['a'].__class__",
        # JoinedStr
        '"" + f"{x}"',
        # Starred
        "*[]",
        # Imports via __import__ inside comprehension
        "[__import__('os') for x in []]",
        # Calls to object internals
        "object()",
        "super()",
        "vars()",
        "locals()",
        "globals()",
        # getattr on function results
        "getattr(len, '__class__')",
        "getattr(max, '__class__')",
        # Additional dunder / introspection vectors
        "().__class__.__name__",
        "[].__class__.__module__",
        "''.__class__.__qualname__",
        "().__hash__",
        "[].__iter__",
        "{}.__iter__",
        "().__repr__",
    ]

    # Benign payloads that should evaluate without error (result is a bool).
    BENIGN_PAYLOADS: ClassVar[list[str]] = [
        "1 == 1",
        "1 != 2",
        "2 > 1",
        "1 < 2",
        "2 >= 2",
        "2 <= 2",
        "True and True",
        "True or False",
        "not False",
        "1 + 2 == 3",
        "5 - 2 == 3",
        "2 * 3 == 6",
        "6 / 2 == 3",
        "7 % 2 == 1",
        "2 ** 3 == 8",
        "5 in [1, 2, 3, 4, 5]",
        "6 not in [1, 2, 3]",
        "'a' in 'abc'",
        "len([1, 2, 3]) == 3",
        "len('hello') == 5",
        "str(1) == '1'",
        "int('1') == 1",
        "float('1.5') == 1.5",
        "bool(1) is True",
        "abs(-5) == 5",
        "min(1, 2) == 1",
        "max(1, 2) == 2",
        "sum([1, 2, 3]) == 6",
        "round(1.5) == 2",
        "pow(2, 3) == 8",
        "any([True, False])",
        "all([True, True])",
        "ord('a') == 97",
        "chr(97) == 'a'",
        "isinstance(1, int)",
        "hasattr([], 'append')",
        "getattr([], 'append') is not None",
        "[x for x in [1, 2, 3] if x > 1] == [2, 3]",
        "[x * 2 for x in [1, 2]] == [2, 4]",
        "{'a': 1}.get('a') == 1",
        "(1, 2, 3)[0] == 1",
        "{1, 2, 3} == {1, 2, 3}",
        "enumerate([1, 2])",
        "zip([1], [2])",
        "filter(lambda: True, [])" if False else "filter(bool, [])",  # lambda blocked
        "filter(bool, [True, False])",
        "map(bool, [1, 0])",
        # Additional benign string / list / dict / tuple / set
        "'abc'.startswith('a')",
        "'abc'.endswith('c')",
        "'a,b,c'.split(',') == ['a', 'b', 'c']",
        "'-'.join(['a', 'b']) == 'a-b'",
        "[1, 2, 3].count(2) == 1",
        "[1, 2, 3].index(2) == 1",
        "'hello'.upper() == 'HELLO'",
        "'HELLO'.lower() == 'hello'",
        "3 % 2 == 1",
        "2 ** 10 == 1024",
        "-5 == -5",
        "+5 == 5",
        "not (1 == 2)",
        "(1 == 1) is True",
        "(1 == 2) is False",
        "None is None",
        "1 is not 2",
        "len({'a': 1, 'b': 2}) == 2",
        "len((1, 2, 3)) == 3",
        "len({1, 2, 3}) == 3",
        "{'a': 1}.keys()",
        "{'a': 1}.values()",
        "{'a': 1}.items()",
        "(1, 2)[1] == 2",
        "{1, 2, 2, 3} == {1, 2, 3}",
        "[x + 1 for x in [1, 2, 3]] == [2, 3, 4]",
        "[x for x in range(3)] == [0, 1, 2]",
        "sum([x for x in [1, 2, 3]]) == 6",
        "list((1, 2)) == [1, 2]",
        "tuple([1, 2]) == (1, 2)",
        "set([1, 2, 2]) == {1, 2}",
        "dict([('a', 1)]) == {'a': 1}",
        "isinstance([], list)",
        "isinstance({}, dict)",
        "isinstance('', str)",
        "hasattr({}, 'get')",
        "getattr({}, 'get') is not None",
        "abs(-10) == 10",
        "min([3, 1, 2]) == 1",
        "max([3, 1, 2]) == 3",
        "sum(range(4)) == 6",
        "round(2.5) == 2",
        "pow(3, 2) == 9",
        "list(enumerate(['a', 'b'])) == [(0, 'a'), (1, 'b')]",
        "list(zip([1, 2], ['a', 'b'])) == [(1, 'a'), (2, 'b')]",
        "list(filter(bool, [0, 1, 2])) == [1, 2]",
        "list(map(str, [1, 2])) == ['1', '2']",
        # Subscript / slice on allowed literals (regression coverage)
        "[1, 2, 3][0] == 1",
        "[1, 2, 3][:] == [1, 2, 3]",
        "'abc'[0] == 'a'",
        "'abc'[:2] == 'ab'",
        "{'a': 1}['a'] == 1",
        "(1, 2, 3)[2] == 3",
        "x == 1",
        "x != 0",
        "x + 2 == 3",
        "x in items",
        "items == [1, 2, 3]",
        "len(items) == 3",
        "True",
        "not False",
        "1 < 2 < 3",
        "1 <= 2 <= 3",
        "3 > 2 > 1",
        "...",
        "bool(...) is True",
        # Non-execution information / obfuscation probes (benign data)
        "getattr(str, 'format')",
        "getattr(list, 'append')",
        "getattr(dict, 'clear')",
        "hasattr(str, 'format') and getattr(str, 'format')",
        "hasattr((), '__class__')",
        "hasattr([], '__class__')",
        "('__' + 'class' + '__')",
        "{'__class__': 1}",
        "chr(95) + chr(95)",
        '"""__import__(\'os\')"""',
        "'＿＿class＿＿'",  # fullwidth underscore
        "0x5f5f",
    ]

    @pytest.fixture(autouse=True)
    def _engine(self):
        self.engine = WorkflowEngine()
        self.context = ExecutionContext(skill_id="fuzz", variables={"x": 1, "items": [1, 2, 3]})

    @pytest.mark.parametrize("payload", MALICIOUS_PAYLOADS)
    def test_malicious_payload_returns_false(self, payload: str) -> None:
        """Every known escape vector must be rejected (return False)."""
        result = self.engine._evaluate_condition(payload, self.context)
        assert result is False, f"Payload escaped sandbox: {payload!r}"

    @pytest.mark.parametrize("payload", BENIGN_PAYLOADS)
    def test_benign_payload_returns_bool(self, payload: str) -> None:
        """Benign expressions evaluate to a bool without exception."""
        result = self.engine._evaluate_condition(payload, self.context)
        assert isinstance(result, bool), f"Payload did not return bool: {payload!r} -> {result!r}"

    # Variable-substitution attack vectors: the attacker controls a context
    # variable value, which is interpolated into the condition string before
    # AST parsing. This is the scenario described in the F-01 finding.
    SUBSTITUTION_ATTACKS: ClassVar[list[tuple[str, dict[str, object]]]] = [
        ("{payload}", {"payload": "().__class__"}),
        ("{payload}", {"payload": "__import__('os')"}),
        ("{payload}", {"payload": "eval('1')"}),
        ("{payload}", {"payload": "getattr((), '__class__')"}),
        ("{payload}", {"payload": "[x.__class__ for x in [()]]"}),
        ("x == {payload}", {"payload": "1 and ().__class__"}),
        ("{payload} == False", {"payload": "().__class__"}),
        ("not {payload}", {"payload": "().__class__"}),
        ("len({payload})", {"payload": "[().__class__]"}),
        ("{a} and {b}", {"a": "True", "b": "().__class__"}),
        # Additional substitution vectors
        ("{payload}", {"payload": "__builtins__"}),
        ("{payload}", {"payload": "().__dict__"}),
        ("{payload}", {"payload": "[].__class__.__mro__"}),
        ("{payload}", {"payload": "{}.__class__.__bases__"}),
        ("{payload}", {"payload": "().__class__.__subclasses__()"}),
        ("{payload}", {"payload": "getattr(1, '__class__')"}),
        ("{payload}", {"payload": "hasattr((), '__class__') and getattr((), '__class__')"}),
        ("{payload}", {"payload": "lambda: 1"}),
        ("{payload}", {"payload": "(lambda: 1)()"}),
        ("{payload}", {"payload": "__import__('os').system('id')"}),
        ("x + {payload}", {"payload": "().__class__"}),
        ("{payload} in [1, 2, 3]", {"payload": "().__class__"}),
        ("{payload} or True", {"payload": "().__class__"}),
        ("True if {payload} else False", {"payload": "().__class__"}),
        ("isinstance({payload}, int)", {"payload": "().__class__"}),
        ("bool({payload})", {"payload": "().__class__"}),
        ("str({payload})", {"payload": "().__class__"}),
        ("len([{payload}])", {"payload": "().__class__"}),
        ("{payload}", {"payload": "f'{x.__class__}'"}),
        ("{payload}", {"payload": "(x := 1)"}),
    ]

    @pytest.mark.parametrize("condition,variables", SUBSTITUTION_ATTACKS)
    def test_substitution_attack_blocked(
        self, condition: str, variables: dict[str, object]
    ) -> None:
        """Attacker-controlled variable values interpolated into the condition
        must not produce an executable AST escape."""
        context = ExecutionContext(skill_id="fuzz", variables=variables)
        result = self.engine._evaluate_condition(condition, context)
        assert result is False, f"Substitution attack escaped: {condition!r} with {variables!r}"

    def test_no_exceptions_propagate_for_malformed_input(self) -> None:
        """Malformed / edge-case inputs are swallowed and return False."""
        for payload in ["", "   ", "::", "@", "$", "`", "\\", "???"]:
            result = self.engine._evaluate_condition(payload, self.context)
            assert result is False, f"Unexpected result for {payload!r}: {result!r}"

    def test_payload_count_meets_target(self) -> None:
        """Sanity check that the fuzz corpus is at least 200 payloads."""
        total = (
            len(self.MALICIOUS_PAYLOADS)
            + len(self.BENIGN_PAYLOADS)
            + len(self.SUBSTITUTION_ATTACKS)
        )
        assert total >= 200, f"Fuzz corpus too small: {total}"
