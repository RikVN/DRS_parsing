# Layer Extraction and Parsing #

We provide a number of scripts to extract specific information from the PMB releases. Also, we give instructions on how run the semantic parser Boxer. Note that this can be quite complicated. For neural DRS parser, see our [Neural_DRS](https://github.com/RikVN/Neural_DRS) repository.

## Layer Extraction ##

The full PMB release contains information about the 6 main annotation layers in the PMB pipeline:

* **tok** - tokenization of the raw sentence
* **sym** - lemmatization/symbolization of the raw sentence
* **sem** - semantic tagging of the raw sentence (see [this paper](https://www.aclweb.org/anthology/W17-6901.pdf) for details)
* **cat** - CCG supertag categories per token
* **sns** - Wordnet senses for the relevant tokens (not all!)
* **rol** - VerbNet roles for the relevant tokens (not all!)

All these layers have a status (gold/silver/bronze). We provide a script that can extract every combination of layers, with every combination of statuses, in CoNLL format.

You can use this script if you are, for example, interested in semantic tagging, lemmatization, or semantic role labeling. You need to download the [latest release](https://pmb.let.rug.nl/data.php) first. Note that unzipping can take quite some time.

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
cur_dir=$(pwd)
export PYTHONPATH=${PYTHONPATH}:${cur_dir}/Neural_DRS/src/
```

To test your setup, you can run Boxer on the gold-standard layer data for the dev set like this:

```
python parsing/run_boxer.py -c parsing/layer_data/3.0.0/en/gold/dev.conll -o parsing/output/
```

The final DRSs are now in parsing/output/final_drss.txt. If you compare this to the gold standard using Counter, it should score an F-score of > 0.99.

```
python evaluation/counter.py -f1 parsing/output/final_drss.txt -f2 data/pmb-3.0.0/gold/dev.txt -g evaluation/clf_signature.yaml -ill dummy
```

Note that you can only run Boxer as a fair semantic parsing model if you provide it with input of your own layer taggers, and do not assume gold standard layers (not even tokenization). Even then, Boxer is partly optimized on the dev/test sets of the PMB, so it is never 100% fair.

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
