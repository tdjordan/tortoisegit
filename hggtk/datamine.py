#
# Data Mining dialog for TortoiseHg and Mercurial
#
# Copyright (C) 2008 Steve Borho <steve@borho.org>

import pygtk
pygtk.require('2.0')
import gtk
import gobject
import os
import pango
import Queue
import re
import threading, thread2
import time
from mercurial import hg, ui, util, revlog
from hglib import hgcmd_toq, toutf, fromutf
from gdialog import *
from vis import treemodel
from vis.colormap import AnnotateColorMap, AnnotateColorSaturation
from vis.treeview import TreeView
import gtklib

class DataMineDialog(GDialog):
    COL_REVID = 0
    COL_TEXT = 1
    COL_TOOLTIP = 2
    COL_PATH = 3
    COL_COLOR = 4
    COL_USER = 5

    def get_title(self):
        return 'DataMining - ' + os.path.basename(self.repo.root)

    def get_icon(self):
        return 'menurepobrowse.ico'

    def parse_opts(self):
        pass

    def get_tbbuttons(self):
        self.stop_button = self.make_toolbutton(gtk.STOCK_STOP, 'Stop', 
                self._stop_current_search, tip='Stop operation on current tab')
        return [
            self.make_toolbutton(gtk.STOCK_FIND, 'New Search', 
                self._search_clicked, tip='Open new search tab'),
            self.stop_button
            ]

    def prepare_display(self):
        os.chdir(self.repo.root)

    def save_settings(self):
        settings = GDialog.save_settings(self)
        settings['datamine'] = ()
        return settings

    def load_settings(self, settings):
        GDialog.load_settings(self, settings)
        # settings['datamine']

    def get_body(self):
        """ Initialize the Dialog. """        
        self.grep_cmenu = self.grep_context_menu()
        self.ann_cmenu = self.annotate_context_menu()
        self.changedesc = {}
        self.newpagecount = 1
        vbox = gtk.VBox()
        notebook = gtk.Notebook()
        notebook.set_tab_pos(gtk.POS_TOP)
        notebook.set_scrollable(True)
        notebook.popup_enable()
        notebook.show()
        self.notebook = notebook
        vbox.pack_start(self.notebook, True, True, 2)

        self.stbar = gtklib.StatusBar()
        vbox.pack_start(self.stbar, False, False, 2)
        self.stop_button.set_sensitive(False)
        return vbox

    def _destroying(self, gtkobj):
        self._stop_all_searches()
        GDialog._destroying(self, gtkobj)

    def ann_header_context_menu(self, treeview):
        _menu = gtk.Menu()
        _button = gtk.CheckMenuItem("Filename")
        _button.connect("toggled", self.toggle_annatate_columns, treeview, 1)
        _menu.append(_button)
        _button = gtk.CheckMenuItem("User")
        _button.connect("toggled", self.toggle_annatate_columns, treeview, 2)
        _menu.append(_button)
        _menu.show_all()
        return _menu

    def grep_context_menu(self):
        _menu = gtk.Menu()
        _menu.append(create_menu('di_splay change', self._cmenu_display))
        _menu.append(create_menu('_annotate file', self._cmenu_annotate))
        _menu.append(create_menu('_file history', self._cmenu_file_log))
        _menu.show_all()
        return _menu

    def annotate_context_menu(self):
        _menu = gtk.Menu()
        _menu.append(create_menu('di_splay change', self._cmenu_display))
        _menu.show_all()
        return _menu

    def _cmenu_display(self, menuitem):
        from changeset import ChangeSet
        statopts = {'rev' : [self.currev] }
        dialog = ChangeSet(self.ui, self.repo, self.cwd, [], statopts, False)
        dialog.display()

    def _cmenu_annotate(self, menuitem):
        self.add_annotate_page(self.curpath, self.currev)

    def _cmenu_file_log(self, menuitem):
        from history import GLog
        dialog = GLog(self.ui, self.repo, self.cwd, [self.repo.root], {}, False)
        dialog.open_with_file(self.curpath)
        dialog.display()

    def _grep_button_release(self, widget, event):
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK |
            gtk.gdk.CONTROL_MASK)):
            self._grep_popup_menu(widget, event.button, event.time)
        return False

    def _grep_popup_menu(self, treeview, button=0, time=0):
        self.grep_cmenu.popup(None, None, None, button, time)
        return True

    def _grep_row_act(self, tree, path, column):
        """Default action is the first entry in the context menu
        """
        self.grep_cmenu.get_children()[0].activate()
        return True

    def get_rev_desc(self, rev):
        if rev in self.changedesc:
            return self.changedesc[rev]
        ctx = self.repo.changectx(rev)
        author = util.shortuser(ctx.user())
        summary = ctx.description().replace('\0', '')
        summary = summary.split('\n')[0]
        date = time.strftime("%y-%m-%d %H:%M", time.gmtime(ctx.date()[0]))
        desc = author+'@'+str(rev)+' '+date+' "'+summary+'"'
        self.changedesc[rev] = (desc, author)
        return (desc, author)

    def _search_clicked(self, button, data):
        self.add_search_page()

    def create_tab_close_button(self):
        button = gtk.Button()
        iconBox = gtk.HBox(False, 0)
        image = gtk.Image()
        image.set_from_stock(gtk.STOCK_CLOSE, gtk.ICON_SIZE_MENU)
        gtk.Button.set_relief(button, gtk.RELIEF_NONE)
        settings = gtk.Widget.get_settings(button)
        (w,h) = gtk.icon_size_lookup_for_settings(settings, gtk.ICON_SIZE_MENU)
        gtk.Widget.set_size_request(button, w + 4, h + 4)
        image.show()
        iconBox.pack_start(image, True, False, 0)
        button.add(iconBox)
        iconBox.show()
        return button

    def add_search_page(self):
        frame = gtk.Frame()
        frame.set_border_width(10)
        vbox = gtk.VBox()

        search_hbox = gtk.HBox()
        regexp = gtk.Entry()
        includes = gtk.Entry()
        if self.cwd.startswith(self.repo.root):
            includes.set_text(util.canonpath(self.repo.root, self.cwd, '.'))
        excludes = gtk.Entry()
        search = gtk.Button('Search')
        search_hbox.pack_start(gtk.Label('Regexp:'), False, False, 4)
        search_hbox.pack_start(regexp, True, True, 4)
        search_hbox.pack_start(gtk.Label('Includes:'), False, False, 4)
        search_hbox.pack_start(includes, True, True, 4)
        search_hbox.pack_start(gtk.Label('Excludes:'), False, False, 4)
        search_hbox.pack_start(excludes, True, True, 4)
        search_hbox.pack_start(search, False, False)
        self.tooltips.set_tip(search, 'Start this search')
        self.tooltips.set_tip(regexp, 'Regular expression search pattern')
        self.tooltips.set_tip(includes, 'Comma separated list of'
                ' inclusion patterns.  By default, the entire repository'
                ' is searched.')
        self.tooltips.set_tip(excludes, 'Comma separated list of'
                ' exclusion patterns.  Exclusion patterns are applied'
                ' after inclusion patterns.')
        vbox.pack_start(search_hbox, False, False, 4)

        hbox = gtk.HBox()
        follow = gtk.CheckButton('Follow copies and renames')
        ignorecase = gtk.CheckButton('Ignore case')
        linenum = gtk.CheckButton('Show line numbers')
        showall = gtk.CheckButton('Show all matching revisions')
        hbox.pack_start(follow, False, False, 4)
        hbox.pack_start(ignorecase, False, False, 4)
        hbox.pack_start(linenum, False, False, 4)
        hbox.pack_start(showall, False, False, 4)
        vbox.pack_start(hbox, False, False, 4)

        treeview = gtk.TreeView()
        treeview.get_selection().set_mode(gtk.SELECTION_SINGLE)
        treeview.set_property('fixed-height-mode', True)
        treeview.connect("cursor-changed", self._grep_selection_changed)
        treeview.connect('button-release-event', self._grep_button_release)
        treeview.connect('popup-menu', self._grep_popup_menu)
        treeview.connect('row-activated', self._grep_row_act)

        results = gtk.ListStore(str, str, str, str)
        treeview.set_model(results)
        for title, width, col, emode in (
                ('Rev', 10, self.COL_REVID, pango.ELLIPSIZE_NONE),
                ('File', 25, self.COL_PATH, pango.ELLIPSIZE_START),
                ('Matches', 80, self.COL_TEXT, pango.ELLIPSIZE_END)):
            cell = gtk.CellRendererText()
            cell.set_property("width-chars", width)
            cell.set_property("ellipsize", emode)
            cell.set_property("family", "Monospace")
            column = gtk.TreeViewColumn(title)
            column.set_resizable(True)
            column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            column.set_fixed_width(cell.get_size(treeview)[2])
            column.pack_start(cell, expand=True)
            column.add_attribute(cell, "text", col)
            treeview.append_column(column)
        if hasattr(treeview, 'set_tooltip_column'):
            treeview.set_tooltip_column(self.COL_TOOLTIP)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(treeview)
        vbox.pack_start(scroller, True, True)
        frame.add(vbox)
        frame.show_all()

        hbox = gtk.HBox()
        lbl = gtk.Label('Search %d' % self.newpagecount)
        close = self.create_tab_close_button()
        close.connect('clicked', self.close_page, frame)
        hbox.pack_start(lbl, True, True, 2)
        hbox.pack_start(close, False, False)
        hbox.show_all()
        num = self.notebook.append_page(frame, hbox)

        self.newpagecount += 1
        objs = (treeview.get_model(), frame, regexp, follow, ignorecase,
                excludes, includes, linenum, showall, search_hbox)
        # Clicking 'search' or hitting Enter in any text entry triggers search
        search.connect('clicked', self.trigger_search, objs)
        regexp.connect('activate', self.trigger_search, objs)
        includes.connect('activate', self.trigger_search, objs)
        excludes.connect('activate', self.trigger_search, objs)
        if hasattr(self.notebook, 'set_tab_reorderable'):
            self.notebook.set_tab_reorderable(frame, True)
        self.notebook.set_current_page(num)
        regexp.grab_focus()

    def trigger_search(self, button, objs):
        (model, frame, regexp, follow, ignorecase, 
                excludes, includes, linenum, showall, search_hbox) = objs
        re = regexp.get_text()
        if not re:
            Prompt('No regular expression given',
                    'You must provide a search expression', self).run()
            regexp.grab_focus()
            return
        
        q = Queue.Queue()
        args = [self.repo.root, q, 'grep']
        if follow.get_active():     args.append('--follow')
        if ignorecase.get_active(): args.append('--ignore-case')
        if linenum.get_active():    args.append('--line-number')
        if showall.get_active():    args.append('--all')
        incs = [x.strip() for x in includes.get_text().split(',')]
        excs = [x.strip() for x in excludes.get_text().split(',')]
        for i in incs:
            if i: args.extend(['-I', i])
        for x in excs:
            if x: args.extend(['-X', x])
        args.append(re)
        thread = thread2.Thread(target=hgcmd_toq, args=args)
        thread.start()
        frame._mythread = thread
        self.stop_button.set_sensitive(True)

        model.clear()
        search_hbox.set_sensitive(False)
        self.stbar.begin()
        self.stbar.set_status_text('hg ' + ' '.join(args[2:]))

        hbox = gtk.HBox()
        lbl = gtk.Label('Search "%s"' % re.split()[0])
        close = self.create_tab_close_button()
        close.connect('clicked', self.close_page, frame)
        hbox.pack_start(lbl, True, True, 2)
        hbox.pack_start(close, False, False)
        hbox.show_all()
        self.notebook.set_tab_label(frame, hbox)

        gobject.timeout_add(50, self.grep_wait, thread, q, model,
                search_hbox, regexp, frame)

    def grep_wait(self, thread, q, model, search_hbox, regexp, frame):
        """
        Handle all the messages currently in the queue (if any).
        """
        while q.qsize():
            line = q.get(0).rstrip('\r\n')
            try:
                (path, revid, text) = line.split(':', 2)
            except ValueError:
                continue
            tip, user = self.get_rev_desc(long(revid))
            model.append((revid, toutf(text), tip, toutf(path)))
        if thread.isAlive():
            return True
        else:
            if threading.activeCount() == 1:
                self.stop_button.set_sensitive(False)
            frame._mythread = None
            search_hbox.set_sensitive(True)
            regexp.grab_focus()
            self.stbar.end()
            return False

    def _grep_selection_changed(self, treeview):
        """
        Callback for when the user selects grep output.
        """
        (path, focus) = treeview.get_cursor()
        model = treeview.get_model()
        if path is not None and model is not None:
            iter = model.get_iter(path)
            self.currev = model[iter][self.COL_REVID]
            self.curpath = fromutf(model[iter][self.COL_PATH])
            self.stbar.set_status_text(toutf(model[iter][self.COL_TOOLTIP]))

    def _stop_current_search(self, button, widget):
        num = self.notebook.get_current_page()
        frame = self.notebook.get_nth_page(num)
        self._stop_search(frame)

    def _stop_all_searches(self):
        for num in xrange(self.notebook.get_n_pages()):
            frame = self.notebook.get_nth_page(num)
            self._stop_search(frame)

    def _stop_search(self, frame):
        if hasattr(frame, '_mythread') and frame._mythread:
            frame._mythread.terminate()
            frame._mythread.join()
            frame._mythread = None

    def close_page(self, button, widget):
        '''Close page button has been pressed'''
        num = self.notebook.page_num(widget)
        if num != -1 and self.notebook.get_n_pages() > 1:
            self.notebook.remove_page(num)

    def _add_header_context_menu(self, col, menu):
        lb = gtk.Label(col.get_title())
        lb.show()
        col.set_widget(lb)
        wgt = lb.get_parent()
        while wgt:
            if type(wgt) == gtk.Button:
                wgt.connect("button-press-event",
                        self._tree_header_button_press, menu)
                break
            wgt = wgt.get_parent()

    def _tree_header_button_press(self, widget, event, menu):
        if event.button == 3:
            menu.popup(None, None, None, event.button, event.time)
            return True
        return False

    def add_annotate_page(self, path, revid):
        '''
        Add new annotation page to notebook.  Start scan of
        file 'path' revision history, start annotate of supplied
        revision 'revid'.
        '''
        if revid == '.':
            ctx = self.repo.workingctx().parents()[0]
            try:
                fctx = ctx.filectx(path)
            except revlog.LookupError:
                Prompt('File is unrevisioned',
                        'Unable to annotate ' + path, self).run()
                return
            rev = fctx.filelog().linkrev(fctx.filenode())
            revid = str(rev)
        else:
            rev = long(revid)

        frame = gtk.Frame()
        frame.set_border_width(10)
        vbox = gtk.VBox()

        # File log revision graph
        graphview = TreeView(self.repo, 5000, self.stbar)
        graphview.connect('revisions-loaded', self.revisions_loaded, rev)
        graphview.refresh(True, None, {'filehist':path, 'filerev':rev})
        graphview.set_property('rev-column-visible', True)
        graphview.set_property('date-column-visible', True)

        hbox = gtk.HBox()
        followlabel = gtk.Label('')
        follow = gtk.Button('Follow')
        follow.connect('clicked', self.follow_rename)
        follow.hide()
        follow.set_sensitive(False)
        hbox.pack_start(gtk.Label(''), True, True)
        hbox.pack_start(followlabel, False, False)
        hbox.pack_start(follow, False, False)

        # Annotation text tree view
        treeview = gtk.TreeView()
        treeview.get_selection().set_mode(gtk.SELECTION_SINGLE)
        treeview.set_property('fixed-height-mode', True)
        treeview.set_border_width(0)
        treeview.connect("cursor-changed", self._ann_selection_changed)
        treeview.connect('button-release-event', self._ann_button_release)
        treeview.connect('popup-menu', self._ann_popup_menu)
        treeview.connect('row-activated', self._ann_row_act)

        results = gtk.ListStore(str, str, str, str, str, str)
        treeview.set_model(results)

        context_menu = self.ann_header_context_menu(treeview)
        for title, width, col, emode, visible in (
                ('Rev', 10, self.COL_REVID, pango.ELLIPSIZE_NONE, True),
                ('File', 15, self.COL_PATH, pango.ELLIPSIZE_START, False),
                ('User', 15, self.COL_USER, pango.ELLIPSIZE_END, False),
                ('Matches', 80, self.COL_TEXT, pango.ELLIPSIZE_END, True)):
            cell = gtk.CellRendererText()
            cell.set_property("width-chars", width)
            cell.set_property("ellipsize", emode)
            cell.set_property("family", "Monospace")
            column = gtk.TreeViewColumn(title)
            column.set_resizable(True)
            column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            column.set_fixed_width(cell.get_size(treeview)[2])
            column.pack_start(cell, expand=True)
            column.add_attribute(cell, "text", col)
            column.add_attribute(cell, "background", self.COL_COLOR)
            column.set_visible(visible)
            treeview.append_column(column)
            self._add_header_context_menu(column, context_menu)
        treeview.set_headers_clickable(True)
        if hasattr(treeview, 'set_tooltip_column'):
            treeview.set_tooltip_column(self.COL_TOOLTIP)
        results.path = path
        results.rev = revid
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(treeview)

        vpaned = gtk.VPaned()
        vpaned.pack1(graphview, True, True)
        vpaned.pack2(scroller, True, True)
        vbox.pack_start(vpaned, True, True)
        vbox.pack_start(hbox, False, False)
        frame.add(vbox)
        frame.show_all()

        hbox = gtk.HBox()
        lbl = gtk.Label(toutf(os.path.basename(path) + '@' + revid))
        close = self.create_tab_close_button()
        close.connect('clicked', self.close_page, frame)
        hbox.pack_start(lbl, True, True, 2)
        hbox.pack_start(close, False, False)
        hbox.show_all()
        num = self.notebook.append_page_menu(frame, 
                hbox, gtk.Label(toutf(path + '@' + revid)))

        if hasattr(self.notebook, 'set_tab_reorderable'):
            self.notebook.set_tab_reorderable(frame, True)
        self.notebook.set_current_page(num)

        graphview.connect('revision-selected', self.log_selection_changed,
                path, followlabel, follow)

        objs = (frame, treeview.get_model(), path)
        graphview.treeview.connect('row-activated', self.log_activate, objs)
        graphview.treeview.connect('button-release-event',
                self._ann_button_release)
        graphview.treeview.connect('popup-menu', self._ann_popup_menu)

    def toggle_annatate_columns(self, button, treeview, col):
        b = button.get_active()
        treeview.get_column(col).set_visible(b)

    def log_selection_changed(self, graphview, path, label, button):
        row = graphview.get_revision()
        rev = row[treemodel.REVID]
        self.currev = str(rev)
        ctx = self.repo.changectx(rev)
        filectx = ctx.filectx(path)
        info = filectx.renamed()
        if info:
            (rpath, node) = info
            frev = self.repo.file(rpath).linkrev(node)
            button.set_label(toutf('%s@%s' % (rpath, frev)))
            button.show()
            button.set_sensitive(True)
            label.set_text('Follow Rename:')
        else:
            button.hide()
            button.set_sensitive(False)
            label.set_text('')

    def follow_rename(self, button):
        path, rev = button.get_label().rsplit('@', 1)
        self.add_annotate_page(path, rev)

    def log_activate(self, treeview, path, column, objs):
        model = treeview.get_model()
        iter = model.get_iter(path)
        rev = model.get_value(iter, treemodel.REVID)
        self.trigger_annotate(rev, objs)

    def revisions_loaded(self, graphview, rev):
        graphview.set_revision_id(rev)
        treeview = graphview.treeview
        path, column = treeview.get_cursor()
        # It's possible that the requested change was not found in the
        # file's filelog history.  In that case, no row will be
        # selected.
        if path != None:
            treeview.row_activated(path, column)

    def trigger_annotate(self, rev, objs):
        '''
        User has selected a file revision to annotate.  Trigger a
        background thread to perform the annotation.  Disable the select
        button until this operation is complete.
        '''
        (frame, model, path) = objs
        q = Queue.Queue()
        args = [self.repo.root, q, 'annotate', '--follow', '--number',
                '--rev', str(rev), path]
        thread = threading.Thread(target=hgcmd_toq, args=args)
        thread.start()
        frame._mythread = thread
        self.stop_button.set_sensitive(True)

        # date of selected revision
        ctx = self.repo.changectx(long(rev))
        curdate = ctx.date()[0]
        # date of initial revision
        fctx = self.repo.filectx(path, fileid=0)
        basedate = fctx.date()[0]
        agedays = (curdate - basedate) / (24 * 60 * 60)
        colormap = AnnotateColorSaturation(agedays)

        model.clear()
        self.stbar.begin()
        self.stbar.set_status_text(toutf('hg ' + ' '.join(args[2:])))

        hbox = gtk.HBox()
        lbl = gtk.Label(toutf(os.path.basename(path) + '@' + str(rev)))
        close = self.create_tab_close_button()
        close.connect('clicked', self.close_page, frame)
        hbox.pack_start(lbl, True, True, 2)
        hbox.pack_start(close, False, False)
        hbox.show_all()
        self.notebook.set_tab_label(frame, hbox)

        gobject.timeout_add(50, self.annotate_wait, thread, q, model,
                curdate, colormap, frame)

    def annotate_wait(self, thread, q, model, curdate, colormap, frame):
        """
        Handle all the messages currently in the queue (if any).
        """
        while q.qsize():
            line = q.get(0).rstrip('\r\n')
            try:
                (revpath, text) = line.split(':', 1)
                revid, path = revpath.lstrip().split(' ', 1)
                rowrev = long(revid)
            except ValueError:
                continue
            tip, user = self.get_rev_desc(rowrev)
            ctx = self.repo.changectx(rowrev)
            color = colormap.get_color(ctx, curdate)
            model.append((revid, toutf(text), tip, toutf(path.strip()),
                    color, toutf(user)))
        if thread.isAlive():
            return True
        else:
            if threading.activeCount() == 1:
                self.stop_button.set_sensitive(False)
            frame._mythread = None
            self.stbar.end()
            return False

    def _ann_selection_changed(self, treeview):
        """
        User selected line of annotate output, describe revision
        responsible for this line in the status bar
        """
        (path, focus) = treeview.get_cursor()
        model = treeview.get_model()
        if path is not None and model is not None:
            iter = model.get_iter(path)
            self.currev = model[iter][self.COL_REVID]
            self.path = model.path
            self.stbar.set_status_text(model[iter][self.COL_TOOLTIP])

    def _ann_button_release(self, widget, event):
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK |
            gtk.gdk.CONTROL_MASK)):
            self._ann_popup_menu(widget, event.button, event.time)
        return False

    def _ann_popup_menu(self, treeview, button=0, time=0):
        self.ann_cmenu.popup(None, None, None, button, time)
        return True

    def _ann_row_act(self, tree, path, column):
        self.ann_cmenu.get_children()[0].activate()


def create_menu(label, callback):
    menuitem = gtk.MenuItem(label, True)
    menuitem.connect('activate', callback)
    menuitem.set_border_width(1)
    return menuitem

def run(root='', cwd='', files=[], **opts):
    u = ui.ui()
    u.updateopts(debug=False, traceback=False)
    repo = hg.repository(u, path=root)

    cmdoptions = {
        'follow':False, 'follow-first':False, 'copies':False, 'keyword':[],
        'limit':0, 'rev':[], 'removed':False, 'no_merges':False, 'date':None,
        'only_merges':None, 'prune':[], 'git':False, 'verbose':False,
        'include':[], 'exclude':[]
    }

    dialog = DataMineDialog(u, repo, cwd, files, cmdoptions, True)
    dialog.display()
    for f in files:
        if os.path.isfile(f):
            cf = util.canonpath(root, cwd, f) 
            dialog.add_annotate_page(cf, '.')
        elif os.path.isdir(f):
            Prompt('Invalid path', "Can't annotate directory: %s" % f,
                    dialog).run()
                    
    if not dialog.notebook.get_n_pages():
        dialog.add_search_page()

    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    import hglib
    opts = {}
    opts['cwd'] = os.getcwd()
    opts['root'] = hglib.rootpath()
    opts['files'] = sys.argv[1:] or []
    run(**opts)
