# Testing Guide

## Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
uv run pytest tests/cli/test_auto.py -v

# Run specific test
uv run pytest tests/test_models.py::test_skill_route -v

# Run only unit tests
uv run pytest -m unit

# Run only integration tests
uv run pytest -m integration

# Run benchmarks
make benchmark
```

## Writing Tests

### Test Structure

```python
class TestComponentName:
    """Tests for ComponentName."""

    def test_specific_behavior(self) -> None:
        """Test a specific behavior."""
        # Arrange
        component = ComponentName()

        # Act
        result = component.method(input)

        # Assert
        assert result == expected
```

### Using Fixtures

Shared fixtures are in `tests/conftest.py`. Module-specific fixtures are in each subdirectory's `conftest.py`.

```python
def test_with_fixture(sample_skill, temp_dir):
    # sample_skill from tests/conftest.py
    # temp_dir from tests/conftest.py
    pass
```

### Mocking

Use `pytest-mock` for mocking:

```python
def test_with_mock(mocker):
    mock_router = mocker.patch('vibesop.routing.engine.SkillRouter')
    mock_router.route.return_value = expected_result
```

## Coverage Gate

The enforced gate — CI `test` job and `make test-cov` — is total coverage
≥ 73% with branch coverage enabled, matching `[tool.coverage.report]
fail_under = 73` in `pyproject.toml`:

```bash
pytest -m "not benchmark and not slow" --cov=src/vibesop --cov-branch --cov-fail-under=73
```

The 73% floor is measured on the non-benchmark/non-slow suite (the full
suite lands ~3% higher). No per-module thresholds are enforced — treat
73% as a floor, not a target.
