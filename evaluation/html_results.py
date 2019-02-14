#!/usr/bin/env python
# -*- coding: utf8 -*-

'''
Contaisn the functions for printing the evaluation results in an HTML file
Contact: Lasha.Abzianidze@gmail.com 
'''

def coda_html(num, ill_drs_ids, counts, measures, types, cr_mdict):
	'''Gets the number of CLFs, ids of ill DRSs, counts for produced, gold and matching clauses,
	   evaluation measures like precision, recall and F-scores, the list of detailed metrics, 
	   and their corresponding evaluation measures.
	   Output is an html content representing the input.
	''' 
	# unpack tuples
	(prod_cl, gold_cl, match_cl) = counts
	types = sorted(types, key=lambda x: lab2num(x))
	# internal css style and other styling
	style = ("table, th, td { border: 1px solid black; border-collapse: collapse;}\n"
			 "#tot {background-color: #222; color: #fff; font-weight: bold;}\n"
			 "td {text-align: right;}\n"
			 ".ltd {text-align: left;}\n" 
			 "th {background-color: #648ca8; color: #fff;}\n" 
			 "th, td {padding: 2px 10px 2px 10px;}\n"
			 ".oddrow {background-color: #eee;}\n"
			 ".evenrow {background-color: #fff;}\n"
			 '.mono {font-family: "Courier New", Courier, monospace;}\n'
			)
	header = '<head>\n<style>\n{}\n</style>\n</head>'.format(style)
	tag = 'p'
	# generating the content
	body = '<{0}>Number of system-gold pairs of CLFs: <b>{1}</b></{0}>\n'.format(
		tag, num)
	body += '<{0}>Number of ill CLFs (i.e. non-DRSs) produced by the system: <b>{1}</b></{0}>\n'.format(
		tag, len(ill_drs_ids))
	body += '<{0}>Total number of clauses in system / gold CLFs: <b>{1}</b> / <b>{2}</b></{0}>\n'.format(
		tag, prod_cl, gold_cl)
	body += '<{0}>Total number of matching clauses: <b>{1}</b></{0}>\n'.format(
		tag, match_cl)
	# create the table with scores
	body += '<table style="width:100%">\n'
	body += '<tr>\n<th>Clause types</th>\n<th>Precision</th>\n<th>Recall</th>\n<th>F-score</th>\n</tr>\n'
	for (i, c) in enumerate(types):
		sty = 'evenrow' if i % 2 == 0 else 'oddrow' 
		body += '<tr class="{}">\n<td class="ltd">{}</td>\n<td>{:.2%}</td>\n<td>{:.2%}</td>\n<td>{:.2%}</td>\n</tr>\n'.format(
			sty, indent(c), *cr_mdict[c])
	body += '<tr id="tot">\n<td class="ltd">Total</td>\n<td>{:.2%}</td>\n<td>{:.2%}</td>\n<td>{:.2%}</td>\n</tr>\n'.format(
		*measures)
	# close the table
	body += '</table>\n'
	# print the list of ill-CLF ids 
	if ill_drs_ids:
		body += '<p>{}: <span class="mono">{}</span></p>\n'.format(
			'IDs of ill CLFs', ', '.join(map(str, ill_drs_ids))) 	
	return '<!DOCTYPE html>\n<meta charset=utf-8>\n<html>\n{}\n<body>\n{}\n</body>\n</html>'.format(header, body)


def indent(label, n=4):
	'''Indent the clause types
	   'operators','roles','concepts','nouns','verbs','adjectives','adverbs','events'
	'''
	mapping = {	'nouns': n*'&nbsp;'+'Nouns',
				'adjectives': 2*n*'&nbsp;'+'Adjectives',
				'verbs': 2*n*'&nbsp;'+'Verbs',
				'adverbs': n*'&nbsp;'+'Adverbs',
				'events': n*'&nbsp;'+'Events'
		}
	return mapping.get(label, label.title()) 
	
	 
def lab2num(label):
	'''Map the type to a number for the ordering purposes: 
	   'operators','roles','concepts','nouns','verbs','adjectives','adverbs','events'
	'''
	mapping = {	'operators': 1,
				'roles': 2,
				'concepts': 3,
				'events': 5,
				'nouns': 4,
				'verbs': 6,
				'adjectives': 7,
				'adverbs': 8
			}
	return mapping[label] 	 
	 
