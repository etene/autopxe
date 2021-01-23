"""Automatically sets up everything for a PXE install"""

from pathlib import Path

import setuptools

VERSION_FILE = Path(__file__).parent / "autopxe" / "VERSION"

try:
    long_description = Path("README.md").read_text()  # TODO write readme
except IOError:
    long_description = (
        "autopxe"
    )

setuptools.setup(
    name="autopxe",
    version=VERSION_FILE.read_text(),
    author="Étienne Noss",
    author_email="etienne.noss+pypi@gmail.com",
    description=__doc__,
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/etene/autopxe",
    packages=["autopxe"],
    install_requires=["pyroute2==0.5.14"],
    entry_points="""
    [console_scripts]
    autopxe=autopxe.__main__:main
    """,
    classifiers=[
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        # TODO
    ],
    package_data={"autopxe": ["py.typed", "VERSION"]},
    # TODO: config file ?
)
