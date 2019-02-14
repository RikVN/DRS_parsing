#!/bin/sh
# run all example calls from readme

(
    cd evaluation
<<<<<<< HEAD
    python clf_referee.py ../data/pmb-2.2.0/boxer_parse_dev.txt
    python counter.py -f1 ../data/pmb-2.2.0/boxer_parse_dev.txt -f2 ../data/pmb-2.2.0/gold/dev.txt
    python counter.py -f1 ../data/pmb-2.2.0/boxer_parse_dev.txt -f2 ../data/pmb-2.2.0/gold/dev.txt -r 20 -s no
    python counter.py -f1 ../data/pmb-2.2.0/boxer_parse_dev.txt -f2 ../data/pmb-2.2.0/gold/dev.txt -p 4 -s no
    python counter.py -f1 ../data/pmb-2.2.0/boxer_parse_dev.txt -f2 ../data/pmb-2.2.0/gold/dev.txt -prin -s conc
    python counter.py -f1 ../data/pmb-2.2.0/boxer_parse_dev.txt -f2 ../data/pmb-2.2.0/gold/dev.txt -prin -ds 10
    python counter.py -f1 ..//data/pmb-2.2.0/baseline_drs.txt -f2 ../data/pmb-2.2.0/baseline_drs.txt -prin
    python counter.py -f1 ../data/pmb-2.2.0/boxer_parse_dev.txt -f2 ../data/pmb-2.2.0/gold/dev.txt -p 1 -ms
    python counter.py -f1 ../data/pmb-2.2.0/baseline_drs.txt -f2 ../data/pmb-2.2.0/gold/dev.txt -prin --baseline
    python counter.py -f1 ../data/pmb-2.2.0/boxer_parse_dev.txt -f2 ../data/pmb-2.2.0/gold/dev.txt -r 50 -dse
)
(
    cd parsing
    python spar.py ../data/pmb-2.2.0/gold/dev.txt.raw
=======
    python clf_referee.py ../data/pmb-2.1.0/boxer_parse_dev.txt
    python counter.py -f1 ../data/pmb-2.1.0/boxer_parse_dev.txt -f2 ../data/pmb-2.1.0/dev.txt
    python counter.py -f1 ../data/pmb-2.1.0/boxer_parse_dev.txt -f2 ../data/pmb-2.1.0/dev.txt -r 20 -s no
    python counter.py -f1 ../data/pmb-2.1.0/boxer_parse_dev.txt -f2 ../data/pmb-2.1.0/dev.txt -p 4 -s no
    python counter.py -f1 ../data/pmb-2.1.0/boxer_parse_dev.txt -f2 ../data/pmb-2.1.0/dev.txt -prin -s conc
    python counter.py -f1 ../data/pmb-2.1.0/boxer_parse_dev.txt -f2 ../data/pmb-2.1.0/dev.txt -prin -ds 10
    python counter.py -f1 ..//data/pmb-2.1.0/baseline_drs.txt -f2 ../data/pmb-2.1.0/baseline_drs.txt -prin
    python counter.py -f1 ../data/pmb-2.1.0/boxer_parse_dev.txt -f2 ../data/pmb-2.1.0/dev.txt -p 1 -ms
    python counter.py -f1 ../data/pmb-2.1.0/baseline_drs.txt -f2 ../data/pmb-2.1.0/dev.txt -prin --baseline
    python counter.py -f1 ../data/pmb-2.1.0/boxer_parse_dev.txt -f2 ../data/pmb-2.1.0/dev.txt -r 50 -dse
)
(
    cd parsing
    python spar.py ../data/pmb-2.1.0/dev.txt.raw
>>>>>>> e150879aefd236a985f2e10caa7fee49bcb01cfb
    python amr2drs.py -i ../data/amr_sample.txt -d OUTPUT_FILE
)
