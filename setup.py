import sys
if sys.version_info < (3,0):
    sys.exit('Sorry, diffengine runs on Python 3')

from setuptools import setup

reqs = open("requirements.txt").read().split()

# hack until htmldiff is updated on pypi
htmldiff = "https://github.com/edsu/htmldiff/tarball/master#egg=htmldiff-0.2"
reqs.remove(htmldiff)
reqs.append("htmldiff==0.2")
deps = [htmldiff]

setup(
    name="diffengine",
    version="0.0.9",
    author="Ed Summers",
    author_email="ehs@pobox.com",
    py_modules=["diffengine"],
    scripts=["bin/diffengine"],
    description="Tweet changes to stories in RSS feeds",
    install_requires=reqs,
    dependency_links=deps,
    setup_requires=["pytest-runner"],
    tests_require=["pytest"]
)
