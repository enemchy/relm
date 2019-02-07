# -*- coding: utf-8 -*-

from distutils.core import setup

install_requires = [
    'gitpython == 2.1.7',
    'prettytable == 0.7.2',
    'requests == 2.20.0',
    'configparser == 3.5.0',
    'future == 0.16.0'
]



setup(
    name='relm',
    version='0.0.1.1',
    packages=['relm'],
    url='',
    license='Apache License 2.0',
    author='enemchy',
    author_email='dzenkir@gmail.com',
    description='Release Management Tool',
    install_requires=install_requires,
    entry_points="""
        [console_scripts]
        relm=relm.app:main
        """
)
