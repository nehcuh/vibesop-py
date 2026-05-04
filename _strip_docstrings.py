#!/usr/bin/env python3
"""Strip verbose/redundant docstrings from Python files."""

import ast
import re
import sys
from pathlib import Path


def get_indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def is_one_liner_method(lines: list[str], docstring_start: int, docstring_end: int) -> bool:
    """Check if the method containing this docstring is essentially a one-liner."""
    # Find the def line
    def_line = docstring_start - 1
    while def_line >= 0 and not lines[def_line].strip().startswith(("def ", "async def ")):
        def_line -= 1
    if def_line < 0:
        return False

    # Find the end of the method body (next def/class at same or lower indent, or end of file)
    method_indent = len(get_indent(lines[def_line]))
    body_end = docstring_end + 1
    non_empty_lines_after_docstring = 0
    while body_end < len(lines):
        stripped = lines[body_end].strip()
        if not stripped:
            body_end += 1
            continue
        line_indent = len(get_indent(lines[body_end]))
        if line_indent <= method_indent and (
            stripped.startswith(("def ", "async def ", "class ", "@", "if __name__"))
            or (stripped and not stripped.startswith(("#", "pass", "return", "raise")))
        ):
            if line_indent < method_indent:
                break
            if line_indent == method_indent and stripped.startswith(("def ", "async def ", "class ", "@")):
                break
        if stripped and not stripped.startswith("#"):
            non_empty_lines_after_docstring += 1
        body_end += 1

    # Also count non-empty lines between def and docstring
    non_empty_before = 0
    for i in range(def_line + 1, docstring_start):
        if lines[i].strip() and not lines[i].strip().startswith("#"):
            non_empty_before += 1
        if lines[i].strip().startswith("@"):
            non_empty_before = 0  # decorators don't count

    return non_empty_lines_after_docstring <= 1 and non_empty_before == 0


def strip_docstring_sections(docstring: str) -> str:
    """Remove Args/Arguments, Returns, Example/Usage sections from docstring."""
    lines = docstring.split("\n")
    result_lines = []
    skip_section = False
    section_indent = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Check for section headers
        section_match = re.match(r"^(\s*)(Args?|Arguments?|Returns?|Example?s?|Usage|Note\s*\d?):\s*$", line)
        if section_match:
            skip_section = True
            section_indent = len(section_match.group(1))
            continue

        # Check for section with inline content like "Returns: something"
        inline_section = re.match(
            r"^(\s*)(Args?|Arguments?|Returns?):\s+\S", line
        )
        if inline_section:
            skip_section = True
            section_indent = len(inline_section.group(1))
            continue

        if skip_section:
            # Check if we've exited the section (new section header or less-indented non-empty line)
            if stripped:
                current_indent = len(line) - len(line.lstrip())
                if current_indent <= section_indent:
                    # This might be a new section or end of indented block
                    new_section = re.match(
                        r"^(\s*)(Args?|Arguments?|Returns?|Example?s?|Usage|Note\s*\d?):\s*",
                        line,
                    )
                    if new_section:
                        # It's a new section header, re-evaluate
                        section_indent = len(new_section.group(1))
                        if re.match(
                            r"^(\s*)(Args?|Arguments?|Returns?|Example?s?|Usage|Note\s*\d?):\s*$",
                            line,
                        ):
                            continue
                        elif re.match(
                            r"^(\s*)(Args?|Arguments?|Returns?):\s+\S", line
                        ):
                            continue
                        else:
                            skip_section = False
                            result_lines.append(line)
                    else:
                        skip_section = False
                        result_lines.append(line)
                # else: still in the section, skip this line
            continue

        result_lines.append(line)

    # Clean up trailing whitespace and empty lines
    result = "\n".join(result_lines)
    # Remove multiple trailing newlines
    result = result.rstrip("\n")

    # If result is empty or just whitespace, return empty
    if not result.strip():
        return ""

    return result


def process_file(filepath: str) -> tuple[int, int]:
    """Process a single file. Returns (before_lines, after_lines)."""
    path = Path(filepath)
    if not path.exists():
        print(f"  SKIP: {filepath} not found")
        return (0, 0)

    original = path.read_text()
    before_lines = len(original.split("\n"))

    lines = original.split("\n")
    removals = []  # List of (start, end) ranges to remove

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Detect docstring start
        # Must be first statement in a function/class/module
        if '"""' in stripped or "'''" in stripped:
            quote = '"""' if '"""' in stripped else "'''"

            # Check if this is actually a docstring (first statement after def/class)
            # or a string literal in code
            is_docstring = False

            # Count quotes on this line
            quote_count = stripped.count(quote)

            if quote_count == 1:
                # Opening quote - find closing
                docstring_start = i
                j = i + 1
                while j < len(lines) and quote not in lines[j]:
                    j += 1
                docstring_end = j

                # Check if this is a docstring position
                if is_docstring_position(lines, docstring_start):
                    is_docstring = True
                    full_docstring = extract_docstring(lines, docstring_start, docstring_end, quote)
                else:
                    i += 1
                    continue

            elif quote_count >= 2:
                # Single-line docstring
                if stripped.startswith(quote) and stripped.endswith(quote) and len(stripped) > 6:
                    docstring_start = i
                    docstring_end = i

                    if is_docstring_position(lines, docstring_start):
                        is_docstring = True
                        full_docstring = stripped[len(quote): -len(quote)]
                    else:
                        i += 1
                        continue
                else:
                    i += 1
                    continue
            else:
                i += 1
                continue

            if not is_docstring:
                i += 1
                continue

            # Now decide what to do with this docstring
            indent = get_indent(lines[docstring_start])

            # Check if method is a one-liner (remove entire docstring)
            if is_one_liner_method(lines, docstring_start, docstring_end):
                # Remove the entire docstring
                if docstring_start == docstring_end:
                    # Single line docstring
                    removals.append((docstring_start, docstring_end + 1))
                else:
                    # Multi-line docstring
                    removals.append((docstring_start, docstring_end + 1))
                i = docstring_end + 1
                continue

            # Check if docstring has sections to strip
            if has_strippable_sections(full_docstring):
                # Try to strip sections
                new_content = strip_docstring_sections(full_docstring)
                if new_content and new_content.strip():
                    # Replace the docstring with stripped version
                    new_lines = format_docstring(new_content, indent, quote)
                    # Replace lines[docstring_start:docstring_end+1] with new_lines
                    lines[docstring_start: docstring_end + 1] = new_lines
                    i = docstring_start + len(new_lines)
                    continue
                else:
                    # Everything was stripped, remove entirely
                    removals.append((docstring_start, docstring_end + 1))
                    i = docstring_end + 1
                    continue

            # Check if it's a redundant one-liner docstring for simple methods
            # e.g., """Convert to dictionary.""" or """Validate step configuration."""
            if is_redundant_simple_docstring(full_docstring, lines, docstring_start):
                if docstring_start == docstring_end:
                    removals.append((docstring_start, docstring_end + 1))
                else:
                    removals.append((docstring_start, docstring_end + 1))
                i = docstring_end + 1
                continue

            i = docstring_end + 1
        else:
            i += 1

    # Apply removals in reverse order
    for start, end in sorted(removals, reverse=True):
        del lines[start:end]

    # Clean up excessive blank lines (more than 2 consecutive)
    result_lines = []
    blank_count = 0
    for line in lines:
        if not line.strip():
            blank_count += 1
            if blank_count <= 2:
                result_lines.append(line)
        else:
            blank_count = 0
            result_lines.append(line)

    result = "\n".join(result_lines)
    # Ensure file ends with newline
    if not result.endswith("\n"):
        result += "\n"

    after_lines = len(result.split("\n"))

    if result != original:
        path.write_text(result)
        return (before_lines, after_lines)
    else:
        return (before_lines, before_lines)


def is_docstring_position(lines: list[str], docstring_line: int) -> bool:
    """Check if a string is in a docstring position (after def/class/module start)."""
    # Look backwards for def/class, or it's the module-level docstring
    j = docstring_line - 1
    while j >= 0:
        stripped = lines[j].strip()
        if not stripped:
            j -= 1
            continue
        if stripped.startswith(("def ", "async def ", "class ")):
            return True
        if stripped.startswith(("@", "#")):
            j -= 1
            continue
        # If we hit any other code, it's not a docstring position
        return False
    # Reached start of file - module docstring
    return True


def extract_docstring(lines: list[str], start: int, end: int, quote: str) -> str:
    """Extract the content of a docstring."""
    if start == end:
        # Single line
        stripped = lines[start].strip()
        return stripped[len(quote): -len(quote)]

    # Multi-line
    first_line = lines[start].strip()
    content_lines = []

    # First line might have content after the opening quotes
    after_open = first_line[len(quote):].strip()
    if after_open:
        content_lines.append(after_open)

    for i in range(start + 1, end):
        content_lines.append(lines[i])

    # Last line has the closing quotes
    last_line = lines[end]
    close_pos = last_line.rfind(quote)
    if close_pos > 0:
        content_lines.append(last_line[:close_pos].rstrip())

    return "\n".join(content_lines)


def has_strippable_sections(docstring: str) -> bool:
    """Check if a docstring has Args/Returns/Example sections."""
    return bool(
        re.search(
            r"^(Args?|Arguments?|Returns?|Example?s?|Usage):",
            docstring,
            re.MULTILINE,
        )
    )


def is_redundant_simple_docstring(
    docstring: str, lines: list[str], docstring_start: int
) -> bool:
    """Check if a simple one-liner docstring is redundant."""
    content = docstring.strip()
    if not content:
        return True

    # Single-line docstrings that just restate what the method name says
    # Only remove for private/internal methods
    if "\n" not in content:
        # Find the def line
        def_line = docstring_start - 1
        while def_line >= 0 and not lines[def_line].strip().startswith(("def ", "async def ")):
            def_line -= 1
        if def_line < 0:
            return False

        method_name = lines[def_line].strip()
        # Don't remove docstrings from public methods (__init__, etc. are fine)
        # Only remove from obviously trivial methods
        for trivial in ["to_dict", "to_list", "validate", "__repr__", "__str__"]:
            if trivial in method_name and len(content) < 60:
                return True

    return False


def format_docstring(content: str, indent: str, quote: str) -> list[str]:
    """Format a docstring with proper indentation."""
    lines = content.split("\n")
    if len(lines) == 1:
        return [f"{indent}{quote}{lines[0]}{quote}"]

    result = [f"{indent}{quote}{lines[0]}"]
    for line in lines[1:]:
        if line.strip():
            result.append(f"{indent}{line}")
        else:
            result.append("")
    # Fix last line - add closing quote
    result[-1] = f"{indent}{result[-1].lstrip()}{quote}"
    return result


def main():
    files = sys.argv[1:]
    if not files:
        print("Usage: python _strip_docstrings.py <file1.py> [file2.py ...]")
        sys.exit(1)

    total_before = 0
    total_after = 0
    changed = 0

    for f in files:
        before, after = process_file(f)
        if before != after:
            diff = before - after
            print(f"  {f}: {before} -> {after} (-{diff})")
            changed += 1
        else:
            print(f"  {f}: {before} (no change)")
        total_before += before
        total_after += after

    print(f"\nTotal: {total_before} -> {total_after} (-{total_before - total_after} lines, {changed} files changed)")


if __name__ == "__main__":
    main()
