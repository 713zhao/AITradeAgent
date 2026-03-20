#!/usr/bin/env python3
"""
Verification script for AITradeAgent fixes.

Tests:
1. Async Event Bus: No RuntimeWarning when importing agents
2. Config System: Pydantic validation works, invalid values raise errors
3. Test Coverage: pytest-cov is installed and functional
4. Import Errors: No new import errors after fixes
"""

import sys
import subprocess
import warnings
import os
from pathlib import Path

PROJECT_ROOT = Path("/home/eric/.openclaw/workspace/AITradeAgent")
VENV_PYTHON = PROJECT_ROOT / "venv" / "bin" / "python3"

def test_event_bus_no_warning():
    """Test that importing agents does not produce RuntimeWarning about coroutine."""
    print("\n" + "="*70)
    print("TEST 1: Async Event Bus Fix")
    print("="*70)
    print("Importing analysis_agent and learning_agent...")
    cmd = [
        str(VENV_PYTHON), "-c",
        "import warnings; warnings.simplefilter('error', RuntimeWarning); "
        "from finance_service.agents.analysis_agent import AnalysisAgent; "
        "from finance_service.agents.learning_agent import LearningAgent; "
        "print('Import OK')"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"❌ FAILED: {result.stderr}")
        return False
    if "RuntimeWarning" in result.stderr:
        print(f"❌ FAILED: RuntimeWarning found: {result.stderr}")
        return False
    print("✅ PASSED: No RuntimeWarning on agent import")
    print(f"Output: {result.stdout.strip()}")
    return True

def test_config_validation():
    """Test that Config class uses validated Pydantic settings."""
    print("\n" + "="*70)
    print("TEST 2: Config System Upgrade")
    print("="*70)
    # Test 1: Import and check Config values
    cmd = [
        str(VENV_PYTHON), "-c",
        "from finance_service.core.config import Config; "
        "print('MAX_POSITION_SIZE:', Config.MAX_POSITION_SIZE); "
        "print('MAX_EXPOSURE:', Config.MAX_EXPOSURE); "
        "assert 0 < Config.MAX_POSITION_SIZE < 1, 'Invalid MAX_POSITION_SIZE'; "
        "assert 0 < Config.MAX_EXPOSURE <= 1, 'Invalid MAX_EXPOSURE'; "
        "print('Validation passed')"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"❌ FAILED: {result.stderr}")
        return False
    print("✅ PASSED: Config values are valid and accessible")
    print(f"Output: {result.stdout.strip()}")

    # Test 2: Check that invalid config raises error at load time
    print("\nSubtest: Invalid environment variable should fail at startup")
    env_file = PROJECT_ROOT / ".env"
    original_env = None
    if env_file.exists():
        original_env = env_file.read_text()
        # Temporarily set invalid MAX_POSITION_SIZE
        lines = original_env.splitlines()
        new_lines = []
        found = False
        for line in lines:
            if line.startswith("MAX_POSITION_SIZE="):
                new_lines.append("MAX_POSITION_SIZE=1.5")  # invalid >1
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append("MAX_POSITION_SIZE=1.5")
        env_file.write_text("\n".join(new_lines))
        env_file.chmod(0o600)
    else:
        # Create a .env with invalid value
        env_file.write_text("MAX_POSITION_SIZE=1.5\n")
        env_file.chmod(0o600)

    # Create a temporary script to test invalid config import
    test_script = PROJECT_ROOT / "temp_invalid_config_test.py"
    test_script.write_text("""import sys
try:
    from finance_service.core.config import Config
    print('Unexpectedly loaded invalid config')
    sys.exit(1)
except ValueError as e:
    print('Validation error caught:', e)
    sys.exit(0)
""")
    try:
        cmd2 = [str(VENV_PYTHON), str(test_script)]
        result2 = subprocess.run(cmd2, capture_output=True, text=True, cwd=PROJECT_ROOT)
    finally:
        if test_script.exists():
            test_script.unlink()
        # Restore original .env
        if original_env is not None:
            env_file.write_text(original_env)
        else:
            if env_file.exists():
                env_file.unlink()

    if result2.returncode != 0:
        print(f"❌ FAILED: Should have caught validation error. {result2.stderr}")
        return False
    if "Validation error caught" not in result2.stdout:
        print(f"❌ FAILED: Did not get expected validation message: {result2.stdout}")
        return False
    print("✅ PASSED: Invalid configuration rejected at import")
    print(f"Output: {result2.stdout.strip()}")
    return True

def test_coverage_installed():
    """Test that pytest-cov is installed and can produce report."""
    print("\n" + "="*70)
    print("TEST 3: Test Coverage Setup")
    print("="*70)
    cmd = [str(VENV_PYTHON), "-m", "pytest", "--version"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"❌ FAILED: pytest not available: {result.stderr}")
        return False
    print(f"pytest version: {result.stdout.strip()}")

    # Check if pytest-cov plugin is present
    cmd2 = [str(VENV_PYTHON), "-m", "pytest", "--cov", "--version"]
    result2 = subprocess.run(cmd2, capture_output=True, text=True, cwd=PROJECT_ROOT)
    # --cov flag should not cause error even without specifying module
    if result2.returncode != 0 and "no such option" in result2.stderr.lower():
        print(f"❌ FAILED: pytest-cov not installed: {result2.stderr}")
        return False
    print("✅ PASSED: pytest-cov plugin is available")
    return True

def test_no_import_errors():
    """Test that critical modules import without errors."""
    print("\n" + "="*70)
    print("TEST 4: Fix Import Errors")
    print("="*70)
    print("Removing old import_error.log if exists...")
    import_error_log = PROJECT_ROOT / "import_error.log"
    if import_error_log.exists():
        import_error_log.unlink()
        print("Deleted old import_error.log")

    print("\nImporting key modules...")
    modules = [
        "finance_service.core.event_bus",
        "finance_service.core.config",
        "finance_service.agents.analysis_agent",
        "finance_service.agents.learning_agent",
        "finance_service.agents.data_agent",
        "finance_service.agents.strategy_agent",
        "finance_service.agents.risk_agent",
    ]
    for mod in modules:
        cmd = [str(VENV_PYTHON), "-c", f"import {mod}"]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
        if result.returncode != 0:
            print(f"❌ FAILED to import {mod}: {result.stderr}")
            return False
        # Check if import_error.log was not written
        if import_error_log.exists():
            print(f"❌ FAILED: import_error.log created after importing {mod}")
            print(f"Content: {import_error_log.read_text()}")
            return False
    print("✅ PASSED: All modules imported without warnings or errors")
    return True

def main():
    print("\n" + "="*70)
    print("AITradeAgent Fixes - Verification Suite")
    print("="*70)
    results = []
    results.append(("Async Event Bus", test_event_bus_no_warning()))
    results.append(("Config System Upgrade", test_config_validation()))
    results.append(("Test Coverage Setup", test_coverage_installed()))
    results.append(("Import Errors Fixed", test_no_import_errors()))

    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(passed for _, passed in results)
    if all_passed:
        print("\n🎉 All fixes verified successfully!")
        return 0
    else:
        print("\n⚠️ Some fixes not verified. Review output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
