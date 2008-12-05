#
# history.py - Changelog dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import os
import pygtk
pygtk.require('2.0')
import gtk
import gobject
import pango
import StringIO

from mercurial.node import *
from mercurial import ui, hg, commands, extensions
from gdialog import *
from changeset import ChangeSet
from logfilter import FilterDialog
from update import UpdateDialog
from merge import MergeDialog
from vis import treemodel
from vis.treeview import TreeView
from hglib import toutf
import gtklib

def create_menu(label, callback):
    menuitem = gtk.MenuItem(label, True)
    menuitem.connect('activate', callback)
    menuitem.set_border_width(1)
    return menuitem

class GLog(GDialog):
    """GTK+ based dialog for displaying repository logs
    """
    def get_title(self):
        return os.path.basename(self.repo.root) + ' log' 

    def get_icon(self):
        return 'menulog.ico'

    def parse_opts(self):
        # Disable quiet to get full log info
        self.ui.quiet = False

    def get_tbbuttons(self):
        return [
                self.make_toolbutton(gtk.STOCK_REFRESH,
                    'Re_fresh',
                    self._refresh_clicked,
                    tip='Reload revision history'),
                gtk.SeparatorToolItem(),
                self.make_toolbutton(gtk.STOCK_INDEX,
                    '_Filter',
                    self._filter_clicked,
                    menu=self._filter_menu(),
                    tip='Filter revisions for display'),
                gtk.SeparatorToolItem(),
                self.make_toolbutton(gtk.STOCK_FIND,
                    '_DataMine',
                    self._datamine_clicked,
                    tip='Search Repository History'),
                gtk.SeparatorToolItem()
             ] + self.changeview.get_tbbuttons()

    def toggle_view_column(self, button, property):
        bool = button.get_active()
        self.graphview.set_property(property, bool)

    def _more_clicked(self, button):
        self.graphview.next_revision_batch()

    def _load_all_clicked(self, button):
        self.graphview.load_all_revisions()
        self.nextbutton.set_sensitive(False)
        self.allbutton.set_sensitive(False)

    def revisions_loaded(self, graphview):
        '''Treeview reports log generator has exited'''
        if not self.graphview.graphdata:
            self.changeview._buffer.set_text('')
            self.changeview._filelist.clear()
            self._last_rev = None
        self.nextbutton.set_sensitive(False)
        self.allbutton.set_sensitive(False)

    def _datamine_clicked(self, toolbutton, data=None):
        from datamine import DataMineDialog
        dialog = DataMineDialog(self.ui, self.repo, self.cwd, [], {}, False)
        dialog.display()
        dialog.add_search_page()

    def _filter_clicked(self, toolbutton, data=None):
        if self._filter_dialog:
            self._filter_dialog.show()
            self._filter_dialog.present()
        else:
            self._show_filter_dialog()

    def _show_filter_dialog(self):
        '''Launch a modeless filter dialog'''
        def do_reload(opts):
            self.custombutton.set_active(True)
            self.reload_log(opts)

        def close_filter_dialog(dialog, response_id):
            dialog.hide()

        revs = []
        if self.currow is not None:
            revs.append(self.currow[treemodel.REVID])
        if self.graphview.get_mark_rev() is not None:
            revs.append(self.graphview.get_mark_rev())
            
        dlg = FilterDialog(self.repo.root, revs, self.pats,
                filterfunc=do_reload)
        dlg.connect('response', close_filter_dialog)
        dlg.set_modal(False)
        dlg.show()
        
        self._filter_dialog = dlg

    def _filter_selected(self, widget, data=None):
        if widget.get_active():
            self._filter = data
            self.reload_log()

    def _view_menu(self):
        menu = gtk.Menu()

        button = gtk.CheckMenuItem("Show Ids")
        button.connect("toggled", self.toggle_view_column,
                'rev-column-visible')
        button.set_active(True)
        button.set_draw_as_radio(True)
        menu.append(button)
        button = gtk.CheckMenuItem("Show Tags")
        button.connect("toggled", self.toggle_view_column,
                'tags-column-visible')
        button.set_active(True)
        button.set_draw_as_radio(True)
        menu.append(button)
        button = gtk.CheckMenuItem("Show Date")
        button.connect("toggled", self.toggle_view_column,
                'date-column-visible')
        button.set_active(True)
        button.set_draw_as_radio(True)
        menu.append(button)
        menu.show_all()
        return menu

    def _filter_menu(self):
        menu = gtk.Menu()
        
        button = gtk.RadioMenuItem(None, "Show All Revisions")
        button.set_active(True)
        button.connect("toggled", self._filter_selected, 'all')
        menu.append(button)
        
        button = gtk.RadioMenuItem(button, "Show Tagged Revisions")
        button.connect("toggled", self._filter_selected, 'tagged')
        menu.append(button)
       
        button = gtk.RadioMenuItem(button, "Show Parent Revisions")
        button.connect("toggled", self._filter_selected, 'parents')
        menu.append(button)
       
        button = gtk.RadioMenuItem(button, "Show Head Revisions")
        button.connect("toggled", self._filter_selected, 'heads')
        menu.append(button)
       
        button = gtk.RadioMenuItem(button, "Show Only Merge Revisions")
        button.connect("toggled", self._filter_selected, 'only_merges')
        menu.append(button)
       
        button = gtk.RadioMenuItem(button, "Show Non-Merge Revisions")
        button.connect("toggled", self._filter_selected, 'no_merges')
        menu.append(button)
       
        self.custombutton = gtk.RadioMenuItem(button, "Custom Filter")
        self.custombutton.set_sensitive(False)
        menu.append(self.custombutton)
       
        menu.show_all()
        return menu

    def open_with_file(self, file):
        '''Call this before display() to open with file history'''
        self.opts['filehist'] = file

    def prepare_display(self):
        '''Called at end of display() method'''
        self._last_rev = None
        self._filter = "all"
        self.currow = None
        self.curfile = None
        self.opts['rev'] = [] # This option is dangerous - used directly by hg
        self.opts['revs'] = None
        os.chdir(self.repo.root)  # paths relative to repo root do not work otherwise

        if 'filehist' in self.opts:
            self.custombutton.set_active(True)
            self.graphview.refresh(True, None, self.opts)
            del self.opts['filehist']
        elif 'revrange' in self.opts:
            self.custombutton.set_active(True)
            self.graphview.refresh(True, None, self.opts)
        elif self.pats == [self.repo.root] or self.pats == ['']:
            self.pats = []
            self.reload_log()
        elif self.pats:
            self.custombutton.set_active(True)
            self.graphview.refresh(False, self.pats, self.opts)
        else:
            self.reload_log()

    def save_settings(self):
        settings = GDialog.save_settings(self)
        settings['glog'] = (self._vpaned.get_position(),
                self._hpaned.get_position())
        return settings

    def load_settings(self, settings):
        '''Called at beginning of display() method'''
        limit_opt = self.repo.ui.config('tortoisehg', 'graphlimit', '500')
        if limit_opt:
            try:
                limit = int(limit_opt)
            except ValueError:
                limit = 0
            if limit <= 0:
                limit = None
        else:
            limit = None

        # Allocate TreeView instance to use internally
        self.limit = limit
        self.stbar = gtklib.StatusBar()
        self.graphview = TreeView(self.repo, limit, self.stbar)

        # Allocate ChangeSet instance to use internally
        self.changeview = ChangeSet(self.ui, self.repo, self.cwd, [],
                self.opts, False, self.stbar)
        self.changeview.display(False)
        self.changeview.glog_parent = self

        GDialog.load_settings(self, settings)
        if settings:
            set = settings['glog']
            if type(set) == int:
                self._setting_vpos = set
                self._setting_hpos = -1
            else:
                (self._setting_vpos, self._setting_hpos) = set
        else:
            self._setting_vpos = -1
            self._setting_hpos = -1

    def reload_log(self, filteropts={}):
        """Send refresh event to treeview object"""
        os.chdir(self.repo.root)  # paths relative to repo root do not work otherwise
        self.nextbutton.set_sensitive(True)
        self.allbutton.set_sensitive(True)
        self.opts['rev'] = []
        self.opts['revs'] = None
        self.opts['no_merges'] = False
        self.opts['only_merges'] = False
        self.opts['revrange'] = filteropts.get('revrange', None)
        self.opts['date'] = filteropts.get('date', None)
        self.opts['keyword'] = filteropts.get('keyword', [])
        revs = []
        if filteropts:
            branch = filteropts.get('branch', None)
            if 'revrange' in filteropts or 'branch' in filteropts:
                self.graphview.refresh(True, branch, self.opts)
            else:
                filter = filteropts.get('pats', [])
                self.graphview.refresh(False, filter, self.opts)
        elif self._filter == "all":
            self.graphview.refresh(True, None, self.opts)
        elif self._filter == "only_merges":
            self.opts['only_merges'] = True
            self.graphview.refresh(False, [], self.opts)
        elif self._filter == "no_merges":
            self.opts['no_merges'] = True
            self.graphview.refresh(False, [], self.opts)
        elif self._filter == "tagged":
            tagged = []
            for t, r in self.repo.tagslist():
                hr = hex(r)
                if hr not in tagged:
                    tagged.insert(0, hr)
            self.opts['revs'] = tagged
            self.graphview.refresh(False, [], self.opts)
        elif self._filter == "parents":
            repo_parents = [x.rev() for x in self.repo.workingctx().parents()]
            self.opts['revs'] = [str(x) for x in repo_parents]
            self.graphview.refresh(False, [], self.opts)
        elif self._filter == "heads":
            heads = [self.repo.changelog.rev(x) for x in self.repo.heads()]
            self.opts['revs'] = [str(x) for x in heads]
            self.graphview.refresh(False, [], self.opts)

    def tree_context_menu(self):
        _menu = gtk.Menu()
        _menu.append(create_menu('di_splay', self._show_status))
        _menu.append(create_menu('_checkout', self._checkout))
        self._cmenu_merge = create_menu('_merge with', self._merge)
        _menu.append(self._cmenu_merge)
        _menu.append(create_menu('_export patch', self._export_patch))
        _menu.append(create_menu('e_mail patch', self._email_patch))
        _menu.append(create_menu('add/remove _tag', self._add_tag))
        _menu.append(create_menu('backout revision', self._backout_rev))
        
        # need mq extension for strip command
        extensions.loadall(self.ui)
        extensions.load(self.ui, 'mq', None)
        _menu.append(create_menu('strip revision', self._strip_rev))
        
        _menu.show_all()
        return _menu
 
    def tree_diff_context_menu(self):
        _menu = gtk.Menu()
        _menu.append(create_menu('_diff with selected', self._diff_revs))
        _menu.append(create_menu('visual diff with selected',
                self._vdiff_selected))
        _menu.show_all()
        return _menu
 
    def get_body(self):
        self._filter_dialog = None
        self._menu = self.tree_context_menu()
        self._menu2 = self.tree_diff_context_menu()

        self.tree_frame = gtk.Frame()
        self.tree_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)

        # PyGtk 2.6 and below did not automatically register types
        if gobject.pygtk_version < (2, 8, 0): 
            gobject.type_register(TreeView)

        self.tree = self.graphview.treeview
        self.graphview.connect('revision-selected', self.selection_changed)
        self.graphview.connect('revisions-loaded', self.revisions_loaded)

        #self.tree.connect('button-release-event', self._tree_button_release)
        self.tree.connect('button-press-event', self._tree_button_press)
        #self.tree.connect('popup-menu', self._tree_popup_menu)
        self.tree.connect('row-activated', self._tree_row_act)
        #self.tree.modify_font(pango.FontDescription(self.fontlist))
        
        hbox = gtk.HBox()
        hbox.pack_start(self.graphview, True, True, 0)
        vbox = gtk.VBox()
        self.colmenu = gtk.MenuToolButton('')
        self.colmenu.set_menu(self._view_menu())
        # A MenuToolButton has two parts; a Button and a ToggleButton
        # we want to see the togglebutton, but not the button
        b = self.colmenu.child.get_children()[0]
        b.unmap()
        b.set_sensitive(False)
        self.nextbutton = gtk.ToolButton(gtk.STOCK_GO_DOWN)
        self.nextbutton.connect('clicked', self._more_clicked)
        self.allbutton = gtk.ToolButton(gtk.STOCK_GOTO_BOTTOM)
        self.allbutton.connect('clicked', self._load_all_clicked)
        vbox.pack_start(self.colmenu, False, False)
        vbox.pack_start(gtk.Label(''), True, True) # expanding blank label
        vbox.pack_start(self.nextbutton, False, False)
        vbox.pack_start(self.allbutton, False, False)

        self.nextbutton.set_tooltip(self.tooltips,
                'show next %d revisions' % self.limit)
        self.allbutton.set_tooltip(self.tooltips,
                'show all remaining revisions')

        hbox.pack_start(vbox, False, False, 0)
        self.tree_frame.add(hbox)
        self.tree_frame.show_all()

        # Add ChangeSet instance to bottom half of vpane
        self.changeview.graphview = self.graphview
        self._hpaned = self.changeview.get_body()

        self._vpaned = gtk.VPaned()
        self._vpaned.pack1(self.tree_frame, True, False)
        self._vpaned.pack2(self._hpaned)
        self._vpaned.set_position(self._setting_vpos)
        self._hpaned.set_position(self._setting_hpos)

        vbox = gtk.VBox()
        vbox.pack_start(self._vpaned, True, True)

        # Append status bar
        vbox.pack_start(gtk.HSeparator(), False, False)
        vbox.pack_start(self.stbar, False, False)

        return vbox

    def _strip_rev(self, menuitem):
        rev = self.currow[treemodel.REVID]
        res = Confirm('Strip Revision(s)', [], self,
                'Remove revision %d and all descendants?' % rev).run()
        if res != gtk.RESPONSE_YES:
            return
        from hgcmd import CmdDialog
        cmdline = ['hg', 'strip', str(rev)]
        dlg = CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        self.repo.invalidate()
        self.reload_log()

    def _backout_rev(self, menuitem):
        from backout import BackoutDialog
        rev = self.currow[treemodel.REVID]
        rev = short(self.repo.changelog.node(rev))
        parents = [x.node() for x in self.repo.workingctx().parents()]
        dialog = BackoutDialog(self.repo.root, rev)
        dialog.set_transient_for(self)
        dialog.show_all()
        dialog.set_notify_func(self.checkout_completed, parents)
        dialog.present()
        dialog.set_transient_for(None)

    def _diff_revs(self, menuitem):
        from status import GStatus
        from gtools import cmdtable
        rev0, rev1 = self._revs
        statopts = self.merge_opts(cmdtable['gstatus|gst'][1],
                ('include', 'exclude', 'git'))
        statopts['rev'] = ['%u:%u' % (rev0, rev1)]
        statopts['modified'] = True
        statopts['added'] = True
        statopts['removed'] = True
        dialog = GStatus(self.ui, self.repo, self.cwd, [], statopts, False)
        dialog.display()
        return True

    def _vdiff_selected(self, menuitem):
        rev0, rev1 = self._revs
        self.opts['rev'] = ["%s:%s" % (rev0, rev1)]
        self._diff_file(None, '')

    def _mark_rev(self, menuitem):
        rev = self.currow[treemodel.REVID]
        self.graphview.set_mark_rev(rev)

    def _add_tag(self, menuitem):
        from tagadd import TagAddDialog

        rev = self.currow[treemodel.REVID]
        parents = self.currow[treemodel.PARENTS]
        
        # save tag info for detecting new tags added
        oldtags = self.repo.tagslist()
        
        def refresh(*args):
            self.repo.invalidate()
            newtags = self.repo.tagslist()
            if newtags != oldtags:
                self.reload_log()

        dialog = TagAddDialog(self.repo.root, rev=str(rev))
        dialog.set_transient_for(self)
        dialog.connect('destroy', refresh)
        dialog.show_all()
        dialog.present()
        dialog.set_transient_for(None)

    def _show_status(self, menuitem):
        rev = self.currow[treemodel.REVID]
        statopts = {'rev' : [str(rev)] }
        dialog = ChangeSet(self.ui, self.repo, self.cwd, [], statopts, False)
        dialog.display()

    def _export_patch(self, menuitem):
        rev = self.currow[treemodel.REVID]
        filename = "%s_rev%s.patch" % (os.path.basename(self.repo.root), rev)
        fd = NativeSaveFileDialogWrapper(Title = "Save patch to",
                                         InitialDir=self.repo.root,
                                         FileName=filename)
        result = fd.run()

        if result:
            # In case new export args are added in the future, merge the
            # hg defaults
            exportOpts= self.merge_opts(commands.table['^export'][1], ())
            exportOpts['output'] = result
            def dohgexport():
                commands.export(self.ui,self.repo,str(rev),**exportOpts)
            success, outtext = self._hg_call_wrapper("Export",dohgexport,False)

    def _email_patch(self, menuitem):
        from hgemail import EmailDialog
        rev = self.currow[treemodel.REVID]
        dlg = EmailDialog(self.repo.root, ['--rev', str(rev)])
        dlg.set_transient_for(self)
        dlg.show_all()
        dlg.present()
        dlg.set_transient_for(None)

    def _checkout(self, menuitem):
        rev = self.currow[treemodel.REVID]
        parents = [x.node() for x in self.repo.workingctx().parents()]
        dialog = UpdateDialog(self.cwd, rev)
        dialog.set_transient_for(self)
        dialog.show_all()
        dialog.set_notify_func(self.checkout_completed, parents)
        dialog.present()
        dialog.set_transient_for(None)

    def checkout_completed(self, oldparents):
        newparents = [x.node() for x in self.repo.workingctx().parents()]
        if not oldparents == newparents:
            self.reload_log()

    def _merge(self, menuitem):
        rev = self.currow[treemodel.REVID]
        parents = [x.node() for x in self.repo.workingctx().parents()]
        node = short(self.repo.changelog.node(rev))
        dialog = MergeDialog(self.repo.root, self.cwd, node)
        dialog.set_transient_for(self)
        dialog.show_all()
        dialog.set_notify_func(self.merge_completed, parents)
        dialog.present()
        dialog.set_transient_for(None)

    def merge_completed(self, oldparents):
        newparents = [x.node() for x in self.repo.workingctx().parents()]
        if not oldparents == newparents:
            self.reload_log()

    def selection_changed(self, treeview):
        self.currow = self.graphview.get_revision()
        rev = self.currow[treemodel.REVID]
        if rev != self._last_rev:
            self._last_rev = rev
            self.changeview.opts['rev'] = [str(rev)]
            self.changeview.load_details(rev)
        return False

    def _refresh_clicked(self, toolbutton, data=None):
        self.reload_log()
        return True

    def _tree_button_release(self, widget, event) :
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK |
            gtk.gdk.CONTROL_MASK)):
            self._tree_popup_menu(widget, event.button, event.time)
        return False

    def _tree_button_press(self, widget, event):
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK |
            gtk.gdk.CONTROL_MASK)):
            crow = widget.get_path_at_pos(int(event.x), int(event.y))[0]
            (model, pathlist) = widget.get_selection().get_selected_rows()
            if pathlist == []:
                return False
            srow = pathlist[0]
            if srow == crow:
                self._tree_popup_menu(widget, event.button, event.time)
            else:
                self._revs = (int(model[srow][treemodel.REVID]),
                        int(model[crow][treemodel.REVID]))
                self._tree_popup_menu_diff(widget, event.button, event.time)
            return True
        return False

    def _tree_popup_menu(self, treeview, button=0, time=0) :
        selrev = self.currow[treemodel.REVID]
        
        # disable/enable menus as required
        parents = [self.repo.changelog.rev(x.node()) for x in
                   self.repo.workingctx().parents()]
        can_merge = selrev not in parents and \
                    len(self.repo.heads()) > 1 and \
                    len(parents) < 2
        self._cmenu_merge.set_sensitive(can_merge)

        # display the context menu
        self._menu.popup(None, None, None, button, time)
        return True

    def _tree_popup_menu_diff(self, treeview, button=0, time=0):        
        # display the context menu
        self._menu2.popup(None, None, None, button, time)
        return True

    def _tree_row_act(self, tree, path, column) :
        """Default action is the first entry in the context menu
        """
        self._menu.get_children()[0].activate()
        return True

def run(root='', cwd='', files=[], **opts):
    u = ui.ui()
    u.updateopts(debug=False, traceback=False)
    repo = hg.repository(u, path=root)

    files = [util.canonpath(root, cwd, f) for f in files]

    cmdoptions = {
        'follow':False, 'follow-first':False, 'copies':False, 'keyword':[],
        'limit':0, 'rev':[], 'removed':False, 'no_merges':False, 'date':None,
        'only_merges':None, 'prune':[], 'git':False, 'verbose':False,
        'include':[], 'exclude':[]
    }

    dialog = GLog(u, repo, cwd, files, cmdoptions, True)

    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    dialog.display()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or os.getcwd()
    opts['files'] = [opts['root']]
    run(**opts)
