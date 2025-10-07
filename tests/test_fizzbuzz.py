"""Tests for FizzBuzz example."""

from examples.fizzbuzz import fizzbuzz


class TestFizzBuzz:
    """Test cases for the FizzBuzz implementation."""

    def test_fizzbuzz_regular_numbers(self):
        """Test that regular numbers return the number as a string."""
        assert fizzbuzz(1) == "1"
        assert fizzbuzz(2) == "2"
        assert fizzbuzz(4) == "4"
        assert fizzbuzz(7) == "7"
        assert fizzbuzz(8) == "8"

    def test_fizzbuzz_multiples_of_3(self):
        """Test that multiples of 3 return 'Fizz'."""
        assert fizzbuzz(3) == "Fizz"
        assert fizzbuzz(6) == "Fizz"
        assert fizzbuzz(9) == "Fizz"
        assert fizzbuzz(12) == "Fizz"

    def test_fizzbuzz_multiples_of_5(self):
        """Test that multiples of 5 return 'Buzz'."""
        assert fizzbuzz(5) == "Buzz"
        assert fizzbuzz(10) == "Buzz"
        assert fizzbuzz(20) == "Buzz"
        assert fizzbuzz(25) == "Buzz"

    def test_fizzbuzz_multiples_of_15(self):
        """Test that multiples of 15 return 'FizzBuzz'."""
        assert fizzbuzz(15) == "FizzBuzz"
        assert fizzbuzz(30) == "FizzBuzz"
        assert fizzbuzz(45) == "FizzBuzz"
        assert fizzbuzz(60) == "FizzBuzz"

    def test_fizzbuzz_edge_cases(self):
        """Test edge cases."""
        # Test the first few numbers in sequence
        expected = [
            "1",
            "2",
            "Fizz",
            "4",
            "Buzz",
            "Fizz",
            "7",
            "8",
            "Fizz",
            "Buzz",
            "11",
            "Fizz",
            "13",
            "14",
            "FizzBuzz",
        ]

        for i, expected_value in enumerate(expected, 1):
            assert fizzbuzz(i) == expected_value

    def test_fizzbuzz_larger_numbers(self):
        """Test larger numbers to ensure pattern holds."""
        assert fizzbuzz(99) == "Fizz"  # 99 = 3 * 33
        assert fizzbuzz(100) == "Buzz"  # 100 = 5 * 20
        assert fizzbuzz(150) == "FizzBuzz"  # 150 = 15 * 10
