#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This script computes an F-score between two DRSs. It is based on and very similar to SMATCH.
For detailed description of smatch, see http://www.isi.edu/natural-language/drs/smatch-13.pdf

As opposed to AMRs, this script takes the clauses directly as input. Each clause should be on a
single line, with DRSs separated by a newline. Lines starting with '%' are ignored.

Command line options:

-f1   : First file with DRS clauses, usually produced file
-f2   : Second file with DRS clauses, usually gold file
-r    : Number of restarts used
-m    : Max number of clauses for a DRS to still take them into account - default 0 means no limit
-p    : Number of parallel threads to use (default 1)
-runs : Number of runs to average over, if you want a more reliable result (there is randomness involved in the initial restarts)
-s    : What kind of smart initial mapping we use:
      -no    No smart mappings
      -conc  Smart mapping based on matching concepts (their match is likely to be in the optimal mapping)
      -role  Smart mapping based on matching role clauses
      -all   Doing both the smart concept and smart role mapping
-prin : Print more specific output, such as individual (average) F-scores for the smart initial mappings, and the matching and non-matching clauses
-sig  : Number of significant digits to output (default 4)
-b    : Use this for baseline experiments, comparing a single DRS to a list of DRSs. Produced DRS file should contain a single DRS.
-ms   : Instead of averaging the score, output a score for each DRS
-pr   : Also output precison and recall
-pa   : Partial matching of clauses instead of full matching -- experimental setting!
        Means that the clauses x1 work "n.01" x2 and x1 run "n.01" x2 are able to match for 0.75, for example
-st   : Printing statistics regarding number of variables and clauses, don't do matching
-ic   : Include REF clauses when matching (otherwise they are ignored because they inflate the matching)
-dr   : Print specific information for scores after X number of restarts
-v    : Verbose output
-vv   : Very verbose output
"""

import os
import random
import time
import argparse
import re
import sys
reload(sys)
sys.setdefaultencoding('utf-8')  # necessary to avoid unicode errors
import multiprocessing
import psutil  # for memory usage


def build_arg_parser():

    parser = argparse.ArgumentParser(
        description="Counter calculator -- arguments")

    parser.add_argument('-f1', required=True, type=str,
                        help='First file with DRS clauses, DRSs need to be separated by blank line')
    parser.add_argument('-f2', required=True, type=str,
                        help='Second file with DRS clauses, DRSs need to be separated by blank line')
    parser.add_argument('-m', '--max_clauses', type=int, default=0,
                        help='Maximum number of clauses for DRS (default 0 means no limit)')
    parser.add_argument('-p', '--parallel', type=int, default=1,
                        help='Number of parallel threads we use (default 1)')
    parser.add_argument('-s', '--smart', default='all', action='store', choices=[
                        'no', 'all', 'conc', 'role'], help='What kind of smart mapping do we use (default all)')
    parser.add_argument('-prin', action='store_true',
                        help='Print very specific output - matching and non-matching clauses and specific F-scores for smart mappings')
    parser.add_argument('-r', '--restarts', type=int,
                        default=20, help='Restart number (default: 20)')
    parser.add_argument('-sig', '--significant', type=int,
                        default=4, help='significant digits to output (default: 4)')
    parser.add_argument('-mem', '--mem_limit', type=int, default=1000,
                        help='Memory limit in MBs (default 1000 -> 1G). Note that this is per parallel thread! If you use -par 4, each thread gets 1000 MB with default settings.')
    parser.add_argument('-b', '--baseline', action='store_true', default=False,
                        help="Helps in deciding a good baseline DRS. If added, prod-file must be a single DRS, gold file a number of DRSs to compare to (default false)")
    parser.add_argument('-ms', action='store_true', default=False,
                        help='Output multiple scores (one pair per score) instead of a single document-level score (Default: false)')
    parser.add_argument('-pr', action='store_true', default=False,
                        help="Output precision and recall as well as the f-score. Default: false")
    parser.add_argument('-nm', '--no_mapping', action='store_true',
                        help='If added, do not print the mapping of variables in terms of clauses')
    parser.add_argument('-pa', '--partial', action='store_true',
                        help='Do partial matching for the DRSs (experimental!)')
    parser.add_argument('-ic', '--include_ref', action='store_true',
                        help='Include REF clauses when matching -- will inflate the scores')
    parser.add_argument('-v', action='store_true',
                        help='Verbose output (Default:false)')
    parser.add_argument('-vv', action='store_true',
                        help='Very Verbose output (Default:false)')
    args = parser.parse_args()

    # Check if files exist

    if not os.path.exists(args.f1):
        raise ValueError("File for -f1 does not exist")
    if not os.path.exists(args.f2):
        raise ValueError("File for -f2 does not exist")

    # Check if combination of arguments is valid
    if args.restarts < 1:
        raise ValueError('Number of restarts must be larger than 0')
    elif args.smart == 'all' and args.restarts < 2:
        raise ValueError(
            "All smart mappings is already 2 restarts, therefore -r should at least be 2, not {0}".format(args.restarts))

    if args.ms and args.parallel > 1:
        print 'WARNING: using -ms and -p > 1 messes up printing to screen - not recommended'
        time.sleep(5)  # so people can still read the warning

    elif (args.vv or args.v) and args.parallel > 1:
        print 'WARNING: using -vv or -v and -p > 1 messes up printing to screen - not recommended'
        time.sleep(5)  # so people can still read the warning

    if args.partial:
        print 'WARNING: partial matching is an experimental setting!'
        time.sleep(5)
    return args


def get_memory_usage():
    '''Return the memory usage in MB'''
    process = psutil.Process(os.getpid())
    mem = process.memory_info()[0] / float(1000000)
    return mem


def get_best_match(clauses_prod, clauses_gold, prefix1, prefix2, var_count, var_types1, var_types2, var_map_prod, var_map_gold, prin, single, significant, memory_limit, counter):
    """
    Get the highest clause match number between two sets of clauses via hill-climbing.
    Arguments:
        clauses_prod: list of lists with all types of clauses
        clauses_gold: list of lists with all types of clauses
        prefix1: prefix label for DRS 1
        prefix2: prefix label for DRS 2
        var_count: number of variables
        var_types: types of variables
        var_map: mapping dictionary of rewritten variables to previous variables
    Returns:
        best_match: the node mapping that results in the highest clause matching number
        best_match_num: the highest clause matching number

    """

    # Compute candidate pool - all possible node match candidates.
    # In the hill-climbing, we only consider candidate in this pool to save computing time.
    # weight_dict is a dictionary that maps a pair of node
    (candidate_mappings, weight_dict) = compute_pool(clauses_prod,
                                                     clauses_gold, prefix1, prefix2, var_count, var_types1, var_types2)

    test_clause_num = sum([len(x) for x in clauses_prod])
    gold_clause_num = sum([len(x) for x in clauses_gold])

    # save mapping and number of matches so that we don't have to calculate stuff twice
    match_clause_dict = {}

    # Set intitial values
    best_match_num = 0
    best_mapping = [-1] * len(var_map_prod)
    found_idx = 0
    all_fscores = []
    cur_best_matches = []

    # Find smart mappings first
    smart_mappings = get_smart_mappings(candidate_mappings, clauses_prod, clauses_gold, weight_dict, args.smart, match_clause_dict)
    num_smart = len(smart_mappings)
    smart_fscores = [0] * num_smart

    # Then add random mappings
    mapping_order   = smart_mappings + get_mapping_list(candidate_mappings, weight_dict, args.restarts - num_smart, match_clause_dict)

    # Set initial values
    num_maps = len(set([tuple(x[0]) for x in mapping_order]))
    done_mappings = {}
    start_time = time.time()

    # Loop over the mappings to find the best score
    for i, map_cur in enumerate(mapping_order):  # number of restarts is number of mappings
        cur_mapping = map_cur[0]
        match_num = map_cur[1]
        if veryVerbose:
            print >> DEBUG_LOG, "Node mapping at start", cur_mapping
            print >> DEBUG_LOG, "Clause match number at start:", match_num

        if tuple(cur_mapping) in done_mappings:
            match_num = done_mappings[tuple(cur_mapping)]
        else:
            # Do hill-climbing until there will be no gain for new node mapping
            while True:
                # get best gain
                (gain, new_mapping, match_clause_dict) = get_best_gain(cur_mapping, candidate_mappings, weight_dict, len(var_map_gold), match_clause_dict)

                if veryVerbose:
                    print >> DEBUG_LOG, "Gain after the hill-climbing", gain

                if match_num + gain > test_clause_num:
                    print new_mapping, match_num + gain, test_clause_num
                    raise ValueError(
                        "More matches than there are produced clauses. If this ever occurs something is seriously wrong with the algorithm")

                if gain <= 0:
                    # print 'No gain so break'
                    break
                # otherwise update match_num and mapping
                match_num += gain

                cur_mapping = new_mapping[:]
                if veryVerbose:
                    print >> DEBUG_LOG, "Update clause match number to:", match_num
                    print >> DEBUG_LOG, "Current mapping:", cur_mapping

            # Save mappings we already did
            done_mappings[tuple(cur_mapping)] = match_num

            # Update our best match number so far
            if match_num > best_match_num:
                best_mapping = cur_mapping[:]
                best_match_num = match_num
                found_idx = i

            # Check if we exceed maximum memory, if so, clear clause_dict
            # (saves us from getting memory issues with high number of
            # restarts)
            if get_memory_usage() > memory_limit:
                match_clause_dict.clear()

        # If we have matched as much we can (precision 1.0), we might as well
        # stop instead of doing all other restarts - but always do smart
        # mappings
        if match_num == test_clause_num and i > num_smart - 1:
            (_, _, f_score) = compute_f(match_num, test_clause_num, gold_clause_num, significant, False)
            all_fscores.append(f_score)
            if prin and single:
                print 'Best match already found, stop restarts at restart {0}'.format(i)
            if i < len(smart_fscores):
                smart_fscores[i] = match_num
            cur_best_matches.append([match_num, time.time() - start_time])
            break

        # Calculate F-score of this restarts
        (_, _, f_score) = compute_f(match_num, test_clause_num, gold_clause_num, significant, False)
        all_fscores.append(f_score)

        # Save best matches at this point in time
        cur_best_matches.append([best_match_num, time.time() - start_time])

        # Add smart F-scores
        if i < len(smart_fscores):  # are we still adding smart F-scores?
            smart_fscores[i] = match_num

    # Compute last results
    avg_f = round(float(sum(all_fscores)) /
                  float(len(all_fscores)), args.significant)
                  # average F-score over all restarts
    _, clause_pairs = compute_match(best_mapping, weight_dict, {}, final=True)

    # Clear matches out of memory
    match_clause_dict.clear()

    return best_mapping, best_match_num, found_idx, len(mapping_order), avg_f, smart_fscores, clause_pairs, num_maps, cur_best_matches


def get_smart_mappings(candidate_mappings, clauses_prod, clauses_gold, weight_dict, smart, match_clause_dict):
    '''Get all the smart mappings specified
    no   : don't do any smart mapping
    conc : Smart mapping based on matching concepts
    role : Smart mapping based on matching roles
    all  : All previously described mappings'''

    # Unpack necessary arguments
    _, _, _, _, roles1, concepts1 = clauses_prod
    _, _, _, _, roles2, concepts2 = clauses_gold

    if smart == 'no':
        return []
    # Best initial mapping based on matching roles
    elif smart == 'role':
        smart_roles = smart_role_mapping(candidate_mappings, roles1, roles2)
        matches, match_clause_dict = compute_match(smart_roles, weight_dict, match_clause_dict)
        smart_mappings_all = [[smart_roles, matches]]
    # Best initial mapping based on matching concepts
    elif smart == 'conc':
        smart_conc = smart_concept_mapping(candidate_mappings, concepts1, concepts2)
        matches, match_clause_dict = compute_match(smart_conc, weight_dict, match_clause_dict)
        smart_mappings_all = [[smart_conc, matches]]
    # Best two initial mappings based on matching roles and concepts
    elif smart == 'all':
        smart_roles = smart_role_mapping(candidate_mappings, roles1, roles2)
        smart_conc = smart_concept_mapping(candidate_mappings, concepts1, concepts2)
        matches_roles, match_clause_dict = compute_match(smart_roles, weight_dict, match_clause_dict)
        matches_conc, match_clause_dict = compute_match(smart_conc, weight_dict, match_clause_dict)
        smart_mappings_all = [[smart_roles, matches_roles], [smart_conc, matches_conc]]

    return smart_mappings_all


def get_mapping_list(candidate_mappings, weight_dict, total_restarts, match_clause_dict):
    '''Function that returns a mapping list, each item being [mapping, match_num] '''

    if total_restarts <= 0:  # nothing to do here, we do more smart mappings than restarts anyway
        return []
    random_maps = get_random_set(candidate_mappings, weight_dict, total_restarts, match_clause_dict)  # get set of random mappings here
    return random_maps


def get_random_set(candidate_mappings, weight_dict, map_ceil, match_clause_dict):
    '''Function that returns a set of random mappings based on candidate_mappings'''

    random_maps = []
    count_duplicate = 0

    while len(random_maps) < map_ceil and count_duplicate <= 50:  # only do random mappings we haven't done before, but if we have 50 duplicates in a row, we are probably done with all mappings
        cur_mapping = add_random_mapping([-1 for x in candidate_mappings], {}, candidate_mappings)
        match_num, match_clause_dict = compute_match(cur_mapping, weight_dict, match_clause_dict)
        if [cur_mapping, match_num] not in random_maps and len(set([x for x in cur_mapping if x != -1])) == len([x for x in cur_mapping if x != -1]):
            random_maps.append([cur_mapping, match_num])
            count_duplicate = 0
        else:
            count_duplicate += 1
    return random_maps


def normalize(item):
    """
    lowercase and remove quote signifiers from items that are about to be compared
    """
    item = item.rstrip('_')
    return item


def add_node_pairs(node_pair1, node_pair2, node_pair3, weight_dict, weight_score, no_match, gold_clause_idx, prod_clause_idx):
    '''Add possible node pairs to weight dict for node pair1'''

    if len([node_pair1, node_pair2, node_pair3]) == len(set([node_pair1, node_pair2, node_pair3])):  # node pairs cant be duplicates
        if node_pair1 in weight_dict:
            if (node_pair2, node_pair3) in weight_dict[node_pair1]:
                weight_dict[node_pair1][(node_pair2, node_pair3)].append([weight_score, no_match, gold_clause_idx, prod_clause_idx])
            else:
                weight_dict[node_pair1][(node_pair2, node_pair3)] = [[weight_score, no_match, gold_clause_idx, prod_clause_idx]]
        else:
            weight_dict[node_pair1] = {}
            weight_dict[node_pair1][(node_pair2, node_pair3)] = [[weight_score, no_match, gold_clause_idx, prod_clause_idx]]
    return weight_dict


def add_candidate_mapping_three_vars(clause1, clause2, prefix1, prefix2, candidate_mapping, weight_dict, index1, index2, index3, edge_index, i, j, var_types1, var_types2, add_to_index, add_to_index2):
    '''Add the candidate mapping for this node pair to the weight dict - for three variables
       It is possible to do partial matching, but the usual case only does full matching'''

    # Set initial variables
    allowed_var1, allowed_var2, allowed_var3, same_edge_type = False, False, False, False
    edge_match = 0

    # Set values to make things a bit clearer
    node1_index_drs1 = int(clause1[i][index1][len(prefix1):])
    node1_index_drs2 = int(clause2[j][index1][len(prefix2):])
    node2_index_drs1 = int(clause1[i][index2][len(prefix1):])
    node2_index_drs2 = int(clause2[j][index2][len(prefix2):])
    node3_index_drs1 = int(clause1[i][index3][len(prefix1):])
    node3_index_drs2 = int(clause2[j][index3][len(prefix2):])

    node_pair1 = (node1_index_drs1, node1_index_drs2)
    node_pair2 = (node2_index_drs1, node2_index_drs2)
    node_pair3 = (node3_index_drs1, node3_index_drs2)

    # Check if nodes are even allowed to match, based on their type
    if var_types1[clause1[i][index1]] == var_types2[clause2[j][index1]]:
        allowed_var1 = True
    if var_types1[clause1[i][index2]] == var_types2[clause2[j][index2]]:
        allowed_var2 = True
    if var_types1[clause1[i][index3]] == var_types2[clause2[j][index3]]:
        allowed_var3 = True

    if not args.partial:
        # Usual case -- do not do partial matching
        # Check if all vars can match and if edges matches as well
        if allowed_var1 and allowed_var2 and allowed_var3 and normalize(clause1[i][edge_index]) == normalize(clause2[j][edge_index]):
            candidate_mapping[node1_index_drs1].add(node1_index_drs2)
            candidate_mapping[node2_index_drs1].add(node2_index_drs2)
            candidate_mapping[node3_index_drs1].add(node3_index_drs2)
            no_match = ''  # empty no_match for normal matching
            weight_score = 1

            # add to weight dict here, only do for 1,2 - 1,3 and 2,3
            weight_dict = add_node_pairs(node_pair1, node_pair2, node_pair3, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)
            weight_dict = add_node_pairs(node_pair2, node_pair1, node_pair3, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)
            weight_dict = add_node_pairs(node_pair3, node_pair1, node_pair2, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)
    else:
        # Do partial matching
        # Check if edge matches
        if same_edge_type_check(clause1[i][edge_index], clause2[j][edge_index]):
            same_edge_type = True
            if normalize(clause1[i][edge_index]) == normalize(clause2[j][edge_index]):
                edge_match = 1 / float(4)

        # Save mapping between the nodes only if edge is of the same type
        if same_edge_type:

            # Add match for all variables
            if allowed_var1 and allowed_var2 and allowed_var3:
                candidate_mapping[node1_index_drs1].add(node1_index_drs2)
                candidate_mapping[node2_index_drs1].add(node2_index_drs2)
                candidate_mapping[node3_index_drs1].add(node3_index_drs2)
                no_match = ''  # empty no_match because all variables already match here
                weight_score = 3 / float(4) + edge_match

                # add to weight dict here, only do for 1,2 - 1,3 and 2,3
                weight_dict = add_node_pairs(node_pair1, node_pair2, node_pair3, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)
                weight_dict = add_node_pairs(node_pair2, node_pair1, node_pair3, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)
                weight_dict = add_node_pairs(node_pair3, node_pair1, node_pair2, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)

            # Partial matches for single variable ##
            if allowed_var1:  # add partial match for single variable 1
                no_match = ((node2_index_drs1, node2_index_drs2), (node3_index_drs1, node3_index_drs2),)
                candidate_mapping[node1_index_drs1].add(node1_index_drs2)
                weight_score = 1 / float(4) + edge_match
                candidate_mapping, weight_dict = add_single_var_mapping(node1_index_drs1, node1_index_drs2, candidate_mapping, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)

            if allowed_var2:  # add partial match for single variable 2
                no_match = ((node1_index_drs1, node1_index_drs2), (node3_index_drs1, node3_index_drs2),)
                candidate_mapping[node2_index_drs1].add(node2_index_drs2)
                weight_score = 1 / float(4) + edge_match
                candidate_mapping, weight_dict = add_single_var_mapping(node2_index_drs1, node2_index_drs2, candidate_mapping, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)

            if allowed_var3:  # add partial match for single variable 3
                no_match = ((node1_index_drs1, node1_index_drs2), (node2_index_drs1, node2_index_drs2),)
                candidate_mapping[node3_index_drs1].add(node3_index_drs2)
                weight_score = 1 / float(4) + edge_match
                candidate_mapping, weight_dict = add_single_var_mapping(node3_index_drs1, node3_index_drs2, candidate_mapping, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)

            # Partial matches for two variables ##

            if allowed_var1 and allowed_var2:  # add partial match for var 1 and 2
                no_match = ((node3_index_drs1, node3_index_drs2),)
                weight_score = 2 / float(4) + edge_match
                candidate_mapping, weight_dict = add_candidate_mapping(candidate_mapping, weight_dict, weight_score, node1_index_drs1, node1_index_drs2, node2_index_drs1, node2_index_drs2, no_match, j + add_to_index, i + add_to_index2)

            if allowed_var1 and allowed_var3:  # add partial match for var 1 and 3
                no_match = ((node2_index_drs1, node2_index_drs2),)
                weight_score = 2 / float(4) + edge_match
                candidate_mapping, weight_dict = add_candidate_mapping(candidate_mapping, weight_dict, weight_score, node1_index_drs1, node1_index_drs2, node3_index_drs1, node3_index_drs2, no_match, j + add_to_index, i + add_to_index2)

            if allowed_var2 and allowed_var3:  # add partial match for var 2 and 3
                no_match = ((node1_index_drs1, node1_index_drs2),)
                weight_score = 2 / float(4) + edge_match
                candidate_mapping, weight_dict = add_candidate_mapping(candidate_mapping, weight_dict, weight_score, node2_index_drs1, node2_index_drs2, node3_index_drs1, node3_index_drs2, no_match, j + add_to_index, i + add_to_index2)

    return candidate_mapping, weight_dict


def add_candidate_mapping(candidate_mapping, weight_dict, weight_score, node1_index_drs1, node1_index_drs2, node2_index_drs1, node2_index_drs2, no_match, gold_clause_idx, prod_clause_idx):
    '''Add the candidate mapping for this node pair to the weight dict - for two variables'''

    # add mapping between two nodes
    candidate_mapping[node1_index_drs1].add(node1_index_drs2)
    candidate_mapping[node2_index_drs1].add(node2_index_drs2)
    node_pair1 = (node1_index_drs1, node1_index_drs2)
    node_pair2 = (node2_index_drs1, node2_index_drs2)
    if node_pair2 != node_pair1:

        # update weight_dict weight. Note that we need to update both entries for future search
        if node_pair1 in weight_dict:
            if node_pair2 in weight_dict[node_pair1]:
                weight_dict[node_pair1][node_pair2].append(
                    [weight_score, no_match, gold_clause_idx, prod_clause_idx])
            else:
                weight_dict[node_pair1][node_pair2] = [
                    [weight_score, no_match, gold_clause_idx, prod_clause_idx]]
        else:
            weight_dict[node_pair1] = {}
            weight_dict[node_pair1][node_pair2] = [
                [weight_score, no_match, gold_clause_idx, prod_clause_idx]]
        if node_pair2 in weight_dict:
            if node_pair1 in weight_dict[node_pair2]:
                weight_dict[node_pair2][node_pair1].append(
                    [weight_score, no_match, gold_clause_idx, prod_clause_idx])
            else:
                weight_dict[node_pair2][node_pair1] = [
                    [weight_score, no_match, gold_clause_idx, prod_clause_idx]]
        else:
            weight_dict[node_pair2] = {}
            weight_dict[node_pair2][node_pair1] = [
                [weight_score, no_match, gold_clause_idx, prod_clause_idx]]
    else:
        raise ValueError("Two nodepairs are the same, should never happen")

    return candidate_mapping, weight_dict


def same_edge_type_check(edge1, edge2):
    '''Check if two edges are of the same type (concepts, roles, operators)
       Roles: Agent, Theme
       concepts: verb
       operators: REF, EQU'''

    if edge1.isupper() and edge2.isupper():  # operator
        return True
    elif edge1[0].isupper() and edge1[1:].islower() and edge2[0].isupper() and edge2[1:].islower():  # role
        return True
    elif edge1.islower() and edge2.islower():  # concept
        return True

    return False


def map_two_vars_edges(clause1, clause2, prefix1, prefix2, edge_numbers, candidate_mapping, weight_dict, var_index1, var_index2, var_types1, var_types2, add_to_index, add_to_index2):
    '''Function that updates weight_dict and candidate mappings for clauses with 2 variable and 1 or 2 edges
       clause looks like: (var1, edge, var2) or (var1, edge, var2, "constant") or (var1, edge, "constant", var2)'''

    # Try different mappings
    for i in range(0, len(clause1)):
        for j in range(0, len(clause2)):
            # Set values to make things a bit easier
            node1_index_drs1 = int(clause1[i][var_index1][len(prefix1):])
            node1_index_drs2 = int(clause2[j][var_index1][len(prefix2):])
            node2_index_drs1 = int(clause1[i][var_index2][len(prefix1):])
            node2_index_drs2 = int(clause2[j][var_index2][len(prefix2):])

            # Set other params
            allowed_var1, allowed_var2, same_edge_type = False, False, False
            edge_match, const_match = 0, 0  # default is no match

            # First check if nodes are even allowed to match, based on the type
            # of the variables (e.g. b1 can never match to x1)
            if var_types1[clause1[i][var_index1]] == var_types2[clause2[j][var_index1]]:
                allowed_var1 = True
            if var_types1[clause1[i][var_index2]] == var_types2[clause2[j][var_index2]]:
                allowed_var2 = True

            # Then do the (partial) matching
            if not args.partial:
                # If there is more than 1 edge number, it should match, else it
                # is allowed anyway
                if len(edge_numbers) > 1:
                    if normalize(clause1[i][edge_numbers[1]]) == normalize(clause2[j][edge_numbers[1]]):
                        allowed_edge = True
                    else:
                        allowed_edge = False
                else:
                    allowed_edge = True

                # We do not do partial matching, normal case -- everything
                # should match
                if allowed_var1 and allowed_var2 and allowed_edge and normalize(clause1[i][edge_numbers[0]]) == normalize(clause2[j][edge_numbers[0]]):
                    weight_score = 1  # clause matches for 1
                    no_match = ''  # since we do not partial matching no_match is empty
                    candidate_mapping, weight_dict = add_candidate_mapping(
                        candidate_mapping, weight_dict, weight_score, node1_index_drs1, node1_index_drs2, node2_index_drs1, node2_index_drs2, no_match, j + add_to_index, i + add_to_index2)
            else:
                # Do partial matching
                # Check if edge is of the same type (e.g. both concepts, both
                # roles, both operators)
                if same_edge_type_check(clause1[i][edge_numbers[0]], clause2[j][edge_numbers[0]]):
                    same_edge_type = True
                    # Clause of the same type can always partially match, but
                    # we have to check if they share the same concept/role, if
                    # they do we add a higher value
                    if normalize(clause1[i][edge_numbers[0]]) == normalize(clause2[j][edge_numbers[0]]):
                        edge_match = 1 / float(len(clause1[0]))  # edge match results in an increase of 0.25 or 0.33

                if len(edge_numbers) > 1:  # also a constant
                    if normalize(clause1[i][edge_numbers[1]]) == normalize(clause2[j][edge_numbers[1]]):
                        const_match = 1 / float(len(clause1[0]))  # const match results in an increase of 0.25 or 0.33

                # Actually update the weight dictionary here

                if allowed_var1 and same_edge_type:  # add for single variable match

                    # Add that other node pair can not match if we do this
                    # single partial matching
                    no_match = ((int(clause1[i][var_index2][1:]), int(clause2[j][var_index2][1:])),)
                    weight_score = 1 / float(len(clause1[0])) + edge_match + const_match
                    candidate_mapping, weight_dict = add_single_var_mapping(int(clause1[i][var_index1][1:]), int(clause2[j][var_index1][1:]), candidate_mapping, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)

                if allowed_var2 and same_edge_type:  # add for single variable match
                    # Add that var1 can not match if we do this single partial matching
                    no_match = ((int(clause1[i][var_index1][1:]), int(clause2[j][var_index1][1:])),)
                    weight_score = 1 / float(len(clause1[0])) + edge_match + const_match
                    candidate_mapping, weight_dict = add_single_var_mapping(int(clause1[i][var_index2][1:]), int(clause2[j][var_index2][1:]), candidate_mapping, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)

                # Add for two variables that have to match  - no match is empty
                # since we only have two variables here
                if allowed_var1 and allowed_var1 and same_edge_type:
                    no_match = ''
                    weight_score = 2 / float(len(clause1[0])) + edge_match + const_match
                    candidate_mapping, weight_dict = add_candidate_mapping(candidate_mapping, weight_dict, weight_score, node1_index_drs1, node1_index_drs2, node2_index_drs1, node2_index_drs2, no_match, j + add_to_index, i + add_to_index2)

    return candidate_mapping, weight_dict


def add_single_var_mapping(node1_index, node2_index, candidate_mapping, weight_dict, weight_score, no_match, gold_clause_idx, prod_clause_idx):
    '''Add to the weight dictionary the result for a single variable match (e.g. x1 to x4)
       Since we might do partial matching we have a [weight_score] to add to the dictionary, between 0 and 1
       For some clauses this means that we only return the score if one other set of nodes does NOT match'''

    candidate_mapping[node1_index].add(node2_index)
    node_pair = (node1_index, node2_index)
    # use -1 as key in weight_dict for single variable mappings
    if node_pair in weight_dict:
        if -1 in weight_dict[node_pair]:
            weight_dict[node_pair][-1].append(
                [weight_score, no_match, gold_clause_idx, prod_clause_idx])
        else:
            weight_dict[node_pair][-1] = [
                [weight_score, no_match, gold_clause_idx, prod_clause_idx]]
    else:
        weight_dict[node_pair] = {}
        weight_dict[node_pair][-1] = [
            [weight_score, no_match, gold_clause_idx, prod_clause_idx]]

    return candidate_mapping, weight_dict


def compute_pool(clauses_prod, clauses_gold, prefix1, prefix2, var_count, var_types1, var_types2):
    """
    compute all possible node mapping candidates and their weights (the clause matching number gain resulting from
    mapping one node in DRS 1 to another node in DRS2)

    Arguments:
        clauses_prod: lists of lists with types of clauses
        clauses_gold: lists of lists with types of clauses
        prefix1: prefix label for DRS 1
        prefix2: prefix label for DRS 2
    Returns:
      candidate_mapping: a list of candidate nodes.
                       The ith element contains the node indices (in DRS 2) the ith node (in DRS 1) can map to.
                       (resulting in non-zero clause match)
      weight_dict: a dictionary which contains the matching clause number for every pair of node mapping. The key
                   is a node pair. The value is another dictionary. Key {-1} is clause match resulting from this node
                   pair alone, and other keys are node pairs that can result
                   in relation clause match together with the first node pair.


    """
    # Unpack lists of lists
    op_two_vars1, op_two_vars_abs1, op_three_vars1, roles_abs1, roles1, concepts1 = clauses_prod
    op_two_vars2, op_two_vars_abs2, op_three_vars2, roles_abs2, roles2, concepts2 = clauses_gold

    candidate_mapping = []
    weight_dict = {}

    for i in range(var_count):  # add as much candidate mappings as we have variables
        candidate_mapping.append(set())

    # Adding mappings for all types of clause that have two variables

    # Clause looks like (var1, OPR, var2)
    candidate_mapping, weight_dict = map_two_vars_edges(
        op_two_vars1, op_two_vars2, prefix1, prefix2, [1], candidate_mapping, weight_dict, 0, 2, var_types1, var_types2, 0, 0)
    # Clause looks like (var1, Role, var2, "item")
    candidate_mapping, weight_dict = map_two_vars_edges(roles_abs1, roles_abs2, prefix1, prefix2, [
                                                        1, 3], candidate_mapping, weight_dict, 0, 2, var_types1, var_types2, len(op_two_vars2), len(op_two_vars1))
    # Clause looks like (var1, concept, "sns", var2)
    candidate_mapping, weight_dict = map_two_vars_edges(concepts1, concepts2, prefix1, prefix2, [
                                                        1, 2], candidate_mapping, weight_dict, 0, 3, var_types1, var_types2, len(roles_abs2) + len(op_two_vars2), len(roles_abs1) + len(op_two_vars1))
    # Clause looks like (var1, OPR, var2, "item")
    candidate_mapping, weight_dict = map_two_vars_edges(op_two_vars_abs1, op_two_vars_abs2, prefix1, prefix2, [
                                                        1, 3], candidate_mapping, weight_dict, 0, 2, var_types1, var_types2, len(roles_abs2) + len(op_two_vars2) + len(concepts2), len(roles_abs1) + len(op_two_vars1) + len(concepts1))

    # Addings mapping for all types of clause that have three variables

    # Clause looks like (var1, OPR, var2, var3)
    for i in range(0, len(op_three_vars1)):
        for j in range(0, len(op_three_vars2)):
            var_index1, edge_index, var_index2, var_index3 = 0, 1, 2, 3
            candidate_mapping, weight_dict = add_candidate_mapping_three_vars(op_three_vars1, op_three_vars2, prefix1, prefix2, candidate_mapping, weight_dict, var_index1, var_index2, var_index3, edge_index, i, j, var_types1, var_types2, len(
                roles_abs2) + len(op_two_vars2) + len(concepts2) + len(op_two_vars_abs2), len(roles_abs1) + len(op_two_vars1) + len(concepts1) + len(op_two_vars_abs1))

    # Clause looks like (var1, Role, var2, var3)
    for i in range(0, len(roles1)):
        for j in range(0, len(roles2)):
            var_index1, edge_index, var_index2, var_index3 = 0, 1, 2, 3
            candidate_mapping, weight_dict = add_candidate_mapping_three_vars(roles1, roles2, prefix1, prefix2, candidate_mapping, weight_dict, var_index1, var_index2, var_index3, edge_index, i, j, var_types1, var_types2, len(
                roles_abs2) + len(op_two_vars2) + len(concepts2) + len(op_two_vars_abs2) + len(op_three_vars2), len(roles_abs1) + len(op_two_vars1) + len(concepts1) + len(op_two_vars_abs1) + len(op_three_vars1))

    return candidate_mapping, weight_dict


def add_random_mapping(result, matched_dict, candidate_mapping):
    '''If mapping is still -1 after adding a smart mapping, randomly fill in the blanks'''
    # First shuffle the way we loop over result, so that we increase the
    # randomness of the mappings
    indices = range(len(result))
    random.shuffle(indices)
    for idx in indices:
        if result[idx] == -1:  # no mapping yet
            candidates = list(candidate_mapping[idx])
            while len(candidates) > 0:
                # get a random node index from candidates
                rid = random.randint(0, len(candidates) - 1)
                if candidates[rid] in matched_dict:
                    candidates.pop(rid)
                else:
                    matched_dict[candidates[rid]] = 1
                    result[idx] = candidates[rid]
                    break
    return result


def smart_role_mapping(candidate_mapping, roles1, roles2):
    """
    Initialize mapping based on matching roles
    Arguments:
        candidate_mapping: candidate node match list
        roles1: role clauses of DRS 1 (v1 Role v2 v3)
        roles2: role clauses of DRS 2
    Returns:
        smart role mapping between two DRSs"""

    # For default mapping nothing matches
    result = [-1] * len(candidate_mapping)
    matched_dict = {}

    for role1 in roles1:
        for role2 in roles2:
            # Roles match
            if role1[1] == role2[1]:
                # Check if variables can match (using fact that we normalized them to a1, a2, etc)
                var11, var12, var13, var21, var22, var23 = int(role1[0][1:]), int(role1[2][1:]), int(
                    role1[3][1:]), int(role2[0][1:]), int(role2[2][1:]), int(role2[3][1:])
                if var21 in candidate_mapping[var11] and var22 in candidate_mapping[var12] and var23 in candidate_mapping[var13]:
                    # If so, add that to our current mapping if we didn't add
                    # it somewhere already
                    if var21 not in matched_dict:
                        result[var11] = var21
                        matched_dict[var21] = 1
                    if var22 not in matched_dict:
                        result[var12] = var22
                        matched_dict[var22] = 1
                    if var23 not in matched_dict:
                        result[var13] = var23
                        matched_dict[var23] = 1

    # Randomly fill in the blanks (-1)
    result = add_random_mapping(result, matched_dict, candidate_mapping)
    return result


def smart_concept_mapping(candidate_mapping, concepts1, concepts2):
    """
    Initialize mapping based on the concept mapping (smart initialization)
    Arguments:
        candidate_mapping: candidate node match list
        concepts1/2: list of concepts clauses: var1 concept "sense" var2
    Returns:
        smart initial mapping between two DRSs based on concepts
    """
    matched_dict = {}
    result = [-1] * len(candidate_mapping)
    for conc1 in concepts1:
        for conc2 in concepts2:
            # Check if concept and sense matches
            if conc1[1] == conc2[1] and conc1[2] == conc2[2]:
                # If so, check if variables can match
                var11, var12, var21, var22 = int(conc1[0][1:]), int(
                    conc1[3][1:]), int(conc2[0][1:]), int(conc2[3][1:])
                if var21 in candidate_mapping[var11] and var22 in candidate_mapping[var12]:
                    # Match here, so add mapping if we didn't do so before
                    if var21 not in matched_dict:
                        result[var11] = var21
                        matched_dict[var21] = 1
                    if var22 not in matched_dict:
                        result[var12] = var22
                        matched_dict[var22] = 1

    # Randomly fill in the blanks for variables that did not have a smart concept mapping
    result = add_random_mapping(result, matched_dict, candidate_mapping)

    return result


def get_best_gain(mapping, candidate_mappings, weight_dict, num_vars, match_clause_dict):
    """
    Hill-climbing method to return the best gain swap/move can get
    Arguments:
    mapping: current node mapping
    candidate_mappings: the candidates mapping list
    weight_dict: the weight dictionary
    num_vars: the number of the nodes in DRG 2
    Returns:
    the best gain we can get via swap/move operation

    """
    largest_gain = 0
    # True: using swap; False: using move
    use_swap = False
    use_move = False
    # the node to be moved/swapped
    node1 = None
    # store the other node affected. In swap, this other node is the node swapping with node1. In move, this other
    # node is the node node1 will move to.
    node2 = None
    # unmatched nodes in DRG 2
    unmatched = set(range(0, num_vars))
    # exclude nodes in current mapping
    # get unmatched nodes
    for nid in mapping:
        if nid in unmatched:
            unmatched.remove(nid)

    matches, match_clause_dict = compute_match(mapping, weight_dict, match_clause_dict)
    old_match_num = matches  #the number of matches we have for our current mapping

    ## compute move gain ##

    for i, nid in enumerate(mapping):
        # current node i in DRG 1 maps to node nid in DRG 2
        for nm in unmatched:
            if nm in candidate_mappings[i]:
                # remap i to another unmatched node (move)
                # (i, m) -> (i, nm)
                new_mapping = mapping[:]
                new_mapping[i] = nm
                ## Check if the mapping does not result in a double mapping
                if len(set([x for x in new_mapping if x != -1])) == len([x for x in new_mapping if x != -1]):
                    matches, match_clause_dict = compute_match(new_mapping, weight_dict, match_clause_dict)
                    new_match_num = matches
                    mv_gain = new_match_num - old_match_num

                    if mv_gain > largest_gain: #new best gain
                        largest_gain = mv_gain
                        node1 = i
                        node2 = nm
                        use_move = True

    ## compute swap gain ##

    for i, m in enumerate(mapping):
        for j in range(i+1, len(mapping)):
            m2 = mapping[j]
            # swap operation (i, m) (j, m2) -> (i, m2) (j, m)
            # j starts from i+1, to avoid duplicate swap

            new_mapping = mapping[:]
            new_mapping[i] = m2
            new_mapping[j] = m
            ## Check if the mapping does not result in a double mapping
            if len(set([x for x in new_mapping if x != -1])) == len([x for x in new_mapping if x != -1]):
                matches, match_clause_dict = compute_match(new_mapping, weight_dict, match_clause_dict)
                new_match_num = matches
                sw_gain = new_match_num - old_match_num

                if sw_gain > largest_gain: #new best swap gain
                    largest_gain = sw_gain
                    node1, node2 = i, j
                    use_swap = True

    # generate a new mapping based on swap/move

    cur_mapping = mapping[:]
    if node1 is not None:
        if use_swap:
            temp = cur_mapping[node1]
            cur_mapping[node1] = cur_mapping[node2]
            cur_mapping[node2] = temp
        elif use_move:
            cur_mapping[node1] = node2

    return largest_gain, cur_mapping, match_clause_dict


def compute_match(mapping, weight_dict, match_clause_dict, final=False):
    """
    Given a node mapping, compute match number based on weight_dict.
    Args:
    mappings: a list of node index in DRG 2. The ith element (value j) means node i in DRG 1 maps to node j in DRG 2.
    Returns:
    matching clause number
    Complexity: O(m*n) , m is the node number of DRG 1, n is the node number of DRG 2

    """
    if tuple(mapping) in match_clause_dict:
        return match_clause_dict[tuple(mapping)], match_clause_dict

    #we have to make sure that each produced and gold clause can only be (partially) matched once. We save that here and check
    clause_dict_gold = {}
    clause_dict_prod = {}
    clause_pairs = {}
    match_num = 0

    # i is node index in DRG 1, m is node index in DRG 2
    matched_clause_keys = {}

    for i, m in enumerate(mapping):
        if m == -1:
            # no node maps to this node
            continue
        # node i in DRG 1 maps to node m in DRG 2
        current_node_pair = (i, m)
        if current_node_pair not in weight_dict:
            continue
        for key in weight_dict[current_node_pair]:
            matched_num, matched_clause_keys, clause_dict_gold, clause_dict_prod, clause_pairs = compute_match_for_key(key, current_node_pair, weight_dict, mapping, matched_clause_keys, clause_dict_gold, clause_dict_prod, clause_pairs) #return number of matches here
            match_num += matched_num

    # update match_clause_dict
    match_clause_dict[tuple(mapping)] = match_num
    if final:
        return match_num, clause_pairs
    else:
        return match_num, match_clause_dict


def check_dict_for_adding(clause_dict_gold, clause_dict_prod, clause_pairs, match_num, item):
    '''Only add value to our score if it is a better match for this clause
       Each gold clause can only (partially) match once'''
    if item[2] in clause_dict_gold and item[3] in clause_dict_prod:
        #we already have a match for this gold clause AND produced clause, only add if this is a better match in total (and substract previous score)
        total_gain = (item[0] - clause_dict_gold[item[2]]) + (item[0] - clause_dict_prod[item[3]])
        if total_gain > 0:
            clause_dict_gold[item[2]] = item[0]
            clause_dict_prod[item[3]] = item[0]
            ## Remove and add the items from our clause pairs so that we can easily find the matching parts later
            clause_pairs[item[2], item[3]] = 1
            match_num += (float(total_gain) / 2) #divide by 2 otherwise we add double
        else: #not an improvement, do nothing
            pass
    elif item[2] in clause_dict_gold:
        #only gold item is already in our dict, so check if adding this clause instead gains us something
        if item[0] > clause_dict_gold[item[2]]:
            match_num += (item[0] - clause_dict_gold[item[2]])
            clause_dict_gold[item[2]] = item[0] #keep track of new value
            ## Remove previous gold item from clause pairs (if there) and add new one
            to_delete = []
            for key in clause_pairs:
                if key[0] == clause_dict_gold[item[2]]:
                    to_delete.append(key)
            for t in to_delete:
                del clause_pairs[t]


            clause_pairs[item[2], item[3]] = 1
        else:
            #this gold clause has already matched and this match is not an improvement, so we do nothing
            pass

    elif item[3] in clause_dict_prod:
        #only prod clause is already matched, check if adding this clause instead gains us something
        if item[0] > clause_dict_prod[item[3]]:
            match_num += (item[0] - clause_dict_prod[item[3]])
            clause_dict_prod[item[3]] = item[0] #keep track of new value

            ## Remove previous gold item from clause pairs (if there) and add new one
            to_delete = []
            for key in clause_pairs:
                if key[1] == clause_dict_prod[item[3]]:
                    to_delete.append(key)
            for t in to_delete:
                del clause_pairs[t]
            #clause_pairs[clause_dict_gold[item[2]],clause_dict_prod[item[3]]] = 1
            clause_pairs[item[2], item[3]] = 1
        else:
            pass
    else:
        #this clause hasn't matched yet, just add score and save
        match_num += item[0]
        clause_dict_gold[item[2]] = item[0]
        clause_dict_prod[item[3]] = item[0]
        clause_pairs[item[2], item[3]] = 1
    return clause_dict_gold, clause_dict_prod, clause_pairs, match_num


def get_matches(weight_dict, current_node_pair, key, mapping, clause_dict_gold, clause_dict_prod, clause_pairs):
    '''Add specific number, but make sure to only to do that if we are allowed to match (given no match)
       clause_dict_gold contains all gold clauses (by index) that already had a (partial) match
       Have to keep track of this to not match gold clauses for more than 1'''

    match_num = 0

    for item in weight_dict[current_node_pair][key]: #item looks like this [score, clause of node pairs, gold_clause_idx, prod_clause_idx] e.g. [0.75, ((2,4), (3,5)), 4, 6]
        if item[1]:                                  #sometimes no_match is empty, then just add
            add = True
            for tup in item[1]:                      #clause of clauses
                if mapping[tup[0]] == tup[1]:        #variable matches while it should not match to add score
                    add = False
            if add:
                clause_dict_gold, clause_dict_prod, clause_pairs, match_num = check_dict_for_adding(clause_dict_gold, clause_dict_prod, clause_pairs, match_num, item) #only add if this is a better match
        else:
            clause_dict_gold, clause_dict_prod, clause_pairs, match_num = check_dict_for_adding(clause_dict_gold, clause_dict_prod, clause_pairs, match_num, item)
    return match_num, clause_dict_gold, clause_dict_prod, clause_pairs


def compute_match_for_key(key, current_node_pair, weight_dict, mapping, matched_clause_keys, clause_dict_gold, clause_dict_prod, clause_pairs):
    '''Compute the matches based on the key'''
    #start with 0 and add when we find matches
    match_num = 0
    if key == -1:
        # matching clause resulting from attribute clauses
        matches, clause_dict_gold, clause_dict_prod, clause_pairs = get_matches(weight_dict, current_node_pair, key, mapping, clause_dict_gold, clause_dict_prod, clause_pairs)
        match_num += matches

    elif not any(isinstance(inst, tuple) for inst in key):  #not a list of clause but just a clause
        # key looks like this: (2,3)
        sorted_t = (key,) + (current_node_pair,)
        sorted_clause = tuple(sorted(sorted_t, key=lambda item: item[0]))

        if sorted_clause in matched_clause_keys: #already matched, don't do again - e.g. if we matched (0,0),(1,1) we don't want to also match (1,1), (0,0), because they match the same clause
            pass
        elif mapping[key[0]] == key[1]:        #variable matches, check how much we want to add
            matches, clause_dict_gold, clause_dict_prod, clause_pairs = get_matches(weight_dict, current_node_pair, key, mapping, clause_dict_gold, clause_dict_prod, clause_pairs)
            match_num += matches
            matched_clause_keys[sorted_clause] = 1
            #print current_node_pair, key, 'matches for', matches, match_num
    else:
        #clause of clauses here for clauses with 3 variables
        #key looks like this: ((2,3), (3,4), (4,7))
        sorted_t = key + (current_node_pair,)
        sorted_clause = tuple(sorted(sorted_t, key=lambda item: item[0]))
        if sorted_clause in matched_clause_keys:   #already matched, don't do again - e.g. if we matched (0,0),(1,1),(2,2) we don't want to also match (1,1), (0,0),(2,2), because they match the same clause
            pass
        else:
            if mapping[key[0][0]] == key[0][1] and mapping[key[1][0]] == key[1][1]: #both nodes also match
                matches, clause_dict_gold, clause_dict_prod, clause_pairs = get_matches(weight_dict, current_node_pair, key, mapping, clause_dict_gold, clause_dict_prod, clause_pairs)
                match_num += matches
                matched_clause_keys[sorted_clause] = 1

    return match_num, matched_clause_keys, clause_dict_gold, clause_dict_prod, clause_pairs



def compute_f(match_num, test_num, gold_num, significant, f_only):
    """
    Compute the f-score based on the matching clause number,
                                 clause number of DRS set 1,
                                 clause number of DRS set 2
    Args:
        match_num: matching clause number
        test_num:  clause number of DRS 1 (test file)
        gold_num:  clause number of DRS 2 (gold file)
    Returns:
        precision: match_num/test_num
        recall: match_num/gold_num
        f_score: 2*precision*recall/(precision+recall)
    """
    if test_num == 0 or gold_num == 0:
        if f_only:
            return 0.00
        else:
            return 0.00, 0.00, 0.00
    precision = round(float(match_num) / float(test_num), significant)
    recall = round(float(match_num) / float(gold_num), significant)
    if (precision + recall) != 0:
        f_score = round(2 * precision * recall / (precision + recall), significant)
        if veryVerbose:
            print >> DEBUG_LOG, "F-score:", f_score
        if f_only:
            return f_score
        else:
            return precision, recall, f_score
    else:
        if veryVerbose:
            print >> DEBUG_LOG, "F-score:", "0.0"
        if f_only:
            return 0.00
        else:
            return precision, recall, 0.00


def get_clauses(file_name):
    '''Function that returns a list of DRSs (that consists of clauses)'''

    clause_list = []
    original_clauses = []
    cur_orig = []
    cur_clauses = []

    with open(file_name, 'r') as in_f:
        input_lines = in_f.read().split('\n')
        for idx, line in enumerate(input_lines):
            if line.strip().startswith('%'):
                pass  # skip comments
            elif not line.strip():
                if cur_clauses:  # newline, so DRS is finished, add to list. Ignore double/clause newlines
                    clause_list.append(cur_clauses)
                    original_clauses.append(cur_orig)
                cur_clauses = []
                cur_orig = []
            else:
                try:
                    spl_line = line.split()
                    if '%' in spl_line:
                        spl_line = spl_line[0:spl_line.index('%')]

                    if len(spl_line) < 3 or len(spl_line) > 4:
                        raise ValueError(
                            'Clause incorrectly format at line {0}\nFor line: {1}\nExiting...'.format(idx, line))
                    cur_clauses.append(spl_line)
                    cur_orig.append(line)
                except:
                    raise ValueError(
                        'Clause incorrectly format at line {0}\nFor line: {1}\nExiting...'.format(idx, line))

    if cur_clauses:  # no newline at the end, still add the DRS
        clause_list.append(cur_clauses)
        original_clauses.append(cur_orig)

    # If we want to include REF clauses we are done now
    if args.include_ref:
        return clause_list, original_clauses

    # Else remove unneccessary b REF x clauses, only keep them if x never occurs
    # again in the same box
    else:
        final_clauses = []
        final_original = []
        for tup_idx, tup_set in enumerate(clause_list):
            cur_tup = []
            cur_orig = []
            for idx, spl_tup in enumerate(tup_set):
                if spl_tup[1] == 'REF':
                    if not var_occurs(tup_set, spl_tup[2], spl_tup[0], idx):  # only add if the variable does not occur afterwards
                        cur_tup.append(spl_tup)
                        cur_orig.append(original_clauses[tup_idx][idx])
                else:
                    cur_tup.append(spl_tup)
                    cur_orig.append(original_clauses[tup_idx][idx])
            final_clauses.append(cur_tup)
            final_original.append(cur_orig)
        return final_clauses, final_original


def var_occurs(clauses, var, box,  idx):
    '''Check if variable occurs with same box in one of the next clauses'''
    for cur_idx in range(0, len(clauses)):
        spl_tup = clauses[cur_idx]
        if cur_idx != idx and spl_tup[0] == box and (var == spl_tup[-1] or var == spl_tup[-2]):
            return True
    return False


def between_quotes(string):
    '''Return true if a value is between quotes'''
    return (string.startswith('"') and string.endswith('"')) or (string.startswith("'") and string.endswith("'"))


def rename_var(var, vars_seen, type_vars, prefix, var_map, var_type, idx):
    '''Function that renames the variables in a standardized way'''

    if var in vars_seen:
        new_var = prefix + str(vars_seen.index(var))
        if type_vars[new_var] != var_type:
            raise ValueError("Variable {0} was used as both a box variable and a non-box variable for clause {1}, not allowed".format(var, idx))
    else:
        new_var = prefix + str(len(vars_seen))
        type_vars[new_var] = var_type
        vars_seen.append(var)

    var_map[new_var] = var
    # print var,'got renamed to', new_var
    return new_var, vars_seen, type_vars, var_map


def all_upper(string):
    '''Checks if all items in a string are uppercase'''
    return all(x.isupper() for x in string)


def is_role(string):
    '''Check if string is in the format of a role'''
    return string[0].isupper() and any(x.islower() for x in string[1:]) and all(x.islower() or x.isupper() or x == '-' for x in string)


def add_if_not_exists(list1, list2,  idx, to_add, to_add2):
    '''Add something to two list of lists if it is not there yet in the first one'''
    if to_add not in list1[idx]:
        list1[idx].append(to_add)
        list2[idx].append(to_add2)
    return list1, list2


def add_role_clauses(cur_clause, val0, vars_seen, type_vars, prefix, var_map, idx, clause_list_all, clause_idx_list):
    '''Add clauses that have a Role as second item to our list of clauses'''

    # Second clause item is a (VerbNet) role
    if between_quotes(cur_clause[2]):
        raise ValueError(
            "Incorrectly format clause: {0}\nThird item of role clause should be a variable and not between quotes".format(cur_clause))
    else:
        # Second item in clause is a role
        val2, vars_seen, type_vars, var_map = rename_var(cur_clause[2], vars_seen, type_vars, prefix, var_map, 'x', idx)

        # If last item is between quotes it belongs in roles_abs (b0 PartOf x2
        # "speaker")
        if between_quotes(cur_clause[3]):
            new_clause = (val0, cur_clause[1], val2, cur_clause[3])
            clause_list_all, clause_idx_list = add_if_not_exists(clause_list_all, clause_idx_list, 3, new_clause, idx)
        # Otherwise it belongs in roles (b1 Patient x1 x2)
        else:
            val3, vars_seen, type_vars, var_map = rename_var(cur_clause[3], vars_seen, type_vars, prefix, var_map, 'x', idx)
            new_clause = (val0, cur_clause[1], val2, val3)
            clause_list_all, clause_idx_list = add_if_not_exists(clause_list_all, clause_idx_list, 4, new_clause, idx)
    return clause_list_all, clause_idx_list, vars_seen, type_vars, var_map


def add_operator_clauses(cur_clause, op_boxes, val0, vars_seen, type_vars, var_map, clause_list_all, clause_idx_list, prefix, idx):
    '''Add clauses that have an operator as second item to our list of close'''
    # Get var type of second variable
    var_type = 'b' if cur_clause[1] in op_boxes and cur_clause[1] != 'PRP' else 'x'

    # Get renamed variable
    val2, vars_seen, type_vars, var_map = rename_var(cur_clause[2], vars_seen, type_vars, prefix, var_map, var_type, idx)

    # If last item is between quotes it belong in op_two_vars_abs (b2 EQU t1 "now")
    if between_quotes(cur_clause[3]):
        new_clause = (val0, cur_clause[1], val2, cur_clause[3])
        clause_list_all, clause_idx_list = add_if_not_exists(clause_list_all, clause_idx_list, 1, new_clause, idx)

    # Else it belongs in op_three_vars (b1 LES x1 x2)
    else:
        var_type = 'b' if cur_clause[1] in op_boxes else 'x'
        val3, vars_seen, type_vars, var_map = rename_var(cur_clause[3], vars_seen, type_vars, prefix, var_map, var_type, idx)
        new_clause = (val0, cur_clause[1], val2, val3)
        clause_list_all, clause_idx_list = add_if_not_exists(clause_list_all, clause_idx_list, 2, new_clause, idx)

    return clause_list_all, clause_idx_list, vars_seen, type_vars, var_map


def add_concept_clauses(cur_clause, val0, vars_seen, type_vars, prefix, var_map, idx, clause_list_all, clause_idx_list):
    '''Add concepts clauses to our list of clauses'''
    if not between_quotes(cur_clause[2]):
        raise ValueError(
            "Incorrectly format clause: {0}\nThird item of concept clause should be a sense and should always be between quotes".format(cur_clause))
    elif between_quotes(cur_clause[3]):
        raise ValueError(
            "Incorrectly format clause: {0}\n Fourth item of concept clause should be a variable and not between quotes".format(cur_clause))
    else:
        val3, vars_seen, type_vars, var_map = rename_var(cur_clause[3], vars_seen, type_vars, prefix, var_map, 'x', idx)
        new_clause = (val0, cur_clause[1], cur_clause[2], val3)
        clause_list_all, clause_idx_list = add_if_not_exists(clause_list_all, clause_idx_list, 5, new_clause, idx)
    return clause_list_all, clause_idx_list, vars_seen, type_vars, var_map


def get_specific_clauses(clause_list, prefix):
    '''Function that gets the specific clauses
       Also renames them and changes their format to DRS format
       Keep track of indices so we can easily print matching DRSs later
       Different types:
            op_two_vars      : b0 REF x1
            op_two_vars_abs  : b2 EQU t1 "now"
            op_three_vars    : b1 LES x1 x2
            roles_abs        : b0 PartOf x2 "speaker"
            roles            : b0 Patient x1 x2
            concepts         : b1 work "v.01" x2'''

    # Save all types of clauses in a list, contains: op_two_vars,
    # op_two_vars_abs, op_three_vars, roles_abs, roles, concepts
    clause_list_all = [[], [], [], [], [], []]

    # Order: op_two_vars, op_two_vars_abs, op_three_vars, roles_abs, roles,
    # concepts
    clause_idx_list = [[], [], [], [], [], []]

    # Keep track of variable information
    vars_seen = []
    type_vars = {}
    var_map = {}

    # Operators that have two box variables
    op_boxes = ['NOT', 'POS', 'NEC', 'IMP', 'DIS', 'PRP', 'DRS',
                'PARALLEL', 'CONTINUATION', 'CONTRAST']
    for idx, cur_clause in enumerate(clause_list):
        # Clause has three items and belongs in op_two_vars (b0 REF x1 ,  b0 NOT b1)
        # print cur_clause
        if len(cur_clause) == 3:
            if between_quotes(cur_clause[2]) or between_quotes(cur_clause[2]) or not cur_clause[0].islower() or not cur_clause[2].islower():
                raise ValueError(
                    "Incorrectly format clause: {0}\nClauses of length three should always contain two variables".format(cur_clause))
            else:
                val0, vars_seen, type_vars, var_map = rename_var(cur_clause[0], vars_seen, type_vars, prefix, var_map, 'b', idx)
                var_type = 'b' if cur_clause[1] in op_boxes else 'x'
                val2, vars_seen, type_vars, var_map = rename_var(cur_clause[2], vars_seen, type_vars, prefix, var_map, var_type, idx)
                new_clause = (val0, cur_clause[1], val2)
                clause_list_all, clause_idx_list = add_if_not_exists(clause_list_all, clause_idx_list, 0, new_clause, idx)

        # Clause has 4 items
        else:
            # First item always is a box variable
            if between_quotes(cur_clause[0]):  # or between_quotes(cur_clause[1]):
                raise ValueError(
                    "Incorrectly format clause: {0}\n".format(cur_clause))
            else:
                val0, vars_seen, type_vars, var_map = rename_var(
                    cur_clause[0], vars_seen, type_vars, prefix, var_map, 'b', idx)

                # Second item is an operator
                if all_upper(cur_clause[1]):
                    clause_list_all, clause_idx_list, vars_seen, type_vars, var_map = add_operator_clauses(
                        cur_clause, op_boxes, val0, vars_seen, type_vars, var_map, clause_list_all, clause_idx_list, prefix, idx)

                # Second item is a role
                elif is_role(cur_clause[1]):
                    clause_list_all, clause_idx_list, vars_seen, type_vars, var_map = add_role_clauses(
                        cur_clause, val0, vars_seen, type_vars, prefix, var_map, idx, clause_list_all, clause_idx_list)

                # Otherwise it must be a concept (b1 work "v.01" x2)
                else:
                    clause_list_all, clause_idx_list, vars_seen, type_vars, var_map = add_concept_clauses(
                        cur_clause, val0, vars_seen, type_vars, prefix, var_map, idx, clause_list_all, clause_idx_list)

    # Flatten indices list and return
    indices_original = [
        item for sublist in clause_idx_list for item in sublist]
    return clause_list_all, len(vars_seen), type_vars, var_map, indices_original


def fill_baseline_list(baseline_drs, clauses_gold_list):
    '''Fill baseline drss so that we can compare all DRSs to a baseline'''
    return [baseline_drs for _ in range(len(clauses_gold_list))]


def create_tab_list(print_rows, print_item):
    '''For multiple rows, return row of strings nicely separated by tabs'''
    col_widths = []
    return_rows = [print_item]
    if print_rows:
        for idx in range(len(print_rows[0])):  # for nice printing, calculate max column length
            col_widths.append(max([len(x[idx].decode('utf-8')) for x in print_rows]) + 1)

        for idx, row in enumerate(print_rows):  # print rows here, adjusted for column width
            return_rows.append("| ".join(word.decode('utf-8').ljust(col_widths[col_idx]) for col_idx, word in enumerate(row)))
    return return_rows


def print_mappings(clause_pairs, indices_prod, indices_gold, original_prod, original_gold, prod_clause_num, gold_clause_num, prec, rec, significant):
    '''Output the matching and non-matching clauses'''

    match = []
    no_match = []

    orig_prod_idx_match = []
    orig_gold_idx_match = []
    # First get all matches and order them based on gold occurence
    ordered_clauses = [[indices_prod[idx1], indices_gold[idx2]] for idx1, idx2 in clause_pairs]

    for idx_prod, idx_gold in sorted(ordered_clauses, key=lambda x: x[1]):
        match.append([original_prod[idx_prod], original_gold[idx_gold]])
        orig_prod_idx_match.append(idx_prod)
        orig_gold_idx_match.append(idx_gold)

    # Get which indices match and do no match (do sorted for no match so that
    # we have some kind of order still)
    no_match_prod = sorted([x for x in range(len(original_prod)) if x not in orig_prod_idx_match])
    no_match_gold = sorted([x for x in range(len(original_gold)) if x not in orig_gold_idx_match])

    # Populate the no match part of what we will print later (is a bit
    # cumbersome because we want aligned printing later)
    for num in no_match_prod:
        no_match.append([original_prod[num], ''])

    for num in no_match_gold:
        found = False
        for no_match_item in no_match:
            if no_match_item[1] == '':  # there is still space to add
                no_match_item[1] = original_gold[num]
                found = True
                break
        if not found:  # no space to add, create new row
            no_match.append(['', original_gold[num]])

    # Check if results make sense compared to our previous result
    print_prec = round(len(match) / float(prod_clause_num), significant)
    print_rec = round(len(match) / float(gold_clause_num), significant)

    if print_prec != prec or print_rec != rec:
        raise ValueError(
            "Error when calculating precision/recall for printing clauses:\nPrint prec {0} vs search prec {1}\nPrint rec {0} vs search rec {1}\n".format(print_prec, prec, print_rec, rec))

    # Print to screen and possibly to file
    print_match = create_tab_list(match, '\nMatching clauses:\n')
    print_no_match = create_tab_list(no_match, '\nNon-matching clauses:\n')

    # Ultimately print to screen
    for print_line in print_match:
        print print_line
    for print_line in print_no_match:
        print print_line


def get_matching_clauses(arg_list):
    '''Function that gets matching clauses (easier to parallelize)'''
    start_time = time.time()
    prod_t, gold_t, args, prefix1, prefix2, significant, prin, single, smart, restarts, max_clauses, memory_limit, counter, original_prod, original_gold = arg_list  # unpack argument list
    clauses_prod, var_count1, var_types1, var_map_prod, indices_prod = get_specific_clauses(prod_t, prefix1)        # prefixes are used to create standardized variable-names
    clauses_gold, var_count2, var_types2, var_map_gold, indices_gold = get_specific_clauses(gold_t, prefix2)

    test_clause_num = sum([len(x) for x in clauses_prod])
    gold_clause_num = sum([len(x) for x in clauses_gold])

    if single and (args.max_clauses > 0 and ((test_clause_num > args.max_clauses) or (gold_clause_num > args.max_clauses))):
        print 'Skip calculation of DRS, clauses longer than max of {0}'.format(args.max_clauses)
        return []


    (best_mapping, best_match_num, found_idx, restarts_done, avg_f, smart_fscores, clause_pairs, num_maps, cur_best_matches) = get_best_match(clauses_prod, clauses_gold,
                                                                                                                                              prefix1, prefix2, var_count1, var_types1, var_types2, var_map_prod, var_map_gold, prin, single, significant, memory_limit, counter)
    if len(set([x for x in best_mapping if x != -1])) != len([x for x in best_mapping if x != -1]):
        raise ValueError(
            "Variable maps to two other variables, not allowed -- {0}".format(best_mapping))

    if verbose:
        print >> DEBUG_LOG, "best match number", best_match_num
        print >> DEBUG_LOG, "best node mapping", best_mapping

    (precision, recall, best_f_score) = compute_f(best_match_num, test_clause_num, gold_clause_num, significant, False)

    # Print clause mapping if -prin is used and we either do multiple scores, or just had a single DRS
    if prin and (args.ms or single) and not args.no_mapping:
        print_mappings(
            clause_pairs, indices_prod, indices_gold, original_prod, original_gold,
            test_clause_num, gold_clause_num, precision, recall, significant)

    # For single DRS we print results later on anyway
    if args.ms and not single:
        print_results([[best_match_num, test_clause_num, gold_clause_num, smart_fscores, avg_f, restarts_done, found_idx, var_count1, num_maps]],
            start_time, prin, smart, restarts, significant, max_clauses, single)

    return [best_match_num, test_clause_num, gold_clause_num, smart_fscores, avg_f, restarts_done, found_idx, var_count1, num_maps, cur_best_matches]


def print_results(res_list, start_time, prin, smart, restarts, significant, max_clauses, single):
    '''Print the final or inbetween scores -- res_list has format [[best_match_num, test_clause_num, total_gold_num, smart_fscores, avg_f, restarts_done, found_idx]]'''

    # Calculate average scores
    total_match_num = sum([x[0] for x in res_list if x])
    total_test_num = sum([x[1] for x in res_list if x])
    total_gold_num = sum([x[2] for x in res_list if x])
    avg_f = round(float(sum([x[4] for x in res_list if x])) / float(
        len([x[4] for x in res_list if x])), significant)
    restarts_done = round(float(sum([x[8] for x in res_list if x])) / float(
        len([x[8] for x in res_list if x])), significant)
    found_idx = round(float(sum([x[6] for x in res_list if x])) / float(
        len([x[6] for x in res_list if x])), significant)
    runtime = round(time.time() - start_time, significant)

    if verbose:
        print >> DEBUG_LOG, "Total match number, total clause number in DRS 1, and total clause number in DRS 2:"
        print >> DEBUG_LOG, total_match_num, total_test_num, total_gold_num
        print >> DEBUG_LOG, "---------------------------------------------------------------------------------"

    # Output document-level score (a single f-score for all DRS pairs in two files)

    (precision, recall, best_f_score) = compute_f(total_match_num,
                                                  total_test_num, total_gold_num, significant, False)
    if not res_list:
        return []  # no results for some reason
    else:
        print '\n## Clause information ##\n'
        print 'Clauses prod : {0}'.format(total_test_num)
        print 'Clauses gold : {0}\n'.format(total_gold_num)
        if max_clauses > 0:
            print 'Max number of clauses per DRS:  {0}\n'.format(max_clauses)
        print '## Main Results ##\n'
        if not single:
            print 'All shown number are averages calculated over {0} DRS-pairs\n'.format(len(res_list))
        print 'Matching clauses: {0}\n'.format(total_match_num)
        if pr_flag:
            print "Precision: {0}".format(round(precision, significant))
            print "Recall   : {0}".format(round(recall, significant))
            print "F-score  : {0}".format(round(best_f_score, significant))
        else:
            if best_f_score > 1:
                raise ValueError(
                    "F-score larger than 1: {0}".format(best_f_score))
            print "F-score  : {0}".format(round(best_f_score, significant))

        if prin:  # print specific output here

            print '\n## Detailed F-scores ##\n'

            if smart != 'no':
                smart_first = compute_f(sum([y[0] for y in [x[3] for x in res_list]]), total_test_num, total_gold_num, significant, True)

            if smart == 'all':
                smart_role = compute_f(sum([y[0] for y in [x[3] for x in res_list]]), total_test_num, total_gold_num, significant, True)
                smart_conc = compute_f(sum([y[1] for y in [x[3] for x in res_list]]), total_test_num, total_gold_num, significant, True)

                print 'Smart F-score roles          : {0}'.format(smart_role)
                print 'Smart F-score concepts       : {0}'.format(smart_conc)
            elif smart == 'role':
                print 'Smart role F-score: {0}'.format(smart_first)
            elif smart == 'conc':
                print 'Smart F-score concepts: {0}'.format(smart_first)
            elif smart == 'all':
                smart_role = compute_f(sum([y[0] for y in [x[3] for x in res_list]]), total_test_num, total_gold_num, significant, True)
                smart_conc = compute_f(sum([y[1] for y in [x[3] for x in res_list]]), total_test_num, total_gold_num, significant, True)
                print 'Smart F-score concepts       : {0}'.format(smart_conc)
                print 'Smart F-score roles          : {0}'.format(smart_role)

            if single:  # averaging does not make for multiple DRSs
                print 'Avg F-score over all restarts: {0}'.format(avg_f)

            print '\n## Restarts and processing time ##\n'

            print 'Num restarts specified       : {0}'.format(restarts)
            print 'Num restarts performed       : {0}'.format(restarts_done)
            print 'Found best mapping at restart: {0}'.format(int(found_idx))
    print 'Total processing time        : {0} sec'.format(runtime)

    return [precision, recall, best_f_score]


def main(arguments):
    """
    Main function of counter score calculation

    """
    global verbose
    global veryVerbose
    global single_score
    global pr_flag

    start = time.time()

    if arguments.ms:
        single_score = False
    if arguments.v:
        verbose = True
    if arguments.vv:
        veryVerbose = True
    if arguments.pr:
        pr_flag = True

    # Set initial values
    prefix1 = 'a'
    prefix2 = 'b'

    # Get the clauses
    clauses_prod_list, original_prod = get_clauses(args.f1)
    clauses_gold_list, original_gold = get_clauses(args.f2)

    single = True if len(clauses_gold_list) == 1 else False  # true if we are doing a single DRS

    # Check if correct input
    if args.baseline:  # if we try a baseline DRS, we have to fill a list of this baseline
        if len(clauses_prod_list) == 1:
            print 'Testing baseline DRS vs {0} DRSs...\n'.format(len(clauses_gold_list))
            clauses_prod_list = fill_baseline_list(clauses_prod_list[0], clauses_gold_list)
            original_prod = fill_baseline_list(original_prod[0], original_gold)
        else:
            raise ValueError(
                "Using --baseline, but there is more than 1 DRS in prod file")
    elif len(clauses_prod_list) != len(clauses_gold_list):
        print "Number of DRSs not equal, {0} vs {1}, exiting...".format(len(clauses_prod_list), len(clauses_gold_list))
        sys.exit(0)
    elif len(clauses_prod_list) == 0 and len(clauses_gold_list) == 0:
        print "Both DRSs empty, exiting..."
        sys.exit(0)
    elif not single:
        print 'Comparing {0} DRSs...\n'.format(len(clauses_gold_list))

    if args.max_clauses > 0 and not single:  # print number of DRSs we skip due to the -max_clauses parameter
        print 'Skipping {0} DRSs due to their length exceeding {1} (--max_clauses)\n'.format(len([x for x, y in zip(clauses_gold_list, clauses_prod_list) if len(x) > args.max_clauses or len(y) > args.max_clauses]), args.max_clauses)

    # Processing clauses
    all_results = []
    arg_list = []
    counter = 0
    for prod_t, gold_t in zip(clauses_prod_list, clauses_gold_list):
        arg_list.append([prod_t, gold_t, args, prefix1, prefix2, args.significant, args.prin, single, args.smart,
             args.restarts, args.max_clauses, args.mem_limit, counter, original_prod[counter], original_gold[counter]])
        counter += 1

    # Parallel processing here
    if args.parallel == 1:  # no need for parallelization for p=1
        all_results = []
        for arguments in arg_list:
            all_results.append(get_matching_clauses(arguments))
    else:
        all_results = multiprocessing.Pool(args.parallel).map(get_matching_clauses, arg_list)

    # If we find results, print them in a nice way
    if all_results:
        print_results(all_results, start, args.prin, args.smart, args.restarts, args.significant, args.max_clauses, single)
    else:
        print 'No results found, exiting..'
        sys.exit(0)



# verbose output switch.
# Default false (no verbose output)
verbose = False
veryVerbose = False

# single score output switch.
# Default true (compute a single score for all DRSs in two files)
single_score = True

# precision and recall output switch.
# Default false (do not output precision and recall, just output F score)
pr_flag = False

# Error log location
ERROR_LOG = sys.stderr

# Debug log location
DEBUG_LOG = sys.stderr

if __name__ == "__main__":
    args = build_arg_parser()
    main(args)
