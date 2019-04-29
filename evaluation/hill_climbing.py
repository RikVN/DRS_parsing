'''Module that has the functions for the hill-climbing method for the clause matching'''

import random, psutil, os

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


def get_memory_usage():
	'''return the memory usage in MB'''
	process = psutil.Process(os.getpid())
	mem = process.memory_info()[0] / float(1000000)
	return mem


def get_best_match(prod_drs, gold_drs, args, single):
	"""
	Get the highest clause match number between two sets of clauses via hill-climbing.
	Arguments:
		prod_drs: Object with all information of the produced DRS
		gold_drs: Object with all information of the gold DRS
		args: command line argparse arguments
		single: whether this is the only DRS we do
	Returns:
		best_match: the node mapping that results in the highest clause matching number
		best_match_num: the highest clause matching number

	"""

	# Compute candidate pool - all possible node match candidates.
	# In the hill-climbing, we only consider candidate in this pool to save computing time.
	# weight_dict is a dictionary that maps a pair of node
	(candidate_mappings, weight_dict) = compute_pool(prod_drs, gold_drs, args)
	#for w in weight_dict:
		#print w
		#for x in weight_dict[w]:
			#print x, weight_dict[w][x]
		#print '\n'
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
	#mapping_order = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]]
	# Set initial values
	done_mappings = {}
	# Loop over the mappings to find the best score
	for i, map_cur in enumerate(mapping_order):  # number of restarts is number of mappings
		cur_mapping = map_cur[0]
		match_num = map_cur[1]
		num_vars = len(gold_drs.var_map)

		if tuple(cur_mapping) in done_mappings:
			match_num = done_mappings[tuple(cur_mapping)]
		else:
			# Do hill-climbing until there will be no gain for new node mapping
			while True:
				# get best gain
				(gain, new_mapping, match_clause_dict) = get_best_gain(cur_mapping, candidate_mappings, weight_dict, num_vars, match_clause_dict)

				if match_num + gain > prod_drs.total_clauses:
					print(new_mapping, match_num + gain, prod_drs.total_clauses)
					raise ValueError(
						"More matches than there are produced clauses. If this ever occurs something is seriously wrong with the algorithm")

				if gain <= 0:
					# print 'No gain so break'
					break
				# otherwise update match_num and mapping
				match_num += gain
				cur_mapping = new_mapping[:]

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
		# stop instead of doing all other restarts - but always do smart mappings
		if match_num == prod_drs.total_clauses and i > len(smart_fscores) - 1:
			if args.prin and single:
				print('Best match already found, stop restarts at restart {0}'.format(i))
			if i < len(smart_fscores):
				smart_fscores[i] = match_num
			break

		# Add smart F-scores
		if i < len(smart_fscores):  # are we still adding smart F-scores?
			smart_fscores[i] = match_num

	_, clause_pairs = compute_match(best_mapping, weight_dict, {}, final=True)

	# Clear matches out of memory
	match_clause_dict.clear()
	if len(set([x for x in best_mapping if x != -1])) != len([x for x in best_mapping if x != -1]):
		raise ValueError("Variable maps to two other variables, not allowed, and should never happen -- {0}".format(best_mapping))
	return best_mapping, best_match_num, found_idx, smart_fscores, clause_pairs,


def add_random_mapping(result, matched_dict, candidate_mapping):
	'''If mapping is still -1 after adding a smart mapping, randomly fill in the blanks'''
	# First shuffle the way we loop over result, so that we increase the randomness of the mappings
	indices = list(range(len(result)))
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
					if result[var11] == -1 and var21 not in matched_dict:
						result[var11] = var21
						matched_dict[var21] = 1
					if result[var12] == -1 and var22 not in matched_dict:
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
			elif (node_pair3, node_pair2) in weight_dict[node_pair1]:
				weight_dict[node_pair1][(node_pair3, node_pair2)].append([weight_score, no_match, gold_clause_idx, prod_clause_idx])
			else:
				weight_dict[node_pair1][(node_pair2, node_pair3)] = [[weight_score, no_match, gold_clause_idx, prod_clause_idx]]
		else:
			weight_dict[node_pair1] = {}
			weight_dict[node_pair1][(node_pair2, node_pair3)] = [[weight_score, no_match, gold_clause_idx, prod_clause_idx]]
	return weight_dict


def add_candidate_mapping_three_vars(prod_clauses, gold_clauses, prod_drs, gold_drs, candidate_mapping, weight_dict, i, j, add_to_index, add_to_index2, args):
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
			
			# If the edge is part of inv_boxes, it means that e.g. b1 INV_BOX x1 x2 == b1 INV_BOX x2 x1
			# We want to add this information to the matching dictionary as well here
			if prod_clauses[i][edge_index] in prod_drs.inv_boxes:
				# Node pairs are inverted now
				node_pair_new1 = (node1_index_drs1, node1_index_drs2)
				node_pair_new2 = (node2_index_drs1, node3_index_drs2)
				node_pair_new3 = (node3_index_drs1, node2_index_drs2)
				# Add correct candidate mappings for these nodes
				candidate_mapping[node1_index_drs1].add(node1_index_drs2)
				candidate_mapping[node2_index_drs1].add(node3_index_drs2)
				candidate_mapping[node3_index_drs1].add(node2_index_drs2)
				# Update the weight dictionary
				weight_dict = add_node_pairs(node_pair_new1, node_pair_new2, node_pair_new3, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)
				weight_dict = add_node_pairs(node_pair_new2, node_pair_new1, node_pair_new3, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)
				weight_dict = add_node_pairs(node_pair_new3, node_pair_new1, node_pair_new2, weight_dict, weight_score, no_match, j + add_to_index, i + add_to_index2)
			
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
													node1_index_drs2, node2_index_drs1, node2_index_drs2, no_match, j + add_to_index, i + add_to_index2, args)

			if allowed_var1 and allowed_var3:  # add partial match for var 1 and 3
				no_match = ((node2_index_drs1, node2_index_drs2),)
				weight_score = 2 / float(4) + edge_match
				candidate_mapping, weight_dict = add_candidate_mapping(candidate_mapping, weight_dict, weight_score, node1_index_drs1,
													node1_index_drs2, node3_index_drs1, node3_index_drs2, no_match, j + add_to_index, i + add_to_index2, args)

			if allowed_var2 and allowed_var3:  # add partial match for var 2 and 3
				no_match = ((node1_index_drs1, node1_index_drs2),)
				weight_score = 2 / float(4) + edge_match
				candidate_mapping, weight_dict = add_candidate_mapping(candidate_mapping, weight_dict, weight_score, node2_index_drs1,
													node2_index_drs2, node3_index_drs1, node3_index_drs2, no_match, j + add_to_index, i + add_to_index2, args)

	return candidate_mapping, weight_dict


def add_candidate_mapping(candidate_mapping, weight_dict, weight_score, node1_index_drs1, node1_index_drs2, node2_index_drs1, node2_index_drs2, no_match, gold_clause_idx, prod_clause_idx, args):
	'''Add the candidate mapping for this node pair to the weight dict - for two variables'''

	# add mapping between two nodes
	candidate_mapping[node1_index_drs1].add(node1_index_drs2)
	candidate_mapping[node2_index_drs1].add(node2_index_drs2)
	node_pair1 = (node1_index_drs1, node1_index_drs2)
	node_pair2 = (node2_index_drs1, node2_index_drs2)
	if node_pair2 == node_pair1:
		print("WARNING: two nodepairs are the same, should never happen, except when using -ill score")
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
			weight_dict[node_pair][-1] = [[weight_score, no_match, gold_clause_idx, prod_clause_idx]]
	else:
		weight_dict[node_pair] = {}
		weight_dict[node_pair][-1] = [[weight_score, no_match, gold_clause_idx, prod_clause_idx]]

	return candidate_mapping, weight_dict


def map_two_vars_edges(clauses_prod, clauses_gold, prod_drs, gold_drs, edge_numbers, candidate_mapping, weight_dict, var_index1, var_index2, add_to_index, add_to_index2, args):
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
																			node2_index_drs1, node2_index_drs2, no_match, j + add_to_index, i + add_to_index2, args)
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
					candidate_mapping, weight_dict = add_candidate_mapping(candidate_mapping, weight_dict, weight_score, node1_index_drs1, node1_index_drs2, node2_index_drs1, node2_index_drs2, no_match, j + add_to_index, i + add_to_index2, args)

	return candidate_mapping, weight_dict


def add_mapping_role_two_abs(prod_drs, gold_drs, weight_dict, candidate_mapping, add_to_index_gold, add_to_index_prod, args):
	'''Add a candidate mapping for a role clause with two constant items
	   Clause looks like: b1 Role "item1" "item2" '''
	minus_count = -1
	for i in range(0, len(prod_drs.roles_two_abs)):
		for j in range(0, len(gold_drs.roles_two_abs)): 
			var_index = 0 
			if not args.partial:
				# Check if all the other values match (Role, "item1", "item2")
				if normalize(prod_drs.roles_two_abs[i][1]) == normalize(gold_drs.roles_two_abs[j][1]) and normalize(prod_drs.roles_two_abs[i][2]) == normalize(gold_drs.roles_two_abs[j][2]) and normalize(prod_drs.roles_two_abs[i][3]) == normalize(gold_drs.roles_two_abs[j][3]):
					# We have a match here, add mapping and weights
					node1_index = int(prod_drs.roles_two_abs[i][var_index][len(prod_drs.prefix):])
					node2_index = int(gold_drs.roles_two_abs[j][var_index][len(gold_drs.prefix):])
					candidate_mapping[node1_index].add(node2_index)
					node_pair = (node1_index, node2_index)
					# use a minus count as key in weight_dict for roles_two_abs
					if node_pair not in weight_dict:
						weight_dict[node_pair] = {}
					weight_dict[node_pair][minus_count] = [[1, '', add_to_index_gold + j, add_to_index_prod + i]]
					minus_count -= 1
			# Do partial matching here
			else:
				partial_value = 1 / len(prod_drs.roles_two_abs[0]) 
				total_match = partial_value
				# Update partial matching score if one of the absolute values match
				if normalize(prod_drs.roles_two_abs[i][1]) == normalize(gold_drs.roles_two_abs[j][1]):
					total_match += partial_value
				if normalize(prod_drs.roles_two_abs[i][2]) == normalize(gold_drs.roles_two_abs[j][2]):  
					total_match += partial_value
				if  normalize(prod_drs.roles_two_abs[i][3]) == normalize(gold_drs.roles_two_abs[j][3]): 
					total_match += partial_value
				# We have a match here, add mapping and weights
				node1_index = int(prod_drs.roles_two_abs[i][var_index][len(prod_drs.prefix):])
				node2_index = int(gold_drs.roles_two_abs[j][var_index][len(gold_drs.prefix):])
				candidate_mapping[node1_index].add(node2_index)
				node_pair = (node1_index, node2_index)
				# Update weight dictionary here
				if node_pair not in weight_dict:
					weight_dict[node_pair] = {}
				weight_dict[node_pair][minus_count] = [total_match, '', add_to_index_gold + j, add_to_index_prod + i]
				minus_count -= 1
	return candidate_mapping, weight_dict           


def compute_pool(prod_drs, gold_drs, args):
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
	candidate_mapping, weight_dict = map_two_vars_edges(prod_drs.op_two_vars, gold_drs.op_two_vars, prod_drs, gold_drs, edge_nums, candidate_mapping, weight_dict, var_spot1, var_spot2, count_clauses_prod, count_clauses_gold, args)
	
	# Clause looks like (var1, OPR, "item", var2)
	candidate_mapping, weight_dict = map_two_vars_edges(prod_drs.op_two_vars_abs1, gold_drs.op_two_vars_abs1, prod_drs, gold_drs, [1, 2], candidate_mapping, weight_dict, 0, 3, len(gold_drs.op_two_vars),  len(prod_drs.op_two_vars), args)
	
	# Clause looks like (var1, OPR, var2, "item")
	candidate_mapping, weight_dict = map_two_vars_edges(prod_drs.op_two_vars_abs2, gold_drs.op_two_vars_abs2, prod_drs, gold_drs, [1, 3], candidate_mapping, weight_dict, 0, 2, len(gold_drs.op_two_vars) + len(gold_drs.op_two_vars_abs1),  len(prod_drs.op_two_vars) + len(prod_drs.op_two_vars_abs1), args)

	# Clause looks like (var1, OPR, var2, var3)
	for i in range(0, len(prod_drs.op_three_vars)):
		for j in range(0, len(gold_drs.op_three_vars)):
			candidate_mapping, weight_dict = add_candidate_mapping_three_vars(prod_drs.op_three_vars, gold_drs.op_three_vars, prod_drs, gold_drs, candidate_mapping, weight_dict, i, j,  len(gold_drs.op_two_vars) + len(gold_drs.op_two_vars_abs1) + len(gold_drs.op_two_vars_abs2),  len(prod_drs.op_two_vars) + len(prod_drs.op_two_vars_abs1) + len(prod_drs.op_two_vars_abs2), args)

	# Clause looks like (var1, Role, "item1", "item2")
	candidate_mapping, weight_dict = add_mapping_role_two_abs(prod_drs, gold_drs, weight_dict, candidate_mapping, len(gold_drs.op_two_vars) + len(gold_drs.op_two_vars_abs1) + len(gold_drs.op_two_vars_abs2) + len(gold_drs.op_three_vars), len(prod_drs.op_two_vars) + len(prod_drs.op_two_vars_abs1) + len(prod_drs.op_two_vars_abs2) + len(prod_drs.op_three_vars), args)

	# Clause looks liks (var1, Role, "item", var2)
	candidate_mapping, weight_dict = map_two_vars_edges(prod_drs.roles_abs1, gold_drs.roles_abs1, prod_drs, gold_drs, [1, 2], candidate_mapping, weight_dict, 0, 3, len(gold_drs.op_two_vars) + len(gold_drs.op_two_vars_abs1) + len(gold_drs.op_two_vars_abs2) + len(gold_drs.op_three_vars) + len(gold_drs.roles_two_abs),  len(prod_drs.op_two_vars) + len(prod_drs.op_two_vars_abs1) + len(prod_drs.op_two_vars_abs2) + len(prod_drs.op_three_vars) + len(prod_drs.roles_two_abs), args)

	# Clause looks like (var1, Role, var2, "item")
	candidate_mapping, weight_dict = map_two_vars_edges(prod_drs.roles_abs2, gold_drs.roles_abs2, prod_drs, gold_drs, [1, 3], candidate_mapping, weight_dict, 0, 2, len(gold_drs.op_two_vars) + len(gold_drs.op_two_vars_abs1) + len(gold_drs.op_two_vars_abs2) + len(gold_drs.op_three_vars) + len(gold_drs.roles_two_abs) + len(gold_drs.roles_abs1),  len(prod_drs.op_two_vars) + len(prod_drs.op_two_vars_abs1) + len(prod_drs.op_two_vars_abs2) + len(prod_drs.op_three_vars) + len(prod_drs.roles_two_abs) + len(prod_drs.roles_abs1), args)
	# Clause looks like (var1, Role, var2, var3)
	for i in range(0, len(prod_drs.roles)):
		for j in range(0, len(gold_drs.roles)):
			candidate_mapping, weight_dict = add_candidate_mapping_three_vars(prod_drs.roles, gold_drs.roles, prod_drs, gold_drs, candidate_mapping, weight_dict, i, j, len(gold_drs.op_two_vars) + len(gold_drs.op_two_vars_abs1) + len(gold_drs.op_two_vars_abs2) + len(gold_drs.roles_two_abs) + len(gold_drs.roles_abs1) + len(gold_drs.roles_abs2) + len(gold_drs.op_three_vars),  len(prod_drs.op_two_vars) + len(prod_drs.op_two_vars_abs1) + len(prod_drs.op_two_vars_abs2) + len(prod_drs.roles_two_abs) + len(prod_drs.roles_abs1) + len(prod_drs.roles_abs2) + len(prod_drs.op_three_vars), args)

	# Clause looks like (var1, concept, "sns", var2)
	candidate_mapping, weight_dict = map_two_vars_edges(prod_drs.concepts, gold_drs.concepts, prod_drs, gold_drs, [1, 2], candidate_mapping, weight_dict, 0, 3, len(gold_drs.op_two_vars) + len(gold_drs.op_two_vars_abs1) + len(gold_drs.op_two_vars_abs2) + len(gold_drs.roles_two_abs) + len(gold_drs.roles_abs1) + len(gold_drs.roles_abs2) + len(gold_drs.op_three_vars) + len(gold_drs.roles),  len(prod_drs.op_two_vars) + len(prod_drs.op_two_vars_abs1) + len(prod_drs.op_two_vars_abs2) + len(prod_drs.roles_two_abs) + len(prod_drs.roles_abs1) + len(prod_drs.roles_abs2) + len(prod_drs.op_three_vars) + len(prod_drs.roles), args)
	return candidate_mapping, weight_dict



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
	if isinstance(key, int) and key < 0:
		# matching clauses resulting from roles_two_abs clauses
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
