#
# revtree.py - a revision tree widget class for TortoiseHg
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import pygtk
pygtk.require("2.0")

import gtk

class RevisionTree(gtk.ScrolledWindow):
    def __init__(self, log=''):
        super(gtk.ScrolledWindow, self).__init__()
        self.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.treeview = gtk.TreeView()
        self._create_treestore()
        self.add(self.treeview)
        if log: self.set_history(log)
        
        self.show_all()
        
    def _create_treestore(self):
        """ create history display """
        
        # add treeview to list change files
        self.model = gtk.TreeStore(str, str)
        self.treeview.connect("cursor-changed", self._cursor_changed)
        #self.treeview.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        self.treeview.set_headers_visible(False)
        self.treeview.set_model(self.model)
        
        cell = gtk.CellRendererText()
        
        column = gtk.TreeViewColumn()
        column.pack_start(cell, expand=True)
        column.add_attribute(cell, "text", 0)
        self.treeview.append_column(column)

        column = gtk.TreeViewColumn()
        column.pack_start(cell, expand=True)
        column.add_attribute(cell, "text", 1)
        self.treeview.append_column(column)

    def set_history(self, log):
        self.history = self._parse_history(log)
        self._update_tree()
        
    def _parse_history(self, log):
        """ conver hg log output into list of revision structures """
        import re
        histlist = []
        cs = {}
        for x in log.splitlines():
            if x == "":
                if cs:
                    histlist.append(cs)
                    cs = {}
            else:
                name, value = re.split(':\s+', x, 1)
                if name not in cs:
                    cs[name] = []
                cs[name].append(value)
        if cs:
            histlist.append(cs)
            
        return histlist
    
    def _update_tree(self):
        # clear changed files display
        self.model.clear()

        # display history
        for cs in self.history:
            titer = self.model.append(None, [ 'changeset:', cs['changeset'][0] ])
            for fld in ('parent', 'tag', 'branch', 'user', 'date', 'summary'):
                if fld not in cs:
                    continue
                vlist = type(cs[fld])==type([]) and cs[fld] or [cs[fld]]
                for v in vlist:
                    self.model.append(titer, [ fld + ":", v ])

        self.treeview.expand_all()

    def _cursor_changed(self, tv):
        (model, iter) = tv.get_selection().get_selected()
        path = self.model.get_path(iter)
        cs = self.history[path[0]]['changeset'][0]
        rev, id = cs.split(':')
        self.selected = (rev, id)

    def get_revision(self, index):
        import string
        try:
            cs = self.history[index]
            revpair = cs['changeset'][0]
            revnum, id = revpair.split(':')
            return string.atoi(revnum), id
        except:
            return None

# sample hg log output for testing purpose
testlog ="""\
changeset:   218:72299521b0e9
tag:         tip
user:        TK Soh <teekaysoh@yahoo.com>
date:        Sun Jun 17 12:33:58 2007 -0500
summary:     hgproc: use new gtk dialog for merge command
"""

# simple dialog for testing RevisionTree class
class TestDialog(gtk.Dialog):
    def __init__(self, root='', log=''):
        """ Initialize the Dialog """
        buttons = (gtk.STOCK_OK, gtk.RESPONSE_ACCEPT)
        super(TestDialog, self).__init__(flags=gtk.DIALOG_MODAL, 
                                         buttons=buttons)

        self.set_default_size(500, 300)

        self.root = root
        self.revtree = RevisionTree()
        self.vbox.pack_start(self.revtree)
        self.vbox.show_all()
        self.revtree.set_history(testlog)

def test(root=''):
    dialog = TestDialog(root=root)
    dialog.run()
    return 

if __name__ == "__main__":
    test()
