#
# status.py - status dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#


import os
import threading
import StringIO
import sys
import shutil
import tempfile
import datetime
import cPickle

import pygtk
pygtk.require('2.0')
import gtk
import gobject
import pango

from mercurial.i18n import _
from mercurial.node import *
from mercurial import cmdutil, util, ui, hg, commands, patch
from hgext import extdiff
from shlib import shell_notify
from hglib import toutf
from gdialog import *

class GStatus(GDialog):
    """GTK+ based dialog for displaying repository status

    Also provides related operations like add, delete, remove, revert, refresh,
    ignore, diff, and edit.

    The following methods are meant to be overridden by subclasses. At this
    point GCommit is really the only intended subclass.

        auto_check(self)
        get_menu_info(self)
    """

    ### Following methods are meant to be overridden by subclasses ###

    def init(self):
        GDialog.init(self)
        
    def auto_check(self):
        if self.test_opt('check'):
            for entry in self.model : entry[0] = True
            self._update_check_count()


    def get_menu_info(self):
        """Returns menu info in this order:
            merge, addrem, unknown, clean, ignored, deleted 
        """
        return (
                (('_difference', self._diff_file),
                    ('_view right', self._view_file), 
                    ('view _left', self._view_left_file),
                    ('_revert', self._revert_file),
                    ('l_og', self._log_file)),
                (('_difference', self._diff_file),
                    ('_view', self._view_file), 
                    ('_revert', self._revert_file), 
                    ('l_og', self._log_file)),
                (('_view', self._view_file),
                    ('_delete', self._delete_file), 
                    ('_add', self._add_file),
                    ('_ignore', self._ignore_file)),
                (('_view', self._view_file),
                    ('re_move', self._remove_file),
                    ('l_og', self._log_file)),
                (('_view', self._view_file),
                    ('_delete', self._delete_file)),
                (('_view', self._view_file),
                    ('_revert', self._revert_file), 
                    ('re_move', self._remove_file),
                    ('l_og', self._log_file))
                )

    ### End of overridable methods ###


    ### Overrides of base class methods ###

    def parse_opts(self):
        self._ready = False

        # Determine which files to display
        if self.test_opt('all'):
            for check in self._show_checks.values():
                check.set_active(True)
        else:
            set = False
            for opt in self.opts :
                if opt in self._show_checks and self.opts[opt]:
                    set = True
                    self._show_checks[opt].set_active(True)
            if not set:
                for check in [item[1] for item in self._show_checks.iteritems() 
                              if item[0] in ('modified', 'added', 'removed', 
                                             'deleted', 'unknown')]:
                    check.set_active(True)


    def get_title(self):
        return os.path.basename(self.repo.root) + ' status ' + ':'.join(self.opts['rev'])  + ' ' + ' '.join(self.pats)

    def get_icon(self):
        return 'menushowchanged.ico'

    def get_defsize(self):
        return self._setting_defsize


    def get_tbbuttons(self):
        tbuttons = [self.make_toolbutton(gtk.STOCK_REFRESH, 'Re_fresh',
            self._refresh_clicked, tip='refresh'),
                     gtk.SeparatorToolItem()]

        if self.count_revs() < 2:
            tbuttons += [
                    self.make_toolbutton(gtk.STOCK_MEDIA_REWIND, 'Re_vert',
                        self._revert_clicked, tip='revert'),
                    self.make_toolbutton(gtk.STOCK_ADD, '_Add',
                        self._add_clicked, tip='add'),
                    self.make_toolbutton(gtk.STOCK_DELETE, '_Remove',
                        self._remove_clicked, tip='remove'),
                    gtk.SeparatorToolItem(),
                    self.make_toolbutton(gtk.STOCK_YES, '_Select',
                        self._sel_desel_clicked, True, tip='select'),
                    self.make_toolbutton(gtk.STOCK_NO, '_Deselect',
                        self._sel_desel_clicked, False, tip='deselect'),
                    gtk.SeparatorToolItem()]

        self.showdiff_toggle = gtk.ToggleToolButton(gtk.STOCK_JUSTIFY_FILL)
        self.showdiff_toggle.set_use_underline(True)
        self.showdiff_toggle.set_label('_Show Diff')
        self.showdiff_toggle.set_tooltip(self.tooltips, 'show diff pane')
        self.showdiff_toggle.set_active(False)
        self._showdiff_toggled_id = self.showdiff_toggle.connect('toggled', self._showdiff_toggled )
        tbuttons.append(self.showdiff_toggle)
        return tbuttons


    def save_settings(self):
        settings = GDialog.save_settings(self)
        settings['gstatus'] = (self._diffpane.get_position(), self._setting_lastpos)
        return settings


    def load_settings(self, settings):
        GDialog.load_settings(self, settings)
        if settings:
            mysettings = settings['gstatus']
            self._setting_pos = mysettings[0]
            self._setting_lastpos = mysettings[1]
        else:
            self._setting_pos = 64000
            self._setting_lastpos = 270


    def get_body(self):
        self.connect('map-event', self._displayed)

        # TODO: should generate menus dynamically during right-click, currently
        # there can be entires that are not always supported or relavant.
        merge, addrem, unknown, clean, ignored, deleted  = self.get_menu_info()
        merge_menu = self.make_menu(merge)
        addrem_menu = self.make_menu(addrem)
        unknown_menu = self.make_menu(unknown)
        clean_menu = self.make_menu(clean)
        ignored_menu = self.make_menu(ignored)
        deleted_menu = self.make_menu(deleted)

        # Dictionary with a key of file-stat and values containing context-menus
        self._menus = {}
        self._menus['M'] = merge_menu
        self._menus['A'] = addrem_menu
        self._menus['R'] = addrem_menu
        self._menus['?'] = unknown_menu
        self._menus['C'] = clean_menu
        self._menus['I'] = ignored_menu
        self._menus['!'] = deleted_menu

        # model stores the file list.
        # model[0] = file checked (marked for commit)
        # model[1] = changetype char
        # model[2] = file path as UTF-8
        # model[3] = file path
        self.model = gtk.ListStore(bool, str, str, str)
        self.model.set_sort_func(1001, self._sort_by_stat)
        self.model.set_default_sort_func(self._sort_by_stat)

        self.tree = gtk.TreeView(self.model)
        self.tree.connect('button-press-event', self._tree_button_press)
        self.tree.connect('button-release-event', self._tree_button_release)
        self.tree.connect('popup-menu', self._tree_popup_menu)
        self.tree.connect('row-activated', self._tree_row_act)
        self.tree.connect('key-press-event', self._tree_key_press)
        self.tree.set_reorderable(False)
        self.tree.set_enable_search(True)
        self.tree.set_search_column(2)
        self.tree.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        self.tree.get_selection().connect('changed',
                self._tree_selection_changed, False)
        if hasattr(self.tree, 'set_rubber_banding'):
            self.tree.set_rubber_banding(True)
        self.tree.modify_font(pango.FontDescription(self.fontlist))
        self.tree.set_headers_clickable(True)
        
        toggle_cell = gtk.CellRendererToggle()
        toggle_cell.connect('toggled', self._select_toggle)
        toggle_cell.set_property('activatable', True)

        path_cell = gtk.CellRendererText()
        stat_cell = gtk.CellRendererText()

        if self.count_revs() < 2:
            col0 = gtk.TreeViewColumn('select', toggle_cell)
            col0.add_attribute(toggle_cell, 'active', 0)
            col0.set_sort_column_id(0)
            col0.set_resizable(False)
            self.tree.append_column(col0)
        
        col1 = gtk.TreeViewColumn('st', stat_cell)
        col1.add_attribute(stat_cell, 'text', 1)
        col1.set_cell_data_func(stat_cell, self._text_color)
        col1.set_sort_column_id(1001)
        col1.set_resizable(False)
        self.tree.append_column(col1)
        
        col2 = gtk.TreeViewColumn('path', path_cell)
        col2.add_attribute(path_cell, 'text', 2)
        col2.set_cell_data_func(path_cell, self._text_color)
        col2.set_sort_column_id(2)
        col2.set_resizable(True)
        self.tree.append_column(col2)
       
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(self.tree)
        
        tree_frame = gtk.Frame()
        tree_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        tree_frame.add(scroller)

        diff_frame = gtk.Frame()
        diff_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        diff_frame.add(scroller)
        
        self.diff_text = gtk.TextView()
        self.diff_text.set_wrap_mode(gtk.WRAP_NONE)
        self.diff_text.set_editable(False)
        self.diff_text.modify_font(pango.FontDescription(self.fontdiff))
        scroller.add(self.diff_text)

        if self.diffbottom:
            self._diffpane = gtk.VPaned()
        else:
            self._diffpane = gtk.HPaned()

        self._diffpane.pack1(tree_frame, True, False)
        self._diffpane.pack2(diff_frame, True, True)
        self._diffpane.set_position(self._setting_pos)
        self._diffpane_moved_id = self._diffpane.connect('notify::position', self._diffpane_moved)
        return self._diffpane


    def get_extras(self):
        table = gtk.Table(rows=2, columns=3)
        table.set_col_spacings(8)

        self._show_checks = {}
        row, col = 0, 0
        checks = ('modified', 'added', 'removed')
        if self.count_revs() <= 1:
            checks += ('deleted', 'unknown', 'clean', 'ignored')

        for type in checks:
            check = gtk.CheckButton('_' + type)
            check.connect('toggled', self._show_toggle, type)
            table.attach(check, col, col+1, row, row+1)
            self._show_checks[type] = check
            col += row
            row = not row
            
        self.counter = gtk.Label('')
        self.counter.set_alignment(1.0, 0.0) # right up

        hbox = gtk.HBox()
        hbox.pack_start(table, expand=False)
        hbox.pack_end(self.counter, expand=True, padding=2)
        
        return hbox

    def _update_check_count(self):
        file_count = 0
        check_count = 0
        for row in self.model:
            file_count = file_count + 1
            if row[0]:
                check_count = check_count + 1
        self.counter.set_text(_('%d selected, %d total') % (check_count, file_count))

    def prepare_display(self):
        self._ready = True
        self._last_files = []
        # If the status load failed, no reason to continue
        if not self.reload_status():
            raise util.Abort('could not load status')
        self.auto_check()


    def _displayed(self, widget, event):
        self._diffpane_moved(self._diffpane)
        return False


    def should_live(self, widget=None, event=None):
        return False

    ### End of overrides ###

    def _do_reload_status(self):
        """Clear out the existing ListStore model and reload it from the repository status. 
        Also recheck and reselect files that remain in the list.
        """
        self.repo.dirstate.invalidate()
        self.repo.invalidate()

        # The following code was copied from the status function in mercurial\commands.py
        # and modified slightly to work here
        
        # node2 is None (the working dir) when 0 or 1 rev is specificed
        self._node1, self._node2 = cmdutil.revpair(self.repo, self.opts.get('rev'))
    
        files, matchfn, anypats = cmdutil.matchpats(self.repo, self.pats, self.opts)
        cwd = (self.pats and self.repo.getcwd()) or ''
        modified, added, removed, deleted, unknown, ignored, clean = [
            n for n in self.repo.status(node1=self._node1, node2=self._node2, files=files,
                                 match=matchfn,
                                 list_ignored=self.test_opt('ignored'),
                                 list_clean=self.test_opt('clean'))]

        changetypes = (('modified', 'M', modified),
                       ('added', 'A', added),
                       ('removed', 'R', removed),
                       ('deleted', '!', deleted),
                       ('unknown', '?', unknown),
                       ('ignored', 'I', ignored))
    
        explicit_changetypes = changetypes + (('clean', 'C', clean),)

        # List of the currently checked and selected files to pass on to the new data
        recheck = [entry[2] for entry in self.model if entry[0]]
        reselect = [self.model[iter][2] for iter in self.tree.get_selection().get_selected_rows()[1]]

        # Load the new data into the tree's model
        self.tree.hide()
        self.model.clear()
    
        for opt, char, changes in ([ct for ct in explicit_changetypes
                                    if self.test_opt(ct[0])] or changetypes) :
            for file in changes:
                file = util.localpath(file)
                self.model.append([file in recheck, char, toutf(file), file])

        self._update_check_count()
        
        selection = self.tree.get_selection()
        selected = False
        for row in self.model:
            if row[2] in reselect:
                selection.select_iter(row.iter)
                selected = True

        if not selected:
            selection.select_path((0,))

        self.tree.show()
        self.tree.grab_focus()
        return True


    def reload_status(self):
        if not self._ready: return False
        success, outtext = self._hg_call_wrapper('Status', self._do_reload_status)
        return success


    def make_menu(self, entries):
        menu = gtk.Menu()
        for entry in entries:
            menu.append(self._make_menuitem(entry[0], entry[1]))
        menu.set_size_request(90, -1)
        menu.show_all()
        return menu


    def _make_menuitem(self, label, handler):
        menuitem = gtk.MenuItem(label, True)
        menuitem.connect('activate', self._context_menu_act, handler)
        menuitem.set_border_width(1)
        return menuitem


    def _select_toggle(self, cellrenderer, path):
        self.model[path][0] = not self.model[path][0]
        self._update_check_count()
        return True


    def _show_toggle(self, check, type):
        self.opts[type] = check.get_active()
        self.reload_status()
        return True


    def _sort_by_stat(self, model, iter1, iter2):
        order = 'MAR!?IC'
        lhs, rhs = (model.get_value(iter1, 1), model.get_value(iter2, 1))

        # GTK+ bug that calls sort before a full row is inserted causing values to be None.
        # When this happens, just return any value since the call is irrelevant and will be
        # followed by another with the correct (non-None) value
        if None in (lhs, rhs) :
            return 0

        result = order.find(lhs) - order.find(rhs)
        return min(max(result, -1), 1)
        

    def _text_color(self, column, text_renderer, list, row_iter):
        stat = list[row_iter][1]
        if stat == 'M':  
            text_renderer.set_property('foreground', '#000090')
        elif stat == 'A':
            text_renderer.set_property('foreground', '#006400')
        elif stat == 'R':
            text_renderer.set_property('foreground', '#900000')
        elif stat == 'C':
            text_renderer.set_property('foreground', 'black')
        elif stat == '!':
            text_renderer.set_property('foreground', 'red')
        elif stat == '?':
            text_renderer.set_property('foreground', '#AA5000')
        elif stat == 'I':
            text_renderer.set_property('foreground', 'black')
        else:
            text_renderer.set_property('foreground', 'black')


    def _view_left_file(self, stat, file):
        return self._view_file(stat, file, True)


    def _remove_file(self, stat, file):
        self._hg_remove([file])
        return True


    def _hg_remove(self, files):
        wfiles = [self.repo.wjoin(x) for x in files]
        if self.count_revs() > 1:
            Prompt('Nothing Removed', 'Remove is not enabled when multiple revisions are specified.', self).run()
            return

        # Create new opts, so nothing unintented gets through
        removeopts = self.merge_opts(commands.table['^remove|rm'][1], ('include', 'exclude'))
        def dohgremove():
            commands.remove(self.ui, self.repo, *wfiles, **removeopts)
        success, outtext = self._hg_call_wrapper('Remove', dohgremove)
        if success:
            self.reload_status()


    def _tree_selection_changed(self, selection, force):
        ''' Update the diff text '''
        def dohgdiff():
            difftext = StringIO.StringIO()
            try:
                if len(files) != 0:
                    wfiles = [self.repo.wjoin(x) for x in files]
                    fns, matchfn, anypats = cmdutil.matchpats(self.repo, wfiles, self.opts)
                    patch.diff(self.repo, self._node1, self._node2, fns, match=matchfn,
                               fp=difftext, opts=patch.diffopts(self.ui, self.opts))

                buffer = gtk.TextBuffer()
                buffer.create_tag('removed', foreground='#900000')
                buffer.create_tag('added', foreground='#006400')
                buffer.create_tag('position', foreground='#FF8000')
                buffer.create_tag('header', foreground='#000090')

                difftext.seek(0)
                iter = buffer.get_start_iter()
                for line in difftext:
                    line = toutf(line)
                    if line.startswith('---') or line.startswith('+++'):
                        buffer.insert_with_tags_by_name(iter, line, 'header')
                    elif line.startswith('-'):
                        buffer.insert_with_tags_by_name(iter, line, 'removed')
                    elif line.startswith('+'):
                        buffer.insert_with_tags_by_name(iter, line, 'added')
                    elif line.startswith('@@'):
                        buffer.insert_with_tags_by_name(iter, line, 'position')
                    else:
                        buffer.insert(iter, line)

                self.diff_text.set_buffer(buffer)
            finally:
                difftext.close()

        if self.showdiff_toggle.get_active():
            files = [self.model[iter][3] for iter in self.tree.get_selection().get_selected_rows()[1]]
            if force or files != self._last_files:
                self._last_files = files
                self._hg_call_wrapper('Diff', dohgdiff)
        return False


    def _showdiff_toggled(self, togglebutton, data=None):
        # prevent movement events while setting position
        self._diffpane.handler_block(self._diffpane_moved_id)

        if togglebutton.get_active():
            self._tree_selection_changed(self.tree.get_selection(), True)
            self._diffpane.set_position(self._setting_lastpos)
        else:
            self._setting_lastpos = self._diffpane.get_position()
            self._diffpane.set_position(64000)
            self.diff_text.set_buffer(gtk.TextBuffer())

        self._diffpane.handler_unblock(self._diffpane_moved_id)
        return True


    def _diffpane_moved(self, paned, data=None):
        # prevent toggle events while setting toolbar state
        self.showdiff_toggle.handler_block(self._showdiff_toggled_id)
        if self.diffbottom:
            sizemax = self._diffpane.get_allocation().height
        else:
            sizemax = self._diffpane.get_allocation().width

        if self.showdiff_toggle.get_active():
            if paned.get_position() >=  sizemax - 55:
                self.showdiff_toggle.set_active(False)
                self.diff_text.set_buffer(gtk.TextBuffer())
        elif paned.get_position() < sizemax - 55:
            self.showdiff_toggle.set_active(True)
            self._tree_selection_changed(self.tree.get_selection(), True)

        self.showdiff_toggle.handler_unblock(self._showdiff_toggled_id)
        return False
        

    def _refresh_clicked(self, toolbutton, data=None):
        self.reload_status()
        return True


    def _revert_clicked(self, toolbutton, data=None):
        revert_list = self._relevant_files('MAR!')
        if len(revert_list) > 0:
            self._hg_revert(revert_list)
        else:
            Prompt('Nothing Reverted', 'No revertable files selected', self).run()
        return True


    def _revert_file(self, stat, file):
        self._hg_revert([file])
        return True


    def _log_file(self, stat, file):
        from gtools import cmdtable
        from history import GLog
        
        # Might want to include 'rev' here... trying without
        statopts = self.merge_opts(cmdtable['glog|ghistory'][1], ('include', 'exclude', 'git'))
        dialog = GLog(self.ui, self.repo, self.cwd, [file], statopts, False)
        dialog.display()
        return True


    def _hg_revert(self, files):
        wfiles = [self.repo.wjoin(x) for x in files]
        if self.count_revs() > 1:
            Prompt('Nothing Reverted', 'Revert is not enabled when multiple revisions are specified.', self).run()
            return

        # Create new opts,  so nothing unintented gets through.
        # commands.table revert key changed after 0.9.5, in change d4ec6d61b3ee
        key = '^revert' in commands.table and '^revert' or 'revert'
        revertopts = self.merge_opts(commands.table[key][1], ('include', 'exclude', 'rev'))
        def dohgrevert():
            commands.revert(self.ui, self.repo, *wfiles, **revertopts)

        # TODO: Ask which revision when multiple parents (currently just shows abort message)
        # TODO: Don't need to prompt when reverting added or removed files
        if self.count_revs() == 1:
            # rev options needs extra tweaking since is not an array for revert command
            revertopts['rev'] = revertopts['rev'][0]
            dialog = Confirm('Revert', files, self, 'Revert files to revision ' + revertopts['rev'] + '?')
        else:
            dialog = Confirm('Revert', files, self)
        if dialog.run() == gtk.RESPONSE_YES:
            success, outtext = self._hg_call_wrapper('Revert', dohgrevert)
            if success:
                shell_notify(wfiles)
                self.reload_status()

    def _add_clicked(self, toolbutton, data=None):
        add_list = self._relevant_files('?')
        if len(add_list) > 0:
            self._hg_add(add_list)
        else:
            Prompt('Nothing Added', 'No addable files selected', self).run()
        return True


    def _add_file(self, stat, file):
        self._hg_add([file])
        return True


    def _hg_add(self, files):
        wfiles = [self.repo.wjoin(x) for x in files]
        # Create new opts, so nothing unintented gets through
        addopts = self.merge_opts(commands.table['^add'][1], ('include', 'exclude'))
        def dohgadd():
            commands.add(self.ui, self.repo, *wfiles, **addopts)
        success, outtext = self._hg_call_wrapper('Add', dohgadd)
        if success:
            shell_notify(wfiles)
            self.reload_status()


    def _remove_clicked(self, toolbutton, data=None):
        remove_list = self._relevant_files('C')
        delete_list = self._relevant_files('?I')
        if len(remove_list) > 0:
            self._hg_remove(remove_list)
        if len(delete_list) > 0:
            self._delete_files(delete_list)
        if not remove_list and not delete_list:
            Prompt('Nothing Removed', 'No removable files selected', self).run()
        return True

    def _delete_file(self, stat, file):
        self._delete_files([file])

    def _delete_files(self, files):
        dialog = Confirm('Delete unrevisioned', files, self)
        if dialog.run() == gtk.RESPONSE_YES :
            errors = ''
            for file in files:
                try: 
                    os.unlink(self.repo.wjoin(file))
                except Exception, inst:
                    errors += str(inst) + '\n\n'

            if errors:
                errors = errors.replace('\\\\', '\\')
                if len(errors) > 500:
                    errors = errors[:errors.find('\n',500)] + '\n...'
                Prompt('Delete Errors', errors, self).run()

            self.reload_status()
        return True


    def _ignore_file(self, stat, file):
        ignore = open(self.repo.wjoin('.hgignore'), 'a')
        try:
            try:
                ignore.write('glob:' + util.pconvert(file) + '\n')
            except IOError:
                Prompt('Ignore Failed', 'Could not update .hgignore', self).run()
        finally:
            ignore.close()
        self.reload_status()
        return True


    def _sel_desel_clicked(self, toolbutton, state):
        for entry in self.model : entry[0] = state
        self._update_check_count()
        return True


    def _relevant_files(self, stats):
        return [item[3] for item in self.model if item[0] and item[1] in stats]


    def _context_menu_act(self, menuitem, handler):
        selection = self.tree.get_selection()
        assert(selection.count_selected_rows() == 1)

        list, paths = selection.get_selected_rows() 
        path = paths[0]
        handler(list[path][1], list[path][2])
        return True


    def _tree_button_press(self, widget, event) :
        # Set the flag to ignore the next activation when the shift/control keys are
        # pressed. This avoids activations with multiple rows selected.
        if event.type == gtk.gdk._2BUTTON_PRESS and  \
          (event.state & (gtk.gdk.SHIFT_MASK | gtk.gdk.CONTROL_MASK)):
            self._ignore_next_act = True
        else:
            self._ignore_next_act = False
        return False


    def _tree_button_release(self, widget, event) :
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK | gtk.gdk.CONTROL_MASK)):
            self._tree_popup_menu(widget, event.button, event.time)
        return False


    def _tree_popup_menu(self, widget, button=0, time=0) :
        selection = self.tree.get_selection()
        if selection.count_selected_rows() != 1:
            return False

        list, paths = selection.get_selected_rows() 
        path = paths[0]
        menu = self._menus[list[path][1]]
        menu.popup(None, None, None, button, time)
        return True


    def _tree_key_press(self, tree, event):
        if event.keyval == 32:
            def toggler(list, path, iter):
                list[path][0] = not list[path][0]

            selection = self.tree.get_selection()
            selection.selected_foreach(toggler)
            return True
        return False


    def _tree_row_act(self, tree, path, column) :
        """Default action is the first entry in the context menu
        """
        # Ignore activations (like double click) on the first column,
        # and ignore all actions if the flag is set
        if column.get_sort_column_id() == 0 or self._ignore_next_act:
            self._ignore_next_act = False
            return True

        selection = self.tree.get_selection()
        if selection.count_selected_rows() != 1:
            return False

        list, paths = selection.get_selected_rows() 
        path = paths[0]
        menu = self._menus[list[path][1]]
        menu.get_children()[0].activate()
        return True

def run(root='', cwd='', files=[], **opts):
    u = ui.ui()
    u.updateopts(debug=False, traceback=False)
    repo = hg.repository(u, path=root)

    cmdoptions = {
        'all':False, 'clean':False, 'ignored':False, 'modified':True,
        'added':True, 'removed':True, 'deleted':True, 'unknown':False, 'rev':[],
        'exclude':[], 'include':[], 'debug':True,'verbose':True,'git':False
    }
    
    dialog = GStatus(u, repo, cwd, files, cmdoptions, True)

    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    dialog.display()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or ''
    run(**opts)
