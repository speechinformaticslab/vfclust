#!/usr/bin/env python
# -*- coding: ascii -*-
"""
To setup (from terminal):
$ cd /path/to/vfclust/download
$ python setup.py install

>> import vfclust

For arguments and default values, see the README.md file.
"""
import sys

__author__ = 'Thomas Christie (tchristie@umn.edu), James Ryan, Serguei Pakhomov'
__copyright__ = 'Copyright (c) 2013-2014 Serguei Pakhomov'
__license__ = 'Apache License, Version 2.0'
__vcs_id__ = '$Id$'
__version__ = '0.1.0'

#if it's run as a script or imported within python, this happens
if __name__ == 'vfclust':
    from vfclust import *
