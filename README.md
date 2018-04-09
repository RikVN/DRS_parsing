# DRS parsing

This folder contains three scripts:

* counter.py - for evaluating scoped meaning representations
* spar.py    - baseline DRS parser
* amr2drs.py - automatically convertings AMRs to DRSs

## Counter: evaluating scoped meaning representations

Counter is a tool that is able to evaluate scoped meaning representations, in this case Discourse Representation Structures (DRSs). It compares sets of clauses and outputs an F-score. The tool can be used to evaluate different DRS-parsers.
It is heavily based on [SMATCH](https://github.com/snowblink14/smatch), with a few modifications. It was developed as part of the [Parallel Meaning Bank](http:/pmb.let.rug.nl).

### Getting Started

```
git clone https://github.com/RikVN/DRS_parsing
```

#### Prerequisites

Counter runs with Python 2.7. The memory component needs [psutil](https://pypi.python.org/pypi/psutil).

### Differences with SMATCH ###

* Counter takes clauses directly as input
* Counter normalizes WordNet concepts to their synset IDs
* Counter can process clauses that contain three variables (instead of max 2)
* Counter can process multiple DRSs in parallel
* Counter can do baseline experiments, comparing a single DRS to a set of DRSs
* Counter can print more detailed output, such as specific matching clauses and F-scores for each smart mapping
* Counter can have a maximum number of clauses for a single DRS, ignoring DRS-pairs with more clauses
* Counter can have a memory limit per parallel thread
* Counter stops restarting if a precision of 1.0 is already found
* Since DRSs have variable two types, Counter ensures that different variable types can never match

### Input format ###

DRSs are sets of clauses, with each clause on a new line and with DRSs separated by a white line. Lines starting with '%' are ignored. The whitespace separates the values of a clause, so it can be spaces or tabs. Everything after a '%' is ignored, so it is possible to put a comment there.

A DRS file looks like this:

```
% DRS 1
% He is a baseball player.
b1 REF x1                     % He 
b1 male "n.02" x1             % He 
k0 EQU t1 "now"               % is 
k0 EQU x1 x2                  % is 
k0 REF t1                     % is 
k0 Time x3 t1                 % is 
k0 time "n.08" t1             % is 
k0 REF x2                     % a 
k0 REF x3                     % baseball~player 
k0 Role x2 x3                 % baseball~player 
k0 baseball_player "n.01" x3  % baseball~player 
k0 person "n.01" x2           % baseball~player

% DRS2
% Everybody laughs .
b2 REF x1            % Everybody 
b2 person "n.01" x1  % Everybody 
k0 IMP b2 b3         % Everybody 
etc
```

#### Structure ####

DRSs in clause format follow a strict format. The second value in the clause identifies its type. Operators are always in capitals (e.g. REF, POS, IMP), concepts always start with a lowercase letter (e.g. person), while roles start with a capital, followed by letters (at least one lowercase) or dashes (e.g. Patient, Co-Agent). Clauses can have two types of variable, box variables and other variables. The type of variable can be determined by the place it occurs in a clause, e.g. the first variable is always a box variable, while non-first variables of concepts are always of the other type. This means that you can name the variables to whatever is convenient for you, but realize that using same name in a DRS matches the same variable.

D-match checks if the input structure is valid according to these standards. They are not all described here, for a full overview please see the [DRS page](http://pmb.let.rug.nl/drs.php) on the PMB website.

Actual examples of our DRSs can be found in the **data** folder.

### Running Counter

The most vanilla version can be run like this:

```
python counter.py -f1 FILE1 -f2 FILE2
```

Running with our example data:

```
python counter.py -f1 data/release_boxer.txt -f2 data/release_gold.txt
```

#### Parameter options ####

```
-f1   : First file with DRS clauses, usually produced file
-f2   : Second file with DRS clauses, usually gold file
-r    : Number of restarts used
-m    : Max number of clauses for a DRS to still take them into account - default 0 means no limit
-p    : Number of parallel threads to use (default 1)
-s    : What kind of smart initial mapping we use:
	    -no   No smart mappings
	    -conc Smart mapping based on matching concepts (their match is likely to be in the optimal mapping)
-prin : Print more specific output, such as individual (average) F-scores for the smart initial mappings, and the matching and non-matching clauses
-sig  : Number of significant digits to output (default 4)
-b    : Use this for baseline experiments, comparing a single DRS to a list of DRSs. Produced DRS file should contain a single DRS.
-ms   : Instead of averaging the score, output a score for each DRS
-msf  : Output individual F-scores per DRS-pair to a file, making it easier to do statistics
-pr   : Also output precison and recall
-pa   : Partial matching of clauses instead of full matching -- experimental setting!
        Means that the clauses x1 work "n.01" x2 and x1 run "n.01" x2 are able to match for 0.75, for example
-ic   : Include REF clauses when matching (otherwise they are ignored because they inflate the matching)
-v    : Verbose output
-vv   : Very verbose output 
```

#### Running some tests ####

Run with 50 restarts, also showing precision and recall, with 4 parallel threads to speed things up:

```
python counter.py -f1 data/release_boxer.txt -f2 data/release_gold.txt -pr -r 50 -p 4 -s no
```

Print specific output, while only using the smart mapping based on concepts:

```
python counter.py -f1 data/release_boxer.txt -f2 data/release_gold.txt -pr -r 100 -p 4 -prin -s conc
```

Only take smaller DRSs into account, with a maximum of 10 clauses:

```
python counter.py -f1 data/release_boxer.txt -f2 data/release_gold.txt -pr -r 100 -p 4 -prin -m 10
```

Doing a single DRS, printing the matching and non-matching clauses:

```
python counter.py -f1 data/baseline_drs.txt -f2 data/baseline_drs.txt -pr -r 100 -p 1 -prin
```

Outputting a score for each DRS and writing them to a file (note we use -p 1 to not mess up printing):

```
python counter.py -f1 data/release_boxer.txt -f2 data/release_gold.txt -pr -r 100 -p 1 -ms -msf idv_scores.txt
```

Doing a baseline experiment, comparing a single DRS to a number of DRSs:

```
python counter.py -f1 data/baseline_drs.txt -f2 data/release_gold.txt -pr -r 100 -p 4 -prin --baseline
```

### Application ###

Counter is currently used in the [Parallel Meaning Bank](http://pmb.let.rug.nl/explorer/explore.php) to estimate the semantic similarity between DRSs of different languages. Come check it out!

## Parsing

The parsing folder includes two baseline parsers. The first is SPAR, which simply outputs a baseline DRS for each input sentence. The input file should contain a sentence on each line, empty lines will be ignored. You can run it like this:

```
python spar.py FILE
```

The second parser is amr2drs.py. It recursively converts an AMR to a DRS based on hand-crafted rules. The idea is based on [this paper](http://www.anthology.aclweb.org/J/J16/J16-3006.pdf). It translates AMR relations to DRS relations based on a translation dictionary (e.g. :ARG0 -> Agent, :purpose -> Goal). Since AMRs do not contain tense, it adds a default past tense to each DRS. For some concepts we have concept-specific rules, e.g. she -> female.n.02.

It takes a file with AMR parses as input. Use --oneline if the each AMR is on its own line, otherwise the AMRs should be separated by empty lines. You can run it like this:

```
python amr2drs.py -i data/amr_sample.txt -d OUTPUT_FILE
``` 

An existing AMR parser is available [here](https://github.com/RikVN/AMR).

## Author

* **Rik van Noord** - PhD-student at University of Groningen - [Personal website](http://www.rikvannoord.nl)

## Paper ##

If you use Counter, amr2drs or SPAR, please refer to our [LREC paper](http://www.let.rug.nl/rob/doc/lrec2018.pdf):

Rik van Noord, Lasha Abzianidze, Hessel Haagsma, and Johan Bos, 2018. **Evaluating scoped meaning representations**. In Proceedings of the Eleventh International Conference on Language Resources andEvaluation (LREC 2018), Miyazaki, Japan

@inproceedings{vanNoordLREC:2018,
   title     = {Evaluating Scoped Meaning Representations},
   author    = {van Noord, Rik and Abzianidze, Lasha and Haagsma, Hessel and Bos, Johan},
   booktitle = {Proceedings of the Eleventh International Conference on Language Resources and Evaluation (LREC 2018)},
   address   = {Miyazaki, Japan},
   year      = {2018}
}

## Acknowledgments

* Thanks to [SMATCH](https://github.com/snowblink14/smatch) for publishing their code open source.
* All members of the [Parallel Meaning Bank](http://pmb.let.rug.nl)
