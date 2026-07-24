```markdown
# certman Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill covers the core development patterns and conventions used in the `certman` Python codebase. You will learn how to structure files, write imports and exports, follow commit message conventions, and understand the project's approach to testing. This guide is designed to help new contributors quickly align with the project's standards.

## Coding Conventions

### File Naming
- Use **snake_case** for all file names.
  - Example: `certificate_manager.py`, `utils.py`

### Import Style
- Use **relative imports** within the package.
  - Example:
    ```python
    from .utils import validate_certificate
    ```

### Export Style
- Use **named exports** (explicitly define what is exported).
  - Example:
    ```python
    __all__ = ['CertificateManager', 'validate_certificate']
    ```

### Commit Messages
- Follow the **Conventional Commits** standard.
- Use the `fix` prefix for bug fixes.
- Keep commit messages concise (average 51 characters).
  - Example:
    ```
    fix: handle expired certificate edge case
    ```

## Workflows

### Making a Code Change
**Trigger:** When you need to update or fix code.
**Command:** `/code-change`

1. Create a new branch for your change.
2. Make your code changes following the coding conventions.
3. Write a commit message using the conventional `fix` prefix if it's a bug fix.
4. Push your branch and open a pull request.

### Adding a New Module
**Trigger:** When introducing new functionality.
**Command:** `/add-module`

1. Create a new Python file using snake_case naming.
2. Use relative imports to access shared utilities.
3. Define `__all__` for explicit exports.
4. Add any necessary tests (see Testing Patterns).
5. Commit with a descriptive message.

## Testing Patterns

- Test files use the `*.test.ts` pattern, suggesting some TypeScript-based tests, though the main codebase is Python.
- The specific testing framework is unknown.
- Place test files alongside or within a `tests/` directory.
- Example test file name: `certificate_manager.test.ts`

## Commands
| Command        | Purpose                                   |
|----------------|-------------------------------------------|
| /code-change   | Steps for making a code change            |
| /add-module    | Steps for adding a new module             |
```
