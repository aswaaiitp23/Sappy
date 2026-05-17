"""
Stress test for the Sapiex agent runtime.
Tests: file reading, cross-file analysis, skill loading, session persistence, edge cases.

Usage:
    python stress_test.py --agent-dir /path/to/your/agent

The script will:
1. Copy test files into a temp folder
2. Run a series of prompts against your agent
3. Grade each response
4. Print a final report
"""

import subprocess
import sys
import os
import shutil
import tempfile
import time
import argparse
from dataclasses import dataclass
from typing import Optional

# ── ANSI colors ───────────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ── Test case definition ──────────────────────────────────────────────────────
@dataclass
class TestCase:
    name: str
    prompt: str
    expect_keywords: list[str]       # at least one must appear in output
    must_not_contain: list[str]      # none of these should appear
    description: str
    points: int = 1


TESTS = [
    # ── Basic file reading ────────────────────────────────────────────────────
    TestCase(
        name="list_files",
        prompt="List all files in the test_data directory.",
        expect_keywords=["techcorp_annual_report.pdf", "techcorp_revenue.xlsx", "techcorp_products.csv"],
        must_not_contain=["error", "Error", "not found"],
        description="Agent should call list_files and return all 3 test files.",
        points=1,
    ),
    TestCase(
        name="read_pdf",
        prompt="Read the file test_data/techcorp_annual_report.pdf and tell me the total revenue for 2023.",
        expect_keywords=["5.2", "billion", "5.2B", "5,200"],
        must_not_contain=["cannot read", "unable to", "Error"],
        description="Agent should extract revenue figure from PDF.",
        points=2,
    ),
    TestCase(
        name="read_excel",
        prompt="Read the file test_data/techcorp_revenue.xlsx and tell me the total annual revenue across all months.",
        expect_keywords=["4,800", "4800", "4.8", "$4"],
        must_not_contain=["cannot read", "unable to", "Error"],
        description="Agent should sum monthly revenue from Excel (answer: $4,800M).",
        points=2,
    ),
    TestCase(
        name="read_csv",
        prompt="Read test_data/techcorp_products.csv and list all product lines.",
        expect_keywords=["Cloud Storage", "Cloud Compute", "SaaS"],
        must_not_contain=["Error", "cannot"],
        description="Agent should parse CSV and list products.",
        points=1,
    ),

    # ── Cross-file analysis (the real test) ───────────────────────────────────
    TestCase(
        name="cross_file_discrepancy",
        prompt=(
            "Read both test_data/techcorp_annual_report.pdf and test_data/techcorp_revenue.xlsx. "
            "The PDF claims total revenue was $5.2B. Does the monthly data in the Excel file support this? "
            "Flag any discrepancies."
        ),
        expect_keywords=["discrepan", "mismatch", "differ", "4,800", "4.8", "does not match", "inconsisten"],
        must_not_contain=["matches perfectly", "consistent", "accurate"],
        description="Agent must catch that Excel monthly sum ($4.8B) doesn't match PDF claim ($5.2B).",
        points=5,
    ),
    TestCase(
        name="cross_file_regional",
        prompt=(
            "Read test_data/techcorp_annual_report.pdf and test_data/techcorp_revenue.xlsx. "
            "The PDF says Asia-Pacific is 15% of revenue. What does the Excel say? Flag if different."
        ),
        expect_keywords=["18%", "discrepan", "differ", "mismatch", "15%"],
        must_not_contain=["same", "matches", "consistent"],
        description="Agent must catch Asia-Pacific % discrepancy (PDF: 15%, Excel: 18%).",
        points=5,
    ),
    TestCase(
        name="three_file_analysis",
        prompt=(
            "Read all three files: test_data/techcorp_annual_report.pdf, "
            "test_data/techcorp_revenue.xlsx, and test_data/techcorp_products.csv. "
            "Summarize the key financial figures from each and flag anything that looks off across them."
        ),
        expect_keywords=["discrepan", "flag", "mismatch", "differ", "inconsisten"],
        must_not_contain=["cannot", "unable"],
        description="Agent must synthesize all 3 files and flag cross-file issues.",
        points=5,
    ),

    # ── Skills system ─────────────────────────────────────────────────────────
    TestCase(
        name="skill_loaded",
        prompt="What skills do you have available?",
        expect_keywords=["financial_analysis", "skill", "Financial"],
        must_not_contain=["no skills", "none"],
        description="Agent should report available skills from the skills folder.",
        points=2,
    ),

    # ── Edge cases ────────────────────────────────────────────────────────────
    TestCase(
        name="missing_file",
        prompt="Read the file test_data/nonexistent_file.pdf",
        expect_keywords=["not found", "doesn't exist", "Error", "error", "cannot find"],
        must_not_contain=["success", "here is the content"],
        description="Agent should gracefully handle missing files.",
        points=1,
    ),
    TestCase(
        name="unsupported_format",
        prompt="Read the file test_data/techcorp_annual_report.pdf — but tell me only about Q4 performance.",
        expect_keywords=["Q4", "quarter", "December", "fourth"],
        must_not_contain=["cannot", "Error reading"],
        description="Agent should extract specific section from PDF.",
        points=2,
    ),
]


# ── Runner ────────────────────────────────────────────────────────────────────

def run_agent_prompt(agent_dir: str, prompt: str, session_id: Optional[str] = None, timeout: int = 60) -> str:
    """Send one prompt to the agent and capture output."""
    cmd = [sys.executable, "agent.py"]
    if session_id:
        cmd += ["--session", session_id]

    env = os.environ.copy()

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=agent_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
        # Send prompt then exit
        stdout, stderr = proc.communicate(input=prompt + "\nexit\n", timeout=timeout)
        return stdout + stderr
    except subprocess.TimeoutExpired:
        proc.kill()
        return "TIMEOUT: Agent did not respond within 60 seconds"
    except Exception as e:
        return f"ERROR: {str(e)}"


def grade(output: str, test: TestCase) -> tuple[bool, str]:
    output_lower = output.lower()

    # Check must_not_contain
    for bad in test.must_not_contain:
        if bad.lower() in output_lower:
            return False, f"Output contained forbidden phrase: '{bad}'"

    # Check expect_keywords (at least one)
    for kw in test.expect_keywords:
        if kw.lower() in output_lower:
            return True, f"Found expected keyword: '{kw}'"

    return False, f"None of the expected keywords found: {test.expect_keywords}"


def setup_test_data(agent_dir: str):
    """Copy generated test files into agent's test_data folder."""
    test_data_dir = os.path.join(agent_dir, "test_data")
    os.makedirs(test_data_dir, exist_ok=True)

    files = {
        "/tmp/techcorp_annual_report.pdf": "techcorp_annual_report.pdf",
        "/tmp/techcorp_revenue.xlsx": "techcorp_revenue.xlsx",
        "/tmp/techcorp_products.csv": "techcorp_products.csv",
    }

    missing = []
    for src, name in files.items():
        dst = os.path.join(test_data_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  ✅ Copied {name}")
        else:
            missing.append(src)
            print(f"  ❌ Missing: {src} — run generate_test_files.py first")

    return len(missing) == 0


def main():
    parser = argparse.ArgumentParser(description="Stress test your Sapiex agent")
    parser.add_argument(
        "--agent-dir",
        default=".",
        help="Path to your agent directory (where agent.py lives)"
    )
    parser.add_argument(
        "--test",
        help="Run only this test by name (e.g. --test cross_file_discrepancy)"
    )
    args = parser.parse_args()

    agent_dir = os.path.abspath(args.agent_dir)
    agent_py = os.path.join(agent_dir, "agent.py")

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  Sapiex Agent Stress Test{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")

    # Verify agent exists
    if not os.path.exists(agent_py):
        print(f"{RED}❌ agent.py not found at {agent_py}{RESET}")
        sys.exit(1)

    # Setup test data
    print(f"{CYAN}Setting up test data...{RESET}")
    ok = setup_test_data(agent_dir)
    if not ok:
        print(f"\n{RED}Generate test files first:{RESET}")
        print("  python generate_test_files.py")
        sys.exit(1)

    print()

    # Run tests
    tests_to_run = TESTS
    if args.test:
        tests_to_run = [t for t in TESTS if t.name == args.test]
        if not tests_to_run:
            print(f"{RED}No test named '{args.test}'{RESET}")
            sys.exit(1)

    results = []
    total_points = sum(t.points for t in tests_to_run)
    earned_points = 0

    for i, test in enumerate(tests_to_run):
        print(f"{CYAN}[{i+1}/{len(tests_to_run)}] {test.name}{RESET}")
        print(f"  {test.description}")
        print(f"  Prompt: \"{test.prompt[:80]}{'...' if len(test.prompt) > 80 else ''}\"")

        start = time.time()
        output = run_agent_prompt(agent_dir, test.prompt)
        elapsed = time.time() - start

        passed, reason = grade(output, test)
        results.append((test, passed, reason, output, elapsed))

        if passed:
            earned_points += test.points
            print(f"  {GREEN}✅ PASS{RESET} ({elapsed:.1f}s) — {reason}")
        else:
            print(f"  {RED}❌ FAIL{RESET} ({elapsed:.1f}s) — {reason}")
            # Show last 300 chars of output for debugging
            snippet = output.strip()[-300:] if output.strip() else "(no output)"
            print(f"  {YELLOW}Output snippet:{RESET} ...{snippet}")

        print()
        time.sleep(1)  # avoid rate limiting

    # Final report
    print(f"{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  Results: {earned_points}/{total_points} points{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")

    passed_count = sum(1 for _, p, _, _, _ in results if p)
    failed_count = len(results) - passed_count

    print(f"  {GREEN}✅ Passed: {passed_count}{RESET}")
    print(f"  {RED}❌ Failed: {failed_count}{RESET}\n")

    if failed_count > 0:
        print(f"{BOLD}Failed tests:{RESET}")
        for test, passed, reason, output, _ in results:
            if not passed:
                print(f"  • {test.name}: {reason}")

    # Score interpretation
    pct = earned_points / total_points * 100
    print()
    if pct >= 90:
        print(f"{GREEN}{BOLD}  🏆 Excellent! Ready to submit.{RESET}")
    elif pct >= 70:
        print(f"{YELLOW}{BOLD}  👍 Good. Fix the failing tests before submitting.{RESET}")
    elif pct >= 50:
        print(f"{YELLOW}{BOLD}  ⚠️  Needs work. Focus on cross-file analysis tests.{RESET}")
    else:
        print(f"{RED}{BOLD}  ❌ Major issues. Start with basic file reading tests.{RESET}")

    print()


if __name__ == "__main__":
    main()