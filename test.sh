#!/bin/bash
# Run example Counter/Referee calls from the README

set -eu -o pipefail
# Set release here
REL="pmb-4.0.0"

cd evaluation
# Check referee
python clf_referee.py ../data/$REL/gold/dev.txt
# Basic usage
python counter.py -f1 ../data/$REL/gold/dev.txt -f2 ../data/$REL/gold/dev.txt -g clf_signature.yaml
# More restarts, no smart initialization
python counter.py -f1 ../data/$REL/gold/dev.txt -f2 ../data/$REL/gold/dev.txt -r 20 -s no -g clf_signature.yaml
# 4 parallel threads
python counter.py -f1 ../data/$REL/gold/dev.txt -f2 ../data/$REL/gold/dev.txt -p 4 -s no -g clf_signature.yaml
# Print specific output
python counter.py -f1 ../data/$REL/gold/dev.txt -f2 ../data/$REL/gold/dev.txt -prin -s conc -g clf_signature.yaml
# Print more detailed stats for clauses that occur more than 10 times
python counter.py -f1 ../data/$REL/gold/dev.txt -f2 ../data/$REL/gold/dev.txt -prin -ds 10 -g clf_signature.yaml
# Doing a single DRS, printing the matching and non-matching clauses:
python counter.py -f1 ..//data/pmb-3.0.0/baseline_drs.txt -f2 ../data/pmb-3.0.0/baseline_drs.txt -prin -g clf_signature.yaml
# Outputting a score for each DRS (note we use -p 1 to not mess up printing):
python counter.py -f1 ../data/$REL/gold/dev.txt -f2 ../data/$REL/gold/dev.txt -p 1 -ms -g clf_signature.yaml
# Doing a baseline experiment, comparing a single DRS to a number of DRSs:
#python counter.py -f1 ../data/$REL/baseline_drs.txt -f2 ../data/$REL/gold/dev.txt -prin --baseline -g clf_signature.yaml
# Doing an experiment by replacing all senses in both files by a default sense ("n.01"), removing the need for word sense disambiguation:
python counter.py -f1 ../data/$REL/gold/dev.txt -f2 ../data/$REL/gold/dev.txt -r 50 -dse -g clf_signature.yaml

# Test SPAR
cd ../parsing
python spar.py ../data/$REL/gold/dev.txt.raw
# Test referee on Boxer output
cd ../evaluation
python clf_referee.py ../data/$REL/gold/dev.txt


