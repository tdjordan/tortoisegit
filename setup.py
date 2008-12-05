# setup.py
# A distutils setup script to register TortoiseGit COM server

# To build stand-alone package, use 'python setup.py py2exe' then use
# InnoSetup to build the installer.  By default, the installer will be
# created as dist\Output\setup.exe.

import time
import sys
import os

# non-Win32 platforms doesn't require setup
if os.name != 'nt':
    sys.stderr.write("abort: %s is for Win32 platforms only" % sys.argv[0])
    sys.exit(1)

# ModuleFinder can't handle runtime changes to __path__, but win32com uses them

try:
    # if this doesn't work, try import modulefinder
    import py2exe.mf as modulefinder
    import win32com
    for p in win32com.__path__[1:]:
        modulefinder.AddPackagePath("win32com", p)
    for extra in ["win32com.shell"]: #,"win32com.mapi"
        __import__(extra)
        m = sys.modules[extra]
        for p in m.__path__[1:]:
            modulefinder.AddPackagePath(extra, p)
except ImportError:
    # no build path setup, no worries.
    pass

from distutils.core import setup
import py2exe

_data_files = []
extra = {}

if 'py2exe' in sys.argv:
    _data_files = [(root, [os.path.join(root, file_) for file_ in files])
                        for root, dirs, files in os.walk('icons')]
    extra['windows'] = [
            {"script":"gitproc.py",
                        "icon_resources": [(1, "icons/tortoise/git.ico")]},
            {"script":"tracelog.py",
                        "icon_resources": [(1, "icons/tortoise/python.ico")]}
            ]
    extra['com_server'] = ["tortoisegit"]
    extra['console'] = ["contrib/git", "contrib/gitgtk"]

opts = {
   "py2exe" : {
       # Don't pull in all this MFC stuff used by the makepy UI.
       "excludes" : "pywin,pywin.dialogs,pywin.dialogs.list",

       # add library files to support PyGtk-based dialogs/windows
       # Note:
       #    after py2exe build, copy GTK's etc and lib directories into
       #    the dist directory created by py2exe.
       #    also needed is the GTK's share/themes (as dist/share/themes), 
       #    for dialogs to display in MS-Windows XP theme.
       "includes" : "dbhash,pango,atk,pangocairo,cairo,gobject," + \
                    ",".join(gitextmods),
   }
}

version = ''

import tortoisegit.version
tortoisegit.version.remember_version(version)

setup(name="TortoiseGit",
        version=tortoisegit.version.get_version(),
        author='Scott Chacon',
        author_email='scahcon@gmail.com',
        url='http://github.com/schacon/tortoisegit',
        description='Windows shell extension for Git VCS',
        license='GNU GPL2',
        packages=['tortoisegit', 'gitgtk', 'gitgtk.vis', 'gitgtk.iniparse'],
        data_files = _data_files,
        options=opts,
        **extra
    )
