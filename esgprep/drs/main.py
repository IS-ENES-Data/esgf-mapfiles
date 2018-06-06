#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    :platform: Unix
    :synopsis: Manages the filesystem tree according to the project the Data Reference Syntax and versioning.

"""

import itertools
import logging
from multiprocessing import Pool

from constants import *
from context import ProcessingContext, ProcessManager
from custom_exceptions import *
from esgprep.utils.misc import load, store, evaluate, checksum, ProcessContext
from handler import File, DRSPath


def process(ffp):
    """
    process(collector_input)

    File process that:

     * Handles files,
     * Deduces facet key, values pairs from file attributes
     * Checks facet values against CV,
     * Applies the versioning
     * Populates the DRS tree crating the appropriate leaves,
     * Stores dataset statistics.


    :param str ffp: The file full path to process

    """
    # Declare context from initializer to avoid IDE warnings
    global cctx
    # Block to avoid program stop if a thread fails
    try:
        # Instantiate file handler
        fh = File(ffp)
        # Ignore files from incoming
        if fh.filename in cctx.ignore_from_incoming:
            return False
        # Loads attributes from filename, netCDF attributes, command-line
        fh.load_attributes(root=cctx.root,
                           pattern=cctx.pattern,
                           set_values=cctx.set_values)
        # Checks the facet values provided by the loaded attributes
        fh.check_facets(facets=cctx.facets,
                        config=cctx.cfg,
                        set_keys=cctx.set_keys)
        # Get parts of DRS path
        parts = fh.get_drs_parts(cctx.facets)
        # Instantiate file DRS path handler
        fph = DRSPath(parts)
        # Ensure that the called project section is ALWAYS part of the DRS path elements (case insensitive)
        assert fph.path().lower().startswith(cctx.project.lower()), 'Inconsistent DRS path. ' \
                                                                    'Must start with "{}/" ' \
                                                                    '(case-insensitive)'.format(cctx.project)
        # If a latest version already exists make some checks FIRST to stop files to not process
        if fph.v_latest:
            # Latest version should be older than upgrade version
            if int(DRSPath.TREE_VERSION[1:]) <= int(fph.v_latest[1:]):
                raise OlderUpgrade(DRSPath.TREE_VERSION, fph.v_latest)
            # Walk through the latest dataset version to check its uniqueness with file checksums
            if not cctx.no_checksum:
                dset_nid = fph.path(f_part=False, latest=True, root=True)
                if dset_nid not in cctx.tree.hash.keys():
                    cctx.tree.hash[dset_nid] = dict()
                    cctx.tree.hash[dset_nid]['latest'] = dict()
                    for root, _, filenames in os.walk(fph.path(f_part=False, latest=True, root=True)):
                        for filename in filenames:
                            cctx.tree.hash[dset_nid]['latest'][filename] = checksum(os.path.join(root, filename),
                                                                                    cctx.checksum_type)
            # Pickup the latest file version
            latest_file = os.path.join(fph.path(latest=True, root=True), fh.filename)
            # Check latest file if exists
            if os.path.exists(latest_file):
                latest_checksum = checksum(latest_file, cctx.checksum_type)
                current_checksum = checksum(fh.ffp, cctx.checksum_type)
                # Check if processed file is a duplicate in comparison with latest version
                if latest_checksum == current_checksum:
                    fh.is_duplicate = True
        # Start the tree generation
        if not fh.is_duplicate:
            # Add the processed file to the "vYYYYMMDD" node
            src = ['..'] * len(fph.items(d_part=False))
            src.extend(fph.items(d_part=False, file_folder=True))
            src.append(fh.filename)
            cctx.tree.create_leaf(nodes=fph.items(root=True),
                                  leaf=fh.filename,
                                  label='{}{}{}'.format(fh.filename, LINK_SEPARATOR, os.path.join(*src)),
                                  src=os.path.join(*src),
                                  mode='symlink',
                                  origin=fh.ffp)
            # Add the "latest" node for symlink
            cctx.tree.create_leaf(nodes=fph.items(f_part=False, version=False, root=True),
                                  leaf='latest',
                                  label='{}{}{}'.format('latest', LINK_SEPARATOR, fph.v_upgrade),
                                  src=fph.v_upgrade,
                                  mode='symlink')
            # Add the processed file to the "files" node
            cctx.tree.create_leaf(nodes=fph.items(file_folder=True, root=True),
                                  leaf=fh.filename,
                                  label=fh.filename,
                                  src=fh.ffp,
                                  mode=cctx.mode)
            if cctx.upgrade_from_latest:
                # Walk through the latest dataset version and create a symlink for each file with a different
                # filename than the processed one
                for root, _, filenames in os.walk(fph.path(f_part=False, latest=True, root=True)):
                    for filename in filenames:
                        # Add latest files as tree leaves with version to upgrade instead of latest version
                        # i.e., copy latest dataset leaves to Tree
                        # Except if file has be ignored from latest version (i.e., with known issue)
                        if filename != fh.filename and filename not in cctx.ignore_from_latest:
                            src = os.path.join(root, filename)
                            cctx.tree.create_leaf(nodes=fph.items(root=True),
                                                  leaf=filename,
                                                  label='{}{}{}'.format(filename, LINK_SEPARATOR, os.readlink(src)),
                                                  src=os.readlink(src),
                                                  mode='symlink',
                                                  origin=os.path.realpath(src))
        else:
            # Pickup the latest file version
            latest_file = os.path.join(fph.path(latest=True, root=True), fh.filename)
            if cctx.upgrade_from_latest:
                # If upgrade from latest is activated, raise the error, no duplicated files allowed
                # Because incoming must only contain modifed/corrected files
                raise DuplicatedFile(latest_file, fh.ffp)
            else:
                # If default behavior, the incoming contains all data for a new version
                # In the case of a duplicated file, just pass to the expected symlink creation
                # and records duplicated file for further removal only if migration mode is the
                # default (i.e., moving files). In the case of --copy or --link, keep duplicates
                # in place into the incoming directory
                src = os.readlink(latest_file)
                cctx.tree.create_leaf(nodes=fph.items(root=True),
                                      leaf=fh.filename,
                                      label='{}{}{}'.format(fh.filename, LINK_SEPARATOR, src),
                                      src=src,
                                      mode='symlink',
                                      origin=fh.ffp)
                if cctx.mode == 'move':
                    cctx.tree.duplicates.append(fh.ffp)
        # Record entry for list()
        incoming = {'src': fh.ffp,
                    'dst': fph.path(root=True),
                    'filename': fh.filename,
                    'latest': fph.v_latest or 'Initial',
                    'size': fh.size}
        if fph.path(f_part=False) in cctx.tree.paths.keys():
            cctx.tree.paths[fph.path(f_part=False)].append(incoming)
        else:
            cctx.tree.paths[fph.path(f_part=False)] = [incoming]
        logging.info('{} <-- {}'.format(fph.path(f_part=False), fh.filename))
        return True
    except KeyboardInterrupt:
        raise
    except Exception as e:
        logging.error('{} skipped\n{}: {}'.format(ffp, e.__class__.__name__, e.message))
        return None
    finally:
        if cctx.pbar:
            cctx.pbar.update()


def initializer(keys, values):
    """
    Initialize process context by setting particular variables as global variables.

    :param list keys: Argument name
    :param list values: Argument value

    """
    assert len(keys) == len(values)
    global cctx
    cctx = ProcessContext({key: values[i] for i, key in enumerate(keys)})


def run(args):
    """
    Main process that:

     * Instantiates processing context,
     * Loads previous program instance,
     * Parallelizes file processing with threads pools,
     * Apply command-line action to the whole DRS tree,
     * Evaluate exit status.

    :param ArgumentParser args: The command-line arguments parser

    """
    # Instantiate processing context
    with ProcessingContext(args) as ctx:
        logging.info('==> Scan started')
        # Init process manager
        manager = ProcessManager()
        if ctx.use_pool:
            manager.start()
        # Init process context
        cctx = {name: getattr(ctx, name) for name in PROCESS_VARS}
        cctx['pbar'] = manager.pbar()
        cctx['cfg'] = manager.cfg()
        cctx['facets'] = manager.list(ctx.facets)
        cctx['tree'] = manager.tree()
        if not ctx.scan:
            reader = load(TREE_FILE)
            _ = reader.next()
            cctx['tree'] = reader.next()
            ctx.scan_err_log = reader.next()
            results = reader.next()
            # Rollback --commands_file value to command-line argument in any case
            cctx['tree'].commands_file = ctx.commands_file
        else:
            if ctx.use_pool:
                # Init processes pool
                pool = Pool(processes=ctx.processes, initializer=initializer, initargs=(cctx.keys(),
                                                                                        cctx.values()))
                processes = pool.imap(process, ctx.sources)
                # Close pool of workers
                pool.close()
                pool.join()
            else:
                initializer(cctx.keys(), cctx.values())
                processes = itertools.imap(process, ctx.sources)
            # Process supplied files
            results = [x for x in processes]
            # Close progress bar
            if cctx['pbar']:
                cctx['pbar'].close()
        # Get number of files scanned (including skipped files)
        ctx.scan_files = len(results)
        # Get number of scan errors
        ctx.scan_errors = results.count(None)
        # Backup tree context for later usage with other command lines
        store(TREE_FILE, data=[{key: ctx.__getattribute__(key) for key in CONTROLLED_ARGS},
                               cctx['tree'],
                               ctx.scan_err_log,
                               results])
        logging.warning('DRS tree recorded for next usage onto {}.'.format(TREE_FILE))
        # Evaluates the scan results to trigger the DRS tree action
        if evaluate(results):
            # Check upgrade uniqueness
            if not ctx.no_checksum:
                cctx['tree'].check_uniqueness(ctx.checksum_type)
            # Apply tree action
            cctx['tree'].get_display_lengths()
            getattr(cctx['tree'], ctx.action)()
