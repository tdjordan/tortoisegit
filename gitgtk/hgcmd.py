#
# A simple dialog to execute random command for TortoiseHg
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import pygtk
pygtk.require("2.0")

import gtk
import gobject
import pango
import os
import threading
import Queue
from hglib import HgThread, hgcmd_toq, toutf
from shlib import set_tortoise_icon, get_system_times

class CmdDialog(gtk.Dialog):
    def __init__(self, cmdline, progressbar=True, width=520, height=400):
        title = 'hg ' + ' '.join(cmdline[1:])
        gtk.Dialog.__init__(self,
                            title=title,
                            flags=gtk.DIALOG_MODAL, 
                            #buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT)
                            )

        set_tortoise_icon(self, 'hg.ico')
        self.cmdline = cmdline
        self.returncode = None

        # construct dialog
        self.set_default_size(width, height)

        self._button_stop = gtk.Button("Stop")
        self._button_stop.connect('clicked', self._on_stop_clicked)
        self.action_area.pack_start(self._button_stop)
        
        self._button_ok = gtk.Button("Close")
        self._button_ok.connect('clicked', self._on_ok_clicked)
        self.action_area.pack_start(self._button_ok)

        self.connect('delete-event', self._delete)
        self.connect('response', self._response)

        self.pbar = None
        if progressbar:
            self.last_pbar_update = 0

            hbox = gtk.HBox()
            
            self.status_text = gtk.Label()
            self.status_text.set_text(toutf(" ".join(cmdline).replace("\n", " ")))
            self.status_text.set_alignment(0, 0.5)
            self.status_text.set_ellipsize(pango.ELLIPSIZE_END)
            hbox.pack_start(self.status_text, True, True, 3)

            # Create a centering alignment object
            align = gtk.Alignment(0.0, 0.0, 1, 0)
            hbox.pack_end(align, False, False, 3)
            align.show()
            
            # create the progress bar
            self.pbar = gtk.ProgressBar()
            align.add(self.pbar)
            self.pbar.pulse()
            self.pbar.show()

            self.vbox.pack_start(hbox, False, False, 3)

        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.textview = gtk.TextView(buffer=None)
        self.textview.set_editable(False)
        self.textview.modify_font(pango.FontDescription("Monospace"))
        scrolledwindow.add(self.textview)
        self.textbuffer = self.textview.get_buffer()
        
        self.vbox.pack_start(scrolledwindow, True, True)
        self.connect('map_event', self._on_window_map_event)

        self.show_all()

    def _on_ok_clicked(self, button):
        """ Ok button clicked handler. """
        self.response(gtk.RESPONSE_ACCEPT)
        
    def _on_stop_clicked(self, button):
        self.hgthread.terminate()
    
    def _delete(self, widget, event):
        return True

    def _response(self, widget, response_id):
        if self.hgthread.isAlive():
            widget.emit_stop_by_name('response')
    
    def _on_window_map_event(self, event, param):
        self.hgthread = HgThread(self.cmdline[1:])
        self.hgthread.start()
        self._button_ok.set_sensitive(False)
        self._button_stop.set_sensitive(True)        
        gobject.timeout_add(10, self.process_queue)
    
    def write(self, msg, append=True):
        msg = toutf(msg)
        if append:
            enditer = self.textbuffer.get_end_iter()
            self.textbuffer.insert(enditer, msg)
        else:
            self.textbuffer.set_text(msg)

    def process_queue(self):
        """
        Handle all the messages currently in the queue (if any).
        """
        self.hgthread.process_dialogs()
        enditer = self.textbuffer.get_end_iter()
        while self.hgthread.getqueue().qsize():
            try:
                msg = self.hgthread.getqueue().get(0)
                self.textbuffer.insert(enditer, toutf(msg))
                self.textview.scroll_to_mark(self.textbuffer.get_insert(), 0)
            except Queue.Empty:
                pass
        self.update_progress()
        if not self.hgthread.isAlive():
            self._button_ok.set_sensitive(True)
            self._button_stop.set_sensitive(False)            
            self.returncode = self.hgthread.return_code()
            if self.returncode is None:
                self.write("\n[command interrupted]")
            return False # Stop polling this function
        else:
            return True

    def update_progress(self):
        if not self.pbar:
            return          # progress bar not enabled
            
        if not self.hgthread.isAlive():
            self.pbar.unmap()
        else:
            # pulse the progress bar every ~100ms
            tm = get_system_times()[4]
            if tm - self.last_pbar_update < 0.100:
                return
            self.last_pbar_update = tm
            self.pbar.pulse()

    def return_code(self):
        return self.hgthread.return_code()

def run(cmdline=[], gui=True, **opts):
    if not gui:
        q = Queue.Queue()
        hgcmd_toq(None, q, *cmdline[1:])
        return

    dlg = CmdDialog(cmdline)
    dlg.connect('response', gtk.main_quit)
    dlg.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()
    
if __name__ == "__main__":
    import sys
    run(sys.argv)

