#
# Add/Remove dialog for TortoiseHg
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

try:
    import pygtk
    pygtk.require("2.0")
except:
    pass

import gtk
import gobject
from mercurial import ui, util, hg
from mercurial.i18n import _
from status import GStatus

def run(hgcmd='add', root='', cwd='', files=[], **opts):
    u = ui.ui()
    u.updateopts(debug=False, traceback=False)
    repo = hg.repository(u, path=root)

    cmdoptions = {
        'all':False, 'clean':False, 'ignored':False, 'modified':False,
        'added':True, 'removed':True, 'deleted':True, 'unknown':False, 'rev':[],
        'exclude':[], 'include':[], 'debug':True,'verbose':True
    }
    
    if hgcmd == 'add':
        cmdoptions['unknown'] = True        
    elif hgcmd == 'remove':
        cmdoptions['clean'] = True
    else:
        raise "Invalid command '%s'" % hgcmd
        
    dialog = GStatus(u, repo, cwd, files, cmdoptions, True)

    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    dialog.display()
    gtk.main()
    gtk.gdk.threads_leave()
    
if __name__ == "__main__":
    import sys
    opts = {}
    opts['hgcmd'] = 'adda'
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or ''
    run(**opts)
