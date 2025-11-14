#!/usr/bin/env python3
"""
LaTeX Project Inliner

This script takes a main LaTeX file and produces a single, self-contained
LaTeX file by recursively resolving all \\input and \\include commands.
Special care is taken to avoid introducing blank lines in ANY math environments
and to avoid commenting out math delimiters.
"""

import re
import os
import sys
from pathlib import Path

class LatexInliner:
    def __init__(self, main_file, output_file=None):
        self.main_file = Path(main_file)
        self.output_file = Path(output_file) if output_file else self.main_file.with_suffix('.inline.tex')
        self.processed_files = set()
        self.current_depth = 0
        self.max_depth = 10  # Prevent infinite recursion
        
        # All math environments where blank lines are not allowed
        self.math_environments = {
            'equation', 'equation*', 'align', 'align*', 'gather', 'gather*',
            'multline', 'multline*', 'flalign', 'flalign*', 'eqnarray', 'eqnarray*',
            'split', 'aligned', 'gathered', 'cases', 'matrix', 'pmatrix',
            'bmatrix', 'Bmatrix', 'vmatrix', 'Vmatrix', 'smallmatrix',
            'subequations', 'math', 'displaymath', 'array'
        }
        
    def read_file(self, file_path):
        """Read a file and return its content."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            # Try with different encoding if UTF-8 fails
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
    
    def is_in_math_mode(self, text, position):
        """
        Check if the given position in text is inside any type of math mode.
        Returns True if in math mode, False otherwise.
        """
        text_before = text[:position]
        
        # Track all math environments and modes
        in_math = False
        in_display_math = False  # For \[ ... \]
        in_double_dollar = False  # For $$ ... $$
        math_env_stack = []
        
        i = 0
        while i < len(text_before):
            char = text_before[i]
            
            if char == '\\':
                # Handle LaTeX commands
                if i + 1 < len(text_before):
                    next_char = text_before[i + 1]
                    
                    if next_char == '[':
                        in_display_math = True
                        in_math = True
                        i += 1
                    elif next_char == ']' and in_display_math:
                        in_display_math = False
                        in_math = False
                        i += 1
                    elif next_char == '(':
                        in_math = True
                        i += 1
                    elif next_char == ')' and in_math and not in_display_math and not in_double_dollar:
                        in_math = False
                        i += 1
                    elif text_before[i:i+6] == '\\begin':
                        # Find the environment name
                        brace_match = re.match(r'\\begin\{([^}]+)\}', text_before[i:])
                        if brace_match:
                            env_name = brace_match.group(1)
                            if env_name in self.math_environments:
                                in_math = True
                                math_env_stack.append(env_name)
                            i += len(brace_match.group(0)) - 1
                    elif text_before[i:i+4] == '\\end':
                        # Find the environment name
                        brace_match = re.match(r'\\end\{([^}]+)\}', text_before[i:])
                        if brace_match:
                            env_name = brace_match.group(1)
                            if math_env_stack and env_name in self.math_environments:
                                math_env_stack.pop()
                                if not math_env_stack and not in_display_math and not in_double_dollar:
                                    in_math = False
                            i += len(brace_match.group(0)) - 1
            
            elif char == '$':
                # Handle dollar sign math
                if i + 1 < len(text_before) and text_before[i + 1] == '$':
                    # Double dollar display math
                    if in_double_dollar:
                        in_double_dollar = False
                        in_math = False
                    else:
                        in_double_dollar = True
                        in_math = True
                    i += 1  # Skip second dollar
                else:
                    # Single dollar inline math
                    if i > 0 and text_before[i-1] == '\\':
                        # Escaped dollar sign, do nothing
                        pass
                    else:
                        in_math = not in_math
            
            i += 1
        
        return in_math or in_display_math or in_double_dollar or bool(math_env_stack)
    
    def safe_add_math_comments(self, content, file_path):
        """
        Safely add inclusion comments in math mode without commenting out delimiters.
        Returns the content with safe comments added.
        """
        filename = file_path.name
        
        # Check if content starts or ends with math delimiters
        content_stripped = content.strip()
        
        # List of math delimiters we must not comment out
        math_delimiters = ['$$', '\\[', '\\]', '$', '\\(', '\\)']
        
        starts_with_delimiter = any(content_stripped.startswith(d) for d in math_delimiters)
        ends_with_delimiter = any(content_stripped.endswith(d) for d in math_delimiters)
        
        # For very short math content, be extra careful
        if len(content_stripped) < 10:
            # Don't risk it - just return the content with minimal comments
            begin_comment = f"% Inline: {filename}"
            end_comment = f"% End: {filename}"
            return f"{begin_comment}\n{content}\n{end_comment}\n"
        
        if starts_with_delimiter or ends_with_delimiter:
            # Content has delimiters at boundaries - place comments carefully
            lines = content.split('\n')
            if len(lines) >= 2:
                # Place begin comment after first line, end comment before last line
                begin_comment = f"% Begin: {filename}"
                end_comment = f"% End: {filename}\n"
                
                result = []
                result.append(lines[0])  # Keep first line (might be delimiter)
                result.append(begin_comment)
                for line in lines[1:-1]:
                    result.append(line)
                result.append(end_comment)
                result.append(lines[-1])  # Keep last line (might be delimiter)
                return '\n'.join(result)
            else:
                # Single line with delimiters - just add comments on separate lines
                begin_comment = f"% Begin: {filename}"
                end_comment = f"% End: {filename}"
                return f"{begin_comment}\n{content}\n{end_comment}\n"
        else:
            # Safe to add comments normally
            begin_comment = f"% Begin: {filename}"
            end_comment = f"% End: {filename}"
            return f"{begin_comment}\n{content}\n{end_comment}\n"
    
    def add_inclusion_comments(self, content, file_path, in_math_mode=False):
        """
        Add inclusion comments, being extremely careful about math mode.
        NEVER add blank lines in math mode and NEVER comment out math delimiters.
        """
        filename = file_path.name
        
        if in_math_mode:
            # In math mode, use safe comment placement
            return self.safe_add_math_comments(content, file_path)
        else:
            # Regular text mode, use comments with blank lines for readability
            begin_comment = f"% --- Begin included file: {filename} ---\n"
            end_comment = f"% --- End included file: {filename} ---\n"
            
            return begin_comment + content + end_comment
    
    def resolve_input_commands(self, content, current_dir):
        """Resolve \\input and \\include commands in the content."""
        if self.current_depth > self.max_depth:
            return content
            
        self.current_depth += 1
        
        # Pattern to match \input and \include commands
        pattern = r'\\(input|include)\s*(\[.*?\])?\s*\{([^}]+)\}'
        
        def replace_command(match):
            command_type = match.group(1)  # input or include
            options = match.group(2) or ""  # optional arguments
            file_arg = match.group(3).strip()
            
            # Get the position of this match in the original content
            match_start = match.start()
            
            # Check if we're in math mode
            in_math_mode = self.is_in_math_mode(content, match_start)
            
            # Handle file extension
            if not file_arg.endswith('.tex'):
                file_arg += '.tex'
            
            # Resolve file path
            file_path = current_dir / file_arg
            
            if not file_path.exists():
                # Try with different extensions or in parent directories
                possible_paths = [
                    file_path,
                    file_path.with_suffix('.tex'),
                    self.main_file.parent / file_arg,
                    self.main_file.parent / file_path.name
                ]
                
                for path in possible_paths:
                    if path.exists():
                        file_path = path
                        break
                else:
                    print(f"Warning: Could not find file {file_arg}")
                    return match.group(0)  # Return original command if file not found
            
            # Check for circular includes
            if file_path in self.processed_files:
                print(f"Warning: Circular include detected for {file_path}")
                if in_math_mode:
                    return f"% Circular include prevented: {match.group(0)}"
                else:
                    return f"\n% Circular include prevented: {match.group(0)}\n"
            
            self.processed_files.add(file_path)
            print(f"Inlining: {file_path} (math mode: {in_math_mode})")
            
            try:
                file_content = self.read_file(file_path)
                
                # Remove any surrounding whitespace that might cause issues in math mode
                if in_math_mode:
                    file_content = file_content.strip()
                
                # Recursively resolve inputs in the included file
                resolved_content = self.resolve_input_commands(file_content, file_path.parent)
                
                # Add appropriate comments based on whether we're in math mode
                final_content = self.add_inclusion_comments(resolved_content, file_path, in_math_mode)
                
                return final_content
                
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                error_msg = f"% Error including {file_path}: {e}"
                if in_math_mode:
                    return f"{error_msg}\n{match.group(0)}"
                else:
                    return f"\n{error_msg}\n{match.group(0)}\n"
        
        # Replace all input and include commands
        content = re.sub(pattern, replace_command, content)
        
        self.current_depth -= 1
        return content
    
    def remove_blank_lines_in_math(self, content):
        """
        Remove blank lines that appear within math environments.
        This handles all math modes: $...$, \(...\), \[...\], $$...$$, and math environments.
        """
        lines = content.split('\n')
        result = []
        
        in_math = False
        in_display_math = False  # \[ ... \]
        in_double_dollar = False  # $$ ... $$
        math_env_stack = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            line_stripped = line.strip()
            
            # Check for display math \[
            if '\\[' in line:
                # Only start display math if we're not already in it and it's not closed on same line
                bracket_pos = line.find('\\[')
                close_bracket_pos = line.find('\\]')
                if not in_display_math and (close_bracket_pos == -1 or close_bracket_pos < bracket_pos):
                    in_display_math = True
                    in_math = True
            
            # Check for display math \]
            if '\\]' in line and in_display_math:
                bracket_pos = line.find('\\]')
                open_bracket_pos = line.find('\\[')
                if open_bracket_pos == -1 or bracket_pos > open_bracket_pos:
                    in_display_math = False
                    if not in_double_dollar and not math_env_stack:
                        in_math = False
            
            # Check for double dollar math $$
            dollar_count = line.count('$$') - line.count('\\$\\$')
            if dollar_count > 0:
                if not in_double_dollar:
                    in_double_dollar = True
                    in_math = True
                else:
                    in_double_dollar = False
                    if not in_display_math and not math_env_stack:
                        in_math = False
            
            # Check for inline math boundaries
            single_dollar_count = line.count('$') - 2 * line.count('$$') - line.count('\\$')
            if single_dollar_count % 2 == 1:
                in_math = not in_math
            
            # Check for \( and \) 
            if '\\(' in line and '\\\\)' not in line:
                in_math = True
            if '\\\\)' in line and in_math and not in_display_math and not in_double_dollar:
                in_math = False
            
            # Check for \begin{math environment}
            begin_matches = list(re.finditer(r'\\begin\{([^}]+)\}', line))
            for match in begin_matches:
                env_name = match.group(1)
                if env_name in self.math_environments:
                    math_env_stack.append(env_name)
                    in_math = True
            
            # Check for \end{math environment}
            end_matches = list(re.finditer(r'\\end\{([^}]+)\}', line))
            for match in end_matches:
                env_name = match.group(1)
                if math_env_stack and env_name in self.math_environments:
                    math_env_stack.pop()
                    if not math_env_stack and not in_display_math and not in_double_dollar:
                        in_math = False
            
            # Determine if we're in any math mode
            any_math_mode = in_math or in_display_math or in_double_dollar or bool(math_env_stack)
            
            # If we're in math mode and this line is blank, skip it
            if any_math_mode and line_stripped == '':
                # Skip blank line in math mode
                i += 1
                continue
            
            result.append(line)
            i += 1
        
        return '\n'.join(result)
    
    def inline_latex(self):
        """Main function to inline the LaTeX project."""
        if not self.main_file.exists():
            print(f"Error: Main file {self.main_file} not found.")
            return False
        
        print(f"Inlining LaTeX project: {self.main_file}")
        print(f"Output file: {self.output_file}")
        
        try:
            # Read main file
            main_content = self.read_file(self.main_file)
            self.processed_files.add(self.main_file)
            
            # Resolve all input commands
            inlined_content = self.resolve_input_commands(main_content, self.main_file.parent)
            
            # Remove any blank lines that might have been introduced in math mode
            inlined_content = self.remove_blank_lines_in_math(inlined_content)
            
            # Write output file
            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write(inlined_content)
            
            print(f"Successfully created inlined LaTeX file: {self.output_file}")
            print(f"Processed {len(self.processed_files)} files")
            return True
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    """Command line interface."""
    if len(sys.argv) < 2:
        print("Usage: python latex_inliner.py <main.tex> [output.tex]")
        print("")
        print("Examples:")
        print("  python latex_inliner.py main.tex")
        print("  python latex_inliner.py main.tex single_file.tex")
        sys.exit(1)
    
    main_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    inliner = LatexInliner(main_file, output_file)
    success = inliner.inline_latex()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
