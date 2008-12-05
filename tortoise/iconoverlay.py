# Published under the GNU GPL, v2 or later.
# Copyright (C) 2007 Henry Ludemann <misc@hl.id.au>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

import os
import win32api
import win32con
from win32com.shell import shell, shellcon
import _winreg
from mercurial import hg, cmdutil, util
from mercurial import repo as _repo
import thgutil
import sys

# FIXME: quick workaround traceback caused by missing "closed" 
# attribute in win32trace.
from mercurial import ui
def write_err(self, *args):
    for a in args:
        sys.stderr.write(str(a))
ui.ui.write_err = write_err

# file/directory status
UNCHANGED = "unchanged"
ADDED = "added"
MODIFIED = "modified"
UNKNOWN = "unknown"
NOT_IN_REPO = "n/a"

# file status cache
CACHE_TIMEOUT = 5000
overlay_cache = {}
cache_tick_count = 0
cache_root = None
cache_pdir = None

# some misc constants
S_OK = 0
S_FALSE = 1

def add_dirs(list):
    dirs = set()
    for f in list:
        dir = os.path.dirname(f)
        if dir in dirs:
            continue
        while dir:
            dirs.add(dir)
            dir = os.path.dirname(dir)
    list.extend(dirs)

class IconOverlayExtension(object):
    """
    Class to implement icon overlays for source controlled files.
    Specialized classes are created for each overlay icon.

    Displays a different icon based on version control status.

    NOTE: The system allocates only 15 slots in _total_ for all
        icon overlays; we (will) use 6, tortoisecvs uses 7... not a good
        recipe for a happy system. By utilizing the TortoiseOverlay.dll
        we can share overlay slots with the other tortoises.
    """
    
    counter = 0

    _com_interfaces_ = [shell.IID_IShellIconOverlayIdentifier]
    _public_methods_ = [
        "GetOverlayInfo", "GetPriority", "IsMemberOf"
        ]
    _reg_threading_ = 'Apartment'

    def GetOverlayInfo(self): 
        return ("", 0, 0) 

    def GetPriority(self):
        return 0
        
    def _get_state(self, upath):
        """
        Get the state of a given path in source control.
        """
        global overlay_cache, cache_tick_count
        global cache_root, cache_pdir
        
        #print "called: _get_state(%s)" % path
        tc = win32api.GetTickCount()
        
        try:
            # handle some Asian charsets
            path = upath.encode('mbcs')
        except:
            path = upath

        # check if path is cached
        pdir = os.path.dirname(path)
        if cache_pdir == pdir and overlay_cache:
            if tc - cache_tick_count < CACHE_TIMEOUT:
                try:
                    status = overlay_cache[path]
                except:
                    status = UNKNOWN
                print "%s: %s (cached)" % (path, status)
                return status
            else:
                print "Timed out!!"
                overlay_cache.clear()

        # path is a drive
        if path.endswith(":\\"):
            overlay_cache[path] = UNKNOWN
            return NOT_IN_REPO

        # open repo
        if cache_pdir == pdir:
            root = cache_root
        else:
            print "find new root"
            cache_pdir = pdir
            cache_root = root = thgutil.find_root(pdir)
        print "_get_state: root = ", root
        if root is None:
            print "_get_state: not in repo"
            overlay_cache = {None : None}
            cache_tick_count = win32api.GetTickCount()
            return NOT_IN_REPO

        try:
            tc1 = win32api.GetTickCount()
            repo = hg.repository(ui.ui(), path=root)
            print "hg.repository() took %d ticks" % (win32api.GetTickCount() - tc1)

            # check if to display overlay icons in this repo
            global_opts = ui.ui().configlist('tortoisehg', 'overlayicons', [])
            repo_opts = repo.ui.configlist('tortoisehg', 'overlayicons', [])
            
            print "%s: global overlayicons = " % path, global_opts
            print "%s: repo overlayicons = " % path, repo_opts
            is_netdrive =  thgutil.netdrive_status(path) is not None
            if (is_netdrive and 'localdisks' in global_opts) \
                    or 'False' in repo_opts:
                print "%s: overlayicons disabled" % path
                overlay_cache = {None : None}
                cache_tick_count = win32api.GetTickCount()
                return NOT_IN_REPO
        except _repo.RepoError:
            # We aren't in a working tree
            print "%s: not in repo" % dir
            overlay_cache[path] = UNKNOWN
            return NOT_IN_REPO

        # get file status
        tc1 = win32api.GetTickCount()

        modified, added, removed, deleted = [], [], [], []
        unknown, ignored, clean = [], [], []
        files = []
        try:
            files, matchfn, anypats = cmdutil.matchpats(repo, [pdir])
            modified, added, removed, deleted, unknown, ignored, clean = \
                    repo.status(files=files, list_ignored=True, 
                            list_clean=True, list_unknown=True)

            # add directory status to list
            for grp in (clean,modified,added,removed,deleted,ignored,unknown):
                add_dirs(grp)
        except util.Abort, inst:
            print "abort: %s" % inst
            print "treat as unknown : %s" % path
            return UNKNOWN
        
        print "status() took %d ticks" % (win32api.GetTickCount() - tc1)
                
        # cached file info
        tc = win32api.GetTickCount()
        overlay_cache = {}
        for grp, st in (
                (ignored, UNKNOWN),
                (unknown, UNKNOWN),                
                (clean, UNCHANGED),
                (added, ADDED),
                (removed, MODIFIED),
                (deleted, MODIFIED),
                (modified, MODIFIED)):
            for f in grp:
                fpath = os.path.join(repo.root, os.path.normpath(f))
                overlay_cache[fpath] = st

        if path in overlay_cache:
            status = overlay_cache[path]
        else:
            status = overlay_cache[path] = UNKNOWN
        print "%s: %s" % (path, status)
        cache_tick_count = win32api.GetTickCount()
        return status

    def IsMemberOf(self, path, attrib):                  
        try:
            tc = win32api.GetTickCount()
            if self._get_state(path) == self.state:
                return S_OK
            return S_FALSE
        finally:
            print "IsMemberOf: _get_state() took %d ticks" % \
                    (win32api.GetTickCount() - tc)
            
def make_icon_overlay(name, icon_type, state, clsid):
    """
    Make an icon overlay COM class.

    Used to create different COM server classes for highlighting the
    files with different source controlled states (eg: unchanged, 
    modified, ...).
    """
    classname = "%sOverlay" % name
    prog_id = "Mercurial.ShellExtension.%s" % classname
    desc = "Mercurial icon overlay shell extension for %s files" % name.lower()
    reg = [
            (_winreg.HKEY_LOCAL_MACHINE,
             r"Software\TortoiseOverlays\%s" % icon_type,
             [("TortoiseHg", clsid)])
        ]
    cls = type(
            classname,
            (IconOverlayExtension, ),
            dict(_reg_clsid_=clsid, _reg_progid_=prog_id, _reg_desc_=desc, registry_keys=reg, stringKey="HG", state=state))

    _overlay_classes.append(cls)
    # We need to register the class as global, as pythoncom will
    # create an instance of it.
    globals()[classname] = cls

_overlay_classes = []
make_icon_overlay("Changed", "Modified", MODIFIED, "{4D0F33E1-654C-4A1B-9BE8-E47A98752BAB}")
make_icon_overlay("Unchanged", "Normal", UNCHANGED, "{4D0F33E2-654C-4A1B-9BE8-E47A98752BAB}")
make_icon_overlay("Added", "Added", ADDED, "{4D0F33E3-654C-4A1B-9BE8-E47A98752BAB}")
