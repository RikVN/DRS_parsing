import sys

'''Baseline parser for DRSs -- always outputs the same set of clauses for a given input
   Each input sentence should be on it's own line, e.g. a file with 200 sentences will
   result in 200 DRS clauses in the output'''

## Usage: python spar.py [FILE]
if __name__ == '__main__':
    # Baseline is DRS clause set for sentence "Tom voted for himself".
    # Based on the training set of PMB release 2.2.0 (English)
	# p18/d1966 in the PMB
    baseline = \
"""
b1 REF x1
b1 Name x1 "tom"
b1 male "n.02" x1
b2 REF e1
b2 REF t1
b2 Agent e1 x1
b2 TPR t1 "now"
b2 Time e1 t1
b2 time "n.08" t1
b2 vote "v.01" e1
b2 Theme e1 x1
"""

    for line in open(sys.argv[1], 'r'):
        print(baseline.strip() + '\n')
