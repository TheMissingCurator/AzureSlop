from setuptools import setup, find_packages

setup(
    name="azureslop",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "watchdog>=3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "azureslop=azureslop.main:main",
        ],
    },
    python_requires=">=3.9",
)
