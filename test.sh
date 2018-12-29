#!/bin/sh
# run all example calls from readme

(
    cd evaluation
    python clf_referee.py ../data/boxer_parse_dev.txt
    python counter.py -f1 ../data/boxer_parse_dev.txt -f2 ../data/dev.txt
    python counter.py -f1 ../data/boxer_parse_dev.txt -f2 ../data/dev.txt -r 20 -s no
    python counter.py -f1 ../data/boxer_parse_dev.txt -f2 ../data/dev.txt -p 4 -s no
    python counter.py -f1 ../data/boxer_parse_dev.txt -f2 ../data/dev.txt -prin -s conc
    python counter.py -f1 ../data/boxer_parse_dev.txt -f2 ../data/dev.txt -prin -ds 10
    python counter.py -f1 ..//data/baseline_drs.txt -f2 ../data/baseline_drs.txt -prin
    python counter.py -f1 ../data/boxer_parse_dev.txt -f2 ../data/dev.txt -p 1 -ms
    python counter.py -f1 ../data/baseline_drs.txt -f2 ../data/dev.txt -prin --baseline
    python counter.py -f1 ../data/boxer_parse_dev.txt -f2 ../data/dev.txt -r 50 -dse
)
(
    cd parsing
    python spar.py ../data/amr_sample.txt
    python amr2drs.py -i ../data/amr_sample.txt -d OUTPUT_FILE
)
