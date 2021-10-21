# DRS parsing

This folder contains scripts for:

* Evaluating DRS parsing (Counter)
* Format checking produced DRSs (Referee)
* Extracting layers from the official PMB release
* Running the semantic parser Boxer

## Getting Started

```
git clone https://github.com/RikVN/DRS_parsing
pip install -r requirements.txt
```

Make sure evaluation/ is on your PYTHONPATH like this:

```
cur_dir=$(pwd)
export PYTHONPATH=${PYTHONPATH}:${cur_dir}/evaluation/
```

All Python scripts should use Python 3, though some might work with Python 2 (Counter).

### Running on older data ###

This version contains the scripts that work with version 4.0.0 (should mostly concern referee, see below). If you plan to do experiments on release 2.2.0 or 3.0.0, please check out the correct version of this repo like this:

```
git checkout v.3.0.0
```

## Counter: evaluating scoped meaning representations

Counter is a tool that is able to evaluate scoped meaning representations, in this case Discourse Representation Structures (DRSs). It compares sets of clauses and outputs an F-score. The tool can be used to evaluate different DRS-parsers. It is based on [SMATCH](https://github.com/snowblink14/smatch), with a number of modifications. It was developed as part of the [Parallel Meaning Bank](http:/pmb.let.rug.nl).

Note: for evaluation DRS parsing experiments, you might be interested in DRS Jury as well, available in our [Neural_DRS](https://github.com/RikVN/Neural_DRS) repository.

### Main differences with SMATCH ###

* Counter is for evaluating DRSs, not AMRs
* Counter takes clauses directly as input
* Counter normalizes WordNet concepts to their synset IDs (see evaluation/wordnet_dict_en.py)
* Counter can process clauses that contain three variables (instead of max 2)
* Counter can do baseline experiments, comparing a single DRS to a set of DRSs
* Counter can print more detailed output, such as specific matching clauses
* Counter ensures that different variable types can never match

### Input format ###

DRSs are sets of clauses, with each clause on a new line and with DRSs separated by a white line. Lines starting with '%' are ignored. The whitespace separates the values of a clause, so it can be spaces or tabs. Everything after a '%' is ignored, so it is possible to put a comment there. Check out [data](data) to see examples.

#### Format checking ####

DRSs in clause format follow a strict format. The second value in the clause identifies its type. We distinguish between DRS operators (e.g. REF, POS, IMP), semantic roles (e.g. Agent, Time, Location) and WordNet concepts (work "n.01"). These are closed classes. For a full list of accepted DRS operators and semantic roles please see `evaluation/clf_signature.yaml`. We do accept concepts that are not in WordNet, however be aware that they can then never match with a clause in the gold standard.

Clauses can have two types of variable, box variables and other variables. The type of variable can be determined by the place it occurs in a clause, e.g. the first variable is always a box variable. This means that you can name the variables to whatever is convenient for you, but realize that using the same name in a DRS matches the same variable.

If all clauses are correctly formatted syntactically, they do not necessarily form a well-formed DRS (e.g. translatable into a first-order logic formula without free occurrences of a variable). To check if the input is a well-formed DRS, we use a format checker called Referee (see `evaluation/clf_referee.py` by [Lasha Abzianidze](https://naturallogic.pro/)). Referee does the following things:

* Checks individual clauses on well-formedness (distinguishing between box variables, entity variables and constants);
* Recovers a transitive subordinate relation over boxes in such a way that free occurrences of variables are avoided (if possible) by inducing parts of the relation;
* Checks that the subordinate relation is loop-free;
* Verifies that every discourse referent is bound;
* Makes sure that the DRSs are forming a connected graph, i.e, any two DRSs are connected with a series of discourse relations;

Counter uses Referee to determine whether the input is well-formed, and throws an error otherwise. The Referee script can also be run separately to spot ill-formed DRSs (with or without the signature file):

```
python evaluation/clf_referee.py $DRS_FILE
python evaluation/clf_referee.py $DRS_FILE -s evaluation/clf_signature.yaml -v 3
```

Counter contains a setting to automatically replace ill-formed DRSs by either a dummy DRS (-ill dummy) or the SPAR default DRS (-ill spar) to make sure you can still get a score when producing ill-formed output.

### Data ###

The data folder contains some data for release 2.1.0, 2.2.0, 3.0.0 and 4.0.0. If you're interested in DRS parsing, please see our [Neural_DRS](https://github.com/RikVN/Neural_DRS) and see the setup scripts to easily get DRS parsing data for releases 2.2.0, 3.0.0 and 4.0.0, for all four languages in the PMB.

For full releases, please see [the PMB webpage](http://pmb.let.rug.nl/data.php).

The data sets contain these data types:

* **Gold** - fully manually annotated
* **Silver** - partially manually annotated
* **Bronze** - no manual annotations involved

The silver and bronze data can be pretty far away from gold standard. Use at your own risk.

### Running Counter

The most vanilla version can be run like this:

```
python counter.py -f1 $FILE1 -f2 $FILE2 -g evaluation/clf_signature.yaml
```

Running with our released data:

```
python counter.py -f1 ../data/pmb-3.0.0/gold/dev.txt -f2 ../data/pmb-3.0.0/gold/dev.txt -g evaluation/clf_signature.yaml
```

Please note that redundant REF-clauses are ignored during matching, since they inflate the F-score. However, they are still needed for the format checker.

### Parameter Options ###

Please run the following command to see the options:

```
python evaluation/counter.py -h
```

To obtain official scores for DRS parsing, you need to run with referee as an argument (-g) and replace ill-formed DRSs by a dummy (-ill dummy).

In ``test.sh`` we have added a number of tests to check and show what Counter can do, please check them out!

## Layer Extraction and Parsing ##

We provide a number of scripts to extract specific information from the PMB releases. Also, we give instructions on how run the semantic parser Boxer. This is all detailed in [this separate README](Extraction.md).

## Application ##

Counter is currently used in the [Parallel Meaning Bank](http://pmb.let.rug.nl/explorer/explore.php) to estimate the semantic similarity between DRSs of different languages. Come check it out!

## Author

* **Rik van Noord** - PhD-student at University of Groningen - [Personal website](http://www.rikvannoord.nl)

## Citation ##

If you use the data or any of the extraction/parsing scripts, please cite:

* Abzianidze, L., Bjerva, J., Evang, K., Haagsma, H., van Noord, R., Ludmann, P., Nguyen, D. & Bos, J. **The Parallel Meaning Bank: Towards a Multilingual Corpus of Translations Annotated with Compositional Meaning Representations**, EACL 2017 [\[PDF\]](https://www.aclweb.org/anthology/E17-2039.pdf) [\[BibTex\]](https://www.aclweb.org/anthology/E17-2039.bib)

If you use Counter, please refer to our [LREC paper](https://www.aclweb.org/anthology/L18-1267/):

* Rik van Noord, Lasha Abzianidze, Hessel Haagsma, and Johan Bos. **Evaluating scoped meaning representations**. LREC 2018 [\[PDF\]](https://www.aclweb.org/anthology/L18-1267.pdf) [\[BibTex\]](https://www.aclweb.org/anthology/L18-1267.bib)

We also keep a list of all papers related to DRS parsing [here](https://pmb.let.rug.nl/publications.php).

## Acknowledgments

* Thanks to [SMATCH](https://github.com/snowblink14/smatch) for publishing their code open source.
* All members of the [Parallel Meaning Bank](http://pmb.let.rug.nl)

