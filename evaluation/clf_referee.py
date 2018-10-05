#!/usr/bin/env python
# -*- coding: utf8 -*-

'''
Validate sets of clauses in the file 
'''

# example how to run: python python/clf_referee.py FILE -v 1

from __future__ import unicode_literals
import sys
import os
import codecs
import argparse
import re
import yaml
from collections import Counter


#################################
#################################
def check_clf(clf, signature, v=0):
    '''checks well-formedness of a clausal form'''
    # get argument typing and for each clause an operator type 
    (op_types, arg_typing) = clf_typing(clf, signature, v=v)
    # get dictionary of box objects
    box_dict = clf_to_box_dict(clf, op_types, arg_typing, v=v)
    if v>=2: print "#boxes = {}".format(len(box_dict))
    if v>=3: 
        for b in box_dict:
            pr_box(box_dict[b])   
    # get transitive closure of subordinate relation (as set)
    sub_rel = box_dict_to_subordinate_rel(box_dict, v=v)
    if v>=2: print "subordinate relation: {}".format(pr_2rel(sub_rel))
    # get main box name
    main_box = detect_main_box(box_dict, sub_rel, v=v)
    if v>=2: print "main box is {}".format(main_box)
    # find is there are unbound referents
    unbound_refs = unbound_referents(box_dict, sub_rel, v=v)
    if unbound_refs: 
        raise RuntimeError('Unbound referents || {}'.format(pr_set(unbound_refs)))
    return (main_box, box_dict, sub_rel, op_types) 

#####################################
def counter_prog(i):
    '''Displays a counter to show the progress'''
    sys.stdout.write('\r{}:'.format(i))
    sys.stdout.flush()
    return True
    

#################################    
def clf_typing(clf, signature, v=0):
    '''Checks well-formedness of a clausal for in terms of typing.
       Return a list of clause types (i.e. opearator types)
       and a dictionary of term typing
    '''
    arg_typing = dict()
    op_types = []
    # check each clause individually and get variable types
    for cl in clf:
        (op_type, typing) = clause_typing(cl, signature, v=v)
        op_types.append(op_type)
        if v >= 4: print "{}: {} @ {}".format(pr_clause(cl), op_type, pr_2rel(typing, sep=':'))  
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
    #print arg_typing info
    #for (i, cl) in enumerate(clf):
    #    print "{}: {} @ {}".format(cl, op_types[i][0], op_types[i][1])
    #for var in arg_typing:
    #    print "{} of type {}".format(var, arg_typing[var])      
    return (op_types, arg_typing)        
    
#################################
def clause_typing(clause, signature, v=0):
    '''checks well-formedness of a clause (context insensitive) 
       and returns its main operator type with the types of variables
    '''
    operator = clause[1]
    arguments = (clause[0],) + clause[2:]
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
    if v >= 4: print arg, t
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
    if re.match('"[avnr]\.\d\d"$', args[1]):
        return ('LEX', 'bct') # b LEX c t   
    # whne signature is empty use a fallback type-checking
    if not sig:
       return operator_type_default(op, args, v=v)
    # Operator is in the signature    
    if op in sig:
        (op_kind, arg_types) = sig[op]
        if op_kind == 'DRS':
            return (op, arg_types)
        if op_kind == 'DRL':
            return ('REL', arg_types)
        return ('ROL', arg_types)
    report_error("unknown clause || {} @ {}".format(op, args), v=v)
        
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
    # is a temporal or spatial relation
    if len(op) == 3 and op.isupper():
        return ('ROL', 'btt')  
    # is a discourse relation  
    if op.isupper():
        return ('REL', 'bbb') 
    # is a role
    if op[0:2].istitle(): # includes the roles like "PartOf" too
        return('ROL', 'btt')         
    report_error("unknown clause || {} @ {}".format(op, args), v=v)       

#################################
#################################
def file_to_clfs(filepath, v=0):
    '''reads a file with clausal forms inside it and
       returns a list of clausal forms where each form is a list of clauses/tuples
       An empty line is a separator of clausal forms
    '''
    list_of_clf = []
    list_of_raw = []
    clf = []
    with codecs.open(filepath, 'r', encoding='UTF-8') as f:
        pre_line = ''
        for line in f:
            # when the line is a comment ignore, 
            # but if its previous line contains a raw text, then save it
            if line.startswith("%"):
                if pre_line.startswith("%%% ") and line.startswith("% "):
                    list_of_raw.append(pre_line[3:].strip())
                pre_line = line
                continue
            if not line.strip(): # clf separator
                if clf: # add only non-empty clf
                    list_of_clf.append(clf)
                    clf = []
                continue
            # remove % comments if any
            line = line.split(' %', 1)[0].strip()
            if v >= 5: print "/{}/".format(line)
            clause = tuple(line.split(' '))
            if len(clause) > 1: #remove lines that are comments and started with whitespace
                clf.append(clause)
    if clf: # add last clf
        list_of_clf.append(clf)
    return (list_of_clf, list_of_raw) 

#################################
def report_error(message, v=0):
    if v >= 1: 
        print message
    raise RuntimeError(message)  

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
        self.box_refs = set() 
        # set of DRS conditions    
        self.conds = set()
        # discourse referents directly mentioned in DRS conditions
        self.cond_refs = set()
        # boxes which this subordinates
        self.subs = set()
        # discourse relations
        self.rels = set()
        # boxes mentioned in discourse relations
        self.rel_boxes = set()
        

#################################
###### Box related functions#####

#################################
def pr_box(box, indent=0):
    '''Print a box object'''
    ind = indent * ' '
    print ind, 20 * '_'
    print ind, box.name
    #discourse referents
    print ind, '| ', ' '.join(box.refs)
    if box.box_refs:
        print ind, '[[ ', ' '.join(box.box_refs)
    print ind, 20 * '-'
    if box.conds:
        for c in box.conds:
            print ind, '| ', ' '.join(c)
    if box.rels:
        for r in box.rels: 
            print ind, '[ ', ' '.join(r), ' ]'  
    if box.cond_refs:
        print ind, '{ ', ' '.join(box.cond_refs), ' }'  
    if box.rel_boxes:
        print ind, '[{ ', ' '.join(box.rel_boxes), ' ]]'
    if box.subs:
        print ind, '< ', ' '.join(box.subs), ' >'

#################################
def pr_2rel(rel, pr=False, sep='>'):
    '''Print binary relation'''
    message = '{ ' + ', '.join([a + sep + b for (a, b) in rel]) + ' }'
    if pr:
        print message
    else:
        return message

#################################
def pr_clf(clf, pr=False, inline=True, indent=0):
    '''Print clf with clause per line'''
    sep = '; ' if inline else '\n' + indent * ' ' 
    message = sep.join([pr_clause(clause) for clause in clf])
    if pr:
        print indent * ' ' + message
    else:
        return indent * ' ' + message

#################################
def pr_set(set, pr=False):
    '''Print set with simple elements'''
    message = '{ ' + ', '.join(set) + ' }'
    if pr:
        print message
    else:
        return message

#################################
def pr_clause(clause, pr=False):
    '''Make clause prettier (and print it if needed)'''
    message = ' '.join(clause)
    if pr:
        print message
    else:
        return message

#################################
def clf_to_box_dict(clf, op_types, arg_typing, v=0):
    '''Convert a clausal form into dictionay of DRSs'''
    box_dict = dict()
    for (i, cl) in enumerate(clf):
        op_type = op_types[i]
        if v>=4: 
            print 30 * '#'
            for b in box_dict:
                pr_box(box_dict[b], indent=5)   
        # Reference clause: b REF x
        if op_type in ['REF']:
            (b, op, x) = cl
            if v >=4: print "Adding {} to {} as {}".format(cl, b, op_type)
            assert (arg_typing[b], arg_typing[x]) == ('b', 'x') 
            box_dict.setdefault(b, Box(b)).refs.add(x)
            continue
        # clause for a condition with a single DRS
        if op_type in ['NOT', 'POS', 'NEC']:
            (b0, op, b1) = cl
            if v >=4: print "Adding {} to {} as {}".format(cl, b0, op_type)
            assert (arg_typing[b0], arg_typing[b1]) == ('b', 'b') 
            box_dict.setdefault(b0, Box(b0)).conds.add((op, b1))
            box_dict[b0].subs.add(b1)
            box_dict.setdefault(b1, Box(b1))
            continue
        # clause for an SDRS-formula: k DRS b
        if op_type in ['DRS']:
            (k, op, b) = cl
            if v >=4: print "Adding {} to {} as {}".format(cl, k, op_type)
            assert (arg_typing[k], arg_typing[b]) == ('b', 'b') 
            box_dict.setdefault(k, Box(k)).box_refs.add(b)
            box_dict[k].subs.add(b)
            box_dict.setdefault(b, Box(b))
            continue
        # clause for an implication (b0 IMP b1 b2) or duplex (b0 DUP b1 b2) condition  
        if op_type in ['IMP', 'DUP']:
            (b0, op, b1, b2) = cl
            if v >=4: print "Adding {} to {} as {}".format(cl, b0, op_type)
            assert (arg_typing[b0], arg_typing[b1], arg_typing[b2]) == ('b', 'b', 'b') 
            box_dict.setdefault(b0, Box(b0)).conds.add((op, b1, b2))
            box_dict[b0].subs.update([b1, b2])
            box_dict.setdefault(b1, Box(b1))
            box_dict.setdefault(b2, Box(b2))
            box_dict[b1].subs.add(b2) # antecedent subordinates consequent
            continue
        # clause for a disjunction condition: b0 DIS b1 b2  
        if op_type in ['DIS']:
            (b0, op, b1, b2) = cl
            if v >=4: print "Adding {} to {} as {}".format(cl, b0, op_type)
            assert (arg_typing[b0], arg_typing[b1], arg_typing[b2]) == ('b', 'b', 'b') 
            box_dict.setdefault(b0, Box(b0)).conds.add((op, b1, b2))
            box_dict[b0].subs.update([b1, b2])
            box_dict.setdefault(b1, Box(b1))
            box_dict.setdefault(b2, Box(b2))
            continue
        # clause for a propositional condition
        if op_type in ['PRP']:
            (b0, op, x, b1) = cl
            if v >=4: print "Adding {} to {} as {}".format(cl, b0, op_type)
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
            if v >=4: print "Adding {} to {} as {}".format(cl, b, op_type)
            box_dict.setdefault(b, Box(b)).conds.add((op, pos, t))
            if arg_typing[t] == 'x': 
                #box_dict[b].refs.add(x)
                box_dict[b].cond_refs.add(t)
            continue
        # clause for a discourse relation
        if op_type in ['REL']:
            (b0, op, b1, b2) = cl
            if v >=4: print "Adding {} to {} as {}".format(cl, b0, op_type)
            assert (arg_typing[b0], arg_typing[b1], arg_typing[b2]) == ('b', 'b', 'b')
            box_dict.setdefault(b0, Box(b0)).rels.add((op, b1, b2))
            box_dict.setdefault(b0).rel_boxes.update([b1, b2])
            continue
        # clause for a condition with Role predicate
        if op_type in ['ROL']:
            (b, op, t1, t2) = cl
            assert arg_typing[b] == 'b' and unify_types(arg_typing[t1], 't') and unify_types(arg_typing[t2], 't') 
            if v >=4: print "Adding {} to {} as {}".format(cl, b, op_type)
            #pr_box(Box(b), indent=10)
            #print "conditions = {}".format(box_dict.setdefault(b, Box(b)).conds)
            box_dict.setdefault(b, Box(b)).conds.add((op, t1, t2))
            refs = [r for r in [t1, t2] if arg_typing[r] == 'x']
            #box_dict[b].refs.update(refs)
            box_dict[b].cond_refs.update(refs)
            continue
        # raise an error for the uncovered clauses 
        raise RuntimeError("Cannot accommodate clause of this type in box || {} {}".format(cl, op_type))
    # a set of referent boxes (introduced by DRS) should equal 
    # a set of boxes participating in discourse relations
    for b in box_dict:
        if box_dict[b].box_refs != box_dict[b].rel_boxes:
            raise RuntimeError("Referent boxes differ from boxes in relations || {} {} {}".format(
                pr_set(box_dict[b].box_refs), b, pr_set(box_dict[b].rel_boxes)))
    return box_dict  
                       
#################################
def box_dict_to_subordinate_rel(box_dict, v=0):
    '''get transitive closure of the subordinate relation () 
       from direct subordination available in box dictionary
    ''' 
    subs = set()           
    for b0 in box_dict:
        for b1 in box_dict[b0].subs:
            # b0 subordinates b1
            subs.add((b0, b1))
    if v>=4: print "direct subs: {}".format(pr_2rel(sorted(subs)))
    old_subs = subs.copy()
    # if b2's condition uses referent introduced by b1,
    # then make b1 subordinate b2
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
    if v>=4: print "+ accessibility subs: {}".format(pr_2rel(sorted(subs - old_subs)))
    # get closure of subs by combining simple transitive rule
    # and subordination connectivity, which encourages connectivity of teh relation  
    # connectivity: if b0 directly subordinates b1, 
    # and b2 is not subordinate to b0 and subordinates b1, then b1 subordinates b0 too
    # for example, k0 subordinates b1, b2 as b1->b2 is in k0, then 
    # presupposition b0 of b1 and b2 will subordinate k0, 
    # but b1 won't subordinate k0 as k0 subordinates b1.
    # cl_subs = subs.copy()
    while True:
        temp_cl = subs.copy() 
        tran_cl = transitive_closure(temp_cl, v=v)
        #subs = tran_cl 
        subs = connectivity_closure(box_dict, tran_cl, v=v)
        if subs == temp_cl:
            break       
    # subordination relation has no loops
    for (a, b) in subs:
        if a == b:
            raise RuntimeError("Subordinate relation has a loop || {}>{}".format(a, b))
    return subs 


#################################
def transitive_closure(relation, v=0):
    '''return a transitive closure of the input relation
    '''
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
    if v>=4: print "+ transitivity closure: {}".format(pr_2rel(sorted(tran_closure - relation)))
    return tran_closure

#################################
def connectivity_closure(box_dict, subs, v=0):
    '''return a connectivity closure of the subordination relation
    '''
    cl_subs = subs.copy()
    for b0 in box_dict:
        for b1 in box_dict[b0].subs:
            # add b>b0 if b>b1 directly, works well in practice 
            for b in [ b2 for (b2, b3) in subs if b3 == b1 and b2 != b0 and (b0, b2) not in subs ]: 
                cl_subs.add((b, b0))   
    if v>=4: print "+ connecticity closure: {}".format(pr_2rel(sorted(cl_subs - subs)))
    return cl_subs

#################################
def detect_main_box(box_dict, sub_rel, v=0):
    '''given boxes and a subordinate relation
       find the main box and revise subordinate relation
    ''' 
    # get a set of boxes that are not sitting inside other boxes
    # e.g., presuppositions will be such boxes  
    independent_boxes = set() 
    for b0 in box_dict:
        # there is no b1 that contains b0 in relations or conditions
        if not next(( b1 for b1 in box_dict if b0 in box_dict[b1].subs or b0 in box_dict[b1].rel_boxes ), False):
            independent_boxes.add(b0)
    if v>=3: print "independent_boxes = {}".format(pr_set(independent_boxes))
    # get the independent boxe that is subordinate to the rest of the independent boxes 
    main_box = set()  
    for b in independent_boxes:
        if len(independent_boxes) == len([b1 for (b1, b2) in sub_rel if b2 == b]) + 1:                                    
            main_box.add(b) 
    # main box is expected to be unique  
    if len(main_box) > 1:
        raise RuntimeError("Non-unique ({}) main boxes || {}".format(len(main_box), main_box))
    elif len(main_box) < 1: 
        raise RuntimeError("No main box found")
    else: 
        return main_box.pop()

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
############ MAIN ###############
def parse_arguments():
    parser = argparse.ArgumentParser(description='Validate sets of caluses in the file')
    parser.add_argument(
    'src', metavar='PATH', 
        help='File containing sets of caluses')
    parser.add_argument(
    '-v', '--verbose', dest='v', default=0, type=int,
        metavar='N', help='verbosity level of reporting')
    #parser.add_argument(
    #'--error', action='store_true', 
    #    help='report the mistakes found by throwing an error')
    parser.add_argument(
    '-s', '--sig', dest='sig_file', default = '', 
        help='If added, this contains a file with all allowed roles\
              otherwise a simple signature is used that\
              mainly recognizes operators based on their formatting') 
    args = parser.parse_args()
    return args

   
#################################
if __name__ == '__main__':
    args = parse_arguments()
    (clfs, raws) = file_to_clfs(args.src, v=args.v) 
    total = len(clfs)
    if args.v >= 1: print "{} clausal forms (with {} raw) retrieved".format(total, len(raws))
    # get info about signature as dictionary
    signature = get_signature(args.sig_file, v=args.v)    
    # check each clausal form
    error_counter = Counter()
    op_type_counter = Counter()
    for (i, clf) in enumerate(clfs):
        counter_prog(i)
        if args.v >= 2 and raws: print ' "{}"'.format(raws[i]) 
        try:
            (mbox, box_dict, subs, op_types) = check_clf(clf, signature, v=args.v)
            op_type_counter.update(op_types)
        except RuntimeError as e:
            error_counter.update([e[0]])
            if args.v >= 1: 
                print "In the CLF:\n{}".format(pr_clf(clf))                
    print "Done"
    error_total = sum(error_counter.values())
    print "#wrong = {} ({:.2f}%)".format(error_total, error_total*100/float(total))  
    if args.v >= 1:
        # print frequency of errors
        if error_counter: print "Error frequency"
        for (err, c) in error_counter.most_common():
            print c, err 
        # print frequency of operator types
        if op_type_counter: print "Operator type frequency"
        for (op_type, c) in op_type_counter.most_common():
            print c, op_type 
            

