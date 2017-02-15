"""Simultaneous unit and coverage testing for python 3 modules."""

# standard library
import argparse
import ast
import importlib
import os.path
import re
import sys
import unittest


class CodeTracer(ast.NodeTransformer):
  """Traces, compiles, and executes an abstract syntax tree."""

  __INJECT_NAME = '__code_tracer__'

  @staticmethod
  def from_source_file(filename):
    """Create a CodeTracer for the given source file."""

    # read the file, parse the AST, and return a tracer
    with open(filename) as f:
      src = f.read()
    tree = ast.parse(src)
    return CodeTracer(tree, filename)

  def __init__(self, tree, filename):
    # a list of all statements in the injected module
    self.nodes = []
    self.original_tree = tree
    self.filename = filename

  def run(self):
    """Trace, compile, and execute the AST, and return global variables."""

    # inject code tracing calls into the AST
    tree = self.visit(self.original_tree)
    ast.fix_missing_locations(tree)

    # execute the new AST, and keep track of global variables it creates
    global_vars = {CodeTracer.__INJECT_NAME: self}
    exec(compile(tree, self.filename, 'exec'), global_vars)

    # return the global variables
    return global_vars

  def get_coverage(self):
    """
    Return code coverage as a list of execution counts and other metadata for
    each statement.

    Each item in the list is a dict containing the following keys:
      - executions: the number of times the statement was executed
      - line: the line number of the statement (1-indexed)
      - column: the column number of the statement (0-indexed)
      - is_string: a boolean indicating whether the statement was a string

    The list is sorted by line number.
    """

    # function to determine whether a given node is a string (e.g. a docstring)
    def is_string(node):
      return isinstance(node, ast.Expr) and isinstance(node.value, ast.Str)

    # iterate over all nodes
    coverage = []
    for node_info in self.nodes:
      node = node_info['node']

      # coverage result for the current node
      coverage.append({
        'executions': node_info['counter'],
        'line': node.lineno,
        'column': node.col_offset,
        'is_string': is_string(node),
      })

    # return sorted coverage results
    return sorted(coverage, key=lambda row: row['line'])

  def execute_node(self, node_id):
    """Increment the execution counter of the given node."""
    self.nodes[node_id]['counter'] += 1

  def generic_visit(self, node):
    """
    Visit an AST node and add tracing if it's a statement.

    This method shouldn't be called directly. It is called by the super class
    when the `run` method of this class is called.
    """

    # let the super class visit this node first
    super().generic_visit(node)

    # only trace statements
    if not isinstance(node, ast.stmt):
      return node

    # a unique identifier and initial data for this node
    node_id = len(self.nodes)
    self.nodes.append({
      'node': node,
      'counter': 0,
    })

    # tracing is done by calling "execute_node" of this class
    func = ast.Attribute(
      value=ast.Name(id=CodeTracer.__INJECT_NAME, ctx=ast.Load()),
      attr='execute_node',
      ctx=ast.Load()
    )

    # the argument to the tracing function is the unique node identifier
    args = [ast.Num(n=node_id)]

    # the tracer will be executed whenever the statement is executed
    tracer = ast.Expr(value=ast.Call(func=func, args=args, keywords=[]))

    # spoof location information for the generated node
    ast.copy_location(tracer, node)

    # inject the tracer into the AST beside the current node
    return [tracer, node]


class TestResult(unittest.TextTestResult):
  """An implementation of python's unittest.TestResult class."""

  ERROR = -2
  FAIL = -1
  SKIP = 0
  PASS = 1

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    # keep a list of passed tests
    self.successes = []
    # record the result of all tests
    self.results = {}

  def __set_result(self, test, skip, error, fail, tb):
    """
    Set the result of the test.

    The result is one of these integers: PASS, SKIP, FAIL, or ERROR.
    """

    # derive a friendly name
    match = re.match('^(\\S+)\\s+\\(\\S+?\\.(\\S+)\\)$', str(test))
    if match is None:
      raise Exception('unrocognized test name: "%s"' % test)
    name = '%s.%s' % (match.group(2), match.group(1))

    # set (or update) the result
    if skip:
      self.results[name] = TestResult.SKIP
    elif error:
      self.results[name] = TestResult.ERROR
    elif fail:
      self.results[name] = TestResult.FAIL
    else:
      # don't overwrite an earlier result (e.g. of a failed subtest)
      if self.results.get(test, None) is None:
        self.results[name] = TestResult.PASS

  def addError(self, test, err):
    super().addError(test, err)
    self.__set_result(test, False, True, False, err[-1])

  def addFailure(self, test, err):
    super().addFailure(test, err)
    self.__set_result(test, False, False, True, err[-1])

  def addSuccess(self, test):
    super().addSuccess(test)
    self.successes.append(test)
    self.__set_result(test, False, False, False, None)

  def addSkip(self, test, reason):
    super().addSkip(test, reason)
    self.__set_result(test, True, False, False, None)

  def addExpectedFailure(self, test, err):
    super().addExpectedFailure(test, err)
    self.__set_result(test, False, False, False, err[-1])

  def addUnexpectedSuccess(self, test):
    super().addUnexpectedSuccess(test)
    self.__set_result(test, False, False, True, None)

  def addSubTest(self, test, subtest, outcome):
    super().addSubTest(test, subtest, outcome)
    # a failed or errored subtest fails or errors the whole test
    fail = outcome is not None
    err = outcome[-1] if fail else None
    self.__set_result(test, False, False, fail, err)


def run_tests(filename):
  """Run all tests in the given file and return unit and coverage resuls."""

  # get the module name from the filename
  match = re.match('^(.*)\\.py$', os.path.basename(filename))
  if match is None:
    raise Exception('not a *.py file: ' + str(filename))
  module_name = match.group(1)

  # import the module and determine the test target
  module = importlib.import_module(module_name)
  target = getattr(module, '__test_target__', None)
  if target is None:
    raise Exception('%s missing attribute __test_target__' % module_name)
  if target[-3:] != '.py':
    raise Exception('test target %s not a *.py file' % target)

  # trace execution while loading the target file
  tracer = CodeTracer.from_source_file(target)
  global_vars = tracer.run()

  # make the target's globals available to the test module
  for key in global_vars:
    if key[:2] != '__':
      setattr(module, key, global_vars[key])

  # load and run unit tests
  tests = unittest.defaultTestLoader.loadTestsFromModule(module)
  runner = unittest.TextTestRunner(
    stream=sys.stdout,
    verbosity=2,
    resultclass=TestResult
  )
  unit_info = runner.run(tests)
  coverage_results = tracer.get_coverage()

  # return unit and coverage results
  return {
    'unit': unit_info.results,
    'coverage': coverage_results,
    'target': target,
  }


def main():
  """Run tests and print results to stdout."""

  # args and usage
  parser = argparse.ArgumentParser()
  parser.add_argument(
    'testfile',
    type=str,
    help='file containing unit tests'
  )
  parser.add_argument(
    '--color',
    default=False,
    action='store_true',
    help='colorize results'
  )
  args = parser.parse_args()

  # run unit and coverage tests
  results = run_tests(args.testfile)

  # colored output
  green, grey, red = 32, 37, 31
  def colorize(txt, color):
    return '\x1b[0;%d;40m%s\x1b[0m' % (color, txt)

  # unit results
  print('=' * 70)
  print('Test results for: %s' % results['target'])
  print('Unit:')
  for name in sorted(results['unit'].keys()):
    result = results['unit'][name]
    txt, color = {
      -2: ('error', red),
      -1: ('fail', red),
      0: ('skip', grey),
      1: ('pass', green),
    }[result]
    if args.color:
      print(' %s: %s' % (name, colorize(txt, color)))
    else:
      print(' %s: %s' % (name, txt))

  # coverage results
  def print_line(line, txt, hits, required):
    txt, cov = '%-80s' % txt, ''
    if required:
      cov = '%dx' % hits
    if args.color:
      if not required:
        color = grey
      elif hits > 0:
        color = green
      else:
        color = red
      txt = colorize(txt, color)
    print(' %4d %s %s' % (line, txt, cov))
  print('Coverage:')
  with open(results['target']) as f:
    src = [(i, line) for (i, line) in enumerate(f.readlines())]
  for row in results['coverage']:
    while len(src) > 0 and src[0][0] < row['line'] - 1:
      line, hits = src[0][0] + 1, 0
      txt, src = '%-80s' % src[0][1][:-1], src[1:]
      print_line(line, txt, hits, False)
    line, hits = row['line'], row['executions']
    txt, src = '%-80s' % src[0][1][:-1], src[1:]
    print_line(line, txt, hits, not row['is_string'])
  while len(src) > 0:
    line, hits = src[0][0] + 1, 0
    txt, src = '%-80s' % src[0][1][:-1], src[1:]
    print_line(line, txt, hits, False)


if __name__ == '__main__':
  main()
