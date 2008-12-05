#
# changeset.py - Changeset dialog for TortoiseHg
#
# Copyright 2008 Steve Borho <steve@borho.org>
#

import os
import subprocess
import sys
import time

import pygtk
pygtk.require('2.0')
import gtk
import gobject
import pango
import StringIO

from mercurial.i18n import _
from mercurial.node import *
from mercurial import cmdutil, util, ui, hg, commands
from mercurial import context, patch, revlog
from gdialog import *
from hgcmd import CmdDialog
from hglib import toutf, fromutf
from gtklib import StatusBar


class ChangeSet(GDialog):
    """GTK+ based dialog for displaying repository logs
    """
    def __init__(self, ui, repo, cwd, pats, opts, main, stbar=None):
        GDialog.__init__(self, ui, repo, cwd, pats, opts, main)
        self.stbar = stbar

    def get_title(self):
        title = os.path.basename(self.repo.root) + ' changeset '
        title += self.opts['rev'][0]
        return title

    def get_icon(self):
        return 'menushowchanged.ico'

    def get_tbbuttons(self):
        self.parent_toggle = gtk.ToggleToolButton(gtk.STOCK_UNDO)
        self.parent_toggle.set_use_underline(True)
        self.parent_toggle.set_label('_other parent')
        self.parent_toggle.set_tooltip(self.tooltips, 'diff other parent')
        self.parent_toggle.set_sensitive(False)
        self.parent_toggle.set_active(False)
        self.parent_toggle.connect('toggled', self._parent_toggled)
        return [self.parent_toggle]

    def _parent_toggled(self, button):
        self.load_details(self.currev)

    def prepare_display(self):
        self.currow = None
        self.graphview = None
        self.glog_parent = None
        node0, node1 = cmdutil.revpair(self.repo, self.opts.get('rev'))
        self.load_details(self.repo.changelog.rev(node0))

    def save_settings(self):
        settings = GDialog.save_settings(self)
        settings['changeset'] = self._hpaned.get_position()
        return settings

    def load_settings(self, settings):
        GDialog.load_settings(self, settings)
        if settings and 'changeset' in settings:
            self._setting_hpos = settings['changeset']
        else:
            self._setting_hpos = -1

    def load_details(self, rev):
        '''Load selected changeset details into buffer and filelist'''
        self.currev = rev
        self._buffer.set_text('')
        self._filelist.clear()

        parents = [x for x in self.repo.changelog.parentrevs(rev) \
                if x != nullrev]
        self.parents = parents
        title = self.get_title()
        if len(parents) == 2:
            self.parent_toggle.set_sensitive(True)
            if self.parent_toggle.get_active():
                title += ':' + str(self.parents[1])
            else:
                title += ':' + str(self.parents[0])
        else:
            self.parent_toggle.set_sensitive(False)
            if self.parent_toggle.get_active():
                # Parent button must be pushed out, but this
                # will cause load_details to be called again
                # so we exit out to prevent recursion.
                self.parent_toggle.set_active(False)
                return

        ctx = self.repo.changectx(rev)
        if not ctx:
            self._last_rev = None
            return False
        self.set_title(title)
        self.textview.freeze_child_notify()
        try:
            self._fill_buffer(self._buffer, rev, ctx, self._filelist)
        finally:
            self.textview.thaw_child_notify()

    def _fill_buffer(self, buf, rev, ctx, filelist):
        self.stbar.begin('Retrieving changeset data...')
        
        def title_line(title, text, tag):
            pad = ' ' * (12 - len(title))
            utext = toutf(title + pad + text)
            buf.insert_with_tags_by_name(eob, utext, tag)
            buf.insert(eob, "\n")

        # TODO: Add toggle for gmtime/localtime
        eob = buf.get_end_iter()
        date = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ctx.date()[0]))
        if self.clipboard:
            self.clipboard.set_text(short(ctx.node()))
        change = str(rev) + ':' + short(ctx.node())
        tags = ' '.join(ctx.tags())
        parents = self.parents

        title_line('changeset:', change, 'changeset')
        if ctx.branch() != 'default':
            title_line('branch:', ctx.branch(), 'greybg')
        title_line('user/date:', ctx.user() + '\t' + date, 'changeset')
        for p in parents:
            pctx = self.repo.changectx(p)
            summary = pctx.description().splitlines()[0]
            summary = toutf(summary)
            change = str(p) + ':' + short(self.repo.changelog.node(p))
            title = 'parent:'
            title += ' ' * (12 - len(title))
            buf.insert_with_tags_by_name(eob, title, 'parent')
            buf.insert_with_tags_by_name(eob, change, 'link')
            buf.insert_with_tags_by_name(eob, ' ' + summary, 'parent')
            buf.insert(eob, "\n")
        for n in self.repo.changelog.children(ctx.node()):
            cctx = self.repo.changectx(n)
            summary = cctx.description().splitlines()[0]
            summary = toutf(summary)
            childrev = self.repo.changelog.rev(n)
            change = str(childrev) + ':' + short(n)
            title = 'child:'
            title += ' ' * (12 - len(title))
            buf.insert_with_tags_by_name(eob, title, 'parent')
            buf.insert_with_tags_by_name(eob, change, 'link')
            buf.insert_with_tags_by_name(eob, ' ' + summary, 'parent')
            buf.insert(eob, "\n")
        for n in self.repo.changelog.children(ctx.node()):
            childrev = self.repo.changelog.rev(n)
        if tags: title_line('tags:', tags, 'tag')

        log = toutf(ctx.description())
        buf.insert(eob, '\n' + log + '\n\n')

        if self.parent_toggle.get_active():
            parent = self.repo.changelog.node(parents[1])
        elif parents:
            parent = self.repo.changelog.node(parents[0])
        else:
            parent = nullid

        buf.create_mark('begmark', buf.get_start_iter())
        filelist.append(('*', '[Description]', 'begmark', False, ()))
        pctx = self.repo.changectx(parent)

        nodes = parent, ctx.node()
        iterator = self.diff_generator(*nodes)
        gobject.idle_add(self.get_diffs, iterator, nodes, pctx, buf, filelist)
        self.curnodes = nodes

    def get_diffs(self, iterator, nodes, pctx, buf, filelist):
        if self.curnodes != nodes:
            return False

        try:
            status, file, txt = iterator.next()
        except StopIteration:
            self.stbar.end()
            return False

        lines = txt.splitlines()
        eob = buf.get_end_iter()
        offset = eob.get_offset()
        fileoffs, tags, lines, statmax = self.prepare_diff(lines, offset, file)
        for l in lines:
            buf.insert(eob, l)

        # inserts the tags
        for name, p0, p1 in tags:
            i0 = buf.get_iter_at_offset(p0)
            i1 = buf.get_iter_at_offset(p1)
            txt = buf.get_text(i0, i1)
            buf.apply_tag_by_name(name, i0, i1)
            
        # inserts the marks
        for mark, offset, stats in fileoffs:
            pos = buf.get_iter_at_offset(offset)
            mark = 'mark_%d' % offset
            buf.create_mark(mark, pos)
            filelist.append((status, toutf(file), mark, True, stats))
        sob, eob = buf.get_bounds()
        buf.apply_tag_by_name("mono", pos, eob)
        return True

    # Hacked up version of mercurial.patch.diff()
    # Use git mode by default (to show copies, renames, permissions) but
    # never show binary diffs.  It operates as a generator, so it can be
    # called iteratively to get file diffs from a changeset
    def diff_generator(self, node1, node2):
        repo = self.repo

        ccache = {}
        def getctx(r):
            if r not in ccache:
                ccache[r] = context.changectx(repo, r)
            return ccache[r]

        flcache = {}
        def getfilectx(f, ctx):
            flctx = ctx.filectx(f, filelog=flcache.get(f))
            if f not in flcache:
                flcache[f] = flctx._filelog
            return flctx

        ctx1 = context.changectx(repo, node1) # parent
        ctx2 = context.changectx(repo, node2) # current

        if node1 == repo.changelog.parents(node2)[0]:
            filelist = ctx2.files()
        else:
            changes = repo.status(node1, node2, None)[:5]
            modified, added, removed, deleted, unknown = changes
            filelist = modified + added + removed


        # force manifest reading
        man1 = ctx1.manifest()
        date1 = util.datestr(ctx1.date())

        execf2 = ctx2.manifest().execf
        linkf2 = ctx2.manifest().linkf

        # returns False if there was no rename between ctx1 and ctx2
        # returns None if the file was created between ctx1 and ctx2
        # returns the (file, node) present in ctx1 that was renamed to f in ctx2
        # This will only really work if c1 is the Nth 1st parent of c2.
        def renamed(c1, c2, man, f):
            startrev = c1.rev()
            c = c2
            crev = c.rev()
            if crev is None:
                crev = repo.changelog.count()
            orig = f
            files = (f,)
            while crev > startrev:
                if f in files:
                    try:
                        src = getfilectx(f, c).renamed()
                    except revlog.LookupError:
                        return None
                    if src:
                        f = src[0]
                crev = c.parents()[0].rev()
                # try to reuse
                c = getctx(crev)
                files = c.files()
            if f not in man:
                return None
            if f == orig:
                return False
            return f

        status = {}
        def filestatus(f):
            if f in status:
                return status[f]
            try:
                # Determine file status by presence in manifests
                s = 'R'
                ctx2.filectx(f)
                s = 'A'
                ctx1.filectx(f)
                s = 'M'
            except revlog.LookupError:
                pass
            status[f] = s
            return s

        copied = {}
        for f in filelist:
            src = renamed(ctx1, ctx2, man1, f)
            if src:
                copied[f] = src

        srcs = [x[1] for x in copied.iteritems() if filestatus(x[0]) == 'A']

        gone = {}
        for f in filelist:
            s = filestatus(f)
            to = None
            tn = None
            dodiff = True
            header = []
            if f in man1:
                to = getfilectx(f, ctx1).data()
            if s != 'R':
                tn = getfilectx(f, ctx2).data()
            a, b = f, f
            def gitmode(x, l):
                return l and '120000' or (x and '100755' or '100644')
            def addmodehdr(header, omode, nmode):
                if omode != nmode:
                    header.append('old mode %s\n' % omode)
                    header.append('new mode %s\n' % nmode)

            if s == 'A':
                mode = gitmode(execf2(f), linkf2(f))
                if f in copied:
                    a = copied[f]
                    omode = gitmode(man1.execf(a), man1.linkf(a))
                    addmodehdr(header, omode, mode)
                    if filestatus(a) == 'R' and a not in gone:
                        op = 'rename'
                        gone[a] = 1
                    else:
                        op = 'copy'
                    header.append('%s from %s\n' % (op, a))
                    header.append('%s to %s\n' % (op, f))
                    to = getfilectx(a, ctx1).data()
                else:
                    header.append('new file mode %s\n' % mode)
                if util.binary(tn):
                    dodiff = 'binary'
            elif s == 'R':
                if f in srcs:
                    dodiff = False
                else:
                    mode = gitmode(man1.execf(f), man1.linkf(f))
                    header.append('deleted file mode %s\n' % mode)
            else:
                omode = gitmode(man1.execf(f), man1.linkf(f))
                nmode = gitmode(execf2(f), linkf2(f))
                addmodehdr(header, omode, nmode)
                if util.binary(to) or util.binary(tn):
                    dodiff = 'binary'
            header.insert(0, 'diff --git a/%s b/%s\n' % (a, b))
            if dodiff == 'binary':
                text = 'binary file has changed.\n'
            elif dodiff:
                try:
                    text = patch.mdiff.unidiff(to, date1,
                                    tn, util.datestr(ctx2.date()),
                                    fn1=a, fn2=b, r=None,
                                    opts=patch.mdiff.defaultopts)
                except TypeError:
                    # hg-0.9.5 and before
                    text = patch.mdiff.unidiff(to, date1,
                                    tn, util.datestr(ctx2.date()),
                                    f, None, opts=patch.mdiff.defaultopts)
            else:
                text = ''
            if header or text: yield (s, f, ''.join(header) + text)

    def prepare_diff(self, difflines, offset, fname):
        '''Borrowed from hgview; parses changeset diffs'''
        DIFFHDR = "=== %s ===\n"
        idx = 0
        outlines = []
        tags = []
        filespos = []
        def addtag( name, offset, length ):
            if tags and tags[-1][0] == name and tags[-1][2]==offset:
                tags[-1][2] += length
            else:
                tags.append( [name, offset, offset+length] )
        stats = [0,0]
        statmax = 0
        for i,l1 in enumerate(difflines):
            l = toutf(l1)
            if l.startswith("diff"):
                txt = toutf(DIFFHDR % fname)
                addtag( "greybg", offset, len(txt) )
                outlines.append(txt)
                markname = "file%d" % idx
                idx += 1
                statmax = max( statmax, stats[0]+stats[1] )
                stats = [0,0]
                filespos.append(( markname, offset, stats ))
                offset += len(txt.decode('utf-8'))
                continue
            elif l.startswith("+++"):
                continue
            elif l.startswith("---"):
                continue
            elif l.startswith("+"):
                tag = "green"
                stats[0] += 1
            elif l.startswith("-"):
                stats[1] += 1
                tag = "red"
            elif l.startswith("@@"):
                tag = "blue"
            else:
                tag = "black"
            l = l+"\n"
            length = len(l.decode('utf-8'))
            addtag( tag, offset, length )
            outlines.append( l )
            offset += length
        statmax = max( statmax, stats[0]+stats[1] )
        return filespos, tags, outlines, statmax

    def link_event(self, tag, widget, event, iter):
        if event.type != gtk.gdk.BUTTON_RELEASE:
            return
        text = self.get_link_text(tag, widget, iter)
        if not text:
            return
        linkrev = long(text.split(':')[0])
        if self.graphview:
            self.graphview.set_revision_id(linkrev)
            self.graphview.scroll_to_revision(linkrev)
        else:
            self.load_details(linkrev)

    def get_link_text(self, tag, widget, iter):
        """handle clicking on a link in a textview"""
        text_buffer = widget.get_buffer()
        beg = iter.copy()
        while not beg.begins_tag(tag):
            beg.backward_char()
        end = iter.copy()
        while not end.ends_tag(tag):
            end.forward_char()
        text = text_buffer.get_text(beg, end)
        return text
        
    def file_context_menu(self):
        def create_menu(label, callback):
            menuitem = gtk.MenuItem(label, True)
            menuitem.connect('activate', callback)
            menuitem.set_border_width(1)
            return menuitem
            
        _menu = gtk.Menu()
        _menu.append(create_menu('_view at revision', self._view_file_rev))
        self._save_menu = create_menu('_save at revision', self._save_file_rev)
        _menu.append(self._save_menu)
        _menu.append(create_menu('_file history', self._file_history))
        self._ann_menu = create_menu('_annotate file', self._ann_file)
        _menu.append(self._ann_menu)
        _menu.append(create_menu('_revert file contents', self._revert_file))
        self._file_diff_to_mark_menu = create_menu('_diff file to mark',
                self._diff_file_to_mark)
        self._file_diff_from_mark_menu = create_menu('diff file _from mark',
                self._diff_file_from_mark)
        _menu.append(self._file_diff_to_mark_menu)
        _menu.append(self._file_diff_from_mark_menu)
        _menu.show_all()
        return _menu

    def get_body(self):
        if self.repo.ui.configbool('tortoisehg', 'copyhash'):
            sel = (os.name == 'nt') and 'CLIPBOARD' or 'PRIMARY'
            self.clipboard = gtk.Clipboard(selection=sel)
        else:
            self.clipboard = None
        self._filemenu = self.file_context_menu()

        details_frame = gtk.Frame()
        details_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        details_frame.add(scroller)
        
        details_text = gtk.TextView()
        details_text.set_wrap_mode(gtk.WRAP_NONE)
        details_text.set_editable(False)
        details_text.modify_font(pango.FontDescription(self.fontcomment))
        scroller.add(details_text)

        self._buffer = gtk.TextBuffer()
        self.setup_tags()
        details_text.set_buffer(self._buffer)
        self.textview = details_text

        filelist_tree = gtk.TreeView()
        filesel = filelist_tree.get_selection()
        filesel.connect("changed", self._filelist_rowchanged)
        filelist_tree.connect('button-release-event',
                self._file_button_release)
        filelist_tree.connect('popup-menu', self._file_popup_menu)
        filelist_tree.connect('row-activated', self._file_row_act)

        self._filelist = gtk.ListStore(
                gobject.TYPE_STRING,   # MAR status
                gobject.TYPE_STRING,   # filename (utf-8 encoded)
                gobject.TYPE_PYOBJECT, # mark
                gobject.TYPE_PYOBJECT, # give cmenu
                gobject.TYPE_PYOBJECT, # diffstats
                )
        filelist_tree.set_model(self._filelist)
        column = gtk.TreeViewColumn('Stat', gtk.CellRendererText(), text=0)
        filelist_tree.append_column(column)
        column = gtk.TreeViewColumn('Files', gtk.CellRendererText(), text=1)
        filelist_tree.append_column(column)

        list_frame = gtk.Frame()
        list_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(filelist_tree)
        list_frame.add(scroller)

        self._hpaned = gtk.HPaned()
        self._hpaned.pack1(list_frame, True, True)
        self._hpaned.pack2(details_frame, True, True)
        self._hpaned.set_position(self._setting_hpos)

        if self.stbar:
            # embedded by changelog browser
            return self._hpaned
        else:
            # add status bar for main app
            vbox = gtk.VBox()
            vbox.pack_start(self._hpaned, True, True)
            self.stbar = StatusBar()
            self.stbar.show()
            vbox.pack_start(gtk.HSeparator(), False, False)
            vbox.pack_start(self.stbar, False, False)
            return vbox

    def setup_tags(self):
        """Creates the tags to be used inside the TextView"""
        def make_texttag( name, **kwargs ):
            """Helper function generating a TextTag"""
            tag = gtk.TextTag(name)
            for key, value in kwargs.iteritems():
                key = key.replace("_","-")
                try:
                    tag.set_property( key, value )
                except TypeError:
                    print "Warning the property %s is unsupported in" % key
                    print "this version of pygtk"
            return tag

        tag_table = self._buffer.get_tag_table()

        tag_table.add( make_texttag('changeset', foreground='#000090',
                paragraph_background='#F0F0F0'))
        tag_table.add(make_texttag('date', foreground='#000090',
                paragraph_background='#F0F0F0'))
        tag_table.add(make_texttag('tag', foreground='#000090',
                paragraph_background='#F0F0F0'))
        tag_table.add(make_texttag('files', foreground='#5C5C5C',
                paragraph_background='#F0F0F0'))
        tag_table.add(make_texttag('parent', foreground='#000090',
                paragraph_background='#F0F0F0'))

        tag_table.add( make_texttag( "mono", family="Monospace" ))
        tag_table.add( make_texttag( "blue", foreground='blue' ))
        tag_table.add( make_texttag( "red", foreground='red' ))
        tag_table.add( make_texttag( "green", foreground='darkgreen' ))
        tag_table.add( make_texttag( "black", foreground='black' ))
        tag_table.add( make_texttag( "greybg",
                                     paragraph_background='grey',
                                     weight=pango.WEIGHT_BOLD ))
        tag_table.add( make_texttag( "yellowbg", background='yellow' ))
        link_tag = make_texttag( "link", foreground="blue",
                                 underline=pango.UNDERLINE_SINGLE )
        link_tag.connect("event", self.link_event )
        tag_table.add( link_tag )

    def _filelist_rowchanged(self, sel):
        model, iter = sel.get_selected()
        if not iter:
            return
        # scroll to file in details window
        mark = self._buffer.get_mark(model[iter][2])
        self.textview.scroll_to_mark(mark, 0.0, True, 0.0, 0.0)
        if model[iter][3]:
            self.curfile = fromutf(model[iter][1])
        else:
            self.curfile = None

    def _file_button_release(self, widget, event):
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK |
            gtk.gdk.CONTROL_MASK)):
            self._file_popup_menu(widget, event.button, event.time)
        return False

    def _file_popup_menu(self, treeview, button=0, time=0):
        if self.curfile is None:
            return
        if self.graphview:
            is_mark = self.graphview.get_mark_rev() is not None
        else:
            is_mark = False
        self._file_diff_to_mark_menu.set_sensitive(is_mark)
        self._file_diff_from_mark_menu.set_sensitive(is_mark)
        self._filemenu.popup(None, None, None, button, time)

        # If the filelog entry this changeset references does not link
        # back to this changeset, it means this changeset did not
        # actually change the contents of this file, and thus the file
        # cannot be annotated at this revision (since this changeset
        # does not appear in the filelog)
        ctx = self.repo.changectx(self.currev)
        try:
            fctx = ctx.filectx(self.curfile)
            has_filelog = fctx.filelog().linkrev(fctx.filenode()) == ctx.rev()
        except revlog.LookupError:
            has_filelog = False
        self._ann_menu.set_sensitive(has_filelog)
        self._save_menu.set_sensitive(has_filelog)
        return True

    def _file_row_act(self, tree, path, column) :
        """Default action is the first entry in the context menu
        """
        self._filemenu.get_children()[0].activate()
        return True

    def _save_file_rev(self, menuitem):
        file = util.localpath(self.curfile)
        file, ext = os.path.splitext(os.path.basename(file))
        filename = "%s@%d%s" % (file, self.currev, ext)
        fd = NativeSaveFileDialogWrapper(Title = "Save file to",
                                         InitialDir=self.cwd,
                                         FileName=filename)
        result = fd.run()
        if result:
            import Queue
            import hglib
            q = Queue.Queue()
            cpath = util.canonpath(self.repo.root, self.cwd, self.curfile)
            hglib.hgcmd_toq(self.repo.root, q, 'cat', '--rev',
                str(self.currev), '--output', result, cpath)

    def _view_file_rev(self, menuitem):
        '''User selected view file revision from the file list context menu'''
        if not self.curfile:
            # ignore view events for the [Description] row
            return
        rev = self.currev
        parents = self.parents
        if len(parents) == 0:
            parent = rev-1
        else:
            parent = parents[0]
        pair = '%u:%u' % (parent, rev)
        self._node1, self._node2 = cmdutil.revpair(self.repo, [pair])
        self._view_file('M', self.curfile, force_left=False)

    def _diff_file_to_mark(self, menuitem):
        '''User selected diff to mark from the file list context menu'''
        from status import GStatus
        from gtools import cmdtable
        rev0 = self.graphview.get_mark_rev()
        rev1 = self.currev
        statopts = self.merge_opts(cmdtable['gstatus|gst'][1],
                ('include', 'exclude', 'git'))
        statopts['rev'] = ['%u:%u' % (rev1, rev0)]
        statopts['modified'] = True
        statopts['added'] = True
        statopts['removed'] = True
        dialog = GStatus(self.ui, self.repo, self.cwd, [self.curfile],
                statopts, False)
        dialog.display()
        return True

    def _diff_file_from_mark(self, menuitem):
        '''User selected diff from mark from the file list context menu'''
        from status import GStatus
        from gtools import cmdtable
        rev0 = self.graphview.get_mark_rev()
        rev1 = self.currev
        statopts = self.merge_opts(cmdtable['gstatus|gst'][1],
                ('include', 'exclude', 'git'))
        statopts['rev'] = ['%u:%u' % (rev0, rev1)]
        statopts['modified'] = True
        statopts['added'] = True
        statopts['removed'] = True
        dialog = GStatus(self.ui, self.repo, self.cwd, [self.curfile],
                statopts, False)
        dialog.display()

    def _ann_file(self, menuitem):
        '''User selected diff from mark from the file list context menu'''
        from datamine import DataMineDialog
        rev = self.currev
        dialog = DataMineDialog(self.ui, self.repo, self.cwd, [], {}, False)
        dialog.display()
        dialog.add_annotate_page(self.curfile, str(rev))

    def _file_history(self, menuitem):
        '''User selected file history from file list context menu'''
        if self.glog_parent:
            # If this changeset browser is embedded in glog, send
            # send this event to the main app
            opts = {'filehist' : self.curfile}
            self.glog_parent.custombutton.set_active(True)
            self.glog_parent.graphview.refresh(True, None, opts)
        else:
            # Else launch our own GLog instance
            from history import GLog
            dialog = GLog(self.ui, self.repo, self.cwd, [self.repo.root],
                    {}, False)
            dialog.open_with_file(self.curfile)
            dialog.display()

    def _revert_file(self, menuitem):
        '''User selected file revert from the file list context menu'''
        rev = self.currev
        dialog = Confirm('revert file to old revision', [], self,
                'Revert %s to contents at revision %d?' % (self.curfile, rev))
        if dialog.run() == gtk.RESPONSE_NO:
            return
        cmdline = ['hg', 'revert', '--verbose', '--rev', str(rev), self.curfile]
        dlg = CmdDialog(cmdline)
        dlg.run()
        dlg.hide()
        shell_notify([self.curfile])

def run(root='', cwd='', files=[], **opts):
    u = ui.ui()
    u.updateopts(debug=False, traceback=False)
    repo = hg.repository(u, path=root)

    dialog = ChangeSet(u, repo, cwd, files, opts, True)
    dialog.display()

    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or os.getcwd()
    opts['rev'] = ['750']
    run(**opts)
