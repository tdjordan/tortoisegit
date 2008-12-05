#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""Difference window.

This module contains the code to manage the diff window which shows
the changes made between two revisions on a branch.
"""

__copyright__ = "Copyright © 2005 Canonical Ltd."
__author__    = "Scott James Remnant <scott@ubuntu.com>"

import gtk
import pango
import sys
from mercurial import hg, ui, cmdutil, util, patch
from mercurial.i18n import _
from shlib import set_tortoise_icon

class DiffWindow(gtk.Window):
    """Diff window.

    This object represents and manages a single window containing the
    differences between two revisions on a branch.
    """

    def __init__(self):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        set_tortoise_icon(self, 'menudiff.ico')
        self.set_border_width(0)
        self.set_title("diff")

        # Use two thirds of the screen by default
        screen = self.get_screen()
        monitor = screen.get_monitor_geometry(0)
        width = int(monitor.width * 0.66)
        height = int(monitor.height * 0.66)
        self.set_default_size(width, height)

        self.construct()

    def construct(self):
        """Construct the window contents."""
        # The   window  consists  of   a  pane   containing:  the
        # hierarchical list  of files on  the left, and  the diff
        # for the currently selected file on the right.
        pane = gtk.HPaned()
        self.add(pane)
        pane.show()

        # The file hierarchy: a scrollable treeview
        scrollwin = gtk.ScrolledWindow()
        scrollwin.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        scrollwin.set_shadow_type(gtk.SHADOW_IN)
        pane.pack1(scrollwin)
        scrollwin.show()

        self.model = gtk.TreeStore(str, str)
        self.treeview = gtk.TreeView(self.model)
        self.treeview.set_headers_visible(False)
        self.treeview.set_search_column(1)
        self.treeview.connect("cursor-changed", self._treeview_cursor_cb)
        scrollwin.add(self.treeview)
        self.treeview.show()

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 20)
        column = gtk.TreeViewColumn()
        column.pack_start(cell, expand=True)
        column.add_attribute(cell, "text", 0)
        self.treeview.append_column(column)

        # The diffs of the  selected file: a scrollable source or
        # text view
        scrollwin = gtk.ScrolledWindow()
        scrollwin.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrollwin.set_shadow_type(gtk.SHADOW_IN)
        pane.pack2(scrollwin)
        scrollwin.show()

        try:
            import gtksourceview
            self.buffer = gtksourceview.SourceBuffer()
            slm = gtksourceview.SourceLanguagesManager()
            gsl = slm.get_language_from_mime_type("text/x-patch")
            self.buffer.set_language(gsl)
            self.buffer.set_highlight(True)

            sourceview = gtksourceview.SourceView(self.buffer)
        except ImportError:
            self.buffer = gtk.TextBuffer()
            sourceview = gtk.TextView(self.buffer)

        sourceview.set_editable(False)
        sourceview.modify_font(pango.FontDescription("Monospace"))
        scrollwin.add(sourceview)
        sourceview.show()

    def set_diff(self, root='', files=[], description=''):
        """Set the differences showed by this window.

        Compares the two trees and populates the window with the
        differences.
        """
        self.root = root
        self.files = files
        
        # open Hg repo
        self.ui = ui.ui()
        try:
            self.repo = hg.repository(self.ui, path=self.root)
        except hg.RepoError:
            return None

        self.files, matchfn, anypats = cmdutil.matchpats(self.repo, self.files)
        modified, added, removed = self.repo.status(files=self.files)[0:3]

        self.model.clear()
        self.model.append(None, [ "Complete Diff", "" ])

        if len(added):
            titer = self.model.append(None, [ "Added", None ])
            for path in added:
                self.model.append(titer, [ path, path ])

        if len(removed):
            titer = self.model.append(None, [ "Removed", None ])
            for path in removed:
                self.model.append(titer, [ path, path ])

        if len(modified):
            titer = self.model.append(None, [ "Modified", None ])
            for path in modified:
                self.model.append(titer, [ path, path ])

        self.treeview.expand_all()
        self.set_title("TortoseHg diff - " + description)

    def set_file(self, file_path):
        tv_path = None
        for data in self.model:
            for child in data.iterchildren():
                if child[0] == file_path or child[1] == file_path:
                    tv_path = child.path
                    break
        if tv_path is None:
            raise NoSuchFile(file_path)
        self.treeview.set_cursor(tv_path)
        self.treeview.scroll_to_cell(tv_path)

    def _treeview_cursor_cb(self, *args):
        """Callback for when the treeview cursor changes."""
        (path, col) = self.treeview.get_cursor()
        specific_files = [ self.model[path][1] ]
        if specific_files == [ None ]:
            return
        elif specific_files == [ "" ]:
            specific_files = self.files

        diff = self._get_hg_diff(specific_files)
        self.buffer.set_text(diff.decode(sys.getdefaultencoding(), 'replace'))

    def _get_hg_diff(self, files):
        self.repo.ui.pushbuffer()
        patch.diff(self.repo, files=files)
        difflines = self.repo.ui.popbuffer()
        return difflines

    def _set_as_window(self):
        self.connect("destroy", gtk.main_quit)

    def _set_as_dialog(self, modal=False):
        self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
        self.set_modal(modal)

def run(root='', files=[], **opts):
    diff = DiffWindow()
    diff.set_diff(root, files)
    diff._set_as_window()
    diff.show()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    run(**{})
