from setuptools import setup, find_packages

setup(
    name="azureslop",
    version="0.7.0",
    license="GPL-3.0-only",
    license_files=["LICENSE"],
    packages=find_packages(),
    install_requires=[],
    entry_points={
        "console_scripts": [
            "azureslop=azureslop.main:main",
        ],
    },
    python_requires=">=3.10",
)
