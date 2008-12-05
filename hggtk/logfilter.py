#
# logfilter.py - TortoiseHg's dialog for defining log filter criteria
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import pygtk
pygtk.require("2.0")

import os
import sys
import gtk
from gdialog import *
from mercurial.node import *
from mercurial import cmdutil, util, hg, ui
from mercurial.repo import RepoError
from shlib import shell_notify, set_tortoise_icon

class FilterDialog(gtk.Dialog):
    """ Dialog for creating log filters """
    def __init__(self, root='', revs=[], files=[], filterfunc=None):
        """ Initialize the Dialog """
        buttons = (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        super(FilterDialog, self).__init__(flags=gtk.DIALOG_MODAL, 
                                           buttons=buttons)

        set_tortoise_icon(self, 'menucheckout.ico')
        self.set_title("hg log filter - %s" % os.path.basename(root))

        self.filterfunc = filterfunc

        try:
            self.repo = hg.repository(ui.ui(), path=root)
        except RepoError:
            return None

        self.set_default_size(350, 120)

        # add toolbar with tooltips
        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()

        tbuttons = [
                self._toolbutton(
                    gtk.STOCK_FIND,
                    'Apply', 
                    self._btn_apply_clicked,
                    tip='Apply filter to revision history'),
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        self.vbox.pack_start(self.tbar, False, False, 2)
        
        # branch: combo box
        hbox = gtk.HBox()
        self.branchradio = gtk.RadioButton(None, 'Branch')
        self.branchlist = gtk.ListStore(str)
        self.branchbox = gtk.ComboBoxEntry(self.branchlist, 0)
        hbox.pack_start(self.branchradio, False, False, 4)
        hbox.pack_start(self.branchbox, True, True, 4)
        eventbox = gtk.EventBox()
        eventbox.add(hbox)
        self.tips.set_tip(eventbox, 'View revision graph of named branch')
        self.vbox.pack_start(eventbox, False, False, 4)
        for name in self.repo.branchtags().keys():
            self.branchlist.append([name])

        # Revision range entries
        hbox = gtk.HBox()
        self.revradio = gtk.RadioButton(self.branchradio, 'Rev Range')
        self.rev0Entry = gtk.Entry()
        self.rev0Entry.connect('activate', self._btn_apply_clicked)
        self.rev1Entry = gtk.Entry()
        self.rev1Entry.connect('activate', self._btn_apply_clicked)
        hbox.pack_start(self.revradio, False, False, 4)
        hbox.pack_start(self.rev0Entry, True, False, 4)
        hbox.pack_start(self.rev1Entry, True, False, 4)
        eventbox = gtk.EventBox()
        eventbox.add(hbox)
        self.tips.set_tip(eventbox, 'View range of revisions')
        self.vbox.pack_start(eventbox, False, False, 4)
        if revs:
            self.rev0Entry.set_text(str(revs[0]))
        if len(revs) > 1:
            self.rev1Entry.set_text(str(revs[1]))

        hbox = gtk.HBox()
        self.searchradio = gtk.RadioButton(self.branchradio, 'Search Filter')
        hbox.pack_start(self.searchradio, False, False, 4)
        eventbox = gtk.EventBox()
        eventbox.add(hbox)
        self.tips.set_tip(eventbox, 'Search repository changelog with criteria')
        self.vbox.pack_start(eventbox, False, False, 4)

        self.searchframe = gtk.Frame()
        self.vbox.pack_start(self.searchframe, True, False, 4)
        vbox = gtk.VBox()
        self.searchframe.add(vbox)

        hbox = gtk.HBox()
        self.filesentry = gtk.Entry()
        self.filesentry.connect('activate', self._btn_apply_clicked)
        lbl = gtk.Label('File(s):')
        lbl.set_property("width-chars", 10)
        lbl.set_alignment(0, 0.5)
        hbox.pack_start(lbl, False, False, 4)
        hbox.pack_start(self.filesentry, True, True, 4)
        eventbox = gtk.EventBox()
        eventbox.add(hbox)
        self.tips.set_tip(eventbox, 'Display only changesets affecting these'
                ' comma separated file paths')
        vbox.pack_start(eventbox, False, False, 4)
        if files:
            self.filesentry.set_text(', '.join(files))
        
        hbox = gtk.HBox()
        self.kwentry = gtk.Entry()
        self.kwentry.connect('activate', self._btn_apply_clicked)
        lbl = gtk.Label('Keyword(s):')
        lbl.set_property("width-chars", 10)
        lbl.set_alignment(0, 0.5)
        hbox.pack_start(lbl, False, False, 4)
        hbox.pack_start(self.kwentry, True, True, 4)
        eventbox = gtk.EventBox()
        eventbox.add(hbox)
        self.tips.set_tip(eventbox, 'Display only changesets matching these'
                ' comma separated case insensitive keywords')
        vbox.pack_start(eventbox, False, False, 4)

        hbox = gtk.HBox()
        self.dateentry = gtk.Entry()
        self.dateentry.connect('activate', self._btn_apply_clicked)
        self.helpbutton = gtk.Button("?")
        self.helpbutton.set_relief(gtk.RELIEF_NONE)
        self.tips.set_tip(self.helpbutton, 'Help on date formats')
        self.helpbutton.connect('clicked', self._date_help)
        lbl = gtk.Label('Date:')
        lbl.set_property("width-chars", 10)
        lbl.set_alignment(0, 0.5)
        hbox.pack_start(lbl, False, False, 4)
        hbox.pack_start(self.dateentry, True, True, 4)
        hbox.pack_start(self.helpbutton, False, False, 4)
        eventbox = gtk.EventBox()
        eventbox.add(hbox)
        self.tips.set_tip(eventbox, 'Display only changesets matching this'
                ' date specification')
        vbox.pack_start(eventbox, False, False, 4)

        self.searchradio.connect('toggled', self.searchtoggle)
        self.revradio.connect('toggled', self.revtoggle)
        self.branchradio.connect('toggled', self.branchtoggle)

        # toggle them all once
        self.searchradio.set_active(True)
        self.branchradio.set_active(True)
        self.revradio.set_active(True)
        self.rev0Entry.grab_focus()

        # show them all
        self.show_all()

    def searchtoggle(self, button):
        self.searchframe.set_sensitive(button.get_active())

    def revtoggle(self, button):
        self.rev0Entry.set_sensitive(button.get_active())
        self.rev1Entry.set_sensitive(button.get_active())

    def branchtoggle(self, button):
        self.branchbox.set_sensitive(button.get_active())

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
        
    def _btn_apply_clicked(self, button, data=None):
        opts = {}
        if self.searchradio.get_active():
            pats = self.filesentry.get_text()
            kw = self.kwentry.get_text()
            date = self.dateentry.get_text()
            if pats:
                opts['pats'] = [p.strip() for p in pats.split(',')]
            if kw:
                opts['keyword'] = [w.strip() for w in kw.split(',')]
            if date:
                try:
                    df = util.matchdate(date)
                    opts['date'] = date
                except Exception, e:
                    Prompt('Invalid date specification', str(e), self).run()
                    self.dateentry.grab_focus()
                    return
        elif self.revradio.get_active():
            rev0 = self.rev0Entry.get_text()
            rev1 = self.rev1Entry.get_text()
            if not rev1:
                rev1 = rev0
            try:
                range = cmdutil.revrange(self.repo, [rev0, rev1])
                range.sort()
                range.reverse()
                opts['revrange'] = range
            except Exception, e:
                Prompt('Invalid revision range', str(e), self).run()
                self.rev0Entry.grab_focus()
                return
        elif self.branchradio.get_active():
            branch = self.branchbox.child.get_text()
            if branch:
                opts['branch'] = branch
            else:
                return

        if self.filterfunc:
            self.filterfunc(opts)
        
    def _date_help(self, button):
        from hgcmd import CmdDialog
        dlg = CmdDialog(['hg', 'help', 'dates'], False)
        dlg.run()
        dlg.hide()

if __name__ == "__main__":
    # this dialog is not designed for standalone use
    # this is for debugging only
    dialog = FilterDialog()
    dialog.show_all()
    dialog.connect('response', gtk.main_quit)
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()
