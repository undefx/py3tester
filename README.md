# py3tester

Simultaneous unit, coverage, and timing testing for python 3 modules.

Unit testing is provided by the python's built-in
[unittest](https://docs.python.org/3/library/unittest.html) package. Line-based
coverage and timing are measured by first injecting tracing calls into the AST
of the target module and then recording which statements were executed, and for
how long, by unit tests.

# api

Testing can be done programmatically by calling `run_tests`. For example:

```python
from py3tester import run_tests
results = run_tests('somefile.py')
```

In the above example, `somefile.py` contains:

- unit tests for some module
- a global variable named `__test_target__` that contains the module name of
  the test target

The return value of `run_tests` is a `dict` containing three things:

- `target_file`: the relative path to the tested file
- `target_module`: the name of the tested module (the value of
  `__test_target__`)
- `unit`: unit test results, with keys:
  - `tests`: a `dict` mapping test name to test result (pass, skip, fail, or
    error)
  - `summary`: maps test result to number of tests with that result
- `coverage`: coverage and timing results, with keys:
  - `lines`: a list of dicts with keys:
    - `line`: line number (1-indexed)
    - `hits`: execution count
    - `time`: execution time (cumulative)
    - `required`: whether the line is executable
  - `hit_counts`: maps a number of executions to the number of lines which were
    executed that many times
  - `summary`: summarizes coverage results with keys:
    - `total_lines`: total number of executable lines
    - `hit_lines`: number of lines which were executed
    - `missed_lines`: number of executable lines which were not executed
    - `percent`: the percent of executable lines which were executed


# example

Testing can also be done from the command line. For example, suppose that there
is a module [thing.py](samples/thing.py) and that unit tests for that module
are in [test_thing.py](samples/test_thing.py). Tests can be run with `python3
src/py3tester.py samples/test_thing.py` (with an optional flag '--color' for
colored output).

The output, edited for brevity, looks as follows:

```
Test results for:
 samples.thing (samples/thing.py)
Unit:
 test_thing.AdvancedTests.test_div0: error
 test_thing.AdvancedTests.test_div1: fail
 test_thing.AdvancedTests.test_get_tau: skip
 test_thing.BasicTests.test_add: pass
 test_thing.BasicTests.test_div: pass
 test_thing.BasicTests.test_get_e: pass
 test_thing.BasicTests.test_get_pi: pass
 test_thing.BasicTests.test_get_pi_minus_phi: pass
 test_thing.BasicTests.test_saxpy: pass
 error: 1
  fail: 1
  skip: 1
  pass: 6
Coverage:
    1 """Simple math helpers."""
    2
    3 # standard library
    4 import math                                        1x
    5
    6
    7 class Thing:                                       1x
    8   """Provides math helpers."""
    9
   10   @staticmethod                                    1x
   11   def add(a, b):
   12     """Add two numbers."""
   13     return a + b                                   26005x          34 ms
   14
   15   @staticmethod                                    1x
   16   def div(a, b):
   17     """Divide two numbers."""
   18     return a / b                                   6x
   19
   20   @staticmethod                                    1x
   21   def saxpy(a, x, y):
   22     """Compute ((a * x) + y)."""
   23     return Thing.add(a * x, y)                     1x
   24
   25   @staticmethod                                    1x
   26   def get_pi(guess=3):
   27     """Make a guess at π."""
   28     return Thing.add(guess, math.sin(guess))       3x
   29
   30   @staticmethod                                    1x
   31   def get_tau(guess=6):
   32     """Make a guess at τ."""
   33     return 2 * Thing.get_pi(Thing.div(guess, 2))   0x
   34
   35   @staticmethod                                    1x
   36   def get_phi(n=10):
   37     """Make a guess at φ, the golden ratio."""
   38     a, b = 0, 1                                    2x
   39     for i in range(n):                             2x      83 ms   166 ms
   40       a, b = b, Thing.add(a, b)                    26000x          138 ms
   41     return Thing.div(b, a)                         2x
   42
   43   @staticmethod                                    1x
   44   def get_pi_minus_phi():
   45     """Return approximately `π - φ`."""
   46     pi = Thing.get_pi(guess=Thing.div(22, 7))      1x
   47     phi = Thing.get_phi(n=25000)                   1x      160 ms  160 ms
   48     return pi - phi                                1x
 0x: 1
 1x: 13
 2x: 3
 3x: 1
 6x: 1
 26000x: 1
 26005x: 1
 overall: 95%
✘ Some tests did not pass. 95% (20/21) coverage.
```

To run this example and see the full output, including unit test results, run:

```shell
git clone https://github.com/undefx/py3tester
cd py3tester
python3 -m src.py3tester --color --full samples
```

# caveats

- **Compound statements.** Coverage and timing depend on the assumption that
  each line has exactly zero or one statements. Multiple statements on a single
  line are not supported by this tester. Compound statements in general are
  explicitly discouraged in the [PEP8 Style Guide for Python
  Code](https://www.python.org/dev/peps/pep-0008/).
