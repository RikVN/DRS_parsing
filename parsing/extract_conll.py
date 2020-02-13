#!/usr/bin/env python
# -*- coding: utf8 -*-

'''Script extracts token-level annotations with desired statuses and splits them
   into desired part defined by a regex for part numbers. The extracted data is formatted
   similarly to the CoNLL-U format. The first column is always for tokens the rest of
   the columns can be changed according to wish. Raw sentences and document IDs are
   included as comments. One needs to provide a file path for a json file that records
   document ids, available translations and their annotation statuses. If the file doesn't
   exist, it will be created.
   Works with python 3
Usage:
Extract gold standard data for English semantic tagging and split it into
train, dev, and test parts (according to the offcial PMB recommendation):
   $ python THIS_FILE.py  en  PMB_DATA_DIR  DIR_FOR_SPLIT_FILES  -j statuses.json -ls tok:g sem:g
Extract silver standard data for English semantic tagging that will be used only
for training (therefore, all the data is collected in a single file 'train_silver'):
   $ python THIS_FILE.py  en  PMB_DATA_DIR  DIR_FOR_SPLIT_FILES  -j statuses.json -ls tok:g sem:s  -sp train_silver:..
# Extract gold standard data for German semantic role labeling, append it with
additional annotation layers, like CCG categories, semantic tags, and symbols of
at least silver annotation status and split it into recommended train, dev, and test parts:
   $ python THIS_FILE.py  de  PMB_DATA_DIR  DIR_FOR_SPLIT_FILES  -j statuses.json -ls tok:g rol:g cat:gs sem:gs sym:gs
'''

import xml.etree.ElementTree as ET
import sys
import json
import os
import re
from os import path as op
import argparse
import logging
from logging import debug, info, warning, error
from collections import defaultdict
import copy
import string

##########################################################################
###################### Parsing the argument list #########################
def parse_arguments():
    parser = argparse.ArgumentParser(description=\
        'Extract and split token-level annotations from the PMB release')
    # Arguments covering directories and files
    parser.add_argument(
    "lang", choices=['en', 'de', 'it', 'nl'], metavar="LANG",
        help="Language of the documents")
    parser.add_argument(
    "data_dir", metavar="DIR_PATH",
        help="Path to the 'data' directory of the PMB release")
    parser.add_argument(
    "split_dir", metavar="DIR_PATH",
        help="The directory where the data splits will be placed")
    parser.add_argument(
    "-j", metavar="PATH", dest='status_json', required=True,
        help="A json file that keeps the statuses of layers of all documents. "
             "If the file doesn't exist, it is created and takes >1h")
    # Arguments covering filters about splits, parts, annotation layers and their statuses
    parser.add_argument(
    "-ls", dest='ly_st', required=True, nargs="+", metavar="LAYER:STATUSES",
        help="A list of layer and status pairs delimited with (:). "
             "Use tok, sym, sns, cat, sem, rol for the PMB annotation layers, "
             "and g, s, b for annotation statuses. It is possible to group "
             "the statuses. No specified status is equivalemt to ':gsb'. "
             "An example: tok:g sym:gs cat rol:s")
    parser.add_argument(
    "-sp", nargs="+", dest='sp_pt', metavar="SPLIT_NAME:PART_PATTERN",
        default=['dev:.0', 'test:.1', 'train:.[2-9]'],
        help="File names of splits with their corresponding python regex for parts. "
             "An example suitable for silver data: all_silver:..")
    # Meta arguments
    parser.add_argument(
    "-v", dest="verbose", default=1, type=int, choices=[0, 1, 2], metavar="LEVEL",
        help="Verbosity of logging: warning(0), info(1), debug(2)")

    # pre-processing arguments
    args = parser.parse_args()
    # Set verbosity
    verbose = {0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
    logging.basicConfig(format='%(levelname)s: %(message)s', level=verbose[args.verbose])
    # preprocess layer:status pairs and split:p-format pairs
    args.ly_st = colon_pairs_to_tuples(args.ly_st, default='gsb')
    args.sp_pt = colon_pairs_to_tuples(args.sp_pt, default=None)
    # check that all requested layers are valid
    valid_layers = "tok sym sem cat sns rol".split()
    invalid_layers = [ ly for ly in next(iter(zip(*args.ly_st))) if ly not in valid_layers ]
    if invalid_layers:
        raise ValueError("The layers {} are not valid".format(invalid_layers))
    return args

####################
def colon_pairs_to_tuples(colon_pairs, default='gsb'):
    '''Convert a list with a colon pairs into a list of tuples'''
    tuples = []
    for cp in [ c_p.split(':', 1) for c_p in colon_pairs ]:
        if len(cp) == 2:
            tuples.append(tuple(cp))
        elif len(cp) == 1:
            if default:
                tuples.append((cp[0], default))
            else:
                raise ValueError("Specify values after layers/splits!")
        else:
            raise ValueError("Use (:) to delimit layers/splits from statuses/patterns!")
    return tuples

###############################################################################
################### Get doc numbers and their statuses ########################
def get_filtered_splits(lang, split_patterns, status_constraints, status_json):
    '''Get the splits where each consists of docs with annotation layer statuses
       satisfying status constraints: {split:{doc_path:{layer:status}}}.
       The annotation statuses are read from status files or from a json file.
    '''
    # Read {doc_pd:{lang:{layer:status}}} from a json file
    with open(status_json) as jsonfile:
        doc_lang_ly_status = json.load(jsonfile)
    info("Annotation statuses of all translations were loaded")
    # filter the translations based on the language, split parts and statuses
    splits = defaultdict(dict)
    info("Filtering {} translations with part and status constraints".format(lang.upper()))
    for pd, lang_ly_status in doc_lang_ly_status.items():
        split = detect_split(pd, split_patterns)
        if not split:
            continue # document number deosn't fall in any split
        if lang in lang_ly_status\
           and meets_status_constraints(lang_ly_status[lang], status_constraints):
            splits[split][pd] = lang_ly_status[lang]
    info("Done. {} translations were retrieved".format(\
        sum([ len(splits[s]) for s in splits ])))
    return splits

####################
def detect_split(doc_path, split_patterns):
    '''Return the (first) split the pattern of which the part/doc matches
    '''
    for split, pat in split_patterns:
        if re.search("p{}/d".format(pat), doc_path):
            return split

####################
def meets_status_constraints(ly_st, status_constraints):
    '''Verify if the statuses of the layers meet the status constraints
    '''
    for layer, statuses in status_constraints:
        # the first letter of status is used instead of the entire status
        if ly_st[layer][0] not in statuses:
            return False
    return True

####################
def read_annotation_statuses(data_dir, langs=['en','nl','de','it'], save=None):
    '''Read annotation statuses of all docs and optionally save them a json file
    '''
    doc_lang_ly_status = defaultdict(dict)
    info("Reading annotation status files for {} translations".format(langs))
    for i, (path, dirs, files) in enumerate(os.walk(data_dir), start=1):
        if i % 1000 == 0: debug("{} paths scanned".format(i))
        if dirs: continue # document directories have no directories inside
        for lang in langs:
            status_file_path = op.join(path, lang + ".status")
            if not op.isfile(status_file_path): continue # status file doesn't exist
            with open(status_file_path) as f:
                status_dict = dict(l.rstrip().split() for l in f)
            pd = re.search('p\d{2}/d\d{4}', path).group(0)
            doc_lang_ly_status[pd][lang] = status_dict
    info("Done. Statuses of {} translations (as {} docs) were recorded".format(\
        sum([ len(trans) for (pd, trans) in doc_lang_ly_status.items() ]),
        len(doc_lang_ly_status)))
    if save:
        if op.isfile(save): warning(save + " will be overwritten")
        with open(save, 'w') as jsonfile:
            json.dump(doc_lang_ly_status, jsonfile, indent=2)
        info("The status data was saved in " + save)
    return doc_lang_ly_status

###############################################################################
######################## Read & write an annotated doc ########################
def write_doc(file_stream, data_dir, lang, doc_id, xml_layers, ly_st):
    '''Write annotated document in the given stream. The order of layer annotations
       follows the input order of layers. It also reads a raw text to extract sentences
    '''
    # verify if all files containing annotations are there
    ext_list = ['drs.xml', 'raw', 'parse.tags'] if 'cat' in xml_layers else ['drs.xml', 'raw']
    dirs = next(os.walk(op.join(data_dir, lang)))[1] # directories under data/
    drs_raw_parse_paths = guess_doc_path(data_dir, dirs, doc_id, lang, ext_list)
    if len(drs_raw_parse_paths) != len(ext_list):
        warning("{} from {} not found. Skipping {}".format(\
        len(ext_list) - len(drs_raw_parse_paths), ext_list, doc_id))
        return False
    # write doc_id and layer annotation statuses as comments
    file_stream.write("# newdoc id = {}\n".format(doc_id))
    ly_st_comment = '\t'.join([ "{}:{}".format(l,s) for (l, s) in ly_st ])
    file_stream.write("# layer:statuses =\n# {}\n".format(ly_st_comment))
    # get CCG categories if requested
    cats = read_categories(drs_raw_parse_paths[2]) if 'cat' in xml_layers else None
    # get most of the annotations from drs.xml
    annot_doc, start_offs = read_annotations_from_drsxml(drs_raw_parse_paths[0], xml_layers,\
                                                         cats=copy.deepcopy(cats))
    # sanity check that we retrieved correct number of annotated tokens
    tokens = [ t for s in annot_doc for t in s ]
    if cats is not None and len(cats) != len(tokens):
        warning("More categories ({}) than annotated tokens ({}). Skipping {} for {}".format(\
            len(cats), len(tokens), lang, op.dirname(drs_raw_parse_paths[0])))
        return False
    # get raw sentences
    raw_doc = raw_sentences(drs_raw_parse_paths[1], start_offs)
    if len(annot_doc) != len(raw_doc): # sanity check
        warning("The numbers of raw ({}) and annotated ({}) sentences "
                "differ. Skipping {}".format(len(raw_doc), len(annot_doc), doc_id))
        return False
    for raw_sen, annot_sen in zip(raw_doc, annot_doc):
        file_stream.write("# raw sent = {}\n".format(raw_sen.replace('\n', ' ').rstrip()))
        # write a sentence with all token-level annotations per line
        file_stream.write('\n'.join('\t'.join(tok) for tok in annot_sen) + '\n\n')
    return True

####################
def guess_doc_path(data_dir, dirs, doc_id, lang, ext_list):
    '''Guess whether the document is in gold, silver or brionze directory of data
    '''
    paths = []
    for ext in ext_list:
        for d in dirs: # loop over all child directories of data/
            path = op.join(data_dir, lang, d, doc_id, '{}.{}'.format(lang, ext))
            if op.isfile(path):
                paths.append(path)
                break
    return paths

#################### 99/2288 #22/2223 #00/3131
def read_annotations_from_drsxml(path, layers, cats=None):
    '''Read drs.xml and return doc[ sen[ tok[ annotation ] ] ].
       Additionally return character offsets for sentence-initial tokens.
       NB: It uses layer names that are found in drs.xml
    '''
    doc, sen, senid0, sen_start_offs = [], [], None, []
    xml_id = '{http://www.w3.org/XML/1998/namespace}id'
    # sanning annotated tokens one-by-one
    for tagtoken in ET.parse(path).getroot().iter('tagtoken'):
        #sentence_start = True if (tokid == '1' and not sentence_start) else False
        # if sentence id chnaged and previous sentence is non-empty,
        # add the sentence to docs and start constructiung a new sentence
        empty_element, tok_annot, sen_from = False, {}, None
        # read token annotations for specified layers, ignore empty tokens
        for tag in tagtoken.iter('tag'):
            #if tag.attrib['type'] == 'to' and tag.text == '-1':
            if tag.attrib['type'] == 'tok' and tag.text == 'ø':
                empty_element = True
                break # skip further scanning an empty token
            if tag.attrib['type'] in layers:
                # If layers have repetitions, this will still yield each layer once
                # Check if tag contains space and raise warning if it does
                # Replace space by ~
                add_tag = tag.text
                if len(add_tag.split()) > 1:
                    add_tag = "~".join(add_tag.split())
                    warning("Tag contains space: {0}, replace space with '~'".format(tag.text))
                tok_annot[tag.attrib['type']] = add_tag
            if tag.attrib['type'] == 'from':
                sen_from = int(tag.text)
        if empty_element: continue
        # A token is not empty and all its layers are read
        if cats: tok_annot['cat'] = cats.pop(0)
        # check if this non-empty token is a sentence-initial
        senid1, _ = re.split('0+', tagtoken.attrib[xml_id][1:], maxsplit=1)
        if senid1 != senid0:
            sen_start_offs.append(sen_from)
            if sen:
                doc.append(sen)
                sen = []
        sen.append([ tok_annot[ly] for ly in layers ])
        senid0 = senid1
    if sen: doc.append(sen) # add the last sentence if it is not empty
    return doc, sen_start_offs

####################
def raw_sentences(raw_file, start_offs):
    '''Using the sentence start offsets, read raw sentences from the raw doc'''
    with open(raw_file) as f:
        raw = f.read()
    return [ raw[start1:start2] for start1, start2 in zip(start_offs, start_offs[1:]+[None]) ]

####################
def read_categories(file_path): # NOTE later categories will be in drs.xml
    '''Read CCG categories from parse.tags, and return as a list.
    '''
    cats = []
    with open(file_path) as parse:
        for line in parse:
            m = re.match('\s+t\((.+?), ', line)
            if m:
                cats.append(m.group(1))
    return cats

###############################################################################
################################ Main function ################################
if __name__ == '__main__':
    # get arguments
    args = parse_arguments()
    # file paths for splits
    sp_paths = { sp_file:op.join(args.split_dir, sp_file) for sp_file in next(iter(zip(*args.sp_pt))) }
    if not op.exists(args.split_dir):
        os.makedirs(args.split_dir)
    # Warn if the split files will overwite any other file
    for path in sp_paths.values():
        while op.isfile(path):
            sys.stdout.write("WARNING: Overwrite the file {}? [yes/TERMINATE]: ".format(path))
            answer = input()
            if answer == '':
                info('The script terminated')
                sys.exit()
            if answer == 'yes': break
    # get docs that satisfy the requested criteria
    # collect annotation statuses if not collected already (takes >1h)
    if not op.isfile(args.status_json):
        if args.status_json:
            warning("Status file {} doesn't exists and it will be created".format(args.status_json))
        read_annotation_statuses(args.data_dir, save=args.status_json)
    splits = get_filtered_splits(args.lang, args.sp_pt, args.ly_st, args.status_json)
    layers = ('tok',) + next(iter(zip(*args.ly_st)))
    three_char2xml = {'rol':'verbnet', 'sns':'wordnet'}
    xml_layers = [ three_char2xml.get(ly, ly) for ly in layers ]
    written, previous, ignored = 0, 0, 0
    for sp, doc_ly_st in splits.items():
        with open(sp_paths[sp], 'w') as f:
            f.write("### Generated by the command:\n### {}\n".format(' '.join(sys.argv)))
            for doc_id in sorted(doc_ly_st):
                #if doc_id not in ['p93/d1734']: continue # has to=-2 p02/d1394
                debug(doc_id)
                if write_doc(f, args.data_dir, args.lang, doc_id, xml_layers,
                            [ (ly, doc_ly_st[doc_id][ly]) for ly in layers ]):
                    written += 1
                else:
                    ignored += 1
            if written % 1000 == 0: debug("{} docs are written".format(written))
        info("{} docs have been written in {}".format(written - previous, sp_paths[sp]))
        previous = written
    info("In total {} docs were written and {} ignored".format(written, ignored))
