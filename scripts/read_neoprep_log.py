#!/usr/bin/env python
from __future__ import print_function
import logging
import os
import sys

from argparse import ArgumentParser
from genologics.lims import Lims
from genologics.config import BASEURI,USERNAME,PASSWORD
from genologics.entities import *
from scilifelab_epps.epp import attach_file
DESC="""EPP used to create csv files for the nanoprep robot"""


def read_log(lims, pid, logfile):
    logger=setupLog(logfile)
    pro=Process(lims, id=pid)
    f=None
    for out in pro.all_outputs():
        if out.type == "ResultFile" and out.name == "NeoPrep Output Log File":
            try:
                fid=out.files[0].id
            except IndexError:
                logger.error("Can't find the machine log file")
                print("Cannot find the NeoPrep Output Log File", file=sys.stderr)
                exit(2)

            file_contents=lims.get_file_contents(id=fid)
            if isinstance(file_contents, bytes):
                file_contents = file_contents.decode('utf-8')
            logger.info("Found the machine log file")

    if file_contents:
        data={}
        read=False
        #default values
        ist_size_idx=5
        sample_idx=2
        conc_idx=6
        norm_idx=7
        stat_idx=8
        logger.info("Reading the file")
        for line in file_contents.split('\n') :
            #This does something that is close from csv.dictreader, but the file is FUBAR
            if not line.rstrip():
                read=False
            if read:
                if "Start Well" in line:
                    #Header row
                    #identify which column goes with which index
                    elements=line.split('\t')
                    for idx, el in enumerate(elements):
                        if el == "Name":
                            sample_idx=idx
                        elif el == "Quant":
                            conc_idx=idx
                        elif el == "Norm":
                            norm_idx=idx
                        elif el == "Status":
                            stat_idx=idx
                        elif el == "Insert Size":
                            ist_size_idx=idx
                else:
                    elements=line.split('\t')
                    #data rows
                    data[elements[sample_idx]]={}
                    data[elements[sample_idx]]['conc']=elements[conc_idx]
                    data[elements[sample_idx]]['norm']=elements[norm_idx]
                    data[elements[sample_idx]]['stat']=elements[stat_idx]
                    data[elements[sample_idx]]['ist_size']=elements[ist_size_idx]

            if "[Sample Information]" in line:
                read=True
        logger.info("obtained data for samples {0}".format(list(data.keys())))

    for inp in pro.all_inputs():
        #save the data from the logfile to the lims artifacts
        if inp.name in data:
            if data[inp.name]['stat'] == 'Pass':
                inp.qc="PASSED"
            elif data[inp.name]['stat'] == 'Fail':
                inp.qc="FAILED"

            try:
                inp.udf['Molar Conc. (nM)']=float(data[inp.name]['conc'])
            except ValueError:
                inp.udf['Molar Conc. (nM)']=0
            try:
                inp.udf['Normalized conc. (nM)']=float(data[inp.name]['norm'])
            except ValueError:
                inp.udf['Normalized conc. (nM)']=0
            try:
                inp.udf['Size (bp)']=float(data[inp.name]['ist_size'])
            except ValueError:
                inp.udf['Size (bp)']=0
            inp.udf['NeoPrep Machine QC']=data[inp.name]['stat']
            inp.put()
            logger.info("updated sample {0}".format(inp.name))

    for out in pro.all_outputs():
        #attach the epp log
        if out.name=="EPP Log":
            attach_file(os.path.join(os.getcwd(), logfile), out)






def setupLog(logfile):
        mainlog = logging.getLogger(__name__)
        mainlog.setLevel(level=logging.INFO)
        mfh = logging.FileHandler(logfile)
        mft = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        mfh.setFormatter(mft)
        mainlog.addHandler(mfh)
        return mainlog


if __name__ == "__main__":
    parser = ArgumentParser(description=DESC)
    parser.add_argument('--pid',
                        help='Lims id for current Process')
    parser.add_argument('--log', default="read_neoprep_log.log",
                        help='logfile for this epp')
    args = parser.parse_args()

    lims = Lims(BASEURI, USERNAME, PASSWORD)
    lims.check_version()
    read_log(lims, args.pid, args.log)
