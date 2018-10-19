#!/usr/bin/env python
# -*- coding: utf8 -*-

'''Script that converts AMRs to DRS format by applying hand-written rules
   Check this paper for core idea: http://www.anthology.aclweb.org/J/J16/J16-3006.pdf'''

import os, argparse, sys, re, copy


def create_arg_parser():
	parser = argparse.ArgumentParser()
	parser.add_argument("-i", "--input_file", required=True, type=str, help="Input-file with AMRs")
	parser.add_argument("-o", "--oneline", action = 'store_true', help="The input file contains AMRs in oneline format")
	parser.add_argument("-d", "--drs_file", required=True, type=str, help="Output file with DRSs")
	args = parser.parse_args()
	## Check arguments
	if not os.path.isfile(args.input_file):
		raise ValueError("Input file does not exist")
	return args


def get_amrs(in_file):
	'''Read AMR file and return AMR in single line format -- do keep comments
	   Returns list of lists in format [[comments_amr1, amr1], [comments_amr2, amr2], ..]'''
	amrs = []
	cur_amr = []
	cur_comments = []
	for line in open(in_file, 'r'):
		if not line.strip(): #new AMR starts here
			if cur_amr:
				## Save as [comment_string, amr_string]
				amrs.append(["\n".join(cur_comments), " ".join(cur_amr)])
				cur_amr = []
				cur_comments = []
		elif line.strip().startswith('#'): #save comments
			cur_comments.append(line.strip())
		else:
			cur_amr.append(line.strip()) #save AMR lines
	if cur_amr:
		amrs.append(["\n".join(cur_comments), " ".join(cur_amr)])
	return amrs


def get_argument_dict():
	'''Translation dictionary for arguments/roles in AMRs and DRSs
	   First item is the role we insert, second is whether we swap the variables (True/False)'''
	d = {}
	d[':ARG0'] = ['Agent', False]
	d[':ARG1'] = ['Patient', False]
	d[':ARG2'] = ['Theme', False]
	d[':ARG3'] = ['Recipient', False]
	d[':ARG4'] = ['Destination', False]

	d[':ARG0-of'] = ['Agent', True]
	d[':ARG1-of'] = ['Patient', True]
	d[':ARG2-of'] = ['Theme', True]
	d[':ARG3-of'] = ['Recipient', True]
	d[':ARG4-of'] = ['Destination', True]

	d[':part-of'] = ['PartOf', False]
	d[':month'] = ['MonthOfYear', False]
	d[':year'] = ['YearOfCentury', False]
	d[':manner'] = ['Manner', False]
	d[':manner-of'] = ['Manner', True]
	d[':location'] = ['Location', False]
	d[':location-of'] = ['Location', True]
	d[':quant'] = ['Quantity', False]
	d[':quant-of'] = ['Quantity', True]
	d[':time'] = ['Time', False]
	d[':time-of'] = ['Time', True]
	d[':mod'] = ['Theme', True]
	d[':purpose'] = ['Goal', False]
	d[':beneficiary'] = ['Beneficiary', False]
	d[':domain'] = ['Theme', False]

	return d


def is_var(var):
	'''Check if item is a variable'''
	var_pattern = re.compile('[a-z][\d]+')
	return var_pattern.match(var)


def find_first_verb(drs):
	'''Function that finds the first verb clause in the DRS and returns the variable'''
	for d in drs:
		if d.split()[2].startswith('"v.'):
			return d.split()[3]
	return False


def add_time(drs, var_count):
	''' Add time clauses for the first REF clause, so for the first b REF e, we add:
		b REF t
		b TPR t "now"
		b Time e t
		b time "n.08" t'''

	## First find the first verb in the DRS, since that creates the tense
	verb_var = find_first_verb(drs)

	## If there is no verb we do not add time
	if not verb_var:
		return drs
	else:
		## Get box count we have now
		box_count = max([int(tup.split()[0][1:]) for tup in drs])

		new_clauses = []
		did_ref = False
		for tup in drs:
			new_clauses.append(tup)
			## For the first REF we add time clauses
			if not did_ref and tup.split()[1] == 'REF' and tup.split()[2] == verb_var:
				box_var = 'b' + str(box_count+1)
				new_var = 'x' + str(var_count + 1)
				new_clauses.append('{0} REF {1}'.format(box_var, new_var))
				new_clauses.append('{0} TPR {1} "now"'.format(box_var, new_var))
				new_clauses.append('{0} time "n.08" {1}'.format(box_var, new_var))
				## The Time role clause has to occur in the same box as the REF
				new_clauses.append('{0} Time {1} {2}'.format(tup.split()[0], tup.split()[2], new_var))
				did_ref = True

	return new_clauses


def look_forward_names(cur_clauses, start_idx):
	'''When we encounter a name we look ahead in the list of clauses to see if we can rewrite it'''
	op_items = []
	remove_indices = [start_idx-1] #we filter previous item as well

	for idx in range(start_idx, len(cur_clauses)):
		cur_item = cur_clauses[idx].split()[1]
		if idx - start_idx == 0:   #first item has to be REF
			if cur_item == 'REF':
				remove_indices.append(idx)
			else:
				return False
		elif idx - start_idx == 1: #second item has to be name
			if cur_item == 'name':
				remove_indices.append(idx)
			else:
				return False
		else:
			## Check if it is an :op1 node, and if the to-be-added value is not a variable (can happen with parses)
			if cur_item.startswith('Op') and cur_item[-1].isdigit() and not is_var(cur_clauses[idx].split()[3].replace('"', '')):
				op_items.append(cur_clauses[idx].split()[3].replace('"',''))
				remove_indices.append(idx)
			else:
				if op_items: #saw :op item, succeeded in finding the rewrite rules, stop now
					return [remove_indices, '"' + "~".join(op_items) +'"']

	# Still have op-items
	if op_items: #saw :op item, succeeded in finding the rewrite rules, stop now
		return [remove_indices, '"' + "~".join(op_items) +'"']
	else:
		return False


def between_quotes(string):
	'''Return true if a value is between quotes'''
	return (string.startswith('"') and string.endswith('"')) or (string.startswith("'") and string.endswith("'"))



def get_disc_refs(drs):
	'''Get all discourse referents that occur in non-REF clauses'''
	op_boxes = ['NOT', 'POS', 'NEC', 'IMP', 'DIS', 'PRP', 'DRS', 'ANSWER', 'PARALLEL', 'CONTINUATION', 'CONTRAST', 'RESULT', 'EXPLANATION']
	disc_refs = []
	for clause in drs:
		if not clause.strip().startswith('%'):
			cur_clause = clause.split()[0:clause.split().index('%')] if '%' in clause.split() else clause.split()
			# If the identifier is not in op_boxes we found a discourse referent
			if len(cur_clause) == 3:
				if cur_clause[1] not in op_boxes and not between_quotes(cur_clause[2]):
					if cur_clause[2] not in disc_refs:
						disc_refs.append([cur_clause[0], cur_clause[2], cur_clause])
			else: # Clause has 4 items
				#Everything that is not between quotes for item 3/4 is a disc ref, except when it is box variable due to the operator
				if cur_clause[1] not in op_boxes and cur_clause[1] != 'PRP' and not between_quotes(cur_clause[2]):
					if cur_clause[2] not in disc_refs:
						disc_refs.append([cur_clause[0], cur_clause[2], cur_clause])
				if cur_clause[1] not in op_boxes and cur_clause[1] != 'PRP' and not between_quotes(cur_clause[3]):
					if cur_clause[3] not in disc_refs:
						disc_refs.append([cur_clause[0], cur_clause[3], cur_clause])
	return disc_refs


def add_ref_clauses(drs):
	'''If a discourse referent does not have a REF clause
	   to introduce it, we will still add it here'''
	refs = [x.split()[2] for x in drs if x.split()[1] == 'REF']                 # all discourse referents introduced by REF
	# Save discourse referents found in other non-REF clauses
	disc_refs = get_disc_refs(drs)
	# Add missing REF clauses
	for d in disc_refs:
		if d[1] not in refs:
			# Simply add REF clause that is missing
			add_clause = '{0} REF {1}'.format(d[0], d[1])
			drs.append(add_clause)
	return drs


def rewrite_names(cur_clauses):
	''' Names are a special case for both AMRs as DRSs. What we do is rewriting a set of 4 or more clauses like this:
		b Name x1 x2
		b REF x2
		b name "n.01" x2
		b :op1 x2 "John"
		b :op2 x2 "Williams"

		to:
		b Name x1 "John~Williams" '''

	filter_idx = []
	new_name_clauses = []
	for idx, tup in enumerate(cur_clauses):
		if tup.split()[1] == 'Name': #found a possible rewrite option
			res = look_forward_names(cur_clauses, idx+1)
			if res:

				filter_items = copy.deepcopy(res[0])
				filter_idx.append(filter_items)
				new_clause = " ".join(tup.split()[0:3]) + ' ' + res[1]
				new_name_clauses.append(new_clause)

	## Check where we reinsert the new clauses later
	insert_idx = []
	counter_extra = 0
	for val in filter_idx:
		insert_idx.append(val[0] - counter_extra)
		counter_extra += (len(val) -1)

	## Filter all unwanted items
	flat_idx = [item for sublist in filter_idx for item in sublist]
	new_clauses = [x for idx, x in enumerate(cur_clauses) if idx not in flat_idx]

	## Add new items
	for idx, i in enumerate(insert_idx):
		new_clauses.insert(i, new_name_clauses[idx])

	return new_clauses


def remove_by_type(drs, remove_roles):
	'''Remove all DRS clauses of a certain type'''
	new_clauses = []
	for clause in drs:
		if clause.split()[1] not in remove_roles: #Check if we remove all clauses with this role (e.g. Wiki)
			new_clauses.append(clause)
	return new_clauses


def get_concept(conc, prev_arg):
	'''DRSs do concepts a bit different than AMRs, check here if it is a noun or verb, and return first sense
	   Also returns whether we want to add the clause (not the case for I/you pronouns)'''

	if len(re.findall("-[\d]+", conc)) > 0:     #verbs look like this in AMRs: work-01
		verb = "-".join(conc.split('-')[0:-1])  #be careful to take right verb/num for verbs such as look-down-01
		num = '01'                              #default first sense
		return '{0} "v.{1}"'.format(verb, num), True
	else:
		## It's not a verb, do different transformations for pronouns
		if conc == 'i' or conc == 'we':
			return '"speaker"', False
		elif conc == 'you':
			return '"hearer"', False
		elif conc == 'he':
			return 'male "n.02"', True
		elif conc == 'she':
			return 'female "n.02"', True
		elif conc == 'it':
			return 'thing "n.12"', True
		elif conc == 'they':
			return 'person "n.01"', True
		## If previous argument was a modifier, we return adjective as tag
		elif prev_arg == ':mod':
			return '{0} "a.01"'.format(conc), True
		else: #normal case, concept with default sense
			return '{0} "n.01"'.format(conc), True


def get_argument(arg, arg_dict):
	'''Get argument if in dictionary'''
	## First check if we have a rule for this argument
	if arg in arg_dict:
		return arg_dict[arg]

	## Else convert it into a role, remove the leading ':' and make the first character uppercase
	try:
		final_arg = arg[1].upper() + arg[2:]
	except:
		print "WARNING: strange AMR argument", arg, "return Agent as default"
		final_arg = "Agent"

	return [final_arg, False]


def get_var_value(var, var_dict, add=True):
	'''Get correct value for the variable'''
	if var in var_dict:
		if add:
			var_dict[var][1] += 1
		return var_dict[var][0], var_dict
	else:
		## All variables (if not b) start with x
		var_dict[var] = ['x' + str(len(var_dict) + 1), 0]
		if add:
			var_dict[var][1] += 1
		return var_dict[var][0], var_dict


def remove_by_value(value, var_dict):
	'''Remove a dictionary item if it contains a certain value'''
	remove_key = ''
	for key in var_dict:
		if var_dict[key][0] == value and var_dict[key][1] == 1: #only do if occurred once
			remove_key = key
	if remove_key:
		del var_dict[remove_key]
	return var_dict, remove_key


def get_drs_from_amr(amr, cur_clauses, arg_dict, level, var_dict, box_num, prev_box_num, cur_arg, removed_keys):
	'''Function that takes AMR as input and returns relevant DRS clauses'''
	split_amr = amr.replace(')', ' ) ').replace('(', ' ( ' ).split()[1:] #skip first bracket so it's easier to handle the different levels
	new_amr = []
	separate_amr = False

	## Keep track of how we started
	old_level = level
	cur_box_num = box_num

	for idx, ent in enumerate(split_amr):
		## At the current level we check if we have to add clauses, or change the level to start a new AMR
		if level == old_level:
			## We start or continue with the base AMR
			if ent == '(':
				if split_amr[idx-1].startswith(':'):
					cur_arg = split_amr[idx-1]
				separate_amr = True
				level += 1
				new_amr.append(ent)
			elif ent == ')':
				level -= 1
			elif ent == '/':
				## Found a variable + concept here
				cur_var, var_dict = get_var_value(split_amr[idx-1], var_dict, add=True)   #current variable is previous item
				cur_concept, add_clause = get_concept(split_amr[idx+1], cur_arg) #current concept is next item
				## Check if we want to add the clauses (for I/you pronouns we just change the current variable to speaker/hearer)
				if add_clause or not cur_clauses: # #some AMRs look like this: (i / i), then just add I the normal way
					box_var = 'b' + str(box_num)
					cur_clauses.append('{0} REF {1}'.format(box_var, cur_var))
					cur_clauses.append('{0} {1} {2}'.format(box_var, cur_concept, cur_var))
				else:
					## We see a I/you pronoun now, means that we have to change the previous clause to add "speaker" or "hearer"
					if len(cur_clauses[-1].split()) == 4: #only do it if it is possible
						# This also means that we have to take this replacement into account in our var_dict
						var_dict, removed_key = remove_by_value(cur_clauses[-1].split()[-1], var_dict)
						if removed_key:
							removed_keys[removed_key] = cur_concept
						cur_clauses = cur_clauses[0:-1] + [" ".join(cur_clauses[-1].split()[0:3]) + ' ' + cur_concept]

			elif ent.startswith(':'):
				## Argument here, so we might want to add clauses by looking ahead
				argument, switch_variables = get_argument(ent, arg_dict)
				box_var = 'b' + str(cur_box_num)
				if split_amr[idx+1] == '(':     #new full AMR, add clauses for current argument here
					next_var, var_dict = get_var_value(split_amr[idx+2], var_dict, add=False)
					## Check if we switch variables, then add clauses
					if switch_variables:
						cur_clauses.append('{0} {1} {2} {3}'.format(box_var, argument, next_var, cur_var))
					else:
						cur_clauses.append('{0} {1} {2} {3}'.format(box_var, argument, cur_var, next_var))
				else:
					## No full AMR but just a value (e.g. :quant 500) or a reference to a previous variable (e.g. :mod i2)
					## Check if the value is in our var_dict, if so add that variable, if not, just add value
					if split_amr[idx+1] in [key for key in var_dict]:
						value = var_dict[split_amr[idx+1]][0]
						cur_clauses.append('{0} {1} {2} {3}'.format(box_var, argument, cur_var, value))
					elif split_amr[idx+1] in removed_keys: #we removed this variable because we added "speaker" or "hearer", add that again now
						value = removed_keys[split_amr[idx+1]]
						cur_clauses.append('{0} {1} {2} {3}'.format(box_var, argument, cur_var, value))
					## Polarity is a special case, add a NOT clause with a fresh box
					elif ent == ':polarity':
						box_num += 1
						box_var = 'b' + str(box_num)
						cur_clauses.append('{0} NOT b{1}'.format(box_var, cur_box_num))
					else:
						value = split_amr[idx+1]
						cur_clauses.append('{0} {1} {2} "{3}"'.format(box_var, argument, cur_var, value))
		else:
			## Else we are adding a new AMR which we will deal with recursively, so first add all information, then process the whole thing
			if ent == '(':
				level += 1
				new_amr.append(ent)
			elif ent == ')':
				level -= 1
				new_amr.append(ent)
				if level == old_level and separate_amr:
					## If we are at our start level and we were adding an AMR: we will process that AMR here (recursive step!)
					## If we go to a next level, give it a new box
					cur_clauses,_ , box_num = get_drs_from_amr(" ".join(new_amr), cur_clauses, arg_dict, level, var_dict, box_num + 1, cur_box_num, cur_arg, removed_keys)

					## We are adding the new AMR now so reset
					new_amr = []
					separate_amr = False
			else:
				new_amr.append(ent)
	return cur_clauses, len(var_dict), box_num


if __name__ == "__main__":
	args = create_arg_parser()

	## Get amrs in single line format, keep comments if present
	if args.oneline:
		amrs = [['', y] for y in [x.strip() for x in open(args.input_file, 'r')]]
	else:
		amrs = get_amrs(args.input_file)

	## Get translation dict for arguments between AMRs and DRSs
	arg_dict = get_argument_dict()

	## Loop over AMRs and transform each one to DRS
	with open(args.drs_file, 'w') as out_f:
		for comments, amr in amrs:
			## Main step: transform AMR to list of clauses (recursive function)
			drs, var_count, _ = get_drs_from_amr(amr, [], arg_dict, 0, {}, 0, 0, '', {})
			## Names are a special case, rewrite those here
			drs = rewrite_names(drs)

			## Add time clauses (since there is no time in AMRs)
			drs = add_time(drs, var_count)

			## Print output
			for d in drs:
				out_f.write(d.strip() + '\n')
			out_f.write('\n')
	print "Changed {0} AMRs to DRS".format(len(amrs))


