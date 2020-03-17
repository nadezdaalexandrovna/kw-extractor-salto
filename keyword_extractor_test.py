#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
@author: Nadezda Okinina

Unit tests for testing keyword_extractor_salto.py
"""

import os
import shutil
import unittest
from keyword_extractor_salto import KeywordExtractor


class KeywordExtractorTest(unittest.TestCase):
    
    def setUp(self):
        self.script_folder, self.script_name = os.path.split(os.path.abspath(__file__))
        self.output_folder = os.path.join(self.script_folder, "test-out")
        self.make_output_directory(self.output_folder)
        
    def tearDown(self):
        shutil.rmtree(self.output_folder)
        
    def make_output_directory(self, folder: str) -> None:
        """
        Create a directory.
        """
        try:
            if not os.path.exists(folder):
                os.makedirs(folder)
        except Exception as e:
            raise Exception('Could not create folder {} due to the following exception: '.format(folder) + repr(e))
        
    
    def test_strip_email_url(self):
        """
        Tests the class method of the KeywordExtractor _strip_email_url.
        Passes a sentence to this method and checks if it has deleted the email and the URL it contained.
        """
        self.assertEqual(KeywordExtractor(os.path.join(self.script_folder, "test"), "21717-de.txt", self.output_folder)._strip_email_url("ecco la mia email io-ho_33Anni@poste.paese e il mio sito:http://www.sito.kria"), 'ecco la mia email  e il mio sito:')
     
    
    def test_de_proper_nouns_fill_main_lang_dictionaries_with_tree_tagger(self):
        """
        Tests the class method of the KeywordExtractor _fill_main_lang_dictionaries_with_tree_tagger.
        Reads a file from the test folder and checks if proper nouns have been correctly detected by the method.
        """
        kw_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "small-mixed.txt", self.output_folder)
        kw_extractor._fill_main_lang_dictionaries_with_tree_tagger()
        self.assertEqual(kw_extractor.tree_taggers_proper_nouns, {'Nico', 'Pascal', 'DFB', 'Rosberg'})
    
    def test_de_add_second_lang_proper_nouns(self):
        """
        Tests the class method of the KeywordExtractor _add_second_lang_proper_nouns.
        Reads a file from the test folder with the majority of German text
        and checks if proper nouns and words from the Title and the Teaser have been correctly detected by the method.
        """
        kw_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "small-mixed.txt", self.output_folder)
        kw_extractor._fill_main_lang_dictionaries_with_tree_tagger()
        kw_extractor._add_second_lang_proper_nouns()
        self.assertEqual(kw_extractor.tree_taggers_proper_nouns, {'DFB', 'Bernardo', 'Magnagi', 'Pascal', 'Nico', 'Rosberg'})
    
    def test_de_fill_dictionaries_with_treetagger(self):
        """
        Tests the class method of the KeywordExtractor _fill_dictionaries_with_treetagger.
        Passes a German sentence to this method and checks the content of dictionaries and sets filled by it.
        """
        kw_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "small-mixed.txt", self.output_folder)
        kw_extractor._fill_dictionaries_with_treetagger('Antworten auf diese Fragen gab es aus dem Passeiertal bereits einige.', 1.0, ('auf', 'dem', 'es', 'aus'))

        self.assertEqual(kw_extractor.noun_lemma_dict, {'Antwort': 1.0, 'Frage': 1.0, 'Passeiertal': 1.0, 'geben': 1.0})
        self.assertEqual(kw_extractor.token_to_lemma_dict_original_case, {'Fragen': 'frage', 'bereits': 'bereits', 'es': 'es', 'aus': 'aus', 'gab': 'geben', 'auf': 'auf', 'Passeiertal': 'passeiertal', 'Antworten': 'antwort', 'diese': 'dies', 'einige': 'einige', 'dem': 'die'})
        self.assertEqual(kw_extractor.lemma_token_to_POS, {'Frage': {'NN'}, 'die': {'ART'}, 'bereits': {'ADV'}, 'einige': {'PIS'}, 'Antworten': {'NN'}, 'auf': {'APPR'}, 'diese': {'PDAT'}, 'dem': {'ART'}, 'Fragen': {'NN'}, 'geben': {'VVFIN'}, 'Antwort': {'NN'}, 'aus': {'APPR'}, 'gab': {'VVFIN'}, 'Passeiertal': {'NN'}, 'dies': {'PDAT'}, 'es': {'PPER'}})
        self.assertEqual(kw_extractor.title_noun_lemmas_dict, {})
        self.assertEqual(kw_extractor.tree_taggers_proper_nouns, set())
        
    def test_it_fill_dictionaries_with_treetagger(self):
        """
        Tests the class method of the KeywordExtractor _fill_dictionaries_with_treetagger.
        Passes an Italian sentence to this method and checks the content of dictionaries and sets filled by it.
        """
        kw_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "small-mixed2.txt", self.output_folder)
        kw_extractor._fill_dictionaries_with_treetagger('Ieri il primario di Casa Basaglia Lorenzo Toresini è andato in pensione.', 1.0, ('il', 'di', 'essere', 'casa', 'in'))
        
        self.assertEqual(kw_extractor.noun_lemma_dict, {'primario': 1.0, 'Basaglia': 1.0, 'Lorenzo': 1.0, 'Toresini': 1.0, 'pensione': 1.0, 'andare': 1.0})
        self.assertEqual(kw_extractor.token_to_lemma_dict_original_case, {'Basaglia': 'basaglia', 'Casa': 'casa', 'Ieri': 'ieri', 'Lorenzo': 'lorenzo',  'Toresini': 'toresini',  'andato': 'andare',  'di': 'di',  'il': 'il',  'in': 'in',  'pensione': 'pensione',  'primario': 'primario',  'è': 'essere'})
        self.assertEqual(kw_extractor.lemma_token_to_POS, {'Basaglia': {'NOM'},  'Casa': {'NPR'},  'Ieri': {'ADV'},  'Lorenzo': {'NPR'},  'Toresini': {'NOM'},  'andare': {'VER:pper'},  'andato': {'VER:pper'},  'di': {'PRE'},  'essere': {'VER:pres'},  'il': {'DET:def'},  'in': {'PRE'},  'pensione': {'NOM'},  'primario': {'NOM'},  'è': {'VER:pres'}})
        self.assertEqual(kw_extractor.title_noun_lemmas_dict,{})
        self.assertEqual(kw_extractor.tree_taggers_proper_nouns, {'Basaglia', 'Lorenzo', 'Toresini'})
        
    
    def test_it_find_second_language_proper_nouns_with_treetagger(self):
        """
        Tests the class method of the KeywordExtractor _find_second_language_proper_nouns_with_treetagger.
        Passes an Italian sentence to this method and finds proper nouns in it.
        """
        kw_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "small-mixed.txt", self.output_folder)
        kw_extractor._find_second_language_proper_nouns_with_treetagger('Bernardo Magnagi viene spesso.', set(['un', 'il']))
        self.assertEqual(kw_extractor.tree_taggers_proper_nouns, {'Bernardo', 'Magnagi'})
        
    
    def test_de_find_second_language_proper_nouns_with_treetagger(self):
        """
        Tests the class method of the KeywordExtractor _find_second_language_proper_nouns_with_treetagger.
        Passes a German sentence to this method and finds proper nouns in it.
        """
        kw_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "small-mixed.txt", self.output_folder)
        kw_extractor._find_second_language_proper_nouns_with_treetagger('Wer ist Schuld am Unfall der beiden Rennfahrer Pascal Wehrlein und Nico Rosberg.', set(['ist', 'am', 'der', 'und']))
        self.assertEqual(kw_extractor.tree_taggers_proper_nouns, {'Pascal', 'Nico', 'Rosberg','Unfall','Rennfahrer','Schuld','Wehrlein'})
     
        
    def test_detect_german_in_italian(self):
        kw_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "small-mixed.txt", self.output_folder)
        self.assertEqual(kw_extractor._detect_german_in_italian('Bernardo Magnagi dice spesso: Gesundheit und Danke.'), "de")
        self.assertEqual(kw_extractor._detect_german_in_italian('Heinrich Hund dice spesso: mio dio!'), "it")
   
    def test_it_delete_POSes_from_beginning_with_TreeTagger(self):
        kw_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "small-mixed2.txt", self.output_folder)        
        kw_extractor._fill_main_lang_dictionaries_with_tree_tagger()
        kw_extractor.proper_noun_with_names_set = {'di Casa Basaglia'}
        kw_extractor.proper_noun_with_names_set = kw_extractor._delete_POSes_from_beginning_with_TreeTagger(kw_extractor.proper_noun_with_names_set, kw_extractor.tagger_it)
        self.assertEqual(kw_extractor.proper_noun_with_names_set, {'Casa Basaglia'})
       
    def test_it_delete_POSes_from_end_with_TreeTagger(self):
        kw_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "small-mixed2.txt", self.output_folder)        
        kw_extractor._fill_main_lang_dictionaries_with_tree_tagger()
        kw_extractor.proper_noun_with_names_set = {'don Chisciotte di'}
        kw_extractor.proper_noun_with_names_set = kw_extractor._delete_POSes_from_end_with_TreeTagger(kw_extractor.proper_noun_with_names_set, kw_extractor.tagger_it)
        self.assertEqual(kw_extractor.proper_noun_with_names_set, {'don Chisciotte'})
    
    def test_it_extract_keywords(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "1008-it.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        
        self.assertTrue('pensione' in key_words_set)
        self.assertTrue('struttura' in key_words_set)
        self.assertTrue('don Chisciotte' in key_words_set)
        self.assertTrue('Franco Basaglia' in key_words_set)
        self.assertTrue('Lorenzo Toresini' in key_words_set)
        
        
    
    def test_it_extract_keywords_2(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "1014-it.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertIn( 'situazione',key_words_set)
        self.assertIn( 'consumatori',key_words_set)
        self.assertIn( 'certa regolamentazione',key_words_set)
        self.assertIn( 'Paolo Pavan',key_words_set)
        self.assertIn( 'Confesercenti',key_words_set)
        self.assertIn( 'sistema dei negozi',key_words_set)
        self.assertIn( 'provincia di Bolzano',key_words_set)
        self.assertIn( 'apertura dei negozi',key_words_set)
        
    
    def test_it_extract_keywords_4(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "1028.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'dialogo', 'Richard Theiner', 'Svp', 'autonomia integrale', 'sorriso degli italiani'})
        
    def test_it_extract_keywords_5(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10006.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'portale', 'VB33', "l'editore SDF Rosengarten Broadcast Media AG", 'SDF - Südtirol Digital Fernsehen', 'GOINFO', 'Davide Bucci', 'lingua italiana','fa informazione','nuovo, indipendente e migliore','Alto Adige'})

    def test_it_extract_keywords_8(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10046.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Alessandro Vicentini', 'Bolzano', 'È una questione strutturale','La crisi morde', 'auto'})
      
    def test_it_extract_keywords_9(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10053.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'dossier', 'Bolzano', 'sito', 'Venezia e Nordest', 'capitale europea della cultura', 'candidatura','caldo involucro','raccomandazione'})
      
    def test_it_extract_keywords_10(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10152.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'incidente', 'contadino', 'investito da un trattore','Kuppelwies'})
     
    def test_it_extract_keywords_11(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10157.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'politico', 'Andreas Perugini', 'MoVimento 5 Stelle', 'presentato','programma', 'estromissione'})

    def test_it_extract_keywords_13(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10187.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Cisl Alto Adige', 'imposta sul valore aggiunto', "aumento dell'Iva", 'euro', 'Freiheitlichen'})

    def test_it_extract_keywords_15(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10212.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Bolzano','quartiere','partecipante','bolzanobici around the world','dedicata alle due ruote','popolare','iniziativa'})
    
    def test_it_extract_keywords_16(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10225.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'pulizia linguistica','Florian Kronbichler','quota Svp','polemica','risolve','teoria','soluzione','rifugi di montagna','ribadisce'})
    
    def test_it_extract_keywords_17(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10227.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Caritas', 'mendicanti','centro Moca','comunale','Merano','polizia','Comune','Provi più tardi','La segreteria ormai è chiusa','Divieto di accattonaggio','La richiamiamo'})

    def test_it_extract_keywords_19(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10267.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'strutture private','rifugi di montagna','Svp','Scelta Civica','Martha Stocker','mondo politico italiano','lingua italiana','Andrea Casolari','Partito democratico','polemiche','Pd','Luis Durnwalder','buon senso','colleghi'})
    
    def test_it_extract_keywords_20(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10275.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Karl Zeller','Svp','Eva Klotz',"accordo",'rifugio','tedesco','provocazione','funzionario','mozione','difenda'})
    
    def test_it_extract_keywords_21(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10286.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Arno Kompatscher','tre domande','entrature particolari','il prossimo Landeshauptmann','democrazia diretta','firma','legge provinciale', 'Svp'})
    
    def test_it_extract_keywords_22(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10288.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Bizzo','tedesco','italiano','quotidiano','Innovation Festival','Alto Adige'})
    
    def test_it_extract_keywords_23(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10290.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'zona', 'acque','Luis Durnwalder','Bolzano Sud','SEL e Azienda Elettrica','capitale dei rifiuti','Ai Piani 5 anni di cattivi odori','unter einem Dach','Das Kreuz mit den Maturabällen','Altri rifiuti verso Bolzano'})
    
    def test_it_extract_keywords_24(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10293.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Giunta comunale','Bolzano','Mercatino di Natale','turismo','Alto Adige','gennaio','ambientalista'})
    
    def test_it_extract_keywords_25(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10297.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'colposo','Federico Aldrovandi'})

    def test_it_extract_keywords_28(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "10328.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'studio Besier', 'comitato proALTvor', 'Tiziana Campagnoli', 'Bressanone', 'Provincia', 'Comune', 'Stephan Besier', 'tecnici', 'incontro','interrompe','ancora valido','sindaco'})

    def test_de_extract_keywords_30(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "21870.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Greta Marcolongo','Live-Musik','Andrea Maffei','Fußball-Übertragungen'})

    def test_de_extract_keywords_31_2(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "21891.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Vermisstenfall','Identifizierung','Etsch','Zahnarztbefunde','Fluss','Verwesungsprozess','Frauenleiche','Serafino Baldessari','Davide Baldessari','Verona'})
    
    def test_de_extract_keywords_32(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "21905.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Sexarbeiterin', 'Day', 'Fotostrecke', 'Problem', 'Xenia', 'internationale Hurentag'})
    
    def test_de_extract_keywords_35(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "21921.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Karl Zeller','SVP-Senator','Abänderungsantrag','RAI-Sitze der sprachlichen Minderheiten'})


    def test_de_extract_keywords_40(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "21965.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Freiheitlichen','Stocker','Landtagswahlen','Wählerstimme','Pius','Ulli','SVP'})
    
    def test_de_extract_keywords_41(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "21969.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Bewerbungsdossiers','Giorgio Orsoni','Kulturhauptstadtregion','Christian Tommasini','Alberto Stenico','Luis Durnwalder','Venedig','Nordest'})

    def test_de_extract_keywords_43(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "21984.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Andreas Pöder','Regionalratsabgeordnete','Movimento 5 Stelle','Paul Köllensperger'})
    
    def test_de_extract_keywords_44(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "21986.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'René Benkos','Busbahnhofsareals','Willi Hüsler','Erlebnishaus Südtirol','Kaufhausprojekt','Boris Podrecca'})

    def test_de_extract_keywords_47(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "22003.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Freiheitlichen','SVP und PD','Volksabstimmung','Seilbahnprojekt','Brixen'})   
        
    def test_de_extract_keywords_48(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "22008.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Politikerrenten','Landeshauptmann Arno Kompatscher','Freiheitlichen','Südtiroler Frühling'})
   
    def test_de_extract_keywords_50(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "22024.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertIn('rechtextreme Bewegung',key_words_set)
        self.assertIn('rechtsradikale Bewegung',key_words_set)
        self.assertIn('DIGOS-Ermittlungen',key_words_set)
        self.assertIn('Luigi Spagnoli',key_words_set)
        self.assertIn('legge Scelba',key_words_set)
        self.assertIn('Socialismo Nazionale',key_words_set)
        
    
    def test_de_extract_keywords_52(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "22051.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Mädchen','Heterobaby','zwanzigminütigen Kurzfilm','Welt','homosexuellen Menschen','Jungs'})
    
    def test_de_extract_keywords_53(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "22056.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'Frau','schwer','Kuh','Franz','Jungbäuerin','Mölten','Sattlerhüttenwirt'})

    def test_de_extract_keywords_55(self):
        key_word_extractor = KeywordExtractor(os.path.join(self.script_folder,"test"), "21717-de.txt", self.output_folder)
        key_words_set = key_word_extractor.extract_keywords()
        self.assertEqual(key_words_set, {'DFB-Teams','Süddeutsche Zeitung','Trainingslager','Rennfahrer','Pascal Wehrlein','verletzt','Oliver Bierhoff','Heinrich Dorfer','Nico Rosberg', 'Ich hätte tot sein können', 'um einen blöden Zufall', 'schweren Schock'})
 
    
if __name__ == "__main__": 
    unittest.main()