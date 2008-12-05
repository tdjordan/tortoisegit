#
# Repository synchronization dialog for TortoiseHg
#
# Copyright (C) 2007 Steve Borho <steve@borho.org>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

try:
    import pygtk
    pygtk.require("2.0")
except:
    pass

import gtk
import gobject
import pango
import Queue
import os
import threading
from mercurial import hg, ui, util, extensions
from mercurial.repo import RepoError
from dialog import error_dialog, question_dialog, info_dialog
from hglib import HgThread, toutf
import shlib
import gtklib

class SynchDialog(gtk.Window):
    def __init__(self, cwd='', root = '', repos=[]):
        """ Initialize the Dialog. """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        shlib.set_tortoise_icon(self, 'menusynch.ico')
        self.root = root
        self.cwd = cwd
        self.selected_path = None
        self.hgthread = None
        
        # persistent app data
        self._settings = shlib.Settings('synch')
        self._recent_src = self._settings.mrul('src_paths')

        self.set_default_size(610, 400)

        self.paths = self._get_paths()
        self.origchangecount = self.repo.changelog.count()

        # load the fetch extension explicitly
        extensions.load(self.ui, 'fetch', None)

        name = self.repo.ui.config('web', 'name') or os.path.basename(root)
        self.set_title("TortoiseHg Synchronize - " + name)

        self.connect('delete-event', self._delete)

        # toolbar
        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()
        self._stop_button = self._toolbutton(gtk.STOCK_STOP,
                'Stop', self._stop_clicked, tip='Stop the hg operation')
        self._stop_button.set_sensitive(False)
        tbuttons = [
                self._toolbutton(gtk.STOCK_GO_DOWN,
                                 'Incoming', 
                                 self._incoming_clicked,
                                 tip='Display changes that can be pulled'
                                 ' from selected repository'),
                self._toolbutton(gtk.STOCK_GOTO_BOTTOM,
                                 '   Pull   ',
                                 self._pull_clicked,
                                 self._pull_menu(),
                                 tip='Pull changes from selected'
                                 ' repository'),
                gtk.SeparatorToolItem(),
                self._toolbutton(gtk.STOCK_GO_UP,
                                 'Outgoing',
                                 self._outgoing_clicked,
                                 tip='Display local changes that will be pushed'
                                 ' to selected repository'),
                self._toolbutton(gtk.STOCK_GOTO_TOP,
                                 'Push',
                                 self._push_clicked,
                                 tip='Push local changes to selected'
                                 ' repository'),
                self._toolbutton(gtk.STOCK_GOTO_LAST,
                                 'Email',
                                 self._email_clicked,
                                 tip='Email local outgoing changes to'
                                 ' one or more recipients'),
                gtk.SeparatorToolItem(),
                self._stop_button,
                gtk.SeparatorToolItem(),
                self._toolbutton(gtk.STOCK_PREFERENCES,
                                 'Configure',
                                 self._conf_clicked,
                                 tip='Configure peer repository paths'),
                gtk.SeparatorToolItem(),
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        sep = gtk.SeparatorToolItem()
        sep.set_expand(True)
        sep.set_draw(False)
        self.tbar.insert(sep, -1)
        button = self._toolbutton(gtk.STOCK_CLOSE, 'Quit',
                self._close_clicked, tip='Quit Application')
        self.tbar.insert(button, -1)
        vbox = gtk.VBox()
        self.add(vbox)
        vbox.pack_start(self.tbar, False, False, 2)
        
        # revision input
        revbox = gtk.HBox()
        lbl = gtk.Button("Remote Path:")
        lbl.unset_flags(gtk.CAN_FOCUS)
        lbl.connect('clicked', self._btn_remotepath_clicked)
        
        # revisions  combo box
        self.pathlist = gtk.ListStore(str)
        self._pathbox = gtk.ComboBoxEntry(self.pathlist, 0)
        self._pathtext = self._pathbox.get_child()
        
        defrow = None
        defpushrow = None
        for row, (name, path) in enumerate(self.paths):
            if name == 'default':
                defrow = row
                if defpushrow is None:
                    defpushrow = row
            elif name == 'default-push':
                defpushrow = row
            self.pathlist.append([path])

        if repos:
            self._pathtext.set_text(repos[0])
        elif defrow is not None:
            self._pathbox.set_active(defrow)
        elif defpushrow is not None:
            self._pathbox.set_active(defpushrow)

        sympaths = [x[1] for x in self.paths]
        for p in self._recent_src:
            if p not in sympaths:
                self.pathlist.append([p])
            
        # create checkbox to disable proxy
        self._use_proxy = gtk.CheckButton("use proxy server")        
        if ui.ui().config('http_proxy', 'host', ''):   
            self._use_proxy.set_active(True)
        else:
            self._use_proxy.set_sensitive(False)

        revbox.pack_start(lbl, False, False)
        revbox.pack_start(self._pathbox, True, True)
        revbox.pack_end(self._use_proxy, False, False)
        vbox.pack_start(revbox, False, False, 2)

        expander = gtk.Expander('Advanced Options')
        expander.set_expanded(False)
        hbox = gtk.HBox()
        expander.add(hbox)

        revvbox = gtk.VBox()
        revhbox = gtk.HBox()
        self._reventry = gtk.Entry()
        self._force = gtk.CheckButton('Force pull or push')
        self.tips.set_tip(self._force, 'Run even when remote repository'
                ' is unrelated.')

        revhbox.pack_start(gtk.Label('Target Revision:'), False, False, 2)
        revhbox.pack_start(self._reventry, True, True, 2)
        eventbox = gtk.EventBox()
        eventbox.add(revhbox)
        self.tips.set_tip(eventbox, 'A specific revision up to which you'
                ' would like to push or pull.')
        revvbox.pack_start(eventbox, True, True, 8)
        revvbox.pack_start(self._force, False, False, 2)
        hbox.pack_start(revvbox, True, True, 4)

        frame = gtk.Frame('Incoming/Outgoing')
        hbox.pack_start(frame, False, False, 2)

        self._showpatch = gtk.CheckButton('Show Patches')
        self._newestfirst = gtk.CheckButton('Show Newest First')
        self._nomerge = gtk.CheckButton('Show No Merges')

        hbox = gtk.HBox()
        hbox.pack_start(self._showpatch, False, False, 2)
        hbox.pack_start(self._newestfirst, False, False, 2)
        hbox.pack_start(self._nomerge, False, False, 2)
        frame.add(hbox)
        vbox.pack_start(expander, False, False, 2)

        # hg output window
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.textview = gtk.TextView(buffer=None)
        self.textview.set_editable(False)
        self.textview.modify_font(pango.FontDescription("Monospace"))
        scrolledwindow.add(self.textview)
        self.textview.set_editable(False)
        self.textbuffer = self.textview.get_buffer()
        vbox.pack_start(scrolledwindow, True, True)

        self.buttonhbox = gtk.HBox()
        self.viewpulled = gtk.Button('View Pulled Revisions')
        self.viewpulled.connect('clicked', self._view_pulled_changes)
        self.updatetip = gtk.Button('Update to Tip')
        self.updatetip.connect('clicked', self._update_to_tip)
        self.buttonhbox.pack_start(self.viewpulled, False, False, 2)
        self.buttonhbox.pack_start(self.updatetip, False, False, 2)
        vbox.pack_start(self.buttonhbox, False, False, 2)

        self.stbar = gtklib.StatusBar()
        vbox.pack_start(self.stbar, False, False, 2)
        self.connect('map', self.update_buttons)

    def update_buttons(self, *args):
        self.buttonhbox.hide()
        self.repo.invalidate()
        tip = self.repo.changelog.count()
        if self.origchangecount == tip:
            self.viewpulled.hide()
        else:
            self.buttonhbox.show()
            self.viewpulled.show()

        self.repo.dirstate.invalidate()
        parent = self.repo.workingctx().parents()[0].rev()
        if parent == tip-1:
            self.updatetip.hide()
        else:
            self.buttonhbox.show()
            self.updatetip.show()

    def _view_pulled_changes(self, button):
        from history import GLog
        revs = (self.repo.changelog.count()-1, self.origchangecount)
        opts = {'revrange' : revs}
        dialog = GLog(self.ui, self.repo, self.cwd, [], opts, False)
        dialog.display()

    def _update_to_tip(self, button):
        self.repo.invalidate()
        wc = self.repo.workingctx()
        pl = wc.parents()
        p1, p2 = pl[0], self.repo.changectx('tip')
        pa = p1.ancestor(p2)
        warning = ''
        flags = []
        if len(pl) > 1:
            warning = "Outstanding uncommitted merges"
        elif pa != p1 and pa != p2:
            warning = "Update spans branches"
        if warning:
            flags = ['--clean']
            msg = 'Lose all changes in your working directory?'
            warning += ', requires clean checkout'
            if question_dialog(self, msg, warning) != gtk.RESPONSE_YES:
                return
        self.write("", False)

        # execute command and show output on text widget
        gobject.timeout_add(10, self.process_queue)

        cmdline = ['update', '-v', '-R', self.repo.root] + flags + ['tip']
        self.hgthread = HgThread(cmdline)
        self.hgthread.start()
        self.stbar.begin()
        self.stbar.set_status_text('hg ' + ' '.join(cmdline))
        
    def _pull_menu(self):
        menu = gtk.Menu()
           
        self._pull_fetch = gtk.CheckMenuItem("Do fetch")
        menu.append(self._pull_fetch)
        self._pull_update = gtk.CheckMenuItem("Update to new tip")
        menu.append(self._pull_update)
        
        # restore states from previous session
        st = self._settings.get_value('_pull_update_state', False)
        self._pull_update.set_active(st)
        
        menu.show_all()
        return menu
        
    def _get_paths(self, sort="value"):
        """ retrieve symbolic paths """
        try:
            self.ui = ui.ui()
            self.repo = hg.repository(self.ui, path=self.root)
            paths = self.repo.ui.configitems('paths')
            if sort:
                if sort == "value":
                    sortfunc = lambda a,b: cmp(a[1], b[1])
                elif sort == "name":
                    sortfunc = lambda a,b: cmp(a[0], b[0])
                else:
                    raise "unknown sort key '%s'" % sort
                paths.sort(sortfunc)
            return paths
        except RepoError:
            return None

    def _btn_remotepath_clicked(self, button):
        """ select source folder to clone """
        dialog = gtk.FileChooserDialog(title="Select Repository",
                action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,
                         gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        dialog.set_default_response(gtk.RESPONSE_OK)
        dialog.set_current_folder(self.root)
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            self._pathtext.set_text(dialog.get_filename())
        dialog.destroy()
        
    def _close_clicked(self, toolbutton, data=None):
        self._do_close()

    def _do_close(self):
        if self._cmd_running():
            error_dialog(self, "Can't close now", "command is running")
        else:
            self._save_settings()
            gtk.main_quit()
        
    def _save_settings(self):
        self._settings.set_value('_pull_update_state',
                self._pull_update.get_active())
        self._settings.write()

    def _delete(self, widget, event):
        self._do_close()
        return True
   
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

    def _get_advanced_options(self):
        opts = {}
        if self._showpatch.get_active():
            opts['patch'] = ['--patch']
        if self._nomerge.get_active():
            opts['no-merges'] = ['--no-merges']
        if self._force.get_active():
            opts['force'] = ['--force']
        if self._newestfirst.get_active():
            opts['newest-first'] = ['--newest-first']
        target_rev = self._reventry.get_text().strip()
        if target_rev != "":
            opts['rev'] = ['--rev', target_rev]
            
        return opts
        
    def _pull_clicked(self, toolbutton, data=None):
        aopts = self._get_advanced_options()
        if self._pull_fetch.get_active():
            cmd = ['fetch', '--message', 'merge']
        else:
            cmd = ['pull']
            cmd += aopts.get('force', [])
            if self._pull_update.get_active():
                cmd.append('--update')
        cmd += aopts.get('rev', [])
        self._exec_cmd(cmd)
    
    def _push_clicked(self, toolbutton, data=None):
        aopts = self._get_advanced_options()
        cmd = ['push']
        cmd += aopts.get('rev', [])
        cmd += aopts.get('force', [])
        self._exec_cmd(cmd)
        
    def _conf_clicked(self, toolbutton, data=None):
        newpath = self._pathtext.get_text()
        for name, path in self.paths:
            if path == newpath:
                newpath = None
                break
        from thgconfig import ConfigDialog
        dlg = ConfigDialog(self.root, True)
        dlg.show_all()
        if newpath:
            dlg.new_path(newpath)
        else:
            dlg.focus_field('paths.default')
        dlg.run()
        dlg.hide()
        self.paths = self._get_paths()
        self.pathlist.clear()
        for row, (name, path) in enumerate(self.paths):
            self.pathlist.append([path])

    def _email_clicked(self, toolbutton, data=None):
        path = self._pathtext.get_text()
        if not path:
            info_dialog(self, 'No repository selected',
                    'Select a peer repository to compare with')
            self._pathbox.grab_focus()
            return
        from hgemail import EmailDialog
        dlg = EmailDialog(self.root, ['--outgoing', path])
        dlg.set_transient_for(self)
        dlg.show_all()
        dlg.present()
        dlg.set_transient_for(None)

    def _incoming_clicked(self, toolbutton, data=None):
        aopts = self._get_advanced_options()
        cmd = ['incoming']
        cmd += aopts.get('rev', [])
        cmd += aopts.get('patch', [])
        cmd += aopts.get('no-merges', [])
        cmd += aopts.get('force', [])
        cmd += aopts.get('newest-first', [])
        self._exec_cmd(cmd)
        
    def _outgoing_clicked(self, toolbutton, data=None):
        aopts = self._get_advanced_options()
        cmd = ['outgoing']
        cmd += aopts.get('rev', [])
        cmd += aopts.get('patch', [])
        cmd += aopts.get('no-merges', [])
        cmd += aopts.get('force', [])
        cmd += aopts.get('newest-first', [])
        self._exec_cmd(cmd)
        
    def _stop_clicked(self, toolbutton, data=None):
        if self._cmd_running():
            self.hgthread.terminate()
            self._stop_button.set_sensitive(False)

    def _exec_cmd(self, cmd):
        if self._cmd_running():
            error_dialog(self, "Can't run now",
                "Pleas try again after the previous command is completed")
            return

        self._stop_button.set_sensitive(True)

        proxy_host = ui.ui().config('http_proxy', 'host', '')
        use_proxy = self._use_proxy.get_active()
        text_entry = self._pathbox.get_child()
        remote_path = str(text_entry.get_text())
        
        cmdline = cmd[:]
        cmdline += ['--verbose', '--repository', self.root]
        if proxy_host and not use_proxy:
            cmdline += ["--config", "http_proxy.host="]
        cmdline += [remote_path]
        
        # show command to be executed
        self.write("", False)

        # execute command and show output on text widget
        gobject.timeout_add(10, self.process_queue)
        self.hgthread = HgThread(cmdline, parent=self)
        self.hgthread.start()
        self.stbar.begin()
        self.stbar.set_status_text('hg ' + ' '.join(cmd + [remote_path]))
        
        self._add_src_to_recent(remote_path)

    def _cmd_running(self):
        if self.hgthread and self.hgthread.isAlive():
            return True
        else:
            return False
        
    def _add_src_to_recent(self, src):
        if os.path.exists(src):
            src = os.path.abspath(src)

        # save path to recent list in history
        self._recent_src.add(src)
        self._settings.write()

        # update drop-down list
        self.pathlist.clear()
        sympaths = [x[1] for x in ui.ui().configitems('paths')]
        paths = list(set(sympaths + [x for x in self._recent_src]))
        paths.sort()
        for p in paths:
            self.pathlist.append([p])

    def write(self, msg, append=True):
        msg = toutf(msg)
        if append:
            enditer = self.textbuffer.get_end_iter()
            self.textbuffer.insert(enditer, msg)
            self.textview.scroll_to_mark(self.textbuffer.get_insert(), 0)
        else:
            self.textbuffer.set_text(msg)

    def process_queue(self):
        """
        Handle all the messages currently in the queue (if any).
        """
        self.hgthread.process_dialogs()
        while self.hgthread.getqueue().qsize():
            try:
                msg = self.hgthread.getqueue().get(0)
                self.write(msg)
            except Queue.Empty:
                pass

        if self._cmd_running():
            return True
        else:
            # Update button states
            self.update_buttons()
            self.stbar.end()
            self._stop_button.set_sensitive(False)
            if self.hgthread.return_code() is None:
                self.write("[command interrupted]")
            return False # Stop polling this function

def run(cwd='', root='', files=[], **opts):
    dialog = SynchDialog(cwd, root, files)
    dialog.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()
    
if __name__ == "__main__":
    run(**{})
