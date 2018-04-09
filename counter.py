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
-s    : What kind of smart initial mapping we use:
	  -no    No smart mappings
	  -conc  Smart mapping based on matching concepts (their match is likely to be in the optimal mapping)
-prin : Print more specific output, such as individual (average) F-scores for the smart initial mappings, and the matching and non-matching clauses
-sig  : Number of significant digits to output (default 4)
-b    : Use this for baseline experiments, comparing a single DRS to a list of DRSs. Produced DRS file should contain a single DRS.
-ms   : Instead of averaging the score, output a score for each DRS
-msf  : The file we write the individual F-score predictions to, makes it easier to do statistics
-pr   : Also output precison and recall
-pa   : Partial matching of clauses instead of full matching -- experimental setting!
		Means that the clauses x1 work "n.01" x2 and x1 run "n.01" x2 are able to match for 0.75, for example
-ic   : Include REF clauses when matching (otherwise they are ignored because they inflate the matching)
-v    : Verbose output
-vv   : Very verbose output
"""

import os
import random
import time
import argparse
import re
import sys
import multiprocessing
from multiprocessing import Pool
import json #reading in dict
from numpy import median
reload(sys)
sys.setdefaultencoding('utf-8')  # necessary to avoid unicode errors
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
	parser.add_argument('-s', '--smart', default='conc', action='store', choices=[
						'no', 'conc'], help='What kind of smart mapping do we use (default concepts)')
	parser.add_argument('-prin', action='store_true',
						help='Print very specific output - matching and non-matching clauses and specific F-scores for smart mappings')
	parser.add_argument('-r', '--restarts', type=int,
						default=20, help='Restart number (default: 20)')
	parser.add_argument('-es', '--en_sense_dict', type=str,
						default='en_sense_dict.json', help='Location of English sense dictionary')					
	parser.add_argument('-sig', '--significant', type=int,
						default=4, help='significant digits to output (default: 4)')
	parser.add_argument('-mem', '--mem_limit', type=int, default=1000,
						help='Memory limit in MBs (default 1000 -> 1G). Note that this is per parallel thread! If you use -par 4, each thread gets 1000 MB with default settings.')
	parser.add_argument('-b', '--baseline', action='store_true', default=False,
						help="Helps in deciding a good baseline DRS. If added, prod-file must be a single DRS, gold file a number of DRSs to compare to (default false)")
	parser.add_argument('-ms', action='store_true', default=False,
						help='Output multiple scores (one pair per score) instead of a single document-level score (Default: false)')
	parser.add_argument('-msf', '--ms_file', default = '',
						help='The file where we print the individual scores per DRS to -- one score per line (float) -- default empty means do not print to file')
	parser.add_argument('-pr', action='store_true', default=False,
						help="Output precision and recall as well as the f-score. Default: false")
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


def load_json_dict(d):
    '''Funcion that loads json dictionaries'''
    
    with open(d, 'r') as in_f:  
        dic = json.load(in_f)
    in_f.close()
    return dic


def get_memory_usage():
	'''return the memory usage in MB'''
	process = psutil.Process(os.getpid())
	mem = process.memory_info()[0] / float(1000000)
	return mem


def write_to_file(lst, file_name):
	'''Write a list to file with newline after each item'''
	print_l = [l.encode('utf-8') for l in lst]
	out_file = codecs.open(file_name, "w", "utf-8")
	for item in print_l:
		out_file.write(item + '\n')


def get_best_match(prod_drs, gold_drs, args, single):
	"""
	Get the highest clause match number between two sets of clauses via hill-climbing.
	Arguments:
		prod_drs: Object with all information of the produced DRS
		gold_Drs: Object with all information of the gold DRS
		args: command line argparse arguments
		single: whether this is the only DRS we do
	Returns:
		best_match: the node mapping that results in the highest clause matching number
		best_match_num: the highest clause matching number

	"""

	# Compute candidate pool - all possible node match candidates.
	# In the hill-climbing, we only consider candidate in this pool to save computing time.
	# weight_dict is a dictionary that maps a pair of node
	(candidate_mappings, weight_dict) = compute_pool(prod_drs, gold_drs)

	# Save mapping and number of matches so that we don't have to calculate stuff twice
	match_clause_dict = {}

	# Set intitial values
	best_match_num = 0
	best_mapping = [-1] * len(prod_drs.var_map)
	found_idx = 0

	# Find smart mappings first, if specified
	if args.smart == 'conc':
		smart_conc = smart_concept_mapping(candidate_mappings, prod_drs.concepts, gold_drs.concepts)
		matches, match_clause_dict = compute_match(smart_conc, weight_dict, match_clause_dict)
		smart_mappings = [[smart_conc, matches]]
		smart_fscores = [0]
	else:
		smart_mappings = []
		smart_fscores  = []

	# Then add random mappings
	mapping_order = smart_mappings + get_mapping_list(candidate_mappings, weight_dict, args.restarts - len(smart_fscores), match_clause_dict)
	# Set initial values
	done_mappings = {}

	# Loop over the mappings to find the best score
	for i, map_cur in enumerate(mapping_order):  # number of restarts is number of mappings
		cur_mapping = map_cur[0]
		match_num = map_cur[1]
		num_vars = len(gold_drs.var_map)
		if veryVerbose:
			print >> DEBUG_LOG, "Node mapping at start", cur_mapping
			print >> DEBUG_LOG, "Clause match number at start:", match_num

		if tuple(cur_mapping) in done_mappings:
			match_num = done_mappings[tuple(cur_mapping)]
		else:
			# Do hill-climbing until there will be no gain for new node mapping
			while True:
				# get best gain
				(gain, new_mapping, match_clause_dict) = get_best_gain(cur_mapping, candidate_mappings, weight_dict, num_vars, match_clause_dict)

				if veryVerbose:
					print >> DEBUG_LOG, "Gain after the hill-climbing", gain

				if match_num + gain > prod_drs.total_clauses:
					print new_mapping, match_num + gain, prod_drs.total_clauses
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
			if get_memory_usage() > args.mem_limit:
				match_clause_dict.clear()

		# If we have matched as much we can (precision 1.0), we might as well
		# stop instead of doing all other restarts - but always do smart
		# mappings
		if match_num == prod_drs.total_clauses and i > len(smart_fscores) - 1:
			if args.prin and single:
				print 'Best match already found, stop restarts at restart {0}'.format(i)
			if i < len(smart_fscores):
				smart_fscores[i] = match_num
			break

		# Add smart F-scores
		if i < len(smart_fscores):  # are we still adding smart F-scores?
			smart_fscores[i] = match_num

	_, clause_pairs = compute_match(best_mapping, weight_dict, {}, final=True)

	# Clear matches out of memory
	match_clause_dict.clear()

	return best_mapping, best_match_num, found_idx, smart_fscores, clause_pairs,


def add_random_mapping(result, matched_dict, candidate_mapping):
	'''If mapping is still -1 after adding a smart mapping, randomly fill in the blanks'''
	# First shuffle the way we loop over result, so that we increase the randomness of the mappings
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

	# only do random mappings we haven't done before, but if we have 50 duplicates in a row, we are probably done with all mappings
	while len(random_maps) < map_ceil and count_duplicate <= 50:
		cur_mapping = add_random_mapping([-1 for x in candidate_mappings], {}, candidate_mappings)
		match_num, match_clause_dict = compute_match(cur_mapping, weight_dict, match_clause_dict)
		if [cur_mapping, match_num] not in random_maps and len(set([x for x in cur_mapping if x != -1])) == len([x for x in cur_mapping if x != -1]):
			random_maps.append([cur_mapping, match_num])
			count_duplicate = 0
		else:
			count_duplicate += 1
	return random_maps


def normalize(item):
	'''We do not normalize anymore, but we might add something here'''
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


def add_candidate_mapping_three_vars(prod_clauses, gold_clauses, prod_drs, gold_drs, candidate_mapping, weight_dict, i, j, add_to_index, add_to_index2):
	'''Add the candidate mapping for this node pair to the weight dict - for three variables
	   It is possible to do partial matching, but the usual case only does full matching'''

	# Set initial variables
	index1, index2, index3, edge_index = 0, 2, 3, 1
	allowed_var1, allowed_var2, allowed_var3, same_edge_type = False, False, False, False
	edge_match = 0

	# Set values to make things a bit clearer
	node1_index_drs1 = int(prod_clauses[i][index1][len(prod_drs.prefix):])
	node1_index_drs2 = int(gold_clauses[j][index1][len(gold_drs.prefix):])
	node2_index_drs1 = int(prod_clauses[i][index2][len(prod_drs.prefix):])
	node2_index_drs2 = int(gold_clauses[j][index2][len(gold_drs.prefix):])
	node3_index_drs1 = int(prod_clauses[i][index3][len(prod_drs.prefix):])
	node3_index_drs2 = int(gold_clauses[j][index3][len(gold_drs.prefix):])

	node_pair1 = (node1_index_drs1, node1_index_drs2)
	node_pair2 = (node2_index_drs1, node2_index_drs2)
	node_pair3 = (node3_index_drs1, node3_index_drs2)

	# Check if nodes are even allowed to match, based on their type
	if prod_drs.type_vars[prod_clauses[i][index1]] == gold_drs.type_vars[gold_clauses[j][index1]]:
		allowed_var1 = True
	if prod_drs.type_vars[prod_clauses[i][index2]] == gold_drs.type_vars[gold_clauses[j][index2]]:
		allowed_var2 = True
	if prod_drs.type_vars[prod_clauses[i][index3]] == gold_drs.type_vars[gold_clauses[j][index3]]:
		allowed_var3 = True

	if not args.partial:
		# Usual case -- do not do partial matching
		# Check if all vars can match and if edges matches as well
		if allowed_var1 and allowed_var2 and allowed_var3 and normalize(prod_clauses[i][edge_index]) == normalize(gold_clauses[j][edge_index]):
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
		if same_edge_type_check(prod_clauses[i][edge_index], gold_clauses[j][edge_index]):
			same_edge_type = True
			if normalize(prod_clauses[i][edge_index]) == normalize(gold_clauses[j][edge_index]):
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
				candidate_mapping, weight_dict = add_single_var_mapping(node1_index_drs1, node1_index_drs2,
					candidate_mapping, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)

			if allowed_var2:  # add partial match for single variable 2
				no_match = ((node1_index_drs1, node1_index_drs2), (node3_index_drs1, node3_index_drs2),)
				candidate_mapping[node2_index_drs1].add(node2_index_drs2)
				weight_score = 1 / float(4) + edge_match
				candidate_mapping, weight_dict = add_single_var_mapping(node2_index_drs1, node2_index_drs2,
					candidate_mapping, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)

			if allowed_var3:  # add partial match for single variable 3
				no_match = ((node1_index_drs1, node1_index_drs2), (node2_index_drs1, node2_index_drs2),)
				candidate_mapping[node3_index_drs1].add(node3_index_drs2)
				weight_score = 1 / float(4) + edge_match
				candidate_mapping, weight_dict = add_single_var_mapping(node3_index_drs1, node3_index_drs2,
					candidate_mapping, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)

			# Partial matches for two variables ##

			if allowed_var1 and allowed_var2:  # add partial match for var 1 and 2
				no_match = ((node3_index_drs1, node3_index_drs2),)
				weight_score = 2 / float(4) + edge_match
				candidate_mapping, weight_dict = add_candidate_mapping(candidate_mapping, weight_dict, weight_score, node1_index_drs1,
													node1_index_drs2, node2_index_drs1, node2_index_drs2, no_match, j + add_to_index, i + add_to_index2)

			if allowed_var1 and allowed_var3:  # add partial match for var 1 and 3
				no_match = ((node2_index_drs1, node2_index_drs2),)
				weight_score = 2 / float(4) + edge_match
				candidate_mapping, weight_dict = add_candidate_mapping(candidate_mapping, weight_dict, weight_score, node1_index_drs1,
													node1_index_drs2, node3_index_drs1, node3_index_drs2, no_match, j + add_to_index, i + add_to_index2)

			if allowed_var2 and allowed_var3:  # add partial match for var 2 and 3
				no_match = ((node1_index_drs1, node1_index_drs2),)
				weight_score = 2 / float(4) + edge_match
				candidate_mapping, weight_dict = add_candidate_mapping(candidate_mapping, weight_dict, weight_score, node2_index_drs1,
													node2_index_drs2, node3_index_drs1, node3_index_drs2, no_match, j + add_to_index, i + add_to_index2)

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


def map_two_vars_edges(clauses_prod, clauses_gold, prod_drs, gold_drs, edge_numbers, candidate_mapping, weight_dict, var_index1, var_index2, add_to_index, add_to_index2):
	'''Function that updates weight_dict and candidate mappings for clauses with 2 variable and 1 or 2 edges
	   clause looks like: (var1, edge, var2) or (var1, edge, var2, "constant") or (var1, edge, "constant", var2)'''

	# Make things a bit more readable
	prefix1 = prod_drs.prefix
	prefix2 = gold_drs.prefix

	# Try different mappings
	for i in range(0, len(clauses_prod)):
		for j in range(0, len(clauses_gold)):
			# Set values to make things a bit easier
			node1_index_drs1 = int(clauses_prod[i][var_index1][len(prefix1):])
			node1_index_drs2 = int(clauses_gold[j][var_index1][len(prefix2):])
			node2_index_drs1 = int(clauses_prod[i][var_index2][len(prefix1):])
			node2_index_drs2 = int(clauses_gold[j][var_index2][len(prefix2):])

			# Set other params
			allowed_var1, allowed_var2, same_edge_type = False, False, False
			edge_match, const_match = 0, 0  # default is no match

			# First check if nodes are even allowed to match, based on the type
			# of the variables (e.g. b1 can never match to x1)
			if prod_drs.type_vars[clauses_prod[i][var_index1]] == gold_drs.type_vars[clauses_gold[j][var_index1]]:
				allowed_var1 = True
			if prod_drs.type_vars[clauses_prod[i][var_index2]] == gold_drs.type_vars[clauses_gold[j][var_index2]]:
				allowed_var2 = True

			# Then do the (partial) matching
			if not args.partial:
				# If there is more than 1 edge number, it should match, else it is allowed anyway
				if len(edge_numbers) > 1 and not normalize(clauses_prod[i][edge_numbers[1]]) == normalize(clauses_gold[j][edge_numbers[1]]):
					allowed_edge = False
				else:
					allowed_edge = True

				# We do not do partial matching, normal case -- everything should match
				if allowed_var1 and allowed_var2 and allowed_edge and normalize(clauses_prod[i][edge_numbers[0]]) == normalize(clauses_gold[j][edge_numbers[0]]):
					weight_score = 1    # clause matches for 1
					no_match = ''       # since we do not partial matching no_match is empty
					candidate_mapping, weight_dict = add_candidate_mapping(candidate_mapping, weight_dict, weight_score, node1_index_drs1, node1_index_drs2,
																			node2_index_drs1, node2_index_drs2, no_match, j + add_to_index, i + add_to_index2)
			else:
				# Do partial matching
				# Check if edge is of the same type (e.g. both concepts, both roles, both operators)
				if same_edge_type_check(clauses_prod[i][edge_numbers[0]], clauses_gold[j][edge_numbers[0]]):
					same_edge_type = True
					# Clause of the same type can always partially match, but
					# we have to check if they share the same concept/role, if
					# they do we add a higher value
					if normalize(clauses_prod[i][edge_numbers[0]]) == normalize(clauses_gold[j][edge_numbers[0]]):
						edge_match = 1 / float(len(clauses_prod[0]))  # edge match results in an increase of 0.25 or 0.33

				if len(edge_numbers) > 1:  # also a constant
					if normalize(clauses_prod[i][edge_numbers[1]]) == normalize(clauses_gold[j][edge_numbers[1]]):
						const_match = 1 / float(len(clauses_prod[0]))  # const match results in an increase of 0.25 or 0.33

				# Actually update the weight dictionary here
				if allowed_var1 and same_edge_type:  # add for single variable match

					# Add that other node pair can not match if we do this
					# single partial matching
					no_match = ((int(clauses_prod[i][var_index2][1:]), int(clauses_gold[j][var_index2][1:])),)
					weight_score = 1 / float(len(clauses_prod[0])) + edge_match + const_match
					candidate_mapping, weight_dict = add_single_var_mapping(int(clauses_prod[i][var_index1][1:]), int(clauses_gold[j][var_index1][1:]), candidate_mapping, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)

				if allowed_var2 and same_edge_type:  # add for single variable match
					# Add that var1 can not match if we do this single partial matching
					no_match = ((int(clauses_prod[i][var_index1][1:]), int(clauses_gold[j][var_index1][1:])),)
					weight_score = 1 / float(len(clauses_prod[0])) + edge_match + const_match
					candidate_mapping, weight_dict = add_single_var_mapping(int(clauses_prod[i][var_index2][1:]), int(clauses_gold[j][var_index2][1:]), candidate_mapping, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)

				# Add for two variables that have to match  - no match is empty
				# since we only have two variables here
				if allowed_var1 and allowed_var1 and same_edge_type:
					no_match = ''
					weight_score = 2 / float(len(clauses_prod[0])) + edge_match + const_match
					candidate_mapping, weight_dict = add_candidate_mapping(candidate_mapping, weight_dict, weight_score, node1_index_drs1, node1_index_drs2, node2_index_drs1, node2_index_drs2, no_match, j + add_to_index, i + add_to_index2)

	return candidate_mapping, weight_dict


def compute_pool(prod_drs, gold_drs):
	"""
	compute all possible node mapping candidates and their weights (the clause matching number gain resulting from
	mapping one node in DRS 1 to another node in DRS2)

	Arguments:
		prod_drs: Object with all information of the produced DRS
		gold_drs: Object with all informtation of the gold DRS
	Returns:
	  candidate_mapping: a list of candidate nodes.
					   The ith element contains the node indices (in DRS 2) the ith node (in DRS 1) can map to.
					   (resulting in non-zero clause match)
	  weight_dict: a dictionary which contains the matching clause number for every pair of node mapping. The key
				   is a node pair. The value is another dictionary. Key {-1} is clause match resulting from this node
				   pair alone, and other keys are node pairs that can result
				   in relation clause match together with the first node pair.


	"""
	candidate_mapping = []
	weight_dict = {}

	# Add as much candidate mappings as we have variables
	for i in range(len(prod_drs.var_map)):
		candidate_mapping.append(set())

	# Adding mappings for all types of clause that have two variables
	# Clause looks like (var1, OPR, var2)
	var_spot1, var_spot2, count_clauses_prod, count_clauses_gold = 0, 2, 0, 0
	edge_nums = [1]
	candidate_mapping, weight_dict = map_two_vars_edges(prod_drs.op_two_vars, gold_drs.op_two_vars, prod_drs, gold_drs, edge_nums, candidate_mapping, weight_dict, var_spot1, var_spot2, count_clauses_prod, count_clauses_gold)

	# Clause looks like (var1, OPR, var2, "item")
	candidate_mapping, weight_dict = map_two_vars_edges(prod_drs.op_two_vars_abs, gold_drs.op_two_vars_abs, prod_drs, gold_drs, [1, 3], candidate_mapping, weight_dict, 0, 2, len(gold_drs.op_two_vars),  len(prod_drs.op_two_vars))


	# Clause looks like (var1, OPR, var2, var3)
	for i in range(0, len(prod_drs.op_three_vars)):
		for j in range(0, len(gold_drs.op_three_vars)):
			candidate_mapping, weight_dict = add_candidate_mapping_three_vars(prod_drs.op_three_vars, gold_drs.op_three_vars, prod_drs, gold_drs, candidate_mapping, weight_dict, i, j,  len(gold_drs.op_two_vars) + len(gold_drs.op_two_vars_abs),  len(prod_drs.op_two_vars) + len(prod_drs.op_two_vars_abs))

	# Clause looks like (var1, Role, var2, "item")
	candidate_mapping, weight_dict = map_two_vars_edges(prod_drs.roles_abs, gold_drs.roles_abs, prod_drs, gold_drs, [1, 3], candidate_mapping, weight_dict, 0, 2, len(gold_drs.op_two_vars) + len(gold_drs.op_two_vars_abs) + len(gold_drs.op_three_vars),  len(prod_drs.op_two_vars) + len(prod_drs.op_two_vars_abs) + len(prod_drs.op_three_vars))

	# Clause looks like (var1, Role, var2, var3)
	for i in range(0, len(prod_drs.roles)):
		for j in range(0, len(gold_drs.roles)):
			candidate_mapping, weight_dict = add_candidate_mapping_three_vars(prod_drs.roles, gold_drs.roles, prod_drs, gold_drs, candidate_mapping, weight_dict, i, j, len(gold_drs.op_two_vars) + len(gold_drs.op_two_vars_abs) + len(gold_drs.roles_abs) + len(gold_drs.op_three_vars),  len(prod_drs.op_two_vars) + len(prod_drs.op_two_vars_abs) + len(prod_drs.roles_abs) + len(prod_drs.op_three_vars))

	# Clause looks like (var1, concept, "sns", var2)
	candidate_mapping, weight_dict = map_two_vars_edges(prod_drs.concepts, gold_drs.concepts, prod_drs, gold_drs, [1, 2], candidate_mapping, weight_dict, 0, 3, len(gold_drs.op_two_vars) + len(gold_drs.op_two_vars_abs) + len(gold_drs.roles_abs) + len(gold_drs.op_three_vars) + len(gold_drs.roles),  len(prod_drs.op_two_vars) + len(prod_drs.op_two_vars_abs) + len(prod_drs.roles_abs) + len(prod_drs.op_three_vars) + len(prod_drs.roles))

	return candidate_mapping, weight_dict


class DRS_match:
	'''Class to keep track of all the matching information'''
	def __init__(self):
		self.matched_clause_keys = {}
		#we have to make sure that each produced and gold clause can only be (partially) matched once. We save that here and check
		self.clause_dict_gold = {}
		self.clause_dict_prod = {}
		#Save all combinations of variables that match, so we can print matching clauses later
		self.clause_pairs = {}
		self.match_num = 0
		self.mapping = [] #initialized empty but always set to the current mapping
		self.weight_dict = {} #initialized empty but always set to the current weight_dict


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

	# Initialize class to save all information in
	drs_match = DRS_match()
	drs_match.mapping = mapping
	drs_match.weight_dict = weight_dict

	for i, m in enumerate(drs_match.mapping):
		if m == -1:
			# no node maps to this node
			continue
		# node i in DRG 1 maps to node m in DRG 2
		current_node_pair = (i, m)
		if current_node_pair not in drs_match.weight_dict:
			continue
		for key in drs_match.weight_dict[current_node_pair]:
			drs_match = compute_match_for_key(key, current_node_pair, drs_match) #return number of matches here

	# update match_clause_dict
	match_clause_dict[tuple(mapping)] = drs_match.match_num
	if final:
		return drs_match.match_num, drs_match.clause_pairs
	else:
		return drs_match.match_num, match_clause_dict


def check_dict_for_adding(drs_match, item):
	'''Only add value to our score if it is a better match for this clause
	   Each gold clause can only (partially) match once'''

	if item[2] in drs_match.clause_dict_gold and item[3] in drs_match.clause_dict_prod:
		#we already have a match for this gold clause AND produced clause, only add if this is a better match in total (and substract previous score)
		total_gain = (item[0] - drs_match.clause_dict_gold[item[2]]) + (item[0] - drs_match.clause_dict_prod[item[3]])
		if total_gain > 0:
			drs_match.clause_dict_gold[item[2]] = item[0]
			drs_match.clause_dict_prod[item[3]] = item[0]
			## Remove and add the items from our clause pairs so that we can easily find the matching parts later
			drs_match.clause_pairs[item[2], item[3]] = 1
			drs_match.match_num += (float(total_gain) / 2) #divide by 2 otherwise we add double
		else: #not an improvement, do nothing
			pass
	elif item[2] in drs_match.clause_dict_gold:
		#only gold item is already in our dict, so check if adding this clause instead gains us something
		if item[0] > drs_match.clause_dict_gold[item[2]]:
			drs_match.match_num += (item[0] - drs_match.clause_dict_gold[item[2]])
			drs_match.clause_dict_gold[item[2]] = item[0] #keep track of new value
			## Remove previous gold item from clause pairs (if there) and add new one
			to_delete = []
			for key in drs_match.clause_pairs:
				if key[0] == drs_match.clause_dict_gold[item[2]]:
					to_delete.append(key)
			for t in to_delete:
				del drs_match.clause_pairs[t]


			drs_match.clause_pairs[item[2], item[3]] = 1
		else:
			#this gold clause has already matched and this match is not an improvement, so we do nothing
			pass

	elif item[3] in drs_match.clause_dict_prod:
		#only prod clause is already matched, check if adding this clause instead gains us something
		if item[0] > drs_match.clause_dict_prod[item[3]]:
			drs_match.match_num += (item[0] - drs_match.clause_dict_prod[item[3]])
			drs_match.clause_dict_prod[item[3]] = item[0] #keep track of new value

			## Remove previous gold item from clause pairs (if there) and add new one
			to_delete = []
			for key in drs_match.clause_pairs:
				if key[1] == drs_match.clause_dict_prod[item[3]]:
					to_delete.append(key)
			for t in to_delete:
				del drs_match.clause_pairs[t]
			#clause_pairs[clause_dict_gold[item[2]],clause_dict_prod[item[3]]] = 1
			drs_match.clause_pairs[item[2], item[3]] = 1
		else:
			pass
	else:
		#this clause hasn't matched yet, just add score and save
		drs_match.match_num += item[0]
		drs_match.clause_dict_gold[item[2]] = item[0]
		drs_match.clause_dict_prod[item[3]] = item[0]
		drs_match.clause_pairs[item[2], item[3]] = 1
	return drs_match


def get_matches(current_node_pair, key, drs_match):
	'''Add specific number, but make sure to only to do that if we are allowed to match (given no match)
	   clause_dict_gold contains all gold clauses (by index) that already had a (partial) match
	   Have to keep track of this to not match gold clauses for more than 1'''

	for item in drs_match.weight_dict[current_node_pair][key]: #item looks like this [score, tuple of node pairs, gold_clause_idx, prod_clause_idx] e.g. [0.75, ((2,4), (3,5)), 4, 6]
		if item[1]:                                  #sometimes no_match is empty, then just add
			add = True
			for tup in item[1]:                      #tuple of tuples
				if drs_match.mapping[tup[0]] == tup[1]:        #variable matches while it should not match to add score
					add = False
			if add:
				drs_match = check_dict_for_adding(drs_match, item) #only add if this is a better match
		else:
			drs_match = check_dict_for_adding(drs_match, item)
	return drs_match


def compute_match_for_key(key, current_node_pair, drs_match):
	'''Compute the matches based on the key'''
	#start with 0 and add when we find matches
	if key == -1:
		# matching clauses resulting from attribute clauses
		drs_match = get_matches(current_node_pair, key, drs_match)

	elif not any(isinstance(inst, tuple) for inst in key):  #not a list of tuple but just a tuple
		# key looks like this: (2,3)
		sorted_t = (key,) + (current_node_pair,)
		sorted_tuple = tuple(sorted(sorted_t, key=lambda item: item[0]))

		if sorted_tuple in drs_match.matched_clause_keys: #already matched, don't do again - e.g. if we matched (0,0),(1,1) we don't want to also match (1,1), (0,0), because they match the same clause
			pass
		elif drs_match.mapping[key[0]] == key[1]:        #variable matches, check how much we want to add
			drs_match = get_matches(current_node_pair, key, drs_match)
			drs_match.matched_clause_keys[sorted_tuple] = 1
	else:
		#tuple of tuples here for tuples with 3 variables
		#key looks like this: ((2,3), (3,4), (4,7))
		sorted_t = key + (current_node_pair,)
		sorted_tuple = tuple(sorted(sorted_t, key=lambda item: item[0]))
		if sorted_tuple in drs_match.matched_clause_keys:   #already matched, don't do again - e.g. if we matched (0,0),(1,1),(2,2) we don't want to also match (1,1), (0,0),(2,2), because they match the same clause
			pass
		else:
			if drs_match.mapping[key[0][0]] == key[0][1] and drs_match.mapping[key[1][0]] == key[1][1]: #both nodes also match
				drs_match = get_matches(current_node_pair, key, drs_match)
				drs_match.matched_clause_keys[sorted_tuple] = 1

	return drs_match



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


def var_occurs(clauses, var, box, idx):
	'''Check if variable occurs with same box in one of the next clauses'''
	for cur_idx in range(0, len(clauses)):
		spl_tup = clauses[cur_idx]
		if cur_idx != idx and spl_tup[0] == box and (var == spl_tup[-1] or var == spl_tup[-2]):
			return True
	return False


def between_quotes(string):
	'''Return true if a value is between quotes'''
	return (string.startswith('"') and string.endswith('"')) or (string.startswith("'") and string.endswith("'"))


def all_upper(string):
	'''Checks if all items in a string are uppercase'''
	return all(x.isupper() for x in string)


def is_role(string):
	'''Check if string is in the format of a role'''
	return string[0].isupper() and any(x.islower() for x in string[1:]) and all(x.islower() or x.isupper() or x == '-' for x in string)


def rewrite_concept(concept, sense, en_sense_dict):
	'''Rewrite concepts to their WordNet 3.0 synset IDs'''
	fixed_sense = sense.replace('"', '') #replace quotes
	dict_key = concept + '.' + fixed_sense
	if dict_key not in en_sense_dict: #not in WordNet, return original values
		#print dict_key, 'not in WN'
		return concept, sense, []
	else:
		conc_sense = en_sense_dict[dict_key]
		# Now divide back again in concept + sense with quotes
		new_concept = conc_sense.split('.')[0]
		new_sense = '"' + ".".join(conc_sense.split('.')[1:]) + '"'
		if dict_key == conc_sense: #nothing normalized after all
			return new_concept, new_sense, []
		else:
			return new_concept, new_sense, [dict_key, conc_sense]



def fill_baseline_list(baseline_drs, clauses_gold_list):
	'''Fill baseline drss so that we can compare all DRSs to a baseline'''
	return [baseline_drs for _ in range(len(clauses_gold_list))]


def create_tab_list(print_rows, print_item, joiner):
	'''For multiple rows, return row of strings nicely separated by tabs'''
	col_widths = []
	if print_item:
		return_rows = [print_item]
	else:
		return_rows = []
	if print_rows:
		for idx in range(len(print_rows[0])):  # for nice printing, calculate max column length
			col_widths.append(max([len(x[idx].decode('utf-8')) for x in print_rows]) + 1)

		for idx, row in enumerate(print_rows):  # print rows here, adjusted for column width
			return_rows.append(joiner.join(word.decode('utf-8').ljust(col_widths[col_idx]) for col_idx, word in enumerate(row)))
	return return_rows


def get_mappings(clause_pairs, prod_drs, gold_drs, prec, rec, significant):
	'''Output the matching and non-matching clauses'''

	# Flatten lists of lists to get list of indices
	indices_prod = prod_drs.op_two_vars_idx + prod_drs.op_two_vars_abs_idx + prod_drs.op_three_vars_idx + prod_drs.roles_abs_idx + prod_drs.roles_idx + prod_drs.concepts_idx
	indices_gold = gold_drs.op_two_vars_idx + gold_drs.op_two_vars_abs_idx + gold_drs.op_three_vars_idx + gold_drs.roles_abs_idx + gold_drs.roles_idx + gold_drs.concepts_idx
	match = []
	no_match = []

	orig_prod_idx_match = []
	orig_gold_idx_match = []

	# First get all matches and order them based on gold occurence
	ordered_clauses = [[indices_prod[idx2], indices_gold[idx1]] for idx1, idx2 in clause_pairs]
	for idx_prod, idx_gold in sorted(ordered_clauses, key=lambda x: x[1]):
		match.append([prod_drs.original_clauses[idx_prod], gold_drs.original_clauses[idx_gold]])
		orig_prod_idx_match.append(idx_prod)
		orig_gold_idx_match.append(idx_gold)

	# Get which indices match and do no match (do sorted for no match so that
	# we have some kind of order still)
	no_match_prod = sorted([x for x in range(len(prod_drs.original_clauses)) if x not in orig_prod_idx_match])
	no_match_gold = sorted([x for x in range(len(gold_drs.original_clauses)) if x not in orig_gold_idx_match])

	# Populate the no match part of what we will print later (is a bit
	# cumbersome because we want aligned printing later)
	for num in no_match_prod:
		no_match.append([prod_drs.original_clauses[num], ''])

	for num in no_match_gold:
		found = False
		for no_match_item in no_match:
			if no_match_item[1] == '':  # there is still space to add
				no_match_item[1] = gold_drs.original_clauses[num]
				found = True
				break
		if not found:  # no space to add, create new row
			no_match.append(['', gold_drs.original_clauses[num]])

	# Check if results make sense compared to our previous result
	print_prec = round(len(match) / float(prod_drs.total_clauses), significant)
	print_rec = round(len(match) / float(gold_drs.total_clauses), significant)

	if print_prec != prec or print_rec != rec:
		raise ValueError(
			"Error when calculating precision/recall for printing clauses:\nPrint prec {0} vs search prec {1}\nPrint rec {0} vs search rec {1}\n".format(print_prec, prec, print_rec, rec))

	# Print to screen and possibly to file later
	print_match = create_tab_list(match, '\n## Matching clauses ##\n', "| ")
	print_no_match = create_tab_list(no_match, '\n## Non-matching clauses ##\n', "| ")

	# Also get number of matching operator/roles/concepts for more detailed results
	match_division = [0, 0, 0]
	for clause in [x[0] for x in match]:
		spl_line = clause.split()
		if '%' in spl_line:
			spl_line = spl_line[0:spl_line.index('%')]

		if all_upper(spl_line[1]):
			match_division[0] += 1
		elif is_role(spl_line[1]):
			match_division[1] += 1
		else:
			match_division[2] += 1

	return print_match, print_no_match, match_division


def get_matching_clauses(arg_list):
	'''Function that gets matching clauses (easier to parallelize)'''
	start_time = time.time()

	# Unpack arguments to make things easier
	prod_t, gold_t, args, single, original_prod, original_gold, en_sense_dict = arg_list

	# Create DRS objects
	prod_drs = DRS()
	gold_drs = DRS()
	prod_drs.prefix = 'a' # Prefixes are used to create standardized variable-names
	gold_drs.prefix = 'b'
	prod_drs.file_name = args.f1
	gold_drs.file_name = args.f2
	prod_drs.original_clauses = original_prod
	gold_drs.original_clauses = original_gold

	# Get the specific clauses here
	prod_drs.get_specific_clauses(prod_t, en_sense_dict)
	gold_drs.get_specific_clauses(gold_t, en_sense_dict)

	if single and (args.max_clauses > 0 and ((prod_drs.total_clauses > args.max_clauses) or (gold_drs.total_clauses > args.max_clauses))):
		print 'Skip calculation of DRS, more clauses than max of {0}'.format(args.max_clauses)
	else:
		# Do the hill-climbing for the matching here
		(best_mapping, best_match_num, found_idx, smart_fscores, clause_pairs) = get_best_match(prod_drs, gold_drs, args, single)

		if len(set([x for x in best_mapping if x != -1])) != len([x for x in best_mapping if x != -1]):
			raise ValueError("Variable maps to two other variables, not allowed -- {0}".format(best_mapping))

		if verbose:
			print >> DEBUG_LOG, "best match number", best_match_num
			print >> DEBUG_LOG, "best node mapping", best_mapping

		(precision, recall, best_f_score) = compute_f(best_match_num, prod_drs.total_clauses, gold_drs.total_clauses, args.significant, False)
		
		print_match, print_no_match, match_division = get_mappings(clause_pairs, prod_drs, gold_drs, precision, recall, args.significant)
		
		# Print clause mapping if -prin is used and we either do multiple scores, or just had a single DRS
		if args.prin and (args.ms or single):

			# Print rewrites of concepts that were performed (only for single instances)
			rewrite_list = create_tab_list(prod_drs.rewritten_concepts + gold_drs.rewritten_concepts, '\n## Normalized concepts to synset ID ##\n', '-> ')
			uniq_rewrite = []
			[uniq_rewrite.append(item) for item in rewrite_list if item not in uniq_rewrite] #only unique transformations, but keep order
			for print_str in uniq_rewrite:
				print print_str

			# Print match and non-match to screen
			for print_line in print_match:
				print print_line
			for print_line in print_no_match:
				print print_line

		# For single DRS we print results later on anyway
		prod_clause_division = [prod_drs.num_operators, prod_drs.num_roles, prod_drs.num_concepts]
		gold_clause_division = [gold_drs.num_operators, gold_drs.num_roles, gold_drs.num_concepts]
		if args.ms and not single:
			print_results([[best_match_num, prod_drs.total_clauses, gold_drs.total_clauses, smart_fscores, found_idx, match_division, prod_clause_division, gold_clause_division, len(prod_drs.var_map)]],
				start_time, single, args)

		return [best_match_num, prod_drs.total_clauses, gold_drs.total_clauses, smart_fscores, found_idx, match_division, prod_clause_division, gold_clause_division, len(prod_drs.var_map)]


def print_results(res_list, start_time, single, args):
	'''Print the final or inbetween scores -- res_list has format '''

	# Calculate average scores
	total_match_num = sum([x[0] for x in res_list if x])
	total_test_num = sum([x[1] for x in res_list if x])
	total_gold_num = sum([x[2] for x in res_list if x])
	found_idx = round(float(sum([x[4] for x in res_list if x])) / float(len([x[4] for x in res_list if x])), args.significant)
	runtime = round(time.time() - start_time, args.significant)

	match_division = [x[5] for x in res_list]
	prod_division = [x[6] for x in res_list]
	gold_division = [x[7] for x in res_list]

	# Calculate detailed F-scores for clauses and roles
	prec_op, rec_op, f_op = compute_f(sum([x[0] for x in match_division]), sum([x[0] for x in prod_division]), sum([x[0] for x in gold_division]), args.significant, False)
	prec_role, rec_role, f_role = compute_f(sum([x[1] for x in match_division]), sum([x[1] for x in prod_division]), sum([x[1] for x in gold_division]), args.significant, False)
	prec_conc, rec_conc, f_conc = compute_f(sum([x[2] for x in match_division]), sum([x[2] for x in prod_division]), sum([x[2] for x in gold_division]), args.significant, False)

	if verbose:
		print >> DEBUG_LOG, "Total match number, total clause number in DRS 1, and total clause number in DRS 2:"
		print >> DEBUG_LOG, total_match_num, total_test_num, total_gold_num
		print >> DEBUG_LOG, "---------------------------------------------------------------------------------"

	# Output document-level score (a single f-score for all DRS pairs in two files)

	(precision, recall, best_f_score) = compute_f(total_match_num,
												  total_test_num, total_gold_num, args.significant, False)
	if not res_list:
		return []  # no results for some reason
	else:
		print '\n## Clause information ##\n'
		print 'Clauses prod : {0}'.format(total_test_num)
		print 'Clauses gold : {0}\n'.format(total_gold_num)
		if args.max_clauses > 0:
			print 'Max number of clauses per DRS:  {0}\n'.format(args.max_clauses)
		print '## Main Results ##\n'
		if not single:
			print 'All shown number are averages calculated over {0} DRS-pairs\n'.format(len(res_list))
		print 'Matching clauses: {0}\n'.format(total_match_num)
		if pr_flag:
			print "Precision: {0}".format(round(precision, args.significant))
			print "Recall   : {0}".format(round(recall, args.significant))
			print "F-score  : {0}".format(round(best_f_score, args.significant))
		else:
			if best_f_score > 1:
				raise ValueError(
					"F-score larger than 1: {0}".format(best_f_score))
			print "F-score  : {0}".format(round(best_f_score, args.significant))

		# Print specific output here
		if args.prin:
			if args.pr:
				print '\n## Detailed precision, recall, F-score ##\n'
				print 'Prec, rec, F1 operators: {0}, {1}, {2}'.format(prec_op, rec_op, f_op)
				print 'Prec, rec, F1 roles    : {0}, {1}, {2}'.format(prec_role, rec_role, f_role)
				print 'Prec, rec, F1 concepts : {0}, {1}, {2}\n'.format(prec_conc, rec_conc, f_conc)
			else:
				print '\n## Detailed F-scores ##\n'
				print 'F-score operators: {0}'.format(f_op)
				print 'F-score roles    : {0}'.format(f_role)
				print 'F-score concepts : {0}\n'.format(f_conc)

			if args.smart == 'conc':
				smart_conc = compute_f(sum([y[0] for y in [x[3] for x in res_list]]), total_test_num, total_gold_num, args.significant, True)
				print 'Smart F-score concepts: {0}'.format(smart_conc)

			# For a single DRS we can print some more information
			if single:
				print '\n## Restarts and processing time ##\n'
				print 'Num restarts specified       : {0}'.format(args.restarts)
				print 'Found best mapping at restart: {0}'.format(int(found_idx))

	print 'Total processing time        : {0} sec'.format(runtime)

	return [precision, recall, best_f_score]


def check_input(clauses_prod_list, original_prod, original_gold, clauses_gold_list, baseline, f1, max_clauses, single):
	'''Check if the input is valid -- or fill baseline if that is asked'''
	if baseline:  # if we try a baseline DRS, we have to fill a list of this baseline
		if len(clauses_prod_list) == 1:
			print 'Testing baseline DRS vs {0} DRSs...\n'.format(len(clauses_gold_list))
			clauses_prod_list = fill_baseline_list(clauses_prod_list[0], clauses_gold_list)
			original_prod = fill_baseline_list(original_prod[0], original_gold)
		else:
			raise ValueError("Using --baseline, but there is more than 1 DRS in prod file")
	elif len(clauses_prod_list) != len(clauses_gold_list):
		raise ValueError("Number of DRSs not equal, {0} vs {1}, exiting...".format(len(clauses_prod_list), len(clauses_gold_list)))
	elif len(clauses_prod_list) == 0 and len(clauses_gold_list) == 0:
		raise ValueError("Both DRSs empty, exiting...")
	elif not single:
		print 'Comparing {0} DRSs...\n'.format(len(clauses_gold_list))

	# Print number of DRSs we skip due to the -max_clauses parameter
	if max_clauses > 0 and not single:
		print 'Skipping {0} DRSs due to their length exceeding {1} (--max_clauses)\n'.format(len([x for x, y in zip(clauses_gold_list, clauses_prod_list) if len(x) > max_clauses or len(y) > max_clauses]), max_clauses)

	return original_prod, clauses_prod_list


class DRS:
	'''Main DRS class with methods to process and rewrite the clauses'''
	op_boxes = ['NOT', 'POS', 'NEC', 'IMP', 'DIS', 'PRP', 'DRS', 'ANSWER', 'PARALLEL', 'CONTINUATION', 'CONTRAST', 'RESULT', 'EXPLANATION', 'TAB']

	def __init__(self):
		# List for different types of clauses
		self.op_two_vars, self.op_two_vars_idx = [], []
		self.op_two_vars_abs, self.op_two_vars_abs_idx = [], []
		self.op_three_vars, self.op_three_vars_idx = [], []
		self.roles_abs, self.roles_abs_idx = [], []
		self.roles, self.roles_idx = [], []
		self.concepts, self.concepts_idx = [], []

		# Lists and dicts to keep track of the variable information and rewritten concepts
		self.vars_seen = []
		self.type_vars = {}
		self.var_map = {}
		self.rewritten_concepts = []

	def rename_var(self, var, var_type):
		'''Function that renames the variables in a standardized way'''
		if var in self.vars_seen:
			new_var = self.prefix + str(self.vars_seen.index(var))
		else:
			new_var = self.prefix + str(len(self.vars_seen))
			self.type_vars[new_var] = var_type
			self.vars_seen.append(var)

		self.var_map[new_var] = var
		return new_var


	def add_if_not_exists(self, list1, list2, to_add, to_add2):
		'''Add something to two list of lists if it is not there yet in the first one'''
		if to_add not in list1:
			list1.append(to_add)
			list2.append(to_add2)


	def add_concept_clauses(self, cur_clause, val0, idx, en_sense_dict):
		'''Add concepts clauses to our list of clauses'''
		if not between_quotes(cur_clause[2]):
			raise ValueError(
				"Incorrectly format clause: {0}\nThird item of concept clause should be a sense and should always be between quotes".format(cur_clause))
		elif between_quotes(cur_clause[3]):
			raise ValueError(
				"Incorrectly format clause: {0}\n Fourth item of concept clause should be a variable and not between quotes".format(cur_clause))
		else:
			# First rename the variable
			val3 = self.rename_var(cur_clause[3], 'x')
			# Then rewrite the concept to its synset ID in WordNet
			new_concept, new_sense, rewritten_values = rewrite_concept(cur_clause[1], cur_clause[2], en_sense_dict)
			self.add_if_not_exists(self.concepts, self.concepts_idx, (val0, new_concept, new_sense, val3), idx)
			# Save rewritten concepts
			if rewritten_values:
				self.rewritten_concepts.append(rewritten_values)


	def add_role_clauses(self, cur_clause, val0, idx):
		'''Add clauses that have a Role as second item to our list of clauses'''

		# Second clause item is a (VerbNet) role
		if between_quotes(cur_clause[2]):
			raise ValueError("Incorrectly format clause: {0}\nThird item of role clause should be a variable and not between quotes".format(cur_clause))
		else:
			# Second item in clause is a role
			val2 = self.rename_var(cur_clause[2], 'x')
			# If last item is between quotes it belongs in roles_abs (b0 PartOf x2 "speaker")
			if between_quotes(cur_clause[3]):
				self.add_if_not_exists(self.roles_abs, self.roles_abs_idx, (val0, cur_clause[1], val2, cur_clause[3]), idx)
			# Otherwise it belongs in roles (b1 Patient x1 x2)
			else:
				val3 = self.rename_var(cur_clause[3], 'x')
				self.add_if_not_exists(self.roles, self.roles_idx, (val0, cur_clause[1], val2, val3), idx)


	def add_operator_clauses(self, val0, cur_clause, idx):
		'''Add clauses that have an operator as second item to our list of close'''
		# Get var type of second variable
		var_type = 'b' if cur_clause[1] in self.op_boxes and cur_clause[1] != 'PRP' else 'x'

		# Get renamed variable
		val2 = self.rename_var(cur_clause[2], var_type)

		# If last item is between quotes it belongs in op_two_vars_abs (b2 EQU t1 "now")
		if between_quotes(cur_clause[3]):
			self.add_if_not_exists(self.op_two_vars_abs, self.op_two_vars_abs_idx, (val0, cur_clause[1], val2, cur_clause[3]), idx)
		# Else it belongs in op_three_vars (b1 LES x1 x2)
		else:
			var_type = 'b' if cur_clause[1] in self.op_boxes else 'x'
			val3 = self.rename_var(cur_clause[3], var_type)
			self.add_if_not_exists(self.op_three_vars, self.op_three_vars_idx, (val0, cur_clause[1], val2, val3), idx)


	def get_specific_clauses(self, clause_list, en_sense_dict):
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

		# Keep track of variable information

		# Operators that have two box variables
		for idx, cur_clause in enumerate(clause_list):
			# Clause has three items and belongs in op_two_vars (b0 REF x1 ,  b0 NOT b1)
			if len(cur_clause) == 3:
				if between_quotes(cur_clause[2]) or between_quotes(cur_clause[2]) or not cur_clause[0].islower() or not cur_clause[2].islower():
					raise ValueError("Incorrectly format clause: {0}\nClauses of length three should always contain two variables".format(cur_clause))
				else:
					val0 = self.rename_var(cur_clause[0], 'b')
					var_type = 'b' if cur_clause[1] in self.op_boxes else 'x'
					val2 = self.rename_var(cur_clause[2], var_type)
					self.add_if_not_exists(self.op_two_vars, self.op_two_vars_idx, (val0, cur_clause[1], val2), idx)

			# Clause has 4 items
			else:
				# First item always is a box variable
				if between_quotes(cur_clause[0]):
					raise ValueError("Incorrectly format clause: {0}\n".format(cur_clause))
				else:
					val0 = self.rename_var(cur_clause[0], 'b')
					if all_upper(cur_clause[1]): # Second item is an operator
						self.add_operator_clauses(val0, cur_clause, idx)
					elif is_role(cur_clause[1]): # Second item is a role
						self.add_role_clauses(cur_clause, val0, idx)
					else:                       # Otherwise it must be a concept (b1 work "v.01" x2)
						self.add_concept_clauses(cur_clause, val0, idx, en_sense_dict)

		# Get number of operator/role/concept clauses
		self.num_operators = len(self.op_two_vars) + len(self.op_two_vars_abs) + len(self.op_three_vars)
		self.num_roles = len(self.roles) + len(self.roles_abs)
		self.num_concepts = len(self.concepts)
		self.total_clauses = self.num_operators + self.num_roles + self.num_concepts



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

	# Read in English sense dict for rewriting concepts to synset ID
	# This is read from a Python import to speed things up (twice as fast as loading JSON every time)
	en_sense_dict = load_json_dict(args.en_sense_dict)
	
	# Get the clauses
	clauses_prod_list, original_prod = get_clauses(args.f1)
	clauses_gold_list, original_gold = get_clauses(args.f2)

	single = True if len(clauses_gold_list) == 1 else False  # true if we are doing a single DRS

	# Check if correct input
	original_prod, clauses_prod_list = check_input(clauses_prod_list, original_prod, original_gold, clauses_gold_list, args.baseline, args.f1, args.max_clauses, single)

	# Processing clauses
	arg_list = []
	for count, (prod_t, gold_t) in enumerate(zip(clauses_prod_list, clauses_gold_list)):
		arg_list.append([prod_t, gold_t, args, single, original_prod[count], original_gold[count], en_sense_dict])

	# Parallel processing here
	if args.parallel == 1:  # no need for parallelization for p=1
		all_results = []
		for arguments in arg_list:
			all_results.append(get_matching_clauses(arguments))
	else:
		all_results = multiprocessing.Pool(args.parallel).map(get_matching_clauses, arg_list)

	# If we find results, print them in a nice way
	if all_results:
		print_results(all_results, start, single, args)
	else:
		raise ValueError('No results found')

	# We might also want to save all individual F-scores, usually for the sake of doing statistics. We print them to a file here
	if args.ms_file:
		with open(args.ms_file, 'w') as out_f:
			for items in all_results:
				_, _, f_score = compute_f(items[0], items[1], items[2], args.significant, False)
				out_f.write(str(f_score) + '\n')
		out_f.close()


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

