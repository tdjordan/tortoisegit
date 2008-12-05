#
# backout.py - TortoiseHg's dialog for backing out changeset
#
# Copyright (C) 2008 Steve Borho <steve@borho.org>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import os
import sys
import gtk
import pango
from dialog import *
from hgcmd import CmdDialog
import histselect

class BackoutDialog(gtk.Window):
    """ Backout effect of a changeset """
    def __init__(self, root='', rev=''):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        self.root = root
        self.set_title('Backout changeset - ' + rev)
        self.set_default_size(600, 400)
        self.notify_func = None
        
        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()

        sep = gtk.SeparatorToolItem()
        sep.set_expand(True)
        sep.set_draw(False)

        tbuttons = [
                self._toolbutton(gtk.STOCK_GO_BACK, 'Backout',
                                 self._backout_clicked,
                                 'Backout selected changeset'),
                sep,
                self._toolbutton(gtk.STOCK_CLOSE, 'Close',
                                 self._close_clicked,
                                 'Close Window')
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        vbox = gtk.VBox()
        self.add(vbox)
        vbox.pack_start(self.tbar, False, False, 2)

        # From: combo box
        self.reventry = gtk.Entry()
        self.reventry.set_text(rev)
        self.browse = gtk.Button("Browse...")
        self.browse.connect('clicked', self._btn_rev_clicked)

        hbox = gtk.HBox()
        hbox.pack_start(gtk.Label('Revision to backout:'), False, False, 4)
        hbox.pack_start(self.reventry, True, True, 4)
        hbox.pack_start(self.browse, False, False, 4)
        vbox.pack_start(hbox, False, False, 4)

        self.logview = gtk.TextView(buffer=None)
        self.logview.set_editable(True)
        self.logview.modify_font(pango.FontDescription("Monospace"))
        buffer = self.logview.get_buffer()
        buffer.set_text('Backed out changeset: ' + rev)
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.add(self.logview)
        scrolledwindow.set_border_width(4)
        frame = gtk.Frame('Backout commit message')
        frame.set_border_width(4)
        frame.add(scrolledwindow)
        self.tips.set_tip(frame, 
                'Commit message text for new changeset that reverses the'
                '  effect of the change being backed out.')
        vbox.pack_start(frame, True, True, 4)

    def _close_clicked(self, toolbutton, data=None):
        self.destroy()

    def set_notify_func(self, func, *args):
        self.notify_func = func
        self.notify_args = args

    def _btn_rev_clicked(self, button):
        """ select revision from history dialog """
        rev = histselect.select(self.root)
        if rev is not None:
            self.reventry.set_text(rev)
            buffer = self.logview.get_buffer()
            buffer.set_text('Backed out changeset: ' + rev)

    def _toolbutton(self, stock, label, handler, tip):
        tbutton = gtk.ToolButton(stock)
        tbutton.set_label(label)
        tbutton.set_tooltip(self.tips, tip)
        tbutton.connect('clicked', handler)
        return tbutton
        
    def _backout_clicked(self, button):
        buffer = self.logview.get_buffer()
        start, end = buffer.get_bounds()
        cmdline = ['hg', 'backout', '--rev', self.reventry.get_text(),
            '--message', buffer.get_text(start, end)]
        dlg = CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        if self.notify_func:
            self.notify_func(self.notify_args)

def run(root='', **opts):
    # This dialog is intended to be launched by the changelog browser
    # It's not expected to be used from hgproc or the command line.  I
    # leave this path in place for testing purposes.
    dialog = BackoutDialog(root, 'tip')
    dialog.show_all()
    dialog.connect('destroy', gtk.main_quit)
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or os.getcwd()
    run(**opts)
