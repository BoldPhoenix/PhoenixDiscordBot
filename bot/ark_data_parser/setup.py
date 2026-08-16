"""Setup script for ark-asa-parser package."""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="ark-asa-parser",
    version="0.1.0",
    description="Python library for parsing ARK: Survival Ascended save files",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="BoldPhoenix",
    author_email="boldphoenix@example.com",
    url="https://github.com/BoldPhoenix/ArkDiscordBot",
    packages=find_packages(exclude=["tests*"]),
    install_requires=[
        "python-dateutil>=2.8.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
        ],
    },
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Games/Entertainment",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords="ark survival ascended asa save parser game data",
    project_urls={
        "Homepage": "https://github.com/BoldPhoenix/ArkDiscordBot",
        "Documentation": "https://github.com/BoldPhoenix/ArkDiscordBot/wiki",
        "Repository": "https://github.com/BoldPhoenix/ArkDiscordBot",
        "Bug Tracker": "https://github.com/BoldPhoenix/ArkDiscordBot/issues",
    },
)
