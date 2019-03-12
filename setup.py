#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

from pkg_resources import parse_requirements

from setuptools import setup, find_packages

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

# parse_requirements() returns generator of pip.req.InstallRequirement objects
# TODO:
# requirements = [str(r) for r in parse_requirements(open('requirements.txt').read())]

setup_requirements = ['pytest-runner', ]

test_requirements = ['pytest', ]

setup(
    author="Gennadii Donchyts",
    author_email='gennadiy.donchyts@gmail.com',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    description="Hydro Engine is a service and a command-line tool to query static and dynamic hydrographic data derived from Earth Observations",
    entry_points={
        'console_scripts': [
            'hydroengine-service=hydroengine_service.cli:main',
        ],
    },
    install_requires=[],
    license="MIT license",
    long_description=readme + '\n\n' + history,
    include_package_data=True,
    keywords='hydroengine_service',
    name='hydroengine_service',
    packages=find_packages(include=['hydroengine_service']),
    setup_requires=setup_requirements,
    test_suite='tests',
    tests_require=test_requirements,
    url='https://github.com/gena/hydroengine_service',
    version='0.1.0',
    zip_safe=False,
)
