from setuptools import setup
import re


def get_property(prop):
    result = re.search(
        r'{}\s*=\s*[\'"]([^\'"]*)[\'"]'.format(prop),
        open("curifactory/__init__.py").read(),
    )
    return result.group(1)


with open("README.md", "r", encoding="utf-8") as infile:
    long_description = infile.read()


setup(
    name="curifactory",
    version=get_property("__version__"),
    description="An experiment workflow and organization tool",
    keywords=["research", "experiment", "workflow"],
    long_description_content_type="text/markdown",
    long_description=long_description,
    author="Nathan Martindale, Jason Hite, Scott L. Stewart, Mark Adams",
    author_email="curifactory-help@ornl.gov",
    python_requires=">=3.8",
    url="https://github.com/ORNL/curifactory",
    project_urls={
        "Documentation": "https://ornl.github.io/curifactory/latest/index.html"
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Science/Research",
    ],
    packages=["curifactory"],
    package_data={"curifactory": ["data/*", "data/.dockerignore"]},
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "experiment=curifactory.experiment:main",
            "curifactory=curifactory.project:main",
        ]
    },
    install_requires=[
        "numpy",
        "pandas",
        "ipynb-py-convert",
        "graphviz",
        "matplotlib",
        "psutil",
        "dataclasses",  # for compatibility with python 3.6
    ],
)
