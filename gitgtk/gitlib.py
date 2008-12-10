import gtk
import os.path
import sys
import traceback
import threading, thread2
import Queue
from mercurial import hg, ui, util, extensions, commands, hook
from mercurial.repo import RepoError
from mercurial.node import *
from mercurial.i18n import _
from dialog import entry_dialog

try:
    try:
        from mercurial import demandimport
    except:
        from mercurial.commands import demandimport # pre 0.9.5
    demandimport.disable()

    try:
        # Mercurail 0.9.4
        from mercurial.cmdutil import parse
        from mercurial.cmdutil import parseconfig as _parseconfig
    except:
        try:
            # Mercurail <= 0.9.3
            from mercurial.commands import parse
            from mercurial.commands import parseconfig as _parseconfig
        except:
            # Mercurail 0.9.5
            from mercurial.dispatch import _parse as parse
            from mercurial.dispatch import _parseconfig
finally:
    demandimport.enable()

def toutf(s):
    """
    Convert a string to UTF-8 encoding
    
    Based on mercurial.util.tolocal()
    """
    for e in ('utf-8', util._encoding):
        try:
            return s.decode(e, 'strict').encode('utf-8')
        except UnicodeDecodeError:
            pass
    return s.decode(util._fallbackencoding, 'replace').encode('utf-8')

def fromutf(s):
    """
    Convert UTF-8 encoded string to local.
    
    It's primarily used on strings converted to UTF-8 by toutf().
    """
    try:
        return s.decode('utf-8').encode(util._encoding)
    except UnicodeDecodeError:
        pass
    except UnicodeEncodeError:
        pass
    return s.decode('utf-8').encode(util._fallbackencoding)

def rootpath(path=None):
    """ find Mercurial's repo root of path """
    if not path:
        path = os.getcwd()
    p = os.path.isdir(path) and path or os.path.dirname(path)
    while not os.path.isdir(os.path.join(p, ".hg")):
        oldp = p
        p = os.path.dirname(p)
        if p == oldp:
            return ''
    return p


class GtkUi(ui.ui):
    '''
    PyGtk enabled mercurial.ui subclass.  All this code will be running
    in a background thread, so it cannot directly call into Gtk.
    Instead, it places output and dialog requests onto queues for the
    main thread to pickup.
    '''
    def __init__(self, outputq=None, dialogq=None, responseq=None,
            parentui=None):
        super(GtkUi, self).__init__()
        if parentui:
            self.parentui = parentui.parentui or parentui
            self.cdata = ui.dupconfig(self.parentui.cdata)
            self.verbose = parentui.verbose
            self.outputq = parentui.outputq
            self.dialogq = parentui.dialogq
            self.responseq = parentui.responseq
        else:
            self.outputq = outputq
            self.dialogq = dialogq
            self.responseq = responseq
        self.interactive = True

    def write(self, *args):
        if self.buffers:
            self.buffers[-1].extend([str(a) for a in args])
        else:
            for a in args:
                self.outputq.put(str(a))

    def write_err(self, *args):
        for a in args:
            self.outputq.put('*** ' + str(a))

    def flush(self):
        pass

    def prompt(self, msg, pat=None, default="y"):
        import re
        if not self.interactive: return default
        while True:
            try:
                # send request to main thread, await response
                self.dialogq.put( (msg, True, default) )
                r = self.responseq.get(True)
                if not r:
                    return default
                if not pat or re.match(pat, r):
                    return r
                else:
                    self.write(_("unrecognized response\n"))
            except EOFError:
                raise util.Abort(_('response expected'))

    def getpass(self, prompt=None, default=None):
        # send request to main thread, await response
        self.dialogq.put( (prompt or _('password: '), False, default) )
        return self.responseq.get(True)

    def print_exc(self):
        traceback.print_exc()
        return True

class HgThread(thread2.Thread):
    '''
    Run an hg command in a background thread, implies output is being
    sent to a rendered text buffer interactively and requests for
    feedback from Mercurial can be handled by the user via dialog
    windows.
    '''
    def __init__(self, args=[], postfunc=None, parent=None):
        self.outputq = Queue.Queue()
        self.dialogq = Queue.Queue()
        self.responseq = Queue.Queue()
        self.ui = GtkUi(self.outputq, self.dialogq, self.responseq)
        self.args = args
        self.ret = None
        self.postfunc = postfunc
        self.parent = parent
        thread2.Thread.__init__(self)

    def getqueue(self):
        return self.outputq

    def return_code(self):
        '''
        None - command is incomplete, possibly exited with exception
        0    - command returned successfully
               else an error was returned
        '''
        return self.ret

    def process_dialogs(self):
        '''Polled every 10ms to serve dialogs for the background thread'''
        try:
            (prompt, visible, default) = self.dialogq.get_nowait()
            self.dlg = entry_dialog(self.parent, prompt, visible, default,
                    self.dialog_response)
        except Queue.Empty:
            pass

    def dialog_response(self, widget, response_id):
        if response_id == gtk.RESPONSE_OK:
            text = self.dlg.entry.get_text()
        else:
            text = None
        self.dlg.destroy()
        self.responseq.put(text)

    def run(self):
        try:
            # Some commands create repositories, and thus must create
            # new ui() instances.  For those, we monkey-patch ui.ui()
            # as briefly as possible
            origui = None
            if self.args[0] in ('clone', 'init'):
                origui = ui.ui
                ui.ui = GtkUi
            try:
                ret = thgdispatch(self.ui, None, self.args)
            finally:
                if origui:
                    ui.ui = origui
            if ret:
                self.ui.write('[command returned code %d]\n' % int(ret))
            else:
                self.ui.write('[command completed successfully]\n')
            self.ret = ret or 0
            if self.postfunc:
                self.postfunc(ret)
        except RepoError, e:
            self.ui.write_err(str(e))
        except util.Abort, e:
            self.ui.write_err(str(e))
            if self.ui.traceback:
                self.ui.print_exc()
        except Exception, e:
            self.ui.write_err(str(e))
            self.ui.print_exc()

def _earlygetopt(aliases, args):
    """Return list of values for an option (or aliases).

    The values are listed in the order they appear in args.
    The options and values are removed from args.
    """
    try:
        argcount = args.index("--")
    except ValueError:
        argcount = len(args)
    shortopts = [opt for opt in aliases if len(opt) == 2]
    values = []
    pos = 0
    while pos < argcount:
        if args[pos] in aliases:
            if pos + 1 >= argcount:
                # ignore and let getopt report an error if there is no value
                break
            del args[pos]
            values.append(args.pop(pos))
            argcount -= 2
        elif args[pos][:2] in shortopts:
            # short option can have no following space, e.g. hg log -Rfoo
            values.append(args.pop(pos)[2:])
            argcount -= 1
        else:
            pos += 1
    return values

_loaded = {}
def thgdispatch(ui, path=None, args=[]):
    '''
    Replicate functionality of mercurial dispatch but force the use
    of the passed in ui for all purposes
    '''
    # read --config before doing anything else
    # (e.g. to change trust settings for reading .hg/hgrc)
    config = _earlygetopt(['--config'], args)
    if config:
        ui.updateopts(config=_parseconfig(config))

    # check for cwd
    cwd = _earlygetopt(['--cwd'], args)
    if cwd:
        os.chdir(cwd[-1])

    # read the local repository .hgrc into a local ui object
    path = rootpath(path) or ""
    if path:
        try:
            ui.readconfig(os.path.join(path, ".hg", "hgrc"))
        except IOError:
            pass

    # now we can expand paths, even ones in .hg/hgrc
    rpath = _earlygetopt(["-R", "--repository", "--repo"], args)
    if rpath:
        path = ui.expandpath(rpath[-1])

    extensions.loadall(ui)
    if not hasattr(extensions, 'extensions'):
        extensions.extensions = lambda: () # pre-0.9.5, loadall did below
    for name, module in extensions.extensions():
        if name in _loaded:
            continue

        # setup extensions
        extsetup = getattr(module, 'extsetup', None)
        if extsetup:
            extsetup()

        cmdtable = getattr(module, 'cmdtable', {})
        overrides = [cmd for cmd in cmdtable if cmd in commands.table]
        if overrides:
            ui.warn(_("extension '%s' overrides commands: %s\n")
                    % (name, " ".join(overrides)))
        commands.table.update(cmdtable)
        _loaded[name] = 1

    # check for fallback encoding
    fallback = ui.config('ui', 'fallbackencoding')
    if fallback:
        util._fallbackencoding = fallback

    fullargs = args
    cmd, func, args, options, cmdoptions = parse(ui, args)

    if options["encoding"]:
        util._encoding = options["encoding"]
    if options["encodingmode"]:
        util._encodingmode = options["encodingmode"]
    ui.updateopts(options["verbose"], options["debug"], options["quiet"],
                 not options["noninteractive"], options["traceback"])

    if options['help']:
        return commands.help_(ui, cmd, options['version'])
    elif options['version']:
        return commands.version_(ui)
    elif not cmd:
        return commands.help_(ui, 'shortlist')

    repo = None
    if cmd not in commands.norepo.split():
        try:
            repo = hg.repository(ui, path=path)
            repo.ui = ui
            ui.setconfig("bundle", "mainreporoot", repo.root)
            if not repo.local():
                raise util.Abort(_("repository '%s' is not local") % path)
        except RepoError:
            if cmd not in commands.optionalrepo.split():
                if not path:
                    raise RepoError(_("There is no Mercurial repository here"
                                         " (.hg not found)"))
                raise
        d = lambda: func(ui, repo, *args, **cmdoptions)
    else:
        d = lambda: func(ui, *args, **cmdoptions)

    # run pre-hook, and abort if it fails
    ret = hook.hook(ui, repo, "pre-%s" % cmd, False, args=" ".join(fullargs))
    if ret:
        return ret

    # Run actual command
    try:
        ret = d()
    except TypeError, inst:
        # was this an argument error?
        tb = traceback.extract_tb(sys.exc_info()[2])
        if len(tb) != 2: # no
            raise
        raise ParseError(cmd, _("invalid arguments"))

    # run post-hook, passing command result
    hook.hook(ui, repo, "post-%s" % cmd, False, args=" ".join(fullargs),
            result = ret)
    return ret


def hgcmd_toq(path, q, *args):
    '''
    Run an hg command in a background thread, pipe all output to a Queue
    object.  Assumes command is completely noninteractive.
    '''
    class Qui(ui.ui):
        def __init__(self):
            ui.ui.__init__(self)
            self.interactive = False

        def write(self, *args):
            if self.buffers:
                self.buffers[-1].extend([str(a) for a in args])
            else:
                for a in args:
                    q.put(str(a))
    u = Qui()
    return thgdispatch(u, path, list(args))
