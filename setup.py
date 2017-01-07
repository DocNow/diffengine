from setuptools import setup

requirements = open("requirements.txt").read().split()

setup(
    name="diffengine",
    version="0.0.1",
    author="Ed Summers",
    author_email="ehs@pobox.com",
    py_modules=["diffengine"],
    scripts=["bin/diffengine"],
    description="Tweet changes to stories in RSS feeds",
    requirements=requirements,
    setup_requires=["pytest-runner"],
    tests_require=["pytest"]
)
