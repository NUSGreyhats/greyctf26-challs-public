#!/usr/local/bin/python

import ast
import re
import sys

ALPHA = r'a-zA-Z'
NUM = r'0-9'
OPS = r'=+\-\/:_\.'
QUOTES = r'\"\''
SPACE = r'\s'
DELIMS = r'\(\)\[\]'

# NOTE: Using *? (lazy quantifier) to prevent catastrophic backtracking
# See: https://www.regular-expressions.info/catastrophic.html
base = f'[{ALPHA}{NUM}{OPS}{QUOTES}{SPACE}{DELIMS}]*?'
group_sq = f'\\[{base}\\]'
group_rd = f'\\({base}\\)'

pattern = re.compile(f'^({base}|{group_sq}|{group_rd})*$')

# Blacklisted word, not allowed in input
BLACKLIST = ['for', 'import', 'exec', 'eval', 'getattr', 'globals', 
             'locals', 'breakpoint', 'compile', 'open', 'os', 'sys']

SAFE_GLOBALS = {
    '__builtins__': {}
}

SAFE_LOCALS = {}


def reject(msg='rejected'):
    print(msg)
    sys.exit(0)


if __name__ == "__main__":
    user_input = sys.argv[1]

    if not pattern.fullmatch(user_input):
        reject("Invalid characters used")

    if len(user_input) > 167:
        reject("Input is too long")

    for b in BLACKLIST:
        if b in user_input.lower():
            reject("Blacklisted word is not allowed: " + b)

    try:
        ast.parse(user_input, mode='eval')
    except Exception as e:
        reject("Parse exception: " + str(e))

    try:
        print("Running user input...")
        result = eval(user_input, SAFE_GLOBALS, SAFE_LOCALS)
        print("Result:", result)
    except Exception as e:
        reject("Eval exception: " + str(e))