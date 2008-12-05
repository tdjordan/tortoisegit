#
# TortoiseHg dialog to clone a repo
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

try:
    import pygtk
    pygtk.require("2.0")
except:
    pass

import os
import sys
import gtk
import pango
from dialog import question_dialog, error_dialog, info_dialog
from mercurial import hg, ui, cmdutil, util
from mercurial.i18n import _
from mercurial.node import *
import shlib

class CloneDialog(gtk.Window):
    """ Dialog to add tag to Mercurial repo """
    def __init__(self, cwd='', repos=[]):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        shlib.set_tortoise_icon(self, 'menuclone.ico')
        if cwd: os.chdir(cwd)
        
        # set dialog title
        title = "hg clone "
        title += " - %s" % (os.getcwd())
        self.set_title(title)

        self._src_path = ''
        self._dest_path = ''
        self._settings = shlib.Settings('clone')
        self._recent_src = self._settings.mrul('src_paths')
        self._recent_dest = self._settings.mrul('dest_paths')

        try:
            self._src_path = repos[0]
            self._dest_path = repos[1]
        except:
            pass
            
        # build dialog
        self._create()

    def _create(self):
        self.set_default_size(520, 180)
        self.connect('destroy', gtk.main_quit)
        ewidth = 16
        
        # add toolbar with tooltips
        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()
        
        self._btn_clone = self._toolbutton(
                gtk.STOCK_COPY,
                'clone', 
                self._btn_clone_clicked,
                tip='Clone a repository')
        tbuttons = [
                self._btn_clone,
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        sep = gtk.SeparatorToolItem()
        sep.set_expand(True)
        sep.set_draw(False)
        self.tbar.insert(sep, -1)
        button = self._toolbutton(gtk.STOCK_CLOSE, 'Close',
                self._close_clicked, tip='Close Application')
        self.tbar.insert(button, -1)
        vbox = gtk.VBox()
        self.add(vbox)
        vbox.pack_start(self.tbar, False, False, 2)

        # clone source
        srcbox = gtk.HBox()
        lbl = gtk.Label("Source Path:")
        lbl.set_property("width-chars", ewidth)
        lbl.set_alignment(0, 0.5)

        # create drop-down list for source paths
        self._srclist = gtk.ListStore(str)
        self._srclistbox = gtk.ComboBoxEntry(self._srclist, 0)
        self._src_input = self._srclistbox.get_child()
        self._src_input.set_text(self._src_path)
        self._src_input.set_position(-1)

        # replace the drop-down widget so we can modify it's properties
        self._srclistbox.clear()
        cell = gtk.CellRendererText()
        cell.set_property('ellipsize', pango.ELLIPSIZE_MIDDLE)
        self._srclistbox.pack_start(cell)
        self._srclistbox.add_attribute(cell, 'text', 0)

        self._btn_src_browse = gtk.Button("Browse...")
        self._btn_src_browse.connect('clicked', self._btn_src_clicked)
        srcbox.pack_start(lbl, False, False)
        srcbox.pack_start(self._srclistbox, True, True)
        srcbox.pack_end(self._btn_src_browse, False, False, 5)
        vbox.pack_start(srcbox, False, False, 2)
        
        # add pre-defined src paths to pull-down list
        sympaths = [x[1] for x in ui.ui().configitems('paths')]
        paths = list(set(sympaths + [x for x in self._recent_src]))
        paths.sort()
        for p in paths:
            self._srclist.append([p])

        # clone destination
        destbox = gtk.HBox()
        lbl = gtk.Label("Destination Path:")
        lbl.set_property("width-chars", ewidth)
        lbl.set_alignment(0, 0.5)
        self._destlist = gtk.ListStore(str)
        self._destlistbox = gtk.ComboBoxEntry(self._destlist, 0)
        self._dest_input = self._destlistbox.get_child()
        self._dest_input.set_text(self._dest_path)
        self._dest_input.set_position(-1)

        # replace the drop-down widget so we can modify it's properties
        self._destlistbox.clear()
        cell = gtk.CellRendererText()
        cell.set_property('ellipsize', pango.ELLIPSIZE_MIDDLE)
        self._destlistbox.pack_start(cell)
        self._destlistbox.add_attribute(cell, 'text', 0)
        
        self._btn_dest_browse = gtk.Button("Browse...")
        self._btn_dest_browse.connect('clicked', self._btn_dest_clicked)
        destbox.pack_start(lbl, False, False)
        destbox.pack_start(self._destlistbox, True, True)
        destbox.pack_end(self._btn_dest_browse, False, False, 5)
        vbox.pack_start(destbox, False, False, 2)
        
        # add most-recent dest paths to pull-down list
        paths = list(self._recent_dest)
        paths.sort()
        for p in paths:
            self._destlist.append([p])

        # revision input
        revbox = gtk.HBox()
        lbl = gtk.Label("Clone To Revision:")
        lbl.set_property("width-chars", ewidth)
        lbl.set_alignment(0, 0.5)
        self._rev_input = gtk.Entry()
        self._rev_input.set_text("")
        self._opt_allrev = gtk.CheckButton("Clone all revisions")
        self._opt_allrev.set_active(True)
        self._btn_rev_browse = gtk.Button("Select...")
        self._btn_rev_browse.connect('clicked', self._btn_rev_clicked)
        revbox.pack_start(lbl, False, False)
        revbox.pack_start(self._rev_input, False, False)
        #revbox.pack_start(self._btn_rev_browse, False, False, 5)
        revbox.pack_start(self._opt_allrev, False, False)
        vbox.pack_start(revbox, False, False, 2)

        # options
        option_box = gtk.VBox()
        self._opt_update = gtk.CheckButton("do not update the new working directory")
        self._opt_pull = gtk.CheckButton("use pull protocol to copy metadata")
        self._opt_uncomp = gtk.CheckButton("use uncompressed transfer")
        self._opt_proxy = gtk.CheckButton("use proxy server")        
        option_box.pack_start(self._opt_update, False, False)
        option_box.pack_start(self._opt_pull, False, False)
        option_box.pack_start(self._opt_uncomp, False, False)
        option_box.pack_start(self._opt_proxy, False, False)
        vbox.pack_start(option_box, False, False, 15)

        if ui.ui().config('http_proxy', 'host', ''):   
            self._opt_proxy.set_active(True)
        else:
            self._opt_proxy.set_sensitive(False)

        # remote cmd
        lbl = gtk.Label("Remote Cmd:")
        lbl.set_alignment(0, 0.5)
        self._remote_cmd = gtk.Entry()
        vbox.pack_end(self._remote_cmd, False, False, 1)
        vbox.pack_end(lbl, False, False, 1)

    def _close_clicked(self, toolbutton, data=None):
        gtk.main_quit()

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

    def _btn_dest_clicked(self, button):
        """ select folder as clone destination """
        dialog = gtk.FileChooserDialog(title=None,
                action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,
                         gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        dialog.set_default_response(gtk.RESPONSE_OK)
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            self._dest_input.set_text(dialog.get_filename())
        dialog.destroy()
        
    def _btn_src_clicked(self, button):
        """ select source folder to clone """
        dialog = gtk.FileChooserDialog(title=None,
                action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,
                         gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        dialog.set_default_response(gtk.RESPONSE_OK)
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            self._src_input.set_text(dialog.get_filename())
        dialog.destroy()

    def _btn_rev_clicked(self, button):
        """ select revision from history dialog """
        import histselect
        rev = histselect.select(self.root)
        if rev is not None:
            self._rev_input.set_text(rev)

    def _add_src_to_recent(self, src):
        if os.path.exists(src):
            src = os.path.abspath(src)

        # save path to recent list in history
        self._recent_src.add(src)
        self._settings.write()

        # update drop-down list
        self._srclist.clear()
        sympaths = [x[1] for x in ui.ui().configitems('paths')]
        paths = list(set(sympaths + [x for x in self._recent_src]))
        paths.sort()
        for p in paths:
            self._srclist.append([p])

    def _add_dest_to_recent(self, dest):
        if os.path.exists(dest):
            dest = os.path.abspath(dest)

        # save path to recent list in history
        self._recent_dest.add(dest)
        self._settings.write()
        
        # update drop down list
        paths = list(self._recent_dest)
        paths.sort()
        self._destlist.clear()
        for p in paths:
            self._destlist.append([p])
 
    def _btn_clone_clicked(self, toolbutton, data=None):
        # gather input data
        src = self._src_input.get_text()
        dest = self._dest_input.get_text() or os.path.basename(src)
        remotecmd = self._remote_cmd.get_text()
        rev = self._rev_input.get_text()
        
        # verify input
        if src == "":
            error_dialog(self, "Source path is empty", "Please enter")
            self._src_input.grab_focus()
            return False
        
        # start cloning        
        try:            
            cmdline = ['hg', 'clone']
            if self._opt_update.get_active():
                cmdline.append('--noupdate')
            if self._opt_uncomp.get_active():
                cmdline.append('--uncompressed')
            if self._opt_pull.get_active():
                cmdline.append('--pull')
            if not (self._opt_proxy.get_active() and
                    ui.ui().config('http_proxy', 'host', '')):
                cmdline += ["--config", "http_proxy.host="]
            if remotecmd:   
                cmdline.append('--remotecmd')
                cmdline.append(remotecmd)
            if not self._opt_allrev.get_active() and rev:   
                cmdline.append('--rev')
                cmdline.append(rev)

            cmdline.append('--verbose')
            cmdline.append(src)
            if dest:
                cmdline.append(dest)

            print "cmdline: ", ' '.join(cmdline)
            from hgcmd import CmdDialog
            dlg = CmdDialog(cmdline)
            dlg.run()
            dlg.hide()
        except util.Abort, inst:
            error_dialog(self, "Clone aborted", str(inst))
            return False
        except:
            import traceback
            error_dialog(self, "Clone error", traceback.format_exc())
            return False

        self._add_src_to_recent(src)
        self._add_dest_to_recent(dest)

def run(cwd='', files=[], **opts):
    dialog = CloneDialog(cwd, repos=files)
    dialog.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()
    
if __name__ == "__main__":
    import sys
    opts = {}
    opts['cwd'] = os.getcwd()
    opts['files'] = sys.argv[1:]
    run(**opts)
