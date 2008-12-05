#
# merge.py - TortoiseHg's dialog for merging revisions
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import pygtk
pygtk.require("2.0")

import sys
import gtk
from dialog import *
from mercurial.node import *
from mercurial import util, hg, ui
from hgcmd import CmdDialog
from shlib import set_tortoise_icon, shell_notify
from mercurial.repo import RepoError
import histselect

class MergeDialog(gtk.Window):
    """ Dialog to merge revisions of a Mercurial repo """
    def __init__(self, root='', cwd='', rev=''):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        set_tortoise_icon(self, 'menumerge.ico')
        # set dialog title
        title = "hg merge"
        if root: title += " - %s" % root
        self.set_title(title)

        self.root = root
        self.cwd = cwd or root
        self.rev = rev
        self.repo = None
        self.notify_func = None
        self._create()

    def set_notify_func(self, func, *args):
        self.notify_func = func
        self.notify_args = args

    def _create(self):
        self.set_default_size(350, 120)
        
        # add toolbar with tooltips
        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()
        
        self._btn_merge = self._toolbutton(
                gtk.STOCK_CONNECT,
                'merge', 
                self._btn_merge_clicked,
                menu=self._merge_menu(),
                tip='Merge working revision with selected revision')
        self._btn_unmerge = self._toolbutton(
                gtk.STOCK_DISCONNECT,
                'unmerge', 
                self._btn_unmerge_clicked,
                tip='Undo merging and return working directory to'
                    ' one of it parent revision')
        sep = gtk.SeparatorToolItem()
        sep.set_expand(True)
        sep.set_draw(False)
        self._btn_close = self._toolbutton(gtk.STOCK_CLOSE, 'Close',
                self._close_clicked, tip='Close Application')
        tbuttons = [
                self._btn_merge,
                gtk.SeparatorToolItem(),
                self._btn_unmerge,
                sep,
                self._btn_close
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        vbox = gtk.VBox()
        self.add(vbox)
        vbox.pack_start(self.tbar, False, False, 2)
        
        # repo parent revisions
        parentbox = gtk.HBox()
        lbl = gtk.Label("Parent revision(s):")
        lbl.set_property("width-chars", 18)
        lbl.set_alignment(0, 0.5)
        self._parent_revs = gtk.Entry()
        parentbox.pack_start(lbl, False, False)
        parentbox.pack_start(self._parent_revs, True, True)
        vbox.pack_start(parentbox, False, False, 2)

        # revision input
        revbox = gtk.HBox()
        self._rev_lbl = gtk.Label("Merge with revision:")
        self._rev_lbl.set_property("width-chars", 18)
        self._rev_lbl.set_alignment(0, 0.5)
        
        # revisions  combo box
        self._revlist = gtk.ListStore(str, str)
        self._revbox = gtk.ComboBoxEntry(self._revlist, 0)
        
        # add extra column to droplist for type of changeset
        cell = gtk.CellRendererText()
        self._revbox.pack_start(cell)
        self._revbox.add_attribute(cell, 'text', 1)
        self._rev_input = self._revbox.get_child()

        self._btn_rev_browse = gtk.Button("Browse...")
        self._btn_rev_browse.connect('clicked', self._btn_rev_clicked)
        revbox.pack_start(self._rev_lbl, False, False)
        revbox.pack_start(self._revbox, False, False)
        revbox.pack_start(self._btn_rev_browse, False, False, 5)
        vbox.pack_start(revbox, False, False, 2)
        
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
        self._parent_revs.set_sensitive(True)
        self._parent_revs.set_text(", ".join([short(x) for x in self._parents]))
        self._parent_revs.set_sensitive(False)
        
        # condition some widgets per state of working directory
        is_merged = len(self._parents) > 1
        if is_merged:
            self._btn_merge.set_sensitive(False)
            self._btn_unmerge.set_sensitive(True)
            self._rev_lbl.set_text("Unmerge to revision:")
            self._btn_rev_browse.set_sensitive(False)
        else:
            self._btn_merge.set_sensitive(True)
            self._btn_unmerge.set_sensitive(False)
            self._rev_lbl.set_text("Merge with revision:")
            self._btn_rev_browse.set_sensitive(True)
            
        # populate revision data        
        heads = self.repo.heads()
        tip = self.repo.changelog.node(nullrev+self.repo.changelog.count())
        self._revlist.clear()
        self._rev_input.set_text("")
        for i, node in enumerate(heads):
            if node in self._parents and not is_merged:
                continue
            
            status = "head %d" % (i+1)
            if node == tip:
                status += ", tip"
            
            self._revlist.append([short(node), "(%s)" %status])
            self._rev_input.set_text(short(node))

        if self.rev:
            self._rev_input.set_text(str(self.rev))
        
    def _merge_menu(self):
        menu = gtk.Menu()
        
        self._chbox_force = gtk.CheckMenuItem("Allow merge with uncommited changes")
        menu.append(self._chbox_force)
        
        menu.show_all()
        return menu
        
    def _btn_rev_clicked(self, button):
        """ select revision from history dialog """
        rev = histselect.select(self.root)
        if rev is not None:
            self._rev_input.set_text(rev)

    def _btn_merge_clicked(self, toolbutton, data=None):
        self._do_merge()
        
    def _btn_unmerge_clicked(self, toolbutton, data=None):
        self._do_unmerge()
        
    def _do_unmerge(self):
        rev = self._rev_input.get_text()
        
        if not rev:
            error_dialog(self, "Can't unmerge", "please select revision to unmerge")
            return
        
        response = question_dialog(self, "Undo merge",
                                   "and checkout revision %s?" % rev)
        if response != gtk.RESPONSE_YES:
            return

        cmdline = ['hg', 'update', '-R', self.root, '--rev', rev, '--clean', '--verbose']
        dlg = CmdDialog(cmdline)
        dlg.run()
        dlg.hide()
        if self.notify_func:
            self.notify_func(self.notify_args)
        shell_notify([self.cwd])
        self._refresh()
        
    def _do_merge(self):
        rev = self._rev_input.get_text()
        force = self._chbox_force.get_active()
        
        if not rev:
            error_dialog(self, "Can't merge", "please enter revision to merge")
            return
        
        response = question_dialog(self, "Really want to merge?",
                                   "with revision %s" % rev)
        if response != gtk.RESPONSE_YES:
            return

        cmdline = ['hg', 'merge', '-R', self.root, '--rev', rev]
        if force:
            cmdline.append("--force")

        dlg = CmdDialog(cmdline)
        dlg.run()
        dlg.hide()
        shell_notify([self.cwd])
        if self.notify_func:
            self.notify_func(self.notify_args)
        self._refresh()

def run(root='', cwd='', rev='', **opts):
    dialog = MergeDialog(root, cwd, rev)
    dialog.connect('destroy', gtk.main_quit)
    dialog.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or ''
    run(**opts)
