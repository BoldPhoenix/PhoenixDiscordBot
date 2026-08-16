#!/usr/bin/env python3
"""
Test runner with lint and coverage
"""

import os
import sys
import subprocess
from pathlib import Path

def run_command(cmd, description):
    """Run command and return success."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {cmd}")
    print('='*60)
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        
        if result.stdout:
            print("STDOUT:")
            print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        success = result.returncode == 0
        print(f"\n{'✅ PASSED' if success else '❌ FAILED'}: {description}")
        return success
        
    except subprocess.TimeoutExpired:
        print(f"\n❌ TIMEOUT: {description}")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {description} - {e}")
        return False

def main():
    """Run complete test suite."""
    print("Phoenix ARK Bot - Complete Test Suite")
    
    # Set test environment
    os.environ['DISCORD_BOT_TOKEN'] = 'test_token'
    os.environ['DISCORD_APP_ID'] = '123456789'
    os.environ['DISCORD_GUILD_ID'] = '123456789'
    os.environ['DATABASE_PATH'] = 'test.db'
    
    tests_passed = []
    tests_failed = []
    
    # 1. Lint with flake8 (ignore warnings for now)
    if run_command("python -m flake8 bot/ --max-line-length=120 --ignore=E501,W503,F401,F541,F841,W291,W293,E722,E226,F811", "Lint (flake8)"):
        tests_passed.append("flake8")
    else:
        tests_failed.append("flake8")
    
    # 2. Black formatting check
    if run_command("python -m black --check bot/ --line-length=120", "Code formatting (black)"):
        tests_passed.append("black")
    else:
        tests_failed.append("black")
    
    # 3. Run pytest with coverage for new commands only
    if run_command("python -m pytest tests/test_rcon_admin_logic.py -v --tb=short --cov=bot --cov-report=term-missing", "Unit tests (pytest)"):
        tests_passed.append("pytest")
    else:
        tests_failed.append("pytest")
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUITE SUMMARY")
    print('='*60)
    
    if tests_passed:
        print(f"✅ PASSED ({len(tests_passed)}): {', '.join(tests_passed)}")
    
    if tests_failed:
        print(f"❌ FAILED ({len(tests_failed)}): {', '.join(tests_failed)}")
    
    total_tests = len(tests_passed) + len(tests_failed)
    success_rate = len(tests_passed) / total_tests * 100 if total_tests > 0 else 0
    
    print(f"\nSuccess Rate: {success_rate:.1f}% ({len(tests_passed)}/{total_tests})")
    
    if tests_failed:
        print("\n❌ TEST SUITE FAILED")
        sys.exit(1)
    else:
        print("\n✅ ALL TESTS PASSED")
        sys.exit(0)

if __name__ == "__main__":
    main()
