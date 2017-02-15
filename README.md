# py3tester
Simultaneous unit and coverage testing for python 3 modules.

Unit testing is provided by the python's built-in [unittest](https://docs.python.org/3/library/unittest.html) package. Line-based coverage is measured by first injecting tracing calls into the AST of the target module and then recording which statements were executed by unit tests.

# api
Testing can be done programmatically by calling `run_tests`. For example:

````python
from py3tester import run_tests
results = run_tests('somefile.py')
````

In the above example, somefile.py contains:
  - unit tests for some module
  - a global variable named `__test_target__` that contains the filename of the test target

The return value of `run_tests` is a `dict` containing three things:
  - 'target': the name of the tested file (the value of `__test_target__`)
  - 'unit': unit test results, as a `dict` of test name to test result (pass, skip, fail, or error)
  - 'coverage': coverage results, as a `list` of `dicts` containing:
    - 'executions': the number of times the statement was executed
    - 'line': the line number of the statement (1-indexed)
    - 'column': the column number of the statement (0-indexed)
    - 'is_string': a boolean indicating whether the statement was a string

# example
Testing can also be done from the command line. For example, suppose that there is a module [thing.py](samples/thing.py) and that unit tests for that module are in [test_thing.py](samples/test_thing.py). Tests can be run with `python3 py3tester.py test_thing.py` (with optional an flag '--color' for colored output).

The output is:
````text
Test results for: thing.py

Unit:
 AdvancedTests.test_div0: error
 AdvancedTests.test_div1: fail
 AdvancedTests.test_get_tau: skip
 BasicTests.test_add: pass
 BasicTests.test_div: pass
 BasicTests.test_get_pi: pass
 BasicTests.test_saxpy: pass

Coverage:
  1 """Simple math helpers."""
  2
  3 # standard library
  4 import math                                      1x
  5
  6
  7 class Thing:                                     1x
  8   """Provides math helpers."""
  9
 10   @staticmethod                                  1x
 11   def add(a, b):
 12     """Add two numbers."""
 13     return a + b                                 4x
 14
 15   @staticmethod                                  1x
 16   def div(a, b):
 17     """Divide two numbers."""
 18     return a / b                                 3x
 19
 20   @staticmethod                                  1x
 21   def saxpy(a, x, y):
 22     """Compute ((a * x) + y)."""
 23     return Thing.add(a * x, y)                   1x
 24
 25   @staticmethod                                  1x
 26   def get_pi(guess=3):
 27     """Make a guess at π."""
 28     return Thing.add(guess, math.sin(guess))     2x
 29
 30   @staticmethod                                  1x
 31   def get_tau(guess=6):
 32     """Make a guess at τ."""
 33     return 2 * Thing.get_pi(Thing.div(guess, 2)) 0x
````
