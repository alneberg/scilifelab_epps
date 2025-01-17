#!/usr/bin/env python
DESC="""Module called by other EPP scripts to write notes to couchdb
"""
import json
import yaml
import couchdb
import smtplib
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import datetime
import markdown

def write_note_to_couch(pid, timestamp, note, lims):
    configf = '~/.statusdb_cred.yaml'
    with open(os.path.expanduser(configf)) as config_file:
        config = yaml.safe_load(config_file)
    if not config['statusdb']:
        email_responsible('Statusdb credentials not found in {}\n '.format(lims), 'genomics-bioinfo@scilifelab.se')
        email_responsible('Running note save for {} failed on LIMS! Please contact {} to resolve the issue!'.format(pid, 'genomics-bioinfo@scilifelab.se'), note['email'])
        sys.exit(1)

    url_string = 'https://{}:{}@{}'.format(config['statusdb'].get('username'), config['statusdb'].get('password'),
                                              config['statusdb'].get('url'))
    couch = couchdb.Server(url=url_string)
    if not couch:
        email_responsible('Connection failed from {} to {}'.format(lims, config['statusdb'].get('url')), 'genomics-bioinfo@scilifelab.se')
        email_responsible('Running note save for {} failed on LIMS! Please contact {} to resolve the issue!'.format(pid, 'genomics-bioinfo@scilifelab.se'), note['email'])

    run_notes_db = couch['running_notes']
    if not run_notes_db.get(note['_id']):
        if '_rev' in note.keys():
            del note['_rev']
        run_notes_db.save(note)
        if not run_notes_db.get(note['_id']):
            msg = 'Running note save failed from {} to {} for {}'.format(lims, config['statusdb'].get('url'), pid)
            for user_email in ['genomics-bioinfo@scilifelab.se', note['email']]:
                email_responsible(msg, user_email)
        else:
            time_in_format = datetime.datetime.strftime(timestamp, "%a %b %d %Y, %I:%M:%S %p")
            proj_db = couch['projects']
            v = proj_db.view('project/project_id')
            for row in v[pid]:
                doc_id = row.value
            doc = proj_db.get(doc_id)
            subject = '[LIMS] Running Note:{}, {}'.format(pid, doc['project_name'])
            proj_coord_name = doc['details'].get('project_coordinator','').lower()
            trans_table = proj_coord_name.maketrans('áéíóú', 'aeiou')
            proj_coord_name_trans = proj_coord_name.translate(trans_table)
            proj_coord = '.'.join(proj_coord_name_trans.split()) + '@scilifelab.se'
            text = 'A note has been created from LIMS in the project {}, {}! The note is as follows\n\
            >{} - {}{}\
            >{}'.format(pid, doc['project_name'], note['user'], time_in_format, note.get('category'), note)

            html = '<html>\
            <body>\
            <p> \
            A note has been created from LIMS in the project {}, {}! The note is as follows</p>\
            <blockquote>\
            <div class="panel panel-default" style="border: 1px solid #e4e0e0; border-radius: 4px;">\
            <div class="panel-heading" style="background-color: #f5f5f5; padding: 10px 15px;">\
                <a href="#">{}</a> - <span>{}</span> <span>{}</span>\
            </div>\
            <div class="panel-body" style="padding: 15px;">\
                <p>{}</p>\
            </div></div></blockquote></body></html>'.format(pid, doc['project_name'], note['user'],
                                    time_in_format, ', '.join(note.get('categories')), markdown.markdown(note.get('note')))
            email_responsible(text, proj_coord, error=False, subject=subject, html=html)

def email_responsible(message, resp_email, error=True, subject=None, html=None):
    if error:
        body = 'Error: '+message
        body += '\n\n--\nThis is an automatically generated error notification'
        msg = MIMEText(body)
        msg['Subject'] = '[Error] Running note sync error from LIMS to Statusdb'
    else:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['To'] = resp_email


        msg.attach(MIMEText(message, 'plain'))
        msg.attach(MIMEText(html, 'html'))

    msg['From'] = 'Lims_monitor'
    msg['To'] = resp_email

    s = smtplib.SMTP('localhost')
    s.sendmail('genologics-lims@scilifelab.se', msg['To'], msg.as_string())
    s.quit()
