#
# miscellaneous PyGTK classes and functions for TortoiseHg
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import pygtk
pygtk.require('2.0')
import gtk
import gobject
import pango

class StatusBar(gtk.HBox):
    def __init__(self, extra=None):
        gtk.HBox.__init__(self)
        self.pbar = gtk.ProgressBar()
        self.sttext = gtk.Label("")
        self.sttext.set_ellipsize(pango.ELLIPSIZE_END)
        self.sttext.set_alignment(0, 0.5)

        self.pbox = gtk.HBox()
        self.pbox.pack_start(gtk.VSeparator(), False, False)
        self.pbox.pack_start(self.pbar, False, False)
        
        self.pack_start(self.sttext, padding=1)
        if extra:
            self.pack_end(extra, False, False)
        self.pack_end(self.pbox, False, False, padding=1)
        self.pbox.set_child_visible(False)
        self.show_all()
        
    def _pulse_timer(self, now=False):
        self.pbar.pulse()
        return True

    def begin(self, msg="Running", timeout=100):
        self.pbox.set_child_visible(True)
        self.pbox.map()
        self.set_status_text(msg)
        self._timeout_event = gobject.timeout_add(timeout, self._pulse_timer)

    def end(self, msg="Done", unmap=True):
        gobject.source_remove(self._timeout_event)
        self.set_status_text(msg)
        if unmap:
            self.pbox.unmap()
        else:
            self.pbar.set_fraction(1.0)

    def set_status_text(self, msg):
        self.sttext.set_text(str(msg))
        
    def set_pulse_step(self, val):
        self.pbar.set_pulse_step(val)

class MessageDialog(gtk.Dialog):
    button_map = {
            gtk.BUTTONS_NONE: None,
            gtk.BUTTONS_OK: (gtk.STOCK_OK, gtk.RESPONSE_OK),
            gtk.BUTTONS_CLOSE : (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE),
            gtk.BUTTONS_CANCEL: (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL),
            gtk.BUTTONS_YES_NO : (gtk.STOCK_YES, gtk.RESPONSE_YES,
                    gtk.STOCK_NO, gtk.RESPONSE_NO),
            gtk.BUTTONS_OK_CANCEL: (gtk.STOCK_OK, gtk.RESPONSE_OK,
                    gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL),
    }
    image_map = {
            gtk.MESSAGE_INFO : gtk.STOCK_DIALOG_INFO,
            gtk.MESSAGE_WARNING : gtk.STOCK_DIALOG_WARNING,
            gtk.MESSAGE_QUESTION : gtk.STOCK_DIALOG_QUESTION,
            gtk.MESSAGE_ERROR : gtk.STOCK_DIALOG_ERROR,
    }
    
    def __init__(self, parent=None, flags=0, type=gtk.MESSAGE_INFO,
            buttons=gtk.BUTTONS_NONE, message_format=None):
        gtk.Dialog.__init__(self,
                parent=parent,
                flags=flags | gtk.DIALOG_NO_SEPARATOR, 
                buttons=MessageDialog.button_map[buttons])
        self.set_resizable(False)

        hbox = gtk.HBox()
        self._image_frame = gtk.Frame()
        self._image_frame.set_shadow_type(gtk.SHADOW_NONE)
        self._image = gtk.Image()
        self._image.set_from_stock(MessageDialog.image_map[type],
                gtk.ICON_SIZE_DIALOG)
        self._image_frame.add(self._image)
        hbox.pack_start(self._image_frame, padding=5)

        lblbox = gtk.VBox(spacing=10)
        self._primary = gtk.Label("")
        self._primary.set_alignment(0.0, 0.5)
        self._primary.set_line_wrap(True)
        lblbox.pack_start(self._primary)

        self._secondary = gtk.Label()
        lblbox.pack_end(self._secondary)
        self._secondary.set_line_wrap(True)
        hbox.pack_start(lblbox, padding=5)

        self.vbox.pack_start(hbox, False, False, 10)
        self.show_all()

    def set_markup(self, s):
        self._primary.set_markup(s)

    def format_secondary_markup(self, message_format):
        self._secondary.set_markup(message_format)

    def format_secondary_text(self, message_format):
        self._secondary.set_text(message_format)

    def set_image(self, image):
        self._image_frame.remove(self._image)
        self._image = image
        self._image_frame.add(self._image)
        self._image.show()
