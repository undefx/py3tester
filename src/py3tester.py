"""Simultaneous unit, coverage, and timing testing for python 3 modules."""

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
import time
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
        'time': node_info['time'],
        'line': node.lineno,
        'column': node.col_offset,
        'is_string': is_string(node),
      })

    # return sorted coverage results
    return sorted(coverage, key=lambda row: row['line'])

  def execute_node1(self, node_id):
    """Increment the execution counter, and start timing the given node."""
    self.nodes[node_id]['counter'] += 1
    self.nodes[node_id]['time'] -= time.time()

  def execute_node2(self, node_id):
    """Stop timing the given node."""
    self.nodes[node_id]['time'] += time.time()

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
      'time': 0,
    })

    # tracing is done by calling "execute_node" of this class
    func1 = ast.Attribute(
      value=ast.Name(id=CodeTracer.__INJECT_NAME, ctx=ast.Load()),
      attr='execute_node1',
      ctx=ast.Load()
    )
    func2 = ast.Attribute(
      value=ast.Name(id=CodeTracer.__INJECT_NAME, ctx=ast.Load()),
      attr='execute_node2',
      ctx=ast.Load()
    )

    # the argument to the tracing function is the unique node identifier
    args = [ast.Num(n=node_id)]

    # the tracer will be executed whenever the statement is executed
    tracer1 = ast.Expr(value=ast.Call(func=func1, args=args, keywords=[]))
    tracer2 = ast.Expr(value=ast.Call(func=func2, args=args, keywords=[]))

    # spoof location information for the generated node
    ast.copy_location(tracer1, node)
    ast.copy_location(tracer2, node)

    # inject tracers in a try-finally construct around this node
    wrapper = ast.Try(body=[node], handlers=[], orelse=[], finalbody=[tracer2])
    return [tracer1, wrapper]


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
    message = (
      'Warning: '
      '%s missing attribute __test_target__. '
      'Coverage will not be tracked.'
    )
    print(message % module_name, file=output)
    target_file = None
  else:
    target_file = target_module.replace('.', os.path.sep) + '.py'

  if target_file:
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

  if target_file:
    coverage_results = tracer.get_coverage()
  else:
    coverage_results = None

  # return unit and coverage results
  return {
    'unit': unit_info.results,
    'coverage': coverage_results,
    'target_module': target_module,
    'target_file': target_file,
  }


def find_tests(location, regex, terminal):
  """Find files containing unit tests."""
  if not os.path.exists(location):
    return []
  elif os.path.isdir(location):
    pattern = re.compile(regex)
    file_set = set()
    for dir_, dirs, files in os.walk(location):
      for f in files:
        if pattern.match(f):
          file_set.add(os.path.join(dir_, f))
      if terminal:
        break
    return sorted(file_set)
  else:
    return [location]
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

  if not results['target_file']:
    # coverage was not computed, return test outcomes only
    return export

  # coverage results
  styler.emit('Coverage:')

  def print_line(line, txt, hits, time, required):
    export['coverage']['lines'].append({
      'line': line,
      'hits': hits,
      'time': time,
      'required': required,
    })

    def format_duration(d):
      if d < 1e-3:
        # less than a millisecond, hide to reduce noise
        return ''
      elif d < 10:
        # millisecond precision for times up to 10 seconds
        return '%.0f ms' % (d * 1e3)
      else:
        return '%.0f sec' % d

    if required:
      args = (
        '%dx' % hits,
        format_duration(time / max(hits, 1)),
        format_duration(time),
      )
      cov = '%-10s %-10s %-10s' % args
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

    if required and time < 0:
      raise Exception('time travel detected')

  with open(results['target_file']) as f:
    src = [(i, line) for (i, line) in enumerate(f.readlines())]

  hit_bins = {0: 0}
  for row in results['coverage']:
    while len(src) > 0 and src[0][0] < row['line'] - 1:
      line, hits, time = src[0][0] + 1, 0, 0
      txt, src = src[0][1][:-1], src[1:]
      print_line(line, txt, hits, time, False)
    line, hits, time = row['line'], row['executions'], row['time']
    txt, src = src[0][1][:-1], src[1:]
    required = not row['is_string']
    print_line(line, txt, hits, time, required)
    if required:
      if hits not in hit_bins:
        hit_bins[hits] = 1
      else:
        hit_bins[hits] += 1
  while len(src) > 0:
    line, hits, time = src[0][0] + 1, 0, 0
    txt, src = src[0][1][:-1], src[1:]
    print_line(line, txt, hits, time, False)

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


def run_test_sets(location, pattern, terminal, show_json, color, full):
  """
  Run all test sets and print results to standard output.

  location (str):
    the path in which to search for unit tests
  pattern (str):
    regular expression for matching unit test filenames
  terminal (bool):
    whether the search should end with the given location (non-recursive)
  show_json (bool):
    whether to show JSON or human-readable output
  color (bool):
    whether human-readable output should be colorized
  full (bool):
    whether human-readable test target source code should be shown
  """

  # run unit and coverage tests
  styler = Styler(
    json_only=show_json,
    use_colors=color,
    show_source=full
  )
  test_files = find_tests(location, pattern, terminal)

  if not test_files:
    raise Exception('no tests found')

  all_pass = True

  if show_json:
    # suppress other output
    all_results = []
    with open(os.devnull, 'w') as output:
      for filename in test_files:
        test_outcomes = run_tests(filename, output)
        test_results = analyze_results(test_outcomes, styler)
        all_results.append(test_results)
        if len(test_results['unit']) > 0:
          unit_stats = test_results['unit']['summary']
          all_pass = all_pass and unit_stats['pass'] == unit_stats['total']
    print(json.dumps(all_results))
  else:
    # use default output
    num_tests = 0
    total_lines = hit_lines = 0
    for filename in test_files:
      test_results = analyze_results(run_tests(filename), styler)
      if len(test_results['unit']) > 0:
        unit_stats = test_results['unit']['summary']
        coverage_stats = test_results['coverage']['summary']
        all_pass = all_pass and unit_stats['pass'] == unit_stats['total']
        num_tests += unit_stats['total']
        if coverage_stats:
          total_lines += coverage_stats['total_lines']
          hit_lines += coverage_stats['hit_lines']
    if total_lines == 0:
      coverage = 0
    else:
      coverage = hit_lines / total_lines
    percent = math.floor(coverage * 100)
    if total_lines:
      args = (percent, hit_lines, total_lines)
      coverage_str = ' %d%% (%d/%d) coverage.' % args
    else:
      coverage_str = ' [coverage unavailable]'
    if color:
      if all_pass:
        icon = '✔ '
      else:
        icon = '✘ '
    else:
      icon = ''
    if all_pass:
      result = '%sAll %d tests passed!%s' % (icon, num_tests, coverage_str)
      txt = styler.colorize(result, Styler.green)
    else:
      result = '%sSome tests did not pass.%s' % (icon, coverage_str)
      txt = styler.colorize(result, Styler.red)
    styler.emit(txt)

  return all_pass


def get_argument_parser():
  """Set up command line arguments and usage."""

  parser = argparse.ArgumentParser()
  parser.add_argument(
    'location',
    type=str,
    help='file or directory containing unit tests'
  )
  parser.add_argument(
    '--pattern',
    '-p',
    default='^(test_.*|.*_test)\\.py$',
    type=str,
    help='filename regex for test discovery'
  )
  parser.add_argument(
    '--terminal',
    '-t',
    default=False,
    action='store_true',
    help='do not search for tests recursively'
  )
  parser.add_argument(
    '--json',
    '--j',
    default=False,
    action='store_true',
    help='print results in JSON format'
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
    '--use-exit-code',
    default=False,
    action='store_true',
    help='use exit code to indicate non-passing tests'
  )
  return parser


def main():
  """Run this script from the command line."""

  args = get_argument_parser().parse_args()
  all_pass = run_test_sets(
    args.location,
    args.pattern,
    args.terminal,
    args.json,
    args.color,
    args.full)

  if args.use_exit_code and not all_pass:
    sys.exit(1)


if __name__ == '__main__':
  main()
