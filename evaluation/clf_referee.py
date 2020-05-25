#!/usr/bin/env python
# -*- coding: utf8 -*-

'''
Validate sets of DRS clauses
# example how to run:
# python src/python/clf_referee.py  /net/gsb/pmb/exp_data/DRS_parsing/train_cv_output.txt -v 1
# python src/python/clf_referee.py  out/p41/d1786/en.drs.clf -s src/resources/clf_signature.yaml  -v 5
'''

from __future__ import unicode_literals
import os
import sys
import codecs
import argparse
import re
import yaml
from collections import Counter


#################################
def parse_arguments():
    parser = argparse.ArgumentParser(description='Validate sets of caluses in the file')
    parser.add_argument(
    'src', metavar='PATH',
        help='File containing sets of caluses')
    parser.add_argument(
    '-v', '--verbose', dest='v', default=0, type=int,
        metavar='N', help='verbosity level of reporting')
    parser.add_argument(
    '-q', '--quiet', action='store_true',
        help='Do not report the found mistakes by throwing an error')
    parser.add_argument(
    '-s', '--sig', dest='sig_file', default = '',
        help='If added, this contains a file with all allowed roles\
              otherwise a simple signature is used that\
              mainly recognizes operators based on their formatting')
    args = parser.parse_args()
    return args


#################################
def check_clf(clf, signature, v=0):
    '''checks well-formedness of a clausal form
       It returns fine-grained information about the CLF and its DRS:
       * main_box subordinates all the boxes, i.e. all boxes are accessible for it
       * box_dict is a dictionary of {box_label:box_object}
       * direct_sub is subordinate relation derived from box nesting, immediate subordination
       * sub_rel is a subordinate relation over boxes: direct_sub + covert subordinate relations
       * op_types is a list of types of the clauses in CLF
    '''
    # get argument typing and for each clause an operator type
    (op_types, arg_typing) = clf_typing(clf, signature, v=v)
    # make all terms, i.e., of unresolved term types, variables (strict mode)
    for term, type in arg_typing.items():
        if type == 't': arg_typing[term] = 'x'
    # get dictionary of box objects. presupp_rel is a subset of disc_rel
    (box_dict, disc_rels, presupp_rels) = clf_to_box_dict(clf, op_types, arg_typing, v=v)
    if v>=2: print("#boxes = {}".format(len(box_dict)))
    if v>=3:
        for b in box_dict:
            pr_box(box_dict[b])
    # assumption on discourse relations
    disc_sub_rel = set([ (a, b) for (_, a, b) in disc_rels ])
    # get transitive closure of subordinate relation (as set)
    # also checks whether there is a loop in terms of element reflexivity
    (sub_rel, direct_sub) = box_dict_to_subordinate_rel(box_dict, presupp_rels, disc_sub_rel, v=v)
    if v>=2: print("subordinate relation: {}".format(pr_2rel(sub_rel)))

    # check connectivity of all boxes and discourse boxes: can travel from any box to any box
    connected_boxes(set(box_dict.keys()), sub_rel.copy(), v=v)

    # find is there are unbound referents
    unbound_refs = unbound_referents(box_dict, sub_rel, v=v)
    if unbound_refs:
        raise RuntimeError('Unbound referents || {}'.format(pr_set(unbound_refs)))

    return (box_dict, sub_rel, direct_sub, op_types)

#################################
def clf_typing(clf, signature, v=0):
    '''Checks well-formedness of a clausal form in terms of typing.
       Return a list of clause types (i.e. opearator types)
       and a dictionary of term typing
    '''
    arg_typing = dict()
    op_types = []
    # check each clause individually and get variable types
    for cl in clf:
        (op_type, typing) = clause_typing(cl, signature, v=v)
        op_types.append(op_type)
        if v >= 4: print("{}: {} @ {}".format(pr_clause(cl), op_type, pr_2rel(typing, sep=':')))
        for (arg, t) in typing:
            # make type more specific if possible
            t = specify_arg_type(arg, t, v=v) # 't' might become 'c'
            if arg in arg_typing:
                u = unify_types(arg_typing[arg], t)
                if not u:
                    report_error("Type clash || '{}' is of type '{}' and '{}' in {}".format(
                        arg, arg_typing[arg], t, cl), v=v)
                arg_typing[arg] = u
            else:
                arg_typing[arg] = t
    return (op_types, arg_typing)

#################################
def clause_typing(clause, signature, v=0):
    '''checks well-formedness of a clause (context insensitive)
       and returns its main operator type with the types of variables
    '''
    if len(clause) > 4:
        report_error("Too many elements in a clause || {}".format(clause), v=v)
    operator, arguments = clause[1],  (clause[0],) + clause[2:]
    (op_type, arg_types) = operator_type(operator, arguments, signature, v=v)
    if len(arguments) != len(arg_types):
        report_error("Arity Error || Arg-number should be {} in /{}/".format(len(arg_types), clause), v=v)
    typing = set(zip(arguments, arg_types))
    # check if typing per se is ok
    return (op_type, typing)

#################################
def specify_arg_type(arg, t, v=0):
    '''check if argument and a type are compatible
       and return a type, more specific if possible
       (e.g., "now" will be of type c instead of t)
    '''
    if v >= 4: print("{} {}".format(arg, t))
    # argument is in double quotes or has no quotes
    if (not re.match('"[^"]+"$', arg) and
        not re.match('[^"]+$', arg)): # try without re
        report_error("Syntax error || argument {} is ill-formed".format(arg), v=v)
    # if in double quotes, then is of type t, and if of type c, then id double quotes
    if ((t == 'c' and (arg[0], arg[-1]) != ('"', '"')) or
        ('c' != unify_types(t, 'c') and (arg[0], arg[-1]) == ('"', '"'))):
        report_error("Type clash || {} is of type {}".format(arg, t), v=v)
    if  (arg[0], arg[-1]) == ('"', '"'):
        return 'c' # constant type
    return t

#################################
def unify_types(t1, t2, v=0):
    '''unify two types. If not possible return false'''
    if t1 == t2:
        return t1
    if set([t1, t2]) == set(['t', 'c']):
        return 'c'
    if set([t1, t2]) == set(['t', 'x']):
        return 'x'
    return False

#################################
def operator_type(op, args, sig, v=0):
    '''detect operator kind and types of its arguments'''
    # Wordnet senses
    if re.match('"[avnr]\.\d\d"$', args[1])\
    and re.match("[.'\w]", op, re.U)\
    and re.match("[^_]", op, re.U):
        return ('LEX', 'bct') # b LEX c t
    # when signature is empty use a fallback type-checking
    if not sig:
       return operator_type_default(op, args, v=v)
    # Operator is in the signature
    if op in sig:
        (op_kind, arg_types) = sig[op]
        if op_kind in ['DRS']:
            return (op, arg_types)
        if op_kind in ['DRL', 'PRE']:
            return (op_kind, arg_types)
        return ('ROL', arg_types) # treat all different types of role as of type ROL
    report_error("unknown clause || {} @ {}".format(op, args).encode('UTF-8'), v=v)

#################################
def operator_type_default(op, args, v=0):
    '''detect operator kind and types of its arguments
       based solely on format, without a specified signature
    '''
    # Operator is in the signature
    if op in ['REF']:
        return (op, 'bx')
    if op in ['NOT', 'POS', 'NEC', 'DRS']:
        return (op, 'bb')
    if op in ['IMP', 'DIS', 'DUP']:
        return (op, 'bbb')
    if op in ['PRP']:
        return (op, 'bxb')
    if op in ['PRESUPPOSITION']:
        return ('PRE', 'bb')
    # is a temporal or spatial relation
    if len(op) == 3 and op.isupper():
        return ('ROL', 'btt')
    # is a discourse relation
    if op.isupper():
        return ('DRL', 'bb') # Disc. Relations are outside box
    # is a role
    if op[0:2].istitle(): # includes the roles like "PartOf" too
        return('ROL', 'btt')
    report_error("unknown clause || {} @ {}".format(op, args), v=v)

#################################
#################################
def file_to_clfs(filepath, v=0):
    '''reads a file with raw text and clausal forms inside it and
       returns a list of clausal forms and a list of raws.
       Each clausal form is a list of clauses/tuples.
       An empty line is a separator of clausal forms
    '''
    list_of_clf = []
    list_of_raw = []
    clf = []
    with codecs.open(filepath, 'r', encoding='UTF-8') as f:
        pre_line = '' # saves previous line
        for i, line in enumerate(f):
            # when the line is a comment ignore,
            # but if its previous line contains a raw text, then save it
            if line.startswith("%"):
                # save the last line starting with %%%, it can be a raw text
                if line.startswith("%%%"):
                    pre_line = line
                continue
            if not line.strip(): # clf separator
                if clf: # add only non-empty clf
                    list_of_clf.append(clf)
                    list_of_raw.append(pre_line[3:].strip())
                    assert len(list_of_clf) == len(list_of_raw),\
                        "Number of clfs ({}) and raws ({}) do not match: {} vs {}".format(
                            len(list_of_clf), len(list_of_raw),
                            list_of_raw[-1], pr_clf(list_of_clf[-1]))
                    clf = []
                continue
            # remove % comments if any
            line = line.split(' %', 1)[0].strip()
            if v >= 5: print("/{}/".format(line))
            clause = tuple(line.split(' '))
            if len(clause) > 1: #remove lines that are comments and started with whitespace
                clf.append(clause)
    if clf: # add last clf
        list_of_clf.append(clf)
        list_of_raw.append(pre_line[3:].strip())
    return (list_of_clf, list_of_raw)

#################################
def report_error(message, v=0):
    if v >= 1:
        print(message)
    raise RuntimeError(message)

############## counter as a progress bar #################
def counter_prog(i, v=0):
    '''Displays a counter to show the progress'''
    if v >= 1:
        sys.stdout.write('\r{}:'.format(i))
        sys.stdout.flush()

#################################
def get_signature(sig_file, out='{op:(kind,types)}', v=0):
    '''get particular information related to operators used in clausal forms'''
    # DRS operators and their argumnet types
    # return an empty dictionary for no signature file
    if not sig_file:
        return {}
    # read signature from the yaml file
    if os.path.isfile(sig_file):
        with codecs.open(sig_file, 'r', encoding='UTF-8') as f:
            sig = yaml.load(f)
    else:
        raise ValueError("Specified signature file is not a file")
    # original as it is from the yaml file
    if out == '{types:{kind:op}}':
        return sig
    # operators as keys
    if out == '{op:(kind,types)}':
        return { op: (k, t) for t in sig for k in sig[t] for op in sig[t][k] }
    # simple list of operators
    if out == '[op]':
        return [ op for t in sig for k in sig[t] for op in sig[t][k] ]
    # error for the uncovered mode found
    raise RuntimeError("Unknown parameter || {}".format(out))

#################################
######### OBJECT MODEL ##########

class Box:
    '''a Box (i.e. DRS) object.
       It is called box because the objects are not recursive.
       Inner boxes are represented by box variable names
    '''

    def __init__(self, name):
        self.name = name
        # discourse referents
        self.refs = set()
        # speech act discourse referents
        # self.box_refs = set()
        # set of DRS conditions
        self.conds = set()
        # discourse referents directly mentioned in DRS conditions
        self.cond_refs = set()
        # boxes which this subordinates
        self.subs = set()
        # discourse relations
        # self.rels = set() # discarded as they are floating outside boxes now
        # boxes mentioned in discourse relations
        # self.rel_boxes = set()


#################################
###### Box related functions#####

#################################
def pr_box(box, indent=0):
    '''Print a box object'''
    ind = indent * ' '
    print("{} {}".format(ind, 20 * '_'))
    print("{} {}".format(ind, box.name))
    #discourse referents
    print("{} {} {}".format(ind, '| ', ' '.join(box.refs)))
    #if box.box_refs: print ind, '[[ ', ' '.join(box.box_refs)
    print("{} {}".format(ind, 20 * '-'))
    if box.conds:
        for c in box.conds:
            print("{} {} {}".format(ind, '| ', ' '.join(c)))
    #if box.rels: # relations are floating outside boxes now
    #    for r in box.rels:
    #        print ind, '[ ', ' '.join(r), ' ]'
    if box.cond_refs: print("{} {} {} {}".format(ind, '{ ', ' '.join(box.cond_refs), ' }'))
    #if box.rel_boxes: print ind, '[{ ', ' '.join(box.rel_boxes), ' ]]'
    if box.subs: print("{} {} {} {}".format(ind, '< ', ' '.join(box.subs), ' >'))

#################################
def pr_2rel(rel, pr=False, sep='>'):
    '''Print binary relation'''
    message = '{ ' + ', '.join([a + sep + b for (a, b) in rel]) + ' }'
    if pr:
        print(message)
    else:
        return message

#################################
def pr_clf(clf, pr=False, inline=True, indent=0):
    '''Print clf with clause per line'''
    sep = '; ' if inline else '\n' + indent * ' '
    message = sep.join([pr_clause(clause) for clause in clf])
    if pr:
        print(indent * ' ' + message)
    else:
        return indent * ' ' + message

#################################
def pr_set(set, pr=False):
    '''Print set with simple elements'''
    message = '{ ' + ', '.join(set) + ' }'
    if pr:
        print(message)
    else:
        return message

#################################
def pr_clause(clause, pr=False):
    '''Make clause prettier (and print it if needed)'''
    message = ' '.join(clause)
    if pr:
        print(message)
    else:
        return message

#################################
def clf_to_box_dict(clf, op_types, arg_typing, v=0):
    '''Convert a clausal form into a dictionay of DRSs.
       Additionally return a set of Discourse relations, typing of conditions,
       and presupposition rels from PRESUPPOSITION
    '''
    box_dict = dict()   # collects all box names and box objects pairs
    disc_rels = set()   # a set of discourse relations
    presupp_rels = set()    # a set of subordinate (currently, presupposition) relations
    for (i, cl) in enumerate(clf):
        op_type = op_types[i]
        #if v >=4: print "Dealing with {} of type {}".format(cl, op_type)
        # gradually print boxes
        if v>=4:
            print(30 * '#')
            for b in box_dict:
                pr_box(box_dict[b], indent=5)
        # Reference clause: b REF x
        if op_type in ['REF']:
            (b, op, x) = cl
            if v >=4: print("Adding {} to {} as {}".format(cl, b, op_type))
            assert (arg_typing[b], arg_typing[x]) == ('b', 'x')
            box_dict.setdefault(b, Box(b)).refs.add(x)
            continue
        # clause for a condition with a single DRS
        if op_type in ['NOT', 'POS', 'NEC']: # remove 'DRS'
            (b0, op, b1) = cl
            if v >=4: print("Adding {} to {} as {}".format(cl, b0, op_type))
            assert (arg_typing[b0], arg_typing[b1]) == ('b', 'b')
            box_dict.setdefault(b0, Box(b0)).conds.add((op, b1))
            box_dict[b0].subs.add(b1)
            box_dict.setdefault(b1, Box(b1))
            continue
        # clause for an implication (b0 IMP b1 b2) or duplex (b0 DUP b1 b2) condition
        # also for disjunction condition: b0 DIS b1 b2
        if op_type in ['IMP', 'DUP', 'DIS']:
            (b0, op, b1, b2) = cl
            if v >=4: print("Adding {} to {} as {}".format(cl, b0, op_type))
            assert (arg_typing[b0], arg_typing[b1], arg_typing[b2]) == ('b', 'b', 'b')
            box_dict.setdefault(b0, Box(b0)).conds.add((op, b1, b2))
            box_dict[b0].subs.update([b1, b2])
            box_dict.setdefault(b1, Box(b1))
            box_dict.setdefault(b2, Box(b2))
            if op_type in ['IMP', 'DUP']:
                box_dict[b1].subs.add(b2) # antecedent subordinates consequent
            continue
        # clause for a propositional condition
        if op_type in ['PRP']:
            (b0, op, x, b1) = cl
            if v >=4: print("Adding {} to {} as {}".format(cl, b0, op_type))
            assert (arg_typing[b0], arg_typing[x], arg_typing[b1]) == ('b', 'x', 'b')
            box_dict.setdefault(b0, Box(b0)).conds.add((op, x, b1))
            box_dict[b0].subs.add(b1)
            box_dict[b0].cond_refs.add(x)
            #box_dict[b0].refs.add(x)
            box_dict.setdefault(b1, Box(b1))
            continue
        # clause for a condition with lexical/WN predicate
        if op_type in ['LEX']:
            (b, op, pos, t) = cl
            assert (arg_typing[b], arg_typing[pos]) == ('b', 'c') and unify_types(arg_typing[t], 't')
            if v >=4: print("Adding {} to {} as {}".format(cl, b, op_type))
            box_dict.setdefault(b, Box(b)).conds.add((op, pos, t))
            if arg_typing[t] == 'x':
                #box_dict[b].refs.add(x)
                box_dict[b].cond_refs.add(t)
            continue
        # clause for a discourse relation
        if op_type in ['DRL']:
            (b1, op, b2) = cl
            if v >=4: print("Adding {} as {}".format(cl, op_type))
            assert (arg_typing[b1], arg_typing[b2]) == ('b', 'b')
            # since there can be an empty box, allow DRLs to introduce boxes
            box_dict.setdefault(b1, Box(b1))
            box_dict.setdefault(b2, Box(b2))
            disc_rels.add((op, b1, b2)) # Disc. rels are floating
            continue
        # clause for a presupposition relation
        if op_type in ['PRE']: # presupposition relation gives subordinate info
            (b1, op, b2) = cl
            if v >=4: print("Adding {} as {}".format(cl, op_type))
            assert (arg_typing[b1], arg_typing[b2]) == ('b', 'b')
            presupp_rels.add((b1, b2)) # b1 subordinates b2 if b1 is a presupposition of b2
            # since there can be an empty box, allow PREs to introduce boxes
            box_dict.setdefault(b1, Box(b1))
            box_dict.setdefault(b2, Box(b2))
            continue
        # clause for a condition with Role predicate
        if op_type in ['ROL']:
            (b, op, t1, t2) = cl
            assert arg_typing[b] == 'b' and unify_types(arg_typing[t1], 't') and unify_types(arg_typing[t2], 't')
            if v >=4: print("Adding {} to {} as {}".format(cl, b, op_type))
            #pr_box(Box(b), indent=10)
            #print "conditions = {}".format(box_dict.setdefault(b, Box(b)).conds)
            box_dict.setdefault(b, Box(b)).conds.add((op, t1, t2))
            refs = [r for r in [t1, t2] if arg_typing[r] == 'x']
            #box_dict[b].refs.update(refs)
            box_dict[b].cond_refs.update(refs)
            continue
        # raise an error for the uncovered clauses
        raise RuntimeError("Cannot accommodate clause of this type in box || {} {}".format(cl, op_type))
    return box_dict, disc_rels, presupp_rels

#################################
def box_dict_to_subordinate_rel(box_dict, presupp_rels, disc_sub_rels, v=0):
    '''get transitive closure of the subordinate relation from
       direct subordination available in box dictionary and a presuposition relations.
       (b1,b2) should be read as 'b1 subordinates b2', or 'b2 is subordinate to b1', or 'refs of b1 are accessible for b2'
    '''
    subs = set()

    # read direct subordination from the box dictionary
    for b0 in box_dict:
        for b1 in box_dict[b0].subs:
            subs.add((b0, b1)) # b0 subordinates b1
    direct_subs = subs.copy()
    if v>=3: print("direct subs: {}".format(pr_2rel(sorted(subs))))
    if v>=3: print("presup subs: {}".format(pr_2rel(sorted(presupp_rels))))
    if v>=3: print("discrs subs: {}".format(pr_2rel(sorted(disc_sub_rels))))

    init_subs = subs.copy() | presupp_rels | disc_sub_rels # record subs before expansion
    subs.update(presupp_rels | disc_sub_rels)
    # if b2's condition uses referent introduced by b1,
    # then make b1 subordinate b2, i.e. b2 is subordinate to b1
    for b2 in box_dict:
        for ref in box_dict[b2].cond_refs:
            if v>=4: "{} if in {}".format(ref, b2)
            if ref not in box_dict[b2].refs:
                if v>=4: "{} is not introduced by {}".format(ref, b2)
                # referent is not introduced by the same box
                for b1 in box_dict:
                    if (b1 != b2) and (ref in box_dict[b1].refs):
                        # b1 introduces referent that b2 uses
                        subs.add((b1, b2))
    if v>=3: print("+ accessibility subs: {}".format(pr_2rel(sorted(subs - init_subs))))
    # get closure of subs by combining simple transitive rule
    # and subordination connectivity, which encourages connectivity of the relation
    # connectivity: if b0 directly subordinates b1, and b2 is not subordinate to b0 and subordinates b1,
    #   then b2 will subordinates b0 too
    #   for example, if k0 directly subordinates b1 & b2 since b1->b2 is in k0,
    #   then presupposition b0 of b1 and b2 will subordinate k0.
    # cl_subs = subs.copy()
    while True:
        temp_cl = subs.copy()
        tran_cl = transitive_closure(temp_cl, v=v)
        #subs = tran_cl
        subs = connectivity_closure(box_dict, tran_cl, v=v) # without connectivity ca 40% of CLFs are wrong
        if subs == temp_cl:
            break
    # subordination relation has no loops
    for (a, b) in subs:
        if a == b:
            raise RuntimeError("Subordinate relation has a loop || {}>{}".format(a, b))
    return subs, direct_subs


#################################
def transitive_closure(relation, v=0):
    '''return a transitive closure of the input relation'''
    tran_closure = relation.copy()
    while True:
        # add trnsitively obtained relations
        temp_rel = tran_closure.copy()
        for (a1, b1) in temp_rel:
            for (a2, b2) in temp_rel:
                if b1 == a2:
                    tran_closure.add((a1, b2))
        # exit when no increase is detected
        if temp_rel == tran_closure:
            break
    if v>=4: print("+ transitivity closure: {}".format(pr_2rel(sorted(tran_closure - relation))))
    return tran_closure

#################################
def connectivity_closure(box_dict, subs, v=0):
    '''return a connectivity closure of the subordination relation'''
    cl_subs = subs.copy()
    for b0 in box_dict:
        for b1 in box_dict[b0].subs:
            # add b>b0 if b0>b1 immediately and b>b1
            for b in [ b2 for (b2, b3) in subs if b3 == b1 and b2 != b0 and (b0, b2) not in subs ]:
                cl_subs.add((b, b0))
    if v>=4: print("+ connecticity closure: {}".format(pr_2rel(sorted(cl_subs - subs))))
    return cl_subs

################################# NOT USED
def linear_order(elements, rels, v=0):
    '''Check if relation is linear over elements and return max/top and min/bot elements.
       Relation is a set of tuples (op, el1, el2)
    '''
    # stop if elemenst or rels is empty
    if not (rels and elements): return None, None
    bot_set, top_set = elements.copy(), elements.copy()
    try: # remove elemenst from set gradually, in the end singleton sets should remain
        for _, a, b in rels:
            bot_set.remove(b)
            top_set.remove(a)
        if not(len(bot_set) == 1 and len(top_set) == 1):
             raise RuntimeError('Error')
    except:
        raise RuntimeError("Discourse boxes are not linearly ordered || min ({}) and max ({})".format(\
                           pr_set(bot_set), pr_set(top_set)))
    return bot_set.pop(), top_set.pop()

################################# not in use
def connected_boxes(elements, rels, v=0):
    '''Check if all boxes are connected with a relation,
       i.e. one can visist to any box from any box via the relation (non-directional)
    '''
    # stop if elements or rels is empty
    if not (rels and elements):
        return False
    # start with empty set and increase gradually to cover all elements
    before_expansion = set()
    expanding = set([elements.pop()]) # start with a random element
    while before_expansion != expanding: # i.e. after expansion it didn't expand
        before_expansion = expanding.copy()
        for i in before_expansion.copy():
            for (a, b) in rels.copy():
                if i == a:
                    expanding.add(b)
                    rels.remove((a,b))
                if i == b:
                    expanding.add(a)
                    rels.remove((a,b))
    diff = elements - expanding
    if diff:
        raise RuntimeError("Boxes are not connected || {} are not connected with {}".format(\
                           pr_set(diff), pr_set(expanding)))
    else:
        if v >= 2: print("Boxes {} are connected".format(pr_set(elements)))

#################################
def unbound_referents(box_dict, sub_rel, v=0):
    '''get a set of unbound discourse referents
    '''
    unbound = set()
    for b in box_dict:
        outsider_refs = box_dict[b].cond_refs - box_dict[b].refs
        #print "outsider refs for {} are {}".format(b, pr_set(outsider_refs))
        for x in outsider_refs:
            # find a box subordinating the current one and introducing x as referent
            if not next(( b1 for (b1, b2) in sub_rel
                          if b2 == b and x in box_dict[b1].refs ),
                    False):
                unbound.add(x)
                # one can already raise error for efficiency
    return unbound

#################################
def non_subordinating_boxes(box_dict, sub_rel, v=0):
    '''Get boxes that do not subordinate anything
    '''
    non_sub_boxes = set()
    for a in box_dict:
        # if there is b such that a subordinates b
        if next((b for b in box_dict if a != b and (a, b) in sub_rel), False):
            continue
        non_sub_boxes.add(a)
    return non_sub_boxes


############ MAIN ###############
#################################
if __name__ == '__main__':
    args = parse_arguments()

    # read clausal forms and raw from the file
    (clfs, raws) = file_to_clfs(args.src, v=args.v)
    assert len(clfs) == len(raws),\
        'clfs ({}) and raws ({}) do not match'.format(len(clfs), len(raws))
    total = len(clfs)
    if total == 0:
        if args.quiet: sys.exit()
        raise ValueError("No CLFs were found")
    if args.v >= 1: print("{} clausal forms (with {} raw) retrieved".format(total, len(raws)))

    # get info about signature as dictionary
    signature = get_signature(args.sig_file, v=args.v)

    # check each clausal form
    error_counter = Counter()
    op_type_counter = Counter() # counts operator types. Used for clf stats

    # clfs = [ clf for clf in clfs if len(clf) > 30 ]  # ignore long CLFs for debugging purpose
    for (i, clf) in enumerate(clfs, start=1):
        counter_prog(i, v=args.v)
        if args.v >= 2 and raws: print(' "{}"'.format(raws[i-1]))
        try:
            (box_dict, subs, _, op_types) = check_clf(clf, signature, v=args.v)
            op_type_counter.update(op_types)
        except RuntimeError as e:
            if not args.quiet: raise
            try: # compatible with py2 and py3
                error_counter.update([str(e).decode('utf-8')])
            except:
                error_counter.update([str(e)])
            print(e)
            if args.v >= 1:
                if raws: print(' "{}"'.format(raws[i-1]))
                print("In the CLF:\n{}".format(pr_clf(clf)))
    if args.v>=1: print("Done")
    error_total = sum(error_counter.values())
    if args.quiet:
        print("#wrong = {} ({:.2f}%)".format(error_total, error_total*100/float(total)))
    if args.v >= 1:
        # print frequency of errors
        if error_counter: print("Error frequency")
        for (err, c) in error_counter.most_common():
            print("{} {}".format(c, err))
        # print frequency of operator types
        if op_type_counter: print("Operator type frequency")
        for (op_type, c) in op_type_counter.most_common():
            print("{} {}".format(c, op_type))
