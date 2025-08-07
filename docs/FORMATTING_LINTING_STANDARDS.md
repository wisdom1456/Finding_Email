# Formatting & Linting Standards

This document outlines the formatting and linting standards for the Legal Document Analysis Portal project, based on modern Ruff-based tooling.

## Overview

The project uses [Ruff](https://github.com/astral-sh/ruff) as the primary Python linter and formatter, replacing traditional tools like Black, isort, and Flake8. Ruff provides faster performance and comprehensive rule coverage in a single tool.

## Configuration

### Main Configuration: [`pyproject.toml`](../pyproject.toml)

```toml
[tool.ruff]
# Set the maximum line length to 88 (Black's default)
line-length = 88
indent-width = 4

# Assume Python 3.9+
target-version = "py39"

[tool.ruff.lint]
# Comprehensive rule selection
select = [
    "E", "W",    # pycodestyle errors/warnings
    "F",         # Pyflakes
    "I",         # isort
    "B",         # flake8-bugbear
    "C4",        # flake8-comprehensions
    "UP",        # pyupgrade
    "ARG",       # flake8-unused-arguments
    "S",         # flake8-bandit (security)
    "T10",       # flake8-debugger
    "RUF",       # Ruff-specific rules
    # ... (see full configuration in pyproject.toml)
]

# Rules to ignore
ignore = [
    "ANN101",    # Missing type annotation for self
    "S101",      # Use of assert detected (common in tests)
    "COM812",    # Trailing comma missing (conflicts with formatter)
    "ISC001",    # Implicitly concatenated strings (conflicts with formatter)
]
```

### Pre-commit Integration: [`.pre-commit-config.yaml`](../.pre-commit-config.yaml)

```yaml
- repo: https://github.com/astral-sh/ruff-pre-commit
  rev: v0.12.4
  hooks:
    # Run the linter with auto-fix
    - id: ruff
      args: [--fix, --exit-non-zero-on-fix]
      types_or: [python, pyi]
    # Run the formatter
    - id: ruff-format
      types_or: [python, pyi]
```

## Development Workflow

### Local Development Commands

```bash
# Format code automatically
ruff format .

# Lint code and apply auto-fixes
ruff check . --fix

# Check for issues without fixing (CI-safe)
ruff check .

# Get detailed statistics
ruff check . --statistics

# Run all pre-commit hooks
pre-commit run --all-files
```

### Pre-commit Setup

Install and activate pre-commit hooks:

```bash
pip install pre-commit
pre-commit install
```

## CI/CD Integration

### GitHub Actions: [`.github/workflows/lint.yml`](../.github/workflows/lint.yml)

The project includes a comprehensive CI workflow that:

1. **Linting**: Runs `ruff check . --output-format=github --fix`
2. **Formatting**: Runs `ruff format --check .`
3. **Testing**: Executes test suite with coverage
4. **Security**: Performs Bandit security scanning

Key features:
- Multi-Python version testing (3.9, 3.10, 3.11)
- GitHub-native output formatting for inline annotations
- Auto-fix application in CI
- Security scanning integration

### Manual CI Commands

```bash
# Lint with GitHub output format
ruff check . --output-format=github

# Check formatting without modifying files
ruff format --check .

# Combined quality check
ruff check . && ruff format --check .
```

## Security Integration

### SAST Scanning

The project includes comprehensive security scanning:

- **Bandit**: Python security linter (integrated in Ruff via `S` rules)
- **Safety**: Dependency vulnerability scanner
- **Pre-commit**: Automated security checks on commits

### Configuration

```toml
# pyproject.toml
[tool.bandit]
exclude_dirs = ["tests", "*/tests/*", "*/test_*"]
skips = ["B101", "B601"]
```

## Rule Categories

### Enabled Rule Groups

| Code | Category | Description |
|------|----------|-------------|
| E, W | pycodestyle | Style guide enforcement |
| F | Pyflakes | Logical errors |
| I | isort | Import sorting |
| B | flake8-bugbear | Bug and design problems |
| S | flake8-bandit | Security issues |
| UP | pyupgrade | Python version upgrades |
| RUF | Ruff-specific | Ruff's custom rules |

### Security Rules (S codes)

- S101: Use of assert statements
- S105-S108: Hardcoded password detection
- S310: URL handling security
- S601: Shell injection detection

## Best Practices

### 1. Pre-commit Usage

Always run pre-commit hooks before pushing:

```bash
pre-commit run --all-files --show-diff-on-failure
```

### 2. Auto-fixing

Use auto-fix capabilities during development:

```bash
# Fix most issues automatically
ruff check . --fix

# Format code to standard
ruff format .
```

### 3. Editor Integration

Configure your editor to run Ruff on save:

**VS Code**: Install the official Ruff extension
**PyCharm**: Configure Ruff as external tool
**Neovim**: Use ruff-lsp

### 4. Testing Integration

Run linting as part of your test suite:

```bash
# In test scripts or Makefile
ruff check . --statistics
ruff format --check .
pytest
```

## Troubleshooting

### Common Issues

1. **Import sorting conflicts**: Use `# ruff: noqa: I001` for specific lines
2. **Long line exceptions**: Use `# ruff: noqa: E501` sparingly
3. **Security false positives**: Document with `# nosec` comments

### Performance

Ruff is significantly faster than traditional tools:
- **~10-100x faster** than Flake8
- **~10-100x faster** than Black
- **Single tool** replaces multiple dependencies

### Migration from Legacy Tools

The project has been migrated from:
- ~~Black~~ → `ruff format`
- ~~isort~~ → `ruff check --select I`
- ~~Flake8~~ → `ruff check`

## Validation

After setup, validate the configuration:

```bash
# Test linting
ruff check . --statistics

# Test formatting  
ruff format --check .

# Test pre-commit
pre-commit run --all-files

# Verify no legacy conflicts
pip list | grep -E "(black|isort)"  # Should show nothing
```

## References

- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Ruff Rules Reference](https://docs.astral.sh/ruff/rules/)
- [Pre-commit Hooks](https://pre-commit.com/)
- [GitHub Actions Integration](https://docs.astral.sh/ruff/integrations/)

---

This configuration provides a modern, fast, and comprehensive linting and formatting setup that follows Python community best practices while maintaining high code quality standards.