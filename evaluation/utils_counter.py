## File with utils for Counter
import sys, os, re, codecs, random


def dummy_drs():
	'''Return dummy DRS in clause format'''
	# Add random string so it never matches with anything
	rand_string = "".join([random.choice(['a','b','c','d','e','f','g','h']) for x in range(10)])
	return [['b1', 'REF', 'x1'], ['b1', 'alwayswrongconcept' + rand_string, '"n.01"', 'x1']]


def spar_drs():
	'''Return the SPAR DRS of "He smiled"'''
	return [['b1', 'REF', 'x1'],
	['b1', 'male', '"n.02"', 'x1'],
	['b3', 'REF', 't1'],
	['b3', 'TPR', 't1', '"now"'],
	['b3', 'time', '"n.08"', 't1'],
	['k0', 'Agent', 'e1', 'x1'],
	['k0', 'REF', 'e1'],
	['k0', 'Time', 'e1', 't1'],
	['k0', 'smile', '"v.01"', 'e1']]


def write_to_file(lst, file_name):
	'''Write a list to file with newline after each item'''
	print_l = [l.encode('utf-8') for l in lst]
	out_file = codecs.open(file_name, "w", "utf-8")
	for item in print_l:
		out_file.write(item + '\n')


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
	if precision < 0.0 or precision > 1.0 or recall < 0.0 or recall > 1.0:
		raise ValueError("Precision and recall should never be outside (0.0-1.0), now {0} and {1}".format(precision, recall))
	
	if (precision + recall) != 0:
		f_score = round(2 * precision * recall / (precision + recall), significant)
		if f_only:
			return f_score
		else:
			return precision, recall, f_score
	else:
		if f_only:
			return 0.00
		else:
			return precision, recall, 0.00


def between_quotes(string):
	'''Return true if a value is between quotes'''
	return (string.startswith('"') and string.endswith('"')) or (string.startswith("'") and string.endswith("'"))


def all_upper(string):
	'''Checks if all items in a string are uppercase'''
	return all(x.isupper() for x in string)


def is_role(string):
	'''Check if string is in the format of a role'''
	return string[0].isupper() and any(x.islower() for x in string[1:]) and all(x.islower() or x.isupper() or x == '-' for x in string)


def merge_dicts(all_dicts, args):
	'''Merge a list of dictionaries in a single dict'''
	new_dict = {}
	for d in all_dicts:
		for key in d:
			if key not in new_dict:
				new_dict[key] = d[key]
			else:
				new_dict[key] = [x + y for x,y in zip(new_dict[key], d[key])]
	
	# Create new dictionary with F-scores so we can easily sort later
	f_dict = {}
	for key in new_dict: 
		f_dict[key] = compute_f(new_dict[key][0], new_dict[key][1], new_dict[key][2], args.significant, True)
	return new_dict, f_dict


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
