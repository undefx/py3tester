"""Simple math helpers."""

# standard library
import math


class Thing:
  """Provides math helpers."""

  @staticmethod
  def add(a, b):
    """Add two numbers."""
    return a + b

  @staticmethod
  def div(a, b):
    """Divide two numbers."""
    return a / b

  @staticmethod
  def saxpy(a, x, y):
    """Compute ((a * x) + y)."""
    return Thing.add(a * x, y)

  @staticmethod
  def get_pi(guess=3):
    """Make a guess at π."""
    return Thing.add(guess, math.sin(guess))

  @staticmethod
  def get_tau(guess=6):
    """Make a guess at τ."""
    return 2 * Thing.get_pi(Thing.div(guess, 2))
