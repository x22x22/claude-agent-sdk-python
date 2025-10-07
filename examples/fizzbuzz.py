#!/usr/bin/env python3
"""FizzBuzz example for Claude Code SDK."""


def fizzbuzz(n: int) -> str:
    """
    Classic FizzBuzz implementation.

    Returns "Fizz" for multiples of 3, "Buzz" for multiples of 5,
    "FizzBuzz" for multiples of both 3 and 5, and the number as a string otherwise.

    Args:
        n: The number to check

    Returns:
        str: The FizzBuzz result for the number
    """
    if n % 15 == 0:
        return "FizzBuzz"
    elif n % 3 == 0:
        return "Fizz"
    elif n % 5 == 0:
        return "Buzz"
    else:
        return str(n)


def print_fizzbuzz(limit: int = 100) -> None:
    """
    Print FizzBuzz sequence from 1 to limit.

    Args:
        limit: The upper limit of the sequence (inclusive)
    """
    print(f"=== FizzBuzz (1 to {limit}) ===")
    for i in range(1, limit + 1):
        print(fizzbuzz(i))


if __name__ == "__main__":
    print_fizzbuzz()
