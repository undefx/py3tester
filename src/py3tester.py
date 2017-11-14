"""Simultaneous unit and coverage testing for python 3 modules."""

# standard library
import argparse
import ast
import importlib
import inspect
import json
import math
import os
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
      if self.results.get(name, None) is None:
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
    tb = outcome[-1] if fail else None
    self.__set_result(test, False, False, fail, tb)


class Styler:
  """Helper class for producing stylized terminal output."""

  green, gray, red = 32, 37, 31

  def __init__(self, json_only=False, use_colors=False, show_source=False):
    self.__json_only = json_only
    self.__use_colors = use_colors
    self.__show_source = show_source

  def colorize(self, txt, color):
    """Color the given string."""
    if self.__use_colors:
      return '\x1b[0;%d;40m%s\x1b[0m' % (color, txt)
    else:
      return txt

  def emit(self, txt, is_source=False):
    """Print the given string, conditional on export settings."""
    if not self.__json_only and (not is_source or self.__show_source):
      print(txt)


def run_tests(filename, output=sys.stdout):
  """Run all tests in the given file and return unit and coverage resuls."""

  # get the module name from the filename
  path, ext = filename[:-3], filename[-3:]
  if ext != '.py':
    raise Exception('not a *.py file: ' + str(filename))
  module_name = path.replace(os.path.sep, '.')

  # needed when the file is in a subdirectory
  sys.path.append(os.getcwd())

  # import the module and determine the test target
  module = importlib.import_module(module_name)
  target_module = getattr(module, '__test_target__', None)
  if target_module is None:
    raise Exception('%s missing attribute __test_target__' % module_name)
  target_file = target_module.replace('.', os.path.sep) + '.py'

  # trace execution while loading the target file
  tracer = CodeTracer.from_source_file(target_file)
  global_vars = tracer.run()

  # make the target's globals available to the test module
  for key in global_vars:
    if key[:2] != '__':
      setattr(module, key, global_vars[key])

  # load and run unit tests
  tests = unittest.defaultTestLoader.loadTestsFromModule(module)
  runner = unittest.TextTestRunner(
    stream=output,
    verbosity=2,
    resultclass=TestResult
  )
  unit_info = runner.run(tests)
  coverage_results = tracer.get_coverage()

  # return unit and coverage results
  return {
    'unit': unit_info.results,
    'coverage': coverage_results,
    'target_module': target_module,
    'target_file': target_file,
  }


def find_tests(location, regex, recursive):
  """Find files containing unit tests."""
  if os.path.isdir(location):
    pattern = re.compile(regex)
    file_set = set()
    for dir_, dirs, files in os.walk(location):
      for f in files:
        file_set.add(os.path.join(dir_, f))
      if not recursive:
        break
    all_files = sorted(file_set)
    ismatch = lambda f: pattern.match(os.path.basename(f)) is not None
    tests_files = list(filter(ismatch, filter(os.path.isfile, all_files)))
  else:
    tests_files = [location]
  return tests_files


def analyze_results(results, styler=None):
  """
  Extract a useful set of information from the results of a single unit test.
  """

  if styler is None:
    styler = Styler(json_only=True)

  # unit results
  export = {
    'target_file': results['target_file'],
    'target_module': results['target_module'],
    'unit': {
      'tests': {},
      'summary': {},
    },
    'coverage': {
      'lines': [],
      'hit_counts': {},
      'summary': {},
    },
  }
  styler.emit('=' * 70)
  styler.emit('Test results for:')
  styler.emit(' %s (%s)' % (results['target_module'], results['target_file']))
  styler.emit('Unit:')

  test_bins = {-2: 0, -1: 0, 0: 0, 1: 0}
  for name in sorted(results['unit'].keys()):
    result = results['unit'][name]
    test_bins[result] += 1
    txt, color = {
      -2: ('error', Styler.red),
      -1: ('fail', Styler.red),
      0: ('skip', Styler.gray),
      1: ('pass', Styler.green),
    }[result]
    export['unit']['tests'][name] = txt
    styler.emit(' %s: %s' % (name, styler.colorize(txt, color)))

  export['unit']['summary'] = {
    'total': len(results['unit']),
    'error': test_bins[-2],
    'fail': test_bins[-1],
    'skip': test_bins[0],
    'pass': test_bins[1],
  }

  def fmt(num, goodness):
    if goodness > 0 and num > 0:
      color = Styler.green
    elif goodness < 0 and num > 0:
      color = Styler.red
    else:
      color = Styler.gray
    return styler.colorize(str(num), color)

  styler.emit(' error: %s' % fmt(test_bins[-2], -1))
  styler.emit('  fail: %s' % fmt(test_bins[-1], -1))
  styler.emit('  skip: %s' % fmt(test_bins[0], 0))
  styler.emit('  pass: %s' % fmt(test_bins[1], 1))

  # coverage results
  styler.emit('Coverage:')

  def print_line(line, txt, hits, required):
    export['coverage']['lines'].append({
      'line': line,
      'hits': hits,
      'required': required,
    })

    if required:
      cov = '%dx' % hits
    else:
      cov = ''

    if not required:
      color = Styler.gray
    elif hits > 0:
      color = Styler.green
    else:
      color = Styler.red
    txt = styler.colorize('%-80s' % txt, color)

    styler.emit(' %4d %s %s' % (line, txt, cov), is_source=True)

  with open(results['target_file']) as f:
    src = [(i, line) for (i, line) in enumerate(f.readlines())]

  hit_bins = {0: 0}
  for row in results['coverage']:
    while len(src) > 0 and src[0][0] < row['line'] - 1:
      line, hits = src[0][0] + 1, 0
      txt, src = src[0][1][:-1], src[1:]
      print_line(line, txt, hits, False)
    line, hits = row['line'], row['executions']
    txt, src = src[0][1][:-1], src[1:]
    required = not row['is_string']
    print_line(line, txt, hits, required)
    if required:
      if hits not in hit_bins:
        hit_bins[hits] = 1
      else:
        hit_bins[hits] += 1
  while len(src) > 0:
    line, hits = src[0][0] + 1, 0
    txt, src = src[0][1][:-1], src[1:]
    print_line(line, txt, hits, False)

  for hits in sorted(hit_bins.keys()):
    num = hit_bins[hits]
    if hits == 0 and num > 0:
      color = Styler.red
    elif hits > 0 and num > 0:
      color = Styler.green
    else:
      color = Styler.gray
    num_str = styler.colorize(str(num), color)

    export['coverage']['hit_counts'][hits] = num
    styler.emit(' %dx: %s' % (hits, num_str))
  total_lines = sum(hit_bins.values())
  lines_hit = total_lines - hit_bins[0]

  export['coverage']['summary'] = {
    'total_lines': total_lines,
    'hit_lines': lines_hit,
    'missed_lines': (total_lines - lines_hit),
    'percent': lines_hit / max(total_lines, 1),
  }
  styler.emit(' overall: %d%%' % math.floor(100 * lines_hit / total_lines))

  # return results
  return export


def main():
  """Run tests and print results to stdout."""

  # args and usage
  parser = argparse.ArgumentParser()
  parser.add_argument(
    'location',
    type=str,
    help='file or directory containing unit tests'
  )
  parser.add_argument(
    '--pattern',
    '-p',
    default='^.*(test_.*|.*_test)\\.py$',
    type=str,
    help='regex for finding test files'
  )
  parser.add_argument(
    '--recursive',
    '-r',
    default=False,
    action='store_true',
    help='search for tests recursively'
  )
  parser.add_argument(
    '--color',
    '-c',
    default=False,
    action='store_true',
    help='colorize results'
  )
  parser.add_argument(
    '--full',
    '--f',
    default=False,
    action='store_true',
    help='show coverage for each line'
  )
  parser.add_argument(
    '--json',
    '--j',
    default=False,
    action='store_true',
    help='print results in JSON format'
  )
  args = parser.parse_args()

  # run unit and coverage tests
  styler = Styler(
    json_only=args.json,
    use_colors=args.color,
    show_source=args.full
  )
  test_files = find_tests(args.location, args.pattern, args.recursive)
  if args.json:
    # suppress other output
    all_results = []
    with open(os.devnull, 'w') as output:
      for filename in test_files:
        test_results = run_tests(filename, output)
        all_results.append(analyze_results(test_results, styler))
    print(json.dumps(all_results))
  else:
    # use default output
    all_pass = True
    for filename in test_files:
      test_results = run_tests(filename)
      analyze_results(test_results, styler)
      if len(test_results['unit']) > 0:
        all_pass = all_pass and min(test_results['unit'].values()) == 1
    if args.color:
      if all_pass:
        icon = '✔ '
      else:
        icon = '✘ '
    else:
      icon = ''
    if all_pass:
      txt = styler.colorize('%sAll tests passed!' % icon, Styler.green)
    else:
      txt = styler.colorize('%sSome tests did not pass.' % icon, Styler.red)
    styler.emit(txt)


if __name__ == '__main__':
  main()
