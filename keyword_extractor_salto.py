#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
@author: Nadezda Okinina
"""

import sys, io, os, subprocess, copy, difflib, argparse, logging, re, string, operator, treetaggerwrapper, editdistance, regex, shutil
from segtok.segmenter import split_multi
from langdetect import detect
import requests, uuid, json
from operator import itemgetter


"""
This script contains a module that extracts keywords from short newspaper articles in German and Italian (salto.bz articles).
Usually extracts between 2 and 10 keywords.

If an article contains phrases in another language (for example, a German article contains Italian phrases), only takes into account proper nouns in the second language (Italian for German texts, German for Italian texts), leaving behind all the other words.

Keywords may belong to any part of speech, but are usually nouns.
Proper nouns are given special attention and some are usually present in the list of keywords.
One keyword may contain several words (ex: dreisprachige RAI).

Keyword extraction is based on the frequency of words in the text.
For German, it is based on the frequency of their parts: morphological analysis is performed by SMOR.
Lemmatisation for both languages is performed with TreeTagger.
For Italian no morphological analysis is performed.
For German texts, the script counts word parts (parts of compounds) and finds the most frequent ones, privileging the longest candidates.
For Italian it counts whole words. Then for both languages it finds words that often co-occur with the candidate keywords.

A word that is not present in the text cannot become its keyword.

Keywords may belong to any part of speech, but are usually nouns.

Proper nouns are given special attention and a few proper nouns are usually present in the list of keywords.

One keyword may contain several words (ex: dreisprachige RAI).


The module needs the following files to be present in the same folder:
    stoplist-de.txt
    stoplist-it.txt
    names-all.txt
    titles.txt
    common-de-surnames.txt
    styr_nachnamen.txt
    good-keywords.txt    
It also needs the directory containing the SMOR tool to be present in the same folder.
TreeTagger for German and Italian must be installed, because it is used by the Python module treetaggerwrapper.

1) Depending on the input format, the KeywordExtractor module has to be initialised differently.
    There are 3 ways to initialise the KeywordExtractor module:

    1 If you want the script to extract keywords from a Salto article saved in a file, initialise the KeywordExtractor module like this:
        key_word_extractor_de = KeywordExtractor( input_file_folder, input_file_name, outputDirectory)

    2 If you want to extract keywords from a Salto article text, initialise the KeywordExtractor module like this:
        key_word_extractor_de = KeywordExtractor( article_text, outputDirectory)
        The article_text must contain a string with a TITLE, TEASER and BODY, as in the example above.

    3 If you want to extract keywords from a Salto article presented as a json, initialise the KeywordExtractor module like this:
        key_word_extractor_de = KeywordExtractor( "json", json, outputDirectory)
        The json must contain 3 fields: "Title", "Teaser" and "Body".

    Words from the title and the teaser are considered more important than words from the body when the scores of words are counted for choosing the most frequent ones.

2) In order to extract keywords from a text, call the extract_keywords() function


The main function of this script takes 3 arguments:
    -i  the name of the file containing the newspaper text
    -o  the name of the output folder that will contain the file with keywords

The extracted keywords are written to a text file of the same name as the input file, with the extension '.KEY' added at the end, 1 keyword \t its translation per line.
"""

SCRIPT_FOLDER=os.path.dirname(os.path.realpath(__file__))+"/"
SMOR_FOLDER = SCRIPT_FOLDER+"SMOR"
SMOR_EXECUTABLE = SCRIPT_FOLDER+"SMOR"+"/smor-infl"
STOPLIST_DE_FILE = SCRIPT_FOLDER+"stoplist-de.txt"
STOPLIST_IT_FILE = SCRIPT_FOLDER+"stoplist-it.txt"
NAMES_FILE = SCRIPT_FOLDER+"names-all.txt"
TITLES_FILE = SCRIPT_FOLDER+"titles.txt"
COMMON_DE_SURNAMES_FILE = SCRIPT_FOLDER+"common-de-surnames.txt"
STYR_SURNAMES = SCRIPT_FOLDER+"styr_nachnamen.txt"
GOOD_KEYWORDS_FILE = SCRIPT_FOLDER+"good-keywords.txt"


class KeywordExtractor():
    def __init__(self, *args) -> None:
        
        if len(args) == 3 and args[0]!="json":
            self._init_from_file(*args)
        elif len(args) == 2:
            self._init_from_text(*args)
        elif len(args) == 3 and args[0]=="json":
            self._init_from_json(*args)
        else:
            logging.error('Could not initialise the KeywordExtractor due to the wrong number of arguments received by the constructor: {}'.format(len(args)))

    
    def _init_from_json(self, json_word: str, json: dict, output_folder_name: str) -> None:
        """
        Keyword extractor class for salto.bz articles in German and Italian. Third init function.
    
        Parameters: 
            :param json_word: string with value "json"
            :param hash json: a json object with a Title, a Teaser and a Body
            :param srt output_folder_name: The folder that will contain the file with keywords
        """
        
        #Compile POS patterns
        self.noun_or_verb_pattern = re.compile("(NN|NNS|NO|VV|VE)")
        self.noun_pattern = re.compile("(NN|NNS|NO)")
        self.proper_noun_pattern = re.compile("(NP|NE)")
        self.adj_pattern = re.compile("ADJ")
        #Pattern to filter out digits  and punctuation
        self.pattern_digit_punct = re.compile(r"[\d{}]+$".format(re.escape(string.punctuation)))
        
        try:                
            
            if not os.path.isdir(output_folder_name):
                raise ValueError('Folder {} does not exist. Create it before calling the constructor of the KeywordExtractor.'.format(output_folder_name))
              
            output_directory = os.path.join(output_folder_name, "temp_folder_")
            self._make_output_directory(output_directory)
            self.output_directory = output_directory
            self._main_lang_sentences = []
            self._second_lang_sentences = []
            output_folder_name
            try:
                self._distribute_sentences_per_language_json(json)
            except ValueError as err:
                raise ValueError(err)

            
            #Initialise TreeTagger analysers for German and Italian
            self.tagger_de = treetaggerwrapper.TreeTagger(TAGLANG='de')
            self.tagger_it = treetaggerwrapper.TreeTagger(TAGLANG='it')
            
            #Read stop words files for both languages
            self.stop_words_set_de = self._read_stop_words_from_file(STOPLIST_DE_FILE)
            self.stop_words_set_it = self._read_stop_words_from_file(STOPLIST_IT_FILE)
            
            #Read the contents of files containing good and bad words
            self.namesHashSet = set()
            self._read_names_from_file(NAMES_FILE, self.namesHashSet)
            self.titlesSet = set()
            self._read_names_from_file(TITLES_FILE, self.titlesSet)
            self.surnames_set = set()
            self._read_names_from_file(COMMON_DE_SURNAMES_FILE, self.surnames_set)
            self._read_names_from_file(STYR_SURNAMES, self.surnames_set)

            self._good_keywords_set = set()
            self._read_names_from_file(GOOD_KEYWORDS_FILE, self._good_keywords_set)
            
        
            if self.lang == "de": #If the main language of the text is German
                self.main_tagger = self.tagger_de
                self.second_tagger = self.tagger_it
                
                self.main_lang_stop_words_set = self.stop_words_set_de
                self.second_lang_stop_words_set = self.stop_words_set_it
                
                self.smor_lemmas_count_hash = {} #Will contain the number of occurences per each part of the noun
                self.noun_parts_and_their_compounds_hash = {}
                self.compound_lemma_to_parts = {}
                
            elif self.lang == "it": #If the main language of the text is Italian
                self.main_tagger = self.tagger_it
                self.second_tagger = self.tagger_de
            
                self.main_lang_stop_words_set = self.stop_words_set_it
                self.second_lang_stop_words_set = self.stop_words_set_de
            
            
            self.key_words_set = set() #The set of keywords that will be returned to the user
            
            self.lemma_dict = {} #Key: lemma, value: number of occurances of tokens of this lemma in the document (can be bugger if the word occurrs in the title or teaser)
            self.lemma_dict_true_number = {} #Key: lemma, value: number of occurances of tokens of this lemma in the document
            self.noun_lemma_dict = {} #Key: lemma (only nouns and verbs), value: number of occurances of tokens of this lemma in the document. Will countain nouns and verbs (both can be keywords)
            self.title_noun_lemmas_dict = {}
            self.token_dict = {} #Key: lemma, value: set of corresponding tokens
            self.token_to_lemma_dict = {} #Key: token, value: corresponding lemma in lowercase
            self.token_to_lemma_dict_original_case = {} #Key: token, value: corresponding lemma in original case
            self.proper_nouns_hash = {}
            self.lemma_token_to_POS = {}
            self.tree_taggers_proper_nouns = set()
            self.proper_noun_with_names_set = set()
            self.persons_set = set()
            self.from_good_words_proper_nouns = set()
            self.smor_analysis_hash =  {}            
            
        except ValueError as value_error:
            logging.error('Could not initialise the KeywordExtractor due to the following error: {}'.format(value_error))
            
    
    def _init_from_file(self, input_file_folder: str, file_name: str, output_folder_name: str) -> None:
        """
        Keyword extractor class for salto.bz articles in German and Italian.
    
        Parameters:
    
        :param str input_file_folder: The folder containing the plain text file with the article to find keywords in
        :param str file_name: The name of the plain text file with the article to find keywords in
        :param srt output_folder_name: The folder that will contain the file with keywords
    
        """        
        #Compile POS patterns
        self.noun_or_verb_pattern = re.compile("(NN|NNS|NO|VV|VE)")
        self.noun_pattern = re.compile("(NN|NNS|NO)")
        self.proper_noun_pattern = re.compile("(NP|NE)")
        self.adj_pattern = re.compile("ADJ")
        #Pattern to filter out digits  and punctuation
        self.pattern_digit_punct = re.compile(r"[\d{}]+$".format(re.escape(string.punctuation)))
        
        try:
            if not os.path.isdir(output_folder_name):
                raise ValueError('Folder {} does not exist. Create it before calling the constructor of the KeywordExtractor.'.format(output_folder_name))
                
            output_directory=os.path.join(output_folder_name, "temp_folder_" + file_name)
            self._make_output_directory(output_directory)
            self.output_directory = output_directory
                
            input_file_path = os.path.join(input_file_folder, file_name)
            self.file_text = self._read_file(input_file_path)
            self.file_text = self.file_text.replace("(",",")
            self.file_text = self.file_text.replace(")",",")
            self.file_text = self.file_text.replace("*","###")
            self.file_text = self.file_text.replace("|","===")
            self.file_text = self.file_text.replace("+","#=#")
            
            #If the text of the file is too short (less than 50 characters), refuses to analyse it
            if len(self.file_text) < 50:
                raise ValueError('The content of file {} is too short to be analysed.'.format(input_file_path))
                
            self._main_lang_sentences = []
            self._second_lang_sentences = []
            
            try:
                self._distribute_sentences_per_language()
            except ValueError as err:
                raise ValueError(err)
            
            #Initialise TreeTagger analysers for German and Italian
            self.tagger_de = treetaggerwrapper.TreeTagger(TAGLANG='de')
            self.tagger_it = treetaggerwrapper.TreeTagger(TAGLANG='it')
            
            #Read stop words files for both languages
            self.stop_words_set_de = self._read_stop_words_from_file(STOPLIST_DE_FILE)
            self.stop_words_set_it = self._read_stop_words_from_file(STOPLIST_IT_FILE)
            
            #Read the contents of files containing good and bad words
            self.namesHashSet = set()
            self._read_names_from_file(NAMES_FILE, self.namesHashSet)
            self.titlesSet = set()
            self._read_names_from_file(TITLES_FILE, self.titlesSet)
            self.surnames_set = set()
            self._read_names_from_file(COMMON_DE_SURNAMES_FILE, self.surnames_set)
            self._read_names_from_file(STYR_SURNAMES, self.surnames_set)

            self._good_keywords_set = set()
            self._read_names_from_file(GOOD_KEYWORDS_FILE, self._good_keywords_set)
        
            if self.lang == "de": #If the main language of the text is German
                self.main_tagger = self.tagger_de
                self.second_tagger = self.tagger_it
                
                self.main_lang_stop_words_set = self.stop_words_set_de
                self.second_lang_stop_words_set = self.stop_words_set_it
                
                self.smor_lemmas_count_hash = {} #Will contain the number of occurences per each part of the noun
                self.noun_parts_and_their_compounds_hash = {}
                self.compound_lemma_to_parts = {}
                
            elif self.lang == "it": #If the main language of the text is Italian
                self.main_tagger = self.tagger_it
                self.second_tagger = self.tagger_de
            
                self.main_lang_stop_words_set = self.stop_words_set_it
                self.second_lang_stop_words_set = self.stop_words_set_de
            
            
            self.key_words_set = set() #The set of keywords that will be returned to the user
            
            self.lemma_dict = {} #Key: lemma, value: number of occurances of tokens of this lemma in the document (can be bugger if the word occurrs in the title or teaser)
            self.lemma_dict_true_number = {} #Key: lemma, value: number of occurances of tokens of this lemma in the document
            self.noun_lemma_dict = {} #Key: lemma (only nouns and verbs), value: number of occurances of tokens of this lemma in the document. Will countain nouns and verbs (both can be keywords)
            self.title_noun_lemmas_dict = {}
            self.token_dict = {} #Key: lemma, value: set of corresponding tokens
            self.token_to_lemma_dict = {} #Key: token, value: corresponding lemma in lowercase
            self.token_to_lemma_dict_original_case = {} #Key: token, value: corresponding lemma in original case
            self.proper_nouns_hash = {}
            self.lemma_token_to_POS = {}
            self.tree_taggers_proper_nouns = set()
            self.proper_noun_with_names_set = set()
            self.persons_set = set()
            self.from_good_words_proper_nouns = set()
            self.smor_analysis_hash =  {}            
            
        except ValueError as value_error:
            logging.error('Could not initialise the KeywordExtractor due to the following error: {}'.format(value_error))
            raise ValueError('Could not initialise the KeywordExtractor due to the following error: {}'.format(value_error))
            
            
    
    def _init_from_text(self, salto_text: str, output_folder_name:str) -> None:
        """
        Keyword extractor class for salto.bz articles in German and Italian. Second init function.
    
        Parameters:
    
            :param str salto_text: the content of the salto article in plain text format
            :param srt output_folder_name: The folder that will contain the file with keywords
            :param str tagdir: directory where Treetagger is installed (with bin, cmd and lib inside)
            :param str lang: the main language of the text (optional parameter)
    
        """
        
        #Compile POS patterns
        self.noun_or_verb_pattern = re.compile("(NN|NNS|NO|VV|VE)")
        self.noun_pattern = re.compile("(NN|NNS|NO)")
        self.proper_noun_pattern = re.compile("(NP|NE)")
        self.adj_pattern = re.compile("ADJ")
        #Pattern to filter out digits  and punctuation
        self.pattern_digit_punct = re.compile(r"[\d{}]+$".format(re.escape(string.punctuation)))
        
        try:                
            self.file_text = salto_text.decode()
            
            #If the text of the file is too short (less than 50 characters), refuses to analyse it
            if len(self.file_text) < 50:
                raise ValueError('The text is too short to be analysed.'.format(self.file_text))
            
            self.file_text = self.file_text.replace("(",",")
            self.file_text = self.file_text.replace(")",",")
            self.file_text = self.file_text.replace("*","###")
            self.file_text = self.file_text.replace("|","===")
            self.file_text = self.file_text.replace("+","#=#")
            
            if not os.path.isdir(output_folder_name):
                raise ValueError('Folder {} does not exist. Create it before calling the constructor of the KeywordExtractor.'.format(output_folder_name))
                
            output_directory=os.path.join(output_folder_name, "temp_folder_")
            self._make_output_directory(output_directory)  
            self.output_directory = output_directory
            
            self._main_lang_sentences = []
            self._second_lang_sentences = []
            
            try:
                self._distribute_sentences_per_language()
            except ValueError as err:
                raise ValueError(err)
            
            #Initialise TreeTagger analysers for German and Italian
            self.tagger_de = treetaggerwrapper.TreeTagger(TAGLANG='de')
            self.tagger_it = treetaggerwrapper.TreeTagger(TAGLANG='it')
            
            #Read stop words files for both languages
            self.stop_words_set_de = self._read_stop_words_from_file(STOPLIST_DE_FILE)
            self.stop_words_set_it = self._read_stop_words_from_file(STOPLIST_IT_FILE)
            
            #Read the contents of files containing good and bad words
            self.namesHashSet = set()
            self._read_names_from_file(NAMES_FILE, self.namesHashSet)
            self.titlesSet = set()
            self._read_names_from_file(TITLES_FILE, self.titlesSet)
            self.surnames_set = set()
            self._read_names_from_file(COMMON_DE_SURNAMES_FILE, self.surnames_set)
            self._read_names_from_file(STYR_SURNAMES, self.surnames_set)

            self._good_keywords_set = set()
            self._read_names_from_file(GOOD_KEYWORDS_FILE, self._good_keywords_set)
        
            if self.lang == "de": #If the main language of the text is German
                self.main_tagger = self.tagger_de
                self.second_tagger = self.tagger_it
                
                self.main_lang_stop_words_set = self.stop_words_set_de
                self.second_lang_stop_words_set = self.stop_words_set_it
                
                self.smor_lemmas_count_hash = {} #Will contain the number of occurences per each part of the noun
                self.noun_parts_and_their_compounds_hash = {}
                self.compound_lemma_to_parts = {}
                
            elif self.lang == "it": #If the main language of the text is Italian
                self.main_tagger = self.tagger_it
                self.second_tagger = self.tagger_de
            
                self.main_lang_stop_words_set = self.stop_words_set_it
                self.second_lang_stop_words_set = self.stop_words_set_de
            
            
            self.key_words_set = set() #The set of keywords that will be returned to the user
            
            self.lemma_dict = {} #Key: lemma, value: number of occurances of tokens of this lemma in the document (can be bugger if the word occurrs in the title or teaser)
            self.lemma_dict_true_number = {} #Key: lemma, value: number of occurances of tokens of this lemma in the document
            self.noun_lemma_dict = {} #Key: lemma (only nouns and verbs), value: number of occurances of tokens of this lemma in the document. Will countain nouns and verbs (both can be keywords)
            self.title_noun_lemmas_dict = {}
            self.token_dict = {} #Key: lemma, value: set of corresponding tokens
            self.token_to_lemma_dict = {} #Key: token, value: corresponding lemma in lowercase
            self.token_to_lemma_dict_original_case = {} #Key: token, value: corresponding lemma in original case
            self.proper_nouns_hash = {}
            self.lemma_token_to_POS = {}
            self.tree_taggers_proper_nouns = set()
            self.proper_noun_with_names_set = set()
            self.persons_set = set()
            self.from_good_words_proper_nouns = set()
            self.smor_analysis_hash =  {}            
            
        except ValueError as value_error:
            logging.error('Could not initialise the KeywordExtractor due to the following error: {}'.format(value_error))
            
            
    def _text_to_utf8(self, st: str, salto_text: str):
        """
        Registers the text passed as parameter to the constructor in utf-8 format, if it is not already in utf-8 format.
        
        Parameters:
    
            :param str salto_text: the content of the salto article in plain text format
            :param st: the content of the salto article in plain text format
        """
        try:
            st.decode('utf-8')
            self.file_text = salto_text
        except UnicodeError:
            self.file_text = salto_text.encode('utf8')
            
         
    def extract_keywords(self) -> set:        
        self._fill_main_lang_dictionaries_with_tree_tagger()        
        hash_keywords_from_list = self._find_keywords_from_list_in_text()        
        self._add_second_lang_proper_nouns()
        
        if self.lang == "de" and len(self.noun_lemma_dict)>0:
            #smorAnalysisHash will contain the result of SMOR analyses of all words of the file
            self.smor_analysis_hash = self._fill_dictionaries_with_SMOR()
        
        #If a proper noun has a unique form, we take the form and not the lemma
        newPNHash = self._take_forms_of_lemmas_with_unique_form(self.proper_nouns_hash, self.token_dict, self.noun_lemma_dict)                        
        self.proper_nouns_hash = newPNHash
        
        quoted_pieces_set = self._find_pieces_between_quotes()
        
        if self.proper_nouns_hash: #If the dictionary is not empty
            #Determine the winning proper nouns
            self.proper_noun_with_names_set = self._find_best_proper_nouns(hash_keywords_from_list)
            
            #Delete proper nouns that are part of other proper nouns
            self.proper_noun_with_names_set = self._delete_keywords_that_are_in_another_set(self.proper_noun_with_names_set, self.proper_noun_with_names_set)
            
            #Combine the proper nouns, if the first on is a beginning and the second one is the end
            self.proper_noun_with_names_set = self._find_overlapping_keywords_rec(self.proper_noun_with_names_set) #This function has to be used twice
            
            if self.lang == "de":
                #Delete from the beginning of keywords words that belong to such POS categories as article, preposition, connective etc.
                self.proper_noun_with_names_set = self._delete_POSes_from_beginning_with_SMOR(self.proper_noun_with_names_set, self.tagger_de)
            elif self.lang == "it":
                self.proper_noun_with_names_set = self._delete_POSes_from_beginning_with_TreeTagger(self.proper_noun_with_names_set, self.tagger_it)
                
            if self.lang == "de":
                #Delete from the end of keywords words that belong to such POS categories as article, preposition, connective etc.
                self.proper_noun_with_names_set = self._delete_POSes_from_end_with_SMOR(self.proper_noun_with_names_set, self.tagger_de)
            elif self.lang == "it":
                self.proper_noun_with_names_set = self._delete_POSes_from_end_with_TreeTagger(self.proper_noun_with_names_set, self.tagger_it)
        
        winningFromSmorHash = {} #Will contain keyword candidates  
        if self.lang == "de" and self.smor_lemmas_count_hash: #Only for German
            #Extract the most frequent words as keyword candidates
            self._find_best_from_SMOR(self.smor_lemmas_count_hash, winningFromSmorHash, self.proper_noun_with_names_set, self.noun_parts_and_their_compounds_hash)
            arrayOfWinningWords = winningFromSmorHash.keys()
            #If one winning word is included into another, delete the shorter one: with help of SMOR
            setOfKeywordsToDelete = self._get_keywords_that_are_part_of_other_keywords(set(arrayOfWinningWords)) #Based on SMOR analysis
            keyWordsSet = set(arrayOfWinningWords).difference(setOfKeywordsToDelete)
            keyWordsSet = self._clean_similar_keywords_with_edit_distance(keyWordsSet)

        else: #If the language is Italian
            #Extract the most frequent words as keyword candidates
            self._find_best_from_TreeTagger(self.proper_noun_with_names_set, winningFromSmorHash)
            arrayOfWinningWords = winningFromSmorHash.keys()
            keyWordsSet = self._clean_similar_keywords_with_edit_distance(set(arrayOfWinningWords))
                    
        #Clean and select
        chosenKeywordsSet = self._choose_keywords(keyWordsSet, quoted_pieces_set)
        self.key_words_set = chosenKeywordsSet
        
        #Remove the temporary directory
        if os.path.exists(self.output_directory):
            shutil.rmtree(self.output_directory)
        
        return self.key_words_set
        
    
    def _find_keywords_from_list_in_text(self) -> None:
        """
        Loops through the set of keywords from the good keywords file and looks for their occurrences in the text.
        Takes the keyword in the form it first occurs in the text and add it to a hash.
        Return the new hash: key: keyword form the list of good keywords in the form in which it occurs in the text; value: the number of times this keyword occurred in the text.
        """
        hash_keywords_from_list = {}
        for w in self._good_keywords_set:
            found = re.findall("[ \-\.\_\:\&\'\*\+\?\!\,]+" + w.lower() + "[ \-\.\_\:\&\'\*\+\?\!\,]+", self.file_text, re.MULTILINE | re.IGNORECASE )
            how_many_matches = len(found)
            
            if how_many_matches > 0:
                #Take the first match
                cleaned_keyword = found[0].strip('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ ') #Remove punctuation and spaces from the beginning and the end of the string
                self._add_item_to_hash_augment_count(cleaned_keyword, hash_keywords_from_list, how_many_matches)
                
        return hash_keywords_from_list
    
    
    def _take_forms_of_lemmas_with_unique_form(self, proper_nouns_hash, token_dict, noun_lemma_dict):
        """
        Loops through a data structure containing lemmas and checks if its elements have only one corresponding form.
        If a lemma has only one form, we take the form and not the lemma.
        """
        newHash = {}
        for el in proper_nouns_hash:
            if el not in noun_lemma_dict:
                newHash[el] = proper_nouns_hash[el]
                continue
            if el.lower() in token_dict and len(token_dict[el.lower()]) == 1:
                (element,) = token_dict[el.lower()]
                if element[0].isupper():
                    newHash[element] = noun_lemma_dict[el]
                else:
                    newHash[el] = noun_lemma_dict[el]
            else:
                newHash[el] = noun_lemma_dict[el]
        
        return newHash
    
    
    def _delete_derivationally_related_words(self, keyWordsSet: set, relatedGroupsHash: dict) -> None:
        """
        Delete derivationally related words from the keywords set.
        """        
        setOfWordsToDelete = set()
        for word in relatedGroupsHash:            
            alreadyDeleted = False
            
            for tag in self.lemma_token_to_POS[word]:
                if tag[0] == "N":
                    setOfWordsToDelete.union(relatedGroupsHash[word])
                    alreadyDeleted = True
                    break
                
            if alreadyDeleted == False:
                for w in relatedGroupsHash[word]:
                    for tag in self.lemma_token_to_POS[w]:
                        if tag[0] == "N":
                            tempSet = copy.deepcopy(relatedGroupsHash[word])
                            tempSet.remove(w)
                            setOfWordsToDelete.add(word)
                            setOfWordsToDelete.union(tempSet) #Add everything except this noun to the set of words that will be deleted from the keyword set
                            alreadyDeleted = True
                            break
                        
            #If there are no nouns in the set of words related to this word, we delete them all and keep this word (even if it is not a noun either) 
            if alreadyDeleted == False:
                setOfWordsToDelete.union(relatedGroupsHash[word])
        
        keyWordsSet = keyWordsSet.difference(setOfWordsToDelete)
        
        return keyWordsSet
                
        
    
    def _find_best_from_TreeTagger(self, properNounWithNamesSet: set, winningFromSmorHash: dict):
        winningFromSmorSet = self._delete_keywords_that_are_in_another_set(set(self.noun_lemma_dict.keys()), properNounWithNamesSet)
        
        newHash = {}
        for el in winningFromSmorSet:
            # If there is only one form corresponding to this lemma and it starts with a capital letter, take the form  and not the lemma
            if el.lower() in self.token_dict and len(self.token_dict[el.lower()]) == 1:
                (element,) = self.token_dict[el.lower()]
                if element[0].isupper():
                    newHash[element] = self.noun_lemma_dict[el]
                else:
                    newHash[el] = self.noun_lemma_dict[el]
            else:
                newHash[el] = self.noun_lemma_dict[el]

        self._join_case_differences(newHash)
        
        sorted_smorLemmasCountHash = sorted(newHash.items(), key=operator.itemgetter(1))
        sorted_smorLemmasCountHash.reverse()

        values_smorLemmasCountHash = sorted(newHash.values())
        values_smorLemmasCountHash.reverse()
        moyenneSmorf = sum(values_smorLemmasCountHash)/len(values_smorLemmasCountHash)

        for m in range(len(values_smorLemmasCountHash)):
            if sorted_smorLemmasCountHash[m][1] > moyenneSmorf and not sorted_smorLemmasCountHash[m][0].isdigit():
                winningFromSmorHash[sorted_smorLemmasCountHash[m][0]] = sorted_smorLemmasCountHash[m][1]

        len_winningFromSmorHash = len(winningFromSmorHash)
        while len_winningFromSmorHash > 10:
            len_winningFromSmorHash = self._reduce_winning_from_SMOR_hash(winningFromSmorHash)
            
    
    def _choose_keywords(self, keyWordsSet: set, quoted_pieces_set: set) -> set:
        """
        Chooses the final set of keywords to present to the user.
        """
        
        if self.lang == "de":
            keyWordsSet = self._find_compounds_of_best_SMOR_suggestions(keyWordsSet, self.noun_parts_and_their_compounds_hash)
        
        keyWordsSet = keyWordsSet.union(self.from_good_words_proper_nouns)
        
        if self.lang == "de":
            wordsToDelete = self._get_keywords_that_are_part_of_other_keywords(keyWordsSet) #Based on SMOR analysis
            keyWordsSet = keyWordsSet.difference(wordsToDelete)
        
        keyWordsSet = self._find_words_that_never_go_alone(list(keyWordsSet), self.token_dict, self.lemma_dict, 1) #Added
            
        cleaned_intersectionOfSets = self._delete_keywords_that_are_in_another_set(keyWordsSet, keyWordsSet) #Delete duplicates
        cleaned = self._delete_keywords_that_are_in_another_set(cleaned_intersectionOfSets, self.proper_noun_with_names_set)
                
        self.proper_noun_with_names_set = self._delete_keywords_that_are_in_another_set(self.proper_noun_with_names_set, cleaned)
        
        cleaned = cleaned.union(self.proper_noun_with_names_set)
        
        if self.lang == "de":
            cleaned = self._delete_POSes_from_beginning_with_SMOR(cleaned, self.tagger_de)
            cleaned = self._delete_POSes_from_end_with_SMOR(cleaned, self.tagger_de)
        elif self.lang == "it":
            cleaned = self._delete_POSes_from_beginning_with_TreeTagger(cleaned, self.tagger_it)
            cleaned = self._delete_POSes_from_end_with_TreeTagger(cleaned, self.tagger_it)
                    
        quoted_pieces_set = self._delete_keywords_that_are_in_another_set(quoted_pieces_set, cleaned_intersectionOfSets)
        cleaned = cleaned.union(quoted_pieces_set)
        
        result = self._find_overlapping_keywords_rec(cleaned)
        
        result = self._join_case_differences_set(result)
        
        result = self._clean_similar_keywords_with_edit_distance(result)
        result2 = set()
        for keyword in result:
            keyword = keyword.replace("###","*")
            keyword = keyword.replace("===","|")
            keyword = keyword.replace("#=#","+")
            result2.add(keyword)
        
        return result2


    def _find_compounds_of_best_SMOR_suggestions(self, maxFromSmorSet: set, nounPartsAndTheirCompoundsHash: dict) -> set:
        mostFrequentFullForms = set()
        for wordPart in maxFromSmorSet:
            if wordPart in nounPartsAndTheirCompoundsHash:
                fullFormsHash = nounPartsAndTheirCompoundsHash[wordPart]
            
                sorted_fullFormsHash = sorted(fullFormsHash.items(), key=operator.itemgetter(1))
                sorted_fullFormsHash.reverse()
                mostFrequentFullForms.add(sorted_fullFormsHash[0][0])
            else:
                mostFrequentFullForms.add(wordPart)
        return mostFrequentFullForms
    
    
    def _add_words_to_delete_with_edit_distance_de(self, theSet: set, setToDelete: set) -> None:
        """
        Find similar German words with edit distance and add the to the set to delete.
        """
        for word in theSet:
            try:
                wordPartsSet = self.compound_lemma_to_parts[word]
            except:
                continue
            
            for word2 in theSet:
                if word.lower() != word2.lower():
                    try:
                        word2PartsSet = self.compound_lemma_to_parts[word2]
                        intersectionOfPartSets = wordPartsSet.intersection(word2PartsSet)
                        #If 2 words contain the  same part, we take only  one of them
                        if len(intersectionOfPartSets) > 0:
                            self._add_the_shortest_word_to_set(setToDelete, word, word2)
                        else:
                            self._add_with_edit_distance(setToDelete, word.lower(), word2.lower())
                    except:
                        self._add_with_edit_distance(setToDelete, word.lower(), word2.lower())
              
                
    def _add_words_to_delete_with_edit_distance_it(self, theSet: set, setToDelete: set) -> None:
        for word in theSet:
            for word2 in theSet:
                if word.lower() != word2.lower():
                    self._add_with_edit_distance(setToDelete, word.lower(), word2.lower())

    def _clean_similar_keywords_with_edit_distance(self, theSet: set) -> None:
        """
        Delete from the given set of keywords the keywords that differ very little.
        The difference is based on the edit distance between lowercase words.
        """
        newSet = set()
        setToDelete = set()
        
        if self.lang == "de":
            self._add_words_to_delete_with_edit_distance_de(theSet, setToDelete)
        if self.lang == "it":
            self._add_words_to_delete_with_edit_distance_it(theSet, setToDelete)
                
        newSet = theSet.difference(setToDelete)
        return newSet

    
    def _get_keywords_that_are_part_of_other_keywords(self, keyWordsSet: set) -> set:
        """
        Finds keywords that are part of other keywords of the same set.
        The comparison is based on SMOR analyses.
        Returns a set of keywords to delete.
        """
        setOfKeywordsToDelete = set()
        for keyword in keyWordsSet:
            for secondKeyword in keyWordsSet:
                if keyword != secondKeyword and keyword.lower() in secondKeyword.lower():
                    #If the words are long and one is part of another, I do not analyse with SMOR
                    if len(keyword) > 5:
                        setOfKeywordsToDelete.add(keyword)
                        continue
                
                    smorAnalysisFirst=""
                    try:
                        smorAnalysisFirst=self.smor_analysis_hash[secondKeyword][0]
                    except:
                        try:
                            smorAnalysisFirst=self.smor_analysis_hash[self.token_to_lemma_dict_original_case[secondKeyword]][0]
                        except:
                            #Analyse the second word with SMOR
                            lemmasFileName = self.output_directory + re.sub("[^a-zA-Z]", "", secondKeyword) + ".txt"
                            smorOutFile = lemmasFileName+".smor.txt"
                        
                            if not os.path.isfile(smorOutFile):
                                lemmaListForSmor = io.open(lemmasFileName, mode="w", encoding="utf-8")
                                lemmaListForSmor.write(secondKeyword+"\n")
                                lemmaListForSmor.close()
                            try:
                                subprocess.check_output([SMOR_EXECUTABLE, lemmasFileName, smorOutFile], cwd=SMOR_FOLDER)
                            except subprocess.CalledProcessError as error:
                                logging.error("error analysing "+lemmasFileName+" with SMOR")
                                logging.error(error.output)
                            
                            #Read smor output line by line
                            newWord = 0
                            if os.path.isfile(smorOutFile):
                                smor_stream = io.open(smorOutFile, mode="r", encoding="utf-8")
                                for smorLine in smor_stream:
                                    smorLine = smorLine.rstrip()
                                    if smorLine[0] == ">":
                                        newWord = 0
                                    else:
                                        newWord += 1
                                    #Take the first analysis
                                    if newWord == 1:
                                        smorAnalysisFirst=smorLine
                                        
                                smor_stream.close()
                                
                    setOfWordParts = set(re.split(r"<[^>]+>", smorAnalysisFirst))
                    setOfWordParts = set(x.lower() for x in setOfWordParts)
                    if keyword.lower() in setOfWordParts:
                        setOfKeywordsToDelete.add(keyword)
        return setOfKeywordsToDelete

    
    def _find_best_from_SMOR(self, smorLemmasCountHash: dict, winningFromSmorHash: dict, properNounWithNamesSet: set, nounPartsAndTheirCompoundsHash: dict) -> None:
        """
        Find the most frequent lemmas from a hash generated with SMOR.
        Returns not more than 10 lemmas.
        """        
        commonFullFormsHash = {}
        alreadyTakenScoresHash = {}
        self._treat_winning_from_SMOR(smorLemmasCountHash, nounPartsAndTheirCompoundsHash, commonFullFormsHash, alreadyTakenScoresHash)

        smorLemmasCountHash.update(commonFullFormsHash)

        winningFromSmorSet = self._delete_keywords_that_are_in_another_set(set(smorLemmasCountHash.keys()), properNounWithNamesSet)

        newHash = {}
        for el in winningFromSmorSet:
            newHash[el] = smorLemmasCountHash[el]

        self._join_case_differences(newHash)

        sorted_smorLemmasCountHash = sorted(newHash.items(), key=operator.itemgetter(1))
        sorted_smorLemmasCountHash.reverse()

        values_smorLemmasCountHash = sorted(newHash.values())
        values_smorLemmasCountHash.reverse()
        moyenneSmorf = sum(values_smorLemmasCountHash)/len(values_smorLemmasCountHash)

        for m in range(len(values_smorLemmasCountHash)):
            if sorted_smorLemmasCountHash[m][1] > moyenneSmorf and not sorted_smorLemmasCountHash[m][0].isdigit():
                winningFromSmorHash[sorted_smorLemmasCountHash[m][0]] = sorted_smorLemmasCountHash[m][1]

        len_winningFromSmorHash = len(winningFromSmorHash)
        while len_winningFromSmorHash > 10:
            len_winningFromSmorHash = self._reduce_winning_from_SMOR_hash(winningFromSmorHash)

        self._delete_words_with_same_parts(winningFromSmorHash, alreadyTakenScoresHash)
    
    
    def _reduce_winning_from_SMOR_hash(self, winningFromSmorHash: dict) -> int:
        """
        Reduces the number of keyword candidates taking only candidates with the highest scores.
        """
        winningFromSmorHash2 = {}
        sorted_smorLemmasCountHash = sorted(winningFromSmorHash.items(), key=operator.itemgetter(1))
        sorted_smorLemmasCountHash.reverse()

        values_smorLemmasCountHash = sorted(winningFromSmorHash.values())
        values_smorLemmasCountHash.reverse()
        meanSmorf = sum(values_smorLemmasCountHash)/len(values_smorLemmasCountHash)

        for m in range(len(values_smorLemmasCountHash)):
            if sorted_smorLemmasCountHash[m][1] > meanSmorf:
                winningFromSmorHash2[sorted_smorLemmasCountHash[m][0]] = sorted_smorLemmasCountHash[m][1]

        winningFromSmorHash.clear()
        winningFromSmorHash.update(winningFromSmorHash2)

        return len(winningFromSmorHash)

    
    def _join_case_differences(self, smorLemmasCountHash: dict) -> None:
        """
        Deletes keys that differ only in case from the hash.
        """        
        smorLemmasCountHashNew = {}
        keysTodelete = set()
        for lemma in smorLemmasCountHash:
            for lemma2 in smorLemmasCountHash:
                if lemma != lemma2 and lemma.lower() == lemma2.lower():
                    if lemma not in keysTodelete and lemma2 not in keysTodelete:
                        smorLemmasCountHashNew.update({lemma.lower():smorLemmasCountHash[lemma]+smorLemmasCountHash[lemma2]})
                        # We delete the least frequent form
                        if smorLemmasCountHash[lemma2] <= smorLemmasCountHash[lemma]:
                            keysTodelete.add(lemma2)
                        else:
                            keysTodelete.add(lemma)

        for key in keysTodelete:
            try:
                del smorLemmasCountHash[key]
            except KeyError:
                pass

        for l in smorLemmasCountHash:
            if l.lower() in smorLemmasCountHashNew:
                smorLemmasCountHash[l] = smorLemmasCountHashNew[l.lower()]
                
    def _join_case_differences_set(self, smorLemmasCountSet: set) -> None:
        """
        Deletes keys that differ only in case from the hash.
        """
        keysTodelete = set()
        for lemma in smorLemmasCountSet:
            for lemma2 in smorLemmasCountSet:
                if lemma != lemma2 and lemma.lower() == lemma2.lower():
                    if lemma not in keysTodelete and lemma2 not in keysTodelete:
                        keysTodelete.add(lemma2)

        return smorLemmasCountSet.difference(keysTodelete)
        
    
    def _register_words_in_tables(self, word: str, word2: str, winningFromSmorHash: dict, greaterScoresHash: dict, wordsWithSameParts: dict) -> None:
        """
        Finds words containing the same parts (based on SMOR analyses).
        """
        if winningFromSmorHash[word] >= winningFromSmorHash[word2] and word2 not in greaterScoresHash:
            greaterScoresHash.add(word)
        elif winningFromSmorHash[word2] >= winningFromSmorHash[word] and word not in greaterScoresHash:
            greaterScoresHash.add(word2)

        if word not in wordsWithSameParts:
            wordsWithSameParts[word] = {word, word2}
        else:
            wordsWithSameParts[word].add(word2)

        if word2 not in wordsWithSameParts:
            wordsWithSameParts[word2] = {word, word2}
        else:
            wordsWithSameParts[word2].add(word)
    
    
    def _delete_words_with_same_parts(self, winningFromSmorHash: dict, alreadyTakenScoresHash: dict) -> None:
        """
        Deletes from the candidate keywords words containing the same parts (detected with SMOR).
        Chooses the longest candidate.
        """
        wordsWithSameParts = {}
        greaterScoresHash = set()
        for word in winningFromSmorHash:
            for word2 in winningFromSmorHash:
                if word != word2:
                    if word in alreadyTakenScoresHash and word2 in alreadyTakenScoresHash:
                        if len(alreadyTakenScoresHash[word].intersection(alreadyTakenScoresHash[word2])) > 0:
                            self._register_words_in_tables(word, word2, winningFromSmorHash, greaterScoresHash, wordsWithSameParts)
                    elif word in alreadyTakenScoresHash:
                        if word2 in alreadyTakenScoresHash[word]:
                            self._register_words_in_tables(word, word2, winningFromSmorHash, greaterScoresHash, wordsWithSameParts)
                    elif word2 in alreadyTakenScoresHash:
                        if word in alreadyTakenScoresHash[word2]:
                            self._register_words_in_tables(word, word2, winningFromSmorHash, greaterScoresHash, wordsWithSameParts)


        greaterScoresHash2 = set()
        wordsToDelete = set()
        for word in greaterScoresHash:
            for word2 in greaterScoresHash:
                if word != word2:
                    if word in alreadyTakenScoresHash and word2 in alreadyTakenScoresHash:
                        if len(alreadyTakenScoresHash[word].intersection(alreadyTakenScoresHash[word2])) > 0:
                            self._add_to_delete(winningFromSmorHash, word, word2, wordsToDelete)
                    elif word2 in alreadyTakenScoresHash:
                        if word in alreadyTakenScoresHash[word2]:
                            self._add_to_delete(winningFromSmorHash, word, word2, wordsToDelete)
                    elif word in alreadyTakenScoresHash:
                        if word2 in alreadyTakenScoresHash[word]:
                            self._add_to_delete(winningFromSmorHash, word2, word, wordsToDelete)

        greaterScoresHash2 = greaterScoresHash.difference(wordsToDelete)

        wordsToKeep = {}
        for word in winningFromSmorHash:
            if word in greaterScoresHash2:
                wordsToKeep[word] = winningFromSmorHash[word]
            elif word not in wordsWithSameParts:
                wordsToKeep[word] = winningFromSmorHash[word]

        winningFromSmorHash.clear()
        winningFromSmorHash.update(wordsToKeep)
    
    
    def _add_to_delete(self, winningFromSmorHash: dict, word:str, word2: str, wordsToDelete: set) -> None:
        """
        Chooses which of the 2 given words to delete from the keyword candidates based on the score associated to them.
        """
        if winningFromSmorHash[word] > winningFromSmorHash[word2]:
            wordsToDelete.add(word2)
        elif winningFromSmorHash[word] == winningFromSmorHash[word2]:
            if word not in wordsToDelete and word2 not in wordsToDelete:
                wordsToDelete.add(word2)
        else:
            wordsToDelete.add(word)
        
    
    def _treat_winning_from_SMOR(self, smorLemmasCountHash: dict, nounPartsAndTheirCompoundsHash: dict, commonFullFormsHash: dict, alreadyTakenScoresHash: dict) -> None:
        """
        Takes compounds from smorLemmasCountHash, finds parts that occur in more than 1 compound and finds their full forms.
        """
        for w in smorLemmasCountHash:
            for w2 in smorLemmasCountHash:
                if w != w2:
                    if w in nounPartsAndTheirCompoundsHash and w2 in nounPartsAndTheirCompoundsHash:
                        wFullWordsSet = set(nounPartsAndTheirCompoundsHash[w].keys())
                        w2FullWordsSet = set(nounPartsAndTheirCompoundsHash[w2].keys())
                        commonFullForms = wFullWordsSet.intersection(w2FullWordsSet)

                        for cFF in commonFullForms:
                            if cFF not in commonFullFormsHash:
                                commonFullFormsHash[cFF] = smorLemmasCountHash[w]+smorLemmasCountHash[w2]
                                alreadyTakenScoresHash[cFF] = {w, w2}
                            else:
                                if w not in alreadyTakenScoresHash[cFF]:
                                    commonFullFormsHash[cFF] += smorLemmasCountHash[w]
                                    alreadyTakenScoresHash[cFF].add(w)

                                if w2 not in alreadyTakenScoresHash[cFF]:
                                    commonFullFormsHash[cFF] += smorLemmasCountHash[w2]
                                    alreadyTakenScoresHash[cFF].add(w2)
                                
    
    def _delete_POSes_from_end(self, wholeKeywordFirstFormTable: list, posesCopy: list) -> None:
        """
        Deletes articles, prepositions, connectives from the end of a table containing keywords.
        """
        regex_italian_words = r"^(i|di|si|che|essere|fos(si|se|sero|te|simo)|er(o|a|ano|avate|avamo)|è|sono|si(a|amo|ete|ate)|avere|h(a|o|anno)|avev(o|i|a|amo|ate|ano)|avete|avendo|abbi(a|amo|ano|ate))$"
        
        if len(posesCopy) <= 1:
            return
        if self.lang == "it":
            if posesCopy[-1][0] == "V" or re.match(r"(ADJA|ADJD|ADV|APPR|CON|DET:def|DET:indef|PRE|PRE:det|PRO:demo|\$.)", posesCopy[-1])  or re.match(regex_italian_words, wholeKeywordFirstFormTable[-1]):
                wholeKeywordFirstFormTable.pop()
                posesCopy.pop()
                self._delete_POSes_from_end(wholeKeywordFirstFormTable, posesCopy)
            else:
                return
        elif self.lang == "de":
            if posesCopy[-1][0] == "V" or re.match(r"(AP|KO|AR|PT|\$.)", posesCopy[-1][:2]):
                wholeKeywordFirstFormTable.pop()
                posesCopy.pop()
                self._delete_POSes_from_end(wholeKeywordFirstFormTable, posesCopy)
            else:
                return
    
    
    def _delete_POSes_from_end_set(self, wholeKeywordFirstFormTable: list, posesCopy: list) -> None:
        """
        Deletes articles, prepositions, connectives from the end of a table containing keywords.
        """
        regex_italian_words = r"^(i|di|si|che|essere|fos(si|se|sero|te|simo)|er(o|a|ano|avate|avamo)|è|sono|si(a|amo|ete|ate)|avere|h(a|o|anno)|avev(o|i|a|amo|ate|ano)|avete|abbi(a|amo|ano|ate))$"
        
        if len(posesCopy) <= 1:
            return
        if self.lang == "it":
            for pos in posesCopy[-1]:
                if re.match(r"(ADJA|ADJD|ADV|APPR|CON|DET:def|DET:indef|PRE|PRE:det|PRO:demo|PRO:poss|\$.)", pos)  or re.match(regex_italian_words, wholeKeywordFirstFormTable[-1]):
                    wholeKeywordFirstFormTable.pop()
                    posesCopy.pop()
                    self._delete_POSes_from_end_set(wholeKeywordFirstFormTable, posesCopy)
            return
        elif self.lang == "de":
            for pos in posesCopy[-1]:
                if pos[0] == "V" or re.match(r"(AP|KO|AR|PT|\$.)", pos[:2]):
                    wholeKeywordFirstFormTable.pop()
                    posesCopy.pop()
                    self._delete_POSes_from_end_set(wholeKeywordFirstFormTable, posesCopy)
            return
            
    
    def _delete_POSes_from_end_with_SMOR(self, properNounWithNamesSet: set, tagger: object) -> set:
        """
        Deletes words such as articles, prepositions etc. from the end of keywords.
        """
        newKeywordsSet = set()

        for keyword in properNounWithNamesSet:
            tags = tagger.tag_text(keyword)
            tokens = []
            poses = []
            self._create_POSes_tokens_with_SMOR(tags, tokens, poses, keyword)                            
            posesCopy = list(poses)
            self._delete_POSes_from_end(tokens, posesCopy)        
            #If the keyword only consists of 1 adjective, we take it with its followers
            if len(tokens) == 1 and poses[0][:3] == "ADJ":
                #We find the follower(s)
                adjWithFollowers=self._find_follower_for_adj(tokens[0]).strip()
                #We delete the follower(s), if they are irrelevant part of speech (article, preposition etc.)
                tags_AdjWithFollowers = tagger.tag_text(adjWithFollowers)
                tokens_AdjWithFollowers = []
                poses_AdjWithFollowers = []
                
                self._create_POSes_tokens_with_SMOR(tags_AdjWithFollowers, tokens_AdjWithFollowers, poses_AdjWithFollowers, adjWithFollowers)
                posesCopy_AdjWithFollowers = list(poses_AdjWithFollowers)
                self._delete_POSes_from_end(tokens_AdjWithFollowers, posesCopy_AdjWithFollowers)
            
                wholeAdjFirstFormString = ""
                spaceAdj = ""
                for ta in range(len(tokens_AdjWithFollowers)):
                    if ta > 0:
                        spaceAdj = " "
                    wholeAdjFirstFormString += spaceAdj+tokens_AdjWithFollowers[ta]
                #We add the obtained keyword to the keyword set
                newKeywordsSet.add(wholeAdjFirstFormString.strip())
                #We pass to the next keyword
                continue

            wholeKeywordFirstFormString = ""
            space = ""
            for t in range(len(tokens)):
                if t > 0:
                    space = " "
                wholeKeywordFirstFormString += space+tokens[t]
            #We add the obtained keyword to the keyword set
            newKeywordsSet.add(wholeKeywordFirstFormString.strip())

        return newKeywordsSet
    
    
    def _delete_POSes_from_end_with_TreeTagger(self, properNounWithNamesSet: set, tagger: object) -> set:
        """
        Deletes words such as articles, prepositions etc. from the end of keywords.
        """
        newKeywordsSet = set()

        for keyword in properNounWithNamesSet:
            tags = tagger.tag_text(keyword)
            tokens = []
            poses = []
            for tag in tags:
                ttArray = tag.split("\t")
                token = ttArray[0]
                tokenCleaned = re.sub('\'$', '', token)
                if "replaced-dns" in tokenCleaned or "repdns text=" in tokenCleaned:
                    continue
                try:
                    posesSet = self.lemma_token_to_POS[tokenCleaned]
                except:
                    posesSet = {ttArray[1]}
                tokens.append(token)
                poses.append(posesSet)
            
            posesCopy = list(poses)
            
            initial_length_of_tokens = len(tokens)
            self._delete_POSes_from_end_set(tokens, posesCopy)
            length_of_tokens_after_deleting = len(tokens)
            
            #If the keyword only consists of 1 adjective, we take it with its followers
            wholeKeywordFirstFormString = ""
            space = ""
            if initial_length_of_tokens != length_of_tokens_after_deleting:
                for t in range(len(tokens)):
                    if t > 0:
                        space = " "
                    wholeKeywordFirstFormString += space+tokens[t]
            else:
                wholeKeywordFirstFormString = keyword
            #We add the obtained keyword to the keyword set
            newKeywordsSet.add(wholeKeywordFirstFormString.strip())

        return newKeywordsSet
    

    def _find_follower_for_adj(self, adjFirstForm):
        """
        Finds the word that frequently follows the given adjective in the text.
        """
        alreadyLookedForItsRightNeighbour = set()
        couplesHash = {}
        couplesWords = {}
        self._recurrent_following_word_finderAdj(adjFirstForm, self.token_dict.keys(), self.lemma_dict, couplesHash, couplesWords, adjFirstForm, alreadyLookedForItsRightNeighbour, 0)

        if adjFirstForm in couplesHash:
            return couplesHash[adjFirstForm]
        else:
            return adjFirstForm
    
    
    def _recurrent_following_word_finderAdj(self, word, listOfCandidates, winningProperNounsWithFrequencies, couplesHash, couplesWords, originalWord, alreadyLookedForItsRightNeighbour, barier: int) -> None:
        """
        Finds the word that is a frequent follower of the given adjective in the text, if such a word exists.
        """        
        for word2 in listOfCandidates:
            if word in alreadyLookedForItsRightNeighbour:
                return
            if word != word2 and len(word) > 0:
                #Replace the word by the set of its forms
                formsForPattern = self._generate_forms_for_patterns(word, self.token_dict)
                formsForPattern2 = self._generate_forms_for_patterns(word2, self.token_dict)

                trueOrFalse = self._word_always_followed_by_word2_adj(couplesHash, couplesWords, winningProperNounsWithFrequencies, formsForPattern, formsForPattern2, word, word2, originalWord, barier)
                if trueOrFalse == True:
                    alreadyLookedForItsRightNeighbour.add(word)
        return

    
    def _word_always_followed_by_word2_adj(self, couplesHash: dict, couplesWords: dict, winningProperNounsWithFrequencies: dict, formsForPattern: str, formsForPattern2: str, word: str, word2: str, wordOrig: str, barier: int) -> None:
        """
        Finds out if an adjective (word) is in most cases followed by word2 in the text.
        """
        
        patternTogether = re.compile(formsForPattern+r"[ \-\.\_\:\&\'\*\+]+"+formsForPattern2+r"([^a-zA-Z\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ]|$)", re.IGNORECASE)
        
        numberEquals = 0
        numberUnequals = 0
        groupToTake = ""
        #If word is at least once preceded by word2
        m = re.findall(patternTogether, self.file_text)
        if len(m) > 0:
            pattern2 = re.compile(formsForPattern+r"(?:[^a-zA-Z\'\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ\,\"]+[a-zA-Z\'\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ\.]+){0,1}([^a-zA-Z\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ]|$)", re.IGNORECASE)
            allGroups = []
            iterator = pattern2.finditer(self.file_text)
            for match in iterator:
                allGroups.append(match.group())

            if len(allGroups) > 0:
                for group in allGroups:
                    if not patternTogether.match(group):
                        numberUnequals += 1
                    else:
                        groupToTake = group
                        numberEquals += 1

                if len(formsForPattern) == 3: #If it's one letter
                    numberUnequals = 0
                if numberEquals > barier:
                    if wordOrig in couplesHash:
                        newWord = (couplesHash[wordOrig]+groupToTake[(re.search(formsForPattern, groupToTake).end()):]).rstrip()
                        couplesHash[wordOrig] += groupToTake[(re.search(formsForPattern, groupToTake).end()):].rstrip()
                        if wordOrig in winningProperNounsWithFrequencies:
                            winningProperNounsWithFrequencies[newWord] = winningProperNounsWithFrequencies[wordOrig]
                        elif wordOrig.lower() in winningProperNounsWithFrequencies:
                            winningProperNounsWithFrequencies[newWord] = winningProperNounsWithFrequencies[wordOrig.lower()]
                        couplesWords[wordOrig].append(word2)
                    else:
                        couplesHash[wordOrig] = groupToTake.rstrip()
                        if wordOrig in winningProperNounsWithFrequencies:
                            winningProperNounsWithFrequencies[groupToTake] = winningProperNounsWithFrequencies[wordOrig]
                        elif wordOrig.lower() in winningProperNounsWithFrequencies:
                            winningProperNounsWithFrequencies[groupToTake] = winningProperNounsWithFrequencies[wordOrig.lower()]

                        couplesWords[wordOrig] = [word, word2]
                    return True
        return False
    
    
    def _delete_POSes_from_beginning_with_TreeTagger(self, keyWordsSetPlusBestOfSMOR: set, tagger: object) -> set:
        """
        Delete words corresponding to unwanted parts of speach from the beginning of the keywords.
        """
        newSet = set()
        
        verbs_to_remove = set()
        
        for keyword in keyWordsSetPlusBestOfSMOR:
            #Delete punctuation from beginning and end of keyword
            remove = regex.compile(r'^([\p{C}]|[\p{P}]|[\p{Z}])+', regex.UNICODE)
            keyword = remove.sub(u"", keyword)
            remove = regex.compile(r'([\p{C}]|[\p{P}]|[\p{Z}])+$', regex.UNICODE)
            keyword = remove.sub(u"", keyword)

            tokens = []
            poses = []
            tags = tagger.tag_text(keyword)
            
            if len(tags)<1:
                continue
            
            for tag in tags:
                ttArray = tag.split("\t")
                token = ttArray[0]
                tokenCleaned = re.sub('\'$', '', token)
                if "replaced-dns" in tokenCleaned or "repdns text=" in tokenCleaned:
                    continue
                
                if len(tags) == 1 and ttArray[1][0:3] == "VER": #if a keyword is just a verb, delete it
                    verbs_to_remove.add(keyword)
                    continue
                try:
                    posesSet = self.lemma_token_to_POS[tokenCleaned]
                except:
                    posesSet = {ttArray[1]}
                
                tokens.append(token)
                poses.append(posesSet)
            
            posesCopy = list(poses)
            
            initial_length_of_tokens = len(tokens)
                        
            self._delete_POSes_from_beginning_set(tokens, posesCopy)
            
            length_of_tokens_after_deleting = len(tokens)
            
            wholeKeywordFirstFormString = ""
            space = ""
            if length_of_tokens_after_deleting != initial_length_of_tokens:
                for t in range(len(tokens)):
                    if t > 0:
                        space = " "
                    wholeKeywordFirstFormString += space+tokens[t]
            else:
                wholeKeywordFirstFormString = keyword

            newSet.add(wholeKeywordFirstFormString.strip())
        
        return newSet.difference(verbs_to_remove)
    
    
    def _delete_POSes_from_beginning_with_SMOR(self, keyWordsSetPlusBestOfSMOR: set, tagger: object) -> set:
        """
        Delete words corresponding to unwanted parts of speach from the beginning of the keywords.
        """
        
        newSet = set()

        for keyword in keyWordsSetPlusBestOfSMOR:
            #Delete punctuation from beginning and end of keyword
            remove = regex.compile(r'^([\p{C}]|[\p{P}]|[\p{Z}])+', regex.UNICODE)
            keyword = remove.sub(u"", keyword)
            remove = regex.compile(r'([\p{C}]|[\p{P}]|[\p{Z}])+$', regex.UNICODE)
            keyword = remove.sub(u"", keyword)

            tokens = []
            poses = []
            tags = tagger.tag_text(keyword)
            self._create_POSes_tokens_with_SMOR(tags, tokens, poses, keyword)
            posesCopy = list(poses)
            self._delete_POSes_from_beginning(tokens, posesCopy)

            wholeKeywordFirstFormString = ""
            space = ""
            for t in range(len(tokens)):
                if t > 0:
                    space = " "
                wholeKeywordFirstFormString += space+tokens[t]

            newSet.add(wholeKeywordFirstFormString.strip())

        return newSet
    
    def _delete_POSes_from_beginning_set(self, wholeKeywordFirstFormTable, posesCopy) -> None:
        """
        Deletes articles, prepositions, connectives etc. from the beginning of a table containing keywords.
        """
        if len(posesCopy) <= 1:
            return
        
        regex_italian_words = r"^(i|di|si|che|essere|fos(si|se|sero|te|simo)|er(o|a|ano|avate|avamo)|è|sono|si(a|amo|ete|ate)|avere|h(a|o|anno)|avev(o|i|a|amo|ate|ano)|avete|avendo|abbi(a|amo|ano|ate))$"
        
        if self.lang == "it":
            poses_to_delete_regex = r"(ADJA|ADJD|ADV|APPR|CON|DET:def|DET:indef|PRE|PRE:det|PRO:demo)"
        elif self.lang == "de":
            poses_to_delete_regex = r"(ADV|ART|APPR|APPART|APPRART|APPO|APZR|KON|PDS|PIS|PIAT|PIDAT|PDAT|PPER|PPOSS|PPOSAT|PRELS|PRELAT|PRF|PWS|PTKZU|PTKNEG|PTKVZ|PTKANT|PTKA|PWAT|PWAV|PAV)"
        
        for pos in posesCopy[0]: #Loop through the set of poses of the first word
            if re.match(poses_to_delete_regex, pos) or (len(wholeKeywordFirstFormTable)>0 and re.match(regex_italian_words, wholeKeywordFirstFormTable[0])):
                wholeKeywordFirstFormTable.pop(0)
                posesCopy.pop(0)
                self._delete_POSes_from_beginning_set(wholeKeywordFirstFormTable, posesCopy)
            elif len(wholeKeywordFirstFormTable)>0 and wholeKeywordFirstFormTable[0][0].islower() and re.match("CARD", pos): #If a number starts with a lowercase letter, we delete it
                wholeKeywordFirstFormTable.pop(0)
                posesCopy.pop(0)
                self._delete_POSes_from_beginning_set(wholeKeywordFirstFormTable, posesCopy)

        return
    
    
    def _delete_POSes_from_beginning(self, wholeKeywordFirstFormTable, posesCopy) -> None:
        """
        Deletes articles, prepositions, connectives etc. from the beginning of a table containing keywords.
        """
        if len(posesCopy) <= 1:
            return
        if self.lang == "it":
            poses_to_delete_regex = r"(ADJA|ADJD|ADV|APPR|CON|DET:def|PRE|PRE:det|PRO:demo)"
        elif self.lang == "de":
            poses_to_delete_regex = r"(ADV|ART|APPR|APPART|APPRART|APPO|APZR|KON|KOUS|PDS|PIS|PIAT|PIDAT|PDAT|PPER|PPOSS|PPOSAT|PRELS|PRELAT|PRF|PWS|PTKZU|PTKNEG|PTKVZ|PTKANT|PTKA|PWAT|PWAV|PAV)"
        
        if re.match(poses_to_delete_regex, posesCopy[0]) or (re.match(r"(i|di|si)", wholeKeywordFirstFormTable[0]) and self.lang == "it"):
            wholeKeywordFirstFormTable.pop(0)
            posesCopy.pop(0)
            self._delete_POSes_from_beginning(wholeKeywordFirstFormTable, posesCopy)
        elif wholeKeywordFirstFormTable[0][0].islower() and re.match("CARD", posesCopy[0]): #If a number starts with a lowercase letter, we delete it
            wholeKeywordFirstFormTable.pop(0)
            posesCopy.pop(0)
            self._delete_POSes_from_beginning(wholeKeywordFirstFormTable, posesCopy)
        else:
            return
    
    
    def _create_POSes_tokens_with_SMOR(self, tags: list, tokens: list, poses: list, keyword: str) -> None:
        """
        Performs SMOR analyses of the given tokens of which consists the given keyword.
        Deletes from the end tokens corresponnding to articles, prepositions, connectives etc.
        """
        smorOutFile = os.path.join(self.output_directory, "lemmas"+re.sub("[^a-zA-Z]", "", keyword)+".smor.txt")
        tokensFileName = os.path.join(self.output_directory, "lemmas"+re.sub("[^a-zA-Z]", "", keyword)+".txt")
        tokensListForSmor = io.open(tokensFileName, mode="w", encoding="utf-8")
    
        needSMOR=False
        smorAnalysisArray=[]
        
        for t in range(len(tags)):
            tag=tags[t]
            if 'replaced-dns' in tag:
                pos = tag.split('\t')[1]
                tokenList = re.findall('"([^"]*)"', tags[t+1])
                token = tokenList[0]
            elif 'repdns' in tag:
                continue
            else:
                ttArray = tag.split("\t")
                token = ttArray[0]
                pos = ttArray[1]
            tokens.append(token)
            poses.append(pos)
            try:
                smorAnalysisArray.append(self.smor_analysis_hash[token])
            except:
                try:
                    smorAnalysisArray.append(self.smor_analysis_hash[self.token_to_lemma_dict_original_case[token]])
                except:
                    needSMOR=True

            tokensListForSmor.write(token+"\n")

        tokensListForSmor.close()   
        
        if needSMOR:
            subprocess.check_output([SMOR_EXECUTABLE, tokensFileName, smorOutFile], cwd=SMOR_FOLDER)
            smorAnalysisArray = self._read_SMOR_result_to_array(smorOutFile)
        
        s = 0
        for smorArray in smorAnalysisArray:
            for line in smorArray:
                if re.search("no result for", line):
                    poses[s] = "deleted after SMOR"
                elif re.search(r"\<\+PREP\>", line) and token[0].islower():
                    poses[s] = "AP"
            s += 1
            
       
    def _read_SMOR_result_to_array(self, smorOutFile: str) -> list:
        """
        Reads the result of analyses by SMOR.
        Returns a list of lists. Each list contains all the analyses of a single word.
        """
        smorAnalysisArray = []
        wordNumber = -1
        if os.path.isfile(smorOutFile):
            smor_stream = io.open(smorOutFile, mode="r", encoding="utf-8")
            for smorLine in smor_stream:
                smorLine = smorLine.rstrip()
                if smorLine[0] == ">":
                    wordNumber += 1
                    smorAnalysisArray.append([])
                else:
                    smorAnalysisArray[wordNumber].append(smorLine)
            smor_stream.close()
        return smorAnalysisArray
    
    def _find_overlapping_keywords_rec(self, properNounWithNamesSet: set) -> set:
        """
        Recursive. Goes back when there are no keywords to delete.
        If 2 keywords that overlap (the end of 1 keyword is the beginning of another).
        Unites them and checks if the united version occurs in the text.
        If yes, replaces the keywords by their union.
        """
        joinedPNSet = set()
        notNeededMorePNSet = set()
        
        for pn in properNounWithNamesSet:
            for pn2 in properNounWithNamesSet:
                if pn != pn2:
                    overlap = self._get_overlap(pn, pn2)
                    if len(overlap) == 0:
                        continue

                    joinedPN = ""
                    if re.search(overlap, pn2)!=None and re.search(overlap, pn2).start() == 0:
                        joinedPN = pn+pn2[re.search(overlap, pn2).end():]
                    elif re.search(overlap, pn)!=None and re.search(overlap, pn).start() == 0:
                        joinedPN = pn2+pn[re.search(overlap, pn).end():]

                    if len(joinedPN) > 0:
                        if re.search(joinedPN, self.file_text):
                            joinedPNSet.add(joinedPN)
                            notNeededMorePNSet.add(pn)
                            notNeededMorePNSet.add(pn2)
                            
        if len(notNeededMorePNSet) == 0:
            return properNounWithNamesSet
        else:
            newSet = properNounWithNamesSet.difference(notNeededMorePNSet).union(joinedPNSet)
            newSet = self._find_overlapping_keywords_rec(newSet)
        
        return newSet
    
    def _find_overlapping_keywords(self, properNounWithNamesSet: set) -> set:
        """
        If 2 keywords that overlap (the end of 1 keyword is the beginning of another).
        Unites them and checks if the united version occurs in the text.
        If yes, replaces the keywords by their union.
        """
        joinedPNSet = set()
        notNeededMorePNSet = set()
        
        for pn in properNounWithNamesSet:
            for pn2 in properNounWithNamesSet:
                if pn != pn2:
                    overlap = self._get_overlap(pn, pn2)
                    if len(overlap) == 0:
                        continue

                    joinedPN = ""
                    if re.search(overlap, pn2).start() == 0:
                        joinedPN = pn+pn2[re.search(overlap, pn2).end():]
                    elif re.search(overlap, pn).start() == 0:
                        joinedPN = pn2+pn[re.search(overlap, pn).end():]

                    if len(joinedPN) > 0:
                        if re.search(joinedPN, self.file_text):
                            joinedPNSet.add(joinedPN)
                            notNeededMorePNSet.add(pn)
                            notNeededMorePNSet.add(pn2)

        newSet = properNounWithNamesSet.difference(notNeededMorePNSet).union(joinedPNSet)
        
        return newSet
    

    def _get_overlap(self, s1: str, s2: str) -> str:
        """
        Finds the overlap between 2 strings.
        Returns the string that represents the overlap.
        """
        s = difflib.SequenceMatcher(None, s1, s2)
        pos_a, pos_b, size = s.find_longest_match(0, len(s1), 0, len(s2))
        return s1[pos_a:pos_a+size]

    
    def _find_mean(self, sortedProperNounsHashValues: list) -> float:
        """
        Find the frequency above which keywords should be taken and below which they should be left out.
        """
        mean = sum(sortedProperNounsHashValues)/len(sortedProperNounsHashValues)
        numberToTake = 0
        numbers = []
        for v in sortedProperNounsHashValues:
            if mean > sortedProperNounsHashValues[-1]:
                if v >= mean:
                    numberToTake += 1
                    numbers.append(v)
            else:
                if v > mean:
                    numberToTake += 1
                    numbers.append(v)

        if numberToTake > 5:
            mean = self._find_mean(numbers)
   
        return mean
    
    def _find_best_proper_nouns(self, hash_keywords_from_list) -> set:
        '''
        We take only proper nouns with the highest score. If there are more than 1 proper nouns with the same highest score, we take them all. Otherwise, we take only 1.
        '''
        
        self.proper_nouns_hash.update(hash_keywords_from_list)
        
        #Check if some proper nouns go together
        joint_proper_nouns = self._find_proper_nouns_that_always_go_together(set(self.proper_nouns_hash.keys()), self.proper_nouns_hash)
        
        joint_proper_nouns = self._find_overlapping_keywords_rec(joint_proper_nouns)
        
        joint_proper_nouns = self._find_words_that_never_go_alone(list(joint_proper_nouns), self.token_dict, self.proper_nouns_hash, 1)
        
        newPNHash = {}
        pns_to_delete = set()
        for pn_joint in joint_proper_nouns:
            for pn in self.proper_nouns_hash:
                if pn != pn_joint and pn in pn_joint:
                    pns_to_delete.add(pn)
                    if pn_joint not in newPNHash:
                        newPNHash[pn_joint] = self.proper_nouns_hash[pn]
                    else:
                        if pn.lower() not in self.namesHashSet: #If the new part of the keyword which score we have to take into account is a surname, we don't add points (because the same surname may occur in different proper nouns and thus have a higher score)
                            newPNHash[pn_joint] = max(self.proper_nouns_hash[pn],newPNHash[pn_joint])
                        
        
        for pn in self.proper_nouns_hash:
            pn_clean = pn.replace(u'\xa0', u'').strip('!"#$%&\'()*+,-\./:;<=>?@[\\]^_`{|}~ \n')
            if pn not in pns_to_delete and pn not in newPNHash.keys() and pn_clean not in pns_to_delete and pn_clean not in newPNHash.keys():
                newPNHash[pn_clean] = self.proper_nouns_hash[pn]
        
        
        #Based on the proper mouns from the list, find those we certainly take, even if their score is low
        pns_to_take_for_sure_set = set()
        hash_from_list_to_add = {}
        for fl in hash_keywords_from_list:
            has_been_taken = False
            for pn in newPNHash:
                if fl in pn:
                   pns_to_take_for_sure_set.add(pn)
                   has_been_taken = True
            if has_been_taken == False:
                hash_from_list_to_add[fl] = hash_keywords_from_list[fl]
                
        
        #Find proper nouns with the best scores
        sortedProperNounsHashValues = sorted(newPNHash.values())
        sortedProperNounsHashValues.reverse()

        sorted_properNounsHash = sorted(newPNHash.items(), key=operator.itemgetter(1))
        sorted_properNounsHash.reverse()
        #We take proper nouns with a score greater than the mean. If all the proper nouns have the same score, we take none of them
        moyenne = self._find_mean(sortedProperNounsHashValues)
                
        winningProperNouns = []
        winningProperNounsWithFrequencies = {}
        numberOfTaken = 0
        for d in range(len(sortedProperNounsHashValues)):
            if moyenne > sortedProperNounsHashValues[-1]:
                if sortedProperNounsHashValues[d] >= moyenne:
                    winningProperNouns.append(sorted_properNounsHash[d][0])
                    numberOfTaken += 1
            else:
                if sortedProperNounsHashValues[d] > moyenne:
                    winningProperNouns.append(sorted_properNounsHash[d][0])
                    numberOfTaken += 1

        for pn in winningProperNouns:
            winningProperNounsWithFrequencies[pn] = newPNHash[pn]
        
        #Adding proper nouns from the "compulsory" ones that were on a list
        for pn in pns_to_take_for_sure_set:
            winningProperNounsWithFrequencies[pn] = newPNHash[pn]
        winningProperNounsWithFrequencies.update(hash_from_list_to_add)
        
        if numberOfTaken == 0 and len(newPNHash) < 10:
            winningProperNouns = newPNHash.keys()
            winningProperNounsWithFrequencies = copy.deepcopy(newPNHash)

        for entry in winningProperNounsWithFrequencies:
            if entry not in self.proper_nouns_hash:
                self.proper_nouns_hash[entry] = winningProperNounsWithFrequencies[entry]
        
        properNounWithNamesSet = set()    
        for pN in winningProperNounsWithFrequencies:
            properNounWithName = self._if_proper_noun_preceded_by_name(pN)
            properNounWithNamesSet.add(properNounWithName)
        
        properNounWithTitlesSet = set()
        for pN in properNounWithNamesSet:
            properNounWithName = self._if_proper_noun_preceded_by_title(pN)
            properNounWithTitlesSet.add(properNounWithName)
        

        for entry in self.proper_nouns_hash:
            if entry not in winningProperNounsWithFrequencies:
                winningProperNounsWithFrequencies[entry] = self.proper_nouns_hash[entry]
        
        properNounWithNamesSet = self._delete_keywords_that_are_in_another_set(properNounWithNamesSet, properNounWithNamesSet)
        properNounWithNamesSet = self._clean_similar_proper_nouns_with_edit_distance(properNounWithNamesSet)
        properNounWithNamesSet = self._clean_proper_nouns_that_only_differ_in_capitalisation(properNounWithNamesSet)
    
        return properNounWithNamesSet
    
    
    def _clean_proper_nouns_that_only_differ_in_capitalisation(self, properNounWithNamesSet: set) -> set:
        """
        Deletes proper nouns that only differ in capitalisation.
        """
        pnsToDelete = set()
        for pn in properNounWithNamesSet:
            for pn2 in properNounWithNamesSet:
                if pn != pn2 and pn.lower() == pn2.lower():
                    if pn not in pnsToDelete:
                        pnsToDelete.add(pn2)
    
        return properNounWithNamesSet.difference(pnsToDelete)

    
    def _clean_similar_proper_nouns_with_edit_distance(self, theSet: set) -> set:
        """
        Delete from the given set of keywords the keywords that differ very little.
        The difference is based on the edit distance between words without changing their case.
        """
        newSet = set()
        setToDelete = set()
        for word in theSet:
            for word2 in theSet:
                if word != word2:
                    self._add_with_edit_distance(setToDelete, word, word2)
        newSet = theSet.difference(setToDelete)
        return newSet


    def _add_with_edit_distance(self, setToDelete: set, word: str, word2: str) -> None:
        """
        If 2 words are more than 4 letters long and the edit distance between them (ignoring the umlaut) is smaller than 3,
        adds the shortest of the 2 words to the set of words to delete.
        """
        if len(word) > 4 and len(word2) > 4:
            wordClean = word.replace("ä", "a").replace("á", "a").replace("à", "a").replace("â", "a").replace("ü", "u").replace("ú", "u").replace("ù", "u").replace("û", "u").replace("ö", "o").replace("ó", "o").replace("ò", "o").replace("ô", "o").replace("ë", "e").replace("é", "e").replace("è", "e").replace("ê", "e").replace("É", "E").replace("È", "E").replace("Ë", "E").replace("Ê", "E").replace("Ä", "A").replace("Á", "A").replace("À", "A").replace("Â", "A").replace("Ü", "U").replace("Ú", "U").replace("Ù", "U").replace("Û", "U").replace("Ö", "O").replace("Ó", "O").replace("Ò", "O").replace("Ô", "O").replace("ß", "ss")
            wordClean2 = word2.replace("ä", "a").replace("á", "a").replace("à", "a").replace("â", "a").replace("ü", "u").replace("ú", "u").replace("ù", "u").replace("û", "u").replace("ö", "o").replace("ó", "o").replace("ò", "o").replace("ô", "o").replace("ë", "e").replace("é", "e").replace("è", "e").replace("ê", "e").replace("É", "E").replace("È", "E").replace("Ë", "E").replace("Ê", "E").replace("Ä", "A").replace("Á", "A").replace("À", "A").replace("Â", "A").replace("Ü", "U").replace("Ú", "U").replace("Ù", "U").replace("Û", "U").replace("Ö", "O").replace("Ó", "O").replace("Ò", "O").replace("Ô", "O").replace("ß", "ss")
            
            if editdistance.eval(wordClean, wordClean2) < 3:
                self._add_the_shortest_word_to_set(setToDelete, word, word2)
    
    
    def _add_the_shortest_word_to_set(self, setToDelete: set, word: str, word2: str) -> None:
        """
        Adds the shortest of the 2 words to the set.
        """
        wordToAdd = word
        otherWord = word2
        if len(word2) < len(word):
            wordToAdd = word2
            otherWord = word
        if otherWord not in setToDelete:
            setToDelete.add(wordToAdd)
    
    
    def _delete_keywords_that_are_in_another_set(self, keyWordsSet: set, properNounWithNamesSet: set) -> set:
        """
        Deletes keywords that are part of keywords of another set.
        """        
        keywordsToDeleteAfterProperNouns = set()
        for keyword in keyWordsSet:
            if keyword in self.token_dict:
                keyWordForms = "("
                for tok in self.token_dict[keyword]:
                    keyWordForms += tok + "|"
                keyWordForms = keyWordForms[:-1] + ")"
            else:
                keyWordForms = keyword
            for pn in properNounWithNamesSet:
                if pn == keyword:
                    continue
                
                if re.search(r"([ \-\.\_\,\:\&\"\'\*\+^$]+"+keyWordForms.lower()+r"|"+keyWordForms.lower()+r"[ \-\.\_\,\:\&\"\'\*\+^$]+)", pn.lower()) != None:
                    keywordsToDeleteAfterProperNouns.add(keyword)
        
        return keyWordsSet.difference(keywordsToDeleteAfterProperNouns)

    
    def _find_words_that_never_go_alone(self, arrayOfWinningWords: list, token_dict: dict, lemmaDict: dict, barier: int) -> set:
        """
        Among the winning words find those that in most cases are preceded or/and followed by other words. Replace them by these collocations.
        """        
        couplesHash = {}
        couplesWords = {}
        #Check if a word is only used with another word
        for word in arrayOfWinningWords:
            howManyWordsToLookFor = {0:3, word:0}
            alreadyLookedForItsRightNeighbour = set()
            formsForPattern = self._generate_forms_for_patterns(word, self.token_dict)

            self._recurrent_following_word_finder(word, self.token_dict.keys(), lemmaDict, couplesHash, couplesWords, howManyWordsToLookFor, word, alreadyLookedForItsRightNeighbour, barier, formsForPattern)
            
            alreadyLookedForItsLeftNeighbour = set()
            self._recurrent_preceding_word_finder(word, self.token_dict.keys(), lemmaDict, couplesHash, couplesWords, howManyWordsToLookFor, word, alreadyLookedForItsLeftNeighbour, barier, formsForPattern)
                    
        newArray = arrayOfWinningWords
        for n in range(len(arrayOfWinningWords)):
            word = arrayOfWinningWords[n]
            if word in couplesHash:
                if isinstance(couplesHash[word], list):
                    found_exact_match = False
                    max_len = 0
                    couple_to_take = ""
                    for couple in couplesHash[word]: #Look through all the variants of collocations of this word
                        if len(couple) > max_len:
                            max_len = len(couple)
                            couple_to_take = couple
                        if re.search(couple,self.file_text, re.IGNORECASE | re.MULTILINE): #Choose the one that actually can be found in the text
                            newArray[n] = couple
                            found_exact_match = True
                    if found_exact_match == False:  #If none can be found in the text, choose the longest one
                        word_list = couple_to_take.split(" ") #Check if the key word contains the same word twice.
                        if len(word_list) > len(set(word_list)): #If yes, do not take it directly, first find it in the text (muro contro muro -> muro contro muro contro muro)
                            shorter_word = self._shorten_keyword_from_end(word_list)
                            if len(shorter_word) > 0:
                                newArray[n] = shorter_word
                            else:
                                shorter_word = self._shorten_keyword_from_beginning(word_list)
                                if len(shorter_word) > 0:
                                    newArray[n] = shorter_word
                        else:
                            newArray[n] = couple_to_take
                else:
                    newArray[n] = couplesHash[word]
        #Remove duplicates
        keyWordsSet = set(newArray)
        return keyWordsSet
    
    
    def _shorten_keyword_from_end(self, word_list) -> str:
        """
        Shortens a key word that contains the same word at least twice.
        Shortens it from the end and tries to find the resulting word in the text.
        If finds the resulting word in the text, returns it.
        """
        if len(word_list) == 0:
            return ""
        new_word = ' '.join(word_list[:-1])
        if re.search(new_word, self.file_text, re.IGNORECASE | re.MULTILINE) == False:
            new_word = self._shorten_keyword( word_list[:-1])
        else:
            return new_word
        
        return new_word
    
    def _shorten_keyword_from_beginning(self, word_list) -> str:
        """
        Shortens a key word that contains the same word at least twice.
        Shortens it from the end and tries to find the resulting word in the text.
        If finds the resulting word in the text, returns it.
        """
        if len(word_list) == 0:
            return ""
        new_word = ' '.join(word_list[1:])
        if re.search(new_word, self.file_text, re.IGNORECASE | re.MULTILINE) == False:
            new_word = self._shorten_keyword( word_list[1:])
        else:
            return new_word
        
        return new_word
    
    
    def _if_proper_noun_preceded_by_title(self, properNoun: str) -> str:
        """
        Finds out if a proper noun is frequently preceded by a title.
        """
        pattern2 = re.compile(r"(?:[a-zA-Z'\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ]+[^a-zA-Z'\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ\,\.\:\;\?\!\'\"\@\<\>\|\=\}\{\]\[}\n]+){0,1}"+properNoun+r"[^a-zA-Z'\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ]", re.IGNORECASE)
        allGroups = []
        iterator = pattern2.finditer(self.file_text)

        for match in iterator:
            allGroups.append(match.group())

        if len(allGroups) < 1:
            return properNoun

        elif len(allGroups) > 0:
            for group in allGroups:
                maybeName = group[:-(len(properNoun)+1)].rstrip()
                if maybeName is not None:
                    if maybeName.lower() in self.titlesSet and not maybeName[0].islower():
                        maybeName = self._find_first_form_herr_frau(maybeName)
                        self.proper_nouns_hash[maybeName+" "+properNoun] = self.proper_nouns_hash[properNoun]
                        self.persons_set.add(maybeName+" "+properNoun)
                        return maybeName+" "+properNoun

        return properNoun
    
    
    def _find_first_form_herr_frau(self, maybeName: str) -> None:
        """
        Finds the first form of the words Herr and Frau.
        """
        hashOfForms = {'herren':'herr', 'herrn':'herr', 'frauen':'frau'}
        if maybeName.lower() in hashOfForms:
            title = hashOfForms[maybeName.lower()]
            return title[0].upper()+title[1:]
        return maybeName

    
    def _if_proper_noun_preceded_by_name(self, properNoun: str) -> str:
        """
        Finds out if a proper noun is frequently preceded by a name.
        """        
        pattern2 = re.compile(re.escape(r"(?:[a-zA-Z'\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ]+[^a-zA-Z'\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ\,\.\:\;\?\!\'\"\@\<\>\|\=\}\{\]\[}\n]+){0,1}"+properNoun+r"[^a-zA-Z'\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ]"), re.IGNORECASE)
        allGroups = []
        
        iterator = pattern2.finditer(re.escape(self.file_text))

        for match in iterator:
            allGroups.append(match.group())

        if len(allGroups) < 1:
            return properNoun

        elif len(allGroups) > 0:
            for group in allGroups:
                maybeName = group[:-(len(properNoun)+1)].rstrip()
                if maybeName is not None:
                    if maybeName.lower() in self.namesHashSet and not maybeName[0].islower():
                        self.proper_nouns_hash[maybeName+" "+properNoun] = self.proper_nouns_hash[properNoun]
                        self.persons_set.add(maybeName+" "+properNoun)
                        return maybeName+" "+properNoun

        return properNoun
    
    
    def _find_proper_nouns_that_always_go_together(self, properNounWithNamesSet: list, winningProperNounsWithFrequencies: dict) -> set:
        """
        Among the winning proper nouns find those that in most cases are preceded or/and followed by other words. Replace them by these collocations.
        """
        couplesHash = {}
        couplesWords = {}
        
        #Check if a word is only used with another word
        for word in properNounWithNamesSet:
            howManyWordsToLookFor = {0:3, word:0}
            alreadyLookedForItsRightNeighbour = set()
            if word.lower() in self.token_dict:
                formsForPattern = "("
                for form in self.token_dict[word.lower()]:
                    formsForPattern += form+"|"
                formsForPattern = formsForPattern[:-1]+")"
            else:
                formsForPattern = word
            self._recurrent_following_word_finder(word, list(properNounWithNamesSet), winningProperNounsWithFrequencies, couplesHash, couplesWords, howManyWordsToLookFor, word, alreadyLookedForItsRightNeighbour, 0, formsForPattern)
            
            alreadyLookedForItsLeftNeighbour = set()
            self._recurrent_preceding_word_finder(word, list(properNounWithNamesSet), winningProperNounsWithFrequencies, couplesHash, couplesWords, howManyWordsToLookFor, word, alreadyLookedForItsLeftNeighbour, 0, formsForPattern)
        
        
        properNounWithNamesSet=list(properNounWithNamesSet)
        newArray = properNounWithNamesSet
        for n in range(len(properNounWithNamesSet)):
            word = properNounWithNamesSet[n]
            if word in couplesHash:
                if isinstance(couplesHash[word], list):
                    newArray[n] = couplesHash[word][0].replace(u'\xa0', u'').strip('!"#$%&\'()*+,-\./:;<=>?@[\\]^_`{|}~ \n')
                else:
                    newArray[n] = couplesHash[word]
            
        #Remove duplicates
        keyWordsSet = set(newArray)
        
        return keyWordsSet

    
    def _recurrent_following_word_finder(self, word: str, listOfCandidates: list, winningProperNounsWithFrequencies: dict, couplesHash: dict, couplesWords, howManyWordsToLookFor: dict, originalWord: str, alreadyLookedForItsRightNeighbour: set, barier: int, beforePattern: str) -> None:
        """
        Finds the word that is a frequent follower of another word in the text, if such a word exists.
        """       
        for word2 in listOfCandidates:
            if word in alreadyLookedForItsRightNeighbour:
                return            
            if word != word2 and len(word) > 0:
                #Replace the word by the set of its forms 
                formsForPattern = self._generate_forms_for_patterns(word, self.token_dict)
                formsForPattern2 = self._generate_forms_for_patterns(word2, self.token_dict)
                
                trueOrFalse = self._word_always_followed_by_word2(couplesHash, couplesWords, winningProperNounsWithFrequencies, formsForPattern, formsForPattern2, word, word2, originalWord, barier, beforePattern)
                if trueOrFalse == True:
                    alreadyLookedForItsRightNeighbour.add(word)
                    beforePattern += "[ \-\.\_\:\&\'\*\+]+" + formsForPattern2
                    self._recurrent_following_word_finder(word2, listOfCandidates, winningProperNounsWithFrequencies, couplesHash, couplesWords, howManyWordsToLookFor, originalWord, alreadyLookedForItsRightNeighbour, barier, beforePattern)
        return
    
    def _generate_forms_for_patterns(self, word2: str, token_dict: dict) -> str:
        """
        For the given lemma finds forms registered in the token dictionary (forms of this word found in the text) and constructs a regular expression out of them.
        In this regular expression the longest form will be the first and the shortest the last: the forms will be sorted by length.
        """
        forms_for_pattern_table = []
        if len(word2) > 0:
            if word2.lower() in token_dict:
                for form2 in token_dict[word2.lower()]:
                    forms_for_pattern_table.append(form2)
            else:
                forms_for_pattern_table.append(word2)
                
        forms_for_pattern_table.sort(key = len, reverse = True)
        formsForPattern2 = "("+"|".join(forms_for_pattern_table)+")"
        return formsForPattern2
    
        
    def _recurrent_preceding_word_finder(self, word: str, listOfCandidates: list, winningProperNounsWithFrequencies: dict, couplesHash: dict, couplesWords: dict, howManyWordsToLookFor: dict, originalWord: str, alreadyLookedForItsLeftNeighbour: set, barier: int, afterPattern: str) -> None:
        """
        Finds the word that frequently precedes another word in the text, if such a word exists.
        """
        
        for word2 in listOfCandidates:
            if word in alreadyLookedForItsLeftNeighbour:
                return
            if word != word2 and len(word) > 0:
                #Replace the word by the set of its forms
                formsForPattern = self._generate_forms_for_patterns(word, self.token_dict)
                formsForPattern2 = self._generate_forms_for_patterns(word2, self.token_dict)

                trueOrFalse = self._word_always_preceded_by_word2(couplesHash, couplesWords, winningProperNounsWithFrequencies, formsForPattern, formsForPattern2, word, word2, originalWord, barier, afterPattern)
                if trueOrFalse == True:
                    alreadyLookedForItsLeftNeighbour.add(word)
                    afterPattern = formsForPattern2 + "[ \-\.\_\:\&\'\*\+]+" + afterPattern
                    self._recurrent_preceding_word_finder(word2, listOfCandidates, winningProperNounsWithFrequencies, couplesHash, couplesWords, howManyWordsToLookFor, originalWord, alreadyLookedForItsLeftNeighbour, barier, afterPattern)
        return
    
    
    def _word_always_preceded_by_word2(self, couplesHash: dict, couplesWords: dict, winningProperNounsWithFrequencies: dict, formsForPattern: str, formsForPattern2: str, word: str, word2: str, wordOrig: str, barier: int, afterPattern: str) -> bool:
        """
        Finds out if word is in most cases preceded by word2 in the text.
        """
        patternTogether = re.compile(formsForPattern2+r"[ \-\.\_\:\&\'\*\+]+"+afterPattern+r"([^a-zA-Z\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ])", re.IGNORECASE)
        
        numberEquals = 0
        numberUnequals = 0
        groupToTake = ""
        
        #If word is at least once preceded by word2
        m = re.findall(patternTogether, self.file_text)
        if len(m) > 0:
            pattern2 = re.compile(r"(?:([a-zA-Z\'\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ\.]|[\p{Pd}])+[^a-zA-ZäöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ\,\"\.]+){0,1}"+afterPattern+r"([^a-zA-Z\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ])", re.IGNORECASE)
                        
            allGroups = []
            iterator = pattern2.finditer(self.file_text)
            for match in iterator:
                allGroups.append(match.group())
            if len(allGroups) > 0:
                
                for group in allGroups:
                    if not patternTogether.match(group):
                        numberUnequals += 1
                    else:
                        groupToTake = group
                        numberEquals += 1

                if len(formsForPattern) == 3: #If it's one letter
                    numberUnequals = 0
                
                if wordOrig in winningProperNounsWithFrequencies:
                    number = winningProperNounsWithFrequencies[wordOrig]
                elif wordOrig.lower() in winningProperNounsWithFrequencies:
                    number = winningProperNounsWithFrequencies[wordOrig.lower()]
                else:
                    number = 0
                
                secondCondition = False
                if barier == 0 and numberEquals > numberUnequals:
                    secondCondition = True
                elif barier > 0 and numberEquals >= numberUnequals:
                    secondCondition = True
               
                if numberEquals > barier and secondCondition == True and numberEquals >= round(number/2):
                    if wordOrig in couplesHash:
                        if isinstance(couplesHash[wordOrig], list):
                            for n in range(len(couplesHash[wordOrig])):
                                newWord = groupToTake[:re.search(formsForPattern2+r"[ \-\.\_\:\&\'\*\+]+", groupToTake, re.IGNORECASE).end()]+couplesHash[wordOrig][n]
                                newWord = newWord.strip('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ \n')
                                couplesHash[wordOrig][n] = newWord
                                winningProperNounsWithFrequencies[newWord] = number
                                couplesWords[wordOrig].insert(0, word2)
                        else:
                            newWord = groupToTake[:re.search(formsForPattern2+r"[ \-\.\_\:\&\'\*\+]+", groupToTake, re.IGNORECASE).end()]+couplesHash[wordOrig]
                            newWord = newWord.strip('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ \n')
                            couplesHash[wordOrig] = newWord
                            winningProperNounsWithFrequencies[newWord] = number
                            couplesWords[wordOrig].insert(0, word2)
                    else:
                        newWord = groupToTake.strip('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ \n')
                        couplesHash[wordOrig] = newWord
                        winningProperNounsWithFrequencies[newWord] = number
                        couplesWords[wordOrig] = [word2, word]
        
                    return True
                
        return False


    def _word_always_preceded_by_word2_before(self, couplesHash: dict, couplesWords: dict, winningProperNounsWithFrequencies: dict, formsForPattern: str, formsForPattern2: str, word: str, word2: str, wordOrig: str, barier: int, afterPattern: str) -> bool:
        """
        Finds out if word is in most cases preceded by word2 in the text.
        """
        patternTogether = re.compile(formsForPattern2+r"[ \-\.\_\:\&\'\*\+]+"+afterPattern+r"([^a-zA-Z\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ])", re.IGNORECASE)
        
        numberEquals = 0
        numberUnequals = 0
        groupToTake = ""
        
        #If word is at least once preceded by word2
        m = re.findall(patternTogether, self.file_text)
        if len(m) > 0:
            pattern2 = re.compile(r"(?:([a-zA-Z\'\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ\.]|[\p{Pd}])+[^a-zA-ZäöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ\,\"\.]+){0,1}"+afterPattern+r"([^a-zA-Z\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ])", re.IGNORECASE)
            
            allGroups = []
            iterator = pattern2.finditer(self.file_text)
            for match in iterator:
                allGroups.append(match.group())
            if len(allGroups) > 0:
                
                for group in allGroups:
                    if not patternTogether.match(group):
                        numberUnequals += 1
                    else:
                        groupToTake = group
                        numberEquals += 1

                if len(formsForPattern) == 3: #If it's one letter
                    numberUnequals = 0
                
                if wordOrig in winningProperNounsWithFrequencies:
                    number = winningProperNounsWithFrequencies[wordOrig]
                elif wordOrig.lower() in winningProperNounsWithFrequencies:
                    number = winningProperNounsWithFrequencies[wordOrig.lower()]
                else:
                    number = 0
                
                secondCondition = False
                if barier == 0 and numberEquals > numberUnequals:
                    secondCondition = True
                elif barier > 0 and numberEquals >= numberUnequals:
                    secondCondition = True
                
                if numberEquals > barier and secondCondition == True and numberEquals >= round(number/2):
                    if wordOrig in couplesHash:
                        newWord = groupToTake[:re.search(formsForPattern2+r"[ \-\.\_\:\&\'\*\+]+", groupToTake, re.IGNORECASE).end()]+couplesHash[wordOrig]
                        newWord = newWord.strip('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ \n')
                                                
                        couplesHash[wordOrig] = newWord
                        winningProperNounsWithFrequencies[newWord] = number
                        couplesWords[wordOrig].insert(0, word2)
                    else:
                        newWord = groupToTake.strip('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ \n')
                        couplesHash[wordOrig] = newWord
                        winningProperNounsWithFrequencies[newWord] = number
                        couplesWords[wordOrig] = [word2, word]
        
                    return True
                
        return False


    def _word_always_followed_by_word2(self, couplesHash: dict, couplesWords: dict, winningProperNounsWithFrequencies, formsForPattern: str, formsForPattern2: str, word: str, word2: str, wordOrig: str, barier: float, beforePattern: str) -> bool:
        """
        Finds out if word is in most cases followed by word2 in the text.
        """        
        patternTogether = re.compile(r"([^a-zA-Z\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ])"+beforePattern+r"[ \-\.\_\:\&\'\*\+]+"+formsForPattern2+r"([^a-zA-Z\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ]|$)", re.IGNORECASE | re.MULTILINE)
                        
        numberEquals = 0
        numberUnequals = 0       
        groupsToTake = []
        
        #If word is at least once preceded by word2        
        m = re.findall(patternTogether, self.file_text)
        
        if len(m) > 0:            
            pattern2 = re.compile(r"([^a-zA-Z\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ])"+beforePattern+r"(?:[^a-zA-Z\'äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ\,\"\.]+[a-zA-Z\'\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ\.]+){0,1}([^a-zA-Z\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ]|$|\n)", re.IGNORECASE | re.MULTILINE)
                       
            allGroups = []
            iterator = pattern2.finditer(self.file_text)
            for match in iterator:
                allGroups.append(match.group())
                    
            if len(allGroups) > 0:                    
                for group in allGroups:
                    if not patternTogether.match(group):
                        numberUnequals += 1
                    else:
                        groupsToTake.append(group)
                        numberEquals += 1


                if len(formsForPattern) == 3: #If it's one letter
                    numberUnequals = 0

                if wordOrig in winningProperNounsWithFrequencies:
                    number = winningProperNounsWithFrequencies[wordOrig]
                elif wordOrig.lower() in winningProperNounsWithFrequencies:
                    number = winningProperNounsWithFrequencies[wordOrig.lower()]
                else:
                    number = 0
                    
                secondCondition = False
                
                if barier == 0 and numberEquals > numberUnequals:
                    secondCondition = True
                elif barier > 0 and numberEquals >= numberUnequals:
                    secondCondition = True
                
                
                couplesHash_wordOrig = ""
                if wordOrig in couplesHash:
                    couplesHash_wordOrig = couplesHash[wordOrig][0]

                if numberEquals > barier and secondCondition == True and numberEquals >= round(number/2):
                    groupNumber = 0
                    for groupToTake in groupsToTake:
                        groupNumber += 1
                        if wordOrig in couplesHash:
                            string_to_add = groupToTake[(re.search(beforePattern, groupToTake, re.IGNORECASE).end()):]
                            newWord = (couplesHash_wordOrig+string_to_add).strip('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ ')

                            if len(couplesHash[wordOrig])==1 and groupNumber == 1 :
                                couplesHash[wordOrig][0] = newWord
                                winningProperNounsWithFrequencies[newWord] = number
                            else:
                                newWord = groupToTake.strip('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ ')
                                couplesHash[wordOrig].append(newWord)
                                winningProperNounsWithFrequencies[newWord] = number

                            couplesWords[wordOrig].append(word2)
                        else: #if wordOrig NOT in couplesHash
                            newWord = groupToTake.strip('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ ')

                            couplesHash[wordOrig] = [newWord]
                            couplesHash_wordOrig = newWord
                            winningProperNounsWithFrequencies[newWord] = number
                            couplesWords[wordOrig] = [word, word2]
                    return True
        return False
    
    
    def _word_always_followed_by_word2_before(self, couplesHash: dict, couplesWords: dict, winningProperNounsWithFrequencies, formsForPattern: str, formsForPattern2: str, word: str, word2: str, wordOrig: str, barier: float, beforePattern: str) -> bool:
        """
        Finds out if word is in most cases followed by word2 in the text.
        """        
        patternTogether = re.compile(r"([^a-zA-Z\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ])"+beforePattern+r"[ \-\.\_\:\&\'\*\+]+"+formsForPattern2+r"([^a-zA-Z\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ]|$)", re.IGNORECASE | re.MULTILINE)
                
        numberEquals = 0
        numberUnequals = 0
        groupToTake = ""
        #If word is at least once preceded by word2
        
        m = re.findall(patternTogether, self.file_text)
        
        if len(m) > 0:            
            pattern2 = re.compile(r"([^a-zA-Z\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ])"+beforePattern+r"(?:[^a-zA-Z\'äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ\,\"\.]+[a-zA-Z\'\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ\.]+){0,1}([^a-zA-Z\-äöüÄÖÜßúùûóòôéèêÉÈÊÁÀÂÚÙÛÓÒÔ]|$|\n)", re.IGNORECASE | re.MULTILINE)
           
            allGroups = []
            iterator = pattern2.finditer(self.file_text)
            for match in iterator:
                allGroups.append(match.group())
                    
            if len(allGroups) > 0:                    
                for group in allGroups:
                    if not patternTogether.match(group):
                        numberUnequals += 1
                    else:
                        groupToTake = group
                        numberEquals += 1


                if len(formsForPattern) == 3: #If it's one letter
                    numberUnequals = 0

                if wordOrig in winningProperNounsWithFrequencies:
                    number = winningProperNounsWithFrequencies[wordOrig]
                elif wordOrig.lower() in winningProperNounsWithFrequencies:
                    number = winningProperNounsWithFrequencies[wordOrig.lower()]
                else:
                    number = 0
                    
                secondCondition = False
                
                if barier == 0 and numberEquals > numberUnequals:
                    secondCondition = True
                elif barier > 0 and numberEquals >= numberUnequals:
                    secondCondition = True
                

                if numberEquals > barier and secondCondition == True and numberEquals >= round(number/2):
                    if wordOrig in couplesHash:
                        string_to_add = groupToTake[(re.search(beforePattern, groupToTake, re.IGNORECASE).end()):]
                        newWord = (couplesHash[wordOrig]+string_to_add).strip('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ ')
                        couplesHash[wordOrig] = newWord                        
                        winningProperNounsWithFrequencies[newWord] = number
                        couplesWords[wordOrig].append(word2)
                    else:
                        newWord = groupToTake.strip('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ ')
                        couplesHash[wordOrig] = newWord
                        winningProperNounsWithFrequencies[newWord] = number
                        couplesWords[wordOrig] = [word, word2]
                
                    return True
        return False
    
    
    def _read_SMOR_result(self, smor_out_file: str) -> dict:
        """
        Reads the file containing SMOR analyses.
        Returns a hash containing lemmas as keys and a list of its analyses by SMOR as values.
        """
        smor_analysis_hash = {}
        if os.path.isfile(smor_out_file):
            smor_stream = io.open(smor_out_file, mode="r", encoding="utf-8")
            for smor_line in smor_stream:
                smor_line = smor_line.rstrip()
                if smor_line[0] == ">":
                    compound_lemma = smor_line[2:]
                    smor_analysis_hash[compound_lemma] = []
                else:
                    smor_analysis_hash[compound_lemma].append(smor_line)
            smor_stream.close()
        return smor_analysis_hash
    
    
    def _get_Nom_from_Gen(self, compound_lemma: str, smor_analysis_list: dict) -> str:
        """
        Returns the Nominative of a noun, if possible.
        If a Genetive ends with ' or 's, deletes ' or 's and returns the obtained nominative.
        Otherwise returns unchanged the lemma received as argument.
        """
        for line in smor_analysis_list:
            if re.search(r"<Nom>", line) and re.search(r"<Sg>", line):
                tableOfWordParts = re.split(r"<[^>]+>", line)
                filter(None, tableOfWordParts)
                if len(tableOfWordParts) == 1:
                    compound_lemma2 = tableOfWordParts[0]
                    return compound_lemma2

        if re.search(r"<Gen>", smor_analysis_list[0]):       
            if compound_lemma[-2:] == "'s":
                compound_lemma = compound_lemma[:-2]
            elif compound_lemma[-1] == "'":
                compound_lemma = compound_lemma[:-1]
    
        return compound_lemma
            
    
    def _fill_dictionaries_with_SMOR(self) -> dict:
        """
        Performs SMOR analyses of the lemmas obtained with TreeTagger. Fills dictionaries passed as argument.
        """        
        #Analyse with SMOR
        lemmas_file_name = os.path.join(self.output_directory,"lemmas.txt")
        smor_out_file = lemmas_file_name+".smor.txt"
        lemma_list_for_smor = io.open(lemmas_file_name, mode="w", encoding="utf-8")
        for lemma in self.noun_lemma_dict:
            lemma_list_for_smor.write(lemma+"\n")
        lemma_list_for_smor.close()
        
        try:
            subprocess.check_output([SMOR_EXECUTABLE, lemmas_file_name, smor_out_file], cwd=SMOR_FOLDER)
            #Read smor output line by line
            compoundLemma = ""
            smorAnalysisHash = self._read_SMOR_result(smor_out_file)
            
            for compoundLemma in smorAnalysisHash:
                smorLine = smorAnalysisHash[compoundLemma][0]
                if re.search("<(Gen|Dat|Acc|Pl)>", smorLine):
                    compoundLemma2 = self._get_Nom_from_Gen(compoundLemma, smorAnalysisHash[compoundLemma])
                    self.noun_lemma_dict[compoundLemma2] = self.noun_lemma_dict[compoundLemma]
                    compoundLemma = compoundLemma2

                if re.search("no result", smorLine):
                    if compoundLemma.lower() not in self.stop_words_set_de and compoundLemma[0].isupper():
                        if compoundLemma in self.tree_taggers_proper_nouns or compoundLemma.lower() in self.surnames_set or compoundLemma.lower() in self.namesHashSet:
                            if compoundLemma in self.title_noun_lemmas_dict:
                                self._add_item_to_hash_augment_count(compoundLemma, self.proper_nouns_hash, self.noun_lemma_dict[compoundLemma]+1)
                            else:
                                self._add_item_to_hash_augment_count(compoundLemma, self.proper_nouns_hash, self.noun_lemma_dict[compoundLemma])
                        else:
                            #If TreeTagger does not think it's a proper noun, add it to common nouns
                            self._add_item_to_hash_augment_count(compoundLemma, self.smor_lemmas_count_hash, self.noun_lemma_dict[compoundLemma])
                    continue

                if compoundLemma in self.from_good_words_proper_nouns:
                    if compoundLemma in self.title_noun_lemmas_dict:
                        self._add_item_to_hash_augment_count(compoundLemma, self.proper_nouns_hash, self.noun_lemma_dict[compoundLemma]+1)
                    else:
                        self._add_item_to_hash_augment_count(compoundLemma, self.proper_nouns_hash, self.noun_lemma_dict[compoundLemma])
                    continue
                
                tableOfWordParts = re.split(r"<[^>]+>", smorLine)

                for wordPart in tableOfWordParts:
                    if re.search("{", wordPart):
                        wordPart = wordPart.replace("{", "").replace("}", "").replace("-", "")
                        
                    if len(wordPart) > 0 and wordPart.lower() not in self.stop_words_set_de:
                        if wordPart.lower() in self._good_keywords_set:
                            if compoundLemma in self.title_noun_lemmas_dict:
                                self._add_item_to_hash_augment_count(compoundLemma, self.proper_nouns_hash, self.noun_lemma_dict[compoundLemma]+1)
                            else:
                                self._add_item_to_hash_augment_count(compoundLemma, self.proper_nouns_hash, self.noun_lemma_dict[compoundLemma])
                                
                        elif re.search(wordPart+r"<\+NPROP>", smorLine):
                            #Check if SMOR also suggests a common noun interpretation
                            onlyProp = True
                            if len(smorAnalysisHash[compoundLemma]) > 1:
                                for r in range(1, len(smorAnalysisHash[compoundLemma])):
                                    line = smorAnalysisHash[compoundLemma][r]
                                    if not re.search(wordPart+r"<\+NPROP>", line):
                                        onlyProp = False
                            
                            if onlyProp == False:
                                #If SMOR suggests both variants, but TreeTagger suggests a proper noun, we take it as a proper noun
                                if compoundLemma in self.tree_taggers_proper_nouns or compoundLemma.lower() in self.surnames_set:
                                    onlyProp = True
                            
                            if onlyProp == True:
                                if re.search("<CAP>"+wordPart, smorLine) or wordPart[0].isupper():
                                    if compoundLemma in self.title_noun_lemmas_dict:
                                        self._add_item_to_hash_augment_count(compoundLemma, self.proper_nouns_hash, self.noun_lemma_dict[compoundLemma]+1)
                                    else:
                                        self._add_item_to_hash_augment_count(compoundLemma, self.proper_nouns_hash, self.noun_lemma_dict[compoundLemma])
                        
                        #If it's not a suffix
                        elif not re.search(wordPart+r"(<[^>]+>)?<(SUFF|VPART)>", smorLine):
                            if re.search(r"<CAP>"+wordPart, smorLine):
                                wordPart = wordPart[0].upper()+wordPart[1:]
                                
                            self._add_item_to_hash_augment_count(wordPart, self.smor_lemmas_count_hash, self.noun_lemma_dict[compoundLemma])
                            self._fill_compound_lemma_to_parts(compoundLemma, wordPart)
                            
                            if wordPart not in self.noun_parts_and_their_compounds_hash:
                                self.noun_parts_and_their_compounds_hash[wordPart] = {}
                                self.noun_parts_and_their_compounds_hash[wordPart][compoundLemma] = self.noun_lemma_dict[compoundLemma]
                            else:
                                self._add_item_to_hash_augment_count(compoundLemma, self.noun_parts_and_their_compounds_hash[wordPart], self.noun_lemma_dict[compoundLemma])
            return smorAnalysisHash
        except subprocess.CalledProcessError as error:
            logging.error("subprocess.CalledProcessError")
            logging.error(error.output)
            return {}
       
        
    def _fill_compound_lemma_to_parts(self, compoundLemma: str, wordPart: str) -> None:
        if compoundLemma in self.compound_lemma_to_parts:
            if wordPart not in self.compound_lemma_to_parts[compoundLemma]:
                self.compound_lemma_to_parts[compoundLemma].add(wordPart)
        else:
            self.compound_lemma_to_parts[compoundLemma] = {wordPart}
        
    
    def _add_second_lang_proper_nouns(self) -> None:
        """
        Adds proper nouns from second language sentences to self.proper_nouns_hash
        """
        if len(self._second_lang_sentences)==0:
            return
        for slSent in self._second_lang_sentences:
            if self.lang == "de": #If the main language is German
                #Detect the language of the sentence
                lang = self._detect_german_in_italian(slSent[0])
                #Not analyse Italian sentences containing German words. Otherwise, German words will be seen by TreeTagger as proper nouns.
                if lang == "de":
                    continue
            self._find_second_language_proper_nouns_with_treetagger(slSent[0], self.second_lang_stop_words_set)
    
    
    def _detect_german_in_italian(self, itSent):
        """
        Detects German letters and words in a piece of text.
        If found, returns "de". Else returns "it".
        """
        if re.search(r"(ß|ä|ü|ö)", itSent, re.IGNORECASE):
            return "de"
        if re.search(r"(^|[ ,.:;\-\"\'?!])(der|die|das|den|dem|des|eine|einen|einem|eines|und|zu|von|nicht|mit|auch|auf|für|dass|es|oder|aber)([ ,.:;\-\"\'?!]|$)", itSent, re.IGNORECASE):
            return "de"
        else:
            return "it"
        
    
    def _fill_main_lang_dictionaries_with_tree_tagger(self) -> None:
        increment_by = None #The weight of the words of  the current part of the article (title, teaser or body)
                
        #Loop through all the sentences of the main language and add their content to dictionaries and sets of the class
        for li in self._main_lang_sentences:
            sentence = li[0]
            where_is_the_sentence = li[1]
            if len(sentence) == 0:
                continue        
            if where_is_the_sentence == "TITLE:":
                increment_by = 2
                if len(sentence) < 1:
                    continue
                self._fill_dictionaries_with_treetagger(sentence, increment_by, self.main_lang_stop_words_set)
            elif where_is_the_sentence == "TEASER:":
                increment_by = 1.5
                if len(sentence) < 1:
                    continue
                self._fill_dictionaries_with_treetagger(sentence, increment_by, self.main_lang_stop_words_set)
            elif where_is_the_sentence == "BODY:":
                increment_by = 1
                if len(sentence) < 1:
                    continue
                self._fill_dictionaries_with_treetagger(sentence, increment_by, self.main_lang_stop_words_set)
            else:
                self._fill_dictionaries_with_treetagger(sentence, increment_by, self.main_lang_stop_words_set)
      
        
    def _clean_sentence_before_tagging(self, sentence: str) -> str:
        remove = regex.compile(r'([\p{C}|\p{M}|\p{Ps}|\p{Pe}|\p{Pi}|\p{Pf}|\p{Pc}|\p{Po}|\p{S}]+|[\p{Pd}]+[\p{Z}]|[\p{Z}][\p{Pd}]+)', regex.UNICODE)
        sentence = remove.sub(u" ", sentence).strip()
        sentence = re.sub(r'\s+', ' ', sentence).strip()
        return sentence
    
        
    def _find_second_language_proper_nouns_with_treetagger(self, sentence: str, stopWordsSet: set) -> None:
        sentence = self._clean_sentence_before_tagging(sentence)
        tags = self.second_tagger.tag_text(sentence)  ##### !!!!!!!!!!
        is_first_word_of_sentence = True
        
        for tag in tags:
            tableForToken = tag.split("\t")
            if len(tableForToken) != 3:
                continue

            token = tableForToken[0]
            pos = tableForToken[1]
            lemma = tableForToken[2]

            if lemma == "<UNKNOWN>":
                lemma = token

            #If TreeTagger suggests more than 1 possible lemma, we take the first one
            if "|" in lemma:
                lemma = max(lemma.split("|"), key=len)

            if token[0].isupper():
                lemma = lemma[0].upper()+lemma[1:]
            
            #If the word is part of the stop list, we pass it; Filter out digits and punctuation
            if token.lower() in stopWordsSet or lemma.lower() in stopWordsSet or self.pattern_digit_punct.match(lemma):
                continue
            
            #If the word is part of the priority keywords list, we add it to the proper nouns hash
            if (token.lower() in self._good_keywords_set or lemma.lower() in self._good_keywords_set):
                if token[0].isupper():
                    lemma = lemma[0].upper()+lemma[1:]                    
                self.tree_taggers_proper_nouns.add(lemma)
                self.from_good_words_proper_nouns.add(lemma)                    
                continue
            #Find words tagged as proper nouns by TreeTagger
            elif self.proper_noun_pattern.match(pos[0:2]):
                    self.tree_taggers_proper_nouns.add(lemma)
                    
            elif (is_first_word_of_sentence == False and token[0].isupper() and self.lang == "de"): #If an Italian (here we work with the second language) word starts with a capital letter and is not the first word of the sentence, it is probably a proper noun
                    self.tree_taggers_proper_nouns.add(lemma)
                    
            elif (self.adj_pattern.match(pos[0:3]) and token[0].isupper() and is_first_word_of_sentence == False and self.lang == "it") : #If a German (here we work with the second language) adjective starts with a capital letter in German, it's very probably a proper noun  
                self.tree_taggers_proper_nouns.add(lemma)
                    
            is_first_word_of_sentence = False
        
                
    def _fill_dictionaries_with_treetagger(self, sentence: str, increment_by: float, stopWordsSet: set) -> None:
        """
        Analyses a sentence with TreeTagger, fills the dictionaries passed as argument based on TreeTagger input.
        """        
        sentence = self._clean_sentence_before_tagging(sentence)
        tags = self.main_tagger.tag_text(sentence)       
        is_first_word_of_sentence = True
        
        for tag in tags:
            already_taken_in_noun_lemma_dict = False
            already_taken_into_proper_nouns = False
            tableForToken = tag.split("\t")
            if len(tableForToken) != 3:
                continue

            token = tableForToken[0]
            pos = tableForToken[1]
            lemma = tableForToken[2]
            if lemma == "<UNKNOWN>":
                lemma = token

            #If TreeTagger suggests more than 1 possible lemma, we take the first one
            if "|" in lemma:
                lemma = max(lemma.split("|"), key=len)

            #Register the pair lemma-token
            if lemma.lower() in self.token_dict:
                self.token_dict[lemma.lower()].add(token)
            else:
                self.token_dict[lemma.lower()] = {token} #a set of tokens corresponding to this lemma

            #Register the pair token-lemma
            if token not in self.token_to_lemma_dict_original_case:
                self.token_to_lemma_dict_original_case[token] = lemma
            
            if token not in self.token_to_lemma_dict:
                self.token_to_lemma_dict_original_case[token] = lemma.lower()

            self._add_item_to_hash_augment_count(lemma, self.lemma_dict, increment_by)
            self._add_item_to_hash_augment_count(lemma, self.lemma_dict_true_number, 1)

            if token[0].isupper():
                lemma = lemma[0].upper()+lemma[1:]

            if lemma in self.lemma_token_to_POS:
                self.lemma_token_to_POS[lemma].add(pos)
            else:
                self.lemma_token_to_POS[lemma] = {pos}

            if token in self.lemma_token_to_POS:
                self.lemma_token_to_POS[token].add(pos)
            else:
                self.lemma_token_to_POS[token] = {pos}
                
            #If the word is part of the stop list, we pass it; Filter out digits and punctuation
            if token.lower() in stopWordsSet or lemma.lower() in stopWordsSet or self.pattern_digit_punct.match(lemma):
                 continue
             
            if increment_by > 1:
                if token[0].isupper():
                    lemma = lemma[0].upper()+lemma[1:]
                self._add_item_to_hash_augment_count(lemma, self.title_noun_lemmas_dict, 1)
                    
            #If the word is part of the priority keywords list, we add it to the proper nouns hash
            if (token.lower() in self._good_keywords_set or lemma.lower() in self._good_keywords_set):
                if increment_by > 1:
                    self.tree_taggers_proper_nouns.add(lemma)
                    self.from_good_words_proper_nouns.add(lemma)
                    self._add_item_to_hash_augment_count(lemma, self.noun_lemma_dict, increment_by)
                    
                if self.lang == "it":
                    self._add_item_to_hash_augment_count(lemma, self.proper_nouns_hash, increment_by)
                    
                continue
            
            if self.proper_noun_pattern.match(pos[0:2]) and token[0].isupper():                
                self.tree_taggers_proper_nouns.add(lemma)
                already_taken_into_proper_nouns = True
                
                if already_taken_in_noun_lemma_dict == False:
                    self._add_item_to_hash_augment_count(lemma[0].upper()+lemma[1:], self.noun_lemma_dict, increment_by)
                if self.lang == "it":
                    self._add_item_to_hash_augment_count(lemma, self.proper_nouns_hash, increment_by)
                
            #Filter out digits, punctuation
            if (self.noun_or_verb_pattern.match(pos[0:2]) or self.adj_pattern.match(pos[0:3])):
                #Put into a nouns hash for later compound decomposition by SMOR
                self._add_item_to_hash_augment_count(lemma, self.noun_lemma_dict, increment_by)
                already_taken_in_noun_lemma_dict = True

            if self.adj_pattern.match(pos[0:3]) and token[0].isupper() and is_first_word_of_sentence == False and self.lang == "de" : #If an adjective starts with a capital letter in German, it's very probably a proper noun
                if already_taken_in_noun_lemma_dict == False:
                    self._add_item_to_hash_augment_count(lemma[0].upper()+lemma[1:], self.noun_lemma_dict, increment_by)
                    already_taken_in_noun_lemma_dict = True
                    
            elif (is_first_word_of_sentence == False and token[0].isupper() and self.lang == "it" and already_taken_into_proper_nouns == False): #If an Italian word starts with a capital letter and is not the first word of the sentence, it is probably a proper noun
                    self.tree_taggers_proper_nouns.add(lemma)
                    self._add_item_to_hash_augment_count(lemma, self.proper_nouns_hash, increment_by)

            is_first_word_of_sentence = False
            
    
    def _add_item_to_hash_augment_count(self, lemma: str, dico: dict, value_to_add: float) -> None:
        """
        Adds an item to hash as a key and attributes it the value value_to_add.
        If the item is already in the hash, incerents its value by value_to_add.
        """
        if lemma in dico:
            dico[lemma] += value_to_add
        else:
            dico[lemma] = value_to_add

           
            
    def _find_derivationally_related_words_with_babelnet(self, setOfKeywords: set, folderForThisFile: str) -> dict:
        """
        Finds derivationally related words with help of Babelnet.
        """
        wordsDomainsHash={}
        
        myBabelnetKey = BABEL_KEY
        
        properNounsHash = {}
        
        derivativesIds = {}
        derivativesLemmas = {}
        
        jsonResponse={}
        for keyword in setOfKeywords:     
            if keyword not in properNounsHash:
                synset_id_file = os.path.join(folderForThisFile, keyword+"-getSynsetIds.txt")
                try:
                    outFile = io.open(synset_id_file, mode="r", encoding="utf-8")
                    jsonResponse=json.loads(outFile.read())
                    outFile.close()
                except:
                    synsetIds = requests.get('https://babelnet.io/v5/getSynsetIds?lemma='+keyword+'&searchLang=IT&targetLang=IT&key='+myBabelnetKey)
                    outFile = io.open(synset_id_file, mode="w", encoding="utf-8")
                    outFile.write(synsetIds.text)
                    outFile.close()
                    jsonResponse=json.loads(synsetIds.text)


                wordsDomainsHash[keyword] = set()
                derivativesIds[keyword] = set()
                derivativesLemmas[keyword] = set()

                for hashEntry in jsonResponse:
                    if "id" in hashEntry:
                        idB=hashEntry["id"]
                        rel_id_file = os.path.join(folderForThisFile, keyword+"-rel-"+idB+".txt")
                        try:
                            outFile = io.open(rel_id_file, mode="r", encoding="utf-8")
                            r2Synset = json.loads(outFile.read())
                            outFile.close()
                        except:
                            r2 = requests.get('https://babelnet.io/v5/getOutgoingEdges?id='+idB+'&searchLang=IT&targetLang=IT&key='+myBabelnetKey)
                            r2Synset=json.loads(r2.text)
                            outFile = io.open(rel_id_file, mode="w", encoding="utf-8")
                            outFile.write(r2.text)
                            outFile.close()
                            
                        for dico in r2Synset:
                            if dico['pointer']['shortName'] == 'deriv':
                                derivativesIds[keyword].add(dico['target'])
        
        for keyword in derivativesIds:
            for target in derivativesIds[keyword]:
                rel_word_file = os.path.join(folderForThisFile, keyword+"-relWord-"+target+".txt")
                try:
                    outFile = io.open(rel_word_file, mode="r", encoding="utf-8")
                    r3Synset = json.loads(outFile.read())
                    outFile.close()
                except:
                    r3 = requests.get('https://babelnet.io/v5/getSynset?id='+target+'&searchLang=IT&targetLang=IT&key='+myBabelnetKey)
                    r3Synset=json.loads(r3.text)
                    outFile3 = io.open(rel_word_file, mode="w", encoding="utf-8")
                    outFile3.write(r3.text)
                    outFile3.close()
                    
                for dic in r3Synset['senses']:
                     derivativesLemmas[keyword].add(dic['properties']['fullLemma'])
        
        
        #Find keywords that are related to others through derivation
        relatedGroupsHash = {}
        for keyword1 in derivativesLemmas:
            for keyword2 in derivativesLemmas:
                if keyword1 != keyword2:
                    if keyword2 in derivativesLemmas[keyword1]:
                        isSomewhere = False
                        if keyword1 in relatedGroupsHash:
                            relatedGroupsHash[keyword1].add(keyword2)
                            isSomewhere = True
                        if keyword2 in relatedGroupsHash:
                            relatedGroupsHash[keyword2].add(keyword1)
                            isSomewhere = True
                            
                        if isSomewhere == False:
                            relatedGroupsHash[keyword1] = {keyword2}
                            
        return relatedGroupsHash
     
    
    def _add_sentences_from_article_element(self, sentences, where_is_the_sentence: str, sentences_per_lang_hash: dict, number_sentences_per_lang_hash: dict) -> None:
        for sent in sentences:                
            for s in sent.split("\n"):
                s = s.strip()
                if len(s) > 0:
                    try:
                        lang = detect(s)
                        if lang in sentences_per_lang_hash:
                            sentences_per_lang_hash[lang].append([s,where_is_the_sentence])
                            number_sentences_per_lang_hash[lang] += 1
                        else:
                            sentences_per_lang_hash[lang] = [[s,where_is_the_sentence]]
                            number_sentences_per_lang_hash[lang] = 1
                    except:
                        print(str(sys.exc_info()[0])+" when trying to detect the language of "+s)
                        pass
                    
    def _clean_file_text(self, text):
        text = text.replace("(",",")
        text = text.replace(")",",")
        text = text.replace("*","###")
        text = text.replace("|","===")
        text = text.replace("+","#=#")
        return text
    
    def _distribute_sentences_per_language_json(self, json) -> None:
        """
        Creates 2 lists:
            one containing sentences in the main language of the text (declared in the class constructor with the lang parameter)
            the other containing sentences in the second language of the text
        """
        sentences_per_lang_hash = {}
        number_sentences_per_lang_hash = {}
        
        title = self._clean_file_text(json["Title"])
        teaser = self._clean_file_text(json["Teaser"])
        body = self._clean_file_text(json["Body"])
        
        self.file_text = title +"\n" + teaser + "\n" + body
        
        #Split sentences
        sentencesTitle = split_multi(title)
        where_is_the_sentence = "TITLE:"        
        self._add_sentences_from_article_element(sentencesTitle, where_is_the_sentence, sentences_per_lang_hash, number_sentences_per_lang_hash)
        
        sentencesTeaser = split_multi(teaser)
        where_is_the_sentence = "TEASER:"
        self._add_sentences_from_article_element(sentencesTeaser, where_is_the_sentence, sentences_per_lang_hash, number_sentences_per_lang_hash)
        
        sentencesBody = split_multi(body)
        where_is_the_sentence = "BODY:"
        self._add_sentences_from_article_element(sentencesBody, where_is_the_sentence, sentences_per_lang_hash, number_sentences_per_lang_hash)
                        
        #Sort by number of sentences, find the main language
        sorted_number_sentences_per_lang_hash = sorted(number_sentences_per_lang_hash.items(), key=itemgetter(1), reverse=True)        
        main_language = sorted_number_sentences_per_lang_hash[0][0]
        
        self.lang = main_language        
        if self.lang == "de":
            self.second_lang = "it"
        elif self.lang == "it":
            self.second_lang = "de"
        elif self.lang == "en":
            raise ValueError('The article is in English. Cannot analyse English text.')
            #return
        else:
            raise ValueError('The detected language of the texts is neither German, nor Italian, and not even English. Cannot proceed.')
        
        self._main_lang_sentences = sentences_per_lang_hash[self.lang]
        
        #We add the sentences detected as English to the main language sentences
        if 'en' in sentences_per_lang_hash:
            self._main_lang_sentences.extend(sentences_per_lang_hash['en'])
        
        if self.second_lang in sentences_per_lang_hash:
            self._second_lang_sentences = sentences_per_lang_hash[self.second_lang]
    
    def _distribute_sentences_per_language(self) -> None:
        """
        Creates 2 lists:
            one containing sentences in the main language of the text (declared in the class constructor with the lang parameter)
            the other containing sentences in the second language of the text
        """
        #Split sentences
        sentences = split_multi(self.file_text)
        
        sentences_per_lang_hash = {}
        number_sentences_per_lang_hash = {}
        
        #where_is_the_sentence = None
        where_is_the_sentence = "BODY:"
        
        for sent in sentences:
            if sent[0:6] == "TITLE:":
                sent = sent[6:]
                where_is_the_sentence = "TITLE:"
            elif sent[0:7] == "TEASER:":
                sent = sent[7:]
                where_is_the_sentence = "TEASER:"
            elif sent[0:5] == "BODY:":
                sent = sent[5:]
                where_is_the_sentence = "BODY:"
                
            for s in sent.split("\n"):
                s = s.strip()
                if len(s) > 0:
                    try:
                        lang = detect(s)
                        if lang in sentences_per_lang_hash:
                            sentences_per_lang_hash[lang].append([s,where_is_the_sentence])
                            number_sentences_per_lang_hash[lang] += 1
                        else:
                            sentences_per_lang_hash[lang] = [[s,where_is_the_sentence]]
                            number_sentences_per_lang_hash[lang] = 1
                    except:
                        print(str(sys.exc_info()[0])+" when trying to detect the language of "+s)
                        pass
                        
        #Sort by number of sentences, find the main language
        sorted_number_sentences_per_lang_hash = sorted(number_sentences_per_lang_hash.items(), key=itemgetter(1), reverse=True)        
        main_language = sorted_number_sentences_per_lang_hash[0][0]
        
        self.lang = main_language        
        if self.lang == "de":
            self.second_lang = "it"
        elif self.lang == "it":
            self.second_lang = "de"
        elif self.lang == "en":
            raise ValueError('The article is in English. Cannot analyse English text.')
        else:
            raise ValueError('The detected language of the texts is neither German, nor Italian, and not even English. Cannot proceed.')
        
        self._main_lang_sentences = sentences_per_lang_hash[self.lang]
        
        #We add the sentences detected as English to the main language sentences
        if 'en' in sentences_per_lang_hash:
            self._main_lang_sentences.extend(sentences_per_lang_hash['en'])
        
        if self.second_lang in sentences_per_lang_hash:
            self._second_lang_sentences = sentences_per_lang_hash[self.second_lang]
            
        
    def _read_file(self, file_name: str) -> str:
        """
        Reads a text file and returns its text content.
        
        Parameters:
            
        :param str file_name: The name of the plain text file to read
        """
        try:
            file_object = io.open(file_name, mode="r", encoding="utf-8")
            file_text = file_object.read()
            file_object.close()
            file_text = self._strip_email_url(file_text)
            return file_text
        except Exception as e:
            logging.error(e)
            
    def _read_stop_words_from_file(self, stop_list_file: str) -> set:
        """
        Reads stop words from a text file, one stop word per line.
        Puts the stopwords into a set and returns it.
        
        Parameters:
            
        :param str stop_list_file: The name of the plain text file containing one stop word per line
        """
        inputstr = io.open(stop_list_file, mode="r", encoding="utf-8")
        stop_words_text = inputstr.read()
        inputstr.close()
        return set(line.strip().lower() for line in stop_words_text.split("\n"))
    
    def _read_names_from_file(self, fileName: str, hashSet: set) -> None:
        """
        Reads words from a text file, one word per line.
        If a line containing a word ends with a number between parenthesis, deletes the number between parenthesis from this line and takes only the words.
        Puts the stopwords into the given set.
        """
        pattern = re.compile(r"(.+)\s{2}\(\d\)")
        read_file = io.open(fileName, mode="r", encoding="utf-8")
        
        for line in read_file:
            nameText = line.rstrip().lower()
            name = re.search(pattern, nameText)
            if name is None:
                hashSet.add(nameText)
            else:
                hashSet.add(nameText[:-5])
                
        read_file.close()
        
    
    def _strip_email_url(self, file_text: str) -> str:
        """
        Deletes emails and URLs from a text.
        Returns the text without emails and URLs.
        
        Parameters:
    
        :param str file_text: The text to strip URLs and emails from.
        
        >>> KeywordExtractor("de", "test", "21717.txt")._strip_email_url("ecco la mia email io-ho_33Anni@poste.paese e il mio sito:http://www.sito.kria")
        'ecco la mia email  e il mio sito:'
        """
        file_text = re.sub(r"[\da-zA-Z\.\-\_]+@[\da-zA-Z\.\-\_]+", "", file_text) #Filter email address
        file_text = re.sub(r"(https?:\/\/)?www\.[^ ]+", "", file_text) #Filter URL
        return file_text

    def _make_output_directory(self, folder: str) -> None:
        """
        Create a directory.
        """
        try:
            if not os.path.exists(folder):
                os.makedirs(folder)
            else:
               logging.warning("\nFolder "+folder+" already exists.\n") 
        except Exception as e:
            logging.warning("\nCould not create folder "+folder+" due to the following error:\n")
            logging.warning(e)
            
    def _find_pieces_between_quotes(self) -> set:
        """
        Finds all quoted text of the maximum length of 30 characters.
        If there are too many quoted strings (more than 3), in case of German takes nothing and in case of Italian chooses the strings that contain at least 1 capital letter.
        Returns a set of found strings.
        """
        between_quotes = re.findall("[\"“\«]([^ \,\-\.\?\!\:\;\"”\»][^\,\-\.\?\!\:\;\"”\»][^\"”\»]{,30}[^ \,\-\.\?\!\:\;\"”\»][^\,\-\.\?\!\:\;\"”\»]?)[\"”\»]",self.file_text, re.MULTILINE)

        strings_to_take = set()
        
        if len(between_quotes)>3:
            if self.lang == "it":            
                for bq in between_quotes:
                    if re.search(r"[A-ZÄÖÜßÉÈÊÁÀÂÚÙÛÓÒÔ]", bq):
                        strings_to_take.add(bq)
        else: #If there are less than 4 quoted strings, we take them all
            strings_to_take = set(between_quotes)
        
        return strings_to_take
    
    def _make_output_directory(self, folder: str) -> None:
        """
        Create a directory.
        """
        try:
            if not os.path.exists(folder):
                os.makedirs(folder)
            else:
                logging.warning("\nFolder "+folder+" already exists.\n")
        except Exception as e:
            logging.warning("\nCould not create folder "+folder+" due to the following error:\n")
            logging.warning(e) 


def make_output_directory(folder: str) -> None:
    """
    Create a directory.
    """
    try:
        if not os.path.exists(folder):
            os.makedirs(folder)
        else:
            logging.warning("\nFolder "+folder+" already exists.\n")
    except Exception as e:
        logging.warning("\nCould not create folder "+folder+" due to the following error:\n")
        logging.warning(e)          

          
def main():
    parser = argparse.ArgumentParser(description='''This script extracts keywords from a file containing text.''')
    parser.add_argument('-i', metavar='file_to_find_keywords_in', help='name of the file containing the text to extract keywords from', required=True)
    parser.add_argument('-o', metavar='output_directory', help='name of the folder that will contain the file with keywords', required=True)
    
    args = vars(parser.parse_args())
    
    script_folder, script_name = os.path.split(os.path.abspath(__file__))
    input_file_folder, input_file_name = os.path.split(os.path.abspath(args['i']))
    output_folder_name = os.path.abspath(args['o'])
    
    #Make the output directory
    make_output_directory(output_folder_name)
    
    logFile = os.path.join(output_folder_name, script_name+".log")
    logging.basicConfig(filename=logFile, level=logging.WARNING)
    
    # A json for test 
    json={'Title': 'DFB Trainingslager: Um Aufklärung bemüht',

        'Teaser': 'Wer ist Schuld am Unfall der beiden Rennfahrer Pascal Wehrlein und Nico Rosberg. Waren sie zu schnell unterwegs? Wurde die Strecke nicht gut genug gesichert? Oder tragen die Schaulustigen, die am Ende als verletzte Opfer im Krankenhaus landeten, auch eine Verantwortung?',

        'Body': 'Antworten auf diese Fragen gab es aus dem Passeiertal bereits einige. Noch am Abend des Unfalls, bei dem die beiden Rennfahrer Nico Rosberg und Pascal Wehrlein zwei Personen mit ihren Mercedes-Sportwagen erfassten und verletzten, gab der Passeierer Hotelier und Gemeinderat Heinrich Dorfer eine erste Stellungnahme ab. Es sei alles reglulär und nach bestem Wissen und Gewissen zugegangen, die beiden Piloten seien nicht schnell gefahren, es habe sich "um einen blöden Zufall" gehandelt, sagte Dorfer in der RAI Tagesschau vom 27. Mai. Auf einer heute Mittag einberufenen Pressekonferenz äußerte sich der Trainer des DFB-Teams, Oliver Bierhoff. Er war zusammen mit den beiden Fahrern Rosberg und Wehrlein bereits bei den Verletzten im Krankenhaus gewesen und "dass der DFB eng mit allen Behörden zusammenarbeiten werden, um so rasch wie möglich Aufklärung in den Fall zu bringen." Auch sprach Bierhoff davon, dass diese Art von Werbung grundsätzlich zu überdenken sei. Auch Bürgermeisterin Rosmarie Pamer möchte nun wieder etwas Ruhe einkehren lassen, nachdem feststeht, dass der 63jährige verletzte Deutsche aus Thüringen außer Lebensgefahr ist. Das Trainingslager der deutschen Nationalelf solle sich unter glücklicheren Umständen fortsetzen. Trotzdem, der schwere Unfall wird in der deutschen Tagespresse gehörig kommentiert. Die Süddeutsche Zeitung titelt etwa "Drama beim Werbe-Dreh des DFB-Teams" und lässt auch die Passeirer Bürgermeisterin in einem Video-Interview zu Wort kommen, in dem sie von einem "schweren Schock" spricht. Noch größer bringt die deutsche Bild-Zeitung die Story. "Ich hätte tot sein können" zitiert der Reporter den zweiten Verletzten, den Streckenposten Michael Klotz aus Walten. Er liegt mit dem Verdacht auf ein Schädelhirntrauma im Bozner Krankenhaus und wurde von lokalen und deutschen Reportern bereits interviewt. Den Unfallhergang beschreibt er ganz genau. Der deutsche Tourist habe nicht auf der Straße, sonden abseits davon gestanden und wollte ein Foto machen. "Trotzdem habe ich geschrien und bin zu ihm hingelaufen, wollte ihn wegziehen, da war es schon zu spät." Da hatte Nico Rosberg bereits gebremst, offensichtlich durch den Tumult irritiert, und das Auto des hinter ihm fahrenden Pascal Wehrlein hatte die beiden Männer im nächsten Moment zu Boden gerissen. Die Carabinieri haben nun die Ermittlungen aufgenommen und bereits Augenzeugen befragt, auch den verletzten Streckenposten, der noch sagte: "Vielleicht hätten sie da nicht ganz so schnell sein müssen, nicht ganz so viel Theater machen sollen. Aber ich weiß es nicht."'
        }
    
    try:
        #Initialise the module
        #key_word_extractor = KeywordExtractor( input_file_folder, input_file_name, output_folder_name) # initialises the module to read an article from a file
        key_word_extractor = KeywordExtractor( "json", json, output_folder_name) # initialises the module to read an article from a json
        
        #Extract the keywords
        key_words_set = key_word_extractor.extract_keywords() # key_words_set contains the set of keywords extracted from the article
        
        #Print the keywords to a file
        keywordsFileName = os.path.join(output_folder_name, input_file_name+".KEY")
        keywordsFile = io.open(keywordsFileName, mode="w", encoding="utf-8")
        
        for keyword in key_words_set:
            keywordsFile.write(keyword+"\n")
            
        keywordsFile.close()
    
    except ValueError as err:
        logging.error(err)
    
        
    
        
if __name__ == "__main__":    
    main()