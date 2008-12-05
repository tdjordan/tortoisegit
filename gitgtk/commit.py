#
# commit.py - commit dialog for TortoiseHg
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
from gdialog import *
from gtools import cmdtable
from status import GStatus
from hgcmd import CmdDialog
from hglib import fromutf

class GCommit(GStatus):
    """GTK+ based dialog for displaying repository status and committing changes.

    Also provides related operations like add, delete, remove, revert, refresh,
    ignore, diff, and edit.
    """

    ### Overrides of base class methods ###

    def init(self):
        GStatus.init(self)
        self._last_commit_id = None

    def parse_opts(self):
        GStatus.parse_opts(self)

        # Need an entry, because extdiff code expects it
        if not self.test_opt('rev'):
            self.opts['rev'] = ''

        if self.test_opt('message'):
            buffer = gtk.TextBuffer()
            buffer.set_text(self.opts['message'])
            self.text.set_buffer(buffer)

        if self.test_opt('logfile'):
            buffer = gtk.TextBuffer()
            buffer.set_text('Comment will be read from file ' + self.opts['logfile'])
            self.text.set_buffer(buffer)
            self.text.set_sensitive(False)


    def get_title(self):
        return os.path.basename(self.repo.root) + ' commit ' + ' '.join(self.pats) + ' ' + self.opts['user'] + ' ' + self.opts['date']

    def get_icon(self):
        return 'menucommit.ico'

    def auto_check(self):
        if self.test_opt('check'):
            for entry in self.model : 
                if entry[1] in 'MAR':
                    entry[0] = True
            self._update_check_count()


    def save_settings(self):
        settings = GStatus.save_settings(self)
        settings['gcommit'] = self._vpaned.get_position()
        return settings


    def load_settings(self, settings):
        GStatus.load_settings(self, settings)
        if settings:
            self._setting_vpos = settings['gcommit']
        else:
            self._setting_vpos = -1


    def get_tbbuttons(self):
        tbbuttons = GStatus.get_tbbuttons(self)
        tbbuttons.insert(2, gtk.SeparatorToolItem())
        self._undo_button = self.make_toolbutton(gtk.STOCK_UNDO, '_Undo',
            self._undo_clicked, tip='undo recent commit')
        tbbuttons.insert(2, self._undo_button)
        tbbuttons.insert(2, self.make_toolbutton(gtk.STOCK_OK, '_Commit',
            self._commit_clicked, tip='commit'))
        return tbbuttons


    def changed_cb(self, combobox):
        model = combobox.get_model()
        index = combobox.get_active()
        if index >= 0:
            buffer = self.text.get_buffer()
            begin, end = buffer.get_bounds()
            cur_msg = buffer.get_text(begin, end)
            if len(cur_msg):
                response = Confirm('Discard Message', [], self,
                        'Discard current commit message?').run()
                if response != gtk.RESPONSE_YES:
                    return
            buffer.set_text(model[index][1])

    def _update_recent_messages(self, msg=None):
        if msg is not None:
            self._mru_messages.add(msg)
            self.settings.write()

        liststore = self.msg_cbbox.get_model()
        liststore.clear()
        for msg in self._mru_messages:
            sumline = msg.split("\n")[0]
            liststore.append([sumline, msg])
        #self.msg_cbbox.set_active(-1)

    def get_body(self):
        status_body = GStatus.get_body(self)

        vbox = gtk.VBox()
        
        mbox = gtk.HBox()
        label = gtk.Label('Recent Commit Messages: ')
        mbox.pack_start(label, False, False, 2)
        self.msg_cbbox = gtk.combo_box_new_text()
        liststore = gtk.ListStore(str, str)
        self.msg_cbbox = gtk.ComboBox(liststore)
        cell = gtk.CellRendererText()
        self.msg_cbbox.pack_start(cell, True)
        self.msg_cbbox.add_attribute(cell, 'text', 0)
        #cell = gtk.CellRendererText()
        #self.msg_cbbox.pack_start(cell, True)
        #self.msg_cbbox.add_attribute(cell, 'text', 1)
        mbox.pack_start(self.msg_cbbox)
        vbox.pack_start(mbox, False, False)
        self._mru_messages = self.settings.mrul('recent_messages')
        self._update_recent_messages()
        self.msg_cbbox.connect('changed', self.changed_cb)
        
        frame = gtk.Frame()
        frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        frame.add(scroller)
        vbox.pack_start(frame)
        
        self.text = gtk.TextView()
        self.text.set_wrap_mode(gtk.WRAP_WORD)
        self.text.modify_font(pango.FontDescription(self.fontcomment))
        scroller.add(self.text)
        
        self._vpaned = gtk.VPaned()
        self._vpaned.add1(vbox)
        self._vpaned.add2(status_body)
        self._vpaned.set_position(self._setting_vpos)
        return self._vpaned


    def get_menu_info(self):
        """Returns menu info in this order: merge, addrem, unknown, clean, ignored, deleted
        """
        merge, addrem, unknown, clean, ignored, deleted  = GStatus.get_menu_info(self)
        return (merge + (('_commit', self._commit_file),),
                addrem + (('_commit', self._commit_file),),
                unknown + (('_commit', self._commit_file),),
                clean,
                ignored,
                deleted + (('_commit', self._commit_file),))


    def should_live(self, widget=None, event=None):
        # If there are more than a few character typed into the commit
        # message, ask if the exit should continue.
        live = False
        if self.text.get_buffer().get_char_count() > 10:
            dialog = Confirm('Exit', [], self, 'Discard commit message and exit?')
            if dialog.run() == gtk.RESPONSE_NO:
                live = True
        return live


    def reload_status(self):
        success = GStatus.reload_status(self)
        self._check_merge()
        self._check_undo()
        return success


    ### End of overridable methods ###

    def _check_undo(self):
        can_undo = os.path.exists(self.repo.sjoin("undo")) and \
                self._last_commit_id is not None
        self._undo_button.set_sensitive(can_undo)


    def _check_merge(self):
        # disable the checkboxes on the filelist if repo in merging state
        merged = len(self.repo.workingctx().parents()) > 1
        cbcell = self.tree.get_column(0).get_cell_renderers()[0]
        cbcell.set_property("activatable", not merged)
        
        self.get_toolbutton('Re_vert').set_sensitive(not merged)
        self.get_toolbutton('_Add').set_sensitive(not merged)
        self.get_toolbutton('_Remove').set_sensitive(not merged)
        self.get_toolbutton('_Select').set_sensitive(not merged)
        self.get_toolbutton('_Deselect').set_sensitive(not merged)
        
        if merged:
            # select all changes if repo is merged
            for entry in self.model:
                if entry[1] in 'MARD':
                    entry[0] = True
            self._update_check_count()

            # pre-fill commit message
            self.text.get_buffer().set_text('merge')


    def _commit_clicked(self, toolbutton, data=None):
        if not self._ready_message():
            return True

        if len(self.repo.workingctx().parents()) > 1:
            # as of Mercurial 1.0, merges must be committed without
            # specifying file list.
            self._hg_commit([])
        else:
            commitable = 'MAR'
            addremove_list = self._relevant_files('?!')
            if len(addremove_list) and self._should_addremove(addremove_list):
                commitable += '?!'

            commit_list = self._relevant_files(commitable)
            if len(commit_list) > 0:
                self._hg_commit(commit_list)
            else:
                Prompt('Nothing Commited', 'No committable files selected', self).run()
        return True


    def _commit_file(self, stat, file):
        if self._ready_message():
            if stat not in '?!' or self._should_addremove([file]):
                self._hg_commit([file])
        return True


    def _undo_clicked(self, toolbutton, data=None):
        response = Confirm('Undo commit', [], self, 'Undo last commit').run() 
        if response != gtk.RESPONSE_YES:
            return
            
        tip = self._get_tip_rev(True)
        if not tip == self._last_commit_id:
            Prompt('Undo commit', 
                    'Unable to undo!\n\n'
                    'Tip revision differs from last commit.',
                    self).run()
            return
            
        try:
            self.repo.rollback()
            self._last_commit_id = None
            self.reload_status()
        except:
            Prompt('Undo commit', 'Errors during rollback!',
                    self).run()


    def _should_addremove(self, files):
        if self.test_opt('addremove'):
            return True
        else:
            response = Confirm('Add/Remove', files, self).run() 
            if response == gtk.RESPONSE_YES:
                # This will stay set for further commits (meaning no more prompts). Problem?
                self.opts['addremove'] = True
                return True
        return False


    def _ready_message(self):
        begin, end = self.text.get_buffer().get_bounds()
        message = self.text.get_buffer().get_text(begin, end) 
        if not self.test_opt('logfile') and not message:
            Prompt('Nothing Commited', 'Please enter commit message', self).run()
            self.text.grab_focus()
            return False
        else:
            if not self.test_opt('logfile'):
                self.opts['message'] = message
            return True


    def _hg_commit(self, files):
        if not self.repo.ui.config('ui', 'username'):
            Prompt('Username not configured', 'Please enter a username', self).run()
            from thgconfig import ConfigDialog
            dlg = ConfigDialog(self.repo.root, False)
            dlg.show_all()
            dlg.focus_field('ui.username')
            dlg.run()
            dlg.hide()
            self.repo = hg.repository(ui.ui(), self.repo.root)
            self.ui = self.repo.ui

        # call the threaded CmdDialog to do the commit, so the the large commit
        # won't get locked up by potential large commit. CmdDialog will also
        # display the progress of the commit operation.
        cmdline  = ["hg", "commit", "--verbose", "--repository", self.repo.root]
        if self.opts['addremove']:
            cmdline += ['--addremove']
        cmdline += ['--message', fromutf(self.opts['message'])]
        cmdline += [self.repo.wjoin(x) for x in files]
        dialog = CmdDialog(cmdline, True)
        dialog.set_transient_for(self)
        dialog.run()
        dialog.hide()

        # refresh overlay icons and commit dialog
        if dialog.return_code() == 0:
            self.text.set_buffer(gtk.TextBuffer())
            self._update_recent_messages(self.opts['message'])
            shell_notify([self.cwd] + files)
            self._last_commit_id = self._get_tip_rev(True)
            self.reload_status()

    def _get_tip_rev(self, refresh=False):
        if refresh:
            self.repo.invalidate()
        cl = self.repo.changelog
        tip = cl.node(nullrev + cl.count())
        return hex(tip)

def launch(root='', files=[], cwd='', main=True):
    u = ui.ui()
    u.updateopts(debug=False, traceback=False)
    repo = hg.repository(u, path=root)
    
    # move cwd to repo root if repo is merged, so we can show
    # all the changed files
    if len(repo.workingctx().parents()) > 1 and repo.root != cwd:
        cwd = repo.root
        repo = hg.repository(u, path=cwd)
        files = [cwd]

    ct = repo.ui.config('tortoisehg', 'commit', 'internal')
    if ct not in ['', 'internal']:
        from hglib import thgdispatch
        args = ['--repository', root, ct]
        try:
            ret = thgdispatch(repo.ui, args=args)
        except SystemExit:
            pass
        return None

    cmdoptions = {
        'user':'', 'date':'',
        'modified':True, 'added':True, 'removed':True, 'deleted':True,
        'unknown':False, 'ignored':False, 
        'exclude':[], 'include':[],
        'check': False, 'git':False, 'logfile':'', 'addremove':False,
    }
    
    dialog = GCommit(u, repo, cwd, files, cmdoptions, main)
    dialog.display()
    return dialog
    
def run(root='', files=[], cwd='', **opts):
    # If no files or directories were selected, take current dir
    # TODO: Not clear if this is best; user may expect repo wide
    if not files and cwd:
        files = [cwd]
    if launch(root, files, cwd, True):
        gtk.gdk.threads_init()
        gtk.gdk.threads_enter()
        gtk.main()
        gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    from hglib import rootpath

    opts = {}
    opts['cwd'] = len(sys.argv) > 1 and sys.argv[1] or os.getcwd()
    opts['root'] = rootpath(opts['cwd'])
    run(**opts)
