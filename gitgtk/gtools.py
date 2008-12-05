# gtools.py - Graphical diff and status extension for Mercurial
#
# Copyright 2007 Brad Schick, brad at gmail . com
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.
# 
"""gtools extension provides graphical status and commit dialogs

The gtools extension provides gtk+ based graphical status, log,
and commit dialogs. Each dialogs provides a convenient way to see what 
has changed in a repository. Data is displayed in a list that can be
sorted, selected, and double-clicked to launch diff and editor tools.
Right-click context menus and toolbars provide operations like commit, 
add, view, delete, ignore, remove, revert, and refresh.

Files are diff'ed and edited in place whenever possible, so you can
make changes within external tools and save them directly back to the
working copy. To enable gtools:

   [extensions]
   hgext.gtools =

   [gtools]
   # external diff tool and options
   diffcmd = gdiff
   diffopts = -Nprc5
 
   # editor, if not specified [ui] editor is used
   editor = scite
 
   # set the fonts for the comments, diffs, and lists
   fontcomment = courier 10
   fontdiff = courier 10
   fontlist = courier 9

   # make the integrated diff window appear at the bottom or side
   diffbottom = False
 
The external diff tool is run as shown below. Unless specified otherwise,
file_rev1 and file_rev2 are the parent revision and the working copy 
respectively:

diffcmd diffopts file_rev1 file_rev2
"""

import mercurial.demandimport; mercurial.demandimport.disable()

import os
import sys

import pygtk
pygtk.require('2.0')
import gtk
import gobject
import pango

from mercurial.i18n import _
from mercurial.node import *
from mercurial import cmdutil, util, ui, hg, commands, patch

def gcommit(ui, repo, *pats, **opts):
    """graphical display for committing outstanding changes

    Displays a list of either all or specified files that can be committed
    and provides a entry field for the commit message. If a list of 
    files is omitted, all changes reported by "hg status" will be 
    committed.

    Each file in the list can be double-clicked to launch a diff or editor
    tool. Right-click context menus allow for single file operations.
    """
    from commit import GCommit
    dialog = GCommit(ui, repo, pats, opts, True)
    run(dialog)

def gstatus(ui, repo, *pats, **opts):
    """graphical display of changed files in the working directory

    Displays the status of files in the repository. If names are given, 
    only files that match are shown. Clean and ignored files are not 
    shown by default, but the can be added from within the dialog or the
    command-line (with -c, -i or -A)

    NOTE: status may appear to disagree with diff if permissions have
    changed or a merge has occurred. The standard diff format does not
    report permission changes and diff only reports changes relative
    to one merge parent.

    If one revision is given, it is used as the base revision.
    If two revisions are given, the difference between them is shown.

    The codes used to show the status of files are:
    M = modified
    A = added
    R = removed
    C = clean
    ! = deleted, but still tracked
    ? = not tracked
    I = ignored

    Each file in the list can be double-clicked to launch a diff or editor
    tool. Right-click context menus allow for single file operations.
    """
    from status import GStatus
    dialog = GStatus(ui, repo, pats, opts, True)
    run(dialog)

def glog(ui, repo, *pats, **opts):
    """display revision history of entire repository or files

    Displays the revision history of the specified files or the entire
    project.

    File history is shown without following rename or copy history of
    files.  Use -f/--follow with a file name to follow history across
    renames and copies. --follow without a file name will only show
    ancestors or descendants of the starting revision. --follow-first
    only follows the first parent of merge revisions.

    If no revision range is specified, the default is tip:0 unless
    --follow is set, in which case the working directory parent is
    used as the starting revision.

    Each log entry in the list can be double-clicked to launch a status
    view of that revision. Diff options like --git are passed to the 
    status view when a log entry is activated.
    """
    from history import GLog
    dialog = GLog(ui, repo, pats, opts, True)
    run(dialog)

def run(dialog):
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    dialog.display()
    gtk.main()
    gtk.gdk.threads_leave()


cmdtable = {
'gcommit|gci':
(gcommit,
 [('A', 'addremove', None, _('skip prompt for marking new/missing files as added/removed')),
  ('d', 'date', '', _('record datecode as commit date')),
  ('u', 'user', '', _('record user as commiter')),
  ('m', 'message', '', _('use <text> as commit message')),
  ('l', 'logfile', '', _('read commit message from <file>')),
  ('g', 'git', None, _('use git extended diff format')),
  ('c', 'check', False, _('automatically check commitable files'))] + commands.walkopts,
 _('hg gcommit [OPTION]... [FILE]...')),
'gstatus|gst':
(gstatus,
 [('A', 'all', None, _('show status of all files')),
  ('m', 'modified', None, _('show only modified files')),
  ('a', 'added', None, _('show only added files')),
  ('r', 'removed', None, _('show only removed files')),
  ('d', 'deleted', None, _('show only deleted (but tracked) files')),
  ('c', 'clean', None, _('show only files without changes')),
  ('u', 'unknown', None, _('show only unknown (not tracked) files')),
  ('i', 'ignored', None, _('show only ignored files')),
  ('',  'rev', [], _('show difference from revision')),
  ('g', 'git', None, _('use git extended diff format')),
  ('c', 'check', False, _('automatically check displayed files'))] + commands.walkopts,
 _('hg gstat [OPTION]... [FILE]...')),
'glog|ghistory':
(glog,
 [('f', 'follow', None,
   _('follow changeset history, or file history across copies and renames')),
  ('', 'follow-first', None,
   _('only follow the first parent of merge changesets')),
  ('d', 'date', '', _('show revs matching date spec')),
  ('C', 'copies', None, _('show copied files')),
  ('k', 'keyword', [], _('do case-insensitive search for a keyword')),
  ('l', 'limit', '', _('limit number of changes displayed')),
  ('r', 'rev', [], _('show the specified revision or range')),
  ('', 'removed', None, _('include revs where files were removed')),
  ('M', 'no-merges', None, _('do not show merges')),
  ('m', 'only-merges', None, _('show only merges')),
  ('P', 'prune', [], _('do not display revision or any of its ancestors')),
  ('g', 'git', None, _('use git extended diff format'))] + commands.walkopts,
_('hg glog [OPTION]... [FILE]')),
}

def findrepo():
    p = os.getcwd()
    while not os.path.isdir(os.path.join(p, '.hg')):
        oldp, p = p, os.path.dirname(p)
        if p == oldp:
            return None
    return p

if __name__ == '__main__':
    u = ui.ui()
    u.updateopts(debug=False, traceback=False)
    repo = hg.repository(u, findrepo())
    gstatus(u, repo, all=False, clean=False, ignored=False, modified=True,
           added=True, removed=True, deleted=True, unknown=True, rev=[],
           exclude=[], include=[], debug=True,
           verbose=True )
#   logparams = {'follow_first': None, 'style': '', 'include': [], 'verbose': True,
#               'only_merges': None, 'keyword': [], 'rev': [], 'copies': None, 'template': '',
#               'patch': None, 'limit': 20, 'no_merges': None, 'exclude': [], 'date': '',
#               'follow': None, 'removed': None, 'prune': [], 'verbose':True }
#    glog(u, repo, **logparams )

