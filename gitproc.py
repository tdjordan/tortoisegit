#
# front-end for TortoiseHg dialogs
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import os
import sys
from tortoisegit.tgitutil import get_prog_root

# always use git exe installed with TortoiseHg
tgitdir = get_prog_root()
try:
    os.environ['PATH'] = os.path.pathsep.join([tgitdir, os.environ['PATH']])
except KeyError:
    os.environ['PATH'] = tgitdir

if not sys.stdin.isatty():
    try:
        import win32traceutil
    except ImportError:
        pass
    except pywintypes.error:
        pass

# Map gitproc commands to dialog modules in gitgtk/
from gitgtk import commit, status, addremove, tagadd, tags, history, merge
from gitgtk import diff, revisions, update, serve, clone, synch, gitcmd, about
from gitgtk import recovery, tgitconfig, datamine
_dialogs = { 'commit' : commit,    'status' : status,    'revert' : status,
             'add'    : addremove, 'remove' : addremove, 'tag'    : tagadd,
             'tags'   : tags,      'log'    : history,   'history': history,
             'diff'   : diff,      'merge'  : merge,     'tip'    : revisions,
             'parents': revisions, 'heads'  : revisions, 'update' : update,
             'clone'  : clone,     'serve'  : serve,     'synch'  : synch,
             'about'  : about,     'config' : tgitconfig, 'recovery': recovery,
             'datamine': datamine }

def get_list_from_file(filename):
    fd = open(filename, "r")
    lines = [ x.replace("\n", "") for x in fd.readlines() ]
    fd.close()
    return lines

def get_option(args):
    import getopt
    long_opt_list = ('command=', 'exepath=', 'listfile=', 'root=', 'cwd=',
            'deletelistfile', 'nogui')
    opts, args = getopt.getopt(args, "c:e:l:dR:", long_opt_list)
    # Set default options
    options = {}
    options['gitcmd'] = 'help'
    options['cwd'] = os.getcwd()
    options['files'] = []
    options['gui'] = True
    listfile = None
    delfile = False
    
    for o, a in opts:
        if o in ("-c", "--command"):
            options['gitcmd'] = a
        elif o in ("-l", "--listfile"):
            listfile = a
        elif o in ("-d", "--deletelistfile"):
            delfile = True
        elif o in ("--nogui"):
            options['gui'] = False
        elif o in ("-R", "--root"):
            options['root'] = a
        elif o in ("--cwd"):
            options['cwd'] = a

    if listfile:
        options['files'] = get_list_from_file(listfile)
        if delfile:
            os.unlink(listfile)

    return (options, args)

def parse(args):
    option, args = get_option(args)
    
    cmdline = ['git', option['gitcmd']] 
    if 'root' in option:
        cmdline.append('--repository')
        cmdline.append(option['root'])
    cmdline.extend(args)
    cmdline.extend(option['files'])
    option['cmdline'] = cmdline

    global _dialogs
    dialog = _dialogs.get(option['gitcmd'], gitcmd)
    dialog.run(**option)


def run_trapped(args):
    try:
        dlg = parse(sys.argv[1:])
    except:
        import traceback
        from gitgtk.dialog import error_dialog
        tr = traceback.format_exc()
        print tr
        error_dialog(None, "Error executing gitproc", tr)

if __name__=='__main__':
    #dlg = parse(['-c', 'help', '--', '-v'])
    #dlg = parse(['-c', 'log', '--root', 'c:\git\h1', '--', '-l1'])
    #dlg = parse(['-c', 'status', '--root', 'c:\hg\h1', ])
    #dlg = parse(['-c', 'add', '--root', 'c:\hg\h1', '--listfile', 'c:\\hg\\h1\\f1', '--notify'])
    #dlg = parse(['-c', 'rollback', '--root', 'c:\\hg\\h1'])
    print "gitproc sys.argv =", sys.argv
    dlg = run_trapped(sys.argv[1:])
