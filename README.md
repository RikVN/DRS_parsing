

# DRS parsing

This folder contains four scripts:

* evaluation/
  * counter.py     - for evaluating scoped meaning representations (DRSs)
  * clf_referee.py - extensive format check of produced DRSs
* parsing/
  * spar.py        - baseline DRS parser
  * amr2drs.py     - automatically converting AMRs to DRSs

## Getting Started

```
git clone https://github.com/RikVN/DRS_parsing
```

### Prerequisites

All scripts are written in Python 2.7 (but should work with Python 3.5+).
Install requirements using:
<<<<<<< HEAD

```
pip install -r requirements.txt
```

## Counter: evaluating scoped meaning representations

=======

```
pip install -r requirements.txt
```

## Counter: evaluating scoped meaning representations

>>>>>>> e150879aefd236a985f2e10caa7fee49bcb01cfb
Counter is a tool that is able to evaluate scoped meaning representations, in this case Discourse Representation Structures (DRSs). It compares sets of clauses and outputs an F-score. The tool can be used to evaluate different DRS-parsers. It is based on [SMATCH](https://github.com/snowblink14/smatch), with a number of modifications. It was developed as part of the [Parallel Meaning Bank](http:/pmb.let.rug.nl).

### Differences with SMATCH ###

* Counter is for evaluating DRSs, not AMRs
* Counter takes clauses directly as input
* Counter normalizes WordNet concepts to their synset IDs (see evaluation/wordnet_dict_en.py)
* Counter can process clauses that contain three variables (instead of max 2)
* Counter can process multiple DRSs in parallel
* Counter can do baseline experiments, comparing a single DRS to a set of DRSs
* Counter can print more detailed output, such as specific matching clauses and F-scores for the smart mapping
* Counter can have a memory limit per parallel thread
* Counter ensures that different variable types can never match
* Counter can do multiple experiments regarding generalization of the input

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

#### Format checking ####

DRSs in clause format follow a strict format. The second value in the clause identifies its type. We distinguish between DRS operators (e.g. REF, POS, IMP), semantic roles (e.g. Agent, Time, Location) and WordNet concepts (work "n.01"). These are closed classes. For a full list of accepted DRS operators and semantic roles please see `clf_signature.yaml`. We do accept concepts that are not in WordNet, however be aware that they can then never match with a clause in the gold standard. 

Clauses can have two types of variable, box variables and other variables. The type of variable can be determined by the place it occurs in a clause, e.g. the first variable is always a box variable. This means that you can name the variables to whatever is convenient for you, but realize that using the same name in a DRS matches the same variable.

If all clauses are correctly formatted syntactically, they do not necessarily form a well-formed DRS (e.g. translatable into a first-order logic formula without free occurrences of a variable). To check if the input is well-formed, we use a format checker called Referee (see `clf_referee.py` by [Lasha Abzianidze](https://sites.google.com/site/lashabzianidze/home)). Referee does the following things:
<<<<<<< HEAD

* Checks individual clauses on well-formedness (distinguishing between box and entity variables)
* Recovers all subordinate relations between boxes in such a way that free occurrences of variables are avoided (if possible)
* Makes sure that there are no free occurrences of variables
* Checks that the subordinate relation is loop-free.
* Finds a unique main box (if exists)

Counter uses Referee to determine whether the input is valid, and throws an error otherwise. The Referee script can also be run separately to spot ill-formed DRSs (with or without the signature file):
```
python clf_referee.py clfs.txt  		      # without the signature
python clf_referee.py clfs.txt -s clf_signature.yaml  # with the signature
```
When Referee is run without signature, it assumes simple heuristics for operators. Roles are in initial caps, comparison operators (e.g., temporal and spatial) in 3-letter all caps, and discourse relations in >3-letter all caps. With a specified signature, Referee is stricter as the signature restricts a set of allowed roles, comparison operators and discourse relatons.  

Counter contains a setting to automatically replace ill-formed DRSs by either a dummy DRS (-ill dummy) or the SPAR default DRS (-ill spar) to make sure you can still get a score when producing ill-formed output.

#### Data ####

The data folder contains the train/dev split for release 2.1.0 and train/dev/test split for release 2.2.0. **Note that these splits are different**. Our annotation is data-driven, meaning we add certain phenomena at the time. We feel that if there are new phenomena in the training set, this should also be reflected in the suggested dev/test splits. Therefore, those splits also change per release.

This data is also available on [the PMB webpage](http://pmb.let.rug.nl/data.php), but here it is already in a more convenient format.

The data for release 2.2.0 contains these data types:

* **Gold** - fully manually annotated
* **Silver** - partially manually annotated
* **Bronze** - no manual annotations involved

Note that this means that the silver and bronze data can be pretty far away from gold standard. Use at your own risk. The data for bronze is split in two parts to circumvent Githubs size limit of 100MB.
=======

* Checks individual clauses on well-formedness (distinguishing between box and entity variables)
* Recovers all subordinate relations between boxes in such a way that free occurrences of variables are avoided (if possible)
* Makes sure that there are no free occurrences of variables
* Checks that the subordinate relation is loop-free.
* Finds a unique main box (if exists)

Counter uses Referee to determine whether the input is valid, and throws an error otherwise. The Referee script can also be run separately to spot ill-formed DRSs (with or without the signature file):
```
python clf_referee.py clfs.txt  		      # without the signature
python clf_referee.py clfs.txt -s clf_signature.yaml  # with the signature
```
When Referee is run without signature, it assumes simple heuristics for operators. Roles are in initial caps, comparison operators (e.g., temporal and spatial) in 3-letter all caps, and discourse relations in >3-letter all caps. With a specified signature, Referee is stricter as the signature restricts a set of allowed roles, comparison operators and discourse relatons.  

Counter contains a setting to automatically replace ill-formed DRSs by either a dummy DRS (-ill dummy) or the SPAR default DRS (-ill spar) to make sure you can still get a score when producing ill-formed output.

#### Data ####

The data folder contains the train/dev split for release 2.1.0 and train/dev/test split for release 2.2.0. **Note that these splits are different**. Our annotation is data-driven, meaning we add certain phenomena at the time. We feel that if there are new phenomena in the training set, this should also be reflected in the suggested dev/test splits. Therefore, those splits also change per release.

This data is also available on [the PMB webpage](http://pmb.let.rug.nl/data.php), but here it is already in a more convenient format.
>>>>>>> e150879aefd236a985f2e10caa7fee49bcb01cfb

### Running Counter

The most vanilla version can be run like this:

```
python counter.py -f1 FILE1 -f2 FILE2
```

Running with our example data:

```
<<<<<<< HEAD
python counter.py -f1 ../data/pmb-2.2.0/boxer_parse_dev.txt -f2 ../data/pmb-2.2.0/gold/dev.txt
=======
python counter.py -f1 ../data/pmb-2.1.0/boxer_parse_dev.txt -f2 ../data/pmb-2.1.0/dev.txt
>>>>>>> e150879aefd236a985f2e10caa7fee49bcb01cfb
```

Please note that redundant REF-clauses are ignored during matching, since they inflate the F-score. However, they are still needed for the format checker.

#### Parameter options ####

```
-f1      : First file with DRS clauses, usually produced file
-f2      : Second file with DRS clauses, usually gold file
-r       : Number of restarts used (default 20)
-p       : Number of parallel threads to use (default 1)
-mem     : Memory limit per parallel thread (default 1G)
-s       : What kind of smart initial mapping we use:
          -no    No smart mappings
          -conc  Smart mapping based on matching concepts (their match is likely to be in the optimal mapping)
-runs    : Number of runs to average over, if you want a more reliable result (there is randomness involved in the initial restarts)
-prin    : Print more specific output, such as individual (average) F-scores for the smart initial mapping, and the matching and non-matching clauses
-sig     : Number of significant digits to output (default 4)
-b       : Use this for baseline experiments, comparing a single DRS to a list of DRSs. Produced DRS file should contain a single DRS.
-ms      : Instead of averaging the score, output a score for each DRS
-ms_file : Print the individual F-scores to a file (one score per line)
-coda    : Print results in codalab style to a file
-nm      : If added, do not print the clause mapping
-st      : Printing statistics regarding number of variables and clauses, don't do matching
-ic      : Include REF clauses when matching (otherwise they are ignored because they inflate the matching)
-ds      : Print detailed stats about individual clauses, parameter value is the minimum count of the clause to be included in the printing
-m       : Max number of clauses for a DRS to still take them into account - default 0 means no limit
-g       : Path of the file that contains the signature of clausal forms 
-dse     : Change all senses to a default sense
-dr      : Change all roles to a default role
-dc      : Change all concepts to a default concept
-ill     : What to do with ill-formed DRSs. Throw an error (default), input dummy DRS or input the SPAR baseline DRS
```

#### Running some tests ####

Run with 20 restarts and no smart initial mappings:

```
<<<<<<< HEAD
python counter.py -f1 ../data/pmb-2.2.0/boxer_parse_dev.txt -f2 ../data/pmb-2.2.0/gold/dev.txt -r 20 -s no
=======
python counter.py -f1 ../data/pmb-2.1.0/boxer_parse_dev.txt -f2 ../data/pmb-2.1.0/dev.txt -r 20 -s no
>>>>>>> e150879aefd236a985f2e10caa7fee49bcb01cfb
```

Run with 4 parallel threads to speed things up

``` 
<<<<<<< HEAD
python counter.py -f1 ../data/pmb-2.2.0/boxer_parse_dev.txt -f2 ../data/pmb-2.2.0/gold/dev.txt -p 4 -s no
=======
python counter.py -f1 ../data/pmb-2.1.0/boxer_parse_dev.txt -f2 ../data/pmb-2.1.0/dev.txt -p 4 -s no
>>>>>>> e150879aefd236a985f2e10caa7fee49bcb01cfb
```

Print specific output, while only using the smart mapping based on concepts:

```
<<<<<<< HEAD
python counter.py -f1 ../data/pmb-2.2.0/boxer_parse_dev.txt -f2 ../data/pmb-2.2.0/gold/dev.txt -prin -s conc
=======
python counter.py -f1 ../data/pmb-2.1.0/boxer_parse_dev.txt -f2 ../data/pmb-2.1.0/dev.txt -prin -s conc
>>>>>>> e150879aefd236a985f2e10caa7fee49bcb01cfb
```

Print even more specific output, for all clause type (e.g. Agent, NOT) that occur 10 times or more

```
<<<<<<< HEAD
python counter.py -f1 ../data/pmb-2.2.0/boxer_parse_dev.txt -f2 ../data/pmb-2.2.0/gold/dev.txt -prin -ds 10
=======
python counter.py -f1 ../data/pmb-2.1.0/boxer_parse_dev.txt -f2 ../data/pmb-2.1.0/dev.txt -prin -ds 10
>>>>>>> e150879aefd236a985f2e10caa7fee49bcb01cfb
```

Doing a single DRS, printing the matching and non-matching clauses:

```
<<<<<<< HEAD
python counter.py -f1 ../data/pmb-2.2.0/baseline_drs.txt -f2 ../data/pmb-2.2.0/baseline_drs.txt -prin
=======
python counter.py -f1 ../data/pmb-2.1.0/baseline_drs.txt -f2 ../data/pmb-2.1.0/baseline_drs.txt -prin
>>>>>>> e150879aefd236a985f2e10caa7fee49bcb01cfb
```

Outputting a score for each DRS (note we use -p 1 to not mess up printing):

```
<<<<<<< HEAD
python counter.py -f1 ../data/pmb-2.2.0/boxer_parse_dev.txt -f2 ../data/pmb-2.2.0/gold/dev.txt -p 1 -ms
=======
python counter.py -f1 ../data/pmb-2.1.0/boxer_parse_dev.txt -f2 ../data/pmb-2.1.0/dev.txt -p 1 -ms
>>>>>>> e150879aefd236a985f2e10caa7fee49bcb01cfb
```

Doing a baseline experiment, comparing a single DRS to a number of DRSs:

```
<<<<<<< HEAD
python counter.py -f1 ../data/pmb-2.2.0/baseline_drs.txt -f2 ../data/pmb-2.2.0/gold/dev.txt -prin --baseline
=======
python counter.py -f1 ../data/pmb-2.1.0/baseline_drs.txt -f2 ../data/pmb-2.1.0/dev.txt -prin --baseline
>>>>>>> e150879aefd236a985f2e10caa7fee49bcb01cfb
```

Doing an experiment by replacing all senses in both files by a default sense ("n.01"), removing the need for word sense disambiguation:

```
<<<<<<< HEAD
python counter.py -f1 ../data/pmb-2.2.0/boxer_parse_dev.txt -f2 ../data/pmb-2.2.0/gold/dev.txt -r 50 -dse
=======
python counter.py -f1 ../data/pmb-2.1.0/boxer_parse_dev.txt -f2 ../data/pmb-2.1.0/dev.txt -r 50 -dse
>>>>>>> e150879aefd236a985f2e10caa7fee49bcb01cfb
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
python amr2drs.py -i ../data/amr_sample.txt -d OUTPUT_FILE
``` 

An existing AMR parser is available [here](https://github.com/RikVN/AMR).

## Author

* **Rik van Noord** - PhD-student at University of Groningen - [Personal website](http://www.rikvannoord.nl)

## Citation ##
<<<<<<< HEAD

If you use any of our scripts, please refer to our [LREC paper](https://arxiv.org/pdf/1802.08599.pdf):

=======

If you use any of our scripts, please refer to our [LREC paper](https://arxiv.org/pdf/1802.08599.pdf):

>>>>>>> e150879aefd236a985f2e10caa7fee49bcb01cfb
Rik van Noord, Lasha Abzianidze, Hessel Haagsma, and Johan Bos, 2018. **Evaluating scoped meaning representations**. In Proceedings of the Eleventh International Conference on Language Resources and Evaluation (LREC 2018), Miyazaki, Japan

@inproceedings{vanNoordLREC:2018,  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; title = {Evaluating Scoped Meaning Representations}  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; author    = {van Noord, Rik and Abzianidze, Lasha and Haagsma, Hessel and Bos, Johan},  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; booktitle = {Proceedings of the Eleventh International Conference on Language Resources and Evaluation (LREC 2018)},  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; address   = {Miyazaki, Japan},  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; year      = {2018}  
}  

## Acknowledgments

* Thanks to [SMATCH](https://github.com/snowblink14/smatch) for publishing their code open source.
* All members of the [Parallel Meaning Bank](http://pmb.let.rug.nl)

