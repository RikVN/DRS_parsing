## File with utils for Counter
import sys, os, re, codecs, random


def dummy_drs(list_output=True):
    '''Return dummy DRS in clause format'''
    # Add random string so it never matches with anything
    rand_string = "".join([random.choice(['a','b','c','d','e','f','g','h']) for x in range(10)])
    dummy = [['b1', 'REF', 'x1'], ['b1', 'alwayswrongconcept' + rand_string, '"n.01"', 'x1']]
    if list_output:
        return dummy
    else:
        return [" ".join(x) for x in dummy]

def spar_drs(list_output=True):
    '''Return the SPAR DRS of "He bragged about it."
       SPAR for PMB release 3.0.0'''
    spar =  [['b1', 'REF', 'x1'],
            ['b1', 'PRESUPPOSITION', 'b2'],
            ['b1', 'male', '"n.02"', 'x1'],
            ['b2', 'REF', 'e1'],
            ['b2', 'REF', 't1'],
            ['b2', 'Agent', 'e1', 'x1'],
            ['b2', 'TPR', 't1', '"now"'],
            ['b2', 'Time', 'e1', 't1'],
            ['b2', 'brag', '"v.01"', 'e1'],
            ['b2', 'time', '"n.08"', 't1'],
            ['b2', 'Theme', 'e1', 'x2'],
            ['b3', 'REF', 'x2'],
            ['b3', 'PRESUPPOSITION', 'b2'],
            ['b3', 'entity', '"n.01"', 'x2']]
    if list_output:
        return spar
    else:
        return [" ".join(x) for x in spar]


def write_to_file(lst, out_file):
    '''Write list to file'''
    with open(out_file, "w") as out_f:
        for line in lst:
            out_f.write(line.strip() + '\n')
    out_f.close()


def write_list_of_lists(lst, out_file, extra_new_line=True):
    '''Write lists of lists to file'''
    with open(out_file, "w") as out_f:
        for sub_list in lst:
            for item in sub_list:
                out_f.write(item.strip() + '\n')
            if extra_new_line:
                out_f.write('\n')
    out_f.close()


def write_list_of_lists_of_lists(lst, out_file, extra_new_line=True):
    '''Write list of lists of lists to file'''
    with open(out_file, "w") as out_f:
        for sub_list in lst:
            for item in sub_list:
                for line in item:
                    out_f.write(line.strip() + '\n')
                if extra_new_line:
                    out_f.write('\n')
            if extra_new_line:
                out_f.write('\n')
    out_f.close()


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


def multiply_if_float(string, first_item, multiplier=100, do_round=4):
    '''Multiply in string by 100 if it's a float between 0 and 1
       Return value as a string, not float
       Hacky fix for not doing for whole numbers: if first item starts with "#",
       we just return the string'''
    if first_item.strip().startswith("#"):
        return string
    try:
        float(string)
        if float(string) > 0 and float(string) <= 1 and "." in string:
            return str(round(float(string) * multiplier, do_round))
        else:
            return string
    except:
        return string


def create_tab_list(print_rows, print_item, joiner, do_percentage=False):
    '''For multiple rows, return row of strings nicely separated by tabs'''
    print_rows = [[str(x) for x in item] for item in print_rows]
    # Check if we want to change floats between 0 and 1 to their percentage between 0-100
    # So essentially multiply each float >0 and <1 with 100
    if do_percentage:
        print_rows = [[multiply_if_float(x, item[0]) for x in item] for item in print_rows]
    col_widths = []
    if print_item:
        return_rows = [print_item]
    else:
        return_rows = []
    if print_rows:
        for idx in range(len(print_rows[0])):  # for nice printing, calculate max column length
            try:
                col_widths.append(max([len(x[idx].decode('utf-8')) for x in print_rows]) + 1)
            except AttributeError:
                # in Python 3 a string is utf8 and has no decode
                col_widths.append(max([len(x[idx]) for x in print_rows]) + 1)

        for idx, row in enumerate(print_rows):  # print rows here, adjusted for column width
            try:
                return_rows.append(joiner.join(word.decode('utf-8').ljust(col_widths[col_idx]) for col_idx, word in enumerate(row)))
            except AttributeError:
                # in Python 3 a string is utf8 and has no decode
                return_rows.append(joiner.join(word.ljust(col_widths[col_idx]) for col_idx, word in enumerate(row)))
    return return_rows
