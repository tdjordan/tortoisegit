#
# hgignore.py - TortoiseHg's dialog for editing .hgignore
#
# Copyright (C) 2008 Steve Borho <steve@borho.org>
#

import os
import gobject
import gtk
import pango
import string
from dialog import *
import hglib
from mercurial import hg, ui

class HgIgnoreDialog(gtk.Window):
    """ Edit a reposiory .hgignore file """
    def __init__(self, root=''):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        self.root = root
        self.set_title('Ignore mask for ' + os.path.basename(root))
        self.set_default_size(630, 400)

        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()

        sep = gtk.SeparatorToolItem()
        sep.set_expand(True)
        sep.set_draw(False)
        self._btn_close = self._toolbutton(gtk.STOCK_CLOSE, 'Close',
                self._close_clicked, 'Close Window')

        tbuttons = [
                self._toolbutton(gtk.STOCK_REFRESH,
                    'Refresh',
                    self._refresh_clicked,
                    tip='Reload hgignore'),
                sep,
                self._btn_close
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        mainvbox = gtk.VBox()
        self.add(mainvbox)
        mainvbox.pack_start(self.tbar, False, False, 2)

        hbox = gtk.HBox()
        lbl = gtk.Label('Glob:')
        lbl.set_property("width-chars", 7)
        lbl.set_alignment(1.0, 0.5)
        hbox.pack_start(lbl, False, False, 4)
        glob_entry = gtk.Entry()
        hbox.pack_start(glob_entry, True, True, 4)
        glob_button = gtk.Button('add')
        hbox.pack_start(glob_button, False, False, 4)
        glob_button.connect('clicked', self.add_glob, glob_entry)
        glob_entry.connect('activate', self.add_glob, glob_entry)
        mainvbox.pack_start(hbox, False, False)

        hbox = gtk.HBox()
        lbl = gtk.Label('Regexp:')
        lbl.set_property("width-chars", 7)
        lbl.set_alignment(1.0, 0.5)
        hbox.pack_start(lbl, False, False, 4)
        regexp_entry = gtk.Entry()
        hbox.pack_start(regexp_entry, True, True, 4)
        regexp_button = gtk.Button('add')
        hbox.pack_start(regexp_button, False, False, 4)
        regexp_button.connect('clicked', self.add_regexp, regexp_entry)
        regexp_entry.connect('activate', self.add_regexp, regexp_entry)
        mainvbox.pack_start(hbox, False, False)

        hbox = gtk.HBox()
        frame = gtk.Frame('Filters')
        hbox.pack_start(frame, True, True, 4)
        pattree = gtk.TreeView()
        sel = pattree.get_selection()
        sel.connect("changed", self.pattern_rowchanged)
        col = gtk.TreeViewColumn('Patterns', gtk.CellRendererText(), text=0)
        pattree.append_column(col) 
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.set_border_width(4)
        scrolledwindow.add(pattree)
        pattree.set_headers_visible(False)
        self.pattree = pattree
        frame.add(scrolledwindow)


        frame = gtk.Frame('Unknown Files')
        hbox.pack_start(frame, True, True, 4)
        unknowntree = gtk.TreeView()
        sel = unknowntree.get_selection()
        sel.connect("changed", self.unknown_rowchanged)
        col = gtk.TreeViewColumn('Files', gtk.CellRendererText(), text=0)
        unknowntree.append_column(col) 
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.set_border_width(4)
        scrolledwindow.add(unknowntree)
        model = gtk.ListStore(gobject.TYPE_STRING)
        unknowntree.set_model(model)
        unknowntree.set_headers_visible(False)
        frame.add(scrolledwindow)

        mainvbox.pack_start(hbox, True, True)

        glob_entry.grab_focus()
        self.connect('map_event', self._on_window_map_event)

    def pattern_rowchanged(self, sel):
        model, iter = sel.get_selected()
        if not iter:
            return

    def unknown_rowchanged(self, sel):
        model, iter = sel.get_selected()
        if not iter:
            return

    def add_glob(self, widget, glob_entry):
        pass

    def add_regexp(self, widget, glob_entry):
        pass

    def _on_window_map_event(self, event, param):
        self._refresh_clicked(None)

    def _refresh_clicked(self, togglebutton, data=None):
        try:
            l = open(os.path.join(self.root, '.hgignore'), 'rb').readlines()
            if l[0].endswith('\r\n'):
                self.doseoln = True
        except IOError, ValueError:
            self.doseoln = os.name == 'nt'
            l = []

        model = gtk.ListStore(gobject.TYPE_STRING)
        l = [string.strip(line) for line in l]
        for line in l:
            model.append([line])
        self.pattree.set_model(model)
        self.ignorelines = l

    def write_ignore_lines(self):
        if doseoln:
            out = [line + '\r\n' for line in self.ignorelines]
        else:
            out = [line + '\n' for line in self.ignorelines]
        try:
            f = open(os.path.join(self.root, '.hgignore'), 'wb')
            f.writelines(out)
            f.close()
        except IOError:
            pass

    def _close_clicked(self, toolbutton, data=None):
        self.destroy()

    def _toolbutton(self, stock, label, handler, tip):
        tbutton = gtk.ToolButton(stock)
        tbutton.set_label(label)
        tbutton.set_tooltip(self.tips, tip)
        tbutton.connect('clicked', handler)
        return tbutton
        
def run(root='', **opts):
    dialog = HgIgnoreDialog(root)
    dialog.show_all()
    dialog.connect('destroy', gtk.main_quit)
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    opts = {'root' : hglib.rootpath()}
    run(**opts)
