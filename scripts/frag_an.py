#!/usr/bin/env python
DESC="""EPP diluting the concentration of samples in the fragment analyzer step"""

from argparse import ArgumentParser
from genologics.lims import Lims
from genologics.config import BASEURI,USERNAME,PASSWORD
from scilifelab_epps.epp import attach_file, EppLogger
import sys
import csv
from genologics.entities import *


def main(lims, args):
    process=Process(lims, id=args.pid)
    log=[]
    fid=None
    #first, read the fragment analyzer results
    for o in process.all_outputs():
        if o.name=='CSV Result File':
            try:
                fid=o.files[0].id
            except:
                sys.exit("Please upload a CSV result file.")
    file_contents=lims.get_file_contents(id=fid)
    frag_data={}
    keys=[]
    for line in file_contents.splitlines():
        if not keys:
            keys=line.split(',')
        else:
            values=line.split(',')
            frag_data[values[0]]={}
            for i in xrange(1, len(values)):
                frag_data[values[0]][keys[i]]=values[i]
    #Then, read the concentration from the step defined in the process udf
    try:
        conc_process_name=process.udf['Concentration Source']
    except KeyError:
        log.append("Concentration Source is not defined.")

    for io in process.input_output_maps:
        if 'Fragment Analyzer' in io[1]['uri'].name:
            base_concentration=None
            base_conc_unit=None
            try:
                concentration_step=lims.get_processes(type=conc_process_name, inputartifactlimsid=io[0]['limsid'])[0]
            except IndexError:
                log.append("Cannot find a {} step starting with {}".format(concentration_step.id, io[0]['limsid']))
            else:
                for io2 in concentration_step.input_output_maps:
                    if io2[0]['limsid']==io[0]['limsid'] and "Concentration" in io2[1]['uri'].udf:
                        base_concentration=io2[1]['uri'].udf['Concentration']
                        base_conc_unit=io2[1]['uri'].udf['Conc. Units']




            well=io[0]['uri'].location[1].replace(":","")
            try:
                io[1]['uri'].udf['Min Size (bp)']=int(frag_data[well]['Range'].split('to')[0].split('bp')[0].strip())
                io[1]['uri'].udf['Max Size (bp)']=int(frag_data[well]['Range'].split('to')[1].split('bp')[0].strip())
                io[1]['uri'].udf['Ratio (%)']=float(frag_data[well]['% Total'])
                io[1]['uri'].udf['Size (bp)']=int(frag_data[well]['Avg. Size'])
                io[1]['uri'].put()

                if base_concentration and base_conc_unit:
                    io[1]['uri'].udf['Concentration']=base_concentration * (float(frag_data[well]['% Total']) / 100)
                    io[1]['uri'].udf['Conc. Units']=base_conc_unit
                    io[1]['uri'].put()
                    log.append("Updated values for output {}".format(io[1]['uri'].name))
                else:
                    log.append("Failed to update the concentration of output {}".format(io[1]['uri'].name))

            except Exception as e:
                log.append("Error updating {} with fragment analyzer data : {}".format(io[1]['uri'].name, e))

            

if __name__=="__main__":
    parser = ArgumentParser(description=DESC)
    parser.add_argument('--pid',
                        help='Lims id for current Process')
    parser.add_argument('--read',  dest='read', action='store_true',
                        help='reads the output csv and populates the fields')
    parser.add_argument('--calc', dest='calc', action='store_true',
                        help='recalculates the concentration')
    args = parser.parse_args()

    lims = Lims(BASEURI, USERNAME, PASSWORD)
    lims.check_version()
    main(lims, args)
