#!/usr/bin/env python
# -*- coding: utf8 -*-

'''
The CoNLL extraction script only extracts based on 6-layers. Also, it doesn't keep the order in for example the
official PMB dev and test files. This script takes a CoNLL file, and only retains DRSs that are present in
a different DRS file (or simply a list of documents). It also orders them based on this set.
'''

import argparse
import re
from run_boxer import get_conll_blocks, merge_by_document
from uts import get_drss, write_list_of_lists_of_lists


def create_arg_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", '--conll_file', required=True, type=str, help="Input file in CONLL format (from extract_conll.py)")
    parser.add_argument("-d", '--drs_file', required=True, type=str, help="DRS file based on which we keep DRSs")
    parser.add_argument("-o", '--output_file', required=True, type=str, help="Output file where we save the DRSs")
    args = parser.parse_args()
    return args


def get_part_doc_list_of_lists(in_file):
    '''Extract part/doc_id for line in file'''
    docs = []
    for line in open(in_file, 'r'):
        pos_doc = re.findall(r'p[\d][\d]/d[\d][\d][\d][\d]', line)
        if pos_doc:
            docs.append(pos_doc[0])
    return docs


def order_and_filter(conll_blocks, docs_conll, docs_drss):
    '''Do the ordering and filtering here: keep CoNLL blocks based on if
       they are present in the DRSs. Also, keep order of DRSs'''
    final_blocks = []
    for ident in docs_drss:
        if ident in docs_conll:
            # Found doc present in conll, save
            final_blocks.append(conll_blocks[docs_conll.index(ident)])
        else:
            print("Could not find {0} -- skip".format(ident))
    return final_blocks


if __name__ == "__main__":
    args = create_arg_parser()

    # First get the data in the correct format
    conll_blocks_tmp, doc_ids = get_conll_blocks(args.conll_file, split_lines=False, add_doc=True)
    conll_blocks = merge_by_document(conll_blocks_tmp, doc_ids)
    drss = get_drss(args.drs_file)

    # Extract the doc_ids as well
    docs_conll = get_part_doc_list_of_lists(args.conll_file)
    docs_drss = get_part_doc_list_of_lists(args.drs_file)

    # Now do the ordering: keep CoNLL blocks based on the DRSs
    output_blocks = order_and_filter(conll_blocks, docs_conll, docs_drss)
    write_list_of_lists_of_lists(output_blocks, args.output_file)
