import sys

'''Baseline parser for DRSs -- always outputs the same set of clauses for a given input
   Each input sentence should be on it's own line, e.g. a file with 200 sentences will
   result in 200 DRS clauses in the output'''

## Usage: python spar.py [FILE]
if __name__ == '__main__':
    # Baseline is DRS clause set for sentence "He smiled".
    baseline = \
"""
b1 REF x1
b1 male "n.02" x1
b3 REF t1
b3 TPR t1 "now"
b3 time "n.08" t1
k0 Agent e1 x1
k0 REF e1
k0 Time e1 t1
k0 smile "v.01" e1
"""

    for line in open(sys.argv[1], 'r'):
        print(baseline.strip() + '\n')
