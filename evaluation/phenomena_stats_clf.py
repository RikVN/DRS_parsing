#!/usr/bin/env python
# -*- coding: utf8 -*-

'''
Gets statistics of certain syntax/semantics phenomena based on CLFs 
contact: Lasha.Abzianidze@gmail.com 
'''
# Usage
# Get counts of modals and negation: python phenomena_stats_clf.py  FILE.CLF  -o NOT POS NEC
# Get counts of scope ambiguity: python phenomena_stats_clf.py FILE.CLF  -s NOT POS NEC IMP -v 1 
# Get counts of discourse rel & implication: python phenomena_stats_clf.py FILE.CLF  -o IMP REL
# Get counts of embedded clauses: python phenomena_stats_clf.py FILE.CLF  -o PRP 
#                    and control: python phenomena_stats_clf.py FILE.CLF  -c
# Get counts of pronoun resolution: python phenomena_stats_clf.py FILE.CLF  -p 

from __future__ import unicode_literals
from contrast_clfs import file_to_clf_dict, get_anaphoric_pronouns
#import codecs
import argparse
#import re
import sys
#import pmb
#import utils
from collections import Counter

#################################
############ Arguments ##########
def parse_arguments():
    parser = argparse.ArgumentParser(description='get statistics of phenomena in CLFs')
    parser.add_argument(
    'clfs', metavar='FILE', 
        help='File containing CLFs')
    parser.add_argument(
    '-o', '--operators', nargs='+', default = [], metavar='LIST', 
        help='Operators which will be counted in CLFs')
    parser.add_argument(
    '-s', '--scope', nargs='+', default = [], metavar='LIST', 
        help='list of operators whose scope interactions we are interested in.')
    parser.add_argument(
    '-p', '--pro-res', action='store_true',
        help='Match CLFs with a pronoun resolution phenomenon')
    parser.add_argument(
    '-c', '--control', action='store_true',
        help='Counts control verbs')
    parser.add_argument('-v', '--verbose', dest='v', default=0, type=int, metavar='N', 
        help='verbosity level of reporting')
    args = parser.parse_args()
    return args  


#################################
def count_operators(raw_clfs, ops, v=0):
    '''Count operators in CLFs. REL stands for discourse relations'''
    count = Counter()
    for (i, (raw, clf)) in enumerate(raw_clfs):
        for cl in clf:
            op = cl[1]  
            # if it is a relevnat operator
            # discourse relations are identified based on the string properties  
            if (op in ops) or\
               ('REL' in ops and op.isupper() and len(op) > 3):
                count.update([op]) 
                if v>=1: print i, op, raw   
    return count
    
#################################
def count_scoping(raw_clfs, ops, v=0):
    '''Count scoping of the specified operators. 
       A sequence of N-nested operators (e.g. POS>NOT>POS) is counted N-1 times,
       i.e., only pairs of **directly** scoping operators
       NB: this procedure doesn't count exact number but good approximaton of scopings 
    '''
    count = Counter()
    # get signature of relevant operators
    all_arity = get_op_arity()
    op_arity = { op: all_arity[op] for op in all_arity if op in ops }
    for (i, (raw, clf)) in enumerate(raw_clfs):
        for cl in clf:
            # if it is the operator get signature, otherwise a dummy signature     
            (arity, box_pos) = op_arity.get(cl[1], (0, []))
            # ignore uninteresting cases
            if arity == 0: continue
            # get box variabes
            box_vars = [ cl[j] for j in box_pos ]
            # find directly scoped operators
            scoped = [ (cl[1], c[1]) for c in clf if c[1] in ops and c[0] in box_vars ]
            count.update(scoped)
            if v>=1 and scoped: 
                print i, scoped, raw 
    return count 

#################################
def count_control(raw_clfs, v=0):
    '''Count control verb phenomenon. The following cases are counted:
       PRP has only untensed events inside, there is an intersection between 
       the participants of these events and the participants of the events which introduces PRP.
       In this way, anaphoras and embeded clauses are avoided as the clause is tensed in the latter.
       Also, if by mistake, embeded clause is not tensed, sharing no participants ignores such cases.   
       NB: this procedure doesn't count exact number but good approximaton of control  
    '''
    count = Counter()
    for (i, (raw, clf)) in enumerate(raw_clfs):
        if not next((c for c in clf if c[1] == 'PRP'), False): continue # ignore clfs without PRP 
        tensed_e = [ c[2] for c in clf if c[1] == 'Time'] # get all tensed events
        for cl in clf:
            if cl[1] != 'PRP': continue # ignore non-PRP clauses
            (b0, _, p, b1) = cl
            # get all tensed events in PRP    
            tensed_prp_e = [ c[3] for c in clf if 
                               is_concept(c, 's') and c[0] == b1 and c[3] in tensed_e ]
            if tensed_prp_e: continue # if e in PRP is tensed this is not control
            # get non-tensed event predicates in PRP
            non_tensed_prp_e = [ c[1] for c in clf if 
                                   is_concept(c, 's') and c[0] == b1 and c[3] not in tensed_e ]
            if not non_tensed_prp_e: continue # ignore if there is no non-tensed e in PRP
            # get inner participants: those in the PRP box (excl. time) 
            inner = [ c[3] for c in clf if 
                        c[0] == b1 and is_role(c, ['Time']) ]
            # ignore cases when PRP has only PRP inside e.g., 26/2437
            if not inner: continue
            # get event variable(s) where prp participates
            e_prp = [ c[2] for c in clf if 
                        is_role(c, ['Time']) and c[3] == p ]
            # e_prp is not singleton for 26/2481  
            # ignore cases when PRP has no corresponding event e.g., 26/2437
            if not e_prp: continue
            # get participants of the event(s) where PRP participates (excl. time)
            outter = [ c[3] for c in clf if 
                         is_role(c, ['Time']) and c[2] in e_prp and c[3] != p  ]
            # keep those inner participants that are outter participants too
            shared = [ r for r in inner if r in outter ]
            # if inner and outter participants are not shared, it is not control
            if not shared: continue
            # 
            # for nice printing get nouns denoting the shared participants
            shared = next(( c[1] for c in clf if 
                              is_concept(c) and c[3] in shared ), 'Deictic') 
            count.update(non_tensed_prp_e)
            if v>=1 and non_tensed_prp_e: 
                print i, non_tensed_prp_e, shared, ':', raw 
    return count    

    
    
#################################
def count_pro_res(raw_clfs, v=0):
    '''Count CLFs with pronoun resolution phenomenon.
       The counting is not exact as the exact procedure is too complex.
       A CLF contaisn a pronoun resolution if: it contains pronouns whose
       referents occure more than once as participants of tensed events.  
    '''    
    pros = get_anaphoric_pronouns(out='dict')
    pro_con = {'he': 'male', 
               'she': 'female', 
               'it': 'entity',
               'they': 'person'}
    count = Counter()
    for (i, (raw, clf)) in enumerate(raw_clfs):
        words = raw.lower().split()
        # nominal prepresentation of pronouns that occur in the raw text
        pro_res = [ p for p in pros if not set(words).isdisjoint(pros[p]) ]
        # ignore the clf if no pronouns found there       
        if not pro_res: continue 
        cons = [ pro_con[p] for p in pro_res ] # concepts of occurred pronouns
        # discourse referents of the pronouns 
        refs = [ c[3] for c in clf if is_concept(c, 'i') and c[1] in cons ]
        # keep those referents that ocurr with more than one semantic relations
        # FIXME 10/2497 shoudl be counted 2 times as it has two possessive pronouns
        res_refs = [ r for r in refs 
                       if len([ c for c in clf 
                                  if is_role(c, ['Time']) and c[3] == r ]) >= 2 ]
        # get non-tensed event referents. If event is under NEC or POS is considered as tensed
        non_tensed_s = [ cl[3] for cl in clf
                           if is_concept(cl, 's') and 
                              not ( [ c for c in clf if c[1] == 'Time' and c[2] == cl[3] ] or 
                                    [ l for l in clf if len(l) == 3 and l[2] == cl[0] and l[1] in ['NEC', 'POS'] ] 
                                  ) 
                       ]     
        # discard referents that are participant of non-tensed events (this excludes control)   
        res_refs2 = [ r for r in res_refs 
                       if not [ c for c in clf 
                                  if is_role(c) and c[3] == r and c[2] in non_tensed_s ] ]    
        count.update(res_refs2)
        if v >= 1 and res_refs2:
            concepts = [ c[1] for c in clf if is_concept(c, 'i') and c[3] in res_refs2 ]
            print i, res_refs2, concepts, raw  
    return count

#################################
def get_op_arity():
    '''Get arity and box variable positions for the operators'''
    op_arity = {'NOT': (1, [2]), 
                'POS': (1, [2]), 
                'NEC': (1, [2]),
                'IMP': (2, [2,3]),
                'DIS': (2, [2,3]),
                'DUP': (2, [2,3]),
                'PRP': (2, [3])
               }        
    return op_arity  
    
#################################    
def is_role(cl, excl=[]):
    '''Check if the clause is a semantic role (with some exclusions)
    '''
    # cl[1].istitle() doesn't cover PartOf
    return len(cl) == 4 and cl[1][0].isupper() and cl[1][1].islower() and cl[1] not in excl

#################################
def is_concept(cl, kind=''):
    '''Check if the clause is a concept caluse (with optional kind)
    '''
    mapping = {'s' : ['v', 's', 'a', 'r'],
               'i' : ['n'] }
    if len(cl) != 4:
        return False
    kind_cond = (cl[2][1] in mapping[kind]) if kind else True  
    return cl[1] == cl[1].lower() and kind_cond and len(cl[2]) == 6 # length of "n.02"               

      
#################################
############ MAIN ###############
#################################

if __name__ == '__main__':
    args = parse_arguments()
    print '%%% Generated by the command: ' + ' '.join(sys.argv)
    # get CLFs from the file
    clf_dict = file_to_clf_dict(args.clfs, v=args.v) 
    total_clfs = len(clf_dict)
    print "{} clfs retrieved".format(total_clfs)
    # counting operators
    if args.operators:
        counts = count_operators(clf_dict.values(), args.operators, v=args.v)
    # count direct scoping of specific operators
    if args.scope:
        counts = count_scoping(clf_dict.values(), args.scope, v=args.v)
    # count control cases 
    if args.pro_res:
        counts = count_pro_res(clf_dict.values(), v=args.v)
    # count pronoun resolution cases 
    if args.control:
        counts = count_control(clf_dict.values(), v=args.v)        
    # print counting details
    print "Frequency list of counted items (total is {}):".format(sum(counts.values()))
    for (item, count) in counts.most_common():
        print "{:>10}\t{:<10}".format(count, item)    
    


