#!/usr/bin/env python

import re
import os
import sys
import pandas as pd

try:
    from io import StringIO
except ImportError:
    from StringIO import StringIO

from argparse import ArgumentParser
from datetime import datetime
from genologics.lims import Lims
from genologics.entities import Process
from scilifelab_epps.epp import EppLogger
from genologics.config import BASEURI, USERNAME, PASSWORD

from data.Chromium_10X_indexes import Chromium_10X_indexes

DESC = """EPP used to check index distance in library pool"""

# Pre-compile regexes in global scope:
IDX_PAT = re.compile("([ATCG]{4,}N*)-?([ATCG]*)")
TENX_PAT = re.compile("SI-(?:GA|NA)-[A-H][1-9][0-2]?")
ST_PAT = re.compile("SI-(?:TT|NT|NN|TN)-[A-H][1-9][0-2]?")
SMARTSEQ_PAT = re.compile('SMARTSEQ[1-9]?-[1-9][0-9]?[A-P]')
NGISAMPLE_PAT =re.compile("P[0-9]+_[0-9]+")


def check_index_distance(data, log):
    pools = set([x['pool'] for x in data])
    for p in pools:
        subset = [i for i in data if i['pool'] == p]
        if len(subset) == 1:
            return None
        for i, sample_a in enumerate(subset[:-1]):
            j = i+1
            for sample_b in subset[j:]:
                d = 0
                if sample_a.get('idx1', '') and sample_b.get('idx1', ''):
                    d += my_distance(sample_a['idx1'], sample_b['idx1'])
                if sample_a.get('idx2', '') and sample_b.get('idx2', ''):
                    d += my_distance(sample_a['idx2'], sample_b['idx2'])
                if d == 0:
                    idx_a = sample_a.get('idx1', '') + '-' + sample_a.get('idx2', '')
                    idx_b = sample_b.get('idx1', '') + '-' + sample_b.get('idx2', '')
                    log.append("INDEX COLLISION ERROR: {} for sample {} and {} for sample {} in pool {}".format(idx_a, sample_a.get('sn', ''), idx_b, sample_b.get('sn', ''), p))


def my_distance(idx_a, idx_b):
    diffs = 0
    short = min((idx_a, idx_b), key=len)
    lon = idx_a if short == idx_b else idx_b
    for i, c in enumerate(short):
        if c != lon[i]:
            diffs += 1
    return diffs


def prepare_index_table(process, log):
    data=[]
    for out in process.all_outputs():
        if out.type == "Analyte":
            pool_name = out.name
            for sample in out.samples:
                sp_obj = {}
                idxs = find_barcode(sample, process)
                if not idxs or idxs[0] == 'NoIndex':
                    sp_obj['pool'] = pool_name
                    sp_obj['sn'] = sample.name.replace(',','')
                    sp_obj['idx1'] = ''
                    sp_obj['idx2'] = ''
                    data.append(sp_obj)
                    log.append("NO INDEX ERROR: Sample {} in pool {} has no index".format(sp_obj['sn'], sp_obj['pool']))
                elif ST_PAT.findall(idxs[0]):
                    sp_obj['pool'] = pool_name
                    sp_obj['sn'] = sample.name.replace(',','')
                    sp_obj['idx1'] = Chromium_10X_indexes[ST_PAT.findall(idxs[0])[0]][0].replace(',','')
                    sp_obj['idx2'] = Chromium_10X_indexes[ST_PAT.findall(idxs[0])[0]][1].replace(',','')
                    data.append(sp_obj)
                elif TENX_PAT.findall(idxs[0]):
                    for tenXidx in Chromium_10X_indexes[TENX_PAT.findall(idxs[0])[0]]:
                        sp_obj_sub = {}
                        sp_obj_sub['pool'] = pool_name
                        sp_obj_sub['sn'] = sample.name.replace(',','')
                        sp_obj_sub['idx1'] = tenXidx.replace(',','')
                        sp_obj_sub['idx2'] = ''
                        data.append(sp_obj_sub)
                else:
                    sp_obj['pool'] = pool_name
                    sp_obj['sn'] = sample.name.replace(',','')
                    sp_obj['idx1'] = idxs[0].replace(',','') if idxs[0] else ''
                    sp_obj['idx2'] = idxs[1].replace(',','') if idxs[1] else ''
                    data.append(sp_obj)
    return data


def find_barcode(sample, process):
    # print "trying to find {} barcode in {}".format(sample.name, process.name)
    for art in process.all_inputs():
        if sample in art.samples:
            if len(art.samples) == 1 and art.reagent_labels:
                reagent_label_name = art.reagent_labels[0].upper().replace(' ', '')
                idxs = TENX_PAT.findall(reagent_label_name) or ST_PAT.findall(reagent_label_name) or SMARTSEQ_PAT.findall(reagent_label_name)
                if idxs:
                    # Put in tuple with empty string as second index to
                    # match expected type:
                    idxs = (idxs[0], "")
                else:
                    try:
                        idxs = IDX_PAT.findall(reagent_label_name)[0]
                    except IndexError:
                        try:
                            # we only have the reagent label name.
                            rt = lims.get_reagent_types(name=reagent_label_name)[0]
                            idxs = IDX_PAT.findall(rt.sequence)[0]
                        except:
                            return ("NoIndex", "")
                return idxs
            else:
                if art == sample.artifact or not art.parent_process:
                    return []
                else:
                    return find_barcode(sample, art.parent_process)


def main(lims, pid, epp_logger):
    log=[]
    process = Process(lims, id = pid)
    data = prepare_index_table(process, log)
    check_index_distance(data, log)
    if log:
        print('\n'.join(log), file=sys.stderr)
    else:
        print('No issue detected with indexes', file=sys.stderr)


if __name__ == "__main__":
    parser = ArgumentParser(description=DESC)
    parser.add_argument('--pid',
                        help='Lims id for current Process')
    parser.add_argument('--log', dest = 'log',
                        help=('File name for standard log file, '
                              'for runtime information and problems.'))
    args = parser.parse_args()

    lims = Lims(BASEURI, USERNAME, PASSWORD)
    lims.check_version()
    with EppLogger(log_file=args.log, lims=lims, prepend=True) as epp_logger:
        main(lims, args.pid, epp_logger)