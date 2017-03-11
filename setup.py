import sys
if sys.version_info < (3,0):
    sys.exit('Sorry, diffengine runs on Python 3')


from setuptools import setup, find_packages

reqs = open("requirements.txt").read().split()

# hack until htmldiff is updated to work with python3 on pypi
htmldiff = "https://github.com/edsu/htmldiff/tarball/master#egg=htmldiff-0.2"
reqs.remove(htmldiff)
reqs.append("htmldiff==0.2")
deps = [htmldiff]
version = "0.0.38"

if __name__ == "__main__":
    setup(
        name="diffengine",
        version=version,
        author="Ed Summers",
        author_email="ehs@pobox.com",
        packages=find_packages(exclude=['test_diffengine']),
        description="Tweet changes to stories in RSS feeds",
        install_requires=reqs,
        dependency_links=deps,
        setup_data={'diffengine': ['diffengine/diff.html']},
        setup_requires=["pytest-runner"],
        tests_require=["pytest"],
        package_data={"diffengine": ["diff.html"]},
        entry_points={
            'console_scripts': [
                'diffengine=diffengine:main'
            ],
        },
    )
