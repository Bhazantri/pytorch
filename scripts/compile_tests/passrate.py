#!/usr/bin/env python3
"""
Pass Rate Calculator for Dynamo Unittests

This script computes the Dynamo unittest pass rate based on two sets of test reports:
1. Eager mode test reports (baseline)
2. Dynamo mode test reports

The pass rate is defined as:
    (Number of tests that pass in Dynamo mode) / (Number of tests that pass in eager mode)
after filtering out certain test cases (e.g., tests from inductor, export, or dynamo directories, and C++ tests).

Usage:
    python passrate.py <commit_sha>
    
Ensure that you have installed and authenticated the `gh` CLI, as it is required for downloading reports.
"""

import argparse
import logging
from typing import Set, Tuple

from common import (
    get_excluded_testcases,
    get_passed_testcases,
    get_testcases,
    key,
    open_test_results,
)
from download_reports import download_reports

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """
    Parse and return the command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Computes the Dynamo unittest pass rate from CI test reports."
    )
    parser.add_argument(
        "commit",
        help=(
            "Commit SHA for the latest commit on a PR from which to pull CI test results, "
            "e.g. 7e5f597aeeba30c390c05f7d316829b3798064a5"
        ),
    )
    return parser.parse_args()


def should_exclude(test_key: str) -> bool:
    """
    Determine if a test should be excluded from the pass rate calculation.
    
    Exclusions:
      - C++ tests (represented by a test file value of "UNKNOWN")
      - Tests under directories: inductor/, export/, or dynamo/
    
    Parameters:
        test_key (str): A string key representing a test, e.g., "module/test_file.py::TestClass::test_method".
        
    Returns:
        bool: True if the test should be excluded, False otherwise.
    """
    test_file = test_key.split("::")[0]
    if test_file == "UNKNOWN":
        return True
    return test_file.startswith(("inductor/", "export/", "dynamo/"))


def compute_pass_rate(eager_dir: str, dynamo_dir: str) -> Tuple[float, Set[str], Set[str]]:
    """
    Compute the pass rate of Dynamo tests compared to eager tests.

    Parameters:
        eager_dir (str): Directory containing eager mode test report XML files.
        dynamo_dir (str): Directory containing dynamo mode test report XML files.

    Returns:
        Tuple[float, Set[str], Set[str]]:
            - pass_rate: Ratio of tests that pass in Dynamo to those that pass in eager mode.
            - eager_pass_keys: Set of test keys (from eager mode) after filtering.
            - failing_keys: Set of test keys that passed in eager mode but did not pass in Dynamo.
    """
    logger.info("Opening test result XML files")
    eager_xmls = open_test_results(eager_dir)
    dynamo_xmls = open_test_results(dynamo_dir)

    logger.info("Extracting passed test cases from eager and dynamo reports")
    eager_passed = get_passed_testcases(eager_xmls)
    dynamo_passed = get_passed_testcases(dynamo_xmls)

    # Filter and build sets of test keys for both modes
    dynamo_pass_keys = {
        key(tc) for tc in dynamo_passed if not should_exclude(key(tc))
    }
    eager_pass_keys = {
        key(tc) for tc in eager_passed if not should_exclude(key(tc))
    }
    # Exclude tests that are explicitly marked as excluded in the dynamo XMLs
    excluded_keys = {key(tc) for tc in get_excluded_testcases(dynamo_xmls)}
    eager_pass_keys.difference_update(excluded_keys)

    # Intersection: tests that passed in both modes
    successful_keys = eager_pass_keys.intersection(dynamo_pass_keys)
    total_eager_tests = len(eager_pass_keys)

    if total_eager_tests == 0:
        logger.warning("No eager mode tests found after filtering. Cannot compute pass rate.")
        return 0.0, eager_pass_keys, set()

    pass_rate = len(successful_keys) / total_eager_tests
    logger.info("Computed pass rate: %.2f (%d/%d)", pass_rate, len(successful_keys), total_eager_tests)

    # Identify tests that passed in eager mode but failed in dynamo mode
    failing_keys = eager_pass_keys - successful_keys

    # Debug: Check if there are eager tests not present in dynamo reports at all.
    dynamo_testcases = get_testcases(dynamo_xmls)
    dynamo_test_keys = {key(tc) for tc in dynamo_testcases}
    missing_in_dynamo = eager_pass_keys - dynamo_test_keys
    if missing_in_dynamo:
        logger.debug("Eager tests not found in dynamo reports: %s", missing_in_dynamo)

    return pass_rate, eager_pass_keys, failing_keys


def main():
    args = parse_arguments()
    commit_sha = args.commit

    logger.info("Downloading test reports for commit: %s", commit_sha)
    # Download reports for dynamo and eager modes. The order of returned directories matches the provided report names.
    dynamo_dir, eager_dir = download_reports(commit_sha, ("dynamo311", "eager311"))

    pass_rate, eager_keys, failing_keys = compute_pass_rate(eager_dir, dynamo_dir)

    print("\n=== Dynamo Test Pass Rate Report ===")
    print("Dynamo Test Pass Rate: {:.2f}".format(pass_rate))
    print("Total Eager Passed Tests (after filtering):", len(eager_keys))
    print("Number of Dynamo Failing Tests:", len(failing_keys))
    if failing_keys:
        print("\nFailing Test Cases:")
        for test in sorted(failing_keys):
            print(" -", test)


if __name__ == "__main__":
    main()

