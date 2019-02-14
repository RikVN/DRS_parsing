#!/usr/bin/env python
# -*- coding: utf8 -*-

'''
Contrast CLFs that have particular phenomena.
This script is used to print side-by-side a system produced CLF and the gold CLF
given that the gold CLF contains some phenomena we are quantifying in system output
contact: Lasha.Abzianidze@gmail.com 
'''
# example how to run: 
# compare those DRSs that contain POS and NOT operators at the same time or that contain NEC operator
# python src/python/contrast_clfs.py  trg_gold  src_system_output  -ok POS NOT -ok NEC

from __future__ import unicode_literals
from clf_referee import check_clf, get_signature, pr_clf, clf_typing
import codecs
import argparse
import re
import sys
#import pmb
#import utils
from collections import Counter
from nltk.tokenize import word_tokenize

#################################
############ Arguments ##########
def parse_arguments():
    parser = argparse.ArgumentParser(description='Contrast set of CLFs')
    parser.add_argument('trg', metavar='FILE', help='File containing gold CLFs')
    parser.add_argument('src', metavar='FILE', help='File containing system output CLFs')
    parser.add_argument('-ok', '--op_keywords', action='append', nargs='+', default = [],
        metavar='LIST of LIST', help='disjunctive normal form of keyword based on which CLFs are filtered')
    parser.add_argument('-tk', '--token_keywords', action='append', nargs='+', default = [],
        metavar='LIST of LIST', help='disjunctive normal form of regular expressions based on which raw texts are filtered')
    parser.add_argument('-pn', '--pronouns', action='store_true',
        help='Compare those that include pronouns')
    parser.add_argument('-s', '--sig', dest='sig_file', default = '', 
        help='If added, this contains a file with all allowed roles\
              otherwise a simple signature is used that\
              mainly recognizes operators based on their formatting')     
    parser.add_argument('-v', '--verbose', dest='v', default=0, type=int,
        metavar='N', help='verbosity level of reporting')
    args = parser.parse_args()
    return args    



#################################
def file_to_clf_dict(filepath, v=0):
    '''Reads a file with clausal forms inside it with ids and raw texts.
       If ids and raw texts are not explicitly titled, then it uses 
       auto enumeration and the last comment starting with %%% is assumed to contain the raw text.
       Returns a dctionary of clausal form and raw sentence pairs
       An empty line is a separator of clausal forms
       % starts comments.
    '''
    clf_dict = dict()
    clf = []
    count = 0 # for files that doesn't have explicit sentence IDs
    pos_raw = '' # possible raw text that is expected to start with %%%
    with codecs.open(filepath, 'r', encoding='UTF-8') as f:
        for line in f:
            line = line.strip()
            # when the line is a commnet. Comments sometimes may include sentence ID and raw text 
            if line.startswith("%"):
                m_sen = re.match('% Sentence: (\d+)', line)
                if m_sen:
                    clf_id = int(m_sen.group(1))
                    continue
                m_raw = re.match('% Raw sent: (.+)', line)
                if m_raw:
                    raw = m_raw.group(1) 
                if line.startswith("%%%"): pos_raw = line # save possibly raw text for possible later usage
                continue
            # when empty line is met -- a clf seperator
            if not line.strip():
                if clf: # if non-empty clf
                    try: raw
                    except NameError, UnboundLocalError: raw = None
                    try: clf_id
                    except NameError, UnboundLocalError: clf_id = count
                    #print clf_id, type(clf_id)
                    clf_dict[clf_id] = (raw, clf)
                    clf = []
                    del clf_id, raw 
                    count += 1
                continue
            # an empty CLFs, system couldnt produce CLF
            if line.find('WARNING: empty') != -1:
                clf.append(tuple('No CLF was generated'.split()))
                continue
            # detect non-explicitly mentioned raw text as the last %%% comment
            if pos_raw.startswith("%%% ") and not clf and 'raw' not in locals(): # avoid rewriting 'Raw sent'
                raw = pos_raw[4:].strip()
            if line.startswith("%%%"): pos_raw = line # save possibly raw text for possible later usage  
            # processing a clause
            # remove % comments if any
            clause = line.split(' %', 1)[0].strip()
            if v >= 5: print "/{}/".format(clause)
            clause = tuple(clause.split(' '))
            clf.append(clause)
    if clf: # add last clf
        try: raw
        except NameError, UnboundLocalError: raw = None
        try: clf_id
        except NameError, UnboundLocalError: clf_id = count
        clf_dict[clf_id] = (raw, clf)
    #if v >= 0:
    #    for clf in list_of_clf:
    #        pr_clf(clf)
    #        print
    return clf_dict 


#################################
def key_dnf_match_set(dnf, key_set, pr=False, v=0):
    '''Whether DNF of keywords match the set.
       Return a list of those keys that fall in key_set
    '''
    matched_keys = []
    for keys in dnf:
        if set(keys) <= key_set:
            matched_keys.append(keys)
    if pr:
        return ' '.join(["[{}]".format(' '.join(l)) for l in matched_keys])
    else:
        return matched_keys

#################################
def get_anaphoric_pronouns(out='dict'):
    '''Return a list or a list of lists of anaphoric pronouns'''
    pronouns = {'he': ['he', 'him', 'his', 'himslef'], 
                'she': ['she', 'her', 'hers', 'herself'], 
                'it': ['it', 'its', 'itself'], 
                'they': ['they', 'their', 'them', 'theirs', 'themselves']
               } 
    if out == 'dnf': # return a list of lists representing a disjunctive normal form
        return [ [x] for group in pronouns.values() for x in group ] 
    if out == 'list':
        return [ x for group in pronouns.values() for x in group ]   
    if out == 'dict':
        return pronouns
    else:
        raise RuntimeError("Unknown input parameter")
        
#################################
############ MAIN ###############
#################################

if __name__ == '__main__':
    args = parse_arguments()
    print '%%% Generated by the command: ' + ' '.join(sys.argv)
    # check if mandatory parameters are there
    dnf_ops = args.op_keywords
    dnf_tks = get_anaphoric_pronouns(out='dnf') if args.pronouns else args.token_keywords
    if not (dnf_ops or dnf_tks) or (dnf_ops and dnf_tks):
        raise RuntimeError("Exactly one of Operator or Token filtering-DNF should be specified")
    # get CLFs from the file
    src_clf_dict = file_to_clf_dict(args.src, v=args.v) 
    trg_clf_dict = file_to_clf_dict(args.trg, v=args.v) 
    # check number of retrieved clfs
    src_total = len(src_clf_dict)
    trg_total = len(trg_clf_dict)
    print "{} src and {} trg clfs retrieved".format(src_total, trg_total)
    # get info about signature as dictionary
    signature = get_signature(args.sig_file, v=args.v)  
    # define counters
    trg_err_counter = Counter()  
    src_err_counter = Counter()
    # contrast CLFs
    sen_ids = []
    for sid in trg_clf_dict:
        # read raw and CLFs
        (raw, trg_clf) = trg_clf_dict[sid]  
        #pr_clf(trg_clf, pr=True, inline=False)
        (src_raw, src_clf) = src_clf_dict[sid] 
        #print raw, src_raw      
        #assert raw == src_raw or src_raw is None 
        # check validity of Gold CLF. If it is invalid, report and go to next CLF
        try:
            check_clf(trg_clf, signature, v=args.v)
        except RuntimeError as e:
            trg_err_counter.update([e[0]])
            print '!nvGold [{}] "{}":\tThe gold CLF is invalid'.format(sid, raw)
            continue
        # check validity of Source CLF
        try:
            check_clf(src_clf, signature, v=args.v)
            src_invalid = ''
        except RuntimeError as e:
            src_err_counter.update([e[0]])
            #print '!nvSyst [{}] "{}":\tThe system produced CLF is invalid'.format(sid, raw)
            src_invalid = '!!!Invalid CLF ' 
        # detect which filter to apply
        dnf = dnf_ops if dnf_ops else dnf_tks 
        # get operator types of the target CLF and carry out filtering
        (trg_op_types, _) = clf_typing(trg_clf, signature, v=args.v)
        trg_set = set(trg_op_types) if dnf_ops else set(word_tokenize(raw.lower())) 
        trg_match = key_dnf_match_set(dnf, trg_set, pr=True, v=args.v)
        # get operator types of the source CLF and carry out filtering
        try: # it can be invalid due to an invalid clause
            (src_op_types, _) = clf_typing(src_clf, signature, v=args.v)
            src_set = set(src_op_types) if dnf_ops else set(raw.lower().split()) 
            src_match = key_dnf_match_set(dnf, src_set, pr=True, v=args.v)
        except RuntimeError as e:
            src_invalid += e[0]
            src_match = False
        # get nice clausal forms in case of printing 
        pr_trg_clf = pr_clf(trg_clf, inline=False, indent=4)
        pr_src_clf = pr_clf(src_clf, inline=False, indent=4)
        if trg_match: # when trg CLF has the wanted phenomena 
            print 'JudgeIt [{}] "{}":\n\tGold keys: [{}]\n\tSystem keys: [{}]'.format(
                sid, raw, trg_match, src_match)
            print 'Gold CLF:\n{}\n{}System CLF:\n{}'.format(pr_trg_clf, src_invalid, pr_src_clf)
            sen_ids.append(sid)
        elif src_match: # and no trg_match
            print 'JudgeIt [{}] "{}":\n\tOnly system keys: [{}]'.format(sid, raw, src_match)
            print 'Gold CLF:\n{}\n{}System CLF:\n{}'.format(pr_trg_clf, src_invalid, pr_src_clf)
            sen_ids.append(sid)
        elif src_invalid: # src is invalid  
            print '!nvSrce [{}] "{}":\tThe source CLF is invalid'.format(sid, raw)
        else:
            if args.v >= 1: print 'NoMatch [{}] "{}":\tCLFs do not contain those operators'.format(sid, raw)        
    print "Done! {} pairs to be Judged".format(len(sen_ids)) 
    if args.v >= 1: print "The list to be Judged:\n{}".format(', '.join(str(x) for x in sen_ids))           

