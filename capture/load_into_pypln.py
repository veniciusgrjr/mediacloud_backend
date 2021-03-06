# -*- coding:utf-8 -*-
u"""
Created on 03/04/14
by fccoelho
license: GPL V3 or Later
"""

__docformat__ = 'restructuredtext en'

import sys
import time

import pymongo

import logging
from logging.handlers import RotatingFileHandler
from multiprocessing import Pool

import nlp
import settings


###########################
#  Setting up Logging
###########################
logger = logging.getLogger("load_into_pypln")
logger.setLevel(logging.DEBUG)
# create console handler and set level to debug
fh = RotatingFileHandler('/tmp/load_pypln.log', maxBytes=5e6, backupCount=3)
# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
# logger.addHandler(ch)  # uncomment for console output of messages
logger.addHandler(fh)


## Media Cloud database setup
client = pymongo.MongoClient(host=settings.MONGOHOST)
articles = client.MCDB.articles # articles collection
pypln_temp = client.MCDB.pypln_temp # pypln_temp temporary collection
articles_analysis = client.MCDB.articles_analysis # articles_analysis collection

articles.ensure_index('status')

# Defines status codes
SENT_TO_PYPLN = 'sent_to_pypln'

def load_document(data):
    article, corpus = data
    _id = article['_id']
    logger.debug('Sending article with id {}'.format(_id))
    start_time = time.time()
    try:
        pypln_document = nlp.send_to_pypln(article, corpus)
    except RuntimeError as exc:
        logger.warn('Article with id {} got an error '
                'when uploading'.format(_id), exc_info=exc)
        return False
    end_time = time.time()
    total_time = end_time - start_time

    logger.debug('Inserting article with id {} into '
            'temporary collection'.format(_id))
    pypln_temp.insert({'pypln_url': pypln_document.url, 'articles_id': _id})


    logger.debug('Updating status for article with '
            'id {}'.format(_id))
    articles.update({'_id': _id},
                    {'$set': {"status": SENT_TO_PYPLN}})

    logger.info('inserted document with id {} into PyPLN. Took {} seconds.'.format(
        article['_id'], total_time))

    return True

def load(skip, limit=0):

    corpus = nlp.get_corpus()
    articles_sent = 0
    filter_ = {'status': {'$ne': SENT_TO_PYPLN}}

    find_kwargs = {'sort': [("_id", pymongo.DESCENDING)]}
    if skip:
        find_kwargs.update({'skip': skip})
    if limit:
        find_kwargs.update({'limit': limit})
    if limit == 0:
        count = articles.count()
    else:
        count = limit
    cursor = articles.find(filter_, limit=10000, **find_kwargs)
    logger.debug('{} articles to be sent'.format(count))
    P = Pool()
    while articles_sent < count:
        P.map(load_document, ((article, corpus) for article in cursor))
        articles_sent += 10000
        logger.debug('{}/{} documents sent.'.format(articles_sent, count))
        cursor = articles.find(filter_, limit=10000, **find_kwargs)
    P.close()
    P.join()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=("Load MediaCloud documents"
                                                  "into a PyPLN instance"))

    # parser.add_argument("-c", "--corpus_name", type=str, metavar="NAME",
    # default="MC_articles",
    #         help="Uploads documents to a corpus named NAME")
    parser.add_argument("-l", "--limit", metavar='N', type=int, default=0,
                        help="Adds limit=N to the mongo query")
    parser.add_argument("-s", "--skip", metavar='N', type=int, default=0,
                        help="Adds skip=N to the mongo query")
    args = parser.parse_args()

    load(args.skip, args.limit)
