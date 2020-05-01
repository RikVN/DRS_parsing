#!/usr/bin/env python
# -*- coding: utf8 -*-

'''
Script that takes an input file in CoNLL format with information about the 6 PMB layers:
tok sym sem cat sns rol and then applies Boxer for each individual one.
The created DRSs are saved and written to the file final_drss.txt

Usage:

python run_boxer.py -c $CONLL_FILE -o $OUTPUT_FOLDER -b $BOXER -e $EASYCCG -em $CCG_MODEL
'''

import argparse
import os
import re
import subprocess
import logging
from logging import debug, info, warning, error
from utils_counter import write_to_file, write_list_of_lists, dummy_drs


def create_arg_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", '--conll_file', required=True, type=str, help="Input file in CONLL format")
    parser.add_argument("-o", '--output_folder', required=True, type=str, help="Folder in which we write (temp) files as input for Boxer")
    parser.add_argument("-b", '--boxer', default="parsing/boxer_3.0.0", type=str, help="Location of Boxer")
    # Arguments for parsing
    parser.add_argument("-e", '--easyccg', default="easyccg/easyccg.jar", type=str, help="Location of easyCCG jar file")
    parser.add_argument("-em", '--easyccg_model', default="easyccg/model", type=str, help="Location of easyCCG model")
    args = parser.parse_args()
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
    # Create output dir if not exists
    if not os.path.exists(args.output_folder):
        os.makedirs(args.output_folder)
        info("Creating {0} because it doesn't exist yet".format(args.output_folder))
    return args


def repl_atomic_category(match):
    return match.group(0).upper()


def convert_cat(cat):
    '''Convert category to the input format the parser expects'''
    ATOMIC_CATEGORY_PATTERN = re.compile(r'(?<=[\\(/ ])[a-z]+')
    FEATURE_OR_VARIABLE_PATTERN = re.compile(r':([a-z]+|[A-Z])')
    # Upper-case atomic parts of basic categories:
    cat = re.sub(ATOMIC_CATEGORY_PATTERN, repl_atomic_category, ' ' + cat)[1:]
    # Use [] instead of : for features and variables:
    cat = re.sub(FEATURE_OR_VARIABLE_PATTERN, r'[\1]', cat)
    # conj should still be lowercase
    cat = cat.replace('CONJ', 'conj')
    return cat


def get_conll_blocks(in_file, split_lines=True, add_doc=False):
    '''Read a CoNLL formatted input file and return the list of lists per sentence/document'''
    docs = []
    cur_doc = []
    doc_ids = []
    num_lines = -1
    for line in open(in_file, 'r'):
        if not line.strip() and cur_doc:
            docs.append(cur_doc)
            cur_doc = []
            doc_ids.append(num_lines)
        elif line.strip().startswith('# newdoc'):
            # Keep track of start of new documents in doc_ids
            # We form a list of all sentences in docs, but at some
            # point we have to put multi-sent docs in a single file
            num_lines += 1
            if add_doc:
                cur_doc.append(line.strip())
        elif not line.strip().startswith('#') and line.strip():
            if len(line.split()) != 6:
                raise ValueError("Line should always consist of 6 layer-values, found {0}\n{1}".format(len(line.split()), line.strip()))
            if split_lines:
                cur_doc.append(line.split())
            else:
                cur_doc.append(line.strip())
    # Add left over one if there's not an ending last line
    if cur_doc:
        docs.append(cur_doc)
        doc_ids.append(num_lines)
    # If num_lines is never increased, this means that the # newdoc information was not added
    # In that case we just assume the default of 1 doc per block
    if num_lines == -1:
        info("Assuming 1 document per CoNLL block")
        doc_ids = range(0, len(docs))
    info("Extracted {0} sents, for {1} docs".format(len(docs), doc_ids[-1] + 1))
    return docs, doc_ids


def read_blocks(lines):
    '''Read blocks of lines separated by whitelines'''
    blocks = []
    cur_block = []
    for line in lines:
        if not line.strip() and cur_block:
            blocks.append(cur_block)
            cur_block = []
        elif line.strip():
            cur_block.append(line.rstrip())
    if cur_block:
        blocks.append(cur_block)
    return blocks


def parse_block(block, output_folder, easyccg, easyccg_model, num):
    '''Parse an input CoNLL block, error is parse failed'''
    p_input = prepare_parse_format(block, use_tags=False)
    p_output = parse_sentences(p_input, output_folder, easyccg, easyccg_model, tmp="{0}".format(num))
    # Rewrite the output to the block format again
    block_parse = strip_ccg(p_output)
    if ccg_succeeded(block_parse):
        warning("Parse {0} succeeded without supertag constraints".format(num))
        return block_parse
    raise ValueError("Parse {0} still failed without supertag constraints, no workaround currently, error".format(num))


def retry_failed_parses(parses, conll_blocks):
    '''Parses sometimes fail, if so, try again without the supertag constraints'''
    new_parses = []
    prev_id = 0
    for parse in parses:
        cur_id = int(re.findall(r'[\d]+', parse[0])[0])
        # Check if we skipped one, if so try again
        if cur_id != prev_id + 1:
            # Do in a forloop if we skipped more in a row
            for num in range(prev_id, cur_id - 1):
                warning("Parse {0} failed, try again without supertag constraints".format(num))
                new_parses.append(parse_block([conll_blocks[num]], args.output_folder, args.easyccg, args.easyccg_model, num))
        # Always add the current parse
        new_parses.append(parse)
        prev_id = cur_id
    # It is possible that the last parse(s) failed, so always check if
    # we have enough parses here, and if not, also retry those
    for num in range(len(parses), len(conll_blocks)):
        warning("Parse {0} failed, try again without supertag constraints".format(num))
        new_parses.append(parse_block([conll_blocks[num]], args.output_folder, args.easyccg, args.easyccg_model, num))
    return new_parses


def ccg_succeeded(lines):
    '''Check if CCG parse succeeded for single sentence'''
    return len([x for x in lines if x.startswith('ccg')]) > 0


def strip_ccg(output):
    '''Strip CCG output to only keep what we want'''
    return [x.rstrip() for x in output if not x.strip() or x[0] in [' ', '\t'] or x.startswith('ccg')]


def merge_by_document(parses, doc_ids):
    '''Merge sentences together that belonged to the same document'''
    new_output = []
    for idx, parse in enumerate(parses):
        if idx > len(doc_ids) -1:
            new_output[-1].append(parse)
        elif idx == 0  or doc_ids[idx] != doc_ids[idx-1]:
            new_output.append([parse])
        else:
            new_output[-1].append(parse)
    return new_output


def parse_output_per_doc(output, doc_ids, conll_blocks):
    '''Format parse output to be able to have multiple sents per doc'''
    # Filter filler lines and read the blocks
    lines = strip_ccg(output)
    parses = read_blocks(lines)
    # Parses sometimes fail, if so, try again without the supertag constraints
    # Print a warning if that happens
    parses = retry_failed_parses(parses, conll_blocks)

    # Now add blocks together that belong to the same document
    parses = merge_by_document(parses, doc_ids)
    return parses


def prepare_parse_format(blocks, use_tags=True):
    '''Prepare the input file for the easyCCG parser by appending
       supertag to the tokens'''
    lines = []
    for block in blocks:
        parse_line = []
        for line in block:
            tok = line[0]
            cat = convert_cat(line[3])
            if use_tags:
                parse_line.append("{0}|{1}".format(tok, cat))
            else:
                parse_line.append("{0}|".format(tok, cat))
        lines.append(" ".join(parse_line))
    return lines


def parse_sentences(parse_input, out_fol, easyccg, model, tmp=""):
    '''Parse a list of sentences in the correct parser input'''
    # Set constants for parsing here
    arguments = "--inputFormat constrained -g --unrestrictedRules -l 70 --rootCategories S S[dcl] S[wq] S[q] NP S[b]\\\\NP S[intj] --outputFormat boxer"
    # Write to file so we can take as input
    tmp_infile = out_fol + 'parse_input.txt' + tmp
    tmp_outfile = out_fol + 'parse_output.txt' + tmp
    write_to_file(parse_input, tmp_infile)
    command = "java -jar {0} --model {1} -f {2} {3} > {4}".format(easyccg, model, tmp_infile, arguments, tmp_outfile)
    # Run command
    subprocess.call(command, shell=True)
    # Read in output parse per block
    return [x.rstrip() for x in open(tmp_outfile, 'r')]


def quotes_around_verbnet(rol):
    '''The parse.tags file needs quotes around the verbnet items to work, which is not
       needed in the layer'''
    items = rol[1:-1].split(',')
    fixed_quotes = ["'" + item + "'" for item in items]
    return '[' + ",".join(fixed_quotes) + ']'


def merge_tags_in_line(block, count, tok_length, line):
    '''Merge the tags we have into the parse'''
    tok, sym, sem, cat, sns, rol = block[count]
    # Escape single quotes in lemma
    sym = sym.replace("'", "\\'")
    # Also add the "from" and "to" information for aligned output
    from_of = tok_length + count
    to_of = tok_length + count + len(tok)
    tok_length += len(tok)
    add_line = "[from:{0}, to:{1}, lemma:'{2}', sem:'{3}', wordnet:'{4}' ".format(from_of, to_of, sym, sem, sns)
    # Verbnet can be empty and then we do not add it
    if rol != '[]':
        add_line += ", verbnet:{0}".format(quotes_around_verbnet(rol))
    add_line += ']'
    # Bit hacky, but we replace the previous stuff between brackets (lemma)
    # with our own version we just created
    final_line = re.sub(r'\[.*\]', add_line, line)
    return final_line


def merge_parse_and_tags(blocks, parses):
    '''Merge the parse and tags of a document to create the input file for Boxer'''
    # Initialize out_lines with the prelude
    out_lines = [":- op(601, xfx, (/)).", ":- op(601, xfx, (\)).", ":- multifile ccg/2, id/2.", ":- discontiguous ccg/2, id/2.", '']
    # Add the tags to the parse, to create a .parse.tags file that Boxer will read
    for block, parse in zip(blocks, parses):
        count = 0
        tok_length = 0
        for line in parse:
            # Add information for each token item in parse
            if line.strip().startswith('t('):
                final_line = merge_tags_in_line(block, count, tok_length, line)
                # Add the line to all out_lines
                out_lines.append(final_line)
                count += 1
            else:
                out_lines.append(line)
        out_lines.append('')
    return out_lines


def make_dir_if_not_exists(cur_dir):
    '''Create directory if it doesn't exist yet'''
    if not os.path.exists(cur_dir):
        os.makedirs(cur_dir)


def do_boxing(boxer, cur_dir):
    '''Run boxer given an input file with the parse + tags'''
    out_file = "{0}drs.clf".format(cur_dir)
    boxer_arguments = "--semantics drg --resolve --tense --instantiate --modal --theory sdrt \
                       --copula false --nn --elimeq --roles verbnet --integrate --warnings false"
    command = "{0} --input {1} {2} --output {3} 2> {3}.log".format(boxer, cur_dir + 'parse.tags', boxer_arguments, out_file)
    subprocess.call(command, shell=True)
    return out_file


def read_and_check_drs(drs_file, idx):
    '''Read in and return the DRS, return a dummy if parsing failed for some reason'''
    if os.path.isfile(drs_file):
        drs = [x.strip() for x in open(drs_file, 'r')]
        # Check if DRS contains content lines
        # Sometimes Boxer produces an empty DRS and does not error
        if len([x for x in drs if not x.startswith('%')]) > 0:
            return drs
        else:
            warning("Empty DRS produced for idx {0}, add dummy DRS".format(idx))
            return drs + ["%%% Adding dummy DRS because parsing failed"] + [" ".join(x) for x in dummy_drs()]
    else:
        warning("No DRS produced for idx {0}, add dummy DRS".format(idx))
        return ["%%% Adding dummy DRS because parsing failed"] + [" ".join(x) for x in dummy_drs()]


def boxer_list(conll_blocks, parse_output, boxer, out_fol):
    '''Run Boxer for each block in conll_blocks individually, keep track of
       all produced DRSs as well and check if they are well-formed'''
    drss = []
    for idx, (blocks, parses) in enumerate(zip(conll_blocks, parse_output)):
        out_lines = merge_parse_and_tags(blocks, parses)

        # Write these lines to a temporary file, in a tmp_dir that we create specially for this document
        cur_dir = out_fol + 'idv/d' + str(idx) + '/'
        make_dir_if_not_exists(cur_dir)
        write_to_file(out_lines, cur_dir + 'parse.tags')

        # Then, finally, we can run Boxer on this input file and save the DRS file
        out_file = do_boxing(boxer, cur_dir)

        # Might as well already read and save the produced DRS, also check if valid
        drss.append(read_and_check_drs(out_file, idx))
    return drss


if __name__ == "__main__":
    args = create_arg_parser()

    # First get the data in the correct format
    conll_blocks, doc_ids = get_conll_blocks(args.conll_file)

    # We only have the supertags, so we still have to do the parsing
    # It's not very efficient to dat on sentence level, so we run the
    # parser on a single file and keep using that for efficiency
    parse_input = prepare_parse_format(conll_blocks)
    parse_output = parse_sentences(parse_input, args.output_folder, args.easyccg, args.easyccg_model)

    # Read in parse output, each item of the list is a list of sentences (usually length 1)
    # but can be larger for multi-sent documents
    parse_output = parse_output_per_doc(parse_output, doc_ids, conll_blocks)
    # Also merge the conll blocks by document
    merged_conll = merge_by_document(conll_blocks, doc_ids)

    # With this information we can run Boxer, though we have to make
    # sure that all data is in the right format. Also, Boxer works on
    # document level, so we will create lots of new small files
    drss = boxer_list(merged_conll, parse_output, args.boxer, args.output_folder)
    # Write the final DRSs to output-file
    write_list_of_lists(drss, args.output_folder + "final_drss.txt")
