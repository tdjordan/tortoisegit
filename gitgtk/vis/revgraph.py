"""Directed graph production.

This module contains the code to produce an ordered directed graph of a
Mercurial repository, such as we display in the tree view at the top of the
history window.  Original code was from graphlog extension.
"""

__copyright__ = "Copyright 2007 Joel Rosdahl, 2008 Steve Borho"
__author__    = "Joel Rosdahl <joel@rosdahl.net>, Steve Borho <steve@borho.org>"

from mercurial.node import nullrev
from mercurial import cmdutil, util, ui

def __get_parents(repo, rev):
    return [x for x in repo.changelog.parentrevs(rev) if x != nullrev]

def revision_grapher(repo, start_rev, stop_rev, branch=None):
    """incremental revision grapher

    This generator function walks through the revision history from
    revision start_rev to revision stop_rev (which must be less than
    or equal to start_rev) and for each revision emits tuples with the
    following elements:

      - Current revision.
      - lines; a list of (col, next_col, color) indicating the edges between
        the current row and the next row
      - Column of the current node in the set of ongoing edges.
      - parent revisions of current revision
    """

    assert start_rev >= stop_rev
    curr_rev = start_rev
    revs = []
    rev_color = {}
    nextcolor = 0
    while curr_rev >= stop_rev:
        # Compute revs and next_revs.
        if curr_rev not in revs:
            if branch:
                ctx = repo.changectx(curr_rev)
                if ctx.branch() != branch:
                    curr_rev -= 1
                    continue
            # New head.
            revs.append(curr_rev)
            rev_color[curr_rev] = curcolor = nextcolor ; nextcolor += 1
            r = __get_parents(repo, curr_rev)
            while r:
                r0 = r[0]
                if r0 < stop_rev: break
                if r0 in rev_color: break
                rev_color[r0] = curcolor
                r = __get_parents(repo, r0)
        curcolor = rev_color[curr_rev]
        rev_index = revs.index(curr_rev)
        next_revs = revs[:]

        # Add parents to next_revs.
        parents = __get_parents(repo, curr_rev)
        parents_to_add = []
        preferred_color = curcolor
        for parent in parents:
            if parent not in next_revs:
                parents_to_add.append(parent)
                if parent not in rev_color:
                    if preferred_color:
                        rev_color[parent] = preferred_color; preferred_color = None
                    else:
                        rev_color[parent] = nextcolor ; nextcolor += 1
        next_revs[rev_index:rev_index + 1] = parents_to_add

        lines = []
        for i, rev in enumerate(revs):
            if rev in next_revs:
                color = rev_color[rev]
                lines.append( (i, next_revs.index(rev), color) )
            elif rev == curr_rev:
                for parent in parents:
                    color = rev_color[parent]
                    lines.append( (i, next_revs.index(parent), color) )

        yield (curr_rev, (rev_index, curcolor), lines, parents)
        revs = next_revs
        curr_rev -= 1


def filelog_grapher(repo, path):
    '''
    Graph the ancestry of a single file (log).  Deletions show
    up as breaks in the graph.
    '''
    filerev = repo.file(path).count() - 1
    revs = []
    rev_color = {}
    nextcolor = 0
    while filerev >= 0:
        fctx = repo.filectx(path, fileid=filerev)

        # Compute revs and next_revs.
        if filerev not in revs:
            revs.append(filerev)
            rev_color[filerev] = nextcolor ; nextcolor += 1
        curcolor = rev_color[filerev]
        index = revs.index(filerev)
        next_revs = revs[:]

        # Add parents to next_revs.
        parents = [f.filerev() for f in fctx.parents() if f.path() == path]
        parents_to_add = []
        for parent in parents:
            if parent not in next_revs:
                parents_to_add.append(parent)
                if len(parents) > 1:
                    rev_color[parent] = nextcolor ; nextcolor += 1
                else:
                    rev_color[parent] = curcolor
        parents_to_add.sort()
        next_revs[index:index + 1] = parents_to_add

        lines = []
        for i, rev in enumerate(revs):
            if rev in next_revs:
                color = rev_color[rev]
                lines.append( (i, next_revs.index(rev), color) )
            elif rev == filerev:
                for parent in parents:
                    color = rev_color[parent]
                    lines.append( (i, next_revs.index(parent), color) )

        pcrevs = [pfc.rev() for pfc in fctx.parents()]
        yield (fctx.rev(), (index, curcolor), lines, pcrevs)
        revs = next_revs
        filerev -= 1


def dumb_log_generator(repo, revs):
    for revname in revs:
        node = repo.lookup(revname)
        rev = repo.changelog.rev(node)
        yield (rev, (0,0), [], __get_parents(repo, rev))

def filtered_log_generator(repo, pats, opts):
    '''Fill view model iteratively
       repo - Mercurial repository object
       pats - list of file names or patterns
       opts - command line options for log command
    '''
    # Log searches: pattern, keyword, date, etc
    df = False
    if opts['date']:
        df = util.matchdate(opts['date'])

    stack = []
    get = util.cachefunc(lambda r: repo.changectx(r).changeset())
    changeiter, matchfn = cmdutil.walkchangerevs(repo.ui, repo, pats, get, opts)
    for st, rev, fns in changeiter:
        if st == 'iter':
            if stack:
                yield stack.pop()
            continue
        if st != 'add':
            continue
        parents = __get_parents(repo, rev)
        if opts['no_merges'] and len(parents) == 2:
            continue
        if opts['only_merges'] and len(parents) != 2:
            continue

        if df:
            changes = get(rev)
            if not df(changes[2][0]):
                continue

        # TODO: add copies/renames later
        if opts['keyword']:
            changes = get(rev)
            miss = 0
            for k in [kw.lower() for kw in opts['keyword']]:
                if not (k in changes[1].lower() or
                        k in changes[4].lower() or
                        k in " ".join(changes[3]).lower()):
                    miss = 1
                    break
            if miss:
                continue
        stack.append((rev, (0,0), [], parents))
