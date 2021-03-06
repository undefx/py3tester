"""Unit tests for thing.py"""

# standard library
import math
import unittest

# special import for tracking coverage
__test_target__ = 'samples.thing'


class BasicTests(unittest.TestCase):
  """Basic tests."""

  def test_add(self):
    self.assertEqual(2, Thing.add(1, 1), '1 + 1 = 2')

  def test_div(self):
    self.assertEqual(2, Thing.div(2, 1), '2 / 1 = 2')

  def test_saxpy(self):
    self.assertEqual(2, Thing.saxpy(2, 2, -2), '2 * 2 - 2 = 2')

  def test_get_pi(self):
    self.assertTrue(3 < Thing.get_pi(guess=3.0) < 3.5, '3 < π < 3.5')
    self.assertTrue(3 < Thing.get_pi(guess=3.5) < 3.5, '3 < π < 3.5')

  def test_get_e(self):
    self.assertTrue(1.618 < Thing.get_phi(n=1000) < 1.619, '1.618 < e < 1.619')

  def test_get_pi_minus_phi(self):
    actual = Thing.get_pi_minus_phi()
    expected = math.pi - (1 + 5 ** 0.5) / 2
    self.assertTrue(abs(actual - expected) < 1e-8, 'π - φ ≈ 1.52356...')


class AdvancedTests(unittest.TestCase):
  """Advanced tests."""

  # commented out to demonstrate error
  #@unittest.expectedFailure
  def test_div0(self):
    self.assertEqual(0, Thing.div(1, 0), '1 / 0 = 0')  # error

  # commented out to demonstrate failure
  #@unittest.expectedFailure
  def test_div1(self):
    self.assertEqual(0, Thing.div(1, 1), '1 / 1 = 0')  # fail

  # demonstrate skipped test
  @unittest.skip('not implemented')
  def test_get_tau(self):
    self.assertTrue(6 < Thing.get_tau() < 6.5, '6 < τ < 6.5')
