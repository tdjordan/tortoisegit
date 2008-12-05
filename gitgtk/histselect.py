#
# History dialog for TortoiseHg
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
import Queue
from dialog import question_dialog, error_dialog
from mercurial import util
from mercurial.i18n import _
from shlib import set_tortoise_icon
import hglib

class HistoryDialog(gtk.Dialog):
    """ Dialog to display Mercurial history """
    def __init__(self, root='', files=[], list_clean=False,
            select=False, page=100):
        """ Initialize the Dialog """
        if select:
            buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
                      gtk.STOCK_OK, gtk.RESPONSE_ACCEPT)
        else:
            buttons = (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        super(HistoryDialog, self).__init__(flags=gtk.DIALOG_MODAL, 
                                           buttons=buttons)

        set_tortoise_icon(self, 'menulog.ico')
        # set dialog title
        title = "hg log "
        if root: title += " - %s" % root
        self.set_title(title)

        self.root = root
        self.files = files
        self.list_clean = list_clean
        self.page_size = page
        self.start_rev = 'tip'
        self.tip_rev = None
        self.selected = (None, None)

        # build dialog
        self._create()

        # display history 
        self._generate_history()

    def _create(self):
        self.set_default_size(650, 400)
        
        self._hbox = gtk.VBox()
        self.vbox.pack_start(self._hbox, True, True)
        
        # add treeview to list change files
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_IN)

        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.treeview = gtk.TreeView()
        self._create_treestore()
        scrolledwindow.add(self.treeview)
        self._hbox.pack_start(scrolledwindow, True, True)
        
        self._button_box = gtk.HBox()
        self._hbox.pack_start(self._button_box, False, False, 10)

        # add navigation controls
        self._btn_goto_tip = gtk.Button("Tip")
        self._button_box.pack_start(self._btn_goto_tip, False, False)
        self._btn_goto_prev = gtk.Button("Prev")
        self._button_box.pack_start(self._btn_goto_prev, False, False)
        self._btn_goto_next = gtk.Button("Next")
        self._button_box.pack_start(self._btn_goto_next, False, False)
        self._btn_goto_first = gtk.Button("(0)")
        self._button_box.pack_start(self._btn_goto_first, False, False)
        
        self._btn_goto_tip.connect('clicked', self._on_goto_clicked, 'tip')
        self._btn_goto_next.connect('clicked', self._on_goto_clicked, 'next')
        self._btn_goto_prev.connect('clicked', self._on_goto_clicked, 'prev')
        self._btn_goto_first.connect('clicked', self._on_goto_clicked, 'first')

        # add search support
        #self._search_input = gtk.Entry()
        #self._button_box.pack_end(self._search_input, False, False)
        #self._btn_search = gtk.Button("Search:")
        #self._button_box.pack_end(self._btn_search, False, False, 3)
        
        # show them all
        self.vbox.show_all()

    def _create_treestore(self):
        """ create history display """
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

    def _cursor_changed(self, tv):
        (model, iter) = tv.get_selection().get_selected()
        path = self.model.get_path(iter)
        cs = self.history[path[0]]['changeset'][0]
        rev, id = cs.split(':')
        self.selected = (rev, id)
        
    def _get_hg_history(self, rev=None, limit=10):    
        # get history
        options = {}
        if rev: options['rev'] = [rev]
        if limit: options['limit'] = limit
        self._do_hg_cmd('log', options)
        
        # parse log output
        import re
        histlist = []
        cs = {}
        for x in self.hgout.splitlines():
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
        
    def _generate_history(self):
        # clear changed files display
        self.model.clear()

        # retrieve repo history
        revrange = '%s:0' % self.start_rev
        self.history = self._get_hg_history(rev=revrange, limit=self.page_size)

        # display history
        for cs in self.history:
            titer = self.model.append(None, [ _('changeset:'), cs['changeset'][0] ])
            for fld in ('parent', 'tag', 'branch', 'user', 'date', 'summary'):
                if fld not in cs:
                    continue
                vlist = type(cs[fld])==type([]) and cs[fld] or [cs[fld]]
                for v in vlist:
                    self.model.append(titer, [ fld + ":", v ])

        self.treeview.expand_all()
        
        if self.start_rev == 'tip':
            self.tip_rev = self._get_revision_on_page(0)
        
    def _do_hg_cmd(self, cmd, options):
        import os.path
                  
        try:
            q = Queue.Queue()
            args = [cmd] + [os.path.join(self.root, x) for x in self.files]
            hglib.hgcmd_toq(self.root, q, *args, **{})
            out = ''
            while q.qsize(): out += q.get(0)
            self.hgout = out
        except util.Abort, inst:
            error_dialog(self, "Error in %s command" % cmd, "abort: %s" % inst)
            return False
        except:
            import traceback
            error_dialog(self, "Error in %s command" % cmd,
                    "Traceback:\n%s" % traceback.format_exc())
            return False
        return True

    def _on_goto_clicked(self, button, nav):
        if nav == 'tip':
            self.start_rev = 'tip'
        elif nav == 'first':
            self.start_rev = self.page_size -1
        elif nav == 'next':
            if self._is_first_revision(-1):
                return
            rev = self._get_revision_on_page(0)
            next_start = rev - self.page_size
            self.start_rev = next_start
        elif nav == 'prev':
            rev = self._get_revision_on_page(0)
            next_start = rev + self.page_size
            if next_start > self.tip_rev:
                next_start = self.tip_rev
            self.start_rev = next_start

        self._generate_history()
    
    def _get_revision_on_page(self, index):
        import string
        cs = self.history[index]
        revpair = cs['changeset'][0]
        revnum = revpair.split(':')[0]
        return string.atoi(revnum)

    def _is_tip_revision(self, index):
        cs = self.history[index]
        tags = cs.get('tag', [])
        if 'tip' in tags:
            return True
        return False
        
    def _is_first_revision(self, index):
        rev = self._get_revision_on_page(index)
        if rev == 0:
            return True
        return False

    def _get_selected_revision(self):
        treeselection = treeview.get_selection()
        mode = treeselection.get_mode()
        list = []
        if mode == gtk.SELECTION_MULTIPLE:
            (model, pathlist) = treeselection.get_selected_rows()
            for p in pathlist:
                iter = model.get_iter(p)
                list.append(model.get_value(iter, index))
        else:
            (model, iter) = treeselection.get_selected()
            list.append(model.get_value(iter, index))
        
        return list
        
def run(root='', files=[], **opts):
    dialog = HistoryDialog(root=root, files=files)
    dialog.show_all()
    dialog.connect('response', gtk.main_quit)
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()
    
def select(root='', files=[]):
    dialog = HistoryDialog(root=root, files=files, select=True)
    resp = dialog.run()
    rev = None
    if resp == gtk.RESPONSE_ACCEPT:
        rev = dialog.selected[1]
    dialog.hide()
    return rev

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1:] or []
    run(**opts)
