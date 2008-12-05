#
# A PyGtk-based Python Trace Collector window
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import pygtk
pygtk.require("2.0")
import gtk
import gobject
import pango
import threading
import Queue
import win32trace

try:
    from hggtk.hglib import toutf
except ImportError:
    import locale
    _encoding = locale.getpreferredencoding()
    def toutf(s):
        return s.decode(_encoding, 'replace').encode('utf-8')

class TraceLog():
    def __init__(self):
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_title("Python Trace Collector")
        
        # construct window
        self.window.set_default_size(700, 400)
        self.main_area = gtk.VBox()
        self.window.add(self.main_area)
        
        # mimic standard dialog widgets
        self.action_area = gtk.HBox()
        self.main_area.pack_end(self.action_area, False, False, 5)
        sep = gtk.HSeparator()
        self.main_area.pack_end(sep, False, False, 0)
        self.vbox = gtk.VBox()
        self.main_area.pack_end(self.vbox)        
        
        # add python trace ouput window
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.textview = gtk.TextView(buffer=None)
        self.textview.set_editable(False)
        self.textview.modify_font(pango.FontDescription("Monospace"))
        scrolledwindow.add(self.textview)
        self.textview.set_editable(False)
        self.textbuffer = self.textview.get_buffer()
        self.vbox.pack_start(scrolledwindow, True, True)
        self.vbox.show_all()

        # add buttons
        self._button_quit = gtk.Button("Quit")
        self._button_quit.connect('clicked', self._on_ok_clicked)
        self.action_area.pack_end(self._button_quit, False, False, 5)        

        self._button_clear = gtk.Button("Clear")
        self._button_clear.connect('clicked', self._on_clear_clicked)
        self.action_area.pack_end(self._button_clear, False, False, 5)

        # add assorted window event handlers
        self.window.connect('map_event', self._on_window_map_event)
        self.window.connect('delete_event', self._on_window_close_clicked)

    def _on_ok_clicked(self, button):
        self._stop_read_thread()
        gtk.main_quit()
        
    def _on_clear_clicked(self, button):
        self.write("", False)
        
    def _on_window_close_clicked(self, event, param):
        self._stop_read_thread()
        gtk.main_quit()
        
    def _on_window_map_event(self, event, param):
        self._begin_trace()
    
    def _begin_trace(self):
        self.queue = Queue.Queue()
        win32trace.InitRead()
        self.write("Collecting Python Trace Output...\n")
        gobject.timeout_add(10, self._process_queue)
        self._start_read_thread()
        
    def _start_read_thread(self):
        self._read_trace = True
        self.thread1 = threading.Thread(target=self._do_read_trace)
        self.thread1.start()

    def _stop_read_thread(self):
        self._read_trace = False

        # wait for worker thread to to fix Unhandled exception in thread
        self.thread1.join() 
        
    def _process_queue(self):
        """
        Handle all the messages currently in the queue (if any).
        """
        while self.queue.qsize():
            try:
                msg = self.queue.get(0)
                self.write(msg)
            except Queue.Empty:
                pass
                
        return True
        
    def _do_read_trace(self):
        """
        print buffer collected in win32trace
        """
        while self._read_trace:
            msg = win32trace.read()
            if msg:
                self.queue.put(msg)
        
    def write(self, msg, append=True):
        msg = toutf(msg)
        if append:
            enditer = self.textbuffer.get_end_iter()
            self.textbuffer.insert(enditer, msg)
        else:
            self.textbuffer.set_text(msg)

    def main(self):
        self.window.show_all()
        gtk.main()
        
def run():
    dlg = TraceLog()
    dlg.main()
    
if __name__ == "__main__":
    run()

