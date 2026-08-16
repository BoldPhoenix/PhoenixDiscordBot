# Contributing to ARK Discord Bot

Thank you for considering contributing to the ARK Discord Bot! This document provides guidelines and instructions for contributing.

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in Issues
2. If not, create a new issue with:
   - Clear, descriptive title
   - Steps to reproduce
   - Expected vs actual behavior
   - Your environment (Python version, OS, etc.)
   - Relevant logs or error messages

### Suggesting Features

1. Check if the feature has been suggested
2. Create a new issue with:
   - Clear description of the feature
   - Use case and benefits
   - Possible implementation approach

### Pull Requests

1. **Fork the repository**
2. **Create a branch** for your feature/fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes** following our coding standards:
   - Use type hints where appropriate
   - Add docstrings to functions and classes
   - Follow PEP 8 style guide
   - Keep functions focused and modular

4. **Test your changes**:
   ```powershell
   .\manage.ps1 lint
   .\manage.ps1 format
   ```

5. **Commit your changes**:
   ```bash
   git commit -m "Add feature: brief description"
   ```

6. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Create a Pull Request**:
   - Provide clear description of changes
   - Reference any related issues
   - Include screenshots if relevant

## Development Setup

```powershell
# Clone your fork
git clone https://github.com/your-username/ArkDiscordBot.git
cd ArkDiscordBot

# Install dependencies
.\manage.ps1 install

# Set up environment
Copy-Item .env.example .env
# Edit .env with your test bot credentials

# Initialize database
.\manage.ps1 setup

# Run the bot
.\manage.ps1 run
```

## Coding Standards

### Python Style

- Follow PEP 8
- Use Black for formatting (max line length: 100)
- Use meaningful variable names
- Add type hints

Example:
```python
async def get_user_balance(user_id: int) -> int:
    """
    Get the Phoenix Coin balance for a user.
    
    Args:
        user_id: Discord user ID
        
    Returns:
        User's coin balance
    """
    user = await user_db.get_user(user_id)
    return user["phoenix_coins"] if user else 0
```

### Commit Messages

- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Reference issues and PRs when relevant
- Keep first line under 50 characters
- Add detailed description after blank line if needed

Good examples:
```
Add coin transaction history command

Implements /history command that shows recent coin transactions
for users. Includes pagination for large histories.

Fixes #123
```

## Testing

### Manual Testing

1. Test with a real Discord server
2. Verify RCON connections work
3. Test purchase flow end-to-end
4. Check error handling

### Adding Tests

```python
# tests/test_user_db.py
import pytest
from bot.database import user_db

@pytest.mark.asyncio
async def test_create_user():
    """Test user creation."""
    await user_db.create_or_update_user(12345, "TestUser")
    user = await user_db.get_user(12345)
    assert user["username"] == "TestUser"
    assert user["phoenix_coins"] == 0
```

## Project Structure

```
bot/
├── cogs/          # Discord command modules
├── database/      # Database operations
├── rcon/          # ARK RCON client
└── utils/         # Utility functions
```

### Adding a New Cog

1. Create file in `bot/cogs/`
2. Inherit from `commands.Cog`
3. Add `setup()` function
4. Import in `main.py`

Example:
```python
from discord.ext import commands

class MyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="mycommand")
    async def my_command(self, interaction: discord.Interaction):
        """Command description."""
        await interaction.response.send_message("Hello!")

async def setup(bot: commands.Bot):
    await bot.add_cog(MyCog(bot))
```

## Areas for Contribution

### High Priority
- Additional store item templates
- Improved error handling
- Performance optimizations
- Documentation improvements

### Feature Ideas
- Web dashboard
- Advanced analytics
- Scheduled rewards
- Tribe management integration
- Multi-language support

### Documentation Needs
- Video tutorials
- More examples
- Troubleshooting guide expansion
- ARK command reference

## Questions?

- Open a Discussion on GitHub
- Join our Discord server
- Check existing Issues and PRs

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing! 🎉
