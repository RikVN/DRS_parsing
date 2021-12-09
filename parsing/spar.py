import sys

'''Baseline parser for DRSs -- always outputs the same set of clauses for a given input
   Each input sentence should be on it's own line, e.g. a file with 200 sentences will
   result in 200 DRS clauses in the output'''

## Usage: python spar.py [FILE]
if __name__ == '__main__':
    # Baseline is DRS clause set for sentence "I sacked him.".
    # Based on the training set of PMB release 4.0.0 (English)
    # p04/d2514 in the PMB
    baseline = \
"""
b1 REF x1             % I [0...1]
b1 EQU x1 "speaker"   % I [0...1]
b1 person "n.01" x1   % I [0...1]
b1 REF e1             % sacked [2...8]
b1 REF t1             % sacked [2...8]
b1 Agent e1 x1        % sacked [2...8]
b1 TPR t1 "now"       % sacked [2...8]
b1 Theme e1 x2        % sacked [2...8]
b1 Time e1 t1         % sacked [2...8]
b1 sack "v.02" e1     % sacked [2...8]
b1 time "n.08" t1     % sacked [2...8]
b2 REF x2             % him [9...12]
b2 PRESUPPOSITION b1  % him [9...12]
b2 male "n.02" x2     % him [9...12]
"""

    for line in open(sys.argv[1], 'r'):
        print(baseline.strip() + '\n')
