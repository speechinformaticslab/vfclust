"""
The VFClust package is designed to generate clustering analyses for transcriptions of semantic and phonemic verbal fluency test responses. In a verbal fluency test, the subject is given a set amount of time (usually 60 seconds) to name as many words as he or she can that correspond to a given specification. For a phonemic test, subjects are asked to name words that begin with a specific letter. For a semantic fluency test, subjects are asked to provide words of a certain category, e.g. animals.  VFClust groups words in responses based on phonemic or semantic similarity, as described below. It then calculates metrics derived from the discovered groups and returns them as a CSV file or Python dict.
"""
from __future__ import division  # makes / do floating point division
import os, re, subprocess, csv, argparse, sys
import cPickle as pickle  # faster for the LSA part
from collections import defaultdict
from tempfile import NamedTemporaryFile
from math import sqrt
from TextGridParser import TextGrid

from nltk.stem.wordnet import WordNetLemmatizer
from nltk import PorterStemmer
lemmatizer = WordNetLemmatizer()
stemmer = PorterStemmer()

data_path = os.path.join(os.path.dirname(__file__), 'data/')
__docformat__ = "restructuredtext en"

def print_table(table):
    """Helper function for printing tables to screen.

    :param table: List of tuples where each tuple contains the contents of a row,
                and each entry in the tuple is the contents of a cell in that row.
    :type table: List of tuples.
    """
    col_width = [max(len(str(x)) for x in col) for col in zip(*table)]
    for line in table:
        print "| " + " | ".join("{:{}}".format(str(x), col_width[i])
                                for i, x in enumerate(line)) + " |"

def get_mean(list_in_question):
    """Computes the mean of a list of numbers.

    :param list list_in_question: list of numbers

    :returns: mean of the list of numbers
    :rtype : float
    """
    return sum(list_in_question) / float(len(list_in_question))


class VFClustException(Exception):
    """Custom exception class -- better than using asserts."""
    pass


class Args():
    """Dummy class to hold argument properties."""
    pass


# holds sequence of adjacent words with the same stem
class Unit():
    """ Class to hold a sequence of 1 or more adjacent words with the same stem, or a compound word.

    A Unit may represent:
        - single words (dog, cat)
        - lemmatized/compound words (polar_bear)
        - several adjacent words with the same root (follow/followed/following)
     The object also includes:
        - phonetic/semantic representation of the FIRST word, if more than one
        - The start time of the first word and the ending time of the final word
    """
    def __init__(self, word, format, type, index_in_timed_response = None):
        """Initialization of Unit object.

        :param word:        Original word that the Unit represents.
        :type word:         If format is "TextGrid", this must be a TextGrid.Word object.
                            If format is "csv", this must be a string.
        :param str format:  'TextGrid' or 'csv'
        :param str type:    'SEMANTIC' or 'PHONETIC
        :param int index_in_timed_response: Index in the raw response input.
                Used to find phone-level information later if necessary.
        :rtype : Unit object
        """
        self.type = type
        self.format = format
        self.phonetic_representation = None
        self.index_in_timed_response = index_in_timed_response

        if self.format == "TextGrid":
            self.text = word.string.lower()
            self.original_text = [word.string.lower()] # list b/c there might be more than one in the future
            self.start_time = word.start
            self.end_time = word.end
            self.duration = word.duration
        elif self.format == "csv":
            self.text = word.lower()
            self.original_text = [word.lower()] # list b/c there might be more than one in the future
            self.start_time = None
            self.end_time = None
            self.duration = None

    def __str__(self):
        """ Enables the str() function. Returns the simplest textual representation of the Unit."""
        return self.text


class ParsedResponse():
    """ Implements a representation of a subject response, along with methods for parsing it.

    ParsedResponse is a list-like class that contains a list of Unit objects and properties
    relevant to type of clustering being performed by VFClust. It implements methods for
    simplifying the list of Units, removing repetitions, creating compound words, removing
    irrelevant response tokens, etc.
         """
    def __init__(self,response_type,
                 letter_or_category,
                 quiet = False,
                 cmudict = None, # dictionary of phonetic representations of words
                 english_words = None, # big list of legal words
                 lemmas = None, # list of available lemmas
                 names = None, # list of tokenized responses, i.e. tokenized animal names
                 permissible_words = None): # list of semantic words (animals, etc)

        """Initializes a ParsedResponse object.

        :param str response_type:    'PHONETIC' or 'SEMANTIC - used for determining whether
                            lemmatization/tokenization should be done during initialization
        :param str letter_or_category: letter (for type='PHONETIC') or string (for type='SEMANTIC')
                            required for determining which Units in the list are appropriate responses
                            to the current fluencyt ask
        :param bool quiet:  If True, suppresses output to screen.
        :param dict cmudict: Dictionary of phonetic representations of words. Used for phonetic clustering.
        :param list english_words: Big list of English words. Used to determine whether responses
                            in the phonetic clustering response are in English.
        :param set lemmas:  Set of available lemmas, i.e. words in their simplest version (non-plural)
        :param list names:  List of tokenized responses, i.e. compound words.
        :param list permissible_words:  List of legal words of the relevant dimension
        """
        self.type = response_type
        self.letter_or_category = letter_or_category
        self.quiet = quiet
        self.cmudict = cmudict
        self.english_words = english_words
        self.lemmas = lemmas
        self.names = names
        self.permissible_words = permissible_words

        self.unit_list = []
        self.timing_included = None

        self.iterator_index = 0 # used for iterating

    def __iter__(self):
        """
        Makes the object iterable, iterates over the list of units in the ParsedResponse.
        """
        return iter(self.unit_list)


    def __len__(self):
        """
        Implements len(), returns length of the list of units in the ParsedResponse.

        """
        return len(self.unit_list)

    def __getitem__(self,i):
        """ Implements e.g. parsed_response[i] to return the ith Unit in the ParsedResponse. """
        return self.unit_list[i]

    def create_from_csv(self,token_list):
        """ Fills the ParsedResponse object with a list of words/tokens originally from a .csv file.

        :param list token_list: List of strings corresponding to words in the subject response.

        Modifies:
            - self.timing_included: csv files do not include timing information
            - self.unit_list: fills it with Unit objects derived from the token_list argument.
                If the type is 'SEMANTIC', the words in these units are automatically lemmatized and
                made into compound words where appropriate.
        """
        self.timing_included = False
        for entry in token_list:
            self.unit_list.append(Unit(entry, format = "csv", type = self.type))

        # combine compound words, remove pluralizations, etc
        if self.type == "SEMANTIC":
            self.lemmatize()
            self.tokenize()

    def create_from_textgrid(self,word_list):
        """ Fills the ParsedResponse object with a list of TextGrid.Word objects originally from a .TextGrid file.

        :param list word_list: List of TextGrid.Word objects corresponding to words/tokens in the subject response.

        Modifies:
            - self.timing_included: TextGrid files include timing information
            - self.unit_list: fills it with Unit objects derived from the word_list argument.
                If the type is 'SEMANTIC', the words in these units are automatically lemmatized and
                made into compound words where appropriate.
        """
        self.timing_included = True
        for i, entry in enumerate(word_list):
            self.unit_list.append(Unit(entry, format="TextGrid",
                                       type=self.type,
                                       index_in_timed_response=i))

        # combine compound words, remove pluralizations, etc
        if self.type == "SEMANTIC":
            self.lemmatize()
            self.tokenize()

    def lemmatize(self):
        """Lemmatize all Units in self.unit_list.

        Modifies:
            - self.unit_list: converts the .text property into its lemmatized form.

        This method lemmatizes all inflected variants of permissible words to
        those words' respective canonical forms. This is done to ensure that
        each instance of a permissible word will correspond to a term vector with
        which semantic relatedness to other words' term vectors can be computed.
        (Term vectors were derived from a corpus in which inflected words were
        similarly lemmatized, meaning that , e.g., 'dogs' will not have a term
        vector to use for semantic relatedness computation.)
        """
        for unit in self.unit_list:
            if lemmatizer.lemmatize(unit.text) in self.lemmas:
                    unit.text = lemmatizer.lemmatize(unit.text)


    def tokenize(self):
        """Tokenizes all multiword names in the list of Units.

        Modifies:
            - (indirectly) self.unit_list, by combining words into compound words.

        This is done because many names may be composed of multiple words, e.g.,
        'grizzly bear'. In order to count the number of permissible words
        generated, and also to compute semantic relatedness between these
        multiword names and other names, multiword names must each be reduced to
        a respective single token.
        """
        if not self.quiet:
            print
            print "Finding compound words..."

        # lists of animal names containing 2-5 separate words
        compound_word_dict = {}
        for compound_length in range(5,1,-1):
            compound_word_dict[compound_length] = [name for name in self.names if len(name.split()) == compound_length]

        current_index = 0
        finished = False
        while not finished:
            for compound_length in range(5,1,-1): #[5, 4, 3, 2]
                if current_index + compound_length - 1 < len(self.unit_list): #don't want to overstep bounds of the list
                    compound_word = ""
                    #create compound word
                    for word in self.unit_list[current_index:current_index + compound_length]:
                        compound_word += " " + word.text
                    compound_word = compound_word.strip() # remove initial white space
                    #check if compound word is in list
                    if compound_word in compound_word_dict[compound_length]:
                        #if so, create the compound word
                        self.make_compound_word(start_index = current_index, how_many = compound_length)
                        current_index += 1
                        break
            else: #if no breaks for any number of words
                current_index += 1
                if current_index >= len(self.unit_list): # check here instead of at the top in case
                                                         # changing the unit list length introduces a bug
                    finished = True

    def make_compound_word(self, start_index, how_many):
        """Combines two Units in self.unit_list to make a compound word token.

        :param int start_index: Index of first Unit in self.unit_list to be combined
        :param int how_many: Index of how many Units in self.unit_list to be combined.

        Modifies:
                - self.unit_list: Modifies the Unit corresponding to the first word
                    in the compound word. Changes the .text property to include .text
                    properties from subsequent Units, separted by underscores. Modifies
                    the .original_text property to record each componentword separately.
                    Modifies the .end_time property to be the .end_time of the final unit
                    in the compound word.  Finally, after extracting the text and timing
                    information, it removes all units in the compound word except for the
                    first.

        .. note: This method is only used with semantic processing, so we don't need to worry
            about the phonetic representation of Units.

        """
        if not self.quiet:
            compound_word = ""
            for word in self.unit_list[start_index:start_index + how_many]:
                compound_word += " " + word.text
            print compound_word.strip(), "-->","_".join(compound_word.split())

        #combine text
        for other_unit in range(1, how_many):
            self.unit_list[start_index].original_text.append(self.unit_list[start_index + other_unit].text)
            self.unit_list[start_index].text += "_" + self.unit_list[start_index + other_unit].text

        #start time is the same. End time is the end time of the LAST word
        self.unit_list[start_index].end_time = self.unit_list[start_index + how_many - 1].end_time

        #shorten unit_list
        self.unit_list = self.unit_list[:start_index + 1] + self.unit_list[start_index + how_many:]

    def remove_unit(self, index):
        '''Removes the unit at the given index in self.unit_list. Does not modify any other units.'''
        if not self.quiet:
            print "Removing", self.unit_list[index].text
        self.unit_list.pop(index)

    def combine_same_stem_units(self, index):
        """Combines adjacent words with the same stem into a single unit.

        :param int index: Index of Unit in self.unit_list to be combined with the
            subsequent Unit.

        Modifies:
                - self.unit_list: Modifies the .original_text property of the Unit
                    corresponding to the index.  Changes the .end_time property to be the
                    .end_time of the next Unit, as Units with the same stem are considered
                     as single Unit inc lustering. Finally, after extracting the text and timing
                    information, it removes the unit at index+1.

        """

        if not self.quiet:
            combined_word = ""
            for word in self.unit_list[index:index + 2]:
                for original_word in word.original_text:
                    combined_word += " " + original_word
            print combined_word.strip(), "-->","/".join(combined_word.split())

        # edit word list to reflect what words are represented by this unit
        self.unit_list[index].original_text.append(self.unit_list[index + 1].text)

        #start time is the same. End time is the end time of the LAST word
        self.unit_list[index].end_time = self.unit_list[index + 1].end_time

        # remove word with duplicate stem
        self.unit_list.pop(index + 1)


    def display(self):
        """Pretty-prints the ParsedResponse to the screen."""

        table_list = []
        table_list.append(("Text","Orig. Text","Start time","End time", "Phonetic"))
        for unit in self.unit_list:
            table_list.append((unit.text,
                               "/".join(unit.original_text),
                               unit.start_time,
                               unit.end_time,
                               unit.phonetic_representation))
        print_table(table_list)

    def generate_phonetic_representation(self, word):
        """
        Returns a generated phonetic representation for a word.

        :param str word: a word to be phoneticized.
        :return: A list of phonemes representing the phoneticized word.

        This method is used for words for which there is no pronunication
        entry in the CMU dictionary. The function generates a
        pronunication for the word in the standard CMU format. This can then
        be converted to a compact phonetic representation using
        modify_phonetic_representation().

        """
        with NamedTemporaryFile() as temp_file:
            # Write the word to a temp file
            temp_file.write(word)
            #todo - clean up this messy t2p path
            t2pargs = [os.path.abspath(os.path.join(os.path.dirname(__file__),'t2p/t2p')),
                       '-transcribe', os.path.join(data_path, 'cmudict.0.7a.tree'),
                       temp_file.name]
            print t2pargs
            temp_file.seek(0)
            output, error = subprocess.Popen(
                t2pargs, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            ).communicate()
            output = output.split()
            phonetic_representation = output[1:]

        return phonetic_representation

    def modify_phonetic_representation(self, phonetic_representation):
        """ Returns a compact phonetic representation given a CMUdict-formatted representation.

        :param list phonetic_representation: a phonetic representation in standard
            CMUdict formatting, i.e. a list of phonemes like ['HH', 'EH0', 'L', 'OW1']
        :returns: A string representing a custom phonetic representation, where each phoneme is
            mapped to a single ascii character.

        Changing the phonetic representation from a list to a string is useful for calculating phonetic
        simlarity scores.
        """

        for i in range(len(phonetic_representation)):
            # Remove numerical stress indicators
            phonetic_representation[i] = re.sub('\d+', '', phonetic_representation[i])

        multis = ['AA', 'AE', 'AH', 'AO', 'AW', 'AY', 'CH', 'DH', 'EH', 'ER',
                  'EY', 'HH', 'IH', 'IY', 'JH', 'NG', 'OW', 'OY', 'SH',
                  'TH', 'UH', 'UW', 'ZH']

        singles = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l',
                   'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w']

        for i in range(len(phonetic_representation)):
            # Convert multicharacter phone symbols to arbitrary
            # single-character symbols
            if phonetic_representation[i] in multis:
                phonetic_representation[i] = singles[multis.index(phonetic_representation[i])]
        phonetic_representation = ''.join(phonetic_representation)

        return phonetic_representation

    def clean(self):
        """ Removes any Units that are not applicable given the current semantic or phonetic category.

        Modifies:
            - self.unit_list: Removes Units from this list that do not fit into the clustering category.
                it does by by either combining units to make compound words, combining units with the
                same stem, or eliminating units altogether if they do not conform to the category.
                 If the type is phonetic, this method also generates phonetic clusters for all Unit
                 objects in self.unit_list.


        This method performs three main tasks:
            1. Removes words that do not conform to the clustering category (i.e. start with the
                wrong letter, or are not an animal).
            2. Combine adjacent words with the same stem into a single unit. The NLTK Porter Stemmer
                is used for determining whether stems are the same.
                http://www.nltk.org/_modules/nltk/stem/porter.html
            3. In the case of PHONETIC clustering, compute the phonetic representation of each unit.

        """

        if not self.quiet:
            print
            print "Preprocessing input..."
            print "Raw response:"
            print self.display()

        if not self.quiet:
            print
            print "Cleaning words..."

        #weed out words not starting with the right letter or in the right category
        current_index = 0
        while current_index < len(self.unit_list):
            word = self.unit_list[current_index].text
            if self.type == "PHONETIC":
                test = (word.startswith(self.letter_or_category) and  #starts with required letter
                        not word.endswith('-') and  # Weed out word fragments
                            '_' not in word and # Weed out, e.g., 'filledpause_um'
                        word.lower() in self.english_words) #make sure the word is english
            elif self.type == "SEMANTIC":
                test = word in self.permissible_words
            if not test: #if test fails remove word
                self.remove_unit(index = current_index)
            else: # otherwise just increment, but check to see if you're at the end of the list
                current_index += 1

        #combine words with the same stem
        current_index = 0
        finished = False
        while current_index < len(self.unit_list) - 1:
            #don't combine for lists of length 0, 1
            if stemmer.stem(self.unit_list[current_index].text) == \
                stemmer.stem(self.unit_list[current_index + 1].text):
                #if same stem as next, merge next unit with current unit
                self.combine_same_stem_units(index = current_index)
            else: # if not same stem, increment index
                current_index += 1

        #get phonetic representations
        if self.type == "PHONETIC":
            for unit in self.unit_list:
                word = unit.text

                #get phonetic representation
                if word in self.cmudict:
                    # If word in CMUdict, get its phonetic representation
                    phonetic_representation = self.cmudict[word]
                if word not in self.cmudict:
                    # Else, generate a phonetic representation for it
                    phonetic_representation = self.generate_phonetic_representation(word)
                    phonetic_representation = self.modify_phonetic_representation(phonetic_representation)

                unit.phonetic_representation = phonetic_representation

        if not self.quiet:
            print
            print "Cleaned response:"
            print self.display()



class VFClustEngine(object):
    """ Class used for encapsulating clustering methods and data. """
    def __init__(self,
                 response_category,
                 response_file_path,
                 target_file_path=None,
                 collection_types=["cluster", "chain"],
                 similarity_measures=["phone", "biphone", "lsa"],  #only the appropriate ones are run
                 clustering_parameter=91,  #for lsa
                 quiet=False):

        """Initialize for VFClust analysis of a verbal phonetic or semantic fluency test response.

        response_file_path -- filepath for a comma-separated string comprising a
                    file ID and the words, pauses, etc., produced during the
                    attempt. Or, if the response format is a TextGrid file,
                    the filepath for that file.
                    Field 1 in the response file should hold some sort of file ID,
                    e.g., a filename or subject ID. Subsequent fields must each hold
                    a single word or filled pause, etc., that was produced during
                    the attempt.
        target_file_path -- file to which VF-Clust CSV output will be written.
        collection_types -- list of "cluster" or "chain" - what the measures should be calculated over
        similarity_measures -- list of types of similarity measures to use between words
            - at this point "phone" and "biphone" are supported

        :param str response_category: a letter in the case of phonetic clustering, or a word category
            (e.g. animals) in for phonetic clustering.
        :param str response_file_path: file path of the subject response to be clustered.
        :param target_file_path: (optional) directory in which the the .csv output file to be produced.
        :param list collection_types: (optional) list of collection types to be used in clustering.
            A "chain" is list of response tokens in which every token is related to the tokens adjacent
            to it. A "cluster" is a list of response tokens in which every token is related to every
            token in the cluster.
        :param similarity_measures: (optional) a list of similarity measures to be used. By default, "lsa"
            (Linear Semantic Analysis) is used for SEMANTIC clustering, and "phone" and "biphone" are used
            for PHONETIC clustering.
        :param clustering_parameter: (optional) parameters to be used in clustering
        :param bool quiet: (optional) If set to True, suppresses output to screen.

        The initialization of a VFClustEngine object performs the following:
            - parse input arguments
            - loads relevant data from the supporting data directory to be used in
                clustering, i.e. permissible words, LSA feature vectors, a dictionary of
                English words, etc
            - parses the subject response, generating a parsed_response object
            - performs clustering
            - produces a .csv file with clustering results.

        The self.measures dictionary is used to hold all measures derived from the analysis.  The
        acutal collections produced are printed to screen, but only the measures derived from
        clustering are output to the .csv file.

        Methods are organized into two categories:
            - load_ methods, in which data is loaded from disk
            - get_ methods, which print processing information to screen, perform preprocessing and call related
                clustering methods. These are called from __init__
            - compute_ methods, which compute cluster-specific measures. These are called from get_ methdos.


        .. note:: Both clusters and chains are implemented as collection types. Because there is more than one type,
            the word "collection" is used throughout to refer to both clusters and chains. However, "clustering"
            is still used to mean the process of discovering these groups.

        .. note:: At this point, the only category of semantic clustering available is "animals."

    """
        self.valid_semantic_categories = ['animals']
        self.valid_phonetic_categories = ['a', 'f', 's', 'p']
        self.valid_semantic_measures = ['lsa']
        self.valid_phonemic_measures = ['phone', 'biphone']
        self.vowels = ['AA', 'AE', 'AH', 'AO', 'AW', 'AY', 'EH', 'ER', 'EY', 'IH', 'IY',
          'OW', 'OY', 'UH', 'UW']
        self.continuants = ['DH', 'F', 'L', 'M', 'N', 'NG', 'R', 'S', 'SH', 'TH', 'V',
               'Z', 'ZH']

        #parse input arguments
        self.quiet = quiet
        self.target_file = target_file_path
        self.response_format = os.path.splitext(response_file_path)[1][1:]
        self.response_category = response_category
        self.collection_types = collection_types
        if self.response_category in self.valid_phonetic_categories:
            self.type = "PHONETIC"
            self.letter = response_category
            self.similarity_measures = [m for m in similarity_measures if m in self.valid_phonemic_measures]

        elif response_category in self.valid_semantic_categories:
            self.type = "SEMANTIC"
            self.category = response_category
            self.clustering_parameter = int(clustering_parameter)
            self.similarity_measures = [m for m in similarity_measures if m in self.valid_semantic_measures]
        else:
            raise VFClustException('Invalid response category!  You provided ' + response_category)

        #dictionary to hold the results
        self.measures = defaultdict(int)
        # makes the default value 0 instead of KeyError but otherwise just like a dict

        #read response file
        if self.response_format not in ['csv', 'TextGrid']:
            raise VFClustException('Currently, VF-Clust only accepts responses in ' +
                                   'comma-separated (csv) or Praat TextGrid formats. ' +
                                   'Your response format is ' + self.response_format)
        if self.response_format == 'csv':
            self.raw_response = open(response_file_path, 'r').readlines()[0].lower()
            self.raw_response = self.raw_response.strip('\n')
            self.raw_response = self.raw_response.split(',')
            self.measures['file_id'] = self.raw_response[0]
            del self.raw_response[0]
            self.raw_response = [re.sub(' ', '', word) for word in
                                  self.raw_response]

        if self.response_format == 'TextGrid':
            # self.full_timed_response is a list of Word objects (defined in TextGridParser.py),
            #   which are defined by having a string for the word, start and end times.
            self.full_timed_response = TextGrid(response_file_path).parse_words()
            # Set filename, less '.TextGrid', as file ID.
            self.measures['file_id'] = os.path.basename(response_file_path)[:-9]

        #load supporting data
        if not self.quiet: print
        if self.type == "PHONETIC":
            self.names = None
            self.lemmas = None
            self.permissible_words = None
            # Load the modified CMU Pronouncing Dictionary (cmudict)
            self.cmudict = pickle.load(open(os.path.join(data_path, 'modified_cmudict.dat'), 'rb'))
            self.english_words = open(os.path.join(data_path,os.path.join('EOWL','english_words.txt')),'r').read().split()
        elif self.type == "SEMANTIC":
            self.cmudict = None
            self.english_words = None
            if not self.quiet:
                print "Loading lemmas..."
            self.lemmas = pickle.load(open(os.path.join(data_path, self.category + '_lemmas.dat'), 'rb'))
            if not self.quiet:
                print "Loading tokenized responses..."
            self.names = pickle.load(open(os.path.join(data_path, self.category + '_names_raw.dat'), 'rb'))
            if not self.quiet:
                print "Loading list of permissible words..."
            with open(os.path.join(data_path, self.category + '_names.dat'), 'rb') as infile:
                self.permissible_words = pickle.load(infile)

            if "lsa" in self.similarity_measures:
                self.load_lsa_information()


        # PARSING AND COUNTING
        # iterable, ordered collection of Units. Need to pass in information required for parsing.
        self.parsed_response = ParsedResponse(self.type,
                                              quiet = self.quiet,
                                              letter_or_category=response_category,
                                              cmudict = self.cmudict,
                                              english_words = self.english_words,
                                              lemmas = self.lemmas,
                                              names = self.names,
                                              permissible_words = self.permissible_words)
        if self.response_format == "csv":
            self.parsed_response.create_from_csv(self.raw_response)
        elif self.response_format == "TextGrid":
            self.parsed_response.create_from_textgrid(self.full_timed_response)

        self.get_raw_counts() #using non-cleaned response, i.e. include all words
        self.parsed_response.clean()  # combine words, get rid of irrevelant input, etc

        #CLUSTERING
        #do calculations for every combination of similarity measure and collection type (cluster, chain, etc).
        for similarity_measure in self.similarity_measures:
            #calculate similarity measures between words
            self.current_similarity_measure = similarity_measure
            self.similarity_threshold = None
            self.similarity_scores = []
            if not self.quiet:
                print
                print
                print "        ########################################################\n" + \
                      "        ###########                                  ###########\n" + \
                      "                         Similarity Measure:                    \n" + \
                      "                         " + similarity_measure + "\n" + \
                      "        ###########                                  ###########\n" + \
                      "        ########################################################\n"

                self.get_similarity_measures()  #calculate similarity measures between words to display

            for collection_type in self.collection_types:
                if not self.quiet:
                    print
                    print
                    print "        ////////////////////////////////////////////////////////\n" + \
                          "        ///////////                                  ///////////\n" + \
                          "                         Collection type:                    \n" + \
                          "                         " + collection_type + "\n" +\
                          "        ///////////                                  ///////////\n" + \
                          "        ////////////////////////////////////////////////////////\n"

                #calculate collection metrics
                self.current_collection_type = collection_type
                self.collection_indices = []
                self.collection_list = []
                self.collection_sizes = []
                self.collection_sizes_no_singletons = []
                self.get_collections()
                self.get_collection_measures()

        self.print_output()


    ########################################################
    ###########                                  ###########
    ###########   Processing helper functions    ###########
    ###########                                  ###########
    ########################################################

    def load_lsa_information(self):
        """Loads a dictionary from disk that maps permissible words to their LSA term vectors."""

        if not (49 < int(self.clustering_parameter) < 101):
            raise Exception('Only LSA dimensionalities in the range 50-100' +
                            ' are supported.')
        if not self.quiet:
            print "Loading LSA term vectors..."
        #the protocol2 used the pickle highest protocol and this one is a smaller file
        with open(os.path.join(data_path, self.category + '_' +
                os.path.join('term_vector_dictionaries',
                             'term_vectors_dict' +
                                     str(self.clustering_parameter) + '_cpickle.dat')),
                  'rb') as infile:
            self.term_vectors = pickle.load(infile)


    def get_similarity_measures(self):
        """Helper function for computing similarity measures."""
        if not self.quiet:
            print
            print "Computing", self.current_similarity_measure, "similarity..."

        self.compute_similarity_scores()
        #output to screen is done within this method

    def get_collections(self):
        """Helper function for determining what the clusters/chains/other collections are."""
        if not self.quiet:
            print
            print "Finding " + self.current_collection_type + "s..."

        self.compute_collections()

        if not self.quiet:
            print self.current_similarity_measure, self.current_collection_type, "information:"
            table_contents = [("Collection","Indices","Size")]
            for (i, j, k) in zip(self.collection_indices,self.collection_sizes,self.collection_list):
                table_contents.append(([unit.text for unit in k], i, j))
            print_table(table_contents)


    def get_collection_measures(self):
        """Helper function for calculating measurements derived from clusters/chains/collections"""

        if not self.quiet:
            print
            print "Computing duration-independent", self.current_collection_type, "measures..."

        self.compute_collection_measures() #include length=1 clusters
        self.compute_collection_measures(no_singletons = True)  #no length=1 clusters

        self.compute_pairwise_similarity_score()

        if not self.quiet:
            collection_measures = [x for x in self.measures \
                               if x.startswith("COLLECTION_")
                                    and self.current_collection_type in x
                                    and self.current_similarity_measure in x]
            collection_measures.sort()
            print_table([(k, str(self.measures[k])) for k in collection_measures])

        if not self.quiet:
            print
            print "Computing duration-based clustering measures..."

        self.compute_duration_measures()



    def get_raw_counts(self):
        """Determines counts for unique words, repetitions, etc using the raw text response.

        Adds the following measures to the self.measures dictionary:
            - COUNT_total_words: count of words (i.e. utterances with semantic content) spoken
                by the subject. Filled pauses, silences, coughs, breaths, words by the interviewer,
                etc. are all excluded from this count.
            - COUNT_permissible_words: Number of words spoken by the subject that qualify as a
                valid response according to the clustering criteria. Compound words are counted
                as a single word in SEMANTIC clustering, but as two words in PHONETIC clustering.
                This is implemented by tokenizing SEMANTIC clustering responses in the __init__
                method before calling the current method.
            - COUNT_exact_repetitions: Number of words which repeat words spoken earlier in the
                response. Responses in SEMANTIC clustering are lemmatized before this function is
                called, so slight variations (dog, dogs) may be counted as exact responses.
            - COUNT_stem_repetitions: Number of words stems identical to words uttered earlier in
                the response, according to the Porter Stemmer.  For example, 'sled' and 'sledding'
                have the same stem ('sled'), and 'sledding' would be counted as a stem repetition.
            - COUNT_examiner_words: Number of words uttered by the examiner. These start
                with "E_" in .TextGrid files.
            - COUNT_filled_pauses: Number of filled pauses uttered by the subject. These begin
                with "FILLEDPAUSE_" in the .TextGrid file.
            - COUNT_word_fragments: Number of word fragments uttered by the subject. These
                end with "-" in the .TextGrid file.
            - COUNT_asides: Words spoken by the subject that do not adhere to the test criteria are
                counted as asides, i.e. words that do not start with the appropriate letter or that
                do not represent an animal.
            - COUNT_unique_permissible_words: Number of works spoken by the subject, less asides,
                stem repetitions and exact repetitions.
        """

        #for making the table at the end
        words = []
        labels = []
        words_said = set()

        # Words like "polar_bear" as one semantically but two phonetically
        # Uncategorizable words are counted as asides
        for unit in self.parsed_response:
            word = unit.text
            test = False
            if self.type == "PHONETIC":
                test = (word.startswith(self.letter) and
                        "T_" not in word and "E_" not in word and "!" not in word and # Weed out tags
                        "FILLEDPAUSE_" not in word and # Weed out filled pauses
                        not word.endswith('-') and # Weed out false starts
                        word.lower() in self.english_words)  #weed out non-words
            elif self.type == "SEMANTIC":
                #automatically weed out all non-semantically-appropriate responses
                test = (word in self.permissible_words)

            if test:
                self.measures['COUNT_total_words'] += 1
                self.measures['COUNT_permissible_words'] += 1
                if any(word == w for w in words_said):
                    self.measures['COUNT_exact_repetitions'] += 1
                    labels.append('EXACT REPETITION')
                elif any(stemmer.stem(word) == stemmer.stem(w) for w in words_said):
                    self.measures['COUNT_stem_repetitions'] += 1
                    labels.append('STEM REPETITION')
                else:
                    labels.append('PERMISSIBLE WORD')
                words_said.add(word)
                words.append(word)
            elif word.lower().startswith('e_'):
                self.measures['COUNT_examiner_words'] += 1
                words.append(word)
                labels.append('EXAMINER WORD')
            elif word.endswith('-'):
                self.measures['COUNT_word_fragments'] += 1
                words.append(word)
                labels.append('WORD FRAGMENT')
            elif word.lower().startswith('filledpause'):
                self.measures['COUNT_filled_pauses'] += 1
                words.append(word)
                labels.append('FILLED PAUSE')
            elif word.lower() not in ['!sil', 't_noise', 't_cough', 't_lipsmack', 't_breath']:
                self.measures['COUNT_total_words'] += 1
                self.measures['COUNT_asides'] += 1
                words.append(word)
                labels.append('ASIDE')

        if not self.quiet:
            print
            print "Labels:"
            print_table([(word,label) for word,label in zip(words,labels)])

        self.measures['COUNT_unique_permissible_words'] = \
            self.measures['COUNT_permissible_words'] - \
            self.measures['COUNT_exact_repetitions'] - \
            self.measures['COUNT_stem_repetitions']

        if not self.quiet:
            print
            print "Counts:"
            collection_measures = [x for x in self.measures if x.startswith("COUNT_")]
            collection_measures.sort()
            if not self.quiet:
                print_table([(k, str(self.measures[k])) for k in collection_measures])

    ########################################################
    ###########                                  ###########
    ###########            Calculate             ###########
    ###########       Similarity Measures        ###########
    ###########                                  ###########
    ########################################################

    def compute_similarity_score(self, unit1, unit2):
        """ Returns the similarity score between two words.

         The type of similarity scoring method used depends on the currently active
         method and clustering type.

        :param unit1: Unit object corresponding to the first word.
        :type unit1: Unit
        :param unit2: Unit object corresponding to the second word.
        :type unit2: Unit
        :return: Number indicating degree of similarity of the two input words.
            The maximum value is 1, and a higher value indicates that the words
            are more similar.
        :rtype : Float

        The similarity method used depends both on the type of test being performed
        (SEMANTIC or PHONETIC) and the similarity method currently assigned to the
        self.current_similarity_measure property of the VFClustEngine object.  The
        similarity measures used are the following:
            - PHONETIC/"phone": the phonetic similarity score (PSS) is calculated
                between the phonetic representations of the input units. It is equal
                to 1 minus the Levenshtein distance between two strings, normalized
                to the length of the longer string. The strings should be compact
                phonetic representations of the two words.
                (This method is a modification of a Levenshtein distance function
                available at http://hetland.org/coding/python/levenshtein.py.)
            - PHONETIC/"biphone": the binary common-biphone score (CBS) depends
                on whether two words share their initial and/or final biphone
                (i.e., set of two phonemes). A score of 1 indicates that two words
                have the same intial and/or final biphone; a score of 0 indicates
                that two words have neither the same initial nor final biphone.
                This is also calculated using the phonetic representation of the
                two words.
            - SEMANTIC/"lsa": a semantic relatedness score (SRS) is calculated
                as the COSINE of the respective term vectors for the first and
                second word in an LSA space of the specified clustering_parameter.
                Unlike the PHONETIC methods, this method uses the .text property
                of the input Unit objects.

        """

        if self.type == "PHONETIC":
            word1 = unit1.phonetic_representation
            word2 = unit2.phonetic_representation
            if self.current_similarity_measure == "phone":
                word1_length, word2_length = len(word1), len(word2)
                if word1_length > word2_length:
                    # Make sure n <= m, to use O(min(n,m)) space
                    word1, word2 = word2, word1
                    word1_length, word2_length = word2_length, word1_length
                current = range(word1_length + 1)
                for i in range(1, word2_length + 1):
                    previous, current = current, [i] + [0] * word1_length
                    for j in range(1, word1_length + 1):
                        add, delete = previous[j] + 1, current[j - 1] + 1
                        change = previous[j - 1]
                        if word1[j - 1] != word2[i - 1]:
                            change += 1
                        current[j] = min(add, delete, change)
                phonetic_similarity_score = 1 - current[word1_length] / word2_length
                return phonetic_similarity_score

            elif self.current_similarity_measure == "biphone":
                if word1[:2] == word2[:2] or word1[-2:] == word2[-2:]:
                    common_biphone_score = 1
                else:
                    common_biphone_score = 0
                return common_biphone_score

        elif self.type == "SEMANTIC":
            word1 = unit1.text
            word2 = unit2.text
            if self.current_similarity_measure == "lsa":
                w1_vec = self.term_vectors[word1]
                w2_vec = self.term_vectors[word2]
                # semantic_relatedness_score = (numpy.dot(w1_vec, w2_vec) /
                #                               numpy.linalg.norm(w1_vec) /
                #                               numpy.linalg.norm(w2_vec))
                dot = sum([w1*w2 for w1,w2 in zip(w1_vec, w2_vec)])
                norm1 = sqrt(sum([w*w for w in w1_vec]))
                norm2 = sqrt(sum([w*w for w in w2_vec]))
                semantic_relatedness_score =  dot/(norm1 * norm2)
                return semantic_relatedness_score
        return None  #shouldn't happen

    def compute_similarity_scores(self):
        """ Produce a list of similarity scores for each contiguous pair in a response.

        Calls compute_similarity_score method for every adjacent pair of words. The results
        are not used in clustering; this is merely to provide a visual representation to
        print to the screen.

        Modifies:
            - self.similarity_scores: Fills the list with similarity scores between adjacent
                words. At this point this list is never used outside of this method.
        """

        for i,unit in enumerate(self.parsed_response):
            if i < len(self.parsed_response) - 1:
                next_unit = self.parsed_response[i + 1]
                self.similarity_scores.append(self.compute_similarity_score(unit, next_unit))

        if not self.quiet:
            print self.current_similarity_measure, "similarity scores (adjacent) -- higher is closer:"
            table = [("Word 1", "Word 2", "Score")] + \
                    [(self.parsed_response[i].text, self.parsed_response[i + 1].text,
                      "{0:.3f}".format(round(self.similarity_scores[i], 2)))
                     for i in range(len(self.parsed_response)-1)]
            print_table(table)

    ########################################################
    ###########                                  ###########
    ###########          Find collections        ###########
    ###########                                  ###########
    ########################################################

    def compute_collections(self):
        """ Finds the collections (clusters,chains) that exist in parsed_response.

        Modified:
            - self.collection_sizes: populated with a list of integers indicating
                the number of units belonging to each collection
            - self.collection_indices: populated with a list of strings indicating
                the indices of each element of each collection
            - self.collection_list: populated with a list lists, each list containing
                Unit objects belonging to each collection

        There are two types of collections currently implemented:
        - cluster: every entry in a cluster is sufficiently similar to every other entry
        - chain: every entry in a chain is sufficiently similar to adjacent entries

        Similarity between words is calculated using the compute_similarity_score method.
        Scores between words are then thresholded and binarized using empirically-derived
        thresholds (see: ???). Overlap of clusters is allowed (a word can be part of
        multiple clusters), but overlapping chains are not possible, as any two adjacent
        words with a lower-than-threshold similarity breaks the chain.  Clusters subsumed
        by other clusters are not counted. Singletons, i.e., clusters of size 1, are
        included in this analysis.


        .. todo: Find source for thresholding values.
        """
        if self.type == "PHONETIC":
            if self.current_similarity_measure == "phone":
                phonetic_similarity_thresholds = {'a': 0.222222222222,
                                                  'b': 0.3,
                                                  'c': 0.2857142857134,
                                                  'd': 0.3,
                                                  'e': 0.25,
                                                  'f': 0.333333333333,
                                                  'g': 0.2857142857142857,
                                                  'h': 0.333333333333,
                                                  'i': 0.3,
                                                  'j': 0.3,
                                                  'k': 0.3,
                                                  'l': 0.333333333333,
                                                  'm': 0.333333333333,
                                                  'n': 0.2857142857142857,
                                                  'o': 0.222222222222,
                                                  'p': 0.2857142857134,
                                                  'q': 0.4285714285714286,
                                                  'r': 0.3,
                                                  's': 0.2857142857134,
                                                  't': 0.2857142857134,
                                                  'u': 0.3076923076923077,
                                                  'v': 0.333333333333,
                                                  'w': 0.333333333333,
                                                  'x': 0.2857142857134,
                                                  'y': 0.333333333333,
                                                  'z': 0.333333333333}
                self.similarity_threshold = phonetic_similarity_thresholds[self.letter]
            elif self.current_similarity_measure == "biphone":
                self.similarity_threshold = 1

        elif self.type == "SEMANTIC":
            if self.current_similarity_measure == "lsa":
                if self.category == 'animals':
                    thresholds = {'50': 0.229306542684, '51': 0.22594687203200001,
                                  '52': 0.22403235205800001, '53': 0.214750475853,
                                  '54': 0.210178113675, '55': 0.209214667474,
                                  '56': 0.204037629443, '57': 0.203801260742,
                                  '58': 0.203261303516, '59': 0.20351336452999999,
                                  '60': 0.19834361415999999, '61': 0.19752806852999999,
                                  '62': 0.191322450624, '63': 0.194312302459,
                                  '64': 0.188165419858, '65': 0.18464545450299999,
                                  '66': 0.18478136731399999, '67': 0.178950849271,
                                  '68': 0.17744175606199999, '69': 0.17639888996299999,
                                  '70': 0.17537403274400001, '71': 0.17235091169799999,
                                  '72': 0.17115875396499999, '73': 0.17262141635100001,
                                  '74': 0.16580303697500001, '75': 0.16416843492800001,
                                  '76': 0.166395146381, '77': 0.162961462955,
                                  '78': 0.161888890545, '79': 0.160416925579,
                                  '80': 0.157132807023, '81': 0.15965395155699999,
                                  '82': 0.155974588379, '83': 0.15606832182700001,
                                  '84': 0.14992240019899999, '85': 0.15186462595399999,
                                  '86': 0.14976638614599999, '87': 0.14942388535199999,
                                  '88': 0.14740916274999999, '89': 0.14821336952600001,
                                  '90': 0.14188941422699999, '91': 0.14039515298300001,
                                  '92': 0.14125100827199999, '93': 0.140135804694,
                                  '94': 0.13933483465099999, '95': 0.139679588617,
                                  '96': 0.13569859464199999, '97': 0.135394351192,
                                  '98': 0.13619473881800001, '99': 0.136671316751,
                                  '100': 0.135307208304}

                    self.similarity_threshold = thresholds[str(self.clustering_parameter)]

        if not self.quiet:
            print "Similarity threshold:", self.similarity_threshold

        for index, unit in enumerate(self.parsed_response):
            next_word_index = index + 1
            collection = [unit] # begin current collection
            collection_index = [index] # begin current collection index list
            collection_terminus_found = False
            while not collection_terminus_found:
                if next_word_index < len(self.parsed_response):
                    # Check whether last word in attempt has been read
                    test = False
                    if self.current_collection_type == "cluster":
                        # Check whether next word is related to
                        # every other word in cluster
                        unit2 = self.parsed_response[next_word_index]
                        test = all([self.compute_similarity_score(unit2, other_unit) >= self.similarity_threshold \
                                for other_unit in collection])
                    elif self.current_collection_type == "chain":
                        #check whether the word is related to the one before it
                        #remember that we're testing words at the end of the chain, and creating new links
                        unit1 = self.parsed_response[next_word_index - 1]
                        unit2 = self.parsed_response[next_word_index]
                        test = self.compute_similarity_score(unit1,unit2) >= self.similarity_threshold
                    if test:
                        #add NEXT word
                        collection.append(self.parsed_response[next_word_index])
                        collection_index.append(next_word_index)
                        next_word_index += 1
                    else:

                        # Check whether cluster is subsequence of cluster
                        # already added to list
                        collection_index = ' '.join([str(w) for w in collection_index])
                        if collection_index not in str(self.collection_indices):
                            self.collection_indices.append(collection_index)
                            self.collection_sizes.append(len(collection))
                        collection_terminus_found = True
                else:
                    # Execute if word is last word in attempt
                    collection_index = ' '.join([str(w) for w in collection_index])
                    if collection_index not in str(self.collection_indices):
                        self.collection_indices.append(collection_index)
                        self.collection_sizes.append(len(collection))
                    collection_terminus_found = True

        # Get a list of collections and their positions in the response.
        for index in self.collection_indices:
            collection = []
            for i in index.split():
                collection.append(self.parsed_response[int(i)])
            self.collection_list.append(collection)



    ########################################################
    ###########                                  ###########
    ###########         Timing-independent       ###########
    ###########             Measures             ###########
    ###########                                  ###########
    ########################################################

    def compute_pairwise_similarity_score(self):
        """Computes the average pairwise similarity score between all pairs of Units.

        The pairwise similarity is calculated as the sum of similarity scores for all pairwise
        word pairs in a response -- except any pair composed of a word and
        itself -- divided by the total number of words in an attempt. I.e.,
        the mean similarity for all pairwise word pairs.

        Adds the following measures to the self.measures dictionary:
            - COLLECTION_collection_pairwise_similarity_score_mean: mean of pairwise similarity scores

        .. todo: divide by (count-1)?
        """
        pairs = []
        all_scores = []
        for i, unit in enumerate(self.parsed_response):
            for j, other_unit in enumerate(self.parsed_response):
                if i != j:
                    pair = (i, j)
                    rev_pair = (j, i)
                    if pair not in pairs and rev_pair not in pairs:
                        score = self.compute_similarity_score(unit, other_unit)
                        pairs.append(pair)
                        pairs.append(rev_pair)
                        all_scores.append(score)

        self.measures["COLLECTION_" + self.current_similarity_measure + "_pairwise_similarity_score_mean"] = get_mean(
            all_scores) \
            if len(pairs) > 0 else 'na'


    def compute_collection_measures(self, no_singletons=False):
        """ Computes summaries of measures using the discovered collections.

        :param no_singletons: if True, omits collections of length 1 from all measures
            and includes "no_singletons_" in the measure name.

        Adds the following measures to the self.measures dictionary, prefaced by
        COLLECTION_(similarity_measure)_(collection_type)_:
            - count: number of collections
            - size_mean: mean size of collections
            - size_max: size of largest collection
            - switch_count: number of changes between clusters
        """

        prefix = "COLLECTION_" + self.current_similarity_measure + "_" + self.current_collection_type + "_"

        if no_singletons:
            prefix += "no_singletons_"

        if no_singletons:
            collection_sizes_temp = [x for x in self.collection_sizes if x != 1]
        else: #include singletons
            collection_sizes_temp = self.collection_sizes

        self.measures[prefix + 'count'] = len(collection_sizes_temp)

        self.measures[prefix + 'size_mean'] = get_mean(collection_sizes_temp) \
            if self.measures[prefix + 'count'] > 0 else 0

        self.measures[prefix + 'size_max'] = max(collection_sizes_temp) \
            if len(self.collection_sizes) > 0 else 0

        self.measures[prefix + 'switch_count'] = self.measures[prefix + 'count'] - 1


    ########################################################
    ###########                                  ###########
    ###########     Timing-based measures        ###########
    ###########                                  ###########
    ########################################################

    def compute_duration_measures(self):
        """ Helper function for computing measures derived from timing information.

        These are only computed if the response is textgrid with timing information.

        All times are in seconds.
        """

        prefix = "TIMING_" + self.current_similarity_measure + "_" + self.current_collection_type + "_"

        if self.response_format == 'TextGrid':

            self.compute_response_vowel_duration("TIMING_")  #prefixes don't need collection or measure type
            self.compute_response_continuant_duration("TIMING_")
            self.compute_between_collection_interval_duration(prefix)
            self.compute_within_collection_interval_duration(prefix)

            #these give different values depending on whether singleton clusters are counted or not
            self.compute_within_collection_vowel_duration(prefix, no_singletons = True)
            self.compute_within_collection_continuant_duration(prefix, no_singletons = True)
            self.compute_within_collection_vowel_duration(prefix, no_singletons = False)
            self.compute_within_collection_continuant_duration(prefix, no_singletons = False)


    def compute_response_vowel_duration(self, prefix):
        """Computes mean vowel duration in entire response.

        :param str prefix: Prefix for the key entry in self.measures.

        Adds the following measures to the self.measures dictionary:
            - TIMING_(similarity_measure)_(collection_type)_response_vowel_duration_mean: average
                vowel duration of all vowels in the response.
        """
        durations = []
        for word in self.full_timed_response:
            if word.phones:
                for phone in word.phones:
                    if phone.string in self.vowels:
                        durations.append(phone.end - phone.start)

        self.measures[prefix + 'response_vowel_duration_mean'] = get_mean(durations) \
            if len(durations) > 0 else 'na'

        if not self.quiet:
            print "Mean response vowel duration:", self.measures[prefix + 'response_vowel_duration_mean']


    def compute_response_continuant_duration(self, prefix):
        """Computes mean duration for continuants in response.

        :param str prefix: Prefix for the key entry in self.measures.

        Adds the following measures to the self.measures dictionary:
            - TIMING_(similarity_measure)_(collection_type)_response_continuant_duration_mean: average
                vowel duration of all vowels in the response.
        """
        durations = []
        for word in self.full_timed_response:
            if word.phones:
                for phone in word.phones:
                    if phone.string in self.continuants:
                        durations.append(phone.end - phone.start)

        self.measures[prefix + 'response_continuant_duration_mean'] = get_mean(durations) \
            if len(durations) > 0 else 'na'

        if not self.quiet:
            print "Mean response continuant duration:", self.measures[prefix + 'response_continuant_duration_mean']




    def compute_between_collection_interval_duration(self, prefix):
        """Calculates BETWEEN-collection intervals for the current collection and measure type
            and takes their mean.

        :param str prefix: Prefix for the key entry in self.measures.

        Negative intervals (for overlapping clusters) are counted as 0 seconds.  Intervals are
        calculated as being the difference between the ending time of the last word in a collection
        and the start time of the first word in the subsequent collection.

        Note that these intervals are not necessarily silences, and may include asides, filled
        pauses, words from the examiner, etc.

        Adds the following measures to the self.measures dictionary:
            - TIMING_(similarity_measure)_(collection_type)_between_collection_interval_duration_mean:
                average interval duration separating clusters

        """

        durations = []  # duration of each collection
        for collection in self.collection_list:
            # Entry, with timing, in timed_response for first word in collection
            start = collection[0].start_time
            # Entry, with timing, in timed_response for last word in collection
            end = collection[-1].end_time
            durations.append((start, end))

        # calculation between-duration intervals
        interstices = [durations[i + 1][0] - durations[i][1] for i, d in enumerate(durations[:-1])]

        # Replace negative interstices (for overlapping clusters) with
        # interstices of duration 0
        for i, entry in enumerate(interstices):
            if interstices[i] < 0:
                interstices[i] = 0

        self.measures[prefix + 'between_collection_interval_duration_mean'] = get_mean(interstices) \
            if len(interstices) > 0 else 'na'

        if not self.quiet:
            print
            print self.current_similarity_measure + " between-" + self.current_collection_type + " durations"
            table = [(self.current_collection_type + " 1 (start,end)", "Interval",
                      self.current_collection_type + " 2 (start,end)")] + \
                    [(str(d1), str(i1), str(d2)) for d1, i1, d2 in zip(durations[:-1], interstices, durations[1:])]
            print_table(table)
            print
            print "Mean " + self.current_similarity_measure + " between-" + self.current_collection_type + " duration", \
                self.measures[prefix + 'between_collection_interval_duration_mean']




    def compute_within_collection_interval_duration(self, prefix):
        """Calculates mean between-word duration WITHIN collections.

        :param str prefix: Prefix for the key entry in self.measures.

        Calculates the mean time between the end of each word in the collection
        and the beginning of the next word.  Note that these times do not necessarily
        reflect pauses, as collection members could be separated by asides or other noises.

        Adds the following measures to the self.measures dictionary:
            - TIMING_(similarity_measure)_(collection_type)_within_collection_interval_duration_mean
        """

        interstices = []
        for cluster in self.collection_list:
            # Make sure cluster is not a singleton
            if len(cluster) > 1:
                for i in range(len(cluster)):
                    if i != len(cluster) - 1:
                        interstice = cluster[i+1].start_time - cluster[i].end_time
                        interstices.append(interstice)

        self.measures[prefix + 'within_collection_interval_duration_mean'] = get_mean(interstices) \
            if len(interstices) > 0 else 'na'

        if not self.quiet:
            print "Mean within-" + self.current_similarity_measure + "-" + self.current_collection_type + \
                  " between-word duration:", self.measures[prefix + 'within_collection_interval_duration_mean']



    def compute_within_collection_vowel_duration(self, prefix, no_singletons=False):
        """ Computes the mean duration of vowels from Units within clusters.

        :param str prefix: Prefix for the key entry in self.measures
        :param bool no_singletons: If False, excludes collections of length 1 from calculations
            and adds "no_singletons" to the prefix

        Adds the following measures to the self.measures dictionary:
            - TIMING_(similarity_measure)_(collection_type)_within_collection_vowel_duration_mean
        """

        if no_singletons:
            min_size = 2
        else:
            prefix += "no_singletons_"
            min_size = 1

        durations = []
        for cluster in self.collection_list:
            if len(cluster) >= min_size:
                for word in cluster:
                    word = self.full_timed_response[word.index_in_timed_response]
                    for phone in word.phones:
                        if phone.string in self.vowels:
                            durations.append(phone.end - phone.start)

        self.measures[prefix + 'within_collection_vowel_duration_mean'] = get_mean(durations) \
            if len(durations) > 0 else 'na'

        if not self.quiet:
            if no_singletons:
                print "Mean within-" + self.current_similarity_measure + "-" + self.current_collection_type + \
                      " vowel duration, excluding singletons:", \
                    self.measures[prefix + 'within_collection_vowel_duration_mean']
            else:
                print "Mean within-" + self.current_similarity_measure + "-" + self.current_collection_type + \
                      " vowel duration, including singletons:", \
                    self.measures[prefix + 'within_collection_vowel_duration_mean']

    def compute_within_collection_continuant_duration(self, prefix, no_singletons=False):
        """Computes the mean duration of continuants from Units within clusters.

        :param str prefix: Prefix for the key entry in self.measures
        :param bool no_singletons: If False, excludes collections of length 1 from calculations
            and adds "no_singletons" to the prefix

        Adds the following measures to the self.measures dictionary:
            - TIMING_(similarity_measure)_(collection_type)_within_collection_continuant_duration_mean
        """

        if no_singletons:
            min_size = 2
        else:
            prefix += "no_singletons_"
            min_size = 1

        durations = []
        for cluster in self.collection_list:
            if len(cluster) >= min_size:
                for word in cluster:
                    word = self.full_timed_response[word.index_in_timed_response]
                    for phone in word.phones:
                        if phone.string in self.continuants:
                            durations.append(phone.end - phone.start)

        self.measures[prefix + 'within_collection_continuant_duration_mean'] = get_mean(durations) \
            if len(durations) > 0 else 'na'

        if not self.quiet:
            if no_singletons:
                print "Mean within-" + self.current_similarity_measure + "-" + self.current_collection_type +  \
                  " continuant duration, excluding singletons:", \
                    self.measures[prefix + 'within_collection_continuant_duration_mean']
            else:
                print "Mean within-" + self.current_similarity_measure + "-" + self.current_collection_type +  \
                  " continuant duration, including singletons:", \
                    self.measures[prefix + 'within_collection_continuant_duration_mean']


    ########################################################
    ###########                                  ###########
    ###########             Output               ###########
    ###########                                  ###########
    ########################################################

    def print_output(self):
        """ Outputs final list of measures to screen a csv file.

        The .csv file created has the same name as the input file, with
        "vfclust_TYPE_CATEGORY" appended to the filename, where TYPE indicates
        the type of task performed done (SEMANTIC or PHONETIC) and CATEGORY
        indicates the category requirement of the stimulus (i.e. 'f' or 'animals'
        for phonetic and semantic fluency test, respectively.
        """
        if self.response_format == "csv":
            for key in self.measures:
                if "TIMING_" in key:
                    self.measures[key] = "NA"

        if not self.quiet:
            print
            print self.type.upper() + " RESULTS:"

            keys = [e for e in self.measures if 'COUNT_' in e]
            keys.sort()
            print "Counts:"
            print_table([(entry, str(self.measures[entry])) for entry in keys])

            keys = [e for e in self.measures if 'COLLECTION_' in e]
            keys.sort()
            print
            print "Collection measures:"
            print_table([(entry, str(self.measures[entry])) for entry in keys])

            if self.response_format == "TextGrid":
                keys = [e for e in self.measures if 'TIMING_' in e]
                keys.sort()
                print
                print "Time-based measures:"
                print_table([(entry, str(self.measures[entry])) for entry in keys])

        #write to CSV file
        if self.target_file:
            with open(self.target_file, 'w') as outfile:
                header = ['file_id'] + \
                         [self.type + "_" + e for e in self.measures if 'COUNT_' in e] + \
                         [self.type + "_" + e for e in self.measures if 'COLLECTION_' in e] + \
                         [self.type + "_" + e for e in self.measures if 'TIMING_' in e]
                writer = csv.writer(outfile, quoting=csv.QUOTE_MINIMAL)
                writer.writerow(header)
                #the split/join gets rid of the type appended just above
                writer.writerow([self.measures["file_id"]] +
                                [self.measures["_".join(e.split('_')[1:])] for e in header[1:]])



def get_duration_measures(source_file_path,
                          output_path=None,
                          phonemic=False,
                          semantic=False,
                          quiet=False):
    """Parses input arguments and runs clustering algorithm.

    :param source_file_path: Required. Location of the .csv or .TextGrid file to be
        analyzed.
    :param output_path: Path to which to write the resultant csv file. If left None,
        path will be set to the source_file_path.  If set to False, no file will be
        written.
    :param phonemic: The letter used for phonetic clustering. Note: should be False if
        semantic clustering is being used.
    :param semantic: The word category used for semantic clustering. Note: should be
        False if phonetic clustering is being used.
    :param quiet: Set to True if you want to suppress output to the screen during processing.

    :return data: A dictionary of measures derived by clustering the input response.

    """

    #validate arguments here rather than where they're first passed in, in case this is used as a package
    args = Args()
    args.output_path = output_path
    args.phonemic = phonemic
    args.semantic = semantic
    args.source_file_path = source_file_path
    args.quiet = quiet
    args = validate_arguments(args)

    if args.phonemic:
        response_category = args.phonemic
        output_prefix = os.path.basename(args.source_file_path).split('.')[0] + "_vfclust_phonemic_" + args.phonemic
    elif args.semantic:
        response_category = args.semantic
        output_prefix = os.path.basename(args.source_file_path).split('.')[0] + "_vfclust_semantic_" + args.semantic
    else:
        response_category = ""
        output_prefix = ""

    if args.output_path:
        #want to output csv file
        target_file_path = os.path.join(args.output_path, output_prefix + '.csv')
    else:
        #no output to system
        target_file_path = False

    engine = VFClustEngine(response_category=response_category,
                      response_file_path=args.source_file_path,
                      target_file_path=target_file_path,
                      quiet = args.quiet
    )


    return dict(engine.measures)


def validate_arguments(args):
    """Makes sure arguments are valid, specified files exist, etc."""

    semantic_tests = ["animals"]
    phonemic_tests = ["a", "p", "s", "f"]
    #check arguments
    print
    print "Checking input...",
    if not (args.source_file_path.lower().endswith('csv') or args.source_file_path.lower().endswith('textgrid')):
        raise VFClustException('The input must be either a .TextGrid or .csv file!')
    if not os.path.isfile(args.source_file_path):
        raise VFClustException('The input file path you provided does not exist on your system!')

    #if no output path provided, write to source file path
    if args.output_path == None:
        args.output_path = args.source_path
    #if output_path is False, don't output anything
    elif args.output_path == False:
        pass
    else:
        #verify/make folders for output
        if len(args.output_path) == 0:
            args.output_path = os.path.abspath(os.path.dirname(args.source_file_path))
        try:
            if not os.path.isdir(args.output_path):
                os.mkdir(args.output_path)
        except:
            print "Error creating folder for program output. " \
                  "Make sure you have write permissions to the folder you provided. " \
                  "You can change the folder with the -o option." \
                  "The output directory will be the same as the input directory."


    #make phonemic and semantic args lower case
    if (args.semantic): args.semantic = args.semantic.lower()
    if (args.phonemic): args.phonemic = args.phonemic.lower()

    #must choose either semantic or phonemic
    if not (args.semantic or args.phonemic):
        raise VFClustException(
            "You must specify at least one phonemic or semantic test to run using -p or -s, followed by the test type.")

    #make sure semantic arguments are legit
    if args.semantic and args.semantic not in semantic_tests:
        raise VFClustException("Currently only " + ",".join(semantic_tests) + " are supported for semantic testing. " \
                                                       "You provided " + args.semantic)

    if args.phonemic and args.phonemic not in phonemic_tests:
        raise VFClustException("Currently only " + ",".join(phonemic_tests) + " are supported for phonemic testing.  " \
                                                       "You provided " + args.phonemic)

    if (args.phonemic and args.semantic):
        raise VFClustException("You must choose EITHER semantic OR phonemic clustering.")

    #make paths absolute
    args.source_file_path = os.path.abspath(args.source_file_path)
    if args.output_path:
        args.output_path = os.path.abspath(args.output_path)

    print "OK!"
    print
    print "Parsed arguments:"
    print_table([(k, str(vars(args)[k])) for k in vars(args)])

    return args

def main(test=False):
    # print "DEBUG",__name__, sys.argv
    # from "vfclust test" --> vfclust.vfclust ['/Library/Frameworks/Python.framework/Versions/2.7/bin/vfclust', 'test']
    # from "pyton vfclust.py" --> DEBUG __main__ ['vfclust.py', 'example/EXAMPLE_sem.TextGrid', '-s', 'animals']

    if test or sys.argv[1] == "test":
        test_script()
    else:

        parser = argparse.ArgumentParser()

        parser.add_argument('source_file_path',
                            help="Full path of textgrid or csv file to parse")

        parser.add_argument('-s', dest='semantic',
                            default=False,action="store",
                            help='''Usage: -s animals\n
                                If included, calculates measures for the given category \n
                                for the semantic fluency test, i.e. animals, fruits, etc.
                                ''')

        parser.add_argument('-p', dest='phonemic',
                            default=False,action='store',
                            help='''Usage: -p f\n
                                If included, calculates measures for the given category \n
                                for the phonemic fluency test, i.e. a, f, s, etc.
                                ''')

        parser.add_argument('-o', dest='output_path', default="",
                            help="Where to put output - default is the same directory as the input file working directory.")

        parser.add_argument('-q', dest='quiet', default=False, action='store_true',
                            help="Use to eliminate output (default is print everything to stdout).")

        args = parser.parse_args()

        get_duration_measures(output_path=args.output_path,
                                        phonemic=args.phonemic,
                                        semantic=args.semantic,
                                        source_file_path=args.source_file_path,
                                        quiet=args.quiet)

def test_script():
    path = os.path.abspath(os.path.join(os.path.dirname(__file__),'example'))
    example_csv = os.path.join(path,'EXAMPLE.csv')
    example_textgrid = os.path.join(path,'EXAMPLE_sem.TextGrid')
    print example_csv
    print example_textgrid
    results_csv = get_duration_measures(source_file_path = example_csv,
                                                output_path=False,
                                                phonemic='f')
    results_textgrid = get_duration_measures(source_file_path = example_textgrid,
                                                output_path=False,
                                                semantic='animals')


#if it's called as python vfclust.py, this happens
if __name__ == "__main__":
    print 'called using python vfclust.py'
    main()