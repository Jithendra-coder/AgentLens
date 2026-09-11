from setuptools import setup, find_packages

setup(
    name="agentlens",
    version="0.2.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "agentlens=agentlens_core.cli:main",
        ],
    },
    python_requires=">=3.9",
    install_requires=[],
    extras_require={
        "postgres": ["psycopg[binary]>=3.1,<4"],
        "test": ["pytest>=7.0"],
    },
)
