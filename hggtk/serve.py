#
# TortoiseHg dialog to start web server
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
import httplib
import os
import pango
import Queue
import socket
import sys
import threading
import time
import hglib
from dialog import question_dialog, error_dialog
from mercurial import hg, ui, commands, cmdutil, util
from mercurial.repo import RepoError
from mercurial.hgweb import server
from mercurial.i18n import _
from shlib import set_tortoise_icon

gservice = None
class ServeDialog(gtk.Window):
    """ Dialog to run web server"""
    def __init__(self, cwd='', root=''):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        set_tortoise_icon(self, 'proxy.ico')
        self.connect('delete-event', self._delete)

        # Pipe stderr, stdout to self.write
        self._queue = Queue.Queue()
        sys.stdout = self
        sys.stderr = self

        # Override mercurial.commands.serve() with our own version
        # that supports being stopped
        commands.table.update(thg_serve_cmd)

        self._url = None
        self._root = root
        if cwd:
            os.chdir(cwd)
        
        self._get_config()
        self.set_default_size(500, 300)
        
        # toolbar
        self.tbar = gtk.Toolbar()
        self._button_start = self._toolbutton(gtk.STOCK_MEDIA_PLAY,
                                              'Start', 
                                              self._on_start_clicked,
                                              None)
        self._button_stop  = self._toolbutton(gtk.STOCK_MEDIA_STOP,
                                              'Stop',
                                              self._on_stop_clicked,
                                              None)
        self._button_browse = self._toolbutton(gtk.STOCK_HOME,
                                              'Browse',
                                              self._on_browse_clicked,
                                              None)
        self._button_conf = self._toolbutton(gtk.STOCK_PREFERENCES,
                                              'Configure',
                                              self._on_conf_clicked,
                                              None)
        sep = gtk.SeparatorToolItem()
        sep.set_expand(True)
        sep.set_draw(False)
        self._button_close = self._toolbutton(gtk.STOCK_CLOSE, 'Quit',
                self._close_clicked)

        tbuttons = [
                self._button_start,
                self._button_stop,
                gtk.SeparatorToolItem(),
                self._button_browse,
                gtk.SeparatorToolItem(),
                self._button_conf,
                sep,
                self._button_close,
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)

        vbox = gtk.VBox()
        self.add(vbox)
        vbox.pack_start(self.tbar, False, False, 2)
        
        # revision input
        revbox = gtk.HBox()
        lbl = gtk.Label("HTTP Port:")
        lbl.set_property("width-chars", 16)
        lbl.set_alignment(0, 0.5)
        self._port_input = gtk.Entry()
        self._port_input.set_text(self.defport)
        revbox.pack_start(lbl, False, False)
        revbox.pack_start(self._port_input, False, False)
        vbox.pack_start(revbox, False, False, 2)

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
        self._set_button_states()

    def _get_config(self):
        try:
            repo = hg.repository(ui.ui(), path=self._root)
        except RepoError:
            print 'no repository found'
            gtk.main_quit()
        self.defport = repo.ui.config('web', 'port') or '8000'
        self.webname = repo.ui.config('web', 'name') or \
                os.path.basename(self._root)
        self.set_title("hg serve - " + self.webname)

    def _toolbutton(self, stock, label, handler, menu=None, userdata=None):
        if menu:
            tbutton = gtk.MenuToolButton(stock)
            tbutton.set_menu(menu)
        else:
            tbutton = gtk.ToolButton(stock)
            
        tbutton.set_label(label)
        tbutton.connect('clicked', handler, userdata)
        return tbutton
            
    def _close_clicked(self, *args):
        if self._server_stopped() == True:
            gtk.main_quit()
        
    def _delete(self, widget, event):
        if self._server_stopped() == True:
            gtk.main_quit()
        else:
            return True

    def _server_stopped(self):
        '''
        check if server is running, or to terminate if running
        '''
        if gservice and not gservice.stopped:
            if question_dialog(self, "Really Exit?",
                    "Server process is still running\n" +
                    "Exiting will stop the server.") != gtk.RESPONSE_YES:
                return False
            else:
                self._stop_server()
                return True
        else:
            return True

    def _set_button_states(self):
        if gservice and not gservice.stopped:
            self._button_start.set_sensitive(False)
            self._button_stop.set_sensitive(True)
            self._button_browse.set_sensitive(True)
            self._button_conf.set_sensitive(False)
        else:
            self._button_start.set_sensitive(True)
            self._button_stop.set_sensitive(False)
            self._button_browse.set_sensitive(False)
            self._button_conf.set_sensitive(True)
            
    def _on_start_clicked(self, *args):
        self._start_server()
        self._set_button_states()
        
    def _on_stop_clicked(self, *args):
        self._stop_server()

    def _on_browse_clicked(self, *args):
        ''' launch default browser to view repo '''
        if self._url:
            def start_browser():
                if os.name == 'nt':
                    try:
                        import win32api, win32con
                        win32api.ShellExecute(0, "open", self._url, None, "", 
                            win32con.SW_SHOW)
                    except:
                        # Firefox likes to create exceptions at launch,
                        # the user doesn't need to be bothered by them
                        pass
                else:
                    import gconf
                    client = gconf.client_get_default()
                    browser = client.get_string(
                            '/desktop/gnome/url-handlers/http/command') + '&'
                    os.system(browser % self._url)
            threading.Thread(target=start_browser).start()
    
    def _on_conf_clicked(self, *args):
        from thgconfig import ConfigDialog
        dlg = ConfigDialog(self._root, True)
        dlg.show_all()
        dlg.focus_field('web.name')
        dlg.run()
        dlg.hide()
        self._get_config()

    def _start_server(self):
        # gather input data
        try:
            port = int(self._port_input.get_text())
        except:
            try: port = int(self.defport)
            except: port = 8000
            error_dialog(self, "Invalid port 2048..65535", "Defaulting to " +
                    self.defport)
        
        global gservice
        gservice = None

        args = [self._root, self._queue, 'serve', '--name', self.webname,
                '--port', str(port)]
        thread = threading.Thread(target=hglib.hgcmd_toq, args=args)
        thread.start()

        while not gservice or not hasattr(gservice, 'httpd'):
            time.sleep(0.1)
        self._url = 'http://%s:%d/' % (gservice.httpd.fqaddr, port)
        gobject.timeout_add(10, self.process_queue)
        
    def _stop_server(self):
        if gservice and not gservice.stopped:
            gservice.stop()

    def flush(self, *args):
        pass

    def write(self, msg):
        self._queue.put(msg)
        
    def _write(self, msg, append=True):
        msg = hglib.toutf(msg)
        if append:
            enditer = self.textbuffer.get_end_iter()
            self.textbuffer.insert(enditer, msg)
        else:
            self.textbuffer.set_text(msg)

    def process_queue(self):
        """
        Handle all the messages currently in the queue (if any).
        """
        while self._queue.qsize():
            try:
                msg = self._queue.get(0)
                self._write(msg)
            except Queue.Empty:
                pass

        if gservice and gservice.stopped:
            self._set_button_states()
            return False # Stop polling this function
        else:
            return True
        
def thg_serve(ui, repo, **opts):
    class service:
        def init(self):
            self.stopped = True
            util.set_signal_handler()
            try:
                parentui = ui.parentui or ui
                optlist = ("name templates style address port prefix ipv6"
                           " accesslog errorlog webdir_conf certificate")
                for o in optlist.split():
                    if opts[o]:
                        parentui.setconfig("web", o, str(opts[o]))
                        if (repo is not None) and (repo.ui != parentui):
                            repo.ui.setconfig("web", o, str(opts[o]))
                self.httpd = server.create_server(ui, repo)
            except socket.error, inst:
                raise util.Abort(_('cannot start server: ') + inst.args[1])

            if self.httpd.prefix:
                prefix = self.httpd.prefix.strip('/') + '/'
            else:
                prefix = ''

            port = ':%d' % self.httpd.port
            if port == ':80':
                port = ''

            ui.status(_('listening at http://%s%s/%s (%s:%d)\n') %
                      (self.httpd.fqaddr, port, prefix, self.httpd.addr, self.httpd.port))

        def stop(self):
            self.stopped = True
            # issue request to trigger handle_request() and quit
            addr = '%s:%d' % (self.httpd.fqaddr, self.httpd.port)
            conn = httplib.HTTPConnection(addr)
            conn.request("GET", "/")
            res = conn.getresponse()
            res.read()
            conn.close()

        def run(self):
            self.stopped = False
            while not self.stopped:
                self.httpd.handle_request()
            self.httpd.server_close() # release port

    global gservice
    gservice = service()
    cmdutil.service(opts, initfn=gservice.init, runfn=gservice.run)

thg_serve_cmd =  {"^serve":
        (thg_serve,
         [('A', 'accesslog', '', _('name of access log file to write to')),
          ('d', 'daemon', None, _('run server in background')),
          ('', 'daemon-pipefds', '', _('used internally by daemon mode')),
          ('E', 'errorlog', '', _('name of error log file to write to')),
          ('p', 'port', 0, _('port to use (default: 8000)')),
          ('a', 'address', '', _('address to use')),
          ('', 'prefix', '', _('prefix path to serve from (default: server root)')),
          ('n', 'name', '',
           _('name to show in web pages (default: working dir)')),
          ('', 'webdir-conf', '', _('name of the webdir config file'
                                    ' (serve more than one repo)')),
          ('', 'pid-file', '', _('name of file to write process ID to')),
          ('', 'stdio', None, _('for remote clients')),
          ('t', 'templates', '', _('web templates to use')),
          ('', 'style', '', _('template style to use')),
          ('6', 'ipv6', None, _('use IPv6 in addition to IPv4')),
          ('', 'certificate', '', _('SSL certificate file'))],
         _('hg serve [OPTION]...'))}


def run(cwd='', root='', **opts):
    dialog = ServeDialog(cwd, root)
    dialog.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()
    
if __name__ == "__main__":
    import sys
    opts = {}
    opts['cwd'] = os.getcwd()
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or ''
    run(**opts)
