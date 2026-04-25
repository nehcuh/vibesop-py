"""Tests for safe AST-based expression evaluation in WorkflowEngine."""

from __future__ import annotations

from vibesop.core.skills.workflow import (
    ExecutionContext,
    WorkflowEngine,
)


class TestSafeEvalCondition:
    """Test safe condition evaluation using AST parsing."""

    def test_safe_eval_basic_comparisons(self) -> None:
        """Test basic comparison operations."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={"x": 5, "y": 10})

        # Equality
        assert engine._evaluate_condition("x == 5", context) is True
        assert engine._evaluate_condition("x == 10", context) is False

        # Inequality
        assert engine._evaluate_condition("x != 10", context) is True
        assert engine._evaluate_condition("x != 5", context) is False

        # Less than
        assert engine._evaluate_condition("x < y", context) is True
        assert engine._evaluate_condition("y < x", context) is False

        # Less than or equal
        assert engine._evaluate_condition("x <= 5", context) is True
        assert engine._evaluate_condition("x <= 4", context) is False

        # Greater than
        assert engine._evaluate_condition("y > x", context) is True
        assert engine._evaluate_condition("x > y", context) is False

        # Greater than or equal
        assert engine._evaluate_condition("x >= 5", context) is True
        assert engine._evaluate_condition("x >= 6", context) is False

    def test_safe_eval_boolean_operations(self) -> None:
        """Test boolean operations (and, or, not)."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={"x": 5, "y": 10, "z": True})

        # AND
        assert engine._evaluate_condition("x == 5 and y == 10", context) is True
        assert engine._evaluate_condition("x == 5 and y == 5", context) is False

        # OR
        assert engine._evaluate_condition("x == 5 or y == 5", context) is True
        assert engine._evaluate_condition("x == 10 or y == 5", context) is False

        # NOT
        assert engine._evaluate_condition("not (x == 10)", context) is True
        assert engine._evaluate_condition("not (x == 5)", context) is False

        # Complex boolean
        assert engine._evaluate_condition("(x == 5 or y == 5) and z", context) is True
        assert engine._evaluate_condition("(x == 10 or y == 5) and z", context) is False

    def test_safe_eval_arithmetic_operations(self) -> None:
        """Test arithmetic operations in conditions."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={"x": 5, "y": 10})

        # Addition
        assert engine._evaluate_condition("x + y == 15", context) is True

        # Subtraction
        assert engine._evaluate_condition("y - x == 5", context) is True

        # Multiplication
        assert engine._evaluate_condition("x * y == 50", context) is True

        # Division
        assert engine._evaluate_condition("y / x == 2", context) is True

        # Modulo
        assert engine._evaluate_condition("y % x == 0", context) is True

        # Power
        assert engine._evaluate_condition("x ** 2 == 25", context) is True

    def test_safe_eval_in_operator(self) -> None:
        """Test 'in' operator."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={"x": 5, "items": [1, 2, 3, 4, 5]})

        # Value in list (if items is a list)
        # Note: This might not work as expected since we're evaluating expressions
        # and 'items' would be the list object
        assert engine._evaluate_condition("5 in [1, 2, 3, 4, 5]", context) is True
        assert engine._evaluate_condition("6 in [1, 2, 3, 4, 5]", context) is False

    def test_safe_eval_string_operations(self) -> None:
        """Test string operations."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={"name": "test"})

        # String equality
        assert engine._evaluate_condition('name == "test"', context) is True
        assert engine._evaluate_condition('name == "other"', context) is False

    def test_safe_eval_builtin_functions(self) -> None:
        """Test safe built-in function calls."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={"x": 5, "items": [1, 2, 3]})

        # len()
        assert engine._evaluate_condition("len(items) == 3", context) is True

        # abs()
        assert engine._evaluate_condition("abs(-5) == 5", context) is True

        # min/max
        assert engine._evaluate_condition("min(1, 2, 3) == 1", context) is True
        assert engine._evaluate_condition("max(1, 2, 3) == 3", context) is True

        # sum()
        assert engine._evaluate_condition("sum([1, 2, 3]) == 6", context) is True

        # any/all
        assert engine._evaluate_condition("any([True, False, False])", context) is True
        assert engine._evaluate_condition("all([True, True, False])", context) is False

        # isinstance
        assert engine._evaluate_condition("isinstance(5, int)", context) is True
        assert engine._evaluate_condition('isinstance("test", str)', context) is True

    def test_safe_eval_blocks_dangerous_operations(self) -> None:
        """Test that dangerous operations are blocked."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={"x": 5})

        # Block import
        assert engine._evaluate_condition('__import__("os")', context) is False

        # Block open
        assert engine._evaluate_condition('open("/etc/passwd")', context) is False

        # Block eval
        assert engine._evaluate_condition('eval("1+1")', context) is False

        # Block exec
        assert engine._evaluate_condition('exec("print(1)")', context) is False

        # Block dangerous attribute access
        assert engine._evaluate_condition('().__class__', context) is False
        assert engine._evaluate_condition('[].__class__', context) is False
        assert engine._evaluate_condition('{}.__class__', context) is False

    def test_safe_eval_syntax_error(self) -> None:
        """Test that syntax errors are handled gracefully."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={"x": 5})

        # Invalid syntax
        assert engine._evaluate_condition("x === 5", context) is False
        assert engine._evaluate_condition("x .. 5", context) is False

    def test_safe_eval_with_variables(self) -> None:
        """Test variable substitution in conditions."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={
            "status": "success",
            "count": 42,
            "enabled": True,
        })

        # String variable
        assert engine._evaluate_condition('status == "success"', context) is True

        # Number variable
        assert engine._evaluate_condition("count == 42", context) is True

        # Boolean variable
        assert engine._evaluate_condition("enabled", context) is True
        assert engine._evaluate_condition("not enabled", context) is False

    def test_safe_eval_complex_expressions(self) -> None:
        """Test complex but safe expressions."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={
            "x": 5,
            "y": 10,
            "z": 15,
            "name": "test",
        })

        # Complex arithmetic and comparison
        assert engine._evaluate_condition("(x + y) * 2 == z * 2", context) is True

        # Complex boolean
        assert engine._evaluate_condition(
            "(x == 5 or y == 5) and (name == 'test')",
            context
        ) is True

        # Nested comparisons
        assert engine._evaluate_condition("x < y < z", context) is True

    def test_safe_eval_returns_false_on_invalid(self) -> None:
        """Test that invalid conditions return False rather than crashing."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={"x": 5})

        # Division by zero should return False
        result = engine._evaluate_condition("x / 0", context)
        assert result is False

        # Type errors should return False
        result = engine._evaluate_condition("x + 'string'", context)
        assert result is False

        # Name errors should return False
        result = engine._evaluate_condition("undefined_var == 5", context)
        assert result is False

    def test_safe_eval_preserves_constants(self) -> None:
        """Test that True, False, None work correctly."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={})

        assert engine._evaluate_condition("True", context) is True
        assert engine._evaluate_condition("False", context) is False
        assert engine._evaluate_condition("None == None", context) is True

        # Combined with variables
        context_with_vals = ExecutionContext(skill_id="test", variables={"x": True, "y": False})
        assert engine._evaluate_condition("x and not y", context_with_vals) is True
