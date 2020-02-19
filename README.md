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
export PYTHONPATH=${PYTHONPATH}:/your/folders/here/DRS_parsing/evaluation/
```

All Python scripts should use Python 3, though some might work with Python 2 (Counter).

### Running on older data ###

This version contains the scripts that work with version 3.0.0 (should mostly concern referee, see below). If you plan to do experiments on release 2.2.0, please check out the 2.2.0 version of this repo:

```
git checkout v.2.2.0
```

## Counter: evaluating scoped meaning representations

Counter is a tool that is able to evaluate scoped meaning representations, in this case Discourse Representation Structures (DRSs). It compares sets of clauses and outputs an F-score. The tool can be used to evaluate different DRS-parsers. It is based on [SMATCH](https://github.com/snowblink14/smatch), with a number of modifications. It was developed as part of the [Parallel Meaning Bank](http:/pmb.let.rug.nl).

### Main differences with SMATCH ###

* Counter is for evaluating DRSs, not AMRs
* Counter takes clauses directly as input
* Counter normalizes WordNet concepts to their synset IDs (see evaluation/wordnet_dict_en.py)
* Counter can process clauses that contain three variables (instead of max 2)
* Counter can do baseline experiments, comparing a single DRS to a set of DRSs
* Counter can print more detailed output, such as specific matching clauses
* Counter ensures that different variable types can never match

### Input format ###

DRSs are sets of clauses, with each clause on a new line and with DRSs separated by a white line. Lines starting with '%' are ignored. The whitespace separates the values of a clause, so it can be spaces or tabs. Everything after a '%' is ignored, so it is possible to put a comment there.

A DRS file looks like this:

```
% DRS 1
% He is a baseball player.
b1 REF x1                     % He [0...2]
b1 PRESUPPOSITION b2          % He [0...2]
b1 male "n.02" x1             % He [0...2]
b2 REF e1                     % is [3...5]
b2 REF t1                     % is [3...5]
etc

% DRS 2
% Sentence here
etc
```

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
python evluation/clf_referee.py $DRS_FILE -s evaluation/clf_signature.yaml -v 3
```

When Referee is run without a signature, it assumes simple heuristics for operators. Roles are in initial caps, comparison operators (e.g., temporal and spatial) in 3-letter all caps, and discourse relations in >3-letter all caps. With a specified signature, Referee is stricter as the signature restricts a set of allowed roles, comparison operators and discourse relations. It supports the verbosity levels that help to expose the details of validity checking.

Counter contains a setting to automatically replace ill-formed DRSs by either a dummy DRS (-ill dummy) or the SPAR default DRS (-ill spar) to make sure you can still get a score when producing ill-formed output.

### Data ###

The data folder contains the train/dev/test splits for release 2.1.0, 2.2.0 and 3.0.0. **Note that these splits are different**. Our annotation is data-driven, meaning we add certain phenomena at the time. We feel that if there are new phenomena in the training set, this should also be reflected in the suggested dev/test splits. Therefore, those splits also change per release.

This data is also available on [the PMB webpage](http://pmb.let.rug.nl/data.php), but here it is already in a more convenient format.

The data for release 3.0.0 contains these data types:

* **Gold** - fully manually annotated
* **Silver** - partially manually annotated
* **Bronze** - no manual annotations involved

Note that this means that the silver and bronze data can be pretty far away from gold standard. Use at your own risk.

For 3.0.0, we add gold English data for convenience in this repo, but all non-en and all silver/bronze data can be downloaded by running this:

```
wget "https://pmb.let.rug.nl/releases/pmb_exp_data_3.0.0.zip"
unzip pmb_exp_data_3.0.0.zip
```

Note that this gives you the train/dev/test splits for DRS parsing, not the full release.

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

## Layer Extraction ##

The full PMB release contains information about the 6 main annotation layers in the PMB pipeline:

* **tok** - tokenization of the raw sentence
* **sym** - lemmatization/symbolization of the raw sentence
* **sem** - semantic tagging of the raw sentence (see [here](https://www.aclweb.org/anthology/W17-6901.pdf) for details)
* **cat** - CCG supertag categories per token
* **sns** - Wordnet senses for the relevant tokens (not all!)
* **rol** - VerbNet roles for the relevant tokens (not all!)

All these layers have a status (gold/silver/bronze). We provide a script that can extract every combination of layers, with every combination of statuses, in CoNLL format.

You can use this script if you are, for example, interested in semantic tagging, lemmatization, or semantic role labeling. You need to download the [latest release](https://pmb.let.rug.nl/data.php) first.

For example, this is how you extract gold standard semantic tagging data, and split it in train/dev/test (default):

```
python parsing/extract_conll.py en $PMB_DATA_DIR $WORKING_DIR -j statuses.json -ls tok:g sem:g
```

Another example: extract gold data for German semantic role labeling, add additional layers CCG categories, semantic tags, and symbols of at least silver status and split in train/dev/test:

```
python parsing/extract_conll.py de $PMB_DATA_DIR $WORKING_DIR -j statuses.json -ls tok:g rol:g cat:gs sem:gs sym:gs
```

The first time you run the script it fills statuses.json if it doesn't exist yet, which will speed up further extractions. $PMB_DATA_DIR should be the data/ folder of the release. Also, since it is CoNLL format, tokens are always extracted anyway.

## Parsing

We provide a working model of the semantic parser Boxer for release 3.0.0. However, getting it to output quality DRSs is not straightforward, since it is dependent on 6 input layers, that are tagged per token (see above).

The file ``run_boxer.py`` is able to provide you with DRSs if you provide it with the information per layer, in CoNLL format.

We have provided the gold standard layer information (see parsing/layer_data/) as an example of what input Boxer expects.

Boxer is created in prolog and needs swipl version 7.2.3 to run, please check [here](https://www.swi-prolog.org/build/PPA.html) and [here](https://launchpad.net/~swi-prolog/+archive/ubuntu/stable) to obtain a working version.

You only need to the provide the supertags, but Boxer still needs access to the full parse. The script will take care of this. However, it needs access to our version of easyCCG, with a corresponding model.

Run this to install these dependencies + the parsing model:

```
git clone https://github.com/ParallelMeaningBank/easyccg
cd easyccg; ant
wget "http://www.let.rug.nl/rikvannoord/easyCCG/model.tar.gz"
tar xvzf model.tar.gz; cd ../
```

You also need access to the [Neural_DRS](https://github.com/RikVN/Neural_DRS) Github repo (for imports), which also should be on your PYTHONPATH:

```
git clone https://github.com/RikVN/Neural_DRS
export PYTHONPATH=${PYTHONPATH}:/your/folders/here/Neural_DRS/src/
```

To test your setup, you can run Boxer on the gold-standard layer data for the dev set like this:

```
python parsing/run_boxer.py -c parsing/layer_data/gold/en/dev.conll -o parsing/output/
```

The final DRSs are now in parsing/output/final_drss.txt. If you compare this to the gold standard using Counter, it should score an F-score of > 0.99.

```
python evaluation/counter.py -f1 parsing/output/final_drss.txt -f2 data/pmb-3.0.0/gold/dev.txt -g evaluation/clf_signature.yaml -ill dummy
```

Note that you can only run Boxer as a fair semantic parsing model if you provide it with input of your own layer taggers, and do not assume gold standard layers (not even tokenization).

### Reordering ###

Important: if you extract your own layers for DRS parsing instead of using our version, you will have to reorder the CoNLL format file if it has to match the released data files (since extract_conll.py does not maintain original ordering). For example, for extracting the gold dev set with 6 gold layers, you have to run this:

```
python parsing/extract_conll.py en $PMB_DATA_DIR $WORKING_DIR -j statuses.json -ls tok:g sym:g sem:g cat:g sns:g rol:g
python filter_and_reorder_conll.py --conll_file ${WORKING_DIR}/dev --drs_file data/pmb-3.0.0/gold/dev.txt --output_file ${WORKING_DIR}/reordered_dev.txt
```

### SPAR ###

We also provide the baseline parser SPAR, which simply outputs a baseline DRS for each input sentence. The input file should contain a sentence on each line, empty lines will be ignored. You can run it like this:

```
python spar.py $FILE
```

## Application ##

Counter is currently used in the [Parallel Meaning Bank](http://pmb.let.rug.nl/explorer/explore.php) to estimate the semantic similarity between DRSs of different languages. Come check it out!

## Author

* **Rik van Noord** - PhD-student at University of Groningen - [Personal website](http://www.rikvannoord.nl)

## Citation ##

If you use the data or any of the extraction/parsing scripts, please cite the [PMB paper](https://www.aclweb.org/anthology/E17-2039.pdf):

Abzianidze, L., Bjerva, J., Evang, K., Haagsma, H., van Noord, R., Ludmann, P., Nguyen, D. & Bos, J **The Parallel Meaning Bank: Towards a Multilingual Corpus of Translations Annotated with Compositional Meaning Representations**, EACL 2017

If you use Counter, please refer to our [LREC paper](https://www.aclweb.org/anthology/L18-1267/):

Rik van Noord, Lasha Abzianidze, Hessel Haagsma, and Johan Bos, 2018. **Evaluating scoped meaning representations**. In Proceedings of the Eleventh International Conference on Language Resources and Evaluation (LREC 2018), Miyazaki, Japan

## Acknowledgments

* Thanks to [SMATCH](https://github.com/snowblink14/smatch) for publishing their code open source.
* All members of the [Parallel Meaning Bank](http://pmb.let.rug.nl)

