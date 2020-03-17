The module KeywordExtractor in the file keyword_extractor_salto.py extracts keywords from short newspaper articles in German and Italian (salto.bz articles).

Usually extracts between 2 and 10 keywords.

If an article contains phrases in another language (for example, a German article contains Italian phrases), only takes into account proper nouns in the second language (Italian for German texts, German for Italian texts), leaving behind all the other words.

Keyword extraction is based on the frequency of words in the text. For German, it is based on the frequency of their parts: morphological analysis is performed by SMOR. Lemmatisation for both languages is performed with TreeTagger. For Italian no morphological analysis is performed. For German texts, the script counts word parts (parts of compounds) and finds the most frequent ones, privileging the longest candidates. For Italian it counts whole words. Then for both languages it finds words that often co-occur with the candidate keywords.

A word that is not present in the text cannot become its keyword.

Keywords may belong to any part of speech, but are usually nouns.

Proper nouns are given special attention and a few proper nouns are usually present in the list of keywords.

One keyword may contain several words (ex: dreisprachige RAI).


The module needs the following files to be present in the same folder:

    stoplist-de-bigger.txt

    stoplist-it.txt

    names-all2.txt

    titles.txt

    common-de-surnames.txt

    styr_nachnamen.txt

    good-keywords.txt
        
It also needs the directory containing the SMOR tool to be present in the same folder.

TreeTagger for German and Italian must be installed, because it is used by the Python module treetaggerwrapper.


The script takes 3 arguments:

    -i  the name of the file containing the newspaper text

    -o  the name of the output folder

    -l  the main language of the file ("it" or "de")

The extracted keywords are written to a text file of the same name as the input file, with the extension '.KEY' added at the end, 1 keyword \t its translation per line.


NB: The newspaper text must contain a title, a teaser and a body, like in the following example:


TITLE: Bozen: Ist Fußball wichtiger als Musik?

TEASER: Empörung in Südtirols Musikszene über die Ausnahmeregelung der Gemeinde Bozen für die Fußball-WM: Für deren Übertragung dürfen die Lokale bis in die frühen Morgenstunden offen halten, bei Konzerten ist dagegen um 23 Uhr Schluss. 

BODY: 
  
    „Alles Fußball“ heißt es von 12. Juni bis 13. Juli, wenn in Brasilien die besten Nationalteams um den Weltmeistertitel kämpfen.
    ...

The newspaper text may be passed to the script as a text or as a json object containing 3 fields: "Title", "Teaser" and "Body".

Depending on the input format, the KeywordExtractor module has to be initialised differently.

## There are 3 ways to initialise the KeywordExtractor module:

1 If you want the script to extract keywords from a Salto article saved in a file, initialise the KeywordExtractor module like this:

key_word_extractor_de = KeywordExtractor( input_file_folder, input_file_name, outputDirectory)

2 If you want to extract keywords from a Salto article text, initialise the KeywordExtractor module like this:

key_word_extractor_de = KeywordExtractor( article_text, outputDirectory)

The article_text must contain a string with a TITLE, TEASER and BODY, as in the example above.

3 If you want to extract keywords from a Salto article presented as a json, initialise the KeywordExtractor module like this:

key_word_extractor_de = KeywordExtractor( "json", json, outputDirectory)

The json must contain 3 fields: "Title", "Teaser" and "Body".


Words from the title and the teaser are considered more important than words from the body when the scores of words are counted for choosing the most frequent ones.

## In order to extract keywords from a text, call the extract_keywords() function

## In order to translate keywords extracted from a text, call the translate_keywords(key_words_set, lang_from, lang_to) function.
The function takes 3 arguments: the set of keywords, the language of the text (lang_from) and the language to which you want to translate the keywords (lang_to).

In order to use the translation function translate_keywords, you need to set the environment variable AZURE where you need to put the subscription key to the Microsoft Azure translation API.
