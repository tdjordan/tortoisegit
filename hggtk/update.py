#
# update.py - TortoiseHg's dialog for updating repo
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import pygtk
pygtk.require("2.0")

import os
import sys
import gtk
from dialog import *
from mercurial.node import *
from mercurial import util, hg, ui
from mercurial.repo import RepoError
from shlib import shell_notify, set_tortoise_icon
from hglib import rootpath

class UpdateDialog(gtk.Window):
    """ Dialog to update Mercurial repo """
    def __init__(self, cwd='', rev=''):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        set_tortoise_icon(self, 'menucheckout.ico')
        self.cwd = cwd or os.getcwd()
        self.root = rootpath(self.cwd)
        self.rev = rev
        self.notify_func = None
        
        u = ui.ui()
        try:
            self.repo = hg.repository(u, path=self.root)
        except RepoError:
            return None

        # set dialog title
        title = "hg update - %s" % self.cwd
        self.set_title(title)

        self._create()
        
    def set_notify_func(self, func, *args):
        self.notify_func = func
        self.notify_args = args

    def _create(self):
        self.set_default_size(350, 120)

        # add toolbar with tooltips
        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()
        
        self._btn_update = self._toolbutton(
                gtk.STOCK_REVERT_TO_SAVED,
                'Update', 
                self._btn_update_clicked,
                tip='Update working directory to selected revision')
        sep = gtk.SeparatorToolItem()
        sep.set_expand(True)
        sep.set_draw(False)
        self._btn_close = self._toolbutton(gtk.STOCK_CLOSE, 'Close',
                self._close_clicked, tip='Close Application')
        tbuttons = [
                self._btn_update,
                sep,
                self._btn_close,
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        vbox = gtk.VBox()
        self.add(vbox)
        vbox.pack_start(self.tbar, False, False, 2)
        
        # repo parent revisions
        parentbox = gtk.HBox()
        lbl = gtk.Label("Parent revisions:")
        lbl.set_property("width-chars", 18)
        lbl.set_alignment(0, 0.5)
        self._parent_revs = gtk.Entry()
        self._parent_revs.set_sensitive(False)
        parentbox.pack_start(lbl, False, False)
        parentbox.pack_start(self._parent_revs, False, False)
        vbox.pack_start(parentbox, False, False, 2)

        # revision input
        revbox = gtk.HBox()
        lbl = gtk.Label("Update to revision:")
        lbl.set_property("width-chars", 18)
        lbl.set_alignment(0, 0.5)
        
        # revisions  combo box
        self._revlist = gtk.ListStore(str, str)
        self._revbox = gtk.ComboBoxEntry(self._revlist, 0)
        
        # add extra column to droplist for type of changeset
        cell = gtk.CellRendererText()
        self._revbox.pack_start(cell)
        self._revbox.add_attribute(cell, 'text', 1)
        self._rev_input = self._revbox.get_child()
        
        # setup buttons
        self._btn_rev_browse = gtk.Button("Browse...")
        self._btn_rev_browse.connect('clicked', self._btn_rev_clicked)
        revbox.pack_start(lbl, False, False)
        revbox.pack_start(self._revbox, False, False)
        revbox.pack_start(self._btn_rev_browse, False, False, 5)
        vbox.pack_start(revbox, False, False, 2)

        self._overwrite = gtk.CheckButton("Overwrite local changes")
        vbox.pack_end(self._overwrite, False, False, 10)
        
        # show them all
        self._refresh()

    def _close_clicked(self, toolbutton, data=None):
        self.destroy()

    def _toolbutton(self, stock, label, handler,
                    menu=None, userdata=None, tip=None):
        if menu:
            tbutton = gtk.MenuToolButton(stock)
            tbutton.set_menu(menu)
        else:
            tbutton = gtk.ToolButton(stock)
            
        tbutton.set_label(label)
        if tip:
            tbutton.set_tooltip(self.tips, tip)
        tbutton.connect('clicked', handler, userdata)
        return tbutton
        
    def _refresh(self):
        """ update display on dialog with recent repo data """
        try:
            # FIXME: force hg to refresh parents info
            del self.repo
            self.repo = hg.repository(ui.ui(), path=self.root)
        except RepoError:
            return None

        # populate parent rev data
        self._parents = [x.node() for x in self.repo.workingctx().parents()]
        self._parent_revs.set_text(", ".join([short(x) for x in self._parents]))

        # populate revision data        
        heads = self.repo.heads()
        tip = self.repo.changelog.node(nullrev+self.repo.changelog.count())
        self._revlist.clear()
        for i, node in enumerate(heads):
            status = "head %d" % (i+1)
            if node == tip:
                status += ", tip"
            self._revlist.append([short(node), "(%s)" %status])
        if self.rev:
            self._revbox.get_child().set_text(str(self.rev))
        else:
            self._revbox.set_active(0)

    def _btn_rev_clicked(self, button):
        """ select revision from history dialog """
        import histselect
        rev = histselect.select(self.root)
        if rev is not None:
            self._rev_input.set_text(rev)

    def _btn_update_clicked(self, button, data=None):
        self._do_update()
        
    def _do_update(self):
        rev = self._rev_input.get_text()
        overwrite = self._overwrite.get_active()
        
        if not rev:
            error_dialog(self, "Can't update", "please enter revision to update to")
            return
        
        response = question_dialog(self, "Really want to update?",
                                   "to revision %s" % rev)
        if response != gtk.RESPONSE_YES:
            return
            
        cmdline = ['hg', 'update', '-R', self.root, '--rev', rev, '--verbose']
        if overwrite: 
            cmdline.append('--clean')

        from hgcmd import CmdDialog
        dlg = CmdDialog(cmdline)
        dlg.run()
        dlg.hide()
        if self.notify_func:
            self.notify_func(self.notify_args)
        self._refresh()
        shell_notify([self.cwd])

def run(cwd='', rev='', **opts):
    dialog = UpdateDialog(cwd, rev)
    dialog.connect('destroy', gtk.main_quit)
    dialog.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['cwd'] = len(sys.argv) > 1 and sys.argv[1] or ''
    #opts['rev'] = 123
    run(**opts)
