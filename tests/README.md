# Phoenix ARK Discord Bot - Test Suite

Comprehensive automated test suite that validates all bot functionality.

## What It Tests

### 1. File Structure
- Verifies all required bot files exist
- Checks for core modules, cogs, database files, and utilities

### 2. Database Schema
- Validates all required tables exist
- Checks column structure for critical tables
- Tests voice_channel_mappings table integrity

### 3. Emoji Encoding
- Scans source files for corrupted emoji sequences
- Detects common corruption patterns:
  - `ðŸ` (corrupted emoji prefix)
  - `â€¢` (corrupted bullet point)
  - `ðŸŸ` (corrupted circle emojis)
  - `ðŸ–¥` (corrupted computer emoji)

### 4. Module Imports
- Tests that all critical modules can be imported
- Verifies required classes and functions exist
- Checks for import errors

### 5. Cog Structure
- Validates all Discord cogs have required classes
- Checks for critical methods in each cog
- Ensures proper structure

### 6. Command Defer Pattern
- Tests that database-heavy commands defer properly
- Ensures defer happens BEFORE database operations
- Prevents Discord timeout errors (3-second limit)

### 7. RCON Client
- Validates SimpleRCONClient implementation
- Ensures asyncio.open_connection is used (Windows compatible)
- Checks that aiorcon is not used (has Python 3.12 issues)

### 8. Environment Template
- Validates .env.template documentation
- Checks for database-first messaging
- Ensures bot token placeholder exists

### 9. Voice Channel Persistence
- Tests voice_channel_mappings table helpers
- Validates get/set/clear functions exist
- Ensures proper database-backed persistence

## Running the Tests

### Basic Usage
```powershell
python tests\test_suite.py
```

### Specify Bot Path
```powershell
python tests\test_suite.py C:\path\to\bot
```

### Run from Live Directory
```powershell
cd C:/PhoenixBot
python tests\test_suite.py .
```

## Test Results

### Exit Codes
- `0` - All tests passed
- `1` - One or more tests failed

### Output Format
```
[PASS] - Test passed successfully
[FAIL] - Test failed with error details
[WARN] - Test passed but with warnings
```

## Common Failures

### Expected Failures

**Database doesn't exist**
- Normal for fresh installations
- Will be created on first bot run
- Not a blocking issue

### Actionable Failures

**Corrupted emoji encoding**
- File has Unicode corruption
- Replace corrupted sequences with actual emojis
- Usually caused by incorrect file encoding

**Missing defer in command**
- Command will timeout (3-second limit)
- Add `await interaction.response.defer(ephemeral=True)` as first line
- Use `interaction.followup.send()` instead of `interaction.response.send_message()`

**Module import failure**
- Missing dependency or syntax error
- Check Python environment
- Verify file exists and has no syntax errors

**Uses aiorcon**
- Will fail on Windows/Python 3.12
- Replace with SimpleRCONClient
- Use asyncio.open_connection instead

## Continuous Testing

### Before Commits
```powershell
# Run tests
python tests\test_suite.py

# Only commit if tests pass
if ($LASTEXITCODE -eq 0) {
    git commit -m "Your commit message"
} else {
    Write-Host "Tests failed! Fix issues before committing."
}
```

### After Making Changes
Always run the test suite after:
- Editing cog files
- Modifying database schema
- Changing RCON client
- Updating emoji usage
- Adding new commands

## Test Coverage

Current test coverage:
- ✅ All core files
- ✅ Database structure
- ✅ RCON connectivity
- ✅ Discord commands
- ✅ Emoji encoding
- ✅ Import integrity
- ✅ Command timeout prevention

## Adding New Tests

To add a new test category:

1. Create async test method in `BotTestSuite` class
2. Use `self.add_result()` to record test results
3. Call `self.print_result()` to display results
4. Add method call in `run_tests()` function

Example:
```python
async def test_my_feature(self):
    """Test my new feature."""
    print(f"\n{Colors.BOLD}Testing My Feature...{Colors.RESET}")
    
    # Your test logic here
    result = some_test()
    
    self.add_result(
        "My feature works",
        result,
        "Error message if failed" if not result else ""
    )
    self.print_result(self.results[-1])
```

## Troubleshooting

### UnicodeEncodeError on Windows
The test suite uses ASCII-safe output (`[PASS]`, `[FAIL]`) instead of Unicode symbols to avoid Windows console encoding issues.

### Import Errors
If you see import errors, make sure you're running from the bot directory or the parent directory contains the bot folder.

### Database Locked
If you get "database is locked" errors, make sure the bot isn't running while tests execute.

## Integration with CI/CD

This test suite can be integrated into CI/CD pipelines:

```yaml
# GitHub Actions example
- name: Run Tests
  run: python tests/test_suite.py
  working-directory: ./bot

- name: Check Results
  run: |
    if [ $? -ne 0 ]; then
      echo "Tests failed!"
      exit 1
    fi
```

## Test Development Status

✅ File structure validation
✅ Database schema validation  
✅ Emoji encoding detection
✅ Module import testing
✅ Cog structure validation
✅ Command defer pattern checking
✅ RCON client validation
✅ Environment template checking
✅ Voice channel persistence testing

Future enhancements:
- [ ] Live Discord connection testing
- [ ] RCON connectivity testing with actual servers
- [ ] Database migration testing
- [ ] Performance benchmarks
- [ ] Memory leak detection
