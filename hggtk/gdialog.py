# gdialog.py - base dialog for gtools
#
# Copyright 2007 Brad Schick, brad at gmail . com
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.
# 

import mercurial.demandimport; mercurial.demandimport.disable()

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
from shlib import shell_notify, set_tortoise_icon, Settings
from thgconfig import ConfigDialog
from gtklib import MessageDialog
from hglib import toutf


class SimpleMessage(MessageDialog):
    def run(self):
        response = MessageDialog.run(self)
        self.destroy()
        return response


class Prompt(SimpleMessage):
    def __init__(self, title, message, parent):
        SimpleMessage.__init__(self, parent, gtk.DIALOG_MODAL,
                gtk.MESSAGE_INFO, gtk.BUTTONS_CLOSE)
        self.set_title(toutf(title))
        self.set_markup('<b>' + toutf(message) + '</b>')

class Confirm(SimpleMessage):
    """Dialog returns gtk.RESPONSE_YES or gtk.RESPONSE_NO 
    """
    def __init__(self, title, files, parent, primary=None):
        SimpleMessage.__init__(self, parent, gtk.DIALOG_MODAL,
                gtk.MESSAGE_QUESTION, gtk.BUTTONS_YES_NO)
        self.set_title(toutf('Confirm ' + title))
        if primary is None:
            primary = title + ' file' + ((len(files) > 1 and 's') or '') + '?'
        primary = '<b>' + primary + '</b>'
        self.set_markup(toutf(primary))
        message = ''
        for i, file in enumerate(files):
            message += '   ' + file + '\n'
            if i == 9: 
                message += '   ...\n'
                break
        self.format_secondary_text(toutf(message))


class GDialog(gtk.Window):
    """GTK+ based dialog for displaying mercurial information

    The following methods are meant to be overridden by subclasses. At this
    point GCommit is really the only intended subclass.

        parse_opts(self)
        get_title(self)
        get_minsize(self)
        get_defsize(self)
        get_tbbuttons(self)
        get_body(self)
        get_extras(self)
        prepare_display(self)
        should_live(self, widget, event)
        save_settings(self)
        load_settings(self, settings)
    """

    # "Constants"
    settings_version = 1

    def __init__(self, ui, repo, cwd, pats, opts, main):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        self.cwd = cwd
        self.ui = ui
        self.ui.interactive=False
        self.repo = repo
        self.pats = pats
        self.opts = opts
        self.main = main
        self.tmproot = None
        self.toolbuttons = {}
        self.settings = Settings(self.__class__.__name__)
        self.init()

    ### Following methods are meant to be overridden by subclasses ###

    def init(self):
        pass

    def parse_opts(self):
        pass


    def get_title(self):
        return ''

    def get_icon(self):
        return ''

    def get_minsize(self):
        return (395, 200)


    def get_defsize(self):
        return self._setting_defsize 


    def get_tbbuttons(self):
        return []


    def get_body(self):
        return None


    def get_extras(self):
        return None


    def prepare_display(self):
        pass


    def should_live(self, widget=None, event=None):
        return False


    def save_settings(self):
        rect = self.get_allocation()
        return {'gdialog': (rect.width, rect.height)}


    def load_settings(self, settings):
        if settings:
            self._setting_defsize = settings['gdialog']
        else:
            self._setting_defsize = (678, 585)

    ### End of overridable methods ###

    def display(self, opengui=True):
        self._parse_config()
        self._load_settings()
        if opengui:
            self._setup_gtk()
            self._parse_opts()
            self.prepare_display()
            self.show_all()
        else:
            self._parse_opts()
            self.tooltips = gtk.Tooltips()


    def test_opt(self, opt):
        return opt in self.opts and self.opts[opt]


    def _parse_config(self):
        # defaults    
        self.fontcomment = 'monospace 10'
        self.fontdiff = 'monospace 10'
        self.fontlist = 'monospace 9'
        self.diffopts = ''
        self.diffcmd = ''
        self.diffbottom = ''

        for attr, setting in self.ui.configitems('gtools'):
            if setting : setattr(self, attr, setting)

        if not self.diffcmd :
            # default to tortoisehg's configuration
            vdiff = self.ui.config('tortoisehg', 'vdiff')
            if vdiff:
                self.diffcmd = self.ui.config('extdiff', 'cmd.'+vdiff) or vdiff
            else:
                self.diffcmd = 'diff'
                if not self.diffopts :
                    self.diffopts = '-Npru'

        if not self.diffbottom:
            self.diffbottom = False
        elif self.diffbottom.lower() == 'false' or self.diffbottom == '0':
            self.diffbottom = False
        else:
            self.diffbottom = True


    def _parse_opts(self):
        # Remove dry_run since Hg only honors it for certain commands
        self.opts['dry_run'] = False
        self.opts['force_editor'] = False
        self.parse_opts()


    def merge_opts(self, defaults, mergelist=()):
        """Merge default options with the specified local options and globals.
        Results is defaults + merglist + globals
        """
        newopts = {}
        for hgopt in defaults:
            newopts[hgopt[1].replace('-', '_')] = hgopt[2]
        for mergeopt in mergelist:
            newopts[mergeopt] = self.opts[mergeopt]
        newopts.update(self.global_opts())
        return newopts


    def global_opts(self):
        globals = {}
        hgglobals = [opt[1].replace('-', '_') for opt in commands.globalopts if opt[1] != 'help']
        for key in self.opts:
            if key in  hgglobals :
                globals[key] = self.opts[key]
        return globals


    def count_revs(self):
        cnt = 0
        if self.test_opt('rev'):
            for rev in self.opts['rev']:
                cnt += len(rev.split(cmdutil.revrangesep, 1))
        return cnt


    def make_toolbutton(self, stock, label, handler,
            userdata=None, menu=None, tip=None):
        if menu:
            tbutton = gtk.MenuToolButton(stock)
            tbutton.set_menu(menu)
        else:
            tbutton = gtk.ToolButton(stock)

        if tip:
            tbutton.set_tooltip(self.tooltips, tip)
        tbutton.set_use_underline(True)
        tbutton.set_label(label)
        tbutton.connect('clicked', handler, userdata)
        self.toolbuttons[label] = tbutton
        return tbutton


    def get_toolbutton(self, label):
        return self.toolbuttons[label]


    def _setup_gtk(self):
        self.set_title(self.get_title())
        set_tortoise_icon(self, self.get_icon())
        
        # Minimum size
        minx, miny = self.get_minsize()
        self.set_size_request(minx, miny)
        # Initial size
        defx, defy = self.get_defsize()
        self.set_default_size(defx, defy)
        
        vbox = gtk.VBox(False, 0)
        self.add(vbox)
        
        self.tooltips = gtk.Tooltips()
        toolbar = gtk.Toolbar()
        tbuttons =  self.get_tbbuttons()
        for tbutton in tbuttons:
            toolbar.insert(tbutton, -1)
        sep = gtk.SeparatorToolItem()
        sep.set_expand(True)
        sep.set_draw(False)
        toolbar.insert(sep, -1)
        if self.main:
            name = 'Quit'
            tip = 'Close Application'
        else:
            name = 'Close'
            tip = 'Close Window'
        button = self.make_toolbutton(gtk.STOCK_CLOSE, name,
                self._quit_clicked, tip=tip)
        toolbar.insert(button, -1)
        self.toolbar = toolbar
        vbox.pack_start(toolbar, False, False, 0)

        # Subclass returns the main body
        body = self.get_body()
        vbox.pack_start(body, True, True, 0)
        
        # Subclass provides extra stuff in bottom hbox
        extras = self.get_extras()
        if extras:
            vbox.pack_end(extras, False, False, 0)

        self.connect('destroy', self._destroying)
        self.connect('delete_event', self.should_live)



    def _quit_clicked(self, button, data=None):
        if not self.should_live():
            self.destroy()


    def _destroying(self, gtkobj):
        try:
            settings = self.save_settings()
            self.settings.set_value('settings_version', GDialog.settings_version)
            self.settings.set_value('dialogs', settings)
            self.settings.write()
        finally:
            if self.main:
                gtk.main_quit()


    def _load_settings(self):
        settings = {}
        version = self.settings.get_value('settings_version', None)
        if version == GDialog.settings_version:
            settings = self.settings.get_value('dialogs', {})
        self.load_settings(settings)


    def _hg_call_wrapper(self, title, command, showoutput=True):
        """Run the specified command and display any resulting aborts, messages, 
        and errors 
        """
        textout = ''
        saved = sys.stderr
        errors = StringIO.StringIO()
        try:
            sys.stderr = errors
            self.ui.pushbuffer()
            try:
                command()
            except util.Abort, inst:
                Prompt(title + ' Aborted', str(inst), self).run()
                return False, ''
        finally:
            sys.stderr = saved
            textout = self.ui.popbuffer() 
            prompttext = ''
            if showoutput:
                prompttext = textout + '\n'
            prompttext += errors.getvalue()
            errors.close()
            if len(prompttext) > 1:
                Prompt(title + ' Messages and Errors', prompttext, self).run()

        return True, textout

    def _diff_file(self, stat, file):
        def dodiff():
            extdiff.dodiff(self.ui, self.repo, self.diffcmd, [self.diffopts],
                            [self.repo.wjoin(file)], self.opts)

        if self.diffcmd == 'diff':
            Prompt('No visual diff configured',
                    'Please select a visual diff application.', self).run()
            dlg = ConfigDialog(self.repo.root, False)
            dlg.show_all()
            dlg.focus_field('tortoisehg.vdiff')
            dlg.run()
            dlg.hide()
            self.ui = ui.ui()
            self._parse_config()
            return
        thread = threading.Thread(target=dodiff, name='diff:'+file)
        thread.setDaemon(True)
        thread.start()


    def _view_file(self, stat, file, force_left=False):
        import atexit
        
        def cleanup():
            shutil.rmtree(self.tmproot)

        if not self.tmproot:
            self.tmproot = tempfile.mkdtemp(prefix='gtools.')
            atexit.register(cleanup)

        def snapshot_node(ui, repo, files, node, tmproot):
            '''
            snapshot files as of some revision
            (adapted from Extdiff extension)
            '''
            mf = repo.changectx(node).manifest()
            dirname = os.path.basename(repo.root)
            if dirname == "":
                dirname = "root"
            dirname = '%s.%s' % (dirname, short(node))
            base = os.path.join(tmproot, dirname)
            try:
                os.mkdir(base)
            except:
                pass
            ui.note(_('making snapshot of %d files from rev %s\n') %
                    (len(files), short(node)))
            for fn in files:
                if not fn in mf:
                    # skipping new file after a merge ?
                    continue
                wfn = util.pconvert(fn)
                ui.note('  %s\n' % wfn)
                dest = os.path.join(base, wfn)
                destdir = os.path.dirname(dest)
                if not os.path.isdir(destdir):
                    os.makedirs(destdir)
                data = repo.wwritedata(wfn, repo.file(wfn).read(mf[wfn]))
                open(dest, 'wb').write(data)
            return dirname

        def doedit():
            pathroot = self.repo.root
            copynode = None
            # if we aren't looking at the wc, copy the node...
            if stat in 'R!' or force_left:
                copynode = self._node1
            elif self._node2:
                copynode = self._node2

            if copynode:
                copydir = snapshot_node(self.ui, self.repo,
                        [util.pconvert(file)], copynode, self.tmproot)
                pathroot = os.path.join(self.tmproot, copydir)

            file_path = os.path.join(pathroot, file)
            util.system("%s \"%s\"" % (editor, file_path),
                        environ={'HGUSER': self.ui.username()},
                        onerr=util.Abort, errprefix=_('edit failed'))
                
        editor = (self.ui.config('tortoisehg', 'editor') or
                self.ui.config('gtools', 'editor') or
                os.environ.get('HGEDITOR') or
                self.ui.config('ui', 'editor') or
                os.environ.get('EDITOR', 'vi'))
        if os.path.basename(editor) in ('vi', 'vim', 'hgeditor'):
            Prompt('No visual editor configured',
                    'Please configure a visual editor.', self).run()
            dlg = ConfigDialog(self.repo.root, False)
            dlg.show_all()
            dlg.focus_field('tortoisehg.editor')
            dlg.run()
            dlg.hide()
            self.ui = ui.ui()
            self._parse_config()
            return
            
        file = util.localpath(file)
        thread = threading.Thread(target=doedit, name='edit:'+file)
        thread.setDaemon(True)
        thread.start()

class NativeSaveFileDialogWrapper:
    """Wrap the windows file dialog, or display default gtk dialog if that isn't available"""
    def __init__(self, InitialDir = None, Title = "Save File", 
                 Filter = {"All files": "*.*"}, FilterIndex = 1, FileName = ''):
        import os.path
        if InitialDir == None:
            InitialDir = os.path.expanduser("~")
        self.InitialDir = InitialDir
        self.FileName = FileName
        self.Title = Title
        self.Filter = Filter
        self.FilterIndex = FilterIndex

    def run(self):
        """run the file dialog, either return a file name, or False if the user aborted the dialog"""
        try:
            import win32gui
            if self.tortoiseHgIsInstalled(): #as of 20071021, the file dialog will hang if the tortoiseHg shell extension is installed. I have no clue why, yet - Tyberius Prime
                   return self.runCompatible()
            else:
                    return self.runWindows()
        except ImportError:
            return self.runCompatible()

    def tortoiseHgIsInstalled(self):
        import _winreg
        try:
            hkey = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,r"Software\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\Changed")
            if hkey:
                cls = _winreg.QueryValue(hkey,"")
                return cls == "{102C6A24-5F38-4186-B64A-237011809FAB}"
        except WindowsError: #reg key not found
            pass
        return False

    def runWindows(self):
        import win32gui, win32con, os
        filter = ""
        for name, pattern in self.Filter.iteritems():
            filter += name + "\0" + pattern + "\0"
        customfilter = "\0"

        fname, customfilter, flags=win32gui.GetSaveFileNameW(
            InitialDir=self.InitialDir,
            Flags=win32con.OFN_EXPLORER,
            File=self.FileName, 
            DefExt='py',
            Title=self.Title,
            Filter="",
            CustomFilter="",
            FilterIndex=1)
        if fname:
            return fname
        else:
           return False

    def runCompatible(self):
        file_save =gtk.FileChooserDialog(self.Title,None,
                gtk.FILE_CHOOSER_ACTION_SAVE
                , (gtk.STOCK_CANCEL
                    , gtk.RESPONSE_CANCEL
                    , gtk.STOCK_SAVE
                    , gtk.RESPONSE_OK))
        file_save.set_default_response(gtk.RESPONSE_OK)
        file_save.set_current_folder(self.InitialDir)
        file_save.set_current_name(self.FileName)
        for name, pattern in self.Filter.iteritems():
            fi = gtk.FileFilter()
            fi.set_name(name)
            fi.add_pattern(pattern)
            file_save.add_filter(fi)
        if file_save.run() == gtk.RESPONSE_OK:
            result = file_save.get_filename();
        else:
            result = False
        file_save.destroy()
        return result
