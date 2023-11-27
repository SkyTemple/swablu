__version__ = '0.0.1'

from setuptools import setup, find_packages

# README read-in
from os import path
this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()
# END README read-in


setup(
    name='swablu',
    version=__version__,
    packages=find_packages(),
    description='A Discord Bot for assigning a role to SkyTemple users and managing hacks '
                '(with a OAuth authenticated web interface for managing them).',
    long_description=long_description,
    long_description_content_type='text/x-rst',
    install_requires=[
        'discord.py>=1.5.1',
        'requests-oauthlib>=1.3.0',
        'tornado>=6.1',
        'mysql-connector-python>=8.0.20',
        'skytemple-dtef>=1.1.5',
        'skytemple-files==1.6.1',
        'pycairo'
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9'
    ]
)
