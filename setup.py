from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='nameko-query',
    version='0.0.2',

    description='Query extension for nameko.',
    long_description=long_description,
    url='https://github.com/kundo/nameko-query',
    author='Kundo team',
    author_email='dev@kundo.se',
    license='MIT',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
    ],
    keywords='sample setuptools development',
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    install_requires=[],
    extras_require={
        'dev': ['check-manifest'],
        'test': ['coverage', 'pytest', 'tox'],
    },
    package_data={},
    data_files=[],
    entry_points={
        'console_scripts': [
            'sample=sample:main',
        ],
    },
)
