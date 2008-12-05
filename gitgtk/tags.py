#
# tags dialog for TortoiseHg
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

try:
    import pygtk
    pygtk.require("2.0")
except:
    pass

import sys
import gtk
import gobject
from mercurial import hg, ui, cmdutil, util, node
from mercurial.repo import RepoError
from mercurial.i18n import _

def get_tag_list(path):
    root = path
    u = ui.ui()
    try:
        repo = hg.repository(u, path=root)
    except RepoError:
        return None

    l = repo.tagslist()
    l.reverse()
    hexfunc = node.hex
    taglist = []
    for t, n in l:
        try:
            hn = hexfunc(n)
            r, c = repo.changelog.rev(n), hexfunc(n)
        except revlog.LookupError:
            r, c = "?", hn

        taglist.append((t, r, c))

    return taglist

class TagsDialog(gtk.Dialog):
    """ TortoiseHg dialog to add/remove files """
    def __init__(self, root='', select=False):
        if select:
            buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
                      gtk.STOCK_OK, gtk.RESPONSE_ACCEPT)
        else:
            buttons = (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        super(TagsDialog, self).__init__(flags=gtk.DIALOG_MODAL, 
                                         buttons=buttons)

        self.root = root

        # set dialog title
        title = "hg tags "
        if root: title += " - %s" % root
        self.set_title(title)

        # build dialog
        self.set_default_size(500, 300)
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self._treeview = gtk.TreeView()
        self._treeview.connect("cursor-changed", self._get_selected_tag)
        scrolledwindow.add(self._treeview)
        self._create_file_view()
        self.vbox.pack_start(scrolledwindow, True, True)
        self.vbox.show_all()
        
        # Generate status output
        self._get_tags()

    def _create_file_view(self):
        self._file_store = gtk.ListStore(
                gobject.TYPE_STRING,    # tag name
                gobject.TYPE_STRING,    # revision
                gobject.TYPE_STRING,    # cset id
            )
        self._treeview.set_model(self._file_store)
        self._treeview.append_column(gtk.TreeViewColumn(_('Tag'),
                                     gtk.CellRendererText(), text=0))
        self._treeview.append_column(gtk.TreeViewColumn(_('Revision'),
                                     gtk.CellRendererText(), text=1))
        self._treeview.append_column(gtk.TreeViewColumn(_('ID'),
                                     gtk.CellRendererText(), text=2))

    def _get_tags(self):
        """ Generate 'hg status' output. """        
        tags = get_tag_list(self.root)

        for t, r, c in tags:
            self._file_store.append([ t, r, c ])
        self._treeview.expand_all()
        
    def _get_selected_tag(self, tv):
        treeselection = tv.get_selection()
        mode = treeselection.get_mode()
        (model, iter) = treeselection.get_selected()
        self.selected = model.get_value(iter, 0)

def run(root='', **opts):
    dialog = TagsDialog(root=root)
    
    # the dialog maybe called by another window/dialog, so we only
    # enable the close dialog handler if dialog is run as mainapp
    dialog.connect('response', gtk.main_quit)

    dialog.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()
    
def select(root=''):
    dialog = TagsDialog(root=root, select=True)
    resp = dialog.run()
    rev = None
    if resp == gtk.RESPONSE_ACCEPT:
        rev = dialog.selected
    dialog.hide()
    return rev
    
if __name__ == "__main__":
    run(**{})
